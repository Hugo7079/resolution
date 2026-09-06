"""
第二段：七軸拆解（繁體中文）
============================

拿 vision.py 的英文客觀描述 + 原文，寫成拆解文。

品質不靠祈禱，靠**可驗證的輸出契約**：
模型必須另外交出一份 `concretes`（它實際引用的具體物 —— 字體名、色票、
格線欄數、尺寸、材質）。交不出四項以上就判定為空話，重寫一次；
再不行就不出這篇（README 四的紅線一）。
"""

from __future__ import annotations
import re

from config import (CATEGORIES, CATEGORY_BOUNDARY_RULES, CROSSOVER_SCOPE,
                    HISTORY_BRIEF, VISION_CFG)
from llm import chat_json, LLMError
from sanitize import verify_subject, verify_concretes
from vision import describe_images

# ─────────────────────────────────────────────────────────────
# 紅線一：禁止抽象形容詞
# 這些詞寫一百篇都一樣，讀者第三天就走。
# ─────────────────────────────────────────────────────────────
BANNED_VAGUE = [
    "和諧", "層次分明", "留白得宜", "簡潔有力", "視覺衝擊", "恰到好處",
    "細膩", "精緻", "大氣", "時尚感", "高級感", "質感十足", "極簡風格",
    "令人印象深刻", "引人入勝", "巧妙地", "完美地", "相得益彰",
    "畫龍點睛", "渾然天成", "呼之欲出", "耐人尋味", "獨具匠心",
]

# 紅線二：批評寫成取捨，不寫成評分
BANNED_JUDGEMENT = [
    "缺點", "不足之處", "做得不好", "失敗", "敗筆", "可惜", "扣分",
    "應該要改", "不夠好", "略顯", "美中不足",
]

AXES = [
    ("intent",   "意圖", "要解決什麼問題、講給誰聽"),
    ("form",     "形式", "構圖比例、格線、色彩、字體、材質 —— 此軸強制具體"),
    ("message",  "訊息", "三秒內讀到什麼、資訊層級對不對"),
    ("context",  "脈絡", "放在它的產業慣例裡，是保守還是破格"),
    ("execution", "落地", "跨媒介延展、無障礙、可生產性、成本"),
    ("tradeoff", "取捨", "得到什麼、放棄什麼"),
    ("takeaway", "可借用的一招", "明天就能用在自己案子上的具體手法"),
]

_AXES_SPEC = "\n".join(f"  {i+1}. {k}（{label}）：{desc}"
                       for i, (k, label, desc) in enumerate(AXES))

_COMMON_RULES = f"""
【紅線一 — 禁止空話】
不准使用這類抽象形容詞：{"、".join(BANNED_VAGUE[:12])} 等。
每一軸都必須引用可觀察的具體物：字體分類或名稱、色票近似 hex、格線欄數、
比例、尺寸、材質、工法、實際文案。看不出來就寫「從圖上判斷不出」，不要瞎猜。

【紅線二 — 批評寫成取捨，不寫成評分】
不准寫「哪裡做得不好」。要寫「為了得到 A，它犧牲了 B；如果目標換成 C，
這個選擇就不成立」。禁用詞：{"、".join(BANNED_JUDGEMENT[:8])} 等。
分析取捨，不打分數。

【語言】
一律繁體中文、台灣用語。來源若是簡體中文，要做用詞在地化
（介面 / 軟體 / 影片 / 專案 / 品質 / 網路 / 螢幕 / 檔案 / 程式），不要留大陸用語。

【誠實】
視覺描述來自模型讀圖，可能有誤。凡是描述裡寫 "not determinable" 的項目，
不要在拆解文裡假裝知道。
""".strip()


def _mk_context(item: dict, vision_notes: list[str]) -> str:
    notes = "\n\n".join(f"[圖 {i+1}]\n{n}" for i, n in enumerate(vision_notes)) \
        or "（沒有可用的視覺描述，請只依文字資訊撰寫，並在 concretes 誠實反映）"
    return f"""
標題：{item.get('title', '')}
來源：{item.get('source_name', '')}（{item.get('region', '')}）
連結：{item.get('url', '')}
原文摘要：
{(item.get('summary') or '')[:2000]}

── 讀圖得到的客觀視覺描述（英文，未經評價）──
{notes}
""".strip()


