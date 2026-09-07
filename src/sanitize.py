"""
資料清洗與可信度把關
====================

這個站的內容是要拿來「認識一個產業」的，給錯資訊比少給資訊嚴重得多。
三道防線：

  1. 業配過濾 —— 設計媒體最大的假資訊來源。廣編稿長得跟編輯內容一模一樣，
     但它是付費刊登的。當成編輯評論來拆解，等於替廠商寫免費廣告。
  2. 頻道過濾 —— 有些來源把求職、電商、活動報名混在同一個 feed。
  3. 事實錨定 —— 設計者／年份／業主這類欄位，只要在原文裡找不到，
     就標成「未確認」，不讓 LLM 自己生。

第 3 點針對的是這個產品最危險的失誤：模型很愛猜字體名和設計師名，
而且猜得非常像真的。
"""

from __future__ import annotations
import re

# ─────────────────────────────────────────────────────────────
# 1. 業配 / 廣編
# ─────────────────────────────────────────────────────────────

# tag 命中即判定為業配（實測 2026-09-04 的 Dezeen feed）
AD_TAGS = {
    "promotions",                    # Dezeen 明示的業配
    "do not show on the homepage",   # Dezeen Showroom 商品貼文 —— 自家首頁都不放
    "sponsored", "partner content", "advertorial", "promoted",
    "廣編", "業配", "贊助內容",
}

AD_URL_PATTERNS = [
    r"/dezeen-showroom/", r"/promotion", r"/sponsored", r"/partner",
    r"[?&]utm_medium=(?:paid|sponsored)",
]

AD_TITLE_PATTERNS = [
    r"\bpromotion\b", r"\bsponsored\b", r"in partnership with",
    r"^five products listed by", r"listed by .+ on dezeen showroom",
    r"廣編", r"業配", r"專案企劃",
]


def is_advertorial(item: dict) -> tuple[bool, str]:
    """回傳 (是否業配, 判定依據)。"""
    for t in (item.get("tags") or []):
        if str(t).strip().lower() in AD_TAGS:
            return True, f"tag:{t}"
    url = item.get("url", "")
    for p in AD_URL_PATTERNS:
        if re.search(p, url, re.I):
            return True, f"url:{p}"
    title = item.get("title", "")
    for p in AD_TITLE_PATTERNS:
        if re.search(p, title, re.I):
            return True, f"title:{p}"
    return False, ""


# ─────────────────────────────────────────────────────────────
# 2. 頻道過濾（per-source）
# ─────────────────────────────────────────────────────────────

# URL 路徑命中就丟掉
CHANNEL_BLOCK = {
    "數英 digitaling": [r"/jobs/", r"/company/", r"/events?/"],
    "Behance":         [r"/joblist", r"/hiring"],
    "Product Hunt":    [r"/jobs/"],
}

# 標題前綴清理（來源自己加的頻道名）
TITLE_PREFIX = [
    (r"^文章频道\s*-\s*", ""), (r"^项目频道\s*-\s*", ""),
    (r"^案例频道\s*-\s*", ""), (r"^专栏频道\s*-\s*", ""),
    (r"^新聞資料\s*", ""),
]

# 全域垃圾主題（招聘、貸款、博彩之類，任何來源都不該出現）
JUNK_TOPIC = re.compile(
    r"(招聘|徵才|求职|求職|房产|貸款|贷款|理财|保险|减肥|博彩|"
    r"加密货币|比特币|casino|forex|weight loss|insurance quote|"
    r"工業廠房|燒賣批發|淨水器)", re.I)


# 編碼壞掉的標題（???Embbli???????? 這種）。放出去就是明顯的錯誤資訊。
_MOJIBAKE = re.compile(r"[?\ufffd]{3,}")


def is_mojibake(title: str) -> bool:
    if _MOJIBAKE.search(title or ""):
        return True
    bad = sum(1 for ch in (title or "") if ch in "?\ufffd")
    return bool(title) and bad / len(title) > 0.25


def blocked_channel(item: dict) -> str:
    url = item.get("url", "")
    for pat in CHANNEL_BLOCK.get(item.get("source_name", ""), []):
        if re.search(pat, url, re.I):
            return f"channel:{pat}"
    hay = f"{item.get('title','')} {item.get('summary','')[:200]}"
    m = JUNK_TOPIC.search(hay)
    return f"junk:{m.group(0)}" if m else ""


