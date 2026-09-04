"""
台灣官網 HTML 抓取
==================

繁中的 RSS 幾乎全滅（見 sources.DEAD_FEEDS），台灣內容只能從官網直接抓。
這些站更新低頻但價值高，一天跑一次即可（不必每次 pipeline 都跑）。

目前兩個目標，都用 schema.org microdata，結構乾淨：

  ‣ 台灣設計研究院 TDRI
      /zh-TW/news          最新消息（.post-card，含 datePublished）
      /zh-TW/trends_watchs 趨勢觀察（同結構，品質特別好）

  ‣ 金點設計獎 Golden Pin
      /                              首頁消息（.post-item）
      /goldenpin/zh-TW/winners       得獎作品庫（.gallery-item，一頁 50 件）

金點的得獎作品庫是繁中作品流的主力 —— 有圖、有標題、品質有得獎背書。
但它是常態展示、沒有日期，所以**必須跨日去重**，否則會天天出現同一批。

注意：台灣設計館 tdm.org.tw 雖然有 WordPress RSS，但網站已遭 SEO spam 佔領
（feed 內容是「工業廠房貸款」「燒賣批發」），見 sources.BLOCKLIST，不要加回來。
"""

from __future__ import annotations
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup  # type: ignore

from config import FETCH_TIMEOUT, USER_AGENT

_LAX = ssl.create_default_context()
_LAX.check_hostname = False
_LAX.verify_mode = ssl.CERT_NONE

TDRI_BASE = "https://www.tdri.org.tw"
GP_BASE = "https://www.goldenpin.org.tw"


def _soup(url: str) -> BeautifulSoup | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-TW,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=_LAX) as resp:
            return BeautifulSoup(resp.read(), "html.parser")
    except Exception as e:
        print(f"  [warn] {url} 抓取失敗: {type(e).__name__}: {str(e)[:60]}")
        return None


def _abs(base: str, u: str) -> str:
    return urllib.parse.urljoin(base, u) if u else ""


def _txt(node) -> str:
    return re.sub(r"\s+", " ", node.get_text()).strip() if node else ""


# ─────────────────────────────────────────────────────────────
# 台灣設計研究院
# ─────────────────────────────────────────────────────────────
def fetch_tdri(days_back: int = 30) -> list[dict]:
    """TDRI 最新消息 + 趨勢觀察。更新低頻，days_back 預設放寬到 30 天。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    out: list[dict] = []
    seen: set[str] = set()

    for path in ("/zh-TW/news", "/zh-TW/trends_watchs"):
        s = _soup(TDRI_BASE + path)
        if not s:
            continue
        for card in s.select(".post-card"):
            a = card.select_one("a[href]")
            if not a:
                continue
            url = _abs(TDRI_BASE, a["href"])
            if url in seen:
                continue

            # <span itemprop="datePublished" content="2026-09-01 10:00:00 +0800">
            pub = None
            dnode = card.select_one('[itemprop="datePublished"]')
            raw = (dnode.get("content") if dnode else "") or _txt(dnode)
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw or "")
            if m:
                pub = datetime(*map(int, m.groups()), tzinfo=timezone.utc)
                if pub < cutoff:
                    continue

            img = card.select_one("img")
            seen.add(url)
            out.append({
                "title":       _txt(card.select_one(".post-card-title")),
                "url":         url,
                "summary":     _txt(card.select_one(".intro"))[:1200],
                "published":   pub.isoformat() if pub else "",
                "source_name": "台灣設計研究院",
                "region":      "zh-tw",
                "kind":        "industry",
                "cat_hint":    None,
                "image_url":   _abs(TDRI_BASE, img.get("src", "")) if img else "",
                "image_from":  "html" if img else "",
                "tw_tag":      _txt(card.select_one(".post-tag")),
            })
    return [it for it in out if it["title"]]


# ─────────────────────────────────────────────────────────────
# 金點設計獎
# ─────────────────────────────────────────────────────────────
def fetch_goldenpin_news() -> list[dict]:
    s = _soup(GP_BASE)
    if not s:
        return []
    out = []
    for art in s.select(".post-item"):
        a = art.select_one("a[href]")
        if not a:
            continue
        img = art.select_one("img")
        out.append({
            "title":       _txt(art.select_one(".post-title")) or a.get("title", ""),
            "url":         _abs(GP_BASE, a["href"]),
            "summary":     _txt(art.select_one(".desc"))[:1200],
            "published":   "",          # 首頁卡片不帶日期
            "source_name": "金點設計獎",
            "region":      "zh-tw",
            "kind":        "industry",
            "cat_hint":    None,
            "image_url":   img.get("src", "") if img else "",
            "image_from":  "html" if img else "",
        })
    return [it for it in out if it["title"]]


def fetch_goldenpin_winners(exclude_urls: set[str] | None = None,
                            limit: int = 20) -> list[dict]:
    """
    得獎作品庫 —— 繁中作品流的主力。

    這是常態展示、沒有日期，天天抓會拿到同一批，
    所以 exclude_urls 傳入「已經出現過的」，跨日去重。
    """
    exclude = exclude_urls or set()
    s = _soup(GP_BASE)
    if not s:
        return []
    out = []
    for item in s.select(".gallery-item"):
        a = item.select_one("a[href]")
        if not a:
            continue
        url = _abs(GP_BASE, a["href"])
        if url in exclude:
            continue
        img = item.select_one("img")
        out.append({
            "title":       _txt(item.select_one(".info-overlay")) or a.get("title", ""),
            "url":         url,
            "summary":     "",
            "published":   "",
            "source_name": "金點設計獎 得獎作品",
            "region":      "zh-tw",
            "kind":        "showcase",
            "cat_hint":    None,
            "image_url":   img.get("src", "") if img else "",
            "image_from":  "html" if img else "",
            "evergreen":   True,        # 無日期，靠 exclude_urls 跨日去重
        })
        if len(out) >= limit:
            break
    return [it for it in out if it["title"] and it["image_url"]]


def fetch_taiwan_all(days_back: int = 30,
                     seen_winner_urls: set[str] | None = None) -> list[dict]:
    items = fetch_tdri(days_back) + fetch_goldenpin_news() \
        + fetch_goldenpin_winners(seen_winner_urls)
    print(f"台灣官網抓取：{len(items)} 則")
    return items
