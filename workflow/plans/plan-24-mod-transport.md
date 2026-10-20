---
gmd: "0.1"
id: plan-24-mod-transport
title: "Plan 24: refmatrix's Claude Code integration as a mod — tighter integration (real session identity, in-engine context injection, tool-call observation, in-engine tools, live surfaces), with hooks kept as the fallback"
tags: [plan, mod, plugin, hooks, mcp, transport, http, integration]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-20
  updated: 2026-10-20
---

# Plan 24: mod transport {#root}

**Date:** 2026-10-20.
**Status:** Drafting. The transition is DECIDED (user, 2026-10-20); task 24.0 (a baseline, not a
gate) is specified, and 24.1-24.8 are written next ([[#tasks]]).
**Origin:** [[exploration-claude-code-mod-transport]]; the wave change is
[[plan-review-2026-10-14#t13-mod-gate]].

rel: derives-from -> [[exploration-claude-code-mod-transport]]
rel: implements -> [[exploration-claude-code-mod-transport#reason]]
rel: amends -> [[plan-review-2026-10-14#t13-mod-gate]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: related-to -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[plan-21-agent-context-usage]]
rel: related-to -> [[plan-19-adaptive-memory-budget]]

## Why: tighter integration {#why}

The user, 2026-10-20: "the spawn cost is not the primary reason to make the transition. The main
reason is tighter integration." refmatrix reaches Claude Code from OUTSIDE the engine today:
generated shell hooks that see a stdin envelope and print text, an MCP stdio server, and a
session identity reconstructed from pids and pointer files. Inside the engine, refmatrix sees
what Claude Code sees and acts where it acts. {#why-lead}

### Integration goals {#goals}

- **G1 Real session identity.** Every event carries the session; the pointer / pid resolver
  ladder (bug-109, 21.1's resolver, bug-139's wrong ring) retires on the Claude Code path.
- **G2 Context where the model reads it.** `prompt.compose` adds a system-prompt section and
  `prompt.submit` shapes the prompt: no hook-output cap
  ([[reference_hook_output_10k_cap]]), no transcript noise, the primer as a cached section.
- **G3 Tool calls observed, not intercepted by shell.** `tool.call` sees every call AND its
  result (`await next(e)`): grep learning, exact `used` detection (21.x), the indexed-symbol
  nudge, STM refs from real results instead of re-parsed stdin.
- **G4 Tools in the engine.** `$.tool.register`, generated from `VERBS`; no `rmx mcp` process,
  no reconnect after a deploy, no orphans ([[feedback_mcp_server_reload_and_orphans]]).
- **G5 Live surfaces.** Status line (store / hub health, version skew, focus subject, queue
  depth), toasts (fast-exit, crash loop, version mismatch), a pane (focus graph, recall-state,
  bus); bus messages wake an idle session with `$.prompt.submit`.
- **G6 Failures visible.** A failing hook is a transcript line and a debug-log line, never a
  `2>/dev/null || true`.

Spawn cost is a secondary benefit, measured as a before/after baseline (24.0), not a gate.
{#goals-tail}

## Decisions (user, 2026-10-20) {#decisions}

| # | decision | where |
|---|----------|-------|
| D0 | The transition is made for tighter integration; spawn cost is secondary and does not gate it | [[exploration-claude-code-mod-transport#reason]] |
| D1 | The hook-shaped work (plan-16's build, 19.5 R1, 19.6's injection design, 21.2-21.4) retargets to the mod instead of being built on hooks | [[plan-review-2026-10-14#t13-mod-gate]] |
| D2 | Two HTTP tiers: per-store (each daemon) and hub (global, federated, bus, discovery) | [[exploration-claude-code-mod-transport#http-tiers]] |
| D3 | The per-store surface serves VERBS ONLY, run server-side; raw ops stay on `rmxd.sock` | [[exploration-claude-code-mod-transport#http-verbs-only]] |
| D4 | No daemon ⇒ the mod spawns the PROJECT's `rmx` (never PATH's); busy never spawns | [[exploration-claude-code-mod-transport#verb-host-absent]] |
| D5 | Distribution: marketplace AND deploy-tree `--plugin-dir`; version + schema handshake; the deploy copy wins | [[exploration-claude-code-mod-transport#distribution]] |
| D6 | Measurements run on refmatrix alone (the only active project) | [[exploration-claude-code-mod-transport#gate-instrument]] |

## Tasks {#tasks}

| task | what | goal | status |
|------|------|------|--------|
| [[task-24.0-hook-cost-baseline]] | spawn + import cost per hook process, before AND after the mod; a baseline, not a gate | secondary | spec written |
| 24.1 | the store records its runtime identity (rmx binary, version, verb-schema hash) on daemon start — D4 / D5's hub-down source | G4, D4, D5 | spec next |
| 24.2 | in-daemon verb host + the per-store HTTP socket (`rmxd-http.sock`), verbs only (D3) | G4 | spec next |
| 24.3 | hub HTTP: discovery (cwd → store socket + identity), global, federated, bus (D2) | G4, G5 | spec next |
| 24.4 | verb-schema export; the mod's tools and routes GENERATED from `VERBS`; a TS transport-error classifier twin with cross-language parity | G4 | spec next |
| 24.5 | the mod: `session.start` handshake, real session identity end to end, tool registration, status line + toasts | G1, G4, G5, G6 | spec next |
| 24.6 | context and observation move in: `prompt.compose` / `prompt.submit` (scan-prompt, recall, primer), `tool.call` (focus pre/post, grep guard); shell hooks stay as the fallback | G1, G2, G3 | spec next |
| 24.7 | distribution: marketplace file, deploy `--plugin-dir`, the double-load stand-down (D5) | — | spec next |
| 24.8 | retire `rmx mcp` on the Claude Code path; the held items re-specified against the mod (D1) | G4 | spec next |

## Phasing {#phasing}

- **24.0 and 24.1** start now, in parallel with Wave 1's engine work: 24.0 needs a week of
  pre-mod data, so its "before" window has to open before the mod exists. {#phase-now}
- **24.2 → 24.3 → 24.4 → 24.5 → 24.6 → 24.7 → 24.8** follow; 24.4 needs 3.7 merged. {#phase-build}
- **The held items** (D1) are re-specified once 24.5 and 24.6 define the mod's events and
  surfaces they build on; their current hook-based specs are kept as records, not built. {#phase-held}

## Out of scope {#out-of-scope}

- Making `scan-prompt` or `memory recall` faster: their cost is daemon work
  ([[exploration-claude-code-mod-transport#measured-work]]).
- Rewriting the engine, CLI, launchd services or evals out of Python.