def clean_title(title: str) -> str:
    t = title or ""
    for pat, rep in TITLE_PREFIX:
        t = re.sub(pat, rep, t)
    return re.sub(r"\s+", " ", t).strip()


# ─────────────────────────────────────────────────────────────
# 對外：清洗一整批
# ─────────────────────────────────────────────────────────────
def sanitize(items: list[dict], verbose: bool = True) -> tuple[list[dict], dict]:
    """回傳 (乾淨的條目, 被丟掉的統計)。被丟的原因會記在 item["_dropped"]。"""
    kept: list[dict] = []
    dropped: dict[str, list[dict]] = {"advertorial": [], "channel": [], "empty": []}

    for it in items:
        it = dict(it)
        it["title"] = clean_title(it.get("title", ""))

        if len(it["title"]) < 2 or not it.get("url"):
            dropped["empty"].append(it)
            continue

        if is_mojibake(it["title"]):
            it["_dropped"] = "mojibake"
            dropped["empty"].append(it)
            continue

        ad, why = is_advertorial(it)
        if ad:
            it["_dropped"] = why
            dropped["advertorial"].append(it)
            continue

        why = blocked_channel(it)
        if why:
            it["_dropped"] = why
            dropped["channel"].append(it)
            continue

        kept.append(it)

    if verbose:
        print(f"清洗：{len(items)} → {len(kept)} 則"
              f"（業配 {len(dropped['advertorial'])}、"
              f"頻道/垃圾 {len(dropped['channel'])}、"
              f"空白 {len(dropped['empty'])}）")
    return kept, dropped


# ─────────────────────────────────────────────────────────────
# 3. 事實錨定 —— 防 LLM 幻覺
# ─────────────────────────────────────────────────────────────
def _normalise(s: str) -> str:
    return re.sub(r"[^\w一-鿿]+", "", (s or "").lower())


def verify_subject(subject: dict, source_text: str) -> tuple[dict, list[str]]:
    """
    設計者／業主／年份必須能在原文裡找到，否則清成「未確認」。

    模型猜設計師名和字體名猜得非常像真的 —— 這是這個產品最危險的失誤，
    所以不靠 prompt 約束，直接比對。
    """
    hay = _normalise(source_text)
    out, unverified = dict(subject or {}), []

    for field in ("designer", "client", "name"):
        val = str(out.get(field) or "").strip()
        if not val:
            continue
        # 拆成詞比對：多字名稱只要主要部分出現即算數
        parts = [p for p in re.split(r"[\s,、／/&×x]+", val) if len(_normalise(p)) >= 2]
        hit = any(_normalise(p) in hay for p in parts) if parts else _normalise(val) in hay
        if not hit:
            out[field] = ""
            unverified.append(field)

    year = str(out.get("year") or "").strip()
    if year:
        m = re.search(r"(19|20)\d{2}", year)
        if not m or m.group(0) not in source_text:
            out["year"] = ""
            unverified.append("year")

    return out, unverified


# 可比對的 token：色票、兩位數以上的數字、三字母以上的拉丁詞。
# 單一數字不算 —— 「#0B3D2E」被拆出一個「0」，而「0」幾乎在任何原文裡都找得到，
# 等於整條驗證失效。
_TOKEN = re.compile(r"#[0-9A-Fa-f]{3,8}|[0-9][0-9,.]*[0-9]|[A-Za-z][A-Za-z\-'’]{2,}")


def verify_concretes(concretes: list, sources: list[str]) -> tuple[list, list]:
    """
    具體物溯源。只驗證「含有可比對 token」的項目 —— 字體名、色票、
    尺寸、數字、專有名詞，也就是幻覺的高危區（模型猜字體名猜得非常像真的）。

    比對用數字與拉丁字母詞而不是整串比對：具體物是繁中寫的
    （「1,200 片曲面面板」），原文是英文（"1,200 curved panels"），
    整串一定對不上，但數字和專有名詞會原樣保留。

    純中文的描述句（「五層樓結構」「非線性有機形態」）沒有可比對 token，
    一律放行 —— 中文數字比對不到英文 five-storey，硬驗只會把真的刪掉。
    代價是純中文的捏造（例如「十二欄格線」）擋不住，但那個風險面小得多，
    而且形式軸的具體物幾乎都帶字體名或色票。
    """
    hay = " ".join(sources).lower()
    ok, unsourced = [], []
    for c in concretes or []:
        toks = _TOKEN.findall(str(c))
        if not toks:
            ok.append(c)          # 沒有可比對的東西，不強求
        elif any(tok.lower() in hay for tok in toks):
            ok.append(c)
        else:
            unsourced.append(c)
    return ok, unsourced


