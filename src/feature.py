"""
每日一件：三層漏斗
==================

拿 vision.py 的英文客觀描述 + 原文，寫成一篇「介紹一件設計」。

結構不是七個並列的軸 —— 那是寫給同行看的評論，圈外人不知道從哪進去。
改成有順序的三層：

  一、先看見    hook + what_it_is    零術語，三秒決定要不要往下讀
  二、多角度欣賞 angles（3–5 個）     每個角度強制配一句白話「所以呢」
  三、帶走      takeaway ×2          給所有人一份、給設計師一份

「所以呢」是這個站的樞紐。它把「洋紅配螢光綠」這種觀察，
翻譯成讀者自己生活裡用得上的東西。少了它，這就只是一篇專業評論。

品質不靠祈禱，靠**可驗證的輸出契約**：
  ‣ concretes：模型必須交出它實際引用的具體物，少於四項判定為空話
  ‣ glossary：用了術語就要有白話解釋，入口與出口一個術語都不准出現
交不出來就重寫一次，再不行就換下一個候選（見 pipeline）。
"""

from __future__ import annotations
import re

from config import (CATEGORIES, CATEGORY_BOUNDARY_RULES, JARGON, LENSES,
                    VISION_CFG)
from llm import chat_json, LLMError
from sanitize import (simplified_leftovers, to_traditional,
                      verify_concretes, verify_subject)
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

# 紅線三：「給所有人的帶走」不准預設讀者是設計師。
# 非設計的人沒有案子、沒有客戶、不會開 Figma —— 對他們講這些，
# 這一段就等於不存在。
BANNED_ASSUMES_DESIGNER = [
    "你的案子", "你的專案", "你的設計", "下次設計", "做設計時",
    "提案時", "跟客戶", "你的作品集", "設計稿",
]

_LENS_SPEC = "\n".join(f"  {k}（{label}）：{desc}"
                       for k, (label, desc) in LENSES.items())

_COMMON_RULES = f"""
【這個站是什麼】
每天介紹一件設計，讀者有兩種，必須同時餵飽：
  A. 不懂設計、但想認識的人 —— 他要的是「原來可以這樣看東西」
  B. 圈內人 —— 他要的是「這個觀察我沒想到」
你是引路人，不是評審。目標是讓人**看見**，不是替作品打分數。

【紅線一 — 禁止空話】
不准使用這類抽象形容詞：{"、".join(BANNED_VAGUE[:12])} 等。
每個角度都必須引用可觀察的具體物：字體分類或名稱、色票近似 hex、
格線欄數、比例、尺寸、材質、工法、實際文案。
看不出來就寫「從圖上判斷不出」，不要瞎猜。

【紅線二 — 批評寫成取捨，不寫成評分】
不准寫「哪裡做得不好」。要寫「為了得到 A，它犧牲了 B；如果目標換成 C，
這個選擇就不成立」。禁用詞：{"、".join(BANNED_JUDGEMENT[:8])} 等。

【紅線三 — 術語要翻譯】
下面這些是設計術語：
{"、".join(JARGON[:40])}…等
  ‣ hook 和 takeaway_everyone **一個都不准出現** —— 那是入口和出口
  ‣ angles 裡可以用，但每個用到的術語都要進 glossary，
    用一句話講給完全不懂的人聽
  ‣ takeaway_everyone 不准預設讀者是設計師（他沒有案子、沒有客戶）

【語言與格式】
一律繁體中文、台灣用語。
**專有名詞保留原文，不要音譯**：品牌、工作室、人名、產品名、獎項名、字體名一律照抄。
  ‣ 對：Studio Gorm、Pentagram、Dezeen、Söhne Halbfett、Norm Architects
  ‣ 錯：約翰運希·阿恩特、五角星、德真
不確定怎麼寫就照抄原文，音譯出來的名字讀者查不到，等於假資訊。
輸出純文字，不要用 markdown —— 不要 **粗體**、不要 # 標題、不要 1. 2. 3. 條列。
前端是直接把字放上版面的，符號會原樣印出來。來源若是簡體中文，要做用詞在地化
（介面 / 軟體 / 影片 / 專案 / 品質 / 網路 / 螢幕 / 檔案 / 程式）。

【誠實】
視覺描述來自模型讀圖，可能有誤。凡是描述裡寫 "not determinable" 的項目，
不要在文章裡假裝知道。原文和圖上都沒有的東西，不要生出來。
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


def _prompt(item: dict, vision_notes: list[str], category: str | None,
            strict_retry: bool = False, problems: list[str] | None = None) -> list[dict]:
    cat = CATEGORIES.get(category or "", {})
    framing = (f"今天輪到的分類是「{cat.get('label', '')}」"
               f"（{cat.get('desc', '')}）。\n{CATEGORY_BOUNDARY_RULES}")

    extra = ""
    if strict_retry:
        why = ("；".join(problems or []))[:300]
        extra = (f"\n\n【重寫要求】上一版沒過，原因：{why}。"
                 "這一版每個角度至少引用一項 concretes 裡的東西，"
                 "其中至少一個角度要引用兩項。寧可寫短，不要寫滿。")

    return [
        {"role": "system",
         "content": "你替台灣讀者寫每日一件設計的導覽。你的價值在於"
                    "讓人看見自己原本看不見的東西，並且讓完全不懂設計的人也跟得上。"},
        {"role": "user",
         "content": f"""{framing}

