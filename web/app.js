/* 解析度 Resolution —— 前端
   資料來源：web/data/{date}.json（本地與 Firestore 之後由 config.json 切換）*/

const CATS = [
  { id: 'visual_brand',   label: '視覺與品牌' },
  { id: 'interface_ux',   label: '介面與體驗' },
  { id: 'product_object', label: '產品與物件' },
  { id: 'space_env',      label: '空間與環境' },
];

const CAT_LABEL = Object.fromEntries(CATS.map(c => [c.id, c.label]));

/* 鏡頭代號 → 白話標籤。名稱本身就是給圈外人的入口，所以不用術語。
   要和 src/config.py 的 LENSES 對齊。 */
const LENS_LABEL = {
  color: '顏色', type: '字', layout: '東西怎麼擺', material: '用什麼做的',
  message: '它在說什麼', context: '放在同類裡看', tradeoff: '它放棄了什麼',
  use: '用起來會怎樣', time: '放到時間裡',
};

/* 舊格式（2026-09 以前的當日檔）用固定七軸。歷史頁還讀得到那些檔案，
   所以保留一份對照表，讓舊的日子照樣打得開。 */
const LEGACY_AXES = [
  ['intent', '意圖'], ['form', '形式'], ['message', '訊息'],
  ['context', '脈絡'], ['execution', '落地'], ['tradeoff', '取捨'],
];

const REGION_FLAG = {
  'zh-tw': '台', 'zh-cn': '中', jp: '日', kr: '韓',
  de: '德', fr: '法', es: '西', it: '義', nl: '荷',
};

/* 四個分類是「用哪一類看過往」，不是篩當天的版面。
   一天只有 8 件作品流、4 則產業動態，切成四類每格剩兩件 —— 篩了也沒東西看；
   而且作品流的來源（Behance、Colossal 這種）本來就跨類，給不出可靠的分類。
   真正每天都有可靠分類的是「今日一件」（分類由 LLM 判、寫在 index.json），
   所以 chip 管的是最下面那面「過往」牆，外加上一天／下一天走哪些日子：
   點「空間與環境」＝ 牆上只留空間類的日子，前後翻也只在那幾天之間跳。

   chip 不會自己換日 —— 一次點擊做兩件事（跳日 + 換牆）會讓人不知道
   剛剛發生了什麼。要看哪一天，牆上點那張卡。 */
const KEY = 'resolution.cats';
let active = new Set(load());
let data = null;

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || []; }
  catch { return []; }
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify([...active])); } catch { /* 無痕模式會丟 */ }
}

const el = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c; if (x) n.textContent = x; return n; };
const esc = s => String(s ?? '');

/* 選了分類之後，仍然是可以前後翻的那串日子。沒選＝全部。 */
function navDays() {
  if (!active.size) return days.map(d => d.date);
  return days.filter(d => active.has(d.category)).map(d => d.date);
}

function renderFilters() {
  const box = document.getElementById('filters');
  box.innerHTML = '';

  CATS.forEach(c => {
    const n = days.filter(d => d.category === c.id).length;
    const b = el('button', 'chip', c.label);
    if (n) b.appendChild(el('span', 'chip__n', n));
    b.setAttribute('aria-pressed', active.has(c.id));
    // 一天都沒有的分類點下去只會把導覽清空，不如先擋著
    b.disabled = !n && !active.has(c.id);
    b.onclick = () => {
      active.has(c.id) ? active.delete(c.id) : active.add(c.id);
      save(); renderFilters(); renderDateNav(); renderArchive();
    };
    box.appendChild(b);
  });

  if (active.size) {
    const clear = el('button', 'chip', '全部');
    clear.onclick = () => { active.clear(); save(); renderFilters(); renderDateNav(); renderArchive(); };
    box.appendChild(clear);

    const list = navDays();
    box.appendChild(el('span', 'filters__note',
      list.length ? `這幾類共 ${list.length} 天` : '這幾類還沒有出過'));
  }
}

