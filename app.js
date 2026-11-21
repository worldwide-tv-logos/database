// Worldwide TV Logos — static site. Routes: #/ (countries), #/<cc> (channels of a country), #/<cc>/<channel id>.
'use strict';

const REPO = 'https://github.com/worldwide-tv-logos/database';
const PAGE = 120;                       // channels shown at once on a country page
const app = document.getElementById('app');
const cache = {};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fold = (s) => String(s ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

async function get(path) {
  if (!cache[path]) {
    cache[path] = fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    });
  }
  return cache[path];
}

function form(template, fields) {
  const q = new URLSearchParams({ template, ...fields });
  return `${REPO}/issues/new?${q.toString()}`;
}

// Country flag as an image (emoji flags are not drawn on Windows). iptv-org uses UK where flag sets use GB.
function flag(code, name) {
  const c = { uk: 'gb' }[code] || code;
  return `<img class="flag" src="https://flagcdn.com/w80/${esc(c)}.png" alt="" title="${esc(name)}" loading="lazy" onerror="this.style.visibility='hidden'">`;
}

function logoId(channel, feed) { return feed ? `${channel}@${feed}` : channel; }

// Forms, prefilled with the channel and the edition.
const forms = {
  add: (c, f) => form('01_logos_add.yml', { title: `Add logo: ${logoId(c, f)}`, channel_id: c, ...(f ? { feed_id: f } : {}) }),
  edit: (c, f) => form('02_logos_edit.yml', { title: `Edit logo: ${logoId(c, f)}`, channel_id: c, ...(f ? { feed_id: f } : {}) }),
  remove: (c, f) => form('03_logos_remove.yml', { title: `Remove logo: ${logoId(c, f)}`, channel_id: c, ...(f ? { feed_id: f } : {}) }),
  request: (c, f) => form('04_logos_request.yml', { title: `Logo wanted: ${logoId(c, f)}`, channel_id: c, ...(f ? { feed_id: f } : {}) }),
  aliasAdd: (c, f) => form('05_aliases_add.yml', { title: `Alias: ${logoId(c, f)}`, channel_id: c, ...(f ? { feed_id: f } : {}) }),
  aliasRemove: (c, a) => form('06_aliases_remove.yml', {
    title: `Remove alias: ${a.source}:${a.epg_id}`, epg_id: a.epg_id, epg_source: a.source, channel_id: c,
    ...(a.feed ? { feed_id: a.feed } : {}),
  }),
};

function mainLogo(ch, feed = null) {
  return ch.logos.find((l) => (l.feed || null) === feed && !l.variant);
}

// logo to show on a dark tile: the white variant when there is one
function darkLogo(ch, feed = null) {
  return ch.logos.find((l) => (l.feed || null) === feed && l.variant === 'white') || mainLogo(ch, feed);
}

function thumb(ch) {
  const l = darkLogo(ch) || ch.logos.find((x) => x.variant === 'white') || ch.logos.find((x) => !x.variant);
  if (!l) return '<div class="thumb none">No logo yet</div>';
  return `<div class="thumb"><img loading="lazy" src="${esc(l.url)}" alt="${esc(ch.name)} logo"></div>`;
}

