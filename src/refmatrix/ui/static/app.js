"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (p) => (await fetch(p)).json();
const post = async (p, b) => (await fetch(p, {
  method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(b),
})).json();
const fmtBytes = (n) => {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
};
const KIND_COLOR = {code: "#58a6ff", doc: "#d29922", concept: "#bc8cff",
  memory: "#3fb950", query: "#8b949e", session: "#8b949e"};

let PROJECTS = [];

// ---- tabs ----
$$("#tabs button").forEach((b) => b.addEventListener("click", () => {
  $$("#tabs button").forEach((x) => x.classList.remove("active"));
  $$(".tab").forEach((x) => x.classList.remove("active"));
  b.classList.add("active");
  $("#tab-" + b.dataset.tab).classList.add("active");
  render(b.dataset.tab);
}));

async function refreshHubState() {
  try {
    const r = await api("/api/hub");
    if (r.ok) $("#hub-state").textContent =
      `hub ● pid ${r.result.pid} · ${r.result.registry_size} stores`;
  } catch { $("#hub-state").textContent = "hub offline"; }
}

// ---- projects ----
async function render(tab) {
  if (tab === "projects") return renderProjects();
  if (tab === "graph") return initGraphTab();
  if (tab === "ops") return renderOps();
  if (tab === "health") return renderHealth();
  if (tab === "usage") return renderUsage();
  if (tab === "memory") return renderMemory();
}

async function loadProjects() {
  const r = await api("/api/projects");
  PROJECTS = r.projects || [];
  return PROJECTS;
}

async function renderProjects() {
  const el = $("#tab-projects");
  el.innerHTML = `<div class="loading">scanning stores…</div>`;
  const ps = await loadProjects();
  el.innerHTML = `<div class="grid">${ps.map(projCard).join("")}</div>`;
  $$("[data-act]", el).forEach((b) => b.addEventListener("click", onProjAction));
}

function projCard(p) {
  const f = p.footprint || {};
  const tot = f.total_bytes || 1;
  const seg = (k) => `width:${Math.max(0, 100 * (f[k + "_bytes"] || 0) / tot)}%`;
  const up = p.daemon.up;
  const lc = p.launchd || {};
  return `<div class="card">
    <h3><span class="dot ${up ? "up" : "down"}"></span>${p.name}</h3>
    <div class="sub">${p.root}</div>
    <div class="kv"><span>daemon</span><span>${up ? "up · pid " + p.daemon.pid : "down"}${p.daemon.rss_mb ? " · " + p.daemon.rss_mb + " MB" : ""}</span></div>
    <div class="kv"><span>supervised</span><span>${lc.loaded ? "launchd ●" : (lc.installed ? "installed" : "no")}</span></div>
    <div class="kv"><span>disk</span><span>${fmtBytes(f.total_bytes)}</span></div>
    <div class="bar">
      <i class="seg-catalog" style="${seg("catalog")}"></i>
      <i class="seg-vectors" style="${seg("vectors")}"></i>
      <i class="seg-logs" style="${seg("logs")}"></i>
    </div>
    <div class="legend" style="padding:0"><span><i style="background:var(--accent)"></i>catalog ${fmtBytes(f.catalog_bytes)}</span>
      <span><i style="background:var(--purple)"></i>vectors ${fmtBytes(f.vectors_bytes)}</span>
      <span><i style="background:var(--amber)"></i>logs ${fmtBytes(f.logs_bytes)}</span></div>
    <div class="row-actions">
      ${up ? `<button class="btn danger" data-act="dstop" data-root="${p.root}">stop daemon</button>`
           : `<button class="btn" data-act="dstart" data-root="${p.root}">start daemon</button>`}
      <button class="btn" data-act="restart" data-root="${p.root}">restart</button>
      <button class="btn" data-act="graph" data-root="${p.root}">graph</button>
    </div>
  </div>`;
}

async function onProjAction(e) {
  const root = e.target.dataset.root, act = e.target.dataset.act;
  e.target.disabled = true; e.target.textContent = "…";
  if (act === "dstart") await post("/api/daemon", {root, action: "start"});
  else if (act === "dstop") await post("/api/daemon", {root, action: "stop"});
  else if (act === "restart") await post("/api/restart", {root});
  else if (act === "graph") {
    $$("#tabs button").forEach((x) => x.classList.remove("active"));
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $('#tabs button[data-tab="graph"]').classList.add("active");
    $("#tab-graph").classList.add("active");
    await initGraphTab(); $("#graph-project").value = root; return;
  }
  setTimeout(renderProjects, 400);
}

