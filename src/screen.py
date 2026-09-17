"""
選題初篩：這是不是一件看得到的作品
==================================

池子的排序是機械規則（來源是不是作品源、分類對不對得上、標題像不像新聞），
擋得掉清單文與校園展（pool.is_roundup），擋不掉這些：

    Autodesk's Aishwarya Balamukundan on Judging Core77's Fusion Forward
    MAKE's 2026 Animation Thesis Grant Now Open to Support the Next Generation
    Don't Know the Difference Between Brand Guidelines and a Brand Book?
    The Conversation: Heritage in Design

四則全是 2026-09-16 當下各分類的候選第一名，沒有一則是「一件看得到的作品」。
它們來自作品源、分類也對，標題句型跟作品介紹沒有兩樣 ——
再往關鍵字表裡加詞是打地鼠，加到後來還會誤殺真的作品。

所以這一關交給模型判，一天一次呼叫、只輸出 true/false 加十個字的理由。
判錯的成本很低（換下一個候選），判對的收益是主菜不再是一篇訪談。

**壞掉就原樣放行**：初篩是加分項，不該讓「今天沒有今日一件」多一個原因。
"""

from __future__ import annotations

from llm import chat_json, LLMError

_SYSTEM = ("你替一個「每天介紹一件設計」的站台篩選題目。"
           "你只判斷一件事：這一則講的是不是一件看得到的設計作品。")

_RULES = """下面每一則給你標題、來源、摘要開頭。

**是**一件看得到的作品：一張海報、一套品牌識別、一本書、一支包裝、
一把椅子、一件產品、一棟建築、一個室內或展場、一個網站或 App 介面、
一支動態影像。重點是讀者點進去看得到那個東西本身。

**不是**：訪談或對談、專欄與評論、教學與觀念文、產業新聞（收購、人事、訴訟）、
獎項徵件或評審介紹、補助與獎學金公告、活動預告與報名、求職、
工具推薦、多件作品的整理與清單。

拿不準就判 false —— 主菜寧可換一件，也不要拿一篇訪談當「今日一件」。

輸出 JSON，一則一個物件，n 對應下面的編號：
{"verdicts": [{"n": 1, "work": true, "why": "不超過十個字的理由"}]}"""


def _brief(i: int, it: dict) -> str:
    return (f"{i}. 標題：{it.get('title', '')}\n"
            f"   來源：{it.get('source_name', '')}\n"
            f"   摘要：{(it.get('summary') or '')[:200]}")


def screen_works(cands: list[dict]) -> list[dict]:
    """
    回傳「是作品」的那些，順序不動（池子的排序有它的道理，這裡只做減法）。

    全部被判掉、或呼叫失敗，一律原樣回傳 —— 沒有候選比候選不完美更糟。
    """
    if len(cands) < 2:
        return cands

    listing = "\n\n".join(_brief(i, it) for i, it in enumerate(cands, 1))
    try:
        out = chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": f"{_RULES}\n\n── 候選 ──\n{listing}"}],
            temperature=0.0, max_tokens=1600)   # 20 則 × 每則一行判定
    except LLMError as e:
        print(f"  [初篩] 跳過（{str(e)[:90]}）—— 照池子的排序走")
        return cands

    verdicts = {}
    for v in (out.get("verdicts") or []):
        if isinstance(v, dict):
            try:
                verdicts[int(v.get("n"))] = (bool(v.get("work")), str(v.get("why", "")))
            except (TypeError, ValueError):
                continue

    kept = []
    for i, it in enumerate(cands, 1):
        work, why = verdicts.get(i, (True, "初篩沒回答"))   # 沒判到的放行
        if work:
            kept.append(it)
        else:
            print(f"  [初篩] 不是一件作品（{why[:20]}）：{it.get('title', '')[:56]}")

    if not kept:
        print("  [初篩] 全部被判掉 —— 不採信，照池子的排序走")
        return cands
    return kept
