"""
解析度 Resolution — 全域設定
=============================

定義：
  1. 四大設計分類（使用者篩選用）
  2. 每週拆解主題輪播
  3. 語言平衡配額
  4. LLM / vision 連線設定
"""

from __future__ import annotations
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(os.getenv("RES_OUTPUT_DIR", "").strip() or (BASE_DIR / "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# 1. 四大分類
#
# 分類是「篩選器」不是「目錄」：互斥、一眼可判、每天都有貨。
# 分類數 = 拆解輪播週期，所以收斂到四類（見 README 一）。
# ─────────────────────────────────────────────────────────────
CATEGORIES: dict[str, dict] = {
    "visual_brand": {
        "label": "視覺與品牌",
        "en": "Visual & Brand",
        "desc": "識別系統、包裝、印刷編排、字體排印、插畫、動態視覺。",
        "audience": "平面／品牌／包裝設計師",
    },
    "interface_ux": {
        "label": "介面與體驗",
        "en": "Interface & Experience",
        "desc": "UI/UX、網站、App、數位產品、互動設計。",
        "audience": "產品設計師、前端、PM",
    },
    "product_object": {
        "label": "產品與物件",
        "en": "Product & Object",
        "desc": "工業設計、家具、器皿、材質與工法。",
        "audience": "工業設計、選品、製造端",
    },
    "space_env": {
        "label": "空間與環境",
        "en": "Space & Environment",
        "desc": "建築、室內、展場、指標與環境圖像。",
        "audience": "建築、室內、策展",
    },
}
CATEGORY_LABEL_BY_ID = {k: v["label"] for k, v in CATEGORIES.items()}

# 邊界判準 —— 寫進 prompt，避免 LLM 每天分得不一樣
CATEGORY_BOUNDARY_RULES = """
判斷歸類時，遇到模糊案例一律套用以下規則：
1. 展場／指標系統：以「使用者是否身處其中」為準。
   身處其中 → space_env；拿在手上或看螢幕 → visual_brand 或 interface_ux。
2. 實體產品上的圖形（包裝、標籤、印刷）→ visual_brand。
   產品本身的形態、材質、結構 → product_object。
3. 網站／App 的視覺風格 → interface_ux（以載體為準，不因為「很平面」就歸 visual_brand）。
4. 動態影像、motion graphics → visual_brand（不獨立成類）。
5. 一件作品只能歸一類。無法判斷時選「使用者接觸它的主要方式」所對應的那類。
""".strip()


# ─────────────────────────────────────────────────────────────
# 2. 每週輪播（0 = 週一 … 6 = 週日）
# ─────────────────────────────────────────────────────────────
WEEKLY_ROTATION: dict[int, dict] = {
    0: {"mode": "category", "category": "visual_brand"},
    1: {"mode": "category", "category": "interface_ux"},
    2: {"mode": "category", "category": "product_object"},
    3: {"mode": "category", "category": "space_env"},
    4: {"mode": "crossover", "category": None},
    5: {"mode": "history",   "category": None},
    6: {"mode": "rest",      "category": None},
}

# 週五「跨界」的收納範圍
CROSSOVER_SCOPE = [
    "AI 對設計職業的衝擊（跨科技／勞動）",
    "運算設計、參數化、數位製造（跨機械／建築）",
    "版權訴訟、AI 訓練資料爭議、商標判決（跨法律）",
    "獎項、收購、工作室興衰（跨產業動態）",
    "無障礙法規、包裝法規、材料科學",
]

# 週六「設計史」的受眾與寫法約束
HISTORY_BRIEF = """
受眾有兩種，必須同時餵飽：
  A. 不太懂設計、但想了解的人 —— 靠「今天的事」進來
  B. 本來就在圈內、喜歡回味的人 —— 靠「新角度」留下

寫法：用本週實際發生的事件當入口 → 帶出歷史脈絡 → 給老手一個沒想過的連結。
  ‣ 術語第一次出現時用一句話帶過，但不要整篇科普腔（會趕走 B）
  ‣ 不要寫成維基百科條目。歷史是用來解釋「為什麼今天會這樣」的
  ‣ 必須錨定本週素材。找不到夠強的連結就退回
    「本週最有話題的一件 × 它的血緣」，不硬掰
""".strip()


# ─────────────────────────────────────────────────────────────
# 3. 語言平衡配額
#
# 英語圈來源量是其他語區總和的三倍以上，放任自然排序會變成 90% 英文。
# 配額不足時「寧可少放一件」，不要用英文源補滿。
# ─────────────────────────────────────────────────────────────
LANG_QUOTA = {
    # 作品流：至少 N 件來自非英語圈
    "showcase_min_non_english": 2,
    "showcase_total": 8,
    # 產業動態：至少 N 則來自華語圈（含 Google News 中文補件）
    "industry_min_chinese": 1,
    "industry_total": 4,
    # 拆解的地區輪替（軟約束，以月為單位檢查）
    "deepdive_monthly_min": {"jp": 1, "eu": 1, "zh": 1},
}

# 語區代碼 → 是否算「非英語圈」
NON_ENGLISH_REGIONS = {"jp", "kr", "zh-tw", "zh-cn", "de", "fr", "es", "it", "nl"}
CHINESE_REGIONS = {"zh-tw", "zh-cn"}


# ─────────────────────────────────────────────────────────────
# 4. 抓取設定
# ─────────────────────────────────────────────────────────────
FETCH_TIMEOUT = int(os.getenv("RES_FETCH_TIMEOUT", "20"))
MAX_PER_SOURCE = int(os.getenv("RES_MAX_PER_SOURCE", "15"))
DEFAULT_DAYS_BACK = int(os.getenv("RES_DAYS_BACK", "2"))

# 低頻源（實測最後更新已隔月）套較寬的時間窗，但不能不套 ——
# 不套的話它們的出貨量反而是全站最大的，而且全是舊文。
LOW_FREQ_DAYS = int(os.getenv("RES_LOW_FREQ_DAYS", "21"))
LOW_FREQ_MAX = int(os.getenv("RES_LOW_FREQ_MAX", "4"))

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 縮圖長邊上限（版權原則：只存縮圖，原圖一律連回來源）
THUMB_MAX_EDGE = int(os.getenv("RES_THUMB_MAX_EDGE", "600"))


# ─────────────────────────────────────────────────────────────
# 5. LLM 設定
#
# 兩段式：Cloudflare vision 讀圖（吐英文描述）→ Mistral 寫繁中拆解。
# 理由見 README 七：CF 的繁中生成品質不足，且 output token 單價是 input 的 14 倍。
# ─────────────────────────────────────────────────────────────
_LLM_CFG_FILE = BASE_DIR / ".resolution_llm_config.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_cfg = _load_json(_LLM_CFG_FILE)

# d8ai gateway（litellm proxy，OpenAI 相容）。
# 原本規劃用 Mistral 免費層，但實測那把金鑰的配額被降為 0
# （429 且 x-ratelimit-limit-req-minute: 0），整條文字生成的路是斷的。
LLM_CFG = {
    "base_url": os.getenv("RES_LLM_BASE_URL") or _cfg.get("base_url", "https://llm-gateway.d8ai.ai/"),
    "api_key":  os.getenv("RES_LLM_API_KEY")  or _cfg.get("api_key", ""),
    "model":    os.getenv("RES_LLM_MODEL")    or _cfg.get("model", "gemma-4-31B-it"),
    "rpm":      int(os.getenv("RES_LLM_RPM", "") or _cfg.get("rpm", 45)),
}

VISION_CFG = {
    "cf_account_id": os.getenv("RES_CF_ACCOUNT_ID", ""),
    "cf_api_token":  os.getenv("RES_CF_API_TOKEN", ""),
    "cf_model":      os.getenv("RES_CF_VISION_MODEL",
                               "@cf/meta/llama-3.2-11b-vision-instruct"),
    # 一次拆解最多讀幾張圖
    "max_images":    int(os.getenv("RES_VISION_MAX_IMAGES", "4")),
    # 每日 neuron 預算上限（帳號與「晨誌」共用 10,000/天，這裡自我節制）
    "daily_neuron_budget": int(os.getenv("RES_CF_NEURON_BUDGET", "1200")),
}

# 送進 vision 前先縮到這個長邊。
# input token 是照畫素量算的，送原圖（動輒 4000px / 7MB）純粹白燒 neurons，
# 而且 CF 的 request body 也吃不下。1024 足夠辨識字體特徵與格線。
VISION_INPUT_EDGE = int(os.getenv("RES_VISION_INPUT_EDGE", "1024"))

# 絕不使用生圖模型 —— 對設計媒體來說生成封面是自傷（README 六）
ENABLE_IMAGE_GENERATION = False
