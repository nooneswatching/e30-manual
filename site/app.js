/* E30 Manual: static single-page app. Data comes from site/data/ (built by tools/build.py). */
(() => {
  'use strict';

  const $app = document.getElementById('app');
  const $q = document.getElementById('q');
  const DATA = 'data/';
  const state = { manuals: null, parts: null, search: null, searchLoading: null, partsSearch: null };

  // ---------------------------------------------------------------- helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const h = (strings, ...vals) => strings.reduce((out, s, i) => out + s + (i < vals.length ? (vals[i] instanceof Raw ? vals[i].s : esc(vals[i])) : ''), '');
  class Raw { constructor(s) { this.s = s; } }
  const raw = s => new Raw(s);
  const join = (arr, fn) => raw(arr.map(fn).join(''));
  const fetchJSON = async (path) => {
    const r = await fetch(DATA + path, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  };
  const normPart = s => String(s || '').replace(/[\s.\-]/g, '').toUpperCase();
  const fmtPart = n => /^\d{11}$/.test(n) ? `${n.slice(0, 2)} ${n.slice(2, 4)} ${n.slice(4, 5)} ${n.slice(5, 8)} ${n.slice(8)}` : n;
  const looksLikePart = s => /^\d{11}$/.test(normPart(s));
  const PART_IN_TEXT = /\b\d{2}\s?\d{2}\s?\d\s?\d{3}\s?\d{3}\b/g;
  const tokenize = s => (s.toLowerCase().match(/[a-z0-9äöüß]+/g) || []);
  const setTitle = t => { document.title = t ? `${t} · E30 Manual` : 'E30 Manual'; };
  const nav = () => {
    const page = location.hash.startsWith('#/parts') ? 'parts' : 'home';
    document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('active', a.dataset.nav === page));
  };

  function parseRoute() {
    const hash = location.hash.replace(/^#\/?/, '');
    const [path, qs] = hash.split('?');
    const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
    const params = Object.fromEntries(new URLSearchParams(qs || ''));
    return { parts, params };
  }

  // Highlight query terms inside a text snippet.
  function highlight(text, terms) {
    if (!terms.length) return esc(text);
    const re = new RegExp('(' + terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
    return esc(text).replace(re, '<mark>$1</mark>');
  }
  function snippet(text, terms, width = 220) {
    const lower = text.toLowerCase();
    let pos = -1;
    for (const t of terms) { const i = lower.indexOf(t.toLowerCase()); if (i >= 0 && (pos < 0 || i < pos)) pos = i; }
    if (pos < 0) return highlight(text.slice(0, width), terms) + (text.length > width ? '…' : '');
    const start = Math.max(0, pos - width / 3);
    const end = Math.min(text.length, start + width);
    return (start > 0 ? '…' : '') + highlight(text.slice(start, end), terms) + (end < text.length ? '…' : '');
  }

  // ---------------------------------------------------------------- data loading
  async function loadManuals() {
    if (state.manuals) return state.manuals;
    try { state.manuals = (await fetchJSON('manuals.json')).manuals || []; }
    catch (e) { console.warn(e); state.manuals = []; }
    return state.manuals;
  }
  async function loadParts() {
    if (state.parts) return state.parts;
    try { state.parts = await fetchJSON('parts/index.json'); }
    catch (e) { console.warn(e); state.parts = { groups: [], diagrams: {}, parts: {} }; }
    return state.parts;
  }
  const manualById = id => (state.manuals || []).find(m => m.id === id);

  // Full-text index over all manual pages, built once in the browser.
  async function loadSearch(onProgress) {
    if (state.search) return state.search;
    if (state.searchLoading) return state.searchLoading;
    state.searchLoading = (async () => {
      const manuals = await loadManuals();
      const ms = new MiniSearch({
        fields: ['t', 's', 'pn'],
        storeFields: ['m', 'p', 's', 't'],
        tokenize: s => tokenize(s),
        processTerm: t => t.length > 1 ? t : null,
        searchOptions: { boost: { s: 3, pn: 5 }, prefix: term => term.length >= 3, fuzzy: term => term.length >= 5 ? 0.15 : 0, combineWith: 'AND' },
      });
      let total = 0, done = 0;
      const corpora = [];
      for (const m of manuals) {
        try { const docs = await fetchJSON(m.search); corpora.push([m, docs]); total += docs.length; }
        catch (e) { console.warn('no search data for', m.id, e); }
      }
      for (const [m, docs] of corpora) {
        const prepared = docs.map(d => ({ id: d.id, m: m.id, p: d.p, s: d.s || '', t: d.t,
          pn: (d.t.match(PART_IN_TEXT) || []).map(normPart).join(' ') }));
        await ms.addAllAsync(prepared, { chunkSize: 200 });
        done += docs.length;
        onProgress && onProgress(done, total);
      }
      state.search = ms;
      return ms;
    })();
    return state.searchLoading;
  }

  function partsSearchIndex(parts) {
    if (state.partsSearch) return state.partsSearch;
    const ms = new MiniSearch({ fields: ['num', 'desc', 'title', 'dia'], storeFields: ['kind', 'key', 'desc', 'title'],
      tokenize: s => tokenize(s), searchOptions: { prefix: true, fuzzy: 0.15, boost: { num: 4, title: 2 } } });
    const docs = [];
    for (const p of Object.values(parts.parts)) docs.push({ id: 'p:' + p.part, kind: 'part', key: p.part, num: p.part, desc: p.desc, title: '', dia: '' });
    for (const d of Object.values(parts.diagrams)) docs.push({ id: 'd:' + d.id, kind: 'diagram', key: d.id, num: '', desc: d.notes || '', title: d.title, dia: d.id.replace(/_/g, ' ') });
    ms.addAll(docs);
    state.partsSearch = ms;
    return ms;
  }

  // ---------------------------------------------------------------- views
  function render(html, { wide = false } = {}) {
    $app.innerHTML = html;
    $app.classList.toggle('wide', wide);
    window.scrollTo(0, 0);
    nav();
  }

  async function viewHome() {
    const manuals = await loadManuals();
    setTitle('');
    const empty = !manuals.length;
    render(h`
      <h1>BMW E30 manuals</h1>
      ${empty ? raw(h`<div class="notice">
          <strong>No manuals built yet.</strong> Put scanned PDFs in <code>manuals/</code> and run
          <code>python tools/build.py</code> (or push to GitHub and let the workflow build them). See <code>manuals/README.md</code>.
        </div>`) : ''}
      <div class="grid">
        ${join(manuals, m => h`<a class="card" href="#/m/${m.id}">
            <h3>${m.title}</h3>
            <div class="meta">${m.pages} pages · ${m.toc.length} sections · ${m.type}</div>
            ${m.description ? raw(h`<p class="small">${m.description}</p>`) : ''}
          </a>`)}
        <a class="card" href="#/parts"><h3>Parts catalogue</h3><div class="meta">Exploded diagrams, part numbers, reverse lookup</div></a>
      </div>
      <h2>Search tips</h2>
      <ul class="small muted">
        <li>Search runs across every page of every manual. Words are matched by prefix, so <code>torq</code> finds "torque".</li>
        <li>Type a part number with or without spaces (<code>11 42 1 730 389</code>) to find it in both the parts catalogue and the manuals.</li>
        <li>Repair group numbers work too: <code>34 11</code> finds front brake procedures.</li>
      </ul>`);
  }

  async function viewManual(id) {
    await loadManuals();
    const m = manualById(id);
    if (!m) return render(h`<p>Unknown manual <code>${id}</code>. <a href="#/">Back</a></p>`);
    setTitle(m.title);
    const groups = m.groups || [];
    const firstPage = m.built_pages?.[0] || 1;
    render(h`
      <div class="breadcrumb"><a href="#/">Manuals</a> › ${m.title}</div>
      <h1>${m.title}</h1>
      <div class="row small muted" style="margin-bottom:1rem">
        <span>${m.pages} pages</span><span>·</span><span>Contents: ${m.toc_source}</span><span>·</span>
        <a class="btn" href="#/m/${m.id}/p/${firstPage}">Open at page ${firstPage}</a>
        <form class="row" id="jump"><input type="number" min="1" max="${m.pages}" placeholder="page" class="find" style="width:6rem"><button class="btn">Go</button></form>
      </div>
      <div class="toc-layout">
        <div class="panel toc-groups">
          <strong>Repair groups</strong>
          ${join(groups, g => h`<a href="#/m/${m.id}#g-${g.id}" data-jump="g-${g.id}">${g.id === 'other' ? '' : g.id + ' '}${g.name} <span class="muted small">(${g.sections.length})</span></a>`)}
          <hr style="border:0;border-top:1px solid var(--line)">
          <a href="#/m/${m.id}" data-jump="pages">All pages</a>
        </div>
        <div>
          ${m.toc.length ? '' : raw('<p class="muted">No headings were detected in this manual. Add a <code>toc</code> to its sidecar JSON to provide one.</p>')}
          ${join(groups, g => h`<div class="panel" id="g-${g.id}" style="margin-bottom:1rem">
              <h2 style="margin-top:0">${g.id === 'other' ? '' : g.id + ' · '}${g.name}
                ${g.id !== 'other' ? raw(h` <a class="small" href="#/parts/g/${g.id}">parts diagrams ›</a>`) : ''}</h2>
              <ul class="toc-list">${join(g.sections, s => h`<li class="l${s.level}"><a href="#/m/${m.id}/p/${s.page}">${s.title}</a><span class="pg">p. ${s.page}</span></li>`)}</ul>
            </div>`)}
          <div class="panel" id="pages"><h2 style="margin-top:0">All pages</h2>
            <div class="pagegrid">${join(m.built_pages || [], p => h`<a href="#/m/${m.id}/p/${p}"><img loading="lazy" src="${DATA}manuals/${m.id}/img/${p}.webp" alt=""><div>${p}</div></a>`)}</div>
          </div>
        </div>
      </div>`);
    $app.querySelectorAll('[data-jump]').forEach(a => a.addEventListener('click', e => {
      e.preventDefault(); document.getElementById(a.dataset.jump)?.scrollIntoView({ behavior: 'smooth' });
    }));
    $app.querySelector('#jump').addEventListener('submit', e => {
      e.preventDefault(); const n = +e.target.querySelector('input').value; if (n) location.hash = `#/m/${m.id}/p/${n}`;
    });
  }

  async function viewPage(id, n, params) {
    await loadManuals();
    const m = manualById(id);
    if (!m) return render(h`<p>Unknown manual. <a href="#/">Back</a></p>`);
    n = Math.max(1, Math.min(m.pages, +n || 1));
    let page = null;
    try { page = await fetchJSON(`manuals/${m.id}/pages/${n}.json`); } catch (e) { /* not built */ }
    const q = params.q || '';
    const terms = tokenize(q);
    const section = [...m.toc].reverse().find(s => s.page <= n);
    const showText = params.text !== '0';
    setTitle(`${m.title} p.${n}`);
    const printed = m.page_offset ? ` (printed p. ${n - m.page_offset})` : '';
    render(h`
      <div class="breadcrumb"><a href="#/">Manuals</a> › <a href="#/m/${m.id}">${m.title}</a>${section ? raw(h` › ${section.title}`) : ''}</div>
      <div class="viewer-bar">
        <a class="btn" href="#/m/${m.id}/p/${n - 1}${q ? '?q=' + encodeURIComponent(q) : ''}" ${n <= 1 ? 'style="visibility:hidden"' : ''}>‹ Prev</a>
        <form id="pf" class="row"><label>Page <input type="number" min="1" max="${m.pages}" value="${n}"></label> <span class="muted small">of ${m.pages}${printed}</span></form>
        <a class="btn" href="#/m/${m.id}/p/${n + 1}${q ? '?q=' + encodeURIComponent(q) : ''}" ${n >= m.pages ? 'style="visibility:hidden"' : ''}>Next ›</a>
        <input class="find" id="find" type="search" placeholder="Find on page…" value="${q}">
        <select id="zoom" class="btn"><option value="">Fit width</option><option value="150">150%</option><option value="200">200%</option><option value="300">300%</option></select>
        <button class="btn" id="toggletext">${showText ? 'Hide' : 'Show'} text</button>
        <a class="btn" href="${DATA}manuals/${m.id}/img/${n}.webp" target="_blank" rel="noopener">Image ↗</a>
        <span class="muted small">Use <span class="kbd">←</span> <span class="kbd">→</span> to turn pages</span>
      </div>
      <div class="viewer ${showText ? 'with-text' : ''}">
        <div class="scan" id="scan"><div class="stage">
          ${page ? raw(h`<img id="pageimg" src="${DATA}manuals/${m.id}/img/${page.img || n + '.webp'}" alt="Page ${n}" width="${page.w}" height="${page.h}"><div id="hits"></div>`)
                 : raw(h`<p style="padding:2rem" class="muted">Page ${n} has not been built. Run <code>python tools/build.py</code>.</p>`)}
        </div></div>
        ${showText ? raw(h`<div class="panel"><div class="row" style="justify-content:space-between"><strong>OCR text</strong>
            <span class="muted small">${page?.source || ''}${page?.text ? '' : ' · empty'}</span></div>
            <pre class="ocrtext" id="ocrtext"></pre></div>`) : ''}
      </div>`, { wide: true });

    const $find = document.getElementById('find');
    const $hits = document.getElementById('hits');
    const $text = document.getElementById('ocrtext');
    const scan = document.getElementById('scan');
    const apply = () => {
      const t = tokenize($find.value);
      if ($text) $text.innerHTML = page ? highlight(page.text || '', t) : '';
      if (!$hits || !page) return;
      const html = [];
      for (const [w, x0, y0, x1, y1] of page.words || []) {
        const lw = w.toLowerCase().replace(/[^a-z0-9äöüß]/g, '');
        if (!lw) continue;
        const strong = t.some(term => lw === term);
        if (strong || t.some(term => term.length >= 3 && lw.startsWith(term))) {
          html.push(`<div class="hit ${strong ? 'strong' : ''}" style="left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%"></div>`);
        }
      }
      $hits.innerHTML = html.join('');
      const first = $hits.firstElementChild;
      if (first && t.length) setTimeout(() => first.scrollIntoView({ block: 'center', behavior: 'smooth' }), 50);
    };
    const img = document.getElementById('pageimg');
    if (img && !img.complete) img.addEventListener('load', apply); else apply();
    $find.addEventListener('input', apply);
    document.getElementById('zoom').addEventListener('change', e => { scan.className = 'scan' + (e.target.value ? ' zoom-' + e.target.value : ''); });
    document.getElementById('toggletext').addEventListener('click', () => {
      const p = new URLSearchParams(params); p.set('text', showText ? '0' : '1'); if ($find.value) p.set('q', $find.value);
      location.hash = `#/m/${m.id}/p/${n}?${p}`;
    });
    document.getElementById('pf').addEventListener('submit', e => { e.preventDefault(); const v = +e.target.querySelector('input').value; if (v) location.hash = `#/m/${m.id}/p/${v}`; });
    state.keyHandler = e => {
      if (e.target.matches('input,textarea,select')) return;
      const qq = $find.value ? '?q=' + encodeURIComponent($find.value) : '';
      if (e.key === 'ArrowLeft' && n > 1) location.hash = `#/m/${m.id}/p/${n - 1}${qq}`;
      if (e.key === 'ArrowRight' && n < m.pages) location.hash = `#/m/${m.id}/p/${n + 1}${qq}`;
    };
  }

  async function viewSearch(query, params) {
    const manuals = await loadManuals();
    setTitle(`Search: ${query}`);
    $q.value = query;
    const filter = params.m || '';
    render(h`<h1>Search</h1><p class="muted" id="status">Loading index…</p><div class="progress" id="prog"><div style="width:0"></div></div><div id="partsres"></div><div id="results"></div>`);
    const $status = document.getElementById('status'), $prog = document.getElementById('prog');

    // Part numbers: show catalogue hits first.
    const parts = await loadParts();
    const pnorm = normPart(query);
    const partHits = Object.values(parts.parts || {}).filter(p => /^\d{4,}$/.test(pnorm) && p.part.startsWith(pnorm));
    if (partHits.length) {
      document.getElementById('partsres').innerHTML = h`<div class="panel" style="margin-bottom:1rem"><strong>Parts catalogue</strong>
        ${join(partHits.slice(0, 10), p => h`<div class="result"><a href="#/parts/p/${p.part}" class="mono">${p.display}</a> ${p.desc}
          <div class="where">${p.uses.length} diagram${p.uses.length === 1 ? '' : 's'}: ${join(p.uses, u => h`<a href="#/parts/d/${u.diagram}?n=${u.n ?? ''}">${parts.diagrams[u.diagram]?.title || u.diagram}</a> `)}</div></div>`)}</div>`;
    }

    if (!manuals.length) { $status.textContent = 'No manuals have been built yet.'; $prog.remove(); return; }
    let ms;
    try { ms = await loadSearch((d, t) => { $status.textContent = `Indexing ${d} / ${t} pages…`; $prog.firstElementChild.style.width = (100 * d / t) + '%'; }); }
    catch (e) { $status.textContent = 'Search index failed to load: ' + e.message; return; }
    $prog.remove();
    if (!query.trim()) { $status.textContent = 'Type something to search.'; return; }

    // Part-number-aware query: an 11-digit number is searched as a single token in the pn field.
    const results = looksLikePart(query) ? ms.search(pnorm, { fields: ['pn'], prefix: false, fuzzy: false }) : ms.search(query);
    const filtered = filter ? results.filter(r => r.m === filter) : results;
    const terms = looksLikePart(query) ? [fmtPart(pnorm), pnorm] : tokenize(query);
    const counts = {};
    for (const r of results) counts[r.m] = (counts[r.m] || 0) + 1;
    $status.innerHTML = h`${filtered.length} page${filtered.length === 1 ? '' : 's'} match <strong>${query}</strong>`;
    const chips = manuals.filter(m => counts[m.id]).map(m => h`<a class="chip ${filter === m.id ? 'active' : ''}" href="#/search/${encodeURIComponent(query)}${filter === m.id ? '' : '?m=' + m.id}">${m.title} (${counts[m.id]})</a>`).join('');
    document.getElementById('results').innerHTML = `<div class="chips">${chips}</div>` +
      filtered.slice(0, 200).map(r => {
        const m = manualById(r.m);
        return h`<div class="result">
          <a href="#/m/${r.m}/p/${r.p}?q=${encodeURIComponent(query)}"><strong>${m?.title || r.m}</strong> · page ${r.p}</a>
          ${r.s ? raw(h`<div class="where">${r.s}</div>`) : ''}
          <p class="snip">${raw(snippet(r.t, terms))}</p></div>`;
      }).join('') + (filtered.length > 200 ? '<p class="muted">Showing the first 200 results.</p>' : '');
  }

  // ---------------------------------------------------------------- parts catalogue
  const sampleNotice = parts => parts.sample ? raw(h`<div class="notice warn"><strong>Sample data.</strong> ${parts.vehicle?.note || 'Replace parts/ with your own diagrams.'}</div>`) : '';

  async function viewParts(params) {
    const parts = await loadParts();
    setTitle('Parts');
    const q = params.q || '';
    render(h`
      <h1>Parts catalogue ${parts.vehicle?.name ? raw(h`<span class="muted" style="font-weight:400;font-size:1rem">${parts.vehicle.name}</span>`) : ''}</h1>
      ${sampleNotice(parts)}
      <form id="psearch" class="row" style="margin-bottom:1rem"><input class="find" style="width:22rem;max-width:100%" type="search" placeholder="Part number or description…" value="${q}"><button class="btn primary">Find part</button></form>
      <div id="pres"></div>
      ${parts.groups.length ? '' : raw('<p class="muted">No diagrams yet. See <code>parts/README.md</code> for how to add them.</p>')}
      <div class="grid">${join(parts.groups, g => h`<a class="card" href="#/parts/g/${g.id}"><h3>${g.id} · ${g.name}</h3><div class="meta">${g.diagrams.length} diagram${g.diagrams.length === 1 ? '' : 's'}</div>
        <div class="small">${g.diagrams.slice(0, 4).map(d => parts.diagrams[d]?.title).filter(Boolean).join(' · ')}${g.diagrams.length > 4 ? ' …' : ''}</div></a>`)}</div>`);
    const form = document.getElementById('psearch');
    const show = () => {
      const v = form.querySelector('input').value.trim();
      const $r = document.getElementById('pres');
      if (!v) { $r.innerHTML = ''; return; }
      const nv = normPart(v);
      let hits;
      if (/^\d{4,}$/.test(nv)) hits = Object.values(parts.parts).filter(p => p.part.startsWith(nv)).map(p => ({ kind: 'part', key: p.part, desc: p.desc }));
      else hits = partsSearchIndex(parts).search(v).map(r => ({ kind: r.kind, key: r.key, desc: r.desc, title: r.title }));
      $r.innerHTML = h`<div class="panel" style="margin-bottom:1rem">${hits.length ? '' : raw('<span class="muted">No matches.</span>')}
        ${join(hits.slice(0, 30), x => x.kind === 'part'
          ? h`<div class="result"><a class="mono" href="#/parts/p/${x.key}">${fmtPart(x.key)}</a> ${x.desc} <span class="where">· ${parts.parts[x.key].uses.length} diagram(s)</span></div>`
          : h`<div class="result"><a href="#/parts/d/${x.key}">${x.title}</a> <span class="where">diagram ${x.key}</span></div>`)}
        ${/^\d{4,}$/.test(nv) ? raw(h`<div class="small" style="margin-top:.5rem"><a href="#/search/${encodeURIComponent(v)}">Search the manuals for "${v}" ›</a></div>`) : ''}</div>`;
    };
    form.addEventListener('submit', e => { e.preventDefault(); show(); });
    form.querySelector('input').addEventListener('input', show);
    if (q) show();
  }

  async function viewPartsGroup(gid) {
    const parts = await loadParts();
    const g = parts.groups.find(x => x.id === gid);
    if (!g) return render(h`<p>Unknown group. <a href="#/parts">Back</a></p>`);
    setTitle(`${g.id} ${g.name}`);
    const manualsWithGroup = (await loadManuals()).filter(m => m.groups.some(x => x.id === gid));
    render(h`<div class="breadcrumb"><a href="#/parts">Parts</a> › ${g.id} ${g.name}</div>
      <h1>${g.id} · ${g.name}</h1>
      ${manualsWithGroup.length ? raw(h`<p class="small">Workshop procedures: ${join(manualsWithGroup, m => h`<a href="#/m/${m.id}#g-${gid}">${m.title}</a> `)}</p>`) : ''}
      <div class="grid">${join(g.diagrams, did => { const d = parts.diagrams[did]; return h`<a class="card" href="#/parts/d/${did}">
        ${d.image ? raw(h`<img src="${DATA}parts/${d.image}" alt="" style="width:100%;aspect-ratio:1.4;object-fit:contain;background:#fff;border-radius:6px;margin-bottom:.5rem">`) : ''}
        <h3>${d.title}</h3><div class="meta">${did} · ${d.items.length} items</div></a>`; })}</div>`);
  }

  async function viewDiagram(did, params) {
    const parts = await loadParts();
    const d = parts.diagrams[did];
    if (!d) return render(h`<p>Unknown diagram <code>${did}</code>. <a href="#/parts">Back</a></p>`);
    const g = parts.groups.find(x => x.id === d.group);
    setTitle(d.title);
    const editing = params.edit === '1';
    const callouts = d.callouts.map(c => ({ ...c }));
    render(h`<div class="breadcrumb"><a href="#/parts">Parts</a> › <a href="#/parts/g/${d.group}">${d.group} ${g?.name || ''}</a> › ${d.title}</div>
      <div class="row" style="justify-content:space-between"><h1 style="margin:0">${d.title} <span class="muted small mono">${d.id}</span></h1>
        <span class="row"><a class="btn" href="#/m" id="manual-link" hidden>Procedures in manuals</a>
        <a class="btn ${editing ? 'primary' : ''}" href="#/parts/d/${d.id}${editing ? '' : '?edit=1'}">${editing ? 'Done editing' : 'Edit hotspots'}</a></span></div>
      ${d.notes ? raw(h`<p class="muted small">${d.notes}</p>`) : ''}
      ${sampleNotice(parts)}
      <div class="diagram-layout">
        <div>
          <div class="diagram ${editing ? 'editing' : ''}" id="dia">
            ${d.image ? raw(h`<img src="${DATA}parts/${d.image}" alt="${d.title}" id="diaimg">`) : raw('<p style="padding:2rem" class="muted">No image for this diagram.</p>')}
            <div id="hots"></div>
          </div>
          ${editing ? raw(h`<div class="panel editor" style="margin-top:1rem">
            <strong>Hotspot editor.</strong> <span class="small muted">Select a row in the table, then click on the drawing to place its callout. Drag a callout to move it, double-click it to delete it. When done, copy the JSON into <code>parts/diagrams/${d.id}.json</code> and rebuild.</span>
            <div class="row" style="margin:.5rem 0"><button class="btn primary" id="copyjson">Copy diagram JSON</button><button class="btn" id="dljson">Download JSON</button><span id="copied" class="small muted"></span></div>
            <textarea id="jsonout" readonly></textarea></div>`) : ''}
        </div>
        <div class="panel sticky">
          <table class="parts-table"><thead><tr><th>#</th><th>Part number</th><th>Description</th><th>Qty</th></tr></thead>
          <tbody>${join(d.items, it => h`<tr class="clickable" data-n="${it.n ?? ''}">
            <td class="n">${it.n ?? ''}</td>
            <td class="pn">${it.part ? raw(h`<a class="mono" href="#/parts/p/${it.part}">${it.part_display}</a>`) : raw('<span class="muted">—</span>')}</td>
            <td>${it.desc || ''}${it.notes ? raw(h`<div class="small muted">${it.notes}</div>`) : ''}${it.models ? raw(h`<div class="small muted">${it.models.join(', ')}</div>`) : ''}</td>
            <td>${it.qty ?? ''}</td></tr>`)}</tbody></table>
          ${d.source ? raw(h`<p class="small muted">Source: ${d.source}</p>`) : ''}
        </div>
      </div>`, { wide: true });

    // Link to the workshop manual group with the same number.
    const manuals = await loadManuals();
    const mm = manuals.find(m => m.groups.some(x => x.id === d.group));
    const ml = document.getElementById('manual-link');
    if (mm) { ml.hidden = false; ml.href = `#/m/${mm.id}#g-${d.group}`; }

    const $hots = document.getElementById('hots'), $dia = document.getElementById('dia');
    const rows = [...$app.querySelectorAll('tr[data-n]')];
    let selected = params.n ? String(params.n) : null;
    const setHL = n => {
      selected = n == null ? null : String(n);
      rows.forEach(r => r.classList.toggle('hl', r.dataset.n === selected));
      $hots.querySelectorAll('.hot').forEach(x => x.classList.toggle('hl', x.dataset.n === selected));
    };
    const drawHots = () => {
      $hots.innerHTML = callouts.map(c => h`<div class="hot" data-n="${c.n}" style="left:${c.x * 100}%;top:${c.y * 100}%" title="Item ${c.n}">${c.n}</div>`).join('');
      $hots.querySelectorAll('.hot').forEach(el => {
        el.addEventListener('click', e => { e.stopPropagation(); setHL(el.dataset.n); rows.find(r => r.dataset.n === el.dataset.n)?.scrollIntoView({ block: 'nearest' }); });
        if (editing) {
          el.addEventListener('dblclick', e => { e.stopPropagation(); const i = callouts.findIndex(c => String(c.n) === el.dataset.n); if (i >= 0) callouts.splice(i, 1); drawHots(); updateJSON(); });
          el.addEventListener('pointerdown', e => {
            e.preventDefault(); const c = callouts.find(x => String(x.n) === el.dataset.n); const rect = $dia.getBoundingClientRect();
            const move = ev => { c.x = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width)); c.y = Math.min(1, Math.max(0, (ev.clientY - rect.top) / rect.height)); el.style.left = c.x * 100 + '%'; el.style.top = c.y * 100 + '%'; };
            const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); c.x = +c.x.toFixed(4); c.y = +c.y.toFixed(4); updateJSON(); };
            window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
          });
        }
      });
      setHL(selected);
    };
    const updateJSON = () => {
      const ta = document.getElementById('jsonout'); if (!ta) return;
      const out = { ...d, callouts: callouts.map(c => ({ n: c.n, x: c.x, y: c.y })), items: d.items.map(({ part_display, ...it }) => ({ ...it, part: part_display || it.part })) };
      out.image = (d.image || '').replace(/^images\//, '');
      ta.value = JSON.stringify(out, null, 1);
    };
    drawHots();
    rows.forEach(r => r.addEventListener('click', () => setHL(r.dataset.n === selected ? null : r.dataset.n)));
    if (editing) {
      updateJSON();
      $dia.addEventListener('click', e => {
        if (e.target.classList.contains('hot')) return;
        const rect = $dia.getBoundingClientRect();
        const x = +((e.clientX - rect.left) / rect.width).toFixed(4), y = +((e.clientY - rect.top) / rect.height).toFixed(4);
        let n = selected != null && selected !== '' ? (isNaN(+selected) ? selected : +selected) : (Math.max(0, ...callouts.map(c => +c.n || 0)) + 1);
        const existing = callouts.find(c => String(c.n) === String(n));
        if (existing) { existing.x = x; existing.y = y; } else callouts.push({ n, x, y });
        drawHots(); updateJSON();
      });
      document.getElementById('copyjson').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(document.getElementById('jsonout').value); document.getElementById('copied').textContent = 'Copied.'; }
        catch { document.getElementById('jsonout').select(); document.getElementById('copied').textContent = 'Select and copy the text above.'; }
      });
      document.getElementById('dljson').addEventListener('click', () => {
        const blob = new Blob([document.getElementById('jsonout').value], { type: 'application/json' });
        const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${d.id}.json` }); a.click();
      });
    }
  }

  async function viewPart(num) {
    const parts = await loadParts();
    const key = normPart(num);
    const p = parts.parts[key];
    setTitle(fmtPart(key));
    if (!p) return render(h`<div class="breadcrumb"><a href="#/parts">Parts</a> › ${fmtPart(key)}</div><h1 class="mono">${fmtPart(key)}</h1>
      <p>This part number is not in the catalogue. <a href="#/search/${encodeURIComponent(fmtPart(key))}">Search the manuals for it ›</a></p>`);
    render(h`<div class="breadcrumb"><a href="#/parts">Parts</a> › ${p.display}</div>
      <h1><span class="mono">${p.display}</span></h1><p style="font-size:1.1rem">${p.desc}</p>
      <div class="panel"><h2 style="margin-top:0">Used in ${p.uses.length} diagram${p.uses.length === 1 ? '' : 's'}</h2>
        <table><thead><tr><th>Diagram</th><th>Callout</th><th>Qty</th><th>Notes</th></tr></thead><tbody>
        ${join(p.uses, u => h`<tr><td><a href="#/parts/d/${u.diagram}?n=${u.n ?? ''}">${parts.diagrams[u.diagram]?.title || u.diagram}</a> <span class="muted small">${u.group} · ${u.diagram}</span></td><td>${u.n ?? ''}</td><td>${u.qty ?? ''}</td><td>${u.notes || ''}</td></tr>`)}
        </tbody></table></div>
      <p style="margin-top:1rem"><a class="btn" href="#/search/${encodeURIComponent(p.display)}">Find "${p.display}" in the manuals</a>
         <a class="btn" href="https://www.realoem.com/bmw/enUS/partxref?q=${encodeURIComponent(p.part)}" target="_blank" rel="noopener">Cross-reference on RealOEM ↗</a></p>`);
  }

  // ---------------------------------------------------------------- router
  async function route() {
    const { parts, params } = parseRoute();
    state.keyHandler = null;
    try {
      if (!parts.length) return await viewHome();
      if (parts[0] === 'search') return await viewSearch(parts[1] || '', params);
      if (parts[0] === 'm' && parts[1] && parts[2] === 'p') return await viewPage(parts[1], parts[3], params);
      if (parts[0] === 'm' && parts[1]) return await viewManual(parts[1]);
      if (parts[0] === 'parts' && !parts[1]) return await viewParts(params);
      if (parts[0] === 'parts' && parts[1] === 'g') return await viewPartsGroup(parts[2]);
      if (parts[0] === 'parts' && parts[1] === 'd') return await viewDiagram(parts[2], params);
      if (parts[0] === 'parts' && parts[1] === 'p') return await viewPart(parts[2]);
      render(h`<p>Page not found. <a href="#/">Home</a></p>`);
    } catch (e) {
      console.error(e);
      render(h`<div class="notice warn"><strong>Something went wrong:</strong> ${e.message}</div>`);
    }
  }

  document.getElementById('topsearch').addEventListener('submit', e => {
    e.preventDefault();
    const v = $q.value.trim(); if (v) location.hash = '#/search/' + encodeURIComponent(v);
  });
  document.addEventListener('keydown', e => { if (state.keyHandler) state.keyHandler(e); if (e.key === '/' && !e.target.matches('input,textarea')) { e.preventDefault(); $q.focus(); } });
  window.addEventListener('hashchange', route);
  loadManuals().then(ms => {
    const info = document.getElementById('buildinfo');
    info.textContent = ms.length ? `${ms.length} manual${ms.length === 1 ? '' : 's'} · ${ms.reduce((a, m) => a + m.pages, 0)} pages` : '';
  });
  route();
})();
