"""
來源健康檢查
============

一整組來源同時失敗，站上就會少掉整個區塊，而且不會有任何錯誤 ——
抓不到只是「今天沒有」，跟「今天真的沒新聞」長得一模一樣。

所以要記住每個來源平常出多少貨，異常歸零時明講。
"""

from __future__ import annotations
import json
from collections import Counter
from datetime import date

from config import OUTPUT_DIR

_FILE = OUTPUT_DIR / "source_health.json"
KEEP_DAYS = 14


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record(items: list[dict]) -> None:
    hist = _load()
    hist[date.today().isoformat()] = dict(Counter(it["source_name"] for it in items))
    for k in sorted(hist)[:-KEEP_DAYS]:
        hist.pop(k, None)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def check(items: list[dict], expected_sources: list[str]) -> list[str]:
    """回傳警示訊息。今天掛零、但近期有出貨的來源就是異常。"""
    hist = _load()
    today = date.today().isoformat()
    now = Counter(it["source_name"] for it in items)

    past: dict[str, list[int]] = {}
    for day, counts in hist.items():
        if day == today:
            continue
        for name in expected_sources:
            past.setdefault(name, []).append(int(counts.get(name, 0)))

    alerts = []
    for name in expected_sources:
        prev = past.get(name) or []
        typical = max(prev) if prev else 0
        if now.get(name, 0) == 0 and typical >= 3:
            alerts.append(f"{name}：今天 0 則，近 {len(prev)} 次最高 {typical} 則 —— 疑似被擋或 feed 變動")
    return alerts
