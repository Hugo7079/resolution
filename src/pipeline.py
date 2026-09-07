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
  5) 入池 + 從池子挑今天的主角（不限當天抓到的）
  6) 兩段式產文（CF 讀圖 → LLM 寫繁中三層漏斗）
  7) 配額挑選 + 標題在地化
  8) 寫 web/data/{date}.json 與 latest.json

失敗就是失敗：抓不到東西、或該出的那一件出不來，一律非零離開。
沉默地產出空白比直接失敗更糟 —— 故障看起來會跟「今天真的沒東西」一模一樣。
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (BASE_DIR, OUTPUT_DIR, CATEGORIES, DEFAULT_DAYS_BACK,
                    DEEPDIVE_TRIES, LANG_QUOTA, category_of_day)
from fetcher import fetch_all_sources, backfill_og_images
from tw_scraper import fetch_taiwan_all
from sanitize import sanitize
from source_health import record as record_health, check as check_health
from sources import SOURCES
from picker import pick_showcase, pick_industry
from translate import localise_items
from feature import build_feature
from vision import disabled_reason as vision_disabled_reason
import pool

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


def _failure_reason(diag: dict) -> str:
    if diag.get("vision_error"):
        return f"讀圖不可用：{diag['vision_error']}"
    if diag.get("llm_error"):
        return f"文字模型失敗：{diag['llm_error']}"
    if diag.get("problems"):
        return f"品質閘沒過：{'；'.join(diag['problems'])}"
    return "未知原因"


def run(date_str: str | None = None, days_back: int = DEFAULT_DAYS_BACK) -> int:
    today = date_str or datetime.now(TZ).date().isoformat()
    today_d = datetime.fromisoformat(today).date()
    weekday = today_d.weekday()
    category = category_of_day(today_d)
    label = CATEGORIES[category]["label"]
    print(f"\n===== 解析度 Resolution {today}（週{'一二三四五六日'[weekday]} · {label}）=====\n")

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

    # 進作品池。今天挑的主角來自整個池子（90 天內），不限今天抓到的 ——
    # 好作品不會剛好每天出現在 RSS 前幾則。
    added = pool.add(items, today_d)
    st = pool.stats()
    print(f"入池 +{added}，池內可選 {st['總數'] - st['用過']} 件")

    # 4) 來源健康
    alerts = check_health(items, [s["name"] for s in SOURCES if s["freq"] == "daily"])
    record_health(items)
    for a in alerts:
        print(f"  ⚠ 來源異常 {a}")

    # 5–6) 今日一件
    print("\n今日一件...")
    diag: dict = {}
    subject = None
    doc = None
    candidates = pool.candidates(category, DEEPDIVE_TRIES, today_d)
    if not candidates:
        print("[失敗] 池子裡沒有可介紹的作品（要有圖、有內文、沒用過）")
        return 1

    warned_no_vision = False
    for i, cand in enumerate(candidates, 1):
        print(f"  題目 {i}/{len(candidates)}：{cand['title'][:70]}"
              f"（{cand.get('source_name', '')}）")
        diag = {}
        doc = build_feature(cand, category=category, diag=diag)
        if doc is not None:
            subject = cand
            pool.mark_used(cand.get("url", ""), today_d)
            break
        print(f"  → 這題出不來（{_failure_reason(diag)}），換下一個候選")
        # 讀圖整條斷掉時後面的候選只能靠純文字 —— 還是值得跑（原文夠厚
        # 就過得了閘），但要講明白接下來是在什麼條件下跑的。
        if vision_disabled_reason() and not warned_no_vision:
            print(f"  [注意] 讀圖已停用（{vision_disabled_reason()}），"
                  f"剩下的候選只用原文文字撰寫")
            warned_no_vision = True

    # 主角沒出來不該讓作品流與產業動態一起陪葬 —— 那兩區不需要 LLM 讀圖，
    # 照樣有價值。當日檔照寫（feature 為 null，前端已能處理），
    # 但流程結束時仍然標記為失敗，讓 Actions 變紅、有人來看一眼。
    feature_failed = doc is None
    reason = _failure_reason(diag) if feature_failed else ""
    if feature_failed:
        print(f"[警告] 今天不出這一件（寧可失敗也不出空話）——「{reason}」。"
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
        "category": cat_id,
        "feature": None if feature_failed else {
            "title": doc.get("title", ""),
            "subject": doc.get("subject", {}),
            "category": cat_id,
            "category_label": CATEGORIES.get(cat_id, {}).get("label", ""),
            "confidence": doc.get("confidence", 0),
            "hook": doc.get("hook", ""),
            "what_it_is": doc.get("what_it_is", ""),
            "angles": doc.get("angles", []),
            "takeaway_everyone": doc.get("takeaway_everyone", ""),
            "takeaway_designer": doc.get("takeaway_designer", ""),
            "glossary": doc.get("glossary", []),
            "concretes": doc.get("concretes", []),
            "source_url": (subject or {}).get("url", ""),
            "source_name": (subject or {}).get("source_name", ""),
            "published": (subject or {}).get("published", ""),
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
    if feature_failed:
        print(f"[失敗] 當日檔已產出，但沒有今天這一件 —— 這是這個站的主菜，"
              f"不能長期缺席。原因：{reason}")
        # 讓 Actions 的錯誤訊息能講出原因，不必翻整份 log。
        # ::error:: 只吃單行，CF 的原始回覆又可能帶換行，所以壓成一行再截斷。
        (OUTPUT_DIR / "last_failure.txt").write_text(
            " ".join(reason.split())[:300], encoding="utf-8")
        return 2
    (OUTPUT_DIR / "last_failure.txt").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="解析度 Resolution 每日流程")
    p.add_argument("--date", help="指定日期 YYYY-MM-DD（預設今天，台灣時區）")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    sys.exit(run(p.parse_args().date, p.parse_args().days))
