"""
第一段：Cloudflare Workers AI 讀圖
==================================

只做一件事：**客觀描述看到什麼**，輸出英文，不評論。

為什麼不讓它直接寫拆解文（README 七）：
  1. CF 這顆模型的繁中生成會簡繁混雜、用詞生硬，而拆解文是產品門面
  2. output token 的 neuron 單價是 input 的 14 倍
     （4,410／M input vs 61,493／M output）——
     讓它少講話，成本直接掉一個量級

免費額度 10,000 neurons／天是**帳號層級**，與「晨誌」共用同一鍋。
這裡自我節制在 VISION_CFG["daily_neuron_budget"]，用量寫進 output/cf_usage.json，
跨次執行累計，超過就停手（而不是把晨誌的生圖額度吃掉）。
"""

from __future__ import annotations
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import date

from config import OUTPUT_DIR, USER_AGENT, VISION_CFG, VISION_INPUT_EDGE
from fetcher import upgrade_image_url

_LAX = ssl.create_default_context()
_LAX.check_hostname = False
_LAX.verify_mode = ssl.CERT_NONE

_USAGE_FILE = OUTPUT_DIR / "cf_usage.json"

# 官方單價（2026-09 查證）
NEURONS_PER_M_INPUT = 4_410
NEURONS_PER_M_OUTPUT = 61_493

DESCRIBE_PROMPT = """You are a visual analyst documenting a design artefact.

Describe ONLY what is objectively visible. Do NOT evaluate, praise, or criticise.
Do NOT speculate about intent.

Report these, each on its own line:
- TYPOGRAPHY: classification (serif/sans/slab/script/display), weight, width,
  distinctive letterform features (terminals, aperture, contrast, x-height).
  Name the typeface ONLY if you are certain; otherwise describe the features.
- COLOR: dominant colors as approximate hex values, how many, and the contrast relationship.
- COMPOSITION: grid or column structure if visible, alignment, symmetry,
  approximate proportion of empty space, where the focal point sits.
- MATERIAL: for physical objects — material, finish, apparent production method.
- FORMAT: what kind of artefact this is and its apparent medium.
- TEXT: any legible text content.

If something cannot be determined from the image, write "not determinable".
Never guess. Guessing a typeface name is worse than describing its features.

Be terse. Under 180 words total."""


def _load_usage() -> dict:
    try:
        return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_usage(d: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def used_today() -> float:
    return float(_load_usage().get(date.today().isoformat(), 0.0))


def _record(neurons: float) -> None:
    d = _load_usage()
    key = date.today().isoformat()
    d[key] = round(float(d.get(key, 0.0)) + neurons, 2)
    # 只留最近 30 天
    for k in sorted(d)[:-30]:
        d.pop(k, None)
    _save_usage(d)


def budget_left() -> float:
    return VISION_CFG["daily_neuron_budget"] - used_today()


def _fetch_image(url: str, max_bytes: int = 30_000_000) -> bytes | None:
    """
    抓圖並縮到長邊 VISION_INPUT_EDGE。

    兩個理由：原圖動輒 7MB 以上（CF 的 request body 吃不下），
    而且 input token 是照圖的畫素量算的 —— 送 4000px 進去純粹白燒 neurons。
    """
    data = None
    for candidate in [upgrade_image_url(url), url]:
        try:
            req = urllib.request.Request(candidate, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30, context=_LAX) as resp:
                blob = resp.read(max_bytes + 1)
            if blob and len(blob) <= max_bytes:
                data = blob
                break
        except Exception:
            continue
    if data is None:
        return None

    try:
        from PIL import Image  # 延後 import，沒裝也不影響抓取層
        import io
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        edge = VISION_INPUT_EDGE
        if max(im.size) > edge:
            im.thumbnail((edge, edge), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        print(f"  [vision] 縮圖失敗（{type(e).__name__}），改送原圖")
        return data if len(data) <= 6_000_000 else None


class VisionError(RuntimeError):
    pass


def describe_image(image_url: str, max_tokens: int = 320) -> tuple[str, float]:
    """
    回傳 (英文客觀描述, 這次花掉的 neurons)。
    抓不到圖或呼叫失敗回 ("", 0.0) —— 呼叫端自行決定要不要退場。
    """
    account = VISION_CFG["cf_account_id"]
    token = VISION_CFG["cf_api_token"]
    if not account or not token:
        raise VisionError("RES_CF_ACCOUNT_ID / RES_CF_API_TOKEN 沒有設定")

    if budget_left() <= 0:
        print(f"  [vision] 今日自訂預算 {VISION_CFG['daily_neuron_budget']} neurons 已用完，跳過")
        return "", 0.0

    blob = _fetch_image(image_url)
    if blob is None:
        return "", 0.0

    url = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
           f"/ai/run/{VISION_CFG['cf_model']}")
    payload = {
        "image": list(blob),           # CF vision 模型吃 uint8 array
        "prompt": DESCRIBE_PROMPT,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        if e.code == 429:
            print("  [vision] 429 —— 帳號當日 neuron 用完（與晨誌共用），停手")
            _record(budget_left())      # 標記為用盡，本日不再嘗試
            return "", 0.0
        raise VisionError(f"HTTP {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise VisionError(f"{type(e).__name__}: {e}") from e

    result = data.get("result") or {}
    text = (result.get("response") or result.get("description") or "").strip()

    # 有 usage 就用實際值，沒有就用長度估算（1 token ≈ 4 bytes）
    usage = result.get("usage") or data.get("usage") or {}
    tin = int(usage.get("prompt_tokens") or 0) or (len(blob) // 750 + len(DESCRIBE_PROMPT) // 4)
    tout = int(usage.get("completion_tokens") or 0) or (len(text) // 4)
    neurons = tin / 1e6 * NEURONS_PER_M_INPUT + tout / 1e6 * NEURONS_PER_M_OUTPUT
    _record(neurons)
    return text, neurons


def describe_images(image_urls: list[str], limit: int | None = None) -> tuple[list[str], float]:
    """讀多張圖。回傳 (描述清單, 總 neurons)。"""
    limit = limit or VISION_CFG["max_images"]
    out, total = [], 0.0
    for u in image_urls[:limit]:
        try:
            desc, n = describe_image(u)
        except VisionError as e:
            print(f"  [vision] {str(e)[:90]}")
            break
        total += n
        if desc:
            out.append(desc)
    return out, total
