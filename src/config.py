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
# 2. 每日一件作品
#
# 這個站每天只做一件事：介紹一件設計，給圈內人也給圈外人。
# 原本的「週五跨界／週六設計史／週日休息」拿掉了 —— 那兩天談的是議題和
# 脈絡，不是一件看得到的作品，讀者每天打開的期待會不一樣。
# 跨界與歷史沒有消失，它們變成「多角度欣賞」裡的兩個鏡頭
# （lens: context / time），在作品本身帶得到的時候才談。
#
# 分類用絕對日數輪播而不是綁星期：四個分類配七天除不盡，
# 綁星期會讓某一類永遠比別類多曝光。
# ─────────────────────────────────────────────────────────────
CATEGORY_CYCLE = ["visual_brand", "interface_ux", "product_object", "space_env"]


def category_of_day(d) -> str:
    """d 是 datetime.date。用絕對日數輪播，四類平均分配。"""
    return CATEGORY_CYCLE[d.toordinal() % len(CATEGORY_CYCLE)]


# ── 作品池 ──
# 每天抓到的東西先進池子存著，不是當天用不到就丟。
# 好作品不會剛好每天出現在 RSS 前幾則；池子越跑越厚，選題品質才會單調上升。
# 保鮮期 90 天：足夠讓好作品浮上來，又不會出現「這什麼老東西」。
POOL_MAX_AGE_DAYS = int(os.getenv("RES_POOL_MAX_AGE_DAYS", "90"))
POOL_MAX_SIZE = int(os.getenv("RES_POOL_MAX_SIZE", "1500"))
# 一天最多試幾個候選：第一個沒過品質閘就換下一個。
# 從 3 提到 5 —— 實測有整天三個候選全倒的情況（模型編造精確尺寸，
# 被事實錨定砍光）。一次失敗約兩次呼叫，而 Mistral 的額度是
# 30 req/min，多試兩個的成本遠低於「主菜缺席一天」。
DEEPDIVE_TRIES = int(os.getenv("RES_DEEPDIVE_TRIES", "5"))


# ── 多角度欣賞的鏡頭 ──
# 不固定七軸。每篇挑 3–5 個「這件作品真的談得動」的角度 ——
# 對一張海報硬談「工法」、對一張椅子硬談「三秒讀到什麼」，
# 出來的都是廢話。鏡頭名稱一律用白話，本身就是給圈外人的入口。
LENSES = {
    "color":    ("顏色",         "用了哪些顏色、彼此什麼關係、為什麼是這幾個"),
    "type":     ("字",           "字的個性、粗細寬窄、大小與間距的安排"),
    "layout":   ("東西怎麼擺",   "位置、比例、格線、視線先看哪再看哪"),
    "material": ("用什麼做的",   "材質、表面處理、怎麼被做出來、摸起來像什麼"),
    "message":  ("它在說什麼",   "三秒內讀到什麼、先讀到哪個、資訊的先後順序"),
    "context":  ("放在同類裡看", "同類的東西長什麼樣，這件是跟著走還是掉頭"),
    "tradeoff": ("它放棄了什麼", "為了得到 A 犧牲了 B；目標換成 C 這選擇就不成立"),
    "use":      ("用起來會怎樣", "實際拿在手上／走進去／滑到它時發生什麼、看不看得清楚"),
    "time":     ("放到時間裡",   "十年前做得出來嗎、十年後會顯得舊嗎、它的血緣是什麼"),
}

