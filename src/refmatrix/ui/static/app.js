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
  if (tab === "bus") return renderBus();
  if (tab === "focus") return renderFocus();
}

async function loadProjects() {
  const r = await api("/api/projects");
  PROJECTS = r.projects || [];
  return PROJECTS;
}

let POLICY = {};  // resolved-root → "auto" | "manual"

async function loadPolicy() {
  try {
    const h = await api("/api/health");
    POLICY = {};
    Object.entries(h.result?.health || {}).forEach(([root, v]) => {
      POLICY[root] = v.policy;
    });
  } catch { POLICY = {}; }
}

async function renderProjects() {
  const el = $("#tab-projects");
  el.innerHTML = `<div class="loading">scanning stores…</div>`;
  const [ps] = await Promise.all([loadProjects(), loadPolicy()]);
  el.innerHTML = `<div class="grid">${ps.map(projCard).join("")}${onboardCard()}</div>`;
  $$("[data-act]", el).forEach((b) => b.addEventListener("click", onProjAction));
  const ob = $("#onboard-go");
  if (ob) ob.addEventListener("click", onboard);
}

function onboardCard() {
  return `<div class="card" style="border-style:dashed">
    <h3>+ onboard a project</h3>
    <div class="sub">add refmatrix to a new repo</div>
    <input id="onboard-path" placeholder="/path/to/project" style="width:100%;padding:6px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;margin-bottom:8px">
    <label class="kv"><span>install hooks</span><input type="checkbox" id="onboard-hooks" checked></label>
    <label class="kv"><span>supervise (launchd)</span><input type="checkbox" id="onboard-launchd"></label>
    <div class="row-actions"><button class="btn" id="onboard-go">onboard</button></div>
    <div id="onboard-out" class="muted" style="font-size:11px;margin-top:8px"></div>
  </div>`;
}

async function onboard() {
  const path = $("#onboard-path").value.trim();
  if (!path) return;
  const out = $("#onboard-out");
  out.textContent = "onboarding…";
  const r = await post("/api/projects/init", {
    path, hooks: $("#onboard-hooks").checked, launchd: $("#onboard-launchd").checked,
  });
  if (!r.ok) { out.textContent = r.error || "failed"; return; }
  out.innerHTML = r.result.steps.map((s) =>
    `${s.ok ? "✓" : "✗"} ${s.step}`).join("<br>");
  setTimeout(renderProjects, 1200);
}

function projCard(p) {
  const f = p.footprint || {};
  const tot = f.total_bytes || 1;
  const seg = (k) => `width:${Math.max(0, 100 * (f[k + "_bytes"] || 0) / tot)}%`;
  const up = p.daemon.up;
  const lc = p.launchd || {};
  const disabled = POLICY[p.root] === "manual";
  return `<div class="card"${disabled ? ' style="opacity:.6"' : ""}>
    <h3><span class="dot ${up ? "up" : "down"}"></span>${p.name}${disabled ? ' <span class="chip">disabled</span>' : ""}</h3>
    <div class="sub">${p.root}</div>
    <div class="kv"><span>daemon</span><span>${up ? "up · pid " + p.daemon.pid : "down"}${p.daemon.rss_mb ? " · " + p.daemon.rss_mb + " MB" : ""}</span></div>
    <div class="kv"><span>watchdog</span><span>${disabled ? "manual (no auto-restart)" : "auto"}</span></div>
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
      ${disabled
        ? `<button class="btn" data-act="enable" data-root="${p.root}">enable</button>`
        : `<button class="btn danger" data-act="disable" data-root="${p.root}">disable</button>`}
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
  else if (act === "disable") {
    // stop auto-restart THEN stop the daemon (else the watchdog races a restart)
    await post("/api/watchdog", {root, policy: "manual"});
    await post("/api/daemon", {root, action: "stop"});
  } else if (act === "enable") {
    await post("/api/watchdog", {root, policy: "auto"});
    await post("/api/daemon", {root, action: "start"});
  } else if (act === "graph") {
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

// ---- bus ----
let BUS_WS = null;
async function renderBus() {
  const el = $("#tab-bus");
  el.innerHTML = `
    <div class="graph-bar" style="border:0;padding:0 0 12px">
      <input id="bus-chan" placeholder="channel (e.g. global:chat or proj:foo:topic)" value="global:">
      <input id="bus-msg" placeholder="message…">
      <select id="bus-type"><option>announce</option><option>decision</option><option>note</option><option>request</option><option>reply</option></select>
      <button class="btn" id="bus-send">publish</button>
      <button class="btn" id="bus-sub">subscribe global:*</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr 360px;gap:12px">
      <div><h2 class="section">live stream</h2><div class="term" id="bus-stream"></div></div>
      <div><h2 class="section">refinement queue</h2><div id="refine"></div></div>
    </div>`;
  $("#bus-send").addEventListener("click", async () => {
    const channel = $("#bus-chan").value, body = $("#bus-msg").value;
    if (!channel || !body) return;
    const project = channel.startsWith("proj:") ? channel.split(":")[1] : null;
    await post("/api/bus/pub", {channel, body, type: $("#bus-type").value, project, from: "ui"});
    $("#bus-msg").value = "";
    loadRefine();
  });
  $("#bus-sub").addEventListener("click", subBus);
  subBus();
  loadRefine();
}

function subBus() {
  if (BUS_WS) { try { BUS_WS.close(); } catch {} }
  const term = $("#bus-stream"); if (!term) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  BUS_WS = new WebSocket(`${proto}://${location.host}/ws/bus`);
  BUS_WS.onopen = () => BUS_WS.send(JSON.stringify({channels: ["*"]}));
  BUS_WS.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.keepalive) return;
    const proj = d.project ? `[${d.project}]` : "";
    term.innerHTML += `<div><span class="muted">${d.ts}</span> <span style="color:var(--accent)">${d.channel}</span> <b>${d.from}</b>${proj} <span style="color:var(--purple)">${d.type}</span>: ${d.body}</div>`;
    term.scrollTop = term.scrollHeight;
    if (d.type === "announce" || d.type === "decision") loadRefine();
  };
}