// ---------- home: global search + countries ----------
async function home() {
  const countries = await get('countries.json');
  const total = countries.reduce((n, c) => n + c.channels, 0);
  const logos = countries.reduce((n, c) => n + c.logos, 0);
  const withLogos = countries.filter((c) => c.logos).length;
  app.innerHTML = `
    <section class="hero">
      <h1>TV channel logos from all over the world</h1>
      <p class="sub">Transparent, trimmed, high resolution — one stable address per logo, named after the iptv-org channel ID.</p>
      <div class="stats">
        <div class="stat"><b>${logos.toLocaleString('en')}</b><span>channels with a logo</span></div>
        <div class="stat"><b>${total.toLocaleString('en')}</b><span>channels listed</span></div>
        <div class="stat"><b>${withLogos}</b><span>countries with logos</span></div>
      </div>
      <div class="search">
        <input id="q" type="search" placeholder="Search a channel by name or ID (e.g. France 3, TF1.fr)" autocomplete="off" aria-label="Search a channel">
        <div class="results" id="results" hidden></div>
      </div>
    </section>
    <div class="toolbar">
      <div class="filter"><input id="cf" type="search" placeholder="Filter countries" aria-label="Filter countries"></div>
      <div class="seg" role="group" aria-label="Countries shown">
        <button data-k="logos" aria-pressed="true">With logos</button><button data-k="all" aria-pressed="false">All</button>
      </div>
    </div>
    <div class="countries" id="countries"></div>`;
  let mode = 'logos';
  const draw = () => {
    const f = fold(document.getElementById('cf').value);
    const list = countries
      .filter((c) => (mode === 'all' || c.logos) && (!f || fold(c.name).includes(f) || c.code.includes(f)))
      .sort((a, b) => (mode === 'logos' ? b.logos - a.logos : 0) || a.name.localeCompare(b.name));
    document.getElementById('countries').innerHTML = list.map((c) => `
      <a class="country" href="#/${c.code}">
        ${flag(c.code, c.name)}
        <span style="flex:1;min-width:0">
          <span class="cn">${esc(c.name)}</span>
          <span class="cc">${c.logos} / ${c.channels} channels</span>
          <span class="bar"><i style="width:${c.channels ? Math.round((100 * c.logos) / c.channels) : 0}%"></i></span>
        </span>
      </a>`).join('') || '<p class="empty">No country found.</p>';
  };
  document.getElementById('cf').addEventListener('input', draw);
  document.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
    mode = b.dataset.k;
    document.querySelectorAll('.seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    draw();
  }));
  draw();
  setupSearch();
}

function setupSearch() {
  const q = document.getElementById('q');
  const box = document.getElementById('results');
  let index = null;
  q.addEventListener('focus', async () => { index = index || await get('search.json'); }, { once: true });
  q.addEventListener('input', async () => {
    index = index || await get('search.json');
    const term = fold(q.value.trim());
    if (term.length < 2) { box.hidden = true; return; }
    const hits = [];
    for (const row of index) {
      if (fold(row[1]).includes(term) || row[0].toLowerCase().includes(term)) hits.push(row);
      if (hits.length >= 40) break;
    }
    hits.sort((a, b) => b[3] - a[3]);
    box.innerHTML = hits.map(([id, name, cc, n]) => `
      <a href="#/${cc}/${encodeURIComponent(id)}"><span>${esc(name)}</span>
        ${n ? '<span class="badge">logo</span>' : ''}<span class="rid">${esc(id)}</span></a>`).join('')
      || '<p class="empty" style="padding:10px 14px">No channel found.</p>';
    box.hidden = false;
  });
  document.addEventListener('click', (e) => { if (!box.contains(e.target) && e.target !== q) box.hidden = true; });
}

// ---------- country ----------
async function country(cc) {
  const data = await get(`countries/${cc}.json`);
  const onAir = data.channels.filter((c) => !c.closed);
  const withLogo = onAir.filter((c) => c.logos.length).length;
  app.innerHTML = `
    <div class="crumbs"><a href="#/">Countries</a> / ${esc(data.name)}</div>
    <h1>${flag(data.code, data.name)}${esc(data.name)}</h1>
    <p class="sub">${withLogo} of ${onAir.length} channels on air have a logo.
      Missing one? Open a channel and use <b>Add logo</b>.</p>
    <div class="toolbar">
      <div class="filter"><input id="f" type="search" placeholder="Filter channels by name or ID" aria-label="Filter channels"></div>
      <div class="seg" role="group" aria-label="Channels shown">
        <button data-k="all" aria-pressed="true">All</button><button data-k="logo" aria-pressed="false">With logo</button><button data-k="missing" aria-pressed="false">Missing</button>
      </div>
      <label class="uses"><input type="checkbox" id="closed"> show closed channels</label>
    </div>
    <div class="grid" id="grid"></div>
    <div class="more" id="more"></div>`;
  let mode = 'all';
  let shown = PAGE;
  const draw = () => {
    const f = fold(document.getElementById('f').value);
    const closed = document.getElementById('closed').checked;
    const list = data.channels.filter((c) => (closed || !c.closed || c.logos.length)
      && (mode === 'all' || (mode === 'logo' ? c.logos.length : !c.logos.length))
      && (!f || fold(c.name).includes(f) || c.id.toLowerCase().includes(f) || (c.alt_names || []).some((a) => fold(a).includes(f))));
    document.getElementById('grid').innerHTML = list.slice(0, shown).map((c) => `
      <a class="card" href="#/${cc}/${encodeURIComponent(c.id)}">
        ${thumb(c)}
        <span class="meta"><span class="nm">${esc(c.name)}</span>
          <span class="id">${esc(c.id)}</span>
          ${c.closed ? '<span class="badge closed">closed</span>' : ''}${c.feeds.length > 1 ? `<span class="badge">${c.feeds.length} editions</span>` : ''}</span>
      </a>`).join('') || '<p class="empty">No channel found.</p>';
    document.getElementById('more').innerHTML = list.length > shown
      ? `<button class="btn" id="mb">Show more (${list.length - shown} left)</button>` : '';
    const mb = document.getElementById('mb');
    if (mb) mb.addEventListener('click', () => { shown += PAGE; draw(); });
  };
  document.getElementById('f').addEventListener('input', () => { shown = PAGE; draw(); });
  document.getElementById('closed').addEventListener('change', draw);
  document.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
    mode = b.dataset.k; shown = PAGE;
    document.querySelectorAll('.seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    draw();
  }));
  draw();
}