function renderFeature() {
  const d = data.feature || data.deepdive, root = document.getElementById('dd');
  root.innerHTML = '';
  if (!d) {
    root.appendChild(el('p', 'dd__meta', '今天沒有通過品質檢查的介紹 —— 寧可不出，也不出空話。'));
    return;
  }

  if (d.is_placeholder) {
    const w = el('div', 'placeholder');
    w.append(el('b', null, '佔位資料'),
             el('span', null, '這篇的文字是手寫的示範，不是系統產出 —— '
                            + 'LLM 額度用盡時，正式流程會直接不出這篇，而不是出空話。'));
    root.appendChild(w);
  }

  root.appendChild(el('div', 'dd__kicker', `今日一件 · ${esc(d.category_label || '')}`));
  root.appendChild(el('h1', 'dd__title', d.title));

  /* 先看見 —— 零術語的入口，排在標題正下方，字級比內文大 */
  if (d.hook) root.appendChild(el('p', 'dd__hook', d.hook));

  const s = d.subject || {};
  const meta = el('p', 'dd__meta');
  meta.innerHTML = [
    s.designer && `設計：<b>${esc(s.designer)}</b>`,
    s.client && `業主：${esc(s.client)}`,
    s.year && `${esc(s.year)}`,
  ].filter(Boolean).join('　·　') || '設計者未確認';
  root.appendChild(meta);

  if (d.image_url) {
    const fig = el('figure', 'figure');
    const img = el('img'); img.alt = ''; img.loading = 'eager';
    // 原圖是把 CMS 尺寸後綴去掉猜出來的，不一定存在 —— 載不到就退回 feed 縮圖
    if (d.image_fallback) img.onerror = () => { img.onerror = null; img.src = d.image_fallback; };
    img.src = d.image_url;
    const cap = el('figcaption');
    cap.appendChild(el('span', null, d.credit || ''));
    const a = el('a', null, `原文：${esc(d.source_name)} ↗`);
    a.href = d.source_url; a.target = '_blank'; a.rel = 'noopener';
    cap.appendChild(a);
    fig.append(img, cap);
    root.appendChild(fig);
  }

  if (d.what_it_is) {
    const s2 = el('section', 'whatis');
    s2.append(el('h3', null, '這是什麼'), el('p', null, d.what_it_is));
    root.appendChild(s2);
  }

  const angles = d.angles || [];
  if (angles.length) {
    root.appendChild(el('h2', 'dd__seph', '從幾個角度看'));
    angles.forEach((a, i) => {
      const sec = el('section', 'angle'); sec.id = `ang-${i}`;
      sec.append(el('h3', 'angle__h', LENS_LABEL[a.lens] || a.lens || ''),
                 el('p', 'angle__b', a.body));
      if (a.so_what) {
        const sw = el('p', 'angle__so');
        sw.append(el('span', 'angle__so__k', '所以呢'), document.createTextNode(a.so_what));
        sec.appendChild(sw);
      }
      root.appendChild(sec);
    });
  } else if (d.axes) {
    /* 舊格式：固定七軸，沒有「所以呢」 */
    root.appendChild(el('h2', 'dd__seph', '七軸拆解'));
    LEGACY_AXES.forEach(([k, label]) => {
      if (!d.axes[k]) return;
      const sec = el('section', 'angle');
      sec.append(el('h3', 'angle__h', label), el('p', 'angle__b', d.axes[k]));
      root.appendChild(sec);
    });
  }

  /* 帶走 —— 兩份，圈外人的那份排前面 */
  const t1 = d.takeaway_everyone, t2 = d.takeaway_designer || d.axes?.takeaway;
  if (t1 || t2) {
    root.appendChild(el('h2', 'dd__seph', '帶走一點東西'));
    if (t1) {
      const b = el('aside', 'takeaway takeaway--all');
      b.append(el('h3', null, '給每一個人'), el('p', null, t1));
      root.appendChild(b);
    }
    if (t2) {
      const b = el('aside', 'takeaway takeaway--pro');
      b.append(el('h3', null, '給做設計的人'), el('p', null, t2));
      root.appendChild(b);
    }
  }

  if (d.glossary?.length) {
    const g = el('details', 'glossary');
    g.appendChild(el('summary', null, `文中的設計詞，一句話說清楚（${d.glossary.length}）`));
    const dl = el('dl');
    d.glossary.forEach(x => {
      dl.appendChild(el('dt', null, x.term));
      dl.appendChild(el('dd', null, x.plain));
    });
    g.appendChild(dl);
    root.appendChild(g);
  }

  if (d.concretes?.length) {
    const c = el('div', 'concretes');
    c.appendChild(el('div', 'concretes__h', '本文引用的具體物'));
    const ul = el('ul');
    d.concretes.forEach(x => ul.appendChild(el('li', null, x)));
    c.appendChild(ul);
    root.appendChild(c);
  }
}

