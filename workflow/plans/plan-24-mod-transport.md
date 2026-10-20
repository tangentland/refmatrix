---
gmd: "0.1"
id: plan-24-mod-transport
title: "Plan 24: refmatrix's Claude Code integration as a mod — measured first (24.0), then per-store verb HTTP, hub discovery, a generated mod, hooks retired behind a fallback"
tags: [plan, mod, plugin, hooks, mcp, transport, http, measurement]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-20
  updated: 2026-10-20
---

# Plan 24: mod transport {#root}

**Date:** 2026-10-20.
**Status:** Drafting. Only task 24.0 (the measurement gate) is specified; its band decides the
scope of 24.1-24.8, which are specified after it reads ([[#phasing]]).
**Origin:** [[exploration-claude-code-mod-transport]], Option A chosen by the user 2026-10-20;
the wave hold is [[plan-review-2026-10-14#t13-mod-gate]].

rel: derives-from -> [[exploration-claude-code-mod-transport]]
rel: implements -> [[exploration-claude-code-mod-transport#option-a]]
rel: amends -> [[plan-review-2026-10-14#t13-mod-gate]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: related-to -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[plan-21-agent-context-usage]]

## Why {#why}

refmatrix reaches Claude Code through generated shell hooks (one `rmx` process per hook event),
an MCP stdio server, and session identity guessed from pids and pointer files. Each produces a
recurring defect family ([[exploration-claude-code-mod-transport#defects]]). A Claude Code mod
runs in the engine, sees the real session on every event, injects context without the hook
output cap, and serves tools without a separate process. Whether the spawn cost alone justifies
the build is not yet known: `cli.log`'s `latency_ms` starts after imports and cannot see it
([[exploration-claude-code-mod-transport#measured-spawn]]). 24.0 measures it first. {#why-lead}

## Decisions already made (user, 2026-10-20) {#decisions}

| # | decision | where |
|---|----------|-------|
| D1 | Option A: measure first, hold the hook-shaped Wave 2-3 work at the gate | [[exploration-claude-code-mod-transport#option-a]] |
| D2 | Two HTTP tiers: per-store (each daemon) and hub (global, federated, bus, discovery) | [[exploration-claude-code-mod-transport#http-tiers]] |
| D3 | The per-store surface serves VERBS ONLY, run server-side; raw ops stay on `rmxd.sock` | [[exploration-claude-code-mod-transport#http-verbs-only]] |
| D4 | No daemon ⇒ the mod spawns the PROJECT's `rmx` (never PATH's); busy never spawns | [[exploration-claude-code-mod-transport#verb-host-absent]] |
| D5 | Distribution: marketplace AND deploy-tree `--plugin-dir`; version + schema handshake; the deploy copy wins | [[exploration-claude-code-mod-transport#distribution]] |
| D6 | The gate week runs on refmatrix alone (the only active project) | [[exploration-claude-code-mod-transport#gate-instrument]] |

## Tasks {#tasks}

| task | what | status |
|------|------|--------|
| [[task-24.0-spawn-cost-gate]] | instrument spawn per hook process, collect one week on refmatrix, report against the pre-registered bands | spec written |
| 24.1 | the store records its runtime identity (rmx binary, version, verb-schema hash) on daemon start — D4 / D5's hub-down source | after the gate |
| 24.2 | in-daemon verb host + the per-store HTTP socket (`rmxd-http.sock`), verbs only (D3) | after the gate |
| 24.3 | hub HTTP: discovery (cwd → store socket + identity), global, federated, bus (D2) | after the gate |
| 24.4 | verb-schema export; the mod's tools and routes GENERATED from `VERBS`; a TS transport-error classifier twin with cross-language parity | after the gate |
| 24.5 | the mod: `session.start` handshake, tool registration, status line + toasts (Option C surfaces) | after the gate |
| 24.6 | the hottest hooks move into the mod (`focus hook` pre/post, `scan-prompt`, recall, grep guard); shell hooks stay as the fallback | after the gate |
| 24.7 | distribution: marketplace file, deploy `--plugin-dir`, the double-load stand-down (D5) | after the gate |
| 24.8 | retire `rmx mcp` for the Claude Code path; re-target or release the held items | after the gate |

## Phasing {#phasing}

- **Phase 0 — 24.0 only.** It is approved and built on its own. It changes one telemetry field
  and the hook-row classifier; it adds no mod code. {#phase-0}
- **Phase 1 — scope set by the band.** When 24.0 reports, this plan is amended: the band's
  action ([[task-24.0-spawn-cost-gate#ranges]]) names which of 24.1-24.8 are specified, their
  order, and what happens to each held item ([[plan-review-2026-10-14#t13-mod-gate]]). Those
  specs then go through the usual spec review before any of them is built. {#phase-1}

## Out of scope {#out-of-scope}

- Making `scan-prompt` or `memory recall` faster: their cost is daemon work
  ([[exploration-claude-code-mod-transport#measured-work]]).
- Rewriting the engine, CLI, launchd services or evals out of Python.
