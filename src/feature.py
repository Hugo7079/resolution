"""
每日一件：三層漏斗
==================

拿**原文正文** + vision.py 的英文客觀描述，寫成一篇「介紹一件設計」。

順序是有意義的：正文在前，讀圖在後。原本只給 RSS 摘要（實測中位數 203 字元，
一半以上不到 200），模型等於只能看著圖猜，於是出現最傷的那種錯 ——
版面上那張圖是展場照或列表縮圖，文章卻整篇在拆「這張海報」，
讀者點連結進去裡面根本沒有海報。

現在「這是什麼東西」一律以原文為準，而且要模型把判斷依據從原文抄出來
（artefact_type / type_evidence），抄不出來就重寫。圖只用來談長什麼樣子。

結構不是七個並列的軸 —— 那是寫給同行看的評論，圈外人不知道從哪進去。
改成有順序的三層：

  一、先看見    hook + what_it_is    零術語，三秒決定要不要往下讀
  二、多角度欣賞 angles（3–5 個）     每個角度強制配一句白話「所以呢」
  三、帶走      takeaway ×2          給所有人一份、給設計師一份

「所以呢」是這個站的樞紐。它把「洋紅配螢光綠」這種觀察，
翻譯成讀者自己生活裡用得上的東西。少了它，這就只是一篇專業評論。

品質不靠祈禱，靠**可驗證的輸出契約**：
  ‣ artefact_type / type_evidence：這是什麼東西，以及原文哪一句這樣說，
    依據回原文比對不到就是看圖猜的
  ‣ concretes：模型必須交出它實際引用的具體物，少於四項判定為空話
  ‣ glossary：用了術語就要有白話解釋，入口與出口一個術語都不准出現
交不出來就重寫一次，再不行就換下一個候選（見 pipeline）。
"""

from __future__ import annotations
import json
import re

from article import fetch_article
from config import (CATEGORIES, CATEGORY_BOUNDARY_RULES, JARGON, JARGON_TERMS,
                    LENSES, VISION_CFG)
from llm import chat_json, LLMError
from sanitize import (quote_in_source, simplified_leftovers, to_traditional,
                      verify_concretes, verify_subject)
from vision import describe_images, disabled_reason as vision_disabled_reason

# 正文有這麼多字，才有資格要求模型「把品類的依據從原文抄出來」。
# 比這少的時候原文本來就沒交代，硬要它交依據只會逼它編一句。
TYPE_EVIDENCE_MIN_CHARS = 300

# 第一版沒過之後修幾次稿。原本是「重寫一次」，實測小模型重寫會把
# 同樣的禁用詞再寫一遍；改成拿上一版修，並多給一次機會。
REVISE_ROUNDS = 2

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

# 紅線四：不准用推測把空缺填起來。
# 抓不到原文時模型不會承認「不知道」，它會改用「可能」「推測」把版面填滿
# （實測 2026-09-16 那篇 403 抓不到正文的 Dezeen 公寓：
#  「雖然原文沒有具體說明，但可以推測可能與中野區的地形有關」，
#  取捨那一段整段五個「可能」）。這種句子讀者拿不走任何東西，
# 偏偏它長得跟事實一模一樣 —— 比空話更危險。
BANNED_SPECULATION = ["推測", "猜測", "或許", "大概是", "應該是", "我認為",
                      "不排除", "想必", "據推斷", "沒有具體說明"]

# 「可能」本身在寫取捨時是正當的（「換個目標這個選擇就不成立」），
# 但一個角度裡出現三次以上，那一段就是在猜而不是在看。
MAX_MAYBE_PER_ANGLE = 2

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
{"、".join(JARGON_TERMS[:40])}…等
  ‣ hook 和 takeaway_everyone **一個都不准出現** —— 那是入口和出口
  ‣ angles 裡可以用，但每個用到的術語都要進 glossary，
    用一句話講給完全不懂的人聽
  ‣ takeaway_everyone 不准預設讀者是設計師（他沒有案子、沒有客戶）