# ── 術語表 ──
# 這個站是「踏入設計的媒介」，所以術語不是不能用，是不能不解釋。
# 入口（hook）和出口（給所有人的帶走）一個術語都不准出現；
# 中間的角度可以用，但第一次出現要給白話解釋。
#
# 解釋寫死在這裡，不叫模型每天重寫。三個理由：
#   1. 這批詞是固定的，沒有理由每天花一次呼叫重新產生
#   2. 跨天用詞一致 —— 讀者第二次看到「字腔」時，讀到的是同一句話
#   3. 不會失敗。實測靠 LLM 補寫時，回傳的 key 對不上就整篇卡在
#      「用了術語但沒解釋」，五個候選全倒
JARGON: dict[str, str] = {
    # 字
    "字腔": "字母中間圍起來的那塊空白，像 o 和 e 中間的洞，它的大小決定字看起來鬆還是緊。",
    "字重": "字的粗細。同一套字通常有細、標準、粗好幾種，用來分主次。",
    "襯線": "筆畫末端那個小小的收尾，像印刷體的「一」兩端翹起來的地方。",
    "無襯線": "筆畫末端沒有收尾裝飾的字，看起來比較乾淨現代，手機介面幾乎都是這種。",
    "字級": "字的大小。",
    "行距": "上下兩行之間的距離，太擠會看不下去，太鬆會散掉。",
    "字距": "字與字之間的距離。",
    "字面": "一個字實際佔掉的框有多滿。",
    "字碗": "字母下半部圍起來的弧形，像 b、p 那個圓肚子。",
    "斜體": "往右傾斜的字，通常用來強調或標示外文書名。",
    "等寬": "每個字佔一樣寬的字，程式碼編輯器用的就是這種。",
    "字型家族": "同一套字的各種變化（細、粗、斜、窄）合起來的一整組。",
    "可變字型": "一個檔案裡就能連續調整粗細寬窄的字，不必分成好幾個檔。",
    # 排版
    "網格": "看不見的格子線，用來把文字和圖片對齊，讓版面看起來是安排過的。",
    "格線": "看不見的格子線，用來把文字和圖片對齊，讓版面看起來是安排過的。",
    "欄位": "版面上直的分欄，報紙分三欄、四欄就是這個意思。",
    "出血": "印刷時圖片故意超出裁切線一點，裁完才不會露出白邊。",
    "負空間": "東西之間沒有填東西的地方。它不是浪費，是讓主角被看見的方法。",
    "視覺層級": "誰先被看到、誰後被看到的順序，靠大小、粗細、顏色排出來。",
    "對齊": "把元素的邊或中心線對到同一條線上。",
    "版心": "版面上實際放內容的那一塊，四周留白之外的範圍。",
    "天地": "版面上下的留白。",
    "留白率": "版面上空著的比例。",
    "跨頁": "書刊攤開後左右兩頁當成一個整體來設計。",
    "開數": "紙張裁切的規格，決定成品多大，A4 就是一種開數。",
    # 色與印刷
    "色相": "顏色本身是紅是藍還是綠。",
    "飽和度": "顏色有多鮮豔，從灰灰的到很濃的。",
    "明度": "顏色有多亮或多暗。",
    "彩度": "顏色有多鮮豔，從灰灰的到很濃的。",
    "對比度": "兩個顏色差多遠。差得夠遠字才看得清楚，這也是無障礙的基本要求。",
    "CMYK": "印刷用的四種油墨（青、洋紅、黃、黑），螢幕上的顏色印出來會略有落差。",
    "RGB": "螢幕發光混出顏色的方式（紅、綠、藍）。",
    "Pantone": "一套國際通用的色票編號，讓不同印刷廠印出來的顏色能對得起來。",
    "特別色": "四色油墨調不出來、要另外單獨調的顏色，例如金色、螢光色。",
    "專色": "四色油墨調不出來、要另外單獨調的顏色，例如金色、螢光色。",
    "燙金": "用金屬箔在紙上壓出會反光的圖案。",
    "打凸": "把紙壓出凸起的形狀，用手摸得出來。",
    "上光": "在印刷品表面加一層膜，可以是亮的或霧的。",
    "網版": "把油墨透過有孔的網子刮印上去，T 恤印圖常用這種。",
    "凹版": "把圖案刻進版材再上墨，印量大時用的傳統工法。",
    "模切": "用刀模把紙裁成非方形的形狀。",
    "壓紋": "在紙面壓出凹凸的紋理。",
    # 產品與材質
    "導角": "把尖銳的邊角削成斜面或圓弧，摸起來不刮手。",
    "圓角": "把直角改成圓弧。",
    "陽極處理": "鋁製品表面的一層電化學處理，讓它更耐刮、也能上色，手機和筆電外殼常見。",
    "射出成型": "把熔化的塑膠打進模具裡成形，是大量生產塑膠件最常見的做法。",
    "沖壓": "用模具把金屬板一次壓出形狀。",
    "車削": "把材料固定住旋轉、用刀具削出形狀。",
    "榫接": "木頭之間互相卡住的接法，不用釘子或膠。",
    "貼皮": "在便宜的板材表面貼一層真材質的薄片。",
    "公差": "實際做出來允許和設計圖差多少，差太多零件就裝不起來。",
    "分模線": "模具兩半合起來的地方，在成品上會留下一條細線。",
    "拔模角": "為了讓成品脫得了模，側面要留的一點斜度。",
    # 空間
    "動線": "人在空間裡實際會怎麼走。",
    "尺度": "東西相對於人體的大小感覺。",
    "立面": "建築物從正面看過去的樣子。",
    "剖面": "把建築物切開來看內部的結構關係。",
    "軸線": "貫穿空間的一條主要方向線，人會不自覺沿著它走。",
    "採光井": "為了把自然光引進建築深處而留的垂直開口。",
    "帷幕牆": "掛在結構外側、不承重的外牆，大樓的整面玻璃就是。",
    # 介面
    "資訊架構": "內容怎麼分類和分層，決定使用者找不找得到東西。",
    "線框": "只有框和位置、還沒上視覺的設計草圖。",
    "原型": "可以點、可以操作的模型，用來在真的做出來之前先試。",
    "響應式": "同一個網頁在手機和電腦上會自動變成不同排法。",
    "斷點": "版面切換排法的那個螢幕寬度。",
    "可用性": "東西好不好用、會不會讓人卡住。",
    "無障礙": "讓視力、聽力、行動不便的人也用得了的設計要求。",
    "設計系統": "一整套講好的顏色、字級、元件規則，讓不同人做出來的畫面長得像同一個產品。",
    "元件庫": "可以重複使用的介面零件（按鈕、輸入框）的集合。",
    "微互動": "按下去會有回饋的小動作，例如按鈕變色、開關滑動。",
    "點擊熱區": "手指或滑鼠實際點得到的範圍，比看得見的圖示大一點才好按。",
}

