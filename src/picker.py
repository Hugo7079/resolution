"""
配額挑選
========

（檔名不能叫 select.py —— 會蓋掉 Python 標準函式庫的 select 模組，
  連 socket 都會跟著壞。）

英語圈來源量是其他語區總和的三倍以上，放任自然排序站上會變成 90% 英文，
那就失去做這個站的意義（README 五之二）。

兩條規則：
  1. 跨來源輪流取 —— 直接取前 N 則會讓整區都來自同一家
  2. 硬性語言配額 —— 不足時「寧可少放一件」，不要用英文源補滿。
     版面短一格沒人會發現，連續兩週全英文讀者會發現。
"""

from __future__ import annotations
from collections import defaultdict

from config import LANG_QUOTA, NON_ENGLISH_REGIONS, CHINESE_REGIONS


def round_robin(rows: list[dict], n: int, key: str = "source_name") -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key, "")].append(r)
    out: list[dict] = []
    i = 0
    while len(out) < n and any(len(v) > i for v in buckets.values()):
        for v in buckets.values():
            if i < len(v) and len(out) < n:
                out.append(v[i])
        i += 1
    return out


def _with_quota(rows: list[dict], total: int, need: int,
                regions: set[str], label: str) -> list[dict]:
    """先把配額名額填滿，剩下的位置再輪流取。"""
    quota_pool = [r for r in rows if r.get("region") in regions]
    picked = round_robin(quota_pool, need)

    if len(picked) < need:
        print(f"  [配額] {label} 只湊到 {len(picked)}/{need} 則 —— "
              f"少放 {need - len(picked)} 格，不用其他語區補滿")

    chosen_urls = {r.get("url") for r in picked}
    rest = [r for r in rows if r.get("url") not in chosen_urls]
    picked += round_robin(rest, total - len(picked))
    return picked


def pick_showcase(rows: list[dict], total: int | None = None) -> list[dict]:
    total = total or LANG_QUOTA["showcase_total"]
    rows = [r for r in rows if r.get("kind") == "showcase" and r.get("image_url")]
    return _with_quota(rows, total, LANG_QUOTA["showcase_min_non_english"],
                       NON_ENGLISH_REGIONS, "作品流非英語圈")


def pick_industry(rows: list[dict], total: int | None = None) -> list[dict]:
    total = total or LANG_QUOTA["industry_total"]
    rows = [r for r in rows if r.get("kind") == "industry" and len(r.get("title", "")) > 12]
    return _with_quota(rows, total, LANG_QUOTA["industry_min_chinese"],
                       CHINESE_REGIONS, "產業動態華語圈")
