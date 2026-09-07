"""
作品池
======

原本的選題是「今天抓到什麼就從裡面挑」。那讓選題被新聞綁架 ——
好作品不會剛好每天出現在 RSS 前幾則，而當天沒用到的東西隔天就丟了。
實測結果是挑到「某邦選前活動」這種新聞稿，不是一件可以欣賞的作品。

改成池子：每天抓到的照樣進池存著，每天從**整個池子**挑今天的主角，
用過的標記起來不再出現。

三個性質：
  1. 保鮮期 POOL_MAX_AGE_DAYS（90 天）—— 不必是今天最新的，
     但不能是幾年前的老東西
  2. 越跑越厚 —— 選題品質單調上升，不會有「今天剛好沒好貨」
  3. 抓取掛掉還有貨 —— 順便解掉「RSS 掛了就整天失敗」
"""

from __future__ import annotations
import json
import re
from datetime import date, datetime, timedelta

from config import OUTPUT_DIR, POOL_MAX_AGE_DAYS, POOL_MAX_SIZE

_POOL_FILE = OUTPUT_DIR / "pool.json"

# 這些來源刊的是「作品」，介紹起來有東西可看；
# 其他來源常是產業評論或懷舊長文，硬拆會變成讀後感。
WORK_SOURCES = {
    "visual_brand":   {"Creative Review", "Logo Design Love", "Typewolf",
                       "Print Magazine", "PAGE Online", "Motionographer"},
    "interface_ux":   {"Awwwards", "Muzli", "Smashing Magazine", "UX Collective"},
    "product_object": {"Core77", "Yanko Design", "Design Milk", "Stylepark",
                       "Dutch Design Daily"},
    "space_env":      {"Dezeen", "ArchDaily", "designboom", "Wallpaper*",
                       "architecturephoto", "Abitare"},
}
_ALL_WORK_SOURCES = set().union(*WORK_SOURCES.values())

# 標題長這樣的多半是新聞、評論或活動公告，不是一件可以介紹的作品。
# 窗口放寬到 7 天之後這類東西變多了 —— 實測「Meet Fusion Forward Juror…」
# （評審介紹）排到候選第一名，因為它來自 Core77 這個作品源。
_NEWS_MARKERS = ("宣布", "收購", "併購", "任命", "離職", "訴訟", "判決", "調查",
                 "報告", "趨勢", "回顧", "專訪", "獎項公布", "入圍", "徵件",
                 "講座", "工作坊", "報名", "招募",
                 "announces", "acquires", "appoints", "lawsuit", "report",
                 "trends", "interview", "opinion", "why ", "how ", "what ",
                 "meet ", "juror", "jury", "call for", "deadline",
                 "podcast", "q&a", "webinar", "workshop", "now hiring")


def _load() -> dict:
    try:
        return json.loads(_POOL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}, "used": {}}


# 池子要跟著 repo 走 —— GitHub Actions 每次都是乾淨的機器，
# 存在 output/ 而不 commit 的話，每天的池子都只有今天抓到的那些，
# 「不限當天」這件事就整個失效了。所以它是被 commit 的（見 .gitignore 的例外）。
#
# key 排序輸出：dict 順序一變就是整份檔案的 diff，
# 每天 commit 一次的東西不能這樣搞。
def _save(pool: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _POOL_FILE.write_text(
        json.dumps(pool, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")


def pub_date(item: dict) -> date | None:
    raw = (item.get("published") or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:len(datetime.now().strftime(fmt))], fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        return None


def add(items: list[dict], today: date) -> int:
    """把今天抓到的東西併進池子。回傳新增幾則。"""
    pool = _load()
    bag = pool.setdefault("items", {})
    added = 0
    for it in items:
        url = it.get("url") or ""
        # 沒圖的東西當不了「今天介紹的這一件」—— 這是視覺媒體
        if not url or url in bag or not it.get("image_url"):
            continue
        # 只留產文用得到的欄位，而且摘要截短 —— 這份檔案每天進 git，
        # 不節制的話一年下來會把 repo 撐爆（實測 416 則就 480KB）。
        row = {k: it.get(k) for k in
               ("title", "url", "published", "source_name", "region",
                "kind", "cat_hint", "image_url", "image_fallback")}
        row["summary"] = (it.get("summary") or "")[:1200]
        row["_seen"] = today.isoformat()
        bag[url] = row
        added += 1
    _prune(pool, today)
    _save(pool)
    return added


def _prune(pool: dict, today: date) -> None:
    """砍掉過期的與用過太久的，並壓到上限。"""
    cutoff = today - timedelta(days=POOL_MAX_AGE_DAYS)
    bag = pool.get("items", {})

    for url in list(bag):
        it = bag[url]
        # 有發表日就用發表日，沒有就用第一次看到它的日子
        d = pub_date(it) or date.fromisoformat(it.get("_seen", today.isoformat()))
        if d < cutoff:
            bag.pop(url, None)

    if len(bag) > POOL_MAX_SIZE:
        # 留新的
        keep = sorted(bag.items(), key=lambda kv: kv[1].get("_seen", ""), reverse=True)
        pool["items"] = dict(keep[:POOL_MAX_SIZE])

    # 用過紀錄也不必留一輩子
    used = pool.get("used", {})
    for url, day in list(used.items()):
        if day < cutoff.isoformat():
            used.pop(url, None)


# 「5 Lamps Designed for…」「10 Best…」這種清單文是 N 件作品的集合，
# 不是一件。硬寫會變成把五個東西各講一句，每個角度都踩不到具體物。
_LISTICLE = re.compile(r"^\s*\d{1,2}\s+\S|^\s*(top|best)\s+\d", re.I)


def _looks_like_news(title: str) -> bool:
    t = title.lower()
    return bool(_LISTICLE.match(title)) or any(m in t for m in _NEWS_MARKERS)


def _score(it: dict, category: str) -> tuple:
    """
    「這是不是一件看得到的作品」，而不是「摘要有多長」。

    舊的評分只看摘要長度，所以長篇評論永遠贏過作品介紹。
    """
    src = it.get("source_name", "")
    summary = it.get("summary") or ""
    return (
        src in WORK_SOURCES.get(category, set()),   # 這一類的作品源
        it.get("cat_hint") == category,             # 分類對得上
        src in _ALL_WORK_SOURCES,                   # 至少是作品源
        not _looks_like_news(it.get("title", "")),  # 標題不像新聞
        200 < len(summary) < 3000,                  # 有內文但不是長篇評論
        min(len(summary), 1200),
    )


def candidates(category: str, n: int, today: date) -> list[dict]:
    """挑今天的候選：沒用過、有圖有內文，依「像不像一件作品」排序。"""
    pool = _load()
    used = pool.get("used", {})
    rows = [it for url, it in pool.get("items", {}).items()
            if url not in used and it.get("image_url")
            and len(it.get("summary") or "") > 120]

    rows.sort(key=lambda it: _score(it, category), reverse=True)

    # 同一家來源連續佔滿候選沒有意義：那幾篇通常長得一樣，
    # 第一篇寫不出來，其他篇多半也寫不出來。
    out, seen = [], set()
    for it in rows:
        src = it.get("source_name", "")
        if src in seen:
            continue
        seen.add(src)
        out.append(it)
        if len(out) >= n:
            break
    return out


def mark_used(url: str, today: date) -> None:
    pool = _load()
    pool.setdefault("used", {})[url] = today.isoformat()
    _save(pool)


def stats() -> dict:
    pool = _load()
    return {"總數": len(pool.get("items", {})), "用過": len(pool.get("used", {}))}