def _prompt_axes(item: dict, vision_notes: list[str], category: str | None,
                 mode: str, strict_retry: bool = False) -> list[dict]:
    if mode == "crossover":
        framing = ("今天是週五「跨界」—— 談設計以外的力量如何改變設計。收納範圍：\n  ‣ "
                   + "\n  ‣ ".join(CROSSOVER_SCOPE)
                   + "\n分類請填 null，跨界題不套四分類。")
    else:
        cat = CATEGORIES.get(category or "", {})
        framing = (f"今天輪到的分類是「{cat.get('label', '')}」"
                   f"（{cat.get('desc', '')}）。\n{CATEGORY_BOUNDARY_RULES}")

    extra = ""
    if strict_retry:
        extra = ("\n\n【重寫要求】上一版被判定為空話 —— 具體物不足或用了禁用詞。"
                 "這一版每一軸至少要引用一項 concretes 裡的東西，"
                 "form 軸至少兩項。寧可寫短，不要寫滿。")

    return [
        {"role": "system",
         "content": "你是資深設計評論者，替台灣讀者寫每日一件設計的拆解。"
                    "你的價值在於指出別人看不到的具體選擇，不在於稱讚。"},
        {"role": "user",
         "content": f"""{framing}

{_COMMON_RULES}{extra}

【七軸】依序寫，每軸 80–150 字：
{_AXES_SPEC}

【輸出 JSON】
{{
  "title": "繁中標題，點出這件作品最關鍵的一個選擇，不要用作品原名照抄",
  "subject": {{"name": "作品名", "designer": "設計者或工作室", "client": "業主", "year": "年份"}},
  "category": "visual_brand | interface_ux | product_object | space_env | null",
  "axes": {{ {", ".join(f'"{k}": "…"' for k, _, _ in AXES)} }},
  "concretes": ["你在文中實際引用的具體物，至少 4 項，例如 'Söhne Halbfett'、'#0B3D2E'、'12 欄格線'、'180×240mm'、'陽極處理鋁'"],
  "confidence": 0-100
}}

── 素材 ──
{_mk_context(item, vision_notes)}"""},
    ]


def _prompt_history(week_items: list[dict], strict_retry: bool = False) -> list[dict]:
    digest = "\n".join(
        f"- [{it.get('source_name','')}] {it.get('title','')}"
        for it in week_items[:60])
    extra = ("\n\n【重寫要求】上一版被判定為空話或變成維基百科條目。"
             "重寫時務必從本週某一件具體的事起手。") if strict_retry else ""
    return [
        {"role": "system",
         "content": "你是設計史寫作者，替台灣讀者寫週六的「設計史」單元。"},
        {"role": "user",
         "content": f"""今天是週六「設計史」。

{HISTORY_BRIEF}

{_COMMON_RULES}{extra}

【輸出 JSON】
{{
  "title": "繁中標題",
  "hook": "從本週哪一件實際發生的事起手（必須是下面清單裡的，寫出它）",
  "lineage": "歷史脈絡本體，400–600 字。流派／人物／風格是怎麼來的、解決了什麼問題",
  "for_beginners": "把文中最關鍵的一個術語用一句話講清楚，給完全不懂設計的人",
  "new_angle": "給圈內老手的：一個他大概沒想過的連結或反直覺的事實",
  "takeaway": "所以今天這件事該怎麼看",
  "concretes": ["文中引用的具體物：人名、年份、作品名、字體名、刊物名，至少 4 項"],
  "confidence": 0-100
}}

── 本週素材（hook 必須從這裡挑）──
{digest}"""},
    ]


# ─────────────────────────────────────────────────────────────
# 品質閘
# ─────────────────────────────────────────────────────────────
def _cited_in(concrete: str, text: str) -> bool:
    """
    具體物有沒有真的出現在這一軸的行文裡。

    不能用整串比對 —— 清單寫「白色主色調」、行文寫「主色調為白色」，
    字序一換 substring 就失敗，於是把明明很具體的文章判成空話。
    改用字元集合重疊：拆掉標點與助詞後，七成以上的字出現過就算引用。
    """
    keep = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff#]", "", concrete)
    keep = re.sub(r"[的了與和及之]", "", keep)
    if len(keep) < 2:
        return False
    chars = set(keep)
    hit = sum(1 for ch in chars if ch in text)
    return hit / len(chars) >= 0.7


