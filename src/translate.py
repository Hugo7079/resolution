"""
標題在地化
==========

站上一律繁體中文、台灣用語。來源橫跨英／日／韓／德／法／西／簡中，
所以列表區塊（產業動態、作品流）的標題都要翻過，不能直接把原文丟給讀者。

兩件事一起做：
  ‣ 外文 → 繁體中文
  ‣ 簡中 → 繁中「並且」在地化用詞（界面→介面、软件→軟體、视频→影片）

原文一律保留在 title_original，前端可以在需要時顯示，
而且出了問題可以追回去對照 —— 翻譯是會出錯的，要留得住原始證據。

批次送、一次一批，因為標題短、逐則呼叫純粹浪費額度。
"""

from __future__ import annotations
import json

from llm import chat_json, LLMError

BATCH = 12

_SYSTEM = "你是把設計產業標題翻成台灣繁體中文的譯者。只翻譯，不評論、不加油添醋。"

_RULES = """
規則：
1. 輸出繁體中文、台灣用語。簡中來源要在地化用詞：
   界面→介面、软件→軟體、视频→影片、项目→專案、质量→品質、
   网络→網路、屏幕→螢幕、文件→檔案、程序→程式、设计师→設計師。
2. 專有名詞（品牌、工作室、人名、產品名、獎項名）**保留原文**，不要音譯。
   例：「Dezeen」不要翻成「德真」，「Pentagram」不要翻成「五角星」。
3. 標題就是標題，不要擴寫、不要補上原文沒有的形容詞、不要加句號。
4. 已經是繁體中文的，原樣輸出。
5. 看不懂或無法確定意思時，原樣輸出，不要猜。
"""


def translate_titles(titles: list[str]) -> list[str]:
    """回傳與輸入等長的繁中標題。任何失敗都退回原文，不讓翻譯失敗擋掉出刊。"""
    if not titles:
        return []
    out: list[str] = []
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        payload = json.dumps({str(n): t for n, t in enumerate(chunk)}, ensure_ascii=False)
        try:
            got = chat_json([
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"{_RULES}\n\n"
                                            f"把下面每一則翻成繁體中文，用同樣的 key 回一個 JSON 物件：\n{payload}"},
            ], temperature=0.1, max_tokens=1600)
        except (LLMError, Exception) as e:  # noqa: BLE001
            print(f"  [translate] 失敗，該批退回原文：{str(e)[:90]}")
            out.extend(chunk)
            continue
        for n, original in enumerate(chunk):
            val = str(got.get(str(n), "") or "").strip()
            # 翻出來異常長或空的，退回原文 —— 多半是模型自己擴寫了
            out.append(val if val and len(val) <= len(original) * 3 + 30 else original)
    return out


def localise_items(items: list[dict], field: str = "title") -> list[dict]:
    """就地翻譯一批條目，原文留在 {field}_original。"""
    if not items:
        return items
    translated = translate_titles([str(it.get(field, "")) for it in items])
    for it, zh in zip(items, translated):
        original = str(it.get(field, ""))
        if zh != original:
            it[f"{field}_original"] = original
            it[field] = zh
    return items
