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


def check(items: list[dict], expected_sources: list[str],
          fetch_result: dict[str, str] | None = None) -> list[str]:
    """
    回傳警示訊息。

    分兩種，因為處置方式完全不同：
      ‣ 抓不到（403／timeout）—— 真的故障，要去看是不是被 CDN 擋
      ‣ 抓到了但 0 則      —— 這家今天沒發文。歐美媒體週末不發，
                              週一早上一次跳出七八個來源是正常的，不是故障
    先前兩者共用一句「疑似被擋」，害人往錯的方向查。
    """
    hist = _load()
    today = date.today().isoformat()
    now = Counter(it["source_name"] for it in items)

    past: dict[str, list[int]] = {}
    for day, counts in hist.items():
        if day == today:
            continue
        for name in expected_sources:
            past.setdefault(name, []).append(int(counts.get(name, 0)))

    fetch_result = fetch_result or {}
    alerts, quiet = [], []
    for name in expected_sources:
        if now.get(name, 0) > 0:
            continue
        got = fetch_result.get(name, "")
        if got and got != "ok":
            alerts.append(f"[抓取失敗] {name}：{got} —— 檢查是不是被 CDN 擋")
            continue
        prev = past.get(name) or []
        typical = max(prev) if prev else 0
        if typical >= 3:
            quiet.append(name)

    if quiet:
        alerts.append(f"[今天沒發文] {len(quiet)} 個來源抓得到但 0 則："
                      f"{'、'.join(quiet[:8])}{' 等' if len(quiet) > 8 else ''}")
    return alerts