// ---- usage ----
async function renderUsage() {
  const el = $("#tab-usage");
  el.innerHTML = `<div class="loading">aggregating telemetry…</div>`;
  const [u, a] = await Promise.all([api("/api/usage"), api("/api/adoption")]);
  const us = u.result || {};
  const barRow = (label, val, max) => `<div class="kv"><span>${label}</span>
    <span>${val}</span></div><div class="bar"><i style="background:var(--accent);width:${100 * val / (max || 1)}%"></i></div>`;
  const sub = us.by_subcommand || {}; const maxSub = Math.max(1, ...Object.values(sub));
  const src = us.by_source || {}; const maxSrc = Math.max(1, ...Object.values(src));
  const proj = us.by_project || {}; const maxP = Math.max(1, ...Object.values(proj));
  const sigs = (a.result?.projects) || [];
  el.innerHTML = `
   <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
    <div class="card"><h2 class="section">by form (source)</h2>
      ${Object.entries(src).map(([k, v]) => barRow(k, v, maxSrc)).join("") || '<div class="muted">no data</div>'}
      <div class="kv" style="margin-top:8px"><span>total invocations</span><span>${us.total || 0}</span></div>
    </div>
    <div class="card"><h2 class="section">top subcommands</h2>
      ${Object.entries(sub).slice(0, 10).map(([k, v]) => barRow(k, v, maxSub)).join("") || '<div class="muted">no data</div>'}
    </div>
    <div class="card"><h2 class="section">by project</h2>
      ${Object.entries(proj).map(([k, v]) => barRow(k, v, maxP)).join("") || '<div class="muted">no data</div>'}
    </div>
   </div>
   <h2 class="section" style="margin-top:18px">adoption — integration refinement</h2>
   ${sigs.length ? sigs.map(adoptionCard).join("") : '<div class="muted">no signals — everything looks wired up</div>'}`;
  $$("[data-fix]", el).forEach((b) => b.addEventListener("click", onFix));
}

function adoptionCard(p) {
  const sevColor = {high: "var(--down)", medium: "var(--amber)", low: "var(--dim)"};
  return `<div class="card"><h3>${p.name}</h3><div class="sub">${p.root}</div>
    ${p.signals.map((s) => `<div class="kv">
      <span style="color:${sevColor[s.severity]}">● ${s.kind}</span>
      <span>${s.fix_action ? `<button class="btn" data-fix="${s.fix_action}" data-root="${p.root}">${s.fix_action}</button>` : ""}</span>
    </div><div class="muted" style="font-size:12px;margin:-2px 0 8px">${s.message}</div>`).join("")}</div>`;
}

async function onFix(e) {
  const fix = e.target.dataset.fix, root = e.target.dataset.root;
  e.target.disabled = true; e.target.textContent = "running…";
  if (fix === "daemon start") await post("/api/daemon", {root, action: "start"});
  else if (fix.startsWith("ingest") || fix === "sync") runOp(root, fix.split(" ")[0], fix.split(" ").slice(1));
  setTimeout(renderUsage, 800);
}

// ---- health ----
async function renderHealth() {
  const el = $("#tab-health");
  const r = await api("/api/health");
  const h = r.result?.health || {};
  const rows = Object.entries(h).map(([root, v]) => {
    const last = v.history[v.history.length - 1] || {};
    return `<tr><td>${last.up ? '<span class="dot up"></span>' : '<span class="dot down"></span>'}</td>
      <td class="mono">${root}</td><td>${v.policy}</td><td>${v.restart_count}</td>
      <td class="muted mono">${last.ts || "—"}</td></tr>`;
  }).join("");
  el.innerHTML = `<h2 class="section">watchdog health</h2>
    <table><thead><tr><th></th><th>store</th><th>policy</th><th>restarts</th><th>last check</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="5" class="muted">no samples yet — watchdog ticks every ~15s</td></tr>'}</tbody></table>
    <h2 class="section" style="margin-top:18px">hub log</h2>
    <div class="term" id="loglines"></div>`;
  tailLog("hub", $("#loglines"));
}