{_COMMON_RULES}{extra}

【可用的角度（鏡頭）】挑 3–5 個**這件作品真的談得動**的，不要硬套：
{_LENS_SPEC}

對一張海報硬談「用什麼做的」、對一張椅子硬談「三秒讀到什麼」，
出來的都是廢話。談不動就不要選那個鏡頭。

【輸出 JSON】
{{
  "title": "繁中標題，點出這件作品最關鍵的一個選擇，不要照抄作品原名",
  "subject": {{"name": "作品名", "designer": "設計者或工作室", "client": "業主", "year": "年份"}},
  "category": "visual_brand | interface_ux | product_object | space_env",
  "hook": "一句話（40–60 字）：這件東西在做什麼、為什麼值得停下來看三秒。零術語。",
  "what_it_is": "這是什麼（60–100 字）：品類、誰做的、給誰用的、什麼時候的事。零術語。",
  "angles": [
    {{"lens": "上面清單裡的代號",
      "body": "90–140 字的觀察，必須引用具體物",
      "so_what": "一句話（30–50 字）白話：這個觀察對不懂設計的人代表什麼。"
                 "每個角度的 so_what 句型要不一樣，不要每句都用同一個開頭"}}
  ],
  "takeaway_everyone": "80–120 字：下次在生活裡看到什麼，可以用今天這雙眼睛看。不必是設計師才做得到。零術語。",
  "takeaway_designer": "80–120 字：一個明天就能用在自己案子上的具體手法。",
  "glossary": [{{"term": "文中用到的術語", "plain": "一句話白話解釋"}}],
  "concretes": ["你在文中實際引用的具體物，至少 4 項，例如 'Söhne Halbfett'、'#0B3D2E'、'12 欄格線'、'180×240mm'、'陽極處理鋁'"],
  "confidence": 0-100
}}