function renderShowcase() {
  const rows = data.showcase || [];
  const box = document.getElementById('showcase');
  box.innerHTML = '';
  document.getElementById('showcase-n').textContent = `${rows.length} 件`;
  rows.forEach(it => {
    const a = el('a', 'card'); a.href = it.url; a.target = '_blank'; a.rel = 'noopener';
    const img = el('img'); img.alt = ''; img.loading = 'lazy';
    if (it.image_fallback) img.onerror = () => { img.onerror = null; img.src = it.image_fallback; };
    img.src = it.image_url;
    a.append(img, el('div', 'card__t', it.title), el('div', 'card__s', it.source_name));
    box.appendChild(a);
  });
}

function renderIndustry() {
  /* 產業動態不套四分類：收購、訴訟、AI 衝擊本來就跨領域，
     硬分只會讓人多想一次（README 三之四）。 */
  const rows = data.industry || [];
  const box = document.getElementById('industry');
  box.innerHTML = '';
  document.getElementById('industry-n').textContent = `${rows.length} 則`;
  rows.forEach(it => {
    const li = el('li'), a = el('a');
    a.href = it.url; a.target = '_blank'; a.rel = 'noopener';
    const t = el('span', 'list__t', it.title);
    const flag = REGION_FLAG[it.region];
    if (flag) t.appendChild(el('span', 'flag', flag));
    a.append(t, el('span', 'list__s', it.source_name));
    li.appendChild(a); box.appendChild(li);
  });
}

/* 介紹過的：同一類的好幾件擺在一起看。日期導覽一次只能給一天，
   要比較「這一類長期長什麼樣」得看得到一整排。

   現在看的那天也留在牆上（標成「現在看的」），不排除掉 ——
   排除的話 chip 上的天數和牆上的天數會差一，而那一格差在哪沒人看得出來。
   留著還多一個好處：一眼知道自己在這一類裡看到哪了。

   主菜沒出來的日子沒有 category，自然不會進來 —— 那天沒有東西可看。

   卡片是站內的日子，用 <a href="?d="> 才複製得走、也開得了新分頁，
   但點擊走 show()，不重新載整頁。 */
function renderArchive() {
  const box = document.getElementById('archive');
  const rows = days.filter(d => d.category && (!active.size || active.has(d.category)))
                   .reverse();                       // 新的排前面
  box.innerHTML = '';

  const cats = active.size ? [...active].map(id => CAT_LABEL[id] || id).join('、') : '';
  document.getElementById('archive-h').textContent = `介紹過的${cats}`;
  document.getElementById('archive-n').textContent = rows.length ? `${rows.length} 天` : '';

  if (!rows.length) {
    box.appendChild(el('div', 'archive__empty', active.size
      ? '這幾類還沒有出過 —— 每天只出一件，四類輪著來，累積需要時間。'
      : '還沒有介紹過任何一件。'));
    return;
  }

  rows.forEach(d => {
    const now = d.date === data.date;
    const a = el('a', now ? 'card card--day card--now' : 'card card--day');
    a.href = `?d=${d.date}`;
    a.onclick = e => { e.preventDefault(); show(d.date, true); };
    if (now) a.setAttribute('aria-current', 'page');
    if (d.image_url) {
      const img = el('img'); img.alt = ''; img.loading = 'lazy';
      if (d.image_fallback) img.onerror = () => { img.onerror = null; img.src = d.image_fallback; };
      img.src = d.image_url;
      a.appendChild(img);
    }
    a.appendChild(el('div', 'card__t', d.title || d.date));
    const s = el('div', 'card__s');
    s.append(el('b', null, now ? '現在看的' : (CAT_LABEL[d.category] || '')),
             el('span', null, d.date));
    a.appendChild(s);
    box.appendChild(a);
  });
}

