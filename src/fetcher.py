"""
抓取層
======

  ‣ fetch_rss(source)      — 單一 feed，含圖片抽取
  ‣ fetch_all_sources()    — 平行抓 sources.SOURCES
  ‣ fetch_og_image(url)    — feed 沒圖時 fallback 抓 og:image

取圖順序（README 六）：
  1. <enclosure> type=image
  2. media:content / media:thumbnail
  3. 內文 content:encoded 的第一張 <img>
  4. fallback：抓文章頁 og:image

完全不使用 AI 生成圖。
"""

from __future__ import annotations
import html
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # noqa: F401  (feedparser 內部用)
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser  # type: ignore

from config import (FETCH_TIMEOUT, MAX_PER_SOURCE, USER_AGENT,
                    LOW_FREQ_DAYS, LOW_FREQ_MAX)
from sources import SOURCES

# 少數站台憑證設定有問題，但內容本身可信 —— 只在抓取時放寬
_LAX = ssl.create_default_context()
_LAX.check_hostname = False
_LAX.verify_mode = ssl.CERT_NONE

# 追蹤像素、佔位圖、頭像 —— 抓到這些等於沒圖
_JUNK_IMG = re.compile(
    r"(feedburner|feedblitz|gravatar|pixel|spacer|blank\.gif|1x1|avatar|"
    r"doubleclick|googletagmanager|/emoji/|badge|button)",
    re.I,
)