// ---------- channel ----------
function logoBlock(ch, feed) {
  const main = mainLogo(ch, feed);
  const white = ch.logos.find((l) => (l.feed || null) === feed && l.variant === 'white');
  const id = logoId(ch.id, feed);
  if (!main) {
    return `<div class="missing-box">No logo for <code>${esc(id)}</code> yet.
      <div class="actions" style="justify-content:center">
        <a class="btn primary" href="${forms.add(ch.id, feed)}" target="_blank" rel="noopener">Add logo</a>
        <a class="btn" href="${forms.request(ch.id, feed)}" target="_blank" rel="noopener">Request it</a>
      </div></div>`;
  }
  return `
    <div class="tiles">
      <div><div class="tile dark"><img src="${esc((white || main).url)}" alt="${esc(id)} logo on a dark background"></div>
        <div class="tile-cap">On a dark background${white ? ' (white variant)' : ''}</div></div>
      <div><div class="tile light"><img src="${esc(main.url)}" alt="${esc(id)} logo on a light background"></div>
        <div class="tile-cap">On a light background</div></div>
    </div>
    <div class="info"><span>${main.width} × ${main.height} px</span><span>updated ${esc(main.updated)}</span>
      <span><a href="${esc(main.url)}" target="_blank" rel="noopener">PNG</a>${white ? ` · <a href="${esc(white.url)}" target="_blank" rel="noopener">white PNG</a>` : ''}</span>
      <button class="copy" data-copy="${esc(main.url)}">Copy URL</button></div>
    <div class="actions">
      <a class="btn" href="${forms.edit(ch.id, feed)}" target="_blank" rel="noopener">Replace logo</a>
      <a class="btn danger" href="${forms.remove(ch.id, feed)}" target="_blank" rel="noopener">Report / remove</a>
    </div>`;
}

function editionCard(ch, f) {
  const own = mainLogo(ch, f.id);
  const shown = own ? darkLogo(ch, f.id) : darkLogo(ch);
  const pic = shown
    ? `<div class="thumb${own ? '' : ' inherit'}"><img loading="lazy" src="${esc(shown.url)}" alt="">${own ? '' : '<span class="tag">channel logo</span>'}</div>`
    : '<div class="thumb none">No logo yet</div>';
  const acts = own
    ? `<a href="${esc(own.url)}" target="_blank" rel="noopener">PNG</a>
       <a href="${forms.edit(ch.id, f.id)}" target="_blank" rel="noopener">Replace</a>
       <a class="danger" href="${forms.remove(ch.id, f.id)}" target="_blank" rel="noopener">Remove</a>`
    : `<a href="${forms.add(ch.id, f.id)}" target="_blank" rel="noopener">Add its logo</a>
       <a href="${forms.request(ch.id, f.id)}" target="_blank" rel="noopener">Request</a>`;
  return `<div class="ed">${pic}<div class="meta"><span class="nm">${esc(f.name)}</span>
    <span class="id">${esc(logoId(ch.id, f.id))}</span><span class="acts">${acts}</span></div></div>`;
}

