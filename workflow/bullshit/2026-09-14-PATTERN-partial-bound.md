---
gmd: "0.1"
id: bsd-pattern-partial-bound
title: "PATTERN: a hook's bound covers the surface the finding named and stops one call, one leg, or one hook short (5 runs)"
tags: [bsd, pattern, hooks, timeouts]
metadata:
  node_type: bsd-pattern
  occurrences: 5
  first_seen: c9d75af
  last_seen: 768f868
---

# PATTERN: the bound stops at the quoted surface {#root}

Four consecutive plan-2 rounds found the same shape: a timeout is added exactly where the finding pointed, and the next call, leg, or hook on the same path keeps the library default. Each remedy was correct for the state it named and measured; the invariant ("a hook may not hold the turn for the store") was never re-checked across the whole path. {#shape}

rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r3-c9d75af]]
rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r4-d68856d]]
rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r5-a89c733]]
rel: evidence-for -> [[bsd-plan2-hooks-reproducible-r6-3fa98bc]]

## Occurrences {#occurrences}

| run | bound added | what stayed unbounded | measured |
|-----|-------------|-----------------------|----------|
| c9d75af (r3 #b-1) | `--timeout 5` on the Stop promote's `memory_add` | `subject_upsert` + `subject_link` on the same hook | 180 s with a subject set |
| d68856d (r4 #s-1) | one cheap probe + `RMX_DETACH_WAIT_S` on the SessionStart bridge | `partition_list` (retries=2) + `ingest_gmd_start` (60 s x 3) behind the probe | 210 s, blank traceback |
| a89c733 (r5 #b-1) | Stop, PreCompact, SessionStart bridge all bounded | the two `memory recall` hooks (UserPromptSubmit every prompt, SessionStart) — `_call` 180 s x 3, `memory_get` 30 s x 3 per hit, hub 30 s | p50 20.0 s over 36 live rows; 19.6 s re-measured |
| 3fa98bc (r6 #b-1) | `--timeout 5` / `--timeout 10` on both recall hooks; one deadline over the daemon RPCs (`memory_partition`, `memory_recall`, `memory_get`, `_call` retries=0) | the rerank on the hub shared worker inside `_replica_memory_recall` (`info()` + `call("rerank")` at the 300 s worker default — ~12.5 s of the 12.8 s), the dense path's global leg (`_global_rows` → no timeout, `hub.global_call` no `retries`), and the `_memory_intent` partition probe that spends its own budget before `_t_start` | 12.8 s idle with results and no warning; 26.8 s and 18.9 s on the first two live firings; sim: wall = 2 × budget on a held writer, 90 s at `--timeout 1` with the global store held |
| 768f868 (plan-3 r4 #b-2) | read twins fall through to the replica on `VerbBusyError` (tested on `_SilentDaemon`, 2 s) | the interactive `memory get` (`memory_partition` 10 s × 3 + `_call` 120 s × 3) and the MCP `memory_recall` default `timeout=None` (10 s × 3 + 60 s × 3) on a held writer | 390.4 s and 210.4 s on `_PingOnlyDaemon` before the lock-free replica is read |

## Systemic cause {#cause}

The remedy loop is finding-driven: the implementer edits the line the finding quotes and the test reproduces the state the finding measured. Nothing in the loop enumerates "every command the generator emits on a memory path" and asks the invariant of each. The generator's own docstring lists them (`hooks.py:99-101`: memory recall, ingest-gmd, save-state, focus summarize); the list was never used as a checklist. {#cause-body}

## What closes it {#closure}

- A table in the plan (or the hooks doc) with one row per generated memory-path command: hook event, command, budget, retries, worst-case wall, where it fails loud. Every row filled or the plan is not complete. {#closure-table}
- One deadline helper (`_left()` in `_file_under_active_subject`) reused by every hook-mode CLI path instead of per-call timeouts. {#closure-helper}
- ch-bsd: on every plan-2 round, time every generated command against `_PingOnlyDaemon`, not the ones the last finding named. {#closure-audit}
- r6 addendum: the bound must be placed where the seconds GO, not where the finding's diagnosis pointed — decompose the command (`--no-rerank`, `RMX_RECALL_REPLICA_FIRST=0`, per-leg timers) before choosing the call to budget; a leg that is not a daemon RPC (model worker socket, in-process replica read, hub) is still a leg. {#closure-decompose}

rel: contradicts -> [[plan-2-hooks-reproducible#q4]]