JARGON_TERMS = list(JARGON)


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
    "feature_monthly_min": {"jp": 1, "eu": 1, "zh": 1},
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

# 進作品池用的窗口，比出刊窗口寬得多。
#
# 2026-09-07（週一）實測：Core77 最新一篇 2 天前、Creative Review 2 天前、
# Muzli 3 天前 —— 歐美媒體週末不發文，2 天的窗口在週一會把整個週五排除掉，
# 而且沒有任何機制回頭補，那些文章就永遠看不到了。
# 池子本來就用 url 去重，重複看到舊條目完全不花成本，所以放寬到 7 天。
# 出刊的作品流與產業動態仍然只取 DEFAULT_DAYS_BACK 內的，版面不會變舊。
POOL_DAYS_BACK = int(os.getenv("RES_POOL_DAYS_BACK", "7"))

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

# 文字模型可以整組切換 —— base_url／model／key 是綁在一起的，
# 只換其中一個必壞（Mistral 的 base_url 帶 /v1，其他家不一定帶）。
#
# 2026-09-07 實測，這把 Mistral 金鑰的額度是**分模型**發的，不是整個 workspace 為零：
#   ✓ ministral-3b / 8b / 14b、open-mistral-nemo、codestral   （30 req/min）
#   ✗ mistral-small / medium / magistral                       （limit-req-minute: 0）
# 所以選 ministral-14b —— 能用的裡面最大的一顆，而且正好是開源小模型那一系。
# 同題實測比較：14b 的白話翻譯寫得最準；8b 三個角度用同一個句型；
# nemo 幻覺明顯（憑空生出「左上角男性臉孔比例較大」這種畫面裡沒有的東西）。
LLM_PROVIDERS = {
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "model":    "ministral-14b-latest",
        "rpm":      28,      # 實測上限 30，留兩格緩衝
    },
    # 之後要換成自架的開源模型走這條：Ollama／vLLM／LM Studio 都是 OpenAI 相容，
    # 只要 base_url 指過去、model 換成本機跑的那顆，程式一行都不用改。
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model":    "qwen2.5:14b",
        "rpm":      600,     # 自己的機器，不必節流
    },
    # 保留但不預設 —— 這是外部 gateway，不是自己的東西
    "d8ai": {
        "base_url": "https://llm-gateway.d8ai.ai/",
        "model":    "gemma-4-31B-it",
        "rpm":      45,
    },
}