async function channel(cc, id) {
  const data = await get(`countries/${cc}.json`);
  const ch = data.channels.find((c) => c.id === id);
  if (!ch) { app.innerHTML = `<p class="empty">Channel <code>${esc(id)}</code> not found. <a href="#/${cc}">Back</a></p>`; return; }
  const facts = [
    ch.network && `<span>Network <b>${esc(ch.network)}</b></span>`,
    ch.categories?.length && `<span>Categories <b>${esc(ch.categories.join(', '))}</b></span>`,
    ch.launched && `<span>Launched <b>${esc(ch.launched)}</b></span>`,
    ch.closed && `<span class="badge closed">closed ${esc(ch.closed)}</span>`,
    ch.replaced_by && `<span>Replaced by <a href="#/${esc(ch.replaced_by.split('.').pop())}/${encodeURIComponent(ch.replaced_by)}">${esc(ch.replaced_by)}</a></span>`,
    ch.website && `<span><a href="${esc(ch.website)}" target="_blank" rel="noopener nofollow">Website</a></span>`,
  ].filter(Boolean).join('');
  const feeds = ch.feeds.filter((f) => !(f.is_main && !mainLogo(ch, f.id)));   // the main edition uses the channel logo
  app.innerHTML = `
    <div class="crumbs"><a href="#/">Countries</a> / <a href="#/${cc}">${flag(data.code, data.name)}${esc(data.name)}</a> / ${esc(ch.name)}</div>
    <div class="head"><div>
      <h1>${esc(ch.name)}</h1>
      <div class="facts"><span>ID <code>${esc(ch.id)}</code> <button class="copy" data-copy="${esc(ch.id)}">Copy</button></span>${facts}</div>
      ${ch.alt_names?.length ? `<p class="sub" style="margin-top:6px">Also known as ${esc(ch.alt_names.join(', '))}</p>` : ''}
    </div>
    <a class="btn" href="https://iptv-org.github.io/?q=${encodeURIComponent(ch.id)}" target="_blank" rel="noopener">View on iptv-org</a></div>

    <h2>Channel logo</h2>
    <section class="edition">${logoBlock(ch, null)}</section>

    ${feeds.length ? `<h2>Editions</h2>
      <p class="sub">Regional or local versions of the channel (iptv-org feeds). An edition without its own logo uses the channel logo.</p>
      <div class="editions">${feeds.map((f) => editionCard(ch, f)).join('')}</div>` : ''}

    <h2>TV guide IDs</h2>
    <p class="sub">IDs that TV guides (EPG) use for this channel when they differ from the iptv-org ID.</p>
    ${ch.aliases.length ? `<div class="table-wrap"><table><thead><tr><th>Guide ID</th><th>Guide</th><th>Edition</th><th></th></tr></thead><tbody>
      ${ch.aliases.map((a) => `<tr><td><code>${esc(a.epg_id)}</code></td><td>${esc(a.source)}</td><td>${esc(a.feed || '—')}</td>
        <td><a href="${forms.aliasRemove(ch.id, a)}" target="_blank" rel="noopener">remove</a></td></tr>`).join('')}
      </tbody></table></div>` : '<p class="empty">None yet.</p>'}
    <div class="actions"><a class="btn" href="${forms.aliasAdd(ch.id, null)}" target="_blank" rel="noopener">Add a guide ID</a></div>`;
}

// ---------- router ----------
async function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  app.innerHTML = '<p class="loading">Loading…</p>';
  try {
    if (parts.length >= 2) await channel(parts[0].toLowerCase(), parts.slice(1).join('/'));
    else if (parts.length === 1) await country(parts[0].toLowerCase());
    else await home();
    document.title = parts.length ? `${document.querySelector('h1')?.textContent.trim()} · Worldwide TV Logos` : 'Worldwide TV Logos';
  } catch (err) {
    app.innerHTML = `<p class="empty">Could not load this page (${esc(err.message)}). <a href="#/">Home</a></p>`;
  }
  window.scrollTo(0, 0);
}

document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-copy]');
  if (!b) return;
  navigator.clipboard?.writeText(b.dataset.copy).then(() => {
    const t = b.textContent; b.textContent = 'Copied'; setTimeout(() => { b.textContent = t; }, 1200);
  });
});
window.addEventListener('hashchange', route);
route();
