"""
抓取驗證 —— 不呼叫 LLM，只確認來源層跑得出貨。

用法：  python3 src/verify_fetch.py [days_back]
產出：  output/raw_YYYY-MM-DD.json + 終端統計
"""

from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

from config import OUTPUT_DIR, LANG_QUOTA, NON_ENGLISH_REGIONS, CHINESE_REGIONS
from fetcher import fetch_all_sources, backfill_og_images
from sources import SOURCES
from sanitize import sanitize
from source_health import record as record_health, check as check_health
from tw_scraper import fetch_taiwan_all


def main(days_back: int = 2) -> None:
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    print(f"\n===== 解析度 Resolution 抓取驗證 {today}（近 {days_back} 天）=====\n")

    items = fetch_all_sources(days_back=days_back)
    print(f"RSS 共 {len(items)} 則")

    tw = fetch_taiwan_all(days_back=30)
    items.extend(tw)

    items, dropped = sanitize(items)
    for kind, rows in dropped.items():
        for r in rows[:8]:
            print(f"    丟棄[{kind}] {r.get('_dropped','')[:30]:30s} "
                  f"{r.get('source_name','')[:14]:14s} {r.get('title','')[:38]}")

    filled = backfill_og_images(items)
    print(f"og:image 補圖：補到 {filled} 張\n")

    with_img = sum(1 for it in items if it["image_url"])
    print(f"總計 {len(items)} 則，有圖 {with_img} 則（{with_img / max(len(items),1):.0%}）\n")

    # 語區分佈
    print("── 語區分佈 ──")
    by_region = Counter(it["region"] for it in items)
    for r, n in by_region.most_common():
        img = sum(1 for it in items if it["region"] == r and it["image_url"])
        print(f"  {r:6s} {n:4d} 則   有圖 {img:4d}")

    non_en = sum(n for r, n in by_region.items() if r in NON_ENGLISH_REGIONS)
    zh = sum(n for r, n in by_region.items() if r in CHINESE_REGIONS)
    print(f"\n  非英語圈 {non_en} 則（{non_en / max(len(items),1):.0%}）、華語圈 {zh} 則")

    # 配額能不能滿足
    print("\n── 配額檢查 ──")
    show_non_en = [it for it in items if it["kind"] == "showcase"
                   and it["region"] in NON_ENGLISH_REGIONS and it["image_url"]]
    ind_zh = [it for it in items if it["kind"] == "industry"
              and it["region"] in CHINESE_REGIONS]
    q1 = LANG_QUOTA["showcase_min_non_english"]
    q2 = LANG_QUOTA["industry_min_chinese"]
    print(f"  作品流非英語圈：{len(show_non_en):3d} 件（需 ≥{q1}）  "
          f"{'✓' if len(show_non_en) >= q1 else '✗ 不足，當天寧可少放一件'}")
    print(f"  產業動態華語圈：{len(ind_zh):3d} 則（需 ≥{q2}）  "
          f"{'✓' if len(ind_zh) >= q2 else '✗ 不足，當天寧可少放一則'}")

    # 各來源出貨
    print("\n── 各來源出貨（0 則者需要注意）──")
    by_src: dict[str, list] = defaultdict(list)
    for it in items:
        by_src[it["source_name"]].append(it)
    for name, rows in sorted(by_src.items(), key=lambda x: -len(x[1])):
        img = sum(1 for r in rows if r["image_url"])
        print(f"  {name[:26]:26s} {len(rows):3d} 則   有圖 {img:3d}")

    alerts = check_health(items, [s["name"] for s in SOURCES if s["freq"] == "daily"])
    record_health(items)
    print("\n── 來源健康 ──")
    if alerts:
        for a in alerts:
            print(f"  ⚠ {a}")
    else:
        print("  正常")

    path = OUTPUT_DIR / f"raw_{today}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
