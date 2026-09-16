"""
原文正文抓取
============

RSS 的 summary 是給「要不要點進去」用的一句話，不是拿來寫文章的材料。
實測 2026-09-07 那批 372 則：中位數 203 字，一半以上不到 200 字，
內容是「Directed by Love Song's Will Dohrn, the dynamic new spot is…」這種程度。

拿這種東西加一張圖去寫一篇六百字的拆解，模型只剩一條路 —— 看圖瞎猜。
於是就出現最傷的那種錯：版面上那張圖是展場照或列表縮圖，
文章卻從頭到尾在談「這張海報」。讀者點連結進去，裡面根本沒有海報。

所以今日一件的候選在寫之前先把連結頁抓下來，取出正文餵進 prompt。
一天最多 DEEPDIVE_TRIES 個候選，也就是最多幾次 HTTP —— 成本可以忽略，
但「這是什麼東西」從此有原文可依據，不必靠視覺模型的推測。

抓不到不算故障（付費牆、JS 才長內容的站台都會抓不到），
呼叫端拿到空字串就退回只有摘要的模式，並且在 prompt 裡講明白：
現在是低證據狀態，不准斷言品類。
"""

from __future__ import annotations
import re
import ssl
import urllib.request

from bs4 import BeautifulSoup  # type: ignore

from config import FETCH_TIMEOUT, USER_AGENT

# 與 fetcher 同樣的理由：少數站台憑證設定有問題，但內容本身可信
_LAX = ssl.create_default_context()
_LAX.check_hostname = False
_LAX.verify_mode = ssl.CERT_NONE

# 讀多少 HTML。設計媒體的文章頁含一堆 inline SVG 和 JSON-LD，
# 400KB 是實測能完整含住正文的量，再多是在下載追蹤腳本。
MAX_BYTES = 900_000

# 送進 prompt 的正文上限。ministral-14b 吃得下更多，但小模型餵太長
# 反而會抓不到重點 —— 設計媒體的文章本體多半 2,000–4,000 字元，
# 超過的部分通常已經是「延伸閱讀」那類尾巴。
MAX_CHARS = 5_000

# 整段丟掉的節點：導覽、頁尾、社群分享、腳本
_DROP_TAGS = ("script", "style", "noscript", "nav", "header", "footer",
              "aside", "form", "iframe", "svg", "button", "template")

# class／id 命中就丟。設計媒體的文章頁裡混最多的就是這幾種區塊，
# 留著會讓「相關文章」的標題被當成正文寫進文章裡。
_JUNK_ATTR = re.compile(
    r"(share|social|newsletter|subscribe|signup|related|more-?stor|read-?more|"
    r"promo|advert|sponsor|sidebar|comment|cookie|consent|breadcrumb|"
    r"pagination|author-?bio|popular|trending|tag-?list|byline-?social|"
    r"nav|menu|modal|banner)", re.I)

# 正文裡有意義的區塊。figcaption 一定要留 ——
# 設計師、攝影師、作品名稱常常只出現在圖說裡。
_BLOCK_TAGS = ("p", "h2", "h3", "h4", "li", "figcaption", "blockquote", "dd")

_BOILERPLATE = re.compile(
    r"^(share this|sign up|subscribe|read more|related stories?|advertisement|"
    r"photo(graphy)? (is |)by |all images? courtesy|follow us|"
    r"the post .+ appeared first on)", re.I)


def _get_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "text/html,application/xhtml+xml,*/*",
                 "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.6"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=_LAX) as resp:
        raw = resp.read(MAX_BYTES)
    charset = (resp.headers.get_content_charset() if hasattr(resp, "headers") else None)
    return raw.decode(charset or "utf-8", "ignore")