// ---- ops ----
async function renderOps() {
  const el = $("#tab-ops");
  const ps = await loadProjects();
  el.innerHTML = `<div class="graph-bar" style="border:0;padding:0 0 12px">
      <select id="ops-project">${ps.map((p) => `<option value="${p.root}">${p.name}</option>`).join("")}</select>
      ${["ingest", "embed", "sync", "vacuum", "checkpoint"].map((o) =>
        `<button class="btn" data-op="${o}">${o}</button>`).join("")}
      <label class="degree"><input type="checkbox" id="ops-semantic"> semantic</label>
    </div>
    <div class="term" id="ops-term"></div>`;
  $$("[data-op]", el).forEach((b) => b.addEventListener("click", () => {
    const root = $("#ops-project").value;
    const args = b.dataset.op === "ingest"
      ? [".", ...($("#ops-semantic").checked ? ["--semantic"] : [])] : [];
    runOp(root, b.dataset.op, args);
  }));
}

function runOp(root, op, args) {
  const term = $("#ops-term") || (() => {
    $('#tabs button[data-tab="ops"]').click(); return $("#ops-term");
  })();
  if (!term) return;
  term.innerHTML += `<div style="color:var(--accent)">$ rmx ${op} ${(args || []).join(" ")} <span class="muted">[${root}]</span></div>`;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/op`);
  ws.onopen = () => ws.send(JSON.stringify({root, op, args}));
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.line !== undefined) { term.innerHTML += d.line + "\n"; term.scrollTop = term.scrollHeight; }
    else if (d.done) { term.innerHTML += `<div class="${d.code ? "err" : "muted"}">— exit ${d.code} —</div>`; term.scrollTop = term.scrollHeight; }
    else if (d.error) term.innerHTML += `<div class="err">${d.error}</div>`;
  };
}

function tailLog(root, el) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);
  ws.onopen = () => ws.send(JSON.stringify({root}));
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.line) { el.textContent += d.line + "\n"; el.scrollTop = el.scrollHeight; }
  };
  el._ws = ws;
}

// ---- memory ----
async function renderMemory() {
  const el = $("#tab-memory");
  const ps = await loadProjects();
  el.innerHTML = `<div class="graph-bar" style="border:0;padding:0 0 12px">
      <select id="mem-project">${ps.map((p) => `<option value="${p.root}">${p.name}</option>`).join("")}</select>
      <input id="mem-q" placeholder="search memory…">
      <input id="mem-tag" placeholder="tag" style="max-width:140px">
      <button class="btn" id="mem-go">search</button></div>
    <div id="mem-results"></div>`;
  const go = async () => {
    const root = $("#mem-project").value, q = $("#mem-q").value, tag = $("#mem-tag").value;
    const qs = new URLSearchParams({root, q, ...(tag ? {tag} : {})});
    const r = await api("/api/memory?" + qs);
    const rows = r.result?.rows || [];
    $("#mem-results").innerHTML = rows.length ? `<table><thead><tr><th>name</th><th>mtype</th><th>tags</th><th>content</th></tr></thead>
      <tbody>${rows.map((m) => `<tr><td class="mono">${m.name}</td><td><span class="chip">${m.mtype || ""}</span></td>
        <td>${(m.tags || []).map((t) => `<span class="chip tag">${t}</span>`).join(" ")}</td>
        <td class="muted">${(m.content || "").slice(0, 120)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="muted">${r.ok ? "no memories" : (r.error || "error")}</div>`;
  };
  $("#mem-go").addEventListener("click", go);
  $("#mem-q").addEventListener("keydown", (e) => e.key === "Enter" && go());
  go();
}

// ---- omnibox (where) ----
let omniTimer;
$("#omni").addEventListener("input", (e) => {
  clearTimeout(omniTimer);
  const q = e.target.value.trim();
  if (q.length < 2) return $("#omni-results").classList.add("hidden");
  omniTimer = setTimeout(() => doWhere(q), 250);
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".omnibox")) $("#omni-results").classList.add("hidden");
});

