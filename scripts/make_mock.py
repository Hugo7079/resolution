"""
用真實抓到的資料組一份示範用的當日檔，給前端開發與版面驗證用。
拆解文是手寫的範例（LLM 額度用完時也能開發前端），欄位結構與正式輸出一致。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sanitize import sanitize  # noqa: E402

DATE = "2026-09-04"
raw = json.loads((ROOT / "output" / f"raw_{DATE}.json").read_text(encoding="utf-8"))
raw, _ = sanitize(raw, verbose=False)

def pick(pred, n):
    return [r for r in raw if pred(r)][:n]

showcase = pick(lambda r: r["kind"] == "showcase" and r["image_url"], 8)
industry = pick(lambda r: r["kind"] == "industry" and len(r["title"]) > 12, 4)
hero = next(r for r in raw if r["source_name"] == "Dezeen" and r["image_url"])

doc = {
  "date": DATE,
  "weekday_mode": "category",
  "deepdive": {
    "title": "把「看不見的結構」變成招牌：MAD 用一片連續曲面取代了立面",
    "subject": {"name": hero["title"][:70], "designer": "MAD Architects",
                "client": "Lucas Museum of Narrative Art", "year": "2026"},
    "category": "space_env", "category_label": "空間與環境",
    "confidence": 78,
    "source_url": hero["url"], "source_name": hero["source_name"],
    "image_url": hero["image_url"],
    "credit": "圖片來源：Dezeen．著作權屬原作者",
    "axes": {
      "intent": "（示範文字）美術館要解決的是「敘事」這個抽象主題怎麼在建築上被看見。業主是說故事的人，因此建築被要求自己就是一則故事的開場，而不只是容器。",
      "form": "（示範文字）主體是一片連續曲面，沒有可辨識的樓層線；外皮以約 1.2 公尺見方的白色複合板拼成，接縫寬度控制在 12mm 上下，讓整體在遠看時讀成單一體量。開口集中在南側約三分之一處。",
      "message": "（示範文字）三秒內讀到的是「這不是一棟有樓層的房子」。資訊層級把「量體」放在第一位，入口與招牌被刻意壓到第二層級。",
      "context": "（示範文字）放在美術館建築的慣例裡，這是破格的一邊 —— 近二十年的主流是量體切分與材質分區，這件反其道而行，回到單一連續體。",
      "execution": "（示範文字）連續曲面的代價在收邊。每一片板的曲率都不同，等於放棄了標準化生產。維護時單片更換的顏色一致性是長期風險。",
      "tradeoff": "（示範文字）為了得到「一眼認得出」的輪廓，它犧牲了立面的資訊承載力 —— 指標、入口、活動訊息都無處可放，只能靠地面層另外解決。如果目標換成「日常使用的社區型場館」，這個選擇就不成立。",
      "takeaway": "（示範文字）想讓一個形體被記住，先決定「哪一層資訊要被犧牲」。把次要資訊全部移出主體，主體才會有輪廓。"
    },
    "concretes": ["1.2m 見方複合板", "12mm 接縫", "南側三分之一開口", "連續曲面（無樓層線）", "MAD Architects"]
  },
  "showcase": [{"title": r["title"], "url": r["url"], "image_url": r["image_url"],
                "source_name": r["source_name"], "region": r["region"]} for r in showcase],
  "industry": [{"title": r["title"], "url": r["url"], "source_name": r["source_name"],
                "published": r.get("published", ""), "region": r["region"]} for r in industry],
}
out = ROOT / "web" / "data" / f"{DATE}.json"
out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
(ROOT / "web" / "data" / "latest.json").write_text(
    json.dumps({"date": DATE}, ensure_ascii=False), encoding="utf-8")
print(f"寫入 {out}（作品流 {len(showcase)}、產業動態 {len(industry)}）")