# Cloudflare Workers AI 也有 OpenAI 相容端點，而且讀圖那條路已經有這個帳號了 ——
# 不必再開一個服務就有備援。實測（2026-09-07，同題）：
#   @cf/qwen/qwen3-30b-a3b-fp8               19 neurons，中文寫得最活
#     （「摸起來像踩在回收物上」）。是 reasoning 模型，max_tokens 要給足
#   @cf/mistralai/mistral-small-3.1-24b      24 neurons，穩，但用詞較套語
#   @cf/meta/llama-3.3-70b-instruct-fp8-fast 52 neurons，body 只是把材料重講一遍
#   @cf/qwen/qwen3.8-27b、@cf/google/gemma-4-26b   回空字串，不能用
# 一篇約兩次呼叫，成本落在 40–60 neurons/天，遠低於自訂的 1200 預算。
_CF_ACCOUNT = os.getenv("RES_CF_ACCOUNT_ID") or _cfg.get("cf_account_id", "")
LLM_PROVIDERS["cloudflare"] = {
    "base_url": f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/v1",
    "model":    "@cf/qwen/qwen3-30b-a3b-fp8",
    "rpm":      60,
}

LLM_PROVIDER = (os.getenv("RES_LLM_PROVIDER") or _cfg.get("provider") or "mistral").lower()
_preset = LLM_PROVIDERS.get(LLM_PROVIDER, LLM_PROVIDERS["mistral"])
# 每家的金鑰各自收在 providers.<name> 底下；頂層的舊欄位仍然讀得到，
# 免得舊的設定檔一升級就整條斷掉。
_pcfg = (_cfg.get("providers") or {}).get(LLM_PROVIDER, {})

LLM_CFG = {
    "provider": LLM_PROVIDER,
    "base_url": os.getenv("RES_LLM_BASE_URL") or _pcfg.get("base_url") or _preset["base_url"],
    # cloudflare 這組用的是讀圖那把 CF token，不必另外給金鑰
    "api_key":  (os.getenv("RES_LLM_API_KEY") or _pcfg.get("api_key")
                 or (os.getenv("RES_CF_API_TOKEN") or _cfg.get("cf_api_token", "")
                     if LLM_PROVIDER == "cloudflare" else "")
                 or _cfg.get("api_key", "")),
    "model":    os.getenv("RES_LLM_MODEL")    or _pcfg.get("model") or _preset["model"],
    "rpm":      int(os.getenv("RES_LLM_RPM", "") or _pcfg.get("rpm") or _preset["rpm"]),
}


VISION_CFG = {
    "cf_account_id": os.getenv("RES_CF_ACCOUNT_ID") or _cfg.get("cf_account_id", ""),
    "cf_api_token":  os.getenv("RES_CF_API_TOKEN")  or _cfg.get("cf_api_token", ""),
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
