const api = async (path) => {
  const response = await fetch(`/api/v1${path}`);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
};

const escape = (value = "") => String(value).replace(/[&<>"]/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[character]);
const number = (value) => new Intl.NumberFormat().format(value || 0);
const lead = '<p class="kicker">INVESTIGATIVE LEAD, NOT PROOF</p>';

function shell(body) {
  document.querySelector('#root').innerHTML = `<div class="site">
    <header class="nav"><button class="logo" data-view="dashboard">DARKTRACE<span>●</span></button>
      <nav><button data-view="dashboard">Dashboard</button><button data-view="actors">Actors</button><button data-view="graph">Evidence graph</button><button data-view="sources">Sources</button><button data-view="audit">Audit</button></nav>
      <div class="nav-right"><span class="online"><i></i>LOCAL / ARCHIVED</span><button class="launch" data-view="actors">SEARCH RECORDS</button></div>
    </header>${body}<footer><div class="footer-inner wrap"><div><button class="logo" data-view="dashboard">DARKTRACE<span>●</span></button><small>Threat actor intelligence.<br>Local research environment.</small></div><div><b>PRODUCT</b><a>Evidence-led analysis</a><a>Timeline filtering</a></div><div><b>GUARDRAILS</b><a>Passive sources only</a><a>Public metadata only</a></div><div><b>STATUS</b><a><i></i>Local API online</a><a>Live collection disabled</a></div></div><div class="copyright wrap">DARKTRACE // THREAT INTELLIGENCE <span>© 2026 LOCAL RESEARCH ENVIRONMENT</span></div></footer></div>`;
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => render(button.dataset.view)));
}

function loading(title) { shell(`<main class="page wrap"><div class="page-hero">${lead}<h1>${title}</h1><p>Loading verified local records…</p></div></main>`); }
function failure(error) { return `<p style="color:var(--purple);font:12px 'DM Mono'">Unable to load local data: ${escape(error.message)}</p>`; }

async function dashboard() {
  loading('System overview');
  try {
    const [stats, health] = await Promise.all([api('/dashboard/stats'), api('/dashboard/sources/health')]);
    shell(`<main class="page wrap"><div class="page-hero"><span class="kicker">INTELLIGENCE DASHBOARD</span><h1>System <em>overview.</em></h1><p>Query the locally ingested, archived research dataset. Live collection and active probing are disabled.</p>${lead}</div>
      <div class="stats"><div><b>${number(stats.actors)}</b><span>STORED ACTORS</span></div><div><b>${number(stats.identifiers)}</b><span>IDENTIFIERS</span></div><div><b>${number(stats.hidden_services)}</b><span>HIDDEN-SERVICE INDICATORS</span></div><div><b>${number(stats.high_confidence_attributions)}</b><span>HIGH-CONFIDENCE LEADS</span></div></div>
      <section class="section"><div class="section-head"><div><span class="num">01</span><span class="kicker">SOURCE REGISTRY</span></div><h2>Archived sources</h2></div><div class="case-list">${health.sources.map((source) => `<article><span>${escape(source.onion_address)}</span><h2>ARCHIVED</h2><p>Reliability: ${escape(source.reliability_score)} · ${number(source.actor_count)} stored records</p><b>${source.last_scan_date ? new Date(source.last_scan_date).toLocaleDateString() : 'NO SCAN'}</b></article>`).join('')}</div></section></main>`);
  } catch (error) { shell(`<main class="page wrap"><h1>System overview</h1>${failure(error)}</main>`); }
}