【紅線四 — 不准推測】
不知道就寫「原文沒寫」「從圖上判斷不出」，不要用「可能」「推測」「或許」
「應該是」把空缺填起來。禁用詞：{"、".join(BANNED_SPECULATION[:8])} 等。
一個角度裡「可能」最多兩次 —— 超過就代表那一段是在猜，不是在看。
寧可少寫一個角度，也不要寫一段猜的。

【語言與格式】
一律繁體中文、台灣用語。
**專有名詞保留原文，不要音譯**：品牌、工作室、人名、產品名、獎項名、字體名一律照抄。
  ‣ 對：Studio Gorm、Pentagram、Dezeen、Söhne Halbfett、Norm Architects
  ‣ 錯：約翰運希·阿恩特、五角星、德真
不確定怎麼寫就照抄原文，音譯出來的名字讀者查不到，等於假資訊。
輸出純文字，不要用 markdown —— 不要 **粗體**、不要 # 標題、不要 1. 2. 3. 條列。
前端是直接把字放上版面的，符號會原樣印出來。來源若是簡體中文，要做用詞在地化
（介面 / 軟體 / 影片 / 專案 / 品質 / 網路 / 螢幕 / 檔案 / 程式）。

【誠實 — 品類以原文為準，不以圖為準】
版面上那張圖常常是列表縮圖、展場照或情境照，**未必就是作品本身**。
  ‣ 「這是什麼東西」（海報／識別／椅子／展覽／建築／App 介面…）
    只能從原文判斷。原文說是展覽就不要寫成海報，說是包裝就不要寫成書，
    說是一整季的服裝就不要寫成一件單品。
  ‣ 原文與讀圖描述打架時，一律以原文為準。圖上看得到、原文沒提的東西，
    要寫就寫成「圖上是…」，不要當成這件作品的事實。
  ‣ 視覺描述來自模型讀圖，可能有誤。凡是描述裡寫 "not determinable" 的項目，
    不要在文章裡假裝知道。
  ‣ 原文和圖上都沒有的東西，不要生出來。
  ‣ 原文若是一次介紹好幾件作品的整理文（校園展、年度精選、清單文），
    只寫版面那張圖對應的那一件，並以原文裡談那一件的那幾句為準；
    原文裡認不出圖上是哪一件，就不要編那一件的細節 ——
    改談原文真的講了的東西，並在 what_it_is 說清楚這是一批作品裡的一件。
""".strip()


def _mk_context(item: dict, vision_notes: list[str], article_text: str = "") -> str:
    notes = "\n\n".join(f"[圖 {i+1}]\n{n}" for i, n in enumerate(vision_notes)) \
        or "（沒有可用的視覺描述，請只依文字資訊撰寫，並在 concretes 誠實反映）"

    if article_text:
        body = ("── 原文正文（連結頁的內容，這是最可靠的一份材料）──\n"
                + article_text)
    else:
        body = ("── 原文正文 ──\n"
                "（抓不到正文，手上只有上面的標題與摘要。這種狀態下「這是什麼東西」"
                "只能講標題與摘要講得出來的那些 —— 其餘一律不要斷言，"
                "尤其不要從圖上推測品類與用途。）")

    return f"""
標題：{item.get('title', '')}
來源：{item.get('source_name', '')}（{item.get('region', '')}）
連結：{item.get('url', '')}
原文摘要：
{(item.get('summary') or '')[:1200]}

{body}