def _texts_of(doc: dict) -> str:
    if "axes" in doc:
        return " ".join(str(v) for v in (doc.get("axes") or {}).values())
    return " ".join(str(doc.get(k, "")) for k in
                    ("hook", "lineage", "for_beginners", "new_angle", "takeaway"))


def quality_check(doc: dict, mode: str) -> tuple[bool, list[str]]:
    """回傳 (是否通過, 失敗原因清單)。"""
    problems: list[str] = []
    concretes = [c for c in (doc.get("concretes") or []) if str(c).strip()]
    if len(concretes) < 4:
        problems.append(f"具體物只有 {len(concretes)} 項（需 ≥4）")

    body = _texts_of(doc)
    if not body.strip():
        problems.append("內文是空的")

    hits = [w for w in BANNED_VAGUE if w in body]
    if hits:
        problems.append(f"用了抽象形容詞：{'、'.join(hits[:5])}")

    judged = [w for w in BANNED_JUDGEMENT if w in body]
    if judged:
        problems.append(f"批評寫成了評分：{'、'.join(judged[:5])}")

    if mode != "history":
        form = str((doc.get("axes") or {}).get("form", ""))
        cited = sum(1 for c in concretes if _cited_in(str(c), form))
        if cited < 2:
            problems.append(f"form 軸只引用了 {cited} 項具體物（需 ≥2）")
    else:
        if not str(doc.get("hook", "")).strip():
            problems.append("週六設計史沒有錨定本週事件（hook 是空的）")

    return (not problems), problems


# ─────────────────────────────────────────────────────────────
# 對外
# ─────────────────────────────────────────────────────────────
def build_deepdive(item: dict, mode: str, category: str | None = None,
                   week_items: list[dict] | None = None,
                   extra_images: list[str] | None = None) -> dict | None:
    """
    產一篇拆解。品質閘沒過就重寫一次，再沒過回 None（當天不出這篇）。
    """
    vision_notes: list[str] = []
    neurons = 0.0

    if mode != "history":
        urls = [u for u in ([item.get("image_url", "")] + (extra_images or [])) if u]
        if urls:
            vision_notes, neurons = describe_images(urls, VISION_CFG["max_images"])
            print(f"  讀圖 {len(vision_notes)}/{len(urls)} 張，花費 {neurons:.0f} neurons")

    for strict in (False, True):
        msgs = (_prompt_history(week_items or [], strict) if mode == "history"
                else _prompt_axes(item, vision_notes, category, mode, strict))
        try:
            doc = chat_json(msgs, temperature=0.35 if not strict else 0.15,
                            max_tokens=2600)
        except LLMError as e:
            print(f"  [deepdive] {str(e)[:120]}")
            return None

        # 事實錨定：設計者／業主／年份與具體物都必須能溯源，
        # 否則就是模型自己生的 —— 這是這個產品最危險的失誤。
        src_texts = [item.get("title", ""), item.get("summary", "")] + vision_notes
        if mode != "history":
            doc["subject"], unverified = verify_subject(doc.get("subject") or {},
                                                        " ".join(src_texts))
            if unverified:
                print(f"  [事實錨定] 原文找不到，已清空：{'、'.join(unverified)}")
        kept, unsourced = verify_concretes(doc.get("concretes") or [], src_texts)
        if unsourced:
            print(f"  [事實錨定] 具體物無法溯源，已移除：{'、'.join(map(str, unsourced))}")
        doc["concretes"] = kept

        ok, problems = quality_check(doc, mode)
        if ok:
            doc["mode"] = mode
            doc["vision_notes"] = vision_notes
            doc["neurons_used"] = round(neurons, 1)
            doc["source_url"] = item.get("url", "")
            doc["source_name"] = item.get("source_name", "")
            return doc
        print(f"  [品質閘] {'重寫後仍' if strict else ''}未過：{'；'.join(problems)}")

    return None