async function actors(query = '') {
  loading('Actor search');
  try {
    const data = await api(`/actors?limit=50${query ? `&q=${encodeURIComponent(query)}` : ''}`);
    shell(`<main class="page wrap"><div class="page-hero"><span class="kicker">ACTOR INTELLIGENCE</span><h1>Search <em>actors.</em></h1><p>Results are stored personas from archived sources. Open a record to inspect identifiers and evidence links.</p>${lead}<div class="hero-actions"><input id="actor-query" value="${escape(query)}" placeholder="Handle or text" style="border:2px solid var(--purple);background:var(--paper);padding:10px 14px;border-radius:8px"><button id="actor-search" class="primary">SEARCH →</button><a class="secondary" href="/api/v1/exports/actors.csv${query ? `?q=${encodeURIComponent(query)}` : ''}">EXPORT CSV</a><a class="secondary" href="/api/v1/exports/actors.json${query ? `?q=${encodeURIComponent(query)}` : ''}">EXPORT JSON</a></div></div>
      <p class="kicker">${number(data.total)} MATCHING RECORDS · SHOWING ${number(data.items.length)}</p><div class="case-list">${data.items.map((actor) => `<article><span>#${actor.id}</span><h2>${escape(actor.name)}</h2><p>${escape(actor.market || 'unknown source')} · ${number(actor.identifier_count)} identifiers · ${escape(actor.primary_category || 'unclassified')}</p><b>${escape(actor.source_reliability || 'unknown')}</b><button data-actor="${actor.id}">INSPECT →</button></article>`).join('') || '<p>No matching records.</p>'}</div></main>`);
    document.querySelector('#actor-search').onclick = () => actors(document.querySelector('#actor-query').value.trim());
    document.querySelector('#actor-query').onkeydown = (event) => { if (event.key === 'Enter') actors(event.target.value.trim()); };
    document.querySelectorAll('[data-actor]').forEach((button) => button.onclick = () => actorDetail(button.dataset.actor));
  } catch (error) { shell(`<main class="page wrap"><h1>Actor search</h1>${failure(error)}</main>`); }
}

async function actorDetail(id) {
  loading('Actor record');
  try {
    const data = await api(`/actors/${id}`), actor = data.actor;
    shell(`<main class="page wrap"><div class="page-hero"><span class="kicker">ACTOR RECORD #${actor.id}</span><h1>${escape(actor.name)}</h1><p>${escape(actor.market || 'Unknown source')} · ${escape(actor.primary_category || 'Unclassified')} · last scan ${escape(actor.last_scan_date || 'unknown')}</p>${lead}<div class="hero-actions"><button class="secondary" data-view="actors">← BACK</button><button class="primary" data-graph="${actor.id}">VIEW EVIDENCE GRAPH →</button><a class="secondary" href="/api/v1/actors/${actor.id}/report.pdf">PDF REPORT</a></div></div>
      <section class="section"><div class="section-head"><div><span class="num">01</span><span class="kicker">IDENTIFIERS</span></div><h2>Observed identifiers</h2></div><div class="case-list">${data.identifiers.map((item) => `<article><span>${escape(item.type)}</span><h2 style="font-size:15px;word-break:break-word">${escape(item.value)}</h2><p>${escape(item.market || '')}</p></article>`).join('') || '<p>No validated identifiers recorded.</p>'}</div></section>
      <section class="section"><div class="section-head"><div><span class="num">02</span><span class="kicker">EVIDENCE</span></div><h2>Persona links</h2></div><div class="case-list">${data.persona_links.map((item) => `<article><span>${escape(item.confidence_band)}</span><h2>${escape(item.name)}</h2><p>${escape(item.explanation || 'No explanation stored')}</p><b>${escape(item.confidence_score)}/100</b></article>`).join('') || '<p>No linked personas recorded.</p>'}</div></section></main>`);
    document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => render(button.dataset.view)));
    document.querySelector('[data-graph]').onclick = () => graph(actor.id);
  } catch (error) { shell(`<main class="page wrap"><h1>Actor record</h1>${failure(error)}</main>`); }
}

async function graph(defaultId = '') {
  loading('Evidence graph');
  shell(`<main class="page wrap"><div class="page-hero"><span class="kicker">RELATIONSHIP GRAPH</span><h1>Evidence <em>graph.</em></h1><p>Enter an actor ID to view the stored attribution edges. Edges are leads with preserved evidence text.</p>${lead}<div class="hero-actions"><input id="graph-id" value="${escape(defaultId)}" placeholder="Actor ID" type="number" style="border:2px solid var(--purple);background:var(--paper);padding:10px 14px;border-radius:8px"><button id="graph-load" class="primary">LOAD GRAPH →</button></div></div><div id="graph-result"></div></main>`);
  document.querySelector('#graph-load').onclick = async () => { const id = document.querySelector('#graph-id').value; if (!id) return; try { const data = await api(`/graph/actor/${id}`); document.querySelector('#graph-result').innerHTML = `<div class="case-list">${data.edges.map((edge) => `<article><span>${escape(edge.confidence)}</span><h2>${escape(edge.source)} → ${escape(edge.target)}</h2><p>${escape(edge.evidence || 'Evidence stored')}</p><b>LEAD</b></article>`).join('') || '<p>No stored graph edges at this confidence threshold.</p>'}</div>`; } catch (error) { document.querySelector('#graph-result').innerHTML = failure(error); } };
}

async function sources() { await dashboard(); }
async function audit() { loading('Audit verification'); try { const data = await api('/audit/verify'); shell(`<main class="page wrap"><div class="page-hero"><span class="kicker">GOVERNANCE</span><h1>Audit <em>trail.</em></h1><p>All local API searches, views, and exports are recorded in a hash-linked log.</p>${lead}</div><div class="feature-grid"><article class="feature"><div class="feature-top"><span>HASH CHAIN</span><small>${data.chain_valid ? 'VALID' : 'INVALID'}</small></div><div class="feature-icon">⌁</div><h3>${number(data.entries)} events</h3><p>${data.chain_valid ? 'The local audit chain is internally consistent.' : 'Audit-chain verification failed. Stop using exports until it is reviewed.'}</p></article></div></main>`); } catch(error) { shell(`<main class="page wrap">${failure(error)}</main>`); } }
function render(view) { ({dashboard, actors, graph, sources, audit}[view] || dashboard)(); }
render('dashboard');