── 讀圖得到的客觀視覺描述（英文，未經評價）──
{notes}
（提醒：這只是在描述那張圖，不保證那張圖就是作品本身）
""".strip()


# 修稿時交回給模型的欄位（其餘是流程自己加的，不必給它看）
_DRAFT_KEYS = ("title", "subject", "artefact_type", "type_evidence", "category",
               "hook", "what_it_is", "angles", "takeaway_everyone",
               "takeaway_designer", "glossary", "concretes", "confidence")


def _revision_block(previous: dict, problems: list[str],
                    removed: list[str]) -> str:
    """
    修稿指示。

    原本重寫只給一句「上一版沒過，原因：…」，模型就從頭再寫一篇，
    同一個禁用詞又冒出來（實測 2026-09-17：五個候選、十次呼叫，
    「精緻」「大氣」「視覺衝擊」輪流出現，全倒）。小模型改稿比重寫可靠得多，
    所以把上一版原封交回去，只要它修掉點名的那幾處。
    """
    draft = json.dumps({k: previous.get(k) for k in _DRAFT_KEYS if k in previous},
                       ensure_ascii=False, indent=1)
    gone = (f"\n這些具體物在原文裡找不到、已經刪掉，不准再加回去："
            f"{'、'.join(map(str, removed))}") if removed else ""
    return f"""

【修稿】下面是你上一版的稿子，品質閘沒過。問題逐條：
{chr(10).join("  ‣ " + p for p in problems)}{gone}

只修這些問題，其他沒被點名的段落原樣保留：
  ‣ 用了禁用詞 → 改寫成具體的觀察（寫出看到了什麼），不是換一個同義的形容詞
  ‣ 批評寫成評分 → 改成「為了得到 A，它放棄了 B」
  ‣ 開頭或帶走用了術語 → 那一段改用白話講同一件事
  ‣ 具體物不夠、角度沒引用到 → 從原文正文找數字、材料、名稱，補進角度與 concretes；
    找不到就刪掉那個角度（至少留 3 個）
  ‣ 用推測填空缺、「可能」太多 → 刪掉那些句子，原文沒寫的就不寫
  ‣ 品類沒有依據 → type_evidence 從原文正文照抄一句
  ‣ 人名音譯 → 改回原文拼法

上一版：
{draft}

輸出修好之後的完整 JSON，格式與上面相同。"""


def _prompt(item: dict, vision_notes: list[str], category: str | None,
            article_text: str = "", revision: str = "") -> list[dict]:
    cat = CATEGORIES.get(category or "", {})
    framing = (f"今天輪到的分類是「{cat.get('label', '')}」"
               f"（{cat.get('desc', '')}）。\n{CATEGORY_BOUNDARY_RULES}")

    return [
        {"role": "system",
         "content": "你替台灣讀者寫每日一件設計的導覽。你的價值在於"
                    "讓人看見自己原本看不見的東西，並且讓完全不懂設計的人也跟得上。"},
        {"role": "user",
         "content": f"""{framing}

{_COMMON_RULES}

【可用的角度（鏡頭）】挑 3–5 個**這件作品真的談得動**的，不要硬套：
{_LENS_SPEC}

對一張海報硬談「用什麼做的」、對一張椅子硬談「三秒讀到什麼」，
出來的都是廢話。談不動就不要選那個鏡頭。