async function loadRefine() {
  const box = $("#refine"); if (!box) return;
  const r = await api("/api/refine?status=pending");
  const items = r.result?.candidates || [];
  box.innerHTML = items.length ? items.map((c) => `<div class="card" style="padding:10px">
      <div class="kv"><span class="chip ${c.scope === "global" ? "tag" : ""}">${c.scope}</span>
        <span class="muted" style="font-size:11px">${c.channel}</span></div>
      <div style="font-size:12px;margin:6px 0">${c.suggested.content.slice(0, 140)}</div>
      <div class="row-actions">
        <button class="btn" data-acc="${c.id}">accept → memory</button>
        <button class="btn danger" data-rej="${c.id}">dismiss</button></div>
    </div>`).join("") : '<div class="muted">no pending candidates</div>';
  $$("[data-acc]", box).forEach((b) => b.addEventListener("click", async () => {
    await post("/api/refine/accept", {id: b.dataset.acc}); loadRefine();
  }));
  $$("[data-rej]", box).forEach((b) => b.addEventListener("click", async () => {
    await post("/api/refine/reject", {id: b.dataset.rej}); loadRefine();
  }));
}

// ---- focus ----
async function renderFocus() {
  const el = $("#tab-focus");
  const ps = await loadProjects();
  el.innerHTML = `<div class="graph-bar" style="border:0;padding:0 0 12px">
      <select id="focus-project">${ps.map((p) => `<option value="${p.root}">${p.name}</option>`).join("")}</select>
      <select id="focus-session"></select>
      <button class="btn" id="focus-go">refresh</button></div>
    <div id="focus-body"></div>`;
  const loadSessions = async () => {
    const root = $("#focus-project").value;
    const r = await api("/api/focus/sessions?root=" + encodeURIComponent(root));
    const ss = r.result?.sessions || ["default"];
    $("#focus-session").innerHTML = (ss.length ? ss : ["default"]).map((s) => `<option>${s}</option>`).join("");
  };
  const go = async () => {
    const root = $("#focus-project").value, session = $("#focus-session").value || "default";
    const r = await api(`/api/focus?root=${encodeURIComponent(root)}&session=${encodeURIComponent(session)}`);
    const g = r.result?.graph || {nodes: [], focus: []};
    const tasks = r.result?.tasks || [];
    const maxW = Math.max(1, ...g.nodes.map((n) => n.weight));
    // Task stack: top of stack = current. Render newest-first, clickable.
    const stackHtml = tasks.length ? tasks.slice().reverse().map((t, i) => {
      const depth = tasks.length - 1 - i;
      return `<div class="kv stack-item" data-depth="${depth}" style="cursor:pointer">
        <span>${i === 0 ? "▸" : "·"} ${t.desc}</span>
        <span class="muted mono" style="font-size:11px">${t.ts || ""}</span></div>`;
    }).join("") : "<div class='muted'>no task on stack — push with <span class='mono'>rmx task push</span></div>";
    $("#focus-body").innerHTML = `
      <div style="display:grid;grid-template-columns:300px 1fr;gap:12px">
        <div class="card"><h2 class="section">task stack (depth ${tasks.length})</h2>
          ${stackHtml}
          <div id="snap" class="muted" style="margin-top:10px;font-size:12px"></div></div>
        <div><h2 class="section">live focus — ${g.events || 0} events · session ${g.session || session}</h2>
          ${g.nodes.length ? g.nodes.map((n) => `<div class="kv"><span class="mono" style="color:var(--${n.kind === "code" ? "accent" : n.kind === "doc" ? "amber" : "purple"})">${n.name}</span>
            <span>w ${n.weight} · ×${n.count} · °${n.degree}${n.pin ? " · 📌" : ""}</span></div>
            <div class="bar"><i style="background:var(--accent);width:${100 * n.weight / maxW}%"></i></div>`).join("")
            : "<div class='muted'>no focus yet — builds from tool use + rmx calls via the focus hook</div>"}</div>
      </div>`;
    $$(".stack-item", $("#focus-body")).forEach((it) => it.addEventListener("click", () => {
      const t = tasks[+it.dataset.depth];
      const snap = (t.focus_snapshot || []);
      $("#snap").innerHTML = `<b>${t.desc}</b> — focus when pushed:<br>` +
        (snap.length ? snap.map((s) => `<span class="chip" style="margin:2px">${s}</span>`).join("")
          : "<span class='muted'>(empty)</span>");
    }));
  };
  $("#focus-project").addEventListener("change", async () => { await loadSessions(); go(); });
  $("#focus-go").addEventListener("click", go);
  await loadSessions(); go();
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
  $("#graph-project").addEventListener("change", () => {
    if (!$("#graph-landing").classList.contains("hidden")) renderLanding();
  });
  if (G.inited) { showLanding(); return; }
  G.inited = true;
  G.canvas = $("#graph-canvas"); G.ctx = G.canvas.getContext("2d");
  $("#graph-go").addEventListener("click", runGraph);
  $("#graph-ref").addEventListener("keydown", (e) => e.key === "Enter" && runGraph());
  $("#graph-home").addEventListener("click", showLanding);
  $$(".landing-toggle button").forEach((b) => b.addEventListener("click", () => {
    $$(".landing-toggle button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    renderLanding(b.dataset.view);
  }));
  setupGraphInput();
  resizeCanvas(); window.addEventListener("resize", resizeCanvas);
  loop();
  showLanding();
}

let LANDING_VIEW = "top";

function showLanding() {
  $("#graph-landing").classList.remove("hidden");
  $("#graph-home").classList.add("hidden");
  $("#node-panel").classList.add("hidden");
  renderLanding(LANDING_VIEW);
}

function hideLanding() {
  $("#graph-landing").classList.add("hidden");
  $("#graph-home").classList.remove("hidden");
}

async function renderLanding(view) {
  if (view) LANDING_VIEW = view;
  const root = $("#graph-project").value;
  const body = $("#landing-body");
  if (!root) { body.innerHTML = '<div class="muted">no project</div>'; return; }
  body.innerHTML = '<div class="loading">loading…</div>';
  if (LANDING_VIEW === "top") {
    const r = await api(`/api/top?root=${encodeURIComponent(root)}&n=40`);
    const cs = r.result?.concepts || [];
    if (!cs.length) { body.innerHTML = '<div class="muted">no ranked concepts (is the project ingested?)</div>'; return; }
    const max = Math.max(1, ...cs.map((c) => c.total));
    body.innerHTML = cs.map((c) => `<div class="top-item" data-name="${c.name}">
      <span class="nm">${c.name}</span>
      <span class="meter"><i style="width:${100 * c.total / max}%"></i></span>
      <span class="n">${c.total}</span></div>`).join("");
    $$(".top-item", body).forEach((it) => it.addEventListener("click", () => {
      $("#graph-ref").value = it.dataset.name; runGraph();
    }));
  } else {
    const r = await api(`/api/tree?root=${encodeURIComponent(root)}`);
    const es = r.result?.entries || [];
    if (!es.length) { body.innerHTML = '<div class="muted">no files</div>'; return; }
    const codeExt = /\.(py|js|ts|tsx|jsx|go|rs|java|c|cpp|h)$/;
    let lastDir = null, html = "";
    es.forEach((e) => {
      if (e.dir !== lastDir) {
        lastDir = e.dir;
        if (e.dir) html += `<div class="tree-row dir">▸ ${e.dir}/</div>`;
      }
      const cls = codeExt.test(e.name) ? "fcode" : "fdoc";
      html += `<div class="tree-row" data-name="${e.name}" style="padding-left:${12 + e.depth * 12}px">
        <span class="${cls}">${e.name}</span></div>`;
    });
    body.innerHTML = html + (r.result.truncated ? '<div class="muted" style="padding:8px">… truncated</div>' : "");
    $$(".tree-row[data-name]", body).forEach((it) => it.addEventListener("click", () => {
      // seed on the file's stem — context resolves the symbol or greps the file
      $("#graph-ref").value = it.dataset.name.replace(/\.[^.]+$/, "");
      runGraph();
    }));
  }
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
  hideLanding();
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