# ─────────────────────────────────────────────────────────────
# 簡體 → 繁體（台灣用詞）
#
# 站上一律繁中，但模型引用簡中來源時會把原文照抄進 concretes 和內文
# （實測漏出「Häme 应用科技大学」）。標題那條路有 translate.py 顧，
# 主文這條路本來沒人顧。
#
# 不能直接把整段丟給 opencc。實測 s2twp / s2tw / s2t **三個設定都會**
# 把已經正確的繁體字改壞：
#     「不是只顧著好看」→「不是隻顧著好看」   （只 被當成 隻 的簡體）
#     「連接機制」      →「連線機制」         （s2twp 的詞彙表，用在傢俱上是錯的）
# 模型吐出來的東西九成是繁體、偶爾夾一兩個簡體字，整段轉換的期望值是負的。
#
# 所以改成逐字轉換，並且跳過「本身就是合法繁體字」的那批歧義字。
# 代價：來源真的是簡體時，這些字不會被轉（「一只貓」會留著）。
# 這個方向的錯誤小得多 —— 少轉一個字只是不夠道地，轉錯一個字是別的意思。
# ─────────────────────────────────────────────────────────────

# 這些字在繁體裡本來就有、而且意思不同，一律不動
_AMBIGUOUS = set("只后里表干云面系制松谷丑几卜斗冲板")

# 簡中特有的詞彙 → 台灣說法。逐字轉換蓋不到詞彙層，這裡明列。
_VOCAB = {
    "界面": "介面", "软件": "軟體", "硬件": "硬體", "视频": "影片",
    "项目": "專案", "质量": "品質", "网络": "網路", "屏幕": "螢幕",
    "文件": "檔案", "程序": "程式", "打印": "列印", "分辨率": "解析度",
    "菜单": "選單", "字体": "字型", "像素": "畫素", "内存": "記憶體",
}

try:
    import opencc as _opencc
    _CONV = _opencc.OpenCC("s2tw")

    def _char(ch: str) -> str:
        return ch if ch in _AMBIGUOUS else _CONV.convert(ch)

except Exception:  # noqa: BLE001
    # CI 沒裝 opencc 時的退路：蓋不全，但常見字擋得住，
    # 擋不住的會被 simplified_leftovers() 抓出來讓模型重寫。
    _FALLBACK = {
        "应": "應", "学": "學", "设": "設", "计": "計", "会": "會", "时": "時",
        "说": "說", "这": "這", "个": "個", "为": "為", "对": "對", "门": "門",
        "问": "問", "间": "間", "车": "車", "长": "長", "东": "東", "马": "馬",
        "电": "電", "视": "視", "频": "頻", "网": "網", "络": "絡", "软": "軟",
        "业": "業", "产": "產", "单": "單", "双": "雙", "关": "關", "观": "觀",
        "规": "規", "华": "華", "构": "構", "样": "樣", "题": "題", "线": "線",
        "结": "結", "组": "組", "级": "級", "统": "統", "术": "術", "现": "現",
        "实": "實", "质": "質", "边": "邊", "选": "選", "转": "轉", "环": "環",
        "简": "簡", "杂": "雜", "标": "標", "识": "識", "创": "創",
        "举": "舉", "细": "細", "节": "節", "图": "圖", "层": "層",
    }

    def _char(ch: str) -> str:
        return ch if ch in _AMBIGUOUS else _FALLBACK.get(ch, ch)


def to_traditional(text: str) -> str:
    if not text:
        return text
    for zh_cn, zh_tw in _VOCAB.items():
        text = text.replace(zh_cn, zh_tw)
    return "".join(_char(ch) for ch in text)


def simplified_leftovers(text: str) -> list[str]:
    """轉換後還殘留的簡體字。歧義字不算 —— 那是刻意不動的。"""
    return sorted({ch for ch in (text or "")
                   if ch not in _AMBIGUOUS and _char(ch) != ch})