【輸出 JSON】
{{
  "title": "繁中標題，點出這件作品最關鍵的一個選擇，不要照抄作品原名",
  "subject": {{"name": "作品名", "designer": "設計者或工作室", "client": "業主", "year": "年份"}},
  "artefact_type": "這是什麼東西，四到十個字的品類，例如「單張海報」「展覽主視覺」「餐椅」「一場展覽」「行動應用程式介面」。只能依原文判斷，不准看圖猜",
  "type_evidence": "原文裡讓你這樣判斷的那一句，照抄原文、不要翻譯也不要改寫，最多一句、30 字以內。原文真的沒明說就寫「原文未明說」",
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
{_mk_context(item, vision_notes, article_text)}{revision}"""},
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


# 讀圖描述判斷不出來的項目會寫 "not determinable"。prompt 要模型
# 「不要假裝知道」，它卻直接把這個英文片語寫進中文行文
# （實測：「採用高強度鋼板（not determinable 具體材質，但…）」）。
# 換成中文說法，句子反而通順。
_ND = re.compile(r"\bnot\s+determinable\b", re.I)


def _plain(text: str) -> str:
    text = _ND.sub("從圖上判斷不出", text or "")
    text = re.sub(r"(從圖上判斷不出)\s+(?=[\u4e00-\u9fff])", r"\1", text)
    text = _MD.sub("", text)
    # 「1. 」這種編號同理，但只剝行首的，不要動「1972 年」
    text = re.sub(r"^\s*\d+[.、)]\s+", "", text, flags=re.M)
    return text.strip()


# 音譯的專有名詞是假資訊 —— 讀者拿「約翰與溫希·阿恩特」查不到任何東西。
# prompt 裡寫了「保留原文」還是擋不住（實測），所以在這裡機械處理：
# 一個欄位同時有拉丁字和括號中文時，留拉丁那半。
# 中間點只有音譯的外國人名在用（「費南達·卡納萊斯」）。中文人名不用它，
# 所以兩邊都是中文字時，那就是一個音譯出來的名字 —— 讀者拿它查不到任何東西。
# prompt 裡寫了「保留原文」，欄位也有 _drop_transliteration 顧著，
# 但行文裡照樣會冒出來（實測 2026-09-16：subject.designer 正確寫著
# Fernanda Canales，what_it_is 卻寫成「費南達·卡納萊斯」）。
# 兩側各抓五個字就夠認人（名字再長也看得出是哪一個），
# 不設上限的話整句話會被當成命中的字串印進錯誤訊息裡
_TRANSLIT_IN_BODY = re.compile(r"[\u4e00-\u9fff]{1,5}[·・][\u4e00-\u9fff]{1,5}")


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
    for k in ("title", "artefact_type", "hook", "what_it_is",
              "takeaway_everyone", "takeaway_designer"):
        doc[k] = _plain(to_traditional(str(doc.get(k, ""))))
    # type_evidence 是照抄原文的一句話（多半是英文），刻意不轉換 ——
    # 轉了就跟原文對不起來，溯源會變成永遠失敗
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


def _term_key(term: str) -> str:
    """
    術語的比對用形式：只留中文本體，這樣「陽極處理」和「陽極處理（anodizing）」
    會收斂成同一個 key。

    純拉丁的詞（字體名之類）沒有中文本體，退回原字串比對 ——
    只挑中文會把 "Söhne Halbfett" 變成 "ö"，一個字元什麼都比得到。
    """
    zh = "".join(ch for ch in (term or "") if "\u4e00" <= ch <= "\u9fff")
    return zh or (term or "").strip()


def _fill_glossary(doc: dict) -> None:
    """
    用了術語就給白話解釋 —— 直接查內建的 JARGON 表，不叫模型寫。

    原本是漏了就發一次小呼叫補寫，但回傳的 key 對不上時什麼都沒補上，
    訊息卻照印「補上 N 個詞」，於是整篇卡在「用了術語但沒解釋」，
    實測一天五個候選全倒。解釋本來就該是固定的，查表不會失敗。

    模型自己寫的那份留著（它可能解釋了 JARGON 以外的詞），
    但同一個詞以內建版本為準 —— 跨天用詞才一致。
    """
    body = " ".join(str(a.get("body", "")) for a in _angles_of(doc))

    out, seen = [], set()
    # 內建表優先
    for term in _jargon_in(body):
        key = _term_key(term)
        if key in seen:
            continue
        seen.add(key)
        out.append({"term": term, "plain": JARGON[term]})

    # 模型多解釋的詞：文中真的出現、而且不是上面已經收錄的才留
    for g in (doc.get("glossary") or []):
        if not isinstance(g, dict):
            continue
        term, plain = str(g.get("term", "")).strip(), str(g.get("plain", "")).strip()
        key = _term_key(term)
        if not term or not plain or key in seen or key not in body:
            continue
        seen.add(key)
        out.append({"term": term, "plain": plain})

    doc["glossary"] = out


def _angles_of(doc: dict) -> list[dict]:
    return [a for a in (doc.get("angles") or []) if isinstance(a, dict)]


def _body_text(doc: dict) -> str:
    parts = [str(doc.get(k, "")) for k in
             ("hook", "what_it_is", "takeaway_everyone", "takeaway_designer")]
    for a in _angles_of(doc):
        parts += [str(a.get("body", "")), str(a.get("so_what", ""))]
    return " ".join(parts)


def _jargon_in(text: str) -> list[str]:
    """
    文中用到的術語。被更長的詞包住的就不算 ——
    文章寫「無襯線」時它不是在用「襯線」這個詞，兩個都列出來只是雜訊。
    """
    hit = [w for w in JARGON_TERMS if w in text]
    return [w for w in hit if not any(w != o and w in o for o in hit)]


def quality_check(doc: dict, source_text: str = "",
                  check_type: bool = False) -> tuple[bool, list[str]]:
    """
    回傳 (是否通過, 失敗原因清單)。

    check_type 開著時多驗一件事：「這是什麼東西」有沒有原文依據。
    只有正文夠厚（TYPE_EVIDENCE_MIN_CHARS）時才開 —— 原文自己都沒交代的時候
    要求它交依據，等於逼它編一句出來，比不驗還糟。
    """
    problems: list[str] = []

    if check_type:
        atype = str(doc.get("artefact_type", "")).strip()
        ev = str(doc.get("type_evidence", "")).strip()
        if not atype:
            problems.append("沒說這是什麼東西（artefact_type 空的）")
        elif not quote_in_source(ev, source_text):
            # 依據抄不出來，就代表品類是看圖推的 —— 正是「圖是展場照、
            # 文章卻在拆海報」那種錯的來源
            why = "沒給依據" if not ev or ev.startswith("原文未明說") else "原文裡找不到這句"
            problems.append(f"「{atype}」在原文裡沒有依據（{why}）")

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

    # 推測只驗事實那幾段 —— 帶走是給建議的，「或許你會注意到」很正常
    factual = " ".join([str(doc.get("hook", "")), str(doc.get("what_it_is", ""))]
                       + [str(a.get("body", "")) for a in angles])
    guessed = [w for w in BANNED_SPECULATION if w in factual]
    if guessed:
        problems.append(f"用推測填空缺：{'、'.join(guessed[:5])}")
    maybe = [str(a.get("lens", "?")) for a in angles
             if str(a.get("body", "")).count("可能") > MAX_MAYBE_PER_ANGLE]
    if maybe:
        problems.append(f"這些角度整段在猜（「可能」超過 {MAX_MAYBE_PER_ANGLE} 次）："
                        f"{'、'.join(maybe)}")

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

    translit = _TRANSLIT_IN_BODY.findall(body)
    if translit:
        problems.append(f"人名音譯了（要照抄原文）：{'、'.join(translit[:3])}")

    leftover = simplified_leftovers(body + " ".join(str(c) for c in concretes))
    if leftover:
        problems.append(f"還有簡體字：{'、'.join(leftover[:8])}")

    explained = {_term_key(str(g.get("term", "")))
                 for g in (doc.get("glossary") or []) if isinstance(g, dict)}
    used = {_term_key(w) for w in
            _jargon_in(" ".join(str(a.get("body", "")) for a in angles))}
    missing = sorted(used - explained)
    if missing:
        problems.append(f"用了術語但沒解釋：{'、'.join(missing[:5])}")

    return (not problems), problems


# ─────────────────────────────────────────────────────────────
# 圖文比對：版面那張圖，拍的是不是文章寫的那一件
#
# 前面每一關都只看文字。讀圖描述回答的是「圖上有什麼」，
# 沒有人去問「那是不是我們在寫的東西」。
# 實測 2026-09-17：ArchDaily 的週報一篇講兩件事，版面那張圖是
# MAD 的 Lucas 博物館，文章寫的卻是聯合國的地圖投影 ——
# 還把博物館照片的顏色硬套成「海洋改用淺綠色 #008000」。
#
# 為什麼不直接問讀圖模型「是不是這件」：實測同一組圖文問兩次，
# 一次 NO 一次 YES（溫度 0 也一樣）。它描述「圖上是什麼」倒是很穩 ——
# 兩次都說「一片城市景觀，中間一棟白色建築」。所以分工：
# 讀圖模型負責看，文字模型負責比。
# ─────────────────────────────────────────────────────────────
MATCH_OK, MATCH_BAD, MATCH_UNSURE, MATCH_UNCHECKED = "match", "mismatch", "unsure", "unchecked"


def check_image_match(doc: dict, vision_notes: list[str]) -> tuple[str, str, str]:
    """
    回傳 (判定, 圖上實際是什麼, 理由)。

    只看第一則描述 —— 那是 item["image_url"]，也就是版面上真的會放的那張。
    unchecked 是「沒比成」（沒有讀圖描述、呼叫失敗），不是模型說不確定。
    """
    # 空描述一定要在這裡擋掉：實測描述是空字串時，文字模型會自己
    # 幻想出「一張非洲被放大的世界地圖」，然後判 match
    if not vision_notes or len(vision_notes[0].strip()) < 40:
        return MATCH_UNCHECKED, "", "沒有讀圖描述"

    subj = doc.get("subject") or {}
    work = " ／ ".join(x for x in (subj.get("name"), subj.get("designer")) if x)
    msgs = [
        {"role": "system",
         "content": "你只做一件事：判斷一張配圖拍的是不是文章寫的那件作品。"},
        {"role": "user",
         "content": f"""文章寫的作品：
  名稱：{work or "（未寫）"}
  品類：{doc.get("artefact_type", "")}
  原文怎麼定義它：{doc.get("type_evidence", "")}
  文章的介紹：{doc.get("what_it_is", "")}

讀圖模型對那張配圖的描述（英文，只描述看到什麼）：
{vision_notes[0][:1500]}

判斷那張圖拍的是不是這件作品（整體、局部、細節、使用情境都算）。

第一步：兩邊各歸到一個大類 ——
  建築與空間（建築外觀、室內、庭院、階梯、牆面、屋頂、展場）
  物件與產品（家具、燈、器具、服裝、包裝的實物）
  平面與印刷（海報、書、標誌、字體、插畫）
  數位介面（網站、App、螢幕畫面）
  地圖與圖表
  人物肖像
  純自然風景（完全沒有人造結構）

注意：描述裡只要出現牆、階梯、開口、屋簷這類人造結構，就是「建築與空間」，
就算讀圖模型把它叫成 landscape。讀圖模型不知道作品叫什麼，
描述裡沒有作品名稱是正常的，不能當成理由。

第二步：
  ‣ mismatch：大類不同（文章寫地圖、圖上是建築；文章寫海報、圖上是建築；
    文章寫椅子、圖上是城市天際線；文章寫 App、圖上是人像）
  ‣ match：大類相同，而且描述沒有跟作品的明確特徵直接打架
    （作品是圓形住宅，圖上是「圓弧牆圍起的庭院」→ match；
     作品是圓柱底座的檯燈，圖上是「幾盞 LED 檯燈」→ match）
  ‣ unsure：大類相同，但描述**明確寫出**跟作品相反的特徵
    （作品是圓形住宅，圖上是「一棟方正的玻璃高樓」）

描述「沒提到」作品的某個特徵不算打架 —— 讀圖模型常常漏講
（沒說圓形、沒說材質都很正常）。只有寫出相反的東西才算。
輸出 JSON：{{"work_kind": "作品的大類",
            "image_kind": "圖的大類",
            "verdict": "match | mismatch | unsure",
            "image_shows": "圖上實際是什麼，十五字以內",
            "why": "二十字以內"}}"""},
    ]
    try:
        out = chat_json(msgs, temperature=0.0, max_tokens=300)
    except LLMError as e:
        return MATCH_UNCHECKED, "", f"比對呼叫失敗：{str(e)[:60]}"

    verdict = str(out.get("verdict", "")).strip().lower()
    if verdict not in (MATCH_OK, MATCH_BAD, MATCH_UNSURE):
        verdict = MATCH_UNSURE
    # 大類不同就是不符 —— 這條由程式判，不靠模型自律。
    # 反過來的情況（大類相同卻判 mismatch）留給模型：週報裡兩棟不同的建築
    # 就是大類相同的不符，放行的話正好漏掉這次要擋的那種錯。
    wk = re.sub(r"\s", "", str(out.get("work_kind", "")))
    ik = re.sub(r"\s", "", str(out.get("image_kind", "")))
    if wk and ik and wk != ik:
        verdict = MATCH_BAD
    return (verdict,
            to_traditional(str(out.get("image_shows", "")))[:40],
            to_traditional(str(out.get("why", "")))[:60])


# ─────────────────────────────────────────────────────────────
# 對外
# ─────────────────────────────────────────────────────────────
def resolve_article_text(item: dict) -> tuple[str, str]:
    """
    這一則的原文正文。回傳 (正文, 怎麼來的)。

    兩條路，先便宜的：
      1. feed 的 content:encoded —— 抓 RSS 時就一起拿到了，不必再發 HTTP，
         而且 Dezeen 這種會把 CI 的 IP 擋掉（403）的站台只剩這條路拿得到全文
      2. 連結頁現抓 —— 池子裡的舊條目已經沒有 feed 全文了（不進 pool.json，
         見 fetcher.CONTENT_TEXT_MAX 的理由），而且 Core77、ArchDaily
         這些站的 feed 本來就只給摘要

    兩邊都拿得到就用長的那份。都拿不到回 ("", 原因)，呼叫端照樣寫，
    只是 prompt 會切到「低證據」模式。
    """
    feed_text = (item.get("content_text") or "").strip()
    if len(feed_text) >= 1200:
        return feed_text, "feed 全文"

    got = fetch_article(item.get("url", ""))
    page_text = (got.get("text") or "").strip()

    if len(page_text) >= len(feed_text) and page_text:
        return page_text, "連結頁"
    if feed_text:
        return feed_text, "feed 全文"
    return "", got.get("error") or "沒有正文"


def build_feature(item: dict, category: str | None = None,
                  extra_images: list[str] | None = None,
                  diag: dict | None = None,
                  article: tuple[str, str] | None = None) -> dict | None:
    """
    產一篇「今日一件」。品質閘沒過就重寫一次，再沒過回 None（換下一個候選）。

    diag 是給呼叫端看的病歷：失敗時填入 vision_error 與最後一輪的 problems，
    這樣 Actions 的錯誤訊息能講出「為什麼」。
    """
    diag = diag if diag is not None else {}
    vision_notes: list[str] = []
    neurons = 0.0

    # 呼叫端可能已經先抓過了（pipeline 要靠正文長度決定候選順序），
    # 不要為了同一篇再發一次 HTTP
    article_text, how = article if article is not None else resolve_article_text(item)
    diag["article_chars"] = len(article_text)
    if article_text:
        print(f"  原文正文 {len(article_text)} 字元（{how}）")
    else:
        print(f"  [注意] 抓不到原文正文（{how}）—— 只靠標題與摘要寫，"
              f"品類不做斷言")

    urls = [u for u in ([item.get("image_url", "")] + (extra_images or [])) if u]
    if urls:
        vision_notes, neurons, verr = describe_images(urls, VISION_CFG["max_images"])
        if verr:
            diag["vision_error"] = verr
        print(f"  讀圖 {len(vision_notes)}/{len(urls)} 張，花費 {neurons:.0f} neurons")

    # 正文夠厚才要求模型交出品類的原文依據（見 quality_check）
    check_type = len(article_text) >= TYPE_EVIDENCE_MIN_CHARS
    src_texts = [item.get("title", ""), item.get("summary", ""), article_text]

    problems: list[str] = []
    revision = ""
    for attempt in range(1 + REVISE_ROUNDS):
        msgs = _prompt(item, vision_notes, category, article_text, revision)
        try:
            # 3000 會被寫滿（實測 2026-09-16 一篇長文回傳半截 JSON），
            # 而契約又多了 artefact_type / type_evidence 兩欄
            doc = chat_json(msgs, temperature=0.35 if not attempt else 0.15,
                            max_tokens=3500)
        except LLMError as e:
            diag["llm_error"] = str(e)
            print(f"  [今日一件] {str(e)[:120]}")
            return None

        _localise(doc)

        # 事實錨定：設計者／業主／年份與具體物都必須能溯源，
        # 否則就是模型自己生的 —— 這是這個產品最危險的失誤。
        # 正文進來之後這一關才真的錨得住：原本只有標題加一句摘要，
        # 真的寫在文章裡的設計師名字一樣會被當成幻覺清掉。
        anchors = src_texts + vision_notes
        doc["subject"], unverified = verify_subject(doc.get("subject") or {},
                                                    " ".join(anchors))
        if unverified:
            print(f"  [事實錨定] 原文找不到，已清空：{'、'.join(unverified)}")
        kept, unsourced = verify_concretes(doc.get("concretes") or [], anchors)
        if unsourced:
            print(f"  [事實錨定] 具體物無法溯源，已移除：{'、'.join(map(str, unsourced))}")
        doc["concretes"] = kept
        _fill_glossary(doc)

        ok, problems = quality_check(doc, " ".join(src_texts), check_type)
        diag["problems"] = problems
        if ok:
            if doc.get("artefact_type"):
                print(f"  品類判定：{doc['artefact_type']}"
                      f"（依據：{str(doc.get('type_evidence', ''))[:60]}）")

            # 圖文比對放在最後：前面的閘全過了才值得多花這一次呼叫。
            # 沒過不重寫 —— 文章怎麼改，版面那張圖都不會變。
            # 沒比成（unchecked）也不放行：圖文對不對得上是這一件最基本的要求，
            # 驗不了就換下一個，整天都驗不了就讓當天缺席、Actions 變紅。
            verdict, shows, why = check_image_match(doc, vision_notes)
            print(f"  圖文比對：{verdict}（圖上是：{shows or '—'}；{why}）")
            if verdict != MATCH_OK:
                label = {MATCH_BAD: "圖文不符", MATCH_UNSURE: "看不出圖是不是這件",
                         MATCH_UNCHECKED: "圖文沒比成"}[verdict]
                diag["problems"] = [f"{label}：圖上是「{shows or '？'}」，"
                                    f"文章寫的是「{doc.get('artefact_type', '')}」（{why}）"]
                if verdict == MATCH_UNCHECKED and vision_disabled_reason():
                    diag["vision_error"] = vision_disabled_reason()
                return None

            doc["image_match"] = verdict
            doc["image_shows"] = shows
            doc["vision_notes"] = vision_notes
            doc["neurons_used"] = round(neurons, 1)
            doc["article_chars"] = len(article_text)
            doc["source_url"] = item.get("url", "")
            doc["source_name"] = item.get("source_name", "")
            return doc
        print(f"  [品質閘] {f'修稿 {attempt} 次後仍' if attempt else ''}"
              f"未過：{'；'.join(problems)}")
        revision = _revision_block(doc, problems, list(unsourced))

    return None