def _get(url: str, timeout: int = FETCH_TIMEOUT) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/rss+xml,application/xml,text/xml,text/html,*/*",
                 "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.6,ko;q=0.5"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_LAX) as resp:
        return resp.read()


def _strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _parse_published(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    raw = entry.get("published") or entry.get("updated") or ""
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


# CMS 會把尺寸寫進檔名（mad-lucas-museum-411x274.jpg）。
# feed 給的常常是這種縮圖，拿來當主視覺對設計媒體來說不能接受，
# 也讀不出字體特徵。去掉後綴就是原圖。
_SIZE_SUFFIX = re.compile(
    r"-(\d{2,4})x(\d{2,4})(?=\.(?:jpe?g|png|webp)(?:$|\?))", re.I)


def upgrade_image_url(url: str) -> str:
    """把 CMS 縮圖網址換成原圖。判斷不出來就原樣回傳。"""
    m = _SIZE_SUFFIX.search(url or "")
    if m and max(int(m.group(1)), int(m.group(2))) < 1000:
        return _SIZE_SUFFIX.sub("", url)
    return url


def _clean_img_url(u: str, base: str = "") -> str:
    if not u:
        return ""
    u = html.unescape(u.strip())
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/") and base:
        u = urllib.parse.urljoin(base, u)
    # 站台走 HTTPS，http 圖片會被當成混合內容擋掉
    if u.startswith("http://"):
        u = "https://" + u[7:]
    if not u.startswith("https://"):
        return ""
    return "" if _JUNK_IMG.search(u) else u


def extract_image(entry, base: str = "") -> tuple[str, str]:
    """回傳 (image_url, 來源方式)。抓不到回 ("", "")。"""
    # 1. enclosure
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            u = _clean_img_url(link.get("href", ""), base)
            if u:
                return u, "enclosure"

    # 2. media:content / media:thumbnail（取最大張）
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key) or []
        best, best_w = "", -1
        for m in media:
            if m.get("type") and not str(m["type"]).startswith("image"):
                continue
            u = _clean_img_url(m.get("url", ""), base)
            if not u:
                continue
            try:
                w = int(m.get("width") or 0)
            except (TypeError, ValueError):
                w = 0
            if w > best_w:
                best, best_w = u, w
        if best:
            return best, key.replace("_", ":")

    # 3. 內文第一張 <img>
    body = ""
    if entry.get("content"):
        body = entry["content"][0].get("value", "") or ""
    body = body or entry.get("summary", "") or ""
    for m in re.finditer(r"<img[^>]+?src=[\"']([^\"']+)[\"']", body, re.I):
        u = _clean_img_url(m.group(1), base)
        if u:
            return u, "inline"

    return "", ""


_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image)["\']'
    r'[^>]+content=["\']([^"\']+)["\']', re.I)
_OG_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)='
    r'["\'](?:og:image(?::secure_url)?|twitter:image)["\']', re.I)


def fetch_og_image(url: str) -> str:
    """抓文章頁的 og:image。只讀前 120KB —— meta 一定在 <head>。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=_LAX) as resp:
            head = resp.read(120_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    for rx in (_OG_RE, _OG_RE_REV):
        m = rx.search(head)
        if m:
            return _clean_img_url(m.group(1), url)
    return ""


def fetch_rss(source: dict, days_back: int = 2, _retry: bool = True) -> list[dict]:
    """單一 feed → items。低頻源套 LOW_FREQ_DAYS 的寬鬆時間窗。"""
    name, url = source["name"], source["url"]
    try:
        raw = _get(url)
    except Exception as e:
        if _retry:
            # 短時間內重複抓同一批來源容易被限速，退避一次多半就回來了
            time.sleep(3)
            return fetch_rss(source, days_back, _retry=False)
        print(f"  [warn] {name} 抓取失敗: {type(e).__name__}: {str(e)[:60]}")
        return []

    feed = feedparser.parse(raw)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    # 低頻源久久才更新一次，套當日窗會永遠是空的；但也不能完全不套 ——
    # 不套的話它們出貨量反而最大（全是舊文），會直接灌爆版面。
    is_low = source.get("freq") == "low"
    low_cutoff = now - timedelta(days=LOW_FREQ_DAYS)
    base = f"{urllib.parse.urlsplit(url).scheme}://{urllib.parse.urlsplit(url).netloc}"

    items: list[dict] = []
    for entry in feed.entries[:MAX_PER_SOURCE * 3]:
        link = (entry.get("link") or "").strip()
        title = _strip_html(entry.get("title", ""))
        if not link or not title:
            continue

        pub = _parse_published(entry)
        if pub and pub < (low_cutoff if is_low else cutoff):
            continue

        img, img_from = extract_image(entry, base)
        # 原圖給版面用，縮圖留著當 onerror fallback（去後綴不一定存在）
        img_full = upgrade_image_url(img)
        # tags 是業配偵測的主要訊號（Dezeen 的 Promotions /
        # "Do not show on the Homepage" 只出現在這裡，標題和內文都看不出來）
        tags = [str(t.get("term", "")).strip()
                for t in (entry.get("tags") or []) if t.get("term")]
        items.append({
            "title":       title,
            "url":         link,
            "summary":     _strip_html(entry.get("summary", ""))[:1200],
            "published":   pub.isoformat() if pub else "",
            "source_name": name,
            "region":      source["region"],
            "kind":        source["kind"],
            "cat_hint":    source.get("cat"),
            "image_url":      img_full,
            "image_fallback": img if img_full != img else "",
            "image_from":     img_from,
            "tags":           tags[:12],
        })
        if len(items) >= (LOW_FREQ_MAX if is_low else MAX_PER_SOURCE):
            break
    return items


def backfill_og_images(items: list[dict], max_workers: int = 8, limit: int = 60) -> int:
    """替沒抓到圖的條目補 og:image。limit 控制成本，只補前 N 則。"""
    targets = [it for it in items if not it["image_url"]][:limit]
    if not targets:
        return 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for it, img in zip(targets, ex.map(lambda x: fetch_og_image(x["url"]), targets)):
            if img:
                it["image_url"], it["image_from"] = img, "og"
    return sum(1 for it in targets if it["image_url"])


def fetch_all_sources(days_back: int = 2,
                      only_kinds: set[str] | None = None,
                      include_low_freq: bool = True,
                      max_workers: int = 12) -> list[dict]:
    srcs = [s for s in SOURCES
            if (only_kinds is None or s["kind"] in only_kinds)
            and (include_low_freq or s["freq"] == "daily")]

    print(f"抓取 {len(srcs)} 個來源（近 {days_back} 天）...")
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for batch in ex.map(lambda s: fetch_rss(s, days_back), srcs):
            out.extend(batch)

    # URL 去重
    seen, uniq = set(), []
    for it in out:
        u = it["url"].split("?")[0]
        if u in seen:
            continue
        seen.add(u)
        uniq.append(it)
    return uniq