── 素材 ──
{_mk_context(item, vision_notes)}"""},
    ]


# ─────────────────────────────────────────────────────────────
# 品質閘
# ─────────────────────────────────────────────────────────────
def _cited_in(concrete: str, text: str) -> bool:
    """
    具體物有沒有真的出現在這一段的行文裡。

    不能用整串比對 —— 清單寫「白色主色調」、行文寫「主色調為白色」，
    字序一換 substring 就失敗，於是把明明很具體的文章判成空話。
    改用字元集合重疊：拆掉標點與助詞後，七成以上的字出現過就算引用。
    """
    keep = re.sub(r"[^0-9A-Za-z一-鿿#]", "", concrete)
    keep = re.sub(r"[的了與和及之]", "", keep)
    if len(keep) < 2:
        return False
    chars = set(keep)
    hit = sum(1 for ch in chars if ch in text)
    return hit / len(chars) >= 0.7


# 模型偶爾會吐 markdown（實測「給設計師」那段出現 1. **模組尺寸的一致性**）。
# 前端是直接把字放上版面的，符號會原樣印出來，所以在這裡剝掉。
_MD = re.compile(r"\*\*|\*|^#{1,6}\s+|^\s*[-–—]\s+", re.M)


def _plain(text: str) -> str:
    text = _MD.sub("", text or "")
    # 「1. 」這種編號同理，但只剝行首的，不要動「1972 年」
    text = re.sub(r"^\s*\d+[.、)]\s+", "", text, flags=re.M)
    return text.strip()


# 音譯的專有名詞是假資訊 —— 讀者拿「約翰與溫希·阿恩特」查不到任何東西。
# prompt 裡寫了「保留原文」還是擋不住（實測），所以在這裡機械處理：
# 一個欄位同時有拉丁字和括號中文時，留拉丁那半。
_TRANSLIT_AFTER = re.compile(
    r"([A-Za-z][A-Za-z0-9 .&'’\-]*?)\s*[（(][\u4e00-\u9fff·・、，\s]+[）)]")
_TRANSLIT_BEFORE = re.compile(
    r"[\u4e00-\u9fff·・、，]+\s*[（(]\s*([A-Za-z][A-Za-z0-9 .&'’\-]*?)\s*[）)]")


def _drop_transliteration(name: str) -> str:
    if not name:
        return name
    out = _TRANSLIT_AFTER.sub(r"\1", name)
    out = _TRANSLIT_BEFORE.sub(r"\1", out)
    return out.strip(" ·、，")


def _localise(doc: dict) -> None:
    """
    就地把整篇轉成繁中台灣用詞，並剝掉 markdown。

    模型引用簡中來源時會照抄原文進 concretes 和內文（實測漏出
    「Häme 应用科技大学」）。這件事在寫完之後統一處理，不靠 prompt 祈禱。
    """
    for k in ("title", "hook", "what_it_is", "takeaway_everyone", "takeaway_designer"):
        doc[k] = _plain(to_traditional(str(doc.get(k, ""))))
    doc["subject"] = {k: _drop_transliteration(to_traditional(str(v)))
                      for k, v in (doc.get("subject") or {}).items()}
    for a in _angles_of(doc):
        a["body"] = _plain(to_traditional(str(a.get("body", ""))))
        a["so_what"] = _plain(to_traditional(str(a.get("so_what", ""))))
    doc["concretes"] = [to_traditional(str(c)) for c in (doc.get("concretes") or [])]
    for g in (doc.get("glossary") or []):
        if isinstance(g, dict):
            g["term"] = to_traditional(str(g.get("term", "")))
            g["plain"] = to_traditional(str(g.get("plain", "")))


def _fill_glossary(doc: dict) -> None:
    """
    用了術語卻沒進 glossary 的，補寫，而不是把整篇打回重寫。

    這個閘門存在的目的是「保證讀者看得懂」，不是懲罰模型漏填欄位。
    實測有兩個候選就是倒在漏了「陽極處理」一項 —— 為了一個詞重寫整篇，
    代價和收穫完全不成比例。缺的詞很好認，補一句解釋是很小的一次呼叫。
    """
    angles = _angles_of(doc)
    body = " ".join(str(a.get("body", "")) for a in angles)
    used = set(_jargon_in(body))

    # 先剪枝：模型會塞進文中根本沒出現的詞（實測多了「陽極處理」）。
    # 術語表是為了讓讀者看懂這一篇，不是設計辭典。
    glossary = [g for g in (doc.get("glossary") or [])
                if isinstance(g, dict) and str(g.get("term", "")).strip()
                and str(g.get("term", "")).strip() in body]
    doc["glossary"] = glossary

    have = {str(g.get("term", "")).strip() for g in glossary}
    missing = sorted(used - have)
    if not missing:
        return

    try:
        got = chat_json([
            {"role": "system", "content": "你把設計術語解釋給完全不懂設計的人聽。"},
            {"role": "user", "content":
                "用繁體中文台灣用語，每個詞用**一句話**解釋，講給完全不懂設計的人聽，"
                "不要再用其他術語。回一個 JSON 物件，key 是詞，value 是那句解釋：\n"
                + "、".join(missing)},
        ], temperature=0.2, max_tokens=600)
    except LLMError as e:
        print(f"  [術語表] 補寫失敗，交給品質閘處理：{str(e)[:80]}")
        return

    for term in missing:
        plain = str(got.get(term, "") or "").strip()
        if plain:
            glossary.append({"term": term, "plain": plain})
    doc["glossary"] = glossary
    print(f"  [術語表] 補上 {len(missing)} 個詞的白話解釋：{'、'.join(missing[:5])}")


def _angles_of(doc: dict) -> list[dict]:
    return [a for a in (doc.get("angles") or []) if isinstance(a, dict)]


def _body_text(doc: dict) -> str:
    parts = [str(doc.get(k, "")) for k in
             ("hook", "what_it_is", "takeaway_everyone", "takeaway_designer")]
    for a in _angles_of(doc):
        parts += [str(a.get("body", "")), str(a.get("so_what", ""))]
    return " ".join(parts)


def _jargon_in(text: str) -> list[str]:
    return [w for w in JARGON if w in text]


def quality_check(doc: dict) -> tuple[bool, list[str]]:
    """回傳 (是否通過, 失敗原因清單)。"""
    problems: list[str] = []

    concretes = [c for c in (doc.get("concretes") or []) if str(c).strip()]
    if len(concretes) < 4:
        problems.append(f"具體物只有 {len(concretes)} 項（需 ≥4）")

    angles = _angles_of(doc)
    if not 3 <= len(angles) <= 5:
        problems.append(f"角度有 {len(angles)} 個（需 3–5 個）")

    thin = [a.get("lens", "?") for a in angles
            if not str(a.get("body", "")).strip() or not str(a.get("so_what", "")).strip()]
    if thin:
        problems.append(f"這些角度缺 body 或「所以呢」：{'、'.join(map(str, thin))}")

    # 至少要有一個角度是真的踩在具體物上的，不然整篇還是浮的
    if angles and concretes:
        best = max(sum(1 for c in concretes if _cited_in(str(c), str(a.get("body", ""))))
                   for a in angles)
        if best < 2:
            problems.append(f"沒有任何一個角度引用到兩項具體物（最多的只有 {best} 項）")

    body = _body_text(doc)
    if not body.strip():
        problems.append("內文是空的")

    hits = [w for w in BANNED_VAGUE if w in body]
    if hits:
        problems.append(f"用了抽象形容詞：{'、'.join(hits[:5])}")

    judged = [w for w in BANNED_JUDGEMENT if w in body]
    if judged:
        problems.append(f"批評寫成了評分：{'、'.join(judged[:5])}")

    # ── 「看得懂」閘 ──
    entry = str(doc.get("hook", "")) + " " + str(doc.get("what_it_is", ""))
    exit_ = str(doc.get("takeaway_everyone", ""))
    for label, text in (("開頭", entry), ("給所有人的帶走", exit_)):
        bad = _jargon_in(text)
        if bad:
            problems.append(f"{label}用了術語（那裡必須零術語）：{'、'.join(bad[:4])}")

    assumed = [w for w in BANNED_ASSUMES_DESIGNER if w in exit_]
    if assumed:
        problems.append(f"「給所有人的帶走」預設讀者是設計師：{'、'.join(assumed[:3])}")

    leftover = simplified_leftovers(body + " ".join(str(c) for c in concretes))
    if leftover:
        problems.append(f"還有簡體字：{'、'.join(leftover[:8])}")

    explained = {str(g.get("term", "")).strip()
                 for g in (doc.get("glossary") or []) if isinstance(g, dict)}
    used = set(_jargon_in(" ".join(str(a.get("body", "")) for a in angles)))
    missing = sorted(used - explained)
    if missing:
        problems.append(f"用了術語但沒解釋：{'、'.join(missing[:5])}")

    return (not problems), problems


# ─────────────────────────────────────────────────────────────
# 對外
# ─────────────────────────────────────────────────────────────
def build_feature(item: dict, category: str | None = None,
                  extra_images: list[str] | None = None,
                  diag: dict | None = None) -> dict | None:
    """
    產一篇「今日一件」。品質閘沒過就重寫一次，再沒過回 None（換下一個候選）。

    diag 是給呼叫端看的病歷：失敗時填入 vision_error 與最後一輪的 problems，
    這樣 Actions 的錯誤訊息能講出「為什麼」。
    """
    diag = diag if diag is not None else {}
    vision_notes: list[str] = []
    neurons = 0.0

    urls = [u for u in ([item.get("image_url", "")] + (extra_images or [])) if u]
    if urls:
        vision_notes, neurons, verr = describe_images(urls, VISION_CFG["max_images"])
        if verr:
            diag["vision_error"] = verr
        print(f"  讀圖 {len(vision_notes)}/{len(urls)} 張，花費 {neurons:.0f} neurons")

    problems: list[str] = []
    for strict in (False, True):
        msgs = _prompt(item, vision_notes, category, strict, problems)
        try:
            doc = chat_json(msgs, temperature=0.35 if not strict else 0.15,
                            max_tokens=3000)
        except LLMError as e:
            diag["llm_error"] = str(e)
            print(f"  [今日一件] {str(e)[:120]}")
            return None

        _localise(doc)

        # 事實錨定：設計者／業主／年份與具體物都必須能溯源，
        # 否則就是模型自己生的 —— 這是這個產品最危險的失誤。
        src_texts = [item.get("title", ""), item.get("summary", "")] + vision_notes
        doc["subject"], unverified = verify_subject(doc.get("subject") or {},
                                                    " ".join(src_texts))
        if unverified:
            print(f"  [事實錨定] 原文找不到，已清空：{'、'.join(unverified)}")
        kept, unsourced = verify_concretes(doc.get("concretes") or [], src_texts)
        if unsourced:
            print(f"  [事實錨定] 具體物無法溯源，已移除：{'、'.join(map(str, unsourced))}")
        doc["concretes"] = kept
        _fill_glossary(doc)

        ok, problems = quality_check(doc)
        diag["problems"] = problems
        if ok:
            doc["vision_notes"] = vision_notes
            doc["neurons_used"] = round(neurons, 1)
            doc["source_url"] = item.get("url", "")
            doc["source_name"] = item.get("source_name", "")
            return doc
        print(f"  [品質閘] {'重寫後仍' if strict else ''}未過：{'；'.join(problems)}")

    return None