/* 有哪幾天可以看、那天是哪一類：[{date, category, title, image_url…}]。
   出刊是有斷層的（抓取失敗、或那天沒跑），所以上一天／下一天不能用日期加減
   —— 減一天會直接撞 404。照 index.json 列出的實際檔案走。 */
let days = [];

function fmtDate(iso) {
  const dt = new Date(iso + 'T00:00:00+08:00');
  return `${iso}（${'日一二三四五六'[dt.getDay()]}）`;
}

async function show(date, push) {
  const res = await fetch(`data/${date}.json`);
  if (!res.ok) return;                       // 檔案不在就原地不動，不要把畫面清空
  data = await res.json();

  renderDateNav();
  renderFilters(); renderFeature(); renderShowcase(); renderIndustry(); renderArchive();
  window.scrollTo(0, 0);

  /* 每一天要有自己的網址，這樣分享得出去、上一頁也回得來 */
  const url = `?d=${data.date}`;
  if (push) history.pushState({ d: data.date }, '', url);
  else history.replaceState({ d: data.date }, '', url);
}

function renderDateNav() {
  document.getElementById('date').textContent = fmtDate(data.date);
  document.getElementById('prev').disabled = !stepTarget(-1);
  document.getElementById('next').disabled = !stepTarget(1);
}

/* 往前／往後的下一天是誰。用「比目前大／小的第一個」而不是 index±1：
   選了分類之後，或是有人直接開 ?d= 一個不在名單裡的日子，
   目前這天可能根本不在可翻的名單裡，indexOf 會是 -1、按鈕就死了。 */
function stepTarget(delta) {
  const list = navDays();
  const here = data ? data.date : '';
  const side = delta < 0 ? list.filter(d => d < here) : list.filter(d => d > here);
  if (!side.length) return null;
  return delta < 0 ? side[side.length - 1] : side[0];
}

function step(delta) {
  const t = stepTarget(delta);
  if (t) show(t, true);
}

async function boot() {
  const latest = await fetch('data/latest.json').then(r => r.json());

  /* index.json 是後來才加的，舊的部署上可能還沒有 ——
     沒有就退回「只有最新這天」，按鈕自己會是 disabled，不會壞掉。
     days 也是後來才加的（分類導覽與過往牆要用）；只有 dates 的舊索引就當作
     沒有分類，chip 會全部是 disabled、牆是空的，日期導覽照樣能翻。 */
  const idx = await fetch('data/index.json')
    .then(r => r.ok ? r.json() : {})
    .catch(() => ({}));
  days = idx.days || (idx.dates || []).map(d => ({ date: d, category: null }));
  if (!days.some(d => d.date === latest.date)) days.push({ date: latest.date, category: null });
  days.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);

  document.getElementById('prev').onclick = () => step(-1);
  document.getElementById('next').onclick = () => step(1);
  addEventListener('popstate', e => {
    const d = e.state?.d || new URLSearchParams(location.search).get('d') || latest.date;
    show(d, false);
  });

  const q = new URLSearchParams(location.search).get('d');
  await show(q && days.some(d => d.date === q) ? q : latest.date, false);
}
boot();
