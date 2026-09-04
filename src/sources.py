"""
來源清單（2026-09-04 全數實抓驗證）
====================================

每個 source 是 dict：
  {
    "name":   顯示名稱,
    "url":    RSS / Atom feed,
    "region": 語區代碼 —— en / zh-tw / zh-cn / jp / kr / de / fr / es / it / nl,
    "cat":    預設分類（LLM 仍會覆寫，這只是先驗權重）,
    "kind":   "media" | "showcase" | "industry" | "podcast",
    "img":    "feed"（feed 內就有圖）| "og"（需 fallback 抓 og:image）,
    "freq":   "daily" | "low"（低頻源，實測最後更新已隔月，保留但不指望）,
  }

判準有三：**能抓、有圖、每天更新**。
「有 feed」不等於「能用」—— 見本檔末的 BLOCKLIST。
"""

SOURCES: list[dict] = [
    # ───────────────────────── 視覺與品牌 ─────────────────────────
    {"name": "Creative Review",   "url": "https://www.creativereview.co.uk/feed/",              "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Print Magazine",    "url": "https://www.printmag.com/feed/",                      "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Logo Design Love",  "url": "https://www.logodesignlove.com/feed",                 "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Design Observer",   "url": "https://designobserver.com/feed/",                    "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Typewolf",          "url": "https://www.typewolf.com/feed",                       "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "I Love Typography", "url": "https://ilovetypography.com/feed/",                   "region": "en", "cat": "visual_brand",   "kind": "media", "img": "og",   "freq": "low"},
    {"name": "Motionographer",    "url": "https://motionographer.com/feed/",                    "region": "en", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},

    # ───────────────────────── 介面與體驗 ─────────────────────────
    {"name": "Nielsen Norman Group", "url": "https://www.nngroup.com/feed/rss/",                "region": "en", "cat": "interface_ux",   "kind": "media", "img": "og",   "freq": "daily"},
    {"name": "Smashing Magazine",    "url": "https://www.smashingmagazine.com/feed/",           "region": "en", "cat": "interface_ux",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "A List Apart",         "url": "https://alistapart.com/main/feed/",                "region": "en", "cat": "interface_ux",   "kind": "media", "img": "og",   "freq": "low"},
    {"name": "UX Collective",        "url": "https://uxdesign.cc/feed",                         "region": "en", "cat": "interface_ux",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "CSS-Tricks",           "url": "https://css-tricks.com/feed/",                     "region": "en", "cat": "interface_ux",   "kind": "media", "img": "og",   "freq": "daily"},

    # ───────────────────────── 產品與物件 ─────────────────────────
    {"name": "Core77",       "url": "https://www.core77.com/feed",       "region": "en", "cat": "product_object", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "region": "en", "cat": "product_object", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Design Milk",  "url": "https://design-milk.com/feed/",     "region": "en", "cat": "product_object", "kind": "media", "img": "feed", "freq": "daily"},

    # ───────────────────────── 空間與環境 ─────────────────────────
    {"name": "Dezeen",     "url": "https://www.dezeen.com/feed/",        "region": "en", "cat": "space_env", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "ArchDaily",  "url": "https://www.archdaily.com/rss/",      "region": "en", "cat": "space_env", "kind": "media", "img": "og",   "freq": "daily"},
    {"name": "Wallpaper*", "url": "https://www.wallpaper.com/feeds/all", "region": "en", "cat": "space_env", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "designboom", "url": "https://www.designboom.com/feed/",    "region": "en", "cat": "space_env", "kind": "media", "img": "feed", "freq": "daily"},

    # ───────────────────────── 日文 ─────────────────────────
    {"name": "AXIS Web",           "url": "https://www.axismag.jp/feed",           "region": "jp", "cat": None,        "kind": "media",    "img": "feed", "freq": "daily"},
    {"name": "architecturephoto",  "url": "https://architecturephoto.net/feed/",   "region": "jp", "cat": "space_env", "kind": "media",    "img": "og",   "freq": "daily"},
    {"name": "Spoon & Tamago",     "url": "https://www.spoon-tamago.com/feed/",    "region": "jp", "cat": None,        "kind": "media",    "img": "feed", "freq": "daily"},
    {"name": "IDEA magazine",      "url": "https://www.idea-mag.com/feed/",        "region": "jp", "cat": "visual_brand", "kind": "media", "img": "feed", "freq": "low"},

    # ───────────────────────── 韓文 ─────────────────────────
    # 唯一存活的韓文設計源（jungle / designdb / notefolio / Brunch 全滅）
    {"name": "월간디자인 月刊 Design", "url": "https://mdesign.designhouse.co.kr/rss", "region": "kr", "cat": None, "kind": "media", "img": "feed", "freq": "daily"},

    # ───────────────────────── 簡中 ─────────────────────────
    {"name": "數英 digitaling", "url": "https://www.digitaling.com/rss",   "region": "zh-cn", "cat": "visual_brand", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "ArchDaily 中國",  "url": "https://www.archdaily.cn/cn/rss/", "region": "zh-cn", "cat": "space_env",    "kind": "media", "img": "og",   "freq": "daily"},

    # ───────────────────────── 歐陸 ─────────────────────────
    {"name": "Stylepark",          "url": "https://www.stylepark.com/en/rss",       "region": "de", "cat": "product_object", "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "PAGE Online",        "url": "https://page-online.de/feed/",           "region": "de", "cat": "visual_brand",   "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Dutch Design Daily", "url": "https://www.dutchdesigndaily.com/feed/", "region": "nl", "cat": None,             "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Étapes",             "url": "https://etapes.com/feed/",               "region": "fr", "cat": "visual_brand",   "kind": "media", "img": "og",   "freq": "daily"},
    {"name": "Yorokobu",           "url": "https://www.yorokobu.es/feed/",          "region": "es", "cat": None,             "kind": "media", "img": "feed", "freq": "daily"},
    {"name": "Abitare",            "url": "https://www.abitare.it/en/feed/",        "region": "it", "cat": "space_env",      "kind": "media", "img": "feed", "freq": "low"},

    # ───────────────────────── 繁中 ─────────────────────────
    # 台灣可用的 RSS 只剩這一家（其餘全滅，見 BLOCKLIST）。
    # 主要靠 tw_scraper.py 的 TDRI / 金點 HTML 抓取補。
    {"name": "Shopping Design", "url": "https://www.shoppingdesign.com.tw/rss", "region": "zh-tw", "cat": None, "kind": "media", "img": "feed", "freq": "daily"},

    # ───────────────────────── 作品流（只取圖，不做分析） ─────────────────────────
    {"name": "Behance",    "url": "https://www.behance.net/feeds/projects",             "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Awwwards",   "url": "https://www.awwwards.com/blog/feed/",                "region": "en", "cat": "interface_ux", "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Muzli",      "url": "https://medium.com/feed/muzli-design-inspiration",   "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Abduzeedo",  "url": "https://abduzeedo.com/rss.xml",                      "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Colossal",   "url": "https://www.thisiscolossal.com/feed/",               "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Booooooom",  "url": "https://www.booooooom.com/feed/",                    "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "daily"},
    {"name": "Sight Unseen","url": "https://www.sightunseen.com/feed/",                 "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "low"},
    {"name": "Trendland",  "url": "https://trendland.com/feed/",                        "region": "en", "cat": None, "kind": "showcase", "img": "feed", "freq": "low"},
    {"name": "Fubiz",      "url": "https://www.fubiz.net/feed/",                        "region": "fr", "cat": None, "kind": "showcase", "img": "feed", "freq": "low"},
    {"name": "Ignant",     "url": "https://www.ignant.com/feed/",                       "region": "de", "cat": None, "kind": "showcase", "img": "feed", "freq": "low"},

    # ───────────────────────── 產業動態 ─────────────────────────
    {"name": "Fast Company Design", "url": "https://www.fastcompany.com/co-design/rss", "region": "en", "cat": None, "kind": "industry", "img": "feed", "freq": "daily"},
    {"name": "Design Week",         "url": "https://www.designweek.co.uk/feed/",        "region": "en", "cat": None, "kind": "industry", "img": "feed", "freq": "daily"},
    {"name": "Creative Bloq",       "url": "https://www.creativebloq.com/feeds/all",    "region": "en", "cat": None, "kind": "industry", "img": "feed", "freq": "daily"},
    {"name": "Sidebar",             "url": "https://sidebar.io/feed.xml",               "region": "en", "cat": None, "kind": "industry", "img": "og",   "freq": "daily"},
    {"name": "Web Designer News",   "url": "https://www.webdesignernews.com/feed",      "region": "en", "cat": None, "kind": "industry", "img": "og",   "freq": "daily"},

    # ───────────────────────── Podcast（週六設計史素材） ─────────────────────────
    {"name": "99% Invisible", "url": "https://feeds.simplecast.com/BqbsxVfO", "region": "en", "cat": None, "kind": "podcast", "img": "feed", "freq": "daily"},
    {"name": "ShopTalk",      "url": "https://shoptalkshow.com/feed/podcast/", "region": "en", "cat": "interface_ux", "kind": "podcast", "img": "og", "freq": "daily"},
]


# Google News 中文補件 —— 繁中破口的補救之一
GOOGLE_NEWS_QUERIES_ZH = [
    "品牌識別 設計", "包裝設計 台灣", "設計獎 台灣",
    "字體 設計", "展覽 視覺設計", "工業設計 台灣", "室內設計 獲獎",
]


# ─────────────────────────────────────────────────────────────
# 黑名單 —— 實測過、明確不能收，避免日後有人「順手加回來」
# ─────────────────────────────────────────────────────────────
BLOCKLIST = {
    # 網站被 SEO spam 佔領：feed 回 200 且格式正確，但內容是
    # 「工業廠房貸款」「燒賣批發」「櫥下淨水器」。只看狀態碼會直接灌垃圾進站。
    "https://www.tdm.org.tw/feed/": "台灣設計館 —— WordPress 遭 SEO spam 佔領（2026-09 驗證）",

    # 無公開介面：Graph API 只能讀自己帳號，TikTok Research API 限學術機構。
    # 爬蟲違反 ToS 且每隔幾週就壞，不能當每日排程的相依。
    "threads.net":  "無公開介面",
    "tiktok.com":   "Research API 限學術機構",
    "instagram.com":"Graph API 只能讀自己帳號",

    "https://dribbble.com/shots/popular.rss": "RSS 已停用（回 202 空內容）",
    "https://www.reddit.com/r/design/.rss":   "429，需 OAuth",
}

# feed 已失效（404 / DNS 失效 / TLS 過舊 / 憑證過期），別再試
DEAD_FEEDS = {
    "en":    ["It's Nice That", "Eye on Design (AIGA)", "Domus", "Frame", "Detail (DE)",
              "Baunetz (DE)", "Experimenta (ES)", "Product Hunt（feed 無圖無用）"],
    "jp":    ["JDN（憑證過期）", "Casa BRUTUS", "Pen Online", "MdN", "SHIFT", "Tokyo Art Beat"],
    "kr":    ["디자인정글 jungle", "designdb (KIDP)", "notefolio", "Brunch"],
    "zh-cn": ["站酷 ZCOOL", "优设 UISDC", "gooood 谷德", "有方空間", "普象工業設計"],
    "zh-tw": ["設計發浪（DNS 失效）", "台灣設計研究院 feed", "MOT TIMES（TLS 版本過舊）",
              "La Vie", "MyDesy", "大人物", "城市美學新態度"],
}
