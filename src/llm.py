"""
LLM 包裝（OpenAI 相容介面，預設 Mistral）
==========================================

第二段用：拿視覺描述 + 原文，寫繁體中文七軸拆解。
第一段的讀圖在 vision.py（Cloudflare Workers AI）。
"""

from __future__ import annotations
import json
import threading
import time
import urllib.error
import urllib.request

from config import LLM_CFG

_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    """簡單的 RPM 節流 —— Mistral 免費層對突發請求很敏感。"""
    global _last_call
    gap = 60.0 / max(LLM_CFG["rpm"], 1)
    with _lock:
        wait = gap - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict],
         *,
         json_mode: bool = False,
         temperature: float = 0.3,
         max_tokens: int = 2000,
         retries: int = 3) -> str:
    if not LLM_CFG["api_key"]:
        raise LLMError("RES_LLM_API_KEY 沒有設定 —— "
                       "到 console.mistral.ai 申請，或寫進 .resolution_llm_config.json")

    payload: dict = {
        "model": LLM_CFG["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = LLM_CFG["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")

    last_err = ""
    for attempt in range(retries):
        _throttle()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_CFG['api_key']}",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:200]
            last_err = f"HTTP {e.code}: {detail}"
            # 429 / 5xx 值得退避重試；4xx 其他錯誤重試沒有意義
            if e.code != 429 and e.code < 500:
                break
            time.sleep(2 ** attempt * 3)
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2 ** attempt * 2)

    raise LLMError(f"LLM 呼叫失敗（{retries} 次）：{last_err}")


def chat_json(messages: list[dict], **kw) -> dict:
    """要求 JSON 輸出並解析。模型偶爾會包 ```json 圍欄，這裡一併處理。"""
    raw = chat(messages, json_mode=True, **kw)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise LLMError(f"回傳不是合法 JSON：{text[:200]}")