def _junky(node, container=None) -> bool:
    """
    這個節點或它在容器**以內**的任一祖先是不是「不是正文」的區塊。

    走到容器就停 —— 容器外面的祖先一概不看。實測 CSS-Tricks 把正文包在
    <div class="articles-and-sidebar"> 裡，往上多走一層就命中 sidebar，
    於是整篇正文被判成側欄，一個字都留不下來。
    """
    cur = node
    for _ in range(6):          # 只往上找幾層，整棵樹走完不划算
        if cur is None or cur is container or getattr(cur, "attrs", None) is None:
            return False
        ident = " ".join(
            [" ".join(cur.get("class") or []), str(cur.get("id") or ""),
             str(cur.get("role") or "")])
        if ident.strip() and _JUNK_ATTR.search(ident):
            return True
        cur = cur.parent
    return False


def _p_weight(node) -> int:
    """這個容器底下的段落總長。挑正文容器用的分數。"""
    return sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p"))


def _pick_container(soup: BeautifulSoup):
    """
    找正文容器。

    先看語意標記（<article>、itemprop=articleBody、常見的 entry-content），
    全都沒有才退回「段落總長最大的那個 div」。
    先挑語意標記是因為有些站台的側欄段落量比正文還大（Dezeen 的
    「相關文章」整欄都是 <p>），純比長度會挑錯。
    """
    cands = []
    cands += soup.find_all("article")
    cands += soup.select('[itemprop="articleBody"], [class*="article-body"], '
                         '[class*="article-content"], [class*="entry-content"], '
                         '[class*="post-content"], [class*="post-body"]')
    cands = [c for c in cands if _p_weight(c) >= 200]

    if not cands:
        cands = [c for c in soup.find_all(["main", "div", "section"])
                 if _p_weight(c) >= 400]
        # 段落總長一樣時取比較深的那個 —— 外層容器一定包住內層，
        # 取外層會把導覽和頁尾一起帶進來
        cands.sort(key=lambda c: (_p_weight(c), len(list(c.parents))))
        return cands[-1] if cands else soup.body or soup

    return max(cands, key=_p_weight)


def _meta_description(soup: BeautifulSoup) -> str:
    for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
        m = soup.select_one(sel)
        if m and m.get("content"):
            return re.sub(r"\s+", " ", m["content"]).strip()
    return ""


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()

    container = _pick_container(soup)

    lines, seen = [], set()
    for node in container.find_all(_BLOCK_TAGS):
        if _junky(node, container):
            continue
        txt = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(txt) < 3 or _BOILERPLATE.match(txt):
            continue
        # 巢狀標籤會讓同一段文字出現兩次（<li><p>…）
        key = txt[:120]
        if key in seen:
            continue
        seen.add(key)
        lines.append(txt)

    text = "\n".join(lines).strip()

    # 正文抓不動（付費牆、JS 才長內容）時，meta description 至少比 RSS 摘要完整
    if len(text) < 200:
        desc = _meta_description(soup)
        if len(desc) > len(text):
            text = desc

    return text[:MAX_CHARS]


def fetch_article(url: str) -> dict:
    """
    回傳 {"text": 正文, "chars": 長度, "error": 失敗原因}。

    失敗不丟例外 —— 抓不到正文只是回到「只有摘要」的舊狀態，
    不該讓整個候選出局（它可能本來就是摘要就夠厚的來源）。
    """
    if not url:
        return {"text": "", "chars": 0, "error": "沒有連結"}
    try:
        html = _get_html(url)
    except Exception as e:  # noqa: BLE001
        return {"text": "", "chars": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}

    try:
        text = extract_text(html)
    except Exception as e:  # noqa: BLE001
        return {"text": "", "chars": 0, "error": f"解析失敗 {type(e).__name__}"}

    if len(text) < 120:
        # 抓到了但沒有東西 —— 與「連不上」要分開講，不然查起來會往錯的方向找
        return {"text": text, "chars": len(text), "error": "頁面抓到了但取不出正文"}
    return {"text": text, "chars": len(text), "error": ""}
