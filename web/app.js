/* 解析度 Resolution —— 前端
   資料來源：web/data/{date}.json（本地與 Firestore 之後由 config.json 切換）*/

const CATS = [
  { id: 'visual_brand',   label: '視覺與品牌' },
  { id: 'interface_ux',   label: '介面與體驗' },
  { id: 'product_object', label: '產品與物件' },
  { id: 'space_env',      label: '空間與環境' },
];

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

/* 篩選只作用在作品流與產業動態 —— 今日這一件永遠顯示。
   每天只有一件，被篩掉主版位就空了；分類均衡靠輪播保證，不靠篩選。 */
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

function renderFilters() {
  const box = document.getElementById('filters');
  box.innerHTML = '';
  CATS.forEach(c => {
    const b = el('button', 'chip', c.label);
    b.setAttribute('aria-pressed', active.has(c.id));
    b.onclick = () => {
      active.has(c.id) ? active.delete(c.id) : active.add(c.id);
      save(); renderFilters(); renderShowcase(); renderIndustry();
    };
    box.appendChild(b);
  });
  if (active.size) {
    const clear = el('button', 'chip', '全部');
    clear.onclick = () => { active.clear(); save(); renderFilters(); renderShowcase(); renderIndustry(); };
    box.appendChild(clear);
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

const pass = it => !active.size || active.has(it.category);

function renderShowcase() {
  const rows = (data.showcase || []).filter(pass);
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
  const rows = (data.industry || []).filter(pass);
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

async function boot() {
  const latest = await fetch('data/latest.json').then(r => r.json());
  const q = new URLSearchParams(location.search).get('d');
  data = await fetch(`data/${q || latest.date}.json`).then(r => r.json());

  const dt = new Date(data.date + 'T00:00:00+08:00');
  const wd = '日一二三四五六'[dt.getDay()];
  document.getElementById('date').textContent = `${data.date}（${wd}）`;
  document.getElementById('mode').textContent = '';
  document.getElementById('next').disabled = true;

  renderFilters(); renderFeature(); renderShowcase(); renderIndustry();
}
boot();