async function doWhere(q) {
  const box = $("#omni-results");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="omni-group">searching…</div>`;
  const r = await api("/api/where?q=" + encodeURIComponent(q));
  const hits = r.result?.results || [];
  if (!hits.length) { box.innerHTML = `<div class="omni-group">no hits</div>`; return; }
  const groups = {};
  hits.forEach((h) => (groups[h.source] = groups[h.source] || []).push(h));
  box.innerHTML = Object.entries(groups).map(([g, items]) =>
    `<div class="omni-group">${g}</div>` + items.slice(0, 8).map((h) =>
      `<div class="omni-item" data-root="${h.root || ""}" data-name="${h.name}">
        <span class="dot" style="background:${KIND_COLOR[h.kind] || "#8b949e"}"></span>
        <span class="nm">${h.name}</span>
        <span class="loc">${h.project || ""}${h.path ? " · " + h.path.split("/").pop() + (h.line ? ":" + h.line : "") : ""}</span>
      </div>`).join("")).join("");
  $$(".omni-item", box).forEach((it) => it.addEventListener("click", () => {
    const root = it.dataset.root, name = it.dataset.name;
    box.classList.add("hidden"); $("#omni").value = "";
    $('#tabs button[data-tab="graph"]').click();
    if (root) $("#graph-project").value = root;
    $("#graph-ref").value = name; runGraph();
  }));
}

// ---- graph (canvas force-directed) ----
let G = {nodes: [], edges: [], canvas: null, ctx: null, raf: null,
  cam: {x: 0, y: 0, z: 1}, drag: null, inited: false};

async function initGraphTab() {
  if (!PROJECTS.length) await loadProjects();
  const sel = $("#graph-project");
  if (!sel.children.length)
    sel.innerHTML = PROJECTS.map((p) => `<option value="${p.root}">${p.name}</option>`).join("");
  if (G.inited) return;
  G.inited = true;
  G.canvas = $("#graph-canvas"); G.ctx = G.canvas.getContext("2d");
  $("#graph-go").addEventListener("click", runGraph);
  $("#graph-ref").addEventListener("keydown", (e) => e.key === "Enter" && runGraph());
  setupGraphInput();
  resizeCanvas(); window.addEventListener("resize", resizeCanvas);
  loop();
}

function resizeCanvas() {
  const c = G.canvas; if (!c) return;
  const r = c.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  c.width = r.width * dpr; c.height = r.height * dpr;
  G.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  G.w = r.width; G.h = r.height;
}

async function runGraph() {
  const root = $("#graph-project").value, ref = $("#graph-ref").value.trim();
  const degree = +$("#graph-degree").value;
  if (!root || !ref) return;
  const r = await api(`/api/graph?root=${encodeURIComponent(root)}&seed=${encodeURIComponent(ref)}&degree=${degree}`);
  if (!r.ok) { alert(r.error || "graph error"); return; }
  mergeGraph(r.result, true);
}

async function expandNode(node) {
  const root = $("#graph-project").value;
  const degree = +$("#graph-degree").value;
  const r = await api(`/api/graph?root=${encodeURIComponent(root)}&seed=${encodeURIComponent(node.name)}&degree=${degree}`);
  if (r.ok) mergeGraph(r.result, false);
}

function mergeGraph(g, reset) {
  if (reset) { G.nodes = []; G.edges = []; }
  const byId = new Map(G.nodes.map((n) => [n.id, n]));
  const cx = G.w / 2, cy = G.h / 2;
  g.nodes.forEach((n) => {
    if (!byId.has(n.id)) {
      n.x = cx + (Math.random() - .5) * 200; n.y = cy + (Math.random() - .5) * 200;
      n.vx = 0; n.vy = 0; byId.set(n.id, n); G.nodes.push(n);
    } else { Object.assign(byId.get(n.id), {tldr: n.tldr, path: n.path, snippet: n.snippet}); }
  });
  const eset = new Set(G.edges.map((e) => e.source + ">" + e.target + e.linkage));
  g.edges.forEach((e) => {
    const k = e.source + ">" + e.target + e.linkage;
    if (!eset.has(k)) { eset.add(k); G.edges.push(e); }
  });
}

function tick() {
  const N = G.nodes, E = G.edges;
  const idx = new Map(N.map((n) => [n.id, n]));
  for (let i = 0; i < N.length; i++) {
    for (let j = i + 1; j < N.length; j++) {
      const a = N[i], b = N[j];
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy || 1;
      const f = 2200 / d2; const d = Math.sqrt(d2);
      a.vx += f * dx / d; a.vy += f * dy / d; b.vx -= f * dx / d; b.vy -= f * dy / d;
    }
  }
  E.forEach((e) => {
    const a = idx.get(e.source), b = idx.get(e.target); if (!a || !b) return;
    let dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const f = (d - 90) * 0.01;
    a.vx += f * dx / d; a.vy += f * dy / d; b.vx -= f * dx / d; b.vy -= f * dy / d;
  });
  const cx = G.w / 2, cy = G.h / 2;
  N.forEach((n) => {
    n.vx += (cx - n.x) * 0.001; n.vy += (cy - n.y) * 0.001;
    n.vx *= 0.85; n.vy *= 0.85;
    if (n !== (G.drag && G.drag.node)) { n.x += n.vx; n.y += n.vy; }
  });
}

function draw() {
  const ctx = G.ctx, {x, y, z} = G.cam;
  ctx.clearRect(0, 0, G.w, G.h);
  ctx.save(); ctx.translate(x, y); ctx.scale(z, z);
  const idx = new Map(G.nodes.map((n) => [n.id, n]));
  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(139,148,158,.25)";
  G.edges.forEach((e) => {
    const a = idx.get(e.source), b = idx.get(e.target); if (!a || !b) return;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  });
  ctx.font = "11px ui-monospace, monospace";
  G.nodes.forEach((n) => {
    const r = n.anchor ? 8 : 5;
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7);
    ctx.fillStyle = KIND_COLOR[n.kind] || "#8b949e"; ctx.fill();
    if (n.anchor) { ctx.lineWidth = 2; ctx.strokeStyle = "#fff"; ctx.stroke(); }
    ctx.fillStyle = "#e6edf3";
    ctx.fillText(n.name.length > 22 ? n.name.slice(0, 21) + "…" : n.name, n.x + r + 3, n.y + 4);
  });
  ctx.restore();
}

function loop() { tick(); draw(); G.raf = requestAnimationFrame(loop); }

function screenToWorld(px, py) {
  return {x: (px - G.cam.x) / G.cam.z, y: (py - G.cam.y) / G.cam.z};
}
function nodeAt(px, py) {
  const w = screenToWorld(px, py);
  return G.nodes.find((n) => Math.hypot(n.x - w.x, n.y - w.y) < 10);
}

function setupGraphInput() {
  const c = G.canvas;
  let downAt = null, moved = false;
  c.addEventListener("mousedown", (e) => {
    const rect = c.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const n = nodeAt(px, py); downAt = {px, py}; moved = false;
    G.drag = n ? {node: n} : {pan: true, sx: px, sy: py, cx: G.cam.x, cy: G.cam.y};
  });
  c.addEventListener("mousemove", (e) => {
    if (!G.drag) return;
    const rect = c.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    if (Math.hypot(px - downAt.px, py - downAt.py) > 3) moved = true;
    if (G.drag.node) { const w = screenToWorld(px, py); G.drag.node.x = w.x; G.drag.node.y = w.y; }
    else if (G.drag.pan) { G.cam.x = G.drag.cx + (px - G.drag.sx); G.cam.y = G.drag.cy + (py - G.drag.sy); }
  });
  c.addEventListener("mouseup", (e) => {
    const rect = c.getBoundingClientRect();
    const n = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (!moved && n) showNode(n);
    G.drag = null;
  });
  c.addEventListener("dblclick", (e) => {
    const rect = c.getBoundingClientRect();
    const n = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (n) expandNode(n);
  });
  c.addEventListener("wheel", (e) => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 0.9;
    G.cam.z = Math.max(0.2, Math.min(4, G.cam.z * f));
  }, {passive: false});
}

function showNode(n) {
  const p = $("#node-panel");
  p.classList.remove("hidden");
  p.innerHTML = `<h3>${n.name}</h3>
    <div class="kv"><span>kind</span><span style="color:${KIND_COLOR[n.kind]}">${n.kind}</span></div>
    ${n.path ? `<div class="sub">${n.path}</div>` : ""}
    ${n.tldr ? `<p class="muted" style="font-size:12px">${n.tldr}</p>` : ""}
    ${n.snippet ? `<pre>${n.snippet.replace(/[<>]/g, "")}</pre>` : ""}
    <div class="row-actions"><button class="btn" id="np-expand">expand</button>
      <button class="btn" id="np-close">close</button></div>`;
  $("#np-expand").addEventListener("click", () => expandNode(n));
  $("#np-close").addEventListener("click", () => p.classList.add("hidden"));
}

// ---- boot ----
refreshHubState();
renderProjects();
setInterval(refreshHubState, 15000);
