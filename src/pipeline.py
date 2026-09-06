"""
每日主流程
==========

    python3 src/pipeline.py              # 當日
    python3 src/pipeline.py --date 2026-09-06

流程：
  1) 抓取（RSS + 台灣官網）
  2) 清洗（業配、招聘、亂碼）
  3) og:image 補圖
  4) 來源健康檢查
  5) 依星期決定拆解主題（四分類輪播 / 週五跨界 / 週六設計史 / 週日休息）
  6) 兩段式拆解（CF 讀圖 → gateway 寫繁中七軸）
  7) 配額挑選 + 標題在地化
  8) 寫 web/data/{date}.json 與 latest.json

失敗就是失敗：抓不到東西、或該出拆解卻出不來，一律非零離開。
沉默地產出空白比直接失敗更糟 —— 故障看起來會跟「今天真的沒東西」一模一樣。
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (BASE_DIR, OUTPUT_DIR, CATEGORIES, WEEKLY_ROTATION,
                    DEFAULT_DAYS_BACK, LANG_QUOTA)
from fetcher import fetch_all_sources, backfill_og_images
from tw_scraper import fetch_taiwan_all
from sanitize import sanitize
from source_health import record as record_health, check as check_health
from sources import SOURCES
from picker import pick_showcase, pick_industry
from translate import localise_items
from deepdive import build_deepdive

WEB_DATA = BASE_DIR / "web" / "data"
TZ = timezone(timedelta(hours=8))

# 金點得獎作品是常態展示、沒有日期，不跨日去重就會天天出現同一批
SEEN_FILE = OUTPUT_DIR / "seen_evergreen.json"
SEEN_KEEP = 200


def _load_seen() -> set[str]:
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(urls: list[str]) -> None:
    old = list(_load_seen())
    merged = (old + urls)[-SEEN_KEEP:]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")


def _week_items(date_str: str, days: int = 6) -> list[dict]:
    """週六設計史用：把本週抓過的東西全部翻出來當錨點素材。"""
    d0 = datetime.fromisoformat(date_str).date()
    out: list[dict] = []
    for i in range(1, days + 1):
        p = OUTPUT_DIR / f"raw_{(d0 - timedelta(days=i)).isoformat()}.json"
        if p.exists():
            try:
                out.extend(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    return out


# 這些來源刊的是「作品」，拆解起來有東西可看；
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


def _pick_deepdive_subject(items: list[dict], category: str | None) -> dict | None:
    """
    挑當天要拆解的那一件。

    條件：有圖、有內文。優先序是「刊作品的來源」→「分類對得上」→ 摘要長度。
    只按摘要長度排會挑到長篇評論（實測挑到一篇談奧美尾牙的懷舊文），
    那種題目拆出來是讀後感不是設計拆解。
    """
    pool = [it for it in items
            if it.get("image_url") and 120 < len(it.get("summary", "")) < 4000
            and it.get("kind") in ("media", "showcase")]
    if not pool:
        return None

    preferred = WORK_SOURCES.get(category or "", set())

    def score(it: dict) -> tuple:
        return (it.get("source_name") in preferred,
                it.get("cat_hint") == category,
                min(len(it.get("summary", "")), 1200))

    pool.sort(key=score, reverse=True)
    return pool[0]


def run(date_str: str | None = None, days_back: int = DEFAULT_DAYS_BACK) -> int:
    today = date_str or datetime.now(TZ).date().isoformat()
    weekday = datetime.fromisoformat(today).weekday()
    plan = WEEKLY_ROTATION[weekday]
    mode, category = plan["mode"], plan["category"]

    label = (CATEGORIES.get(category, {}).get("label") if category else
             {"crossover": "跨界", "history": "設計史", "rest": "休息"}[mode])
    print(f"\n===== 解析度 Resolution {today}（週{'一二三四五六日'[weekday]} · {label}）=====\n")

    if mode == "rest":
        print("週日休息 —— 不跑 pipeline，前端顯示週六產出的本週彙整。")
        return 0

    # 1–3) 抓取、清洗、補圖
    items = fetch_all_sources(days_back=days_back)
    print(f"RSS 共 {len(items)} 則")
    items.extend(fetch_taiwan_all(days_back=30, seen_winner_urls=_load_seen()))
    items, _dropped = sanitize(items)
    backfill_og_images(items)

    if len(items) < 30:
        print(f"[失敗] 只抓到 {len(items)} 則，遠低於正常量 —— 判定為抓取故障，"
              f"不要產出一份空白的當日檔。")
        return 1

    (OUTPUT_DIR / f"raw_{today}.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) 來源健康
    alerts = check_health(items, [s["name"] for s in SOURCES if s["freq"] == "daily"])
    record_health(items)
    for a in alerts:
        print(f"  ⚠ 來源異常 {a}")

    # 5–6) 拆解
    print("\n拆解中...")
    if mode == "history":
        doc = build_deepdive({}, mode="history", week_items=_week_items(today))
        subject = None
    else:
        subject = _pick_deepdive_subject(items, category)
        if subject is None:
            print("[失敗] 找不到可拆解的素材（要有圖、有內文）")
            return 1
        print(f"  題目：{subject['title'][:70]}")
        doc = build_deepdive(subject, mode=mode, category=category)

    # 拆解沒過不該讓作品流與產業動態一起陪葬 —— 那兩區不需要 LLM 讀圖，
    # 照樣有價值。當日檔照寫（deepdive 為 null，前端已能處理），
    # 但流程結束時仍然標記為失敗，讓 Actions 變紅、有人來看一眼。
    deepdive_failed = doc is None
    if deepdive_failed:
        print("[警告] 拆解沒通過品質閘 —— 今天不出這篇（寧可失敗也不出空話）。"
              "作品流與產業動態照常發布。")

    # 7) 配額挑選 + 在地化
    showcase = pick_showcase(items)
    industry = pick_industry(items)
    localise_items(showcase)
    localise_items(industry)

    non_en = sum(1 for s in showcase if s.get("region") != "en")
    print(f"\n作品流 {len(showcase)} 件（非英語圈 {non_en}）、產業動態 {len(industry)} 則")

    # 8) 寫出當日檔
    cat_id = (doc.get("category") if doc else None) or category
    day = {
        "date": today,
        "weekday_mode": mode,
        "deepdive": None if deepdive_failed else {
            "title": doc.get("title", ""),
            "subject": doc.get("subject", {}),
            "category": cat_id,
            "category_label": CATEGORIES.get(cat_id, {}).get("label", "跨界"),
            "confidence": doc.get("confidence", 0),
            "axes": doc.get("axes", {}),
            "concretes": doc.get("concretes", []),
            "source_url": (subject or {}).get("url", ""),
            "source_name": (subject or {}).get("source_name", ""),
            "image_url": (subject or {}).get("image_url", ""),
            "image_fallback": (subject or {}).get("image_fallback", ""),
            "credit": f"圖片來源：{(subject or {}).get('source_name','')}．著作權屬原作者",
        },
        "showcase": [{"title": s["title"], "title_original": s.get("title_original", ""),
                      "url": s["url"], "image_url": s["image_url"],
                      "image_fallback": s.get("image_fallback", ""),
                      "source_name": s["source_name"], "region": s["region"],
                      "category": s.get("cat_hint")} for s in showcase],
        "industry": [{"title": s["title"], "title_original": s.get("title_original", ""),
                      "url": s["url"], "source_name": s["source_name"],
                      "published": s.get("published", ""), "region": s["region"]}
                     for s in industry],
    }

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / f"{today}.json").write_text(
        json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")
    (WEB_DATA / "latest.json").write_text(
        json.dumps({"date": today}, ensure_ascii=False), encoding="utf-8")

    _save_seen([s["url"] for s in showcase
                if s.get("source_name", "").startswith("金點")])

    print(f"\n[完成] web/data/{today}.json")
    if deepdive_failed:
        print("[失敗] 當日檔已產出，但沒有拆解 —— 這是這個站的主菜，不能長期缺席。")
        return 2
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="解析度 Resolution 每日流程")
    p.add_argument("--date", help="指定日期 YYYY-MM-DD（預設今天，台灣時區）")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    sys.exit(run(p.parse_args().date, p.parse_args().days))
