"""
把 web/ 打包成單檔預覽（圖片內嵌成 data URI）。
用途：在沒有伺服器的環境、或要在手機上檢視版面時使用。
正式部署走 web/ 原始檔 + Firebase Hosting，不使用這份。
"""
from __future__ import annotations
import base64, io, json, re, ssl, urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE


def data_uri(url: str, edge: int = 640, q: int = 72) -> str:
    """下載並縮成 ≤edge 的 JPEG data URI（也順便驗證版權原則：只用縮圖）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
            blob = r.read(20_000_000)
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        im.thumbnail((edge, edge), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=q, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  [warn] 取圖失敗 {url[:60]}：{type(e).__name__}")
        return ""


def icon_uri(name: str) -> str:
    return "data:image/png;base64," + base64.b64encode((WEB / "icons" / name).read_bytes()).decode()


def main() -> None:
    date = json.loads((WEB / "data" / "latest.json").read_text())["date"]
    data = json.loads((WEB / "data" / f"{date}.json").read_text(encoding="utf-8"))

    print("內嵌圖片中...")
    feat = data.get("feature") or data.get("deepdive") or {}
    if feat.get("image_url"):
        feat["image_url"] = data_uri(feat["image_url"], 900, 78)
    for it in data["showcase"]:
        it["image_url"] = data_uri(it["image_url"], 560, 70)
    data["showcase"] = [it for it in data["showcase"] if it["image_url"]]

    css = (WEB / "style.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    # 單檔版不 fetch，直接用內嵌資料
    js = re.sub(r"async function boot\(\)[\s\S]*?\n}\nboot\(\);",
                """function boot() {
  data = window.__DATA__;
  const dt = new Date(data.date + 'T00:00:00+08:00');
  const wd = '日一二三四五六'[dt.getDay()];
  document.getElementById('date').textContent = `${data.date}（${wd}）`;
  document.getElementById('mode').textContent = '';
  document.getElementById('next').disabled = true;
  renderFilters(); renderFeature(); renderShowcase(); renderIndustry();
}
boot();""", js)

    body = (WEB / "index.html").read_text(encoding="utf-8")
    body = body.split("<body>", 1)[1].split("</body>", 1)[0]
    body = body.replace('src="icons/icon-64.png"', f'src="{icon_uri("icon-64.png")}"')
    body = body.replace('<script src="app.js"></script>', "")

    out = f"""<title>解析度 Resolution</title>
<style>{css}</style>
{body}
<script>window.__DATA__ = {json.dumps(data, ensure_ascii=False)};</script>
<script>{js}</script>
"""
    p = ROOT / "output" / "preview.html"
    p.write_text(out, encoding="utf-8")
    print(f"寫入 {p}（{len(out)/1024:.0f} KB）")


if __name__ == "__main__":
    main()
