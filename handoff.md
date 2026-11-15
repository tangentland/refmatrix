---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-15 early (session 070141d0, "refmatrix-08"). **0.83.0 is deployed** (deploy tree
`2aab81a`, daemon pid 21151, hub pid 21506, fleet on 0.83.0). **0.83.1 is in its last fold**
(L114) and ships when green-216 reports (the user's standing order). **Plan-29 and plan-30 are
both approved.** Prior handoff archived at
`workflow/past_handoffs/023-0830-deployed-paused_2026-11-14.md`.

rel: supersedes -> [[handoff-023-0830-deployed-paused]]
rel: depends-on -> [[plan-review-2026-11-13]]
rel: depends-on -> [[agent-briefs-inflight-2026-11-15]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[plan-30-materialisation]]

## Active goal {#active-goal}

No active `/goal`. Standing user order: **"ship 0.83.1 when green-216 reports"** (merge →
release → deploy → backup → forced reingest → AC-6 recount). The live forced reingest runs only on
the deploy carrying L112 S1 (else a ~17 min store-lock hold).

**Agents at save time** — full brief in `workflow/agents/inflight-2026-11-15.md`:

| agent · type | clone (`/Volumes/littlebig/…`) · branch | base · tip at save | expected artifact |
|---|---|---|---|
| `green-216` · ch-implementer | `refmatrix-bug241` · `task-bug241-rule-docs-gmd-on-reingest` | `78c0c11` · `bba7313` (+ uncommitted summary; branch full suite running, `bug241-l112-full.log` ~58% at 18:17 PST) | suite E lines vs baseline; L114 GREEN on red-216's `111e4b0`; mutations; report |

Idle and done (addressable, nothing owed): red-216 (L114 RED `111e4b0` in `refmatrix-bug241-r2`),
bsd-216 (0.83.1 r1/r2), spec-30 + bsd-plan29 (plan-30), spec-29-7 (stopped, 29.7 dropped),
perf-bitmap. green-216 may miss its own run ending — tail the log
(`feedback_check_the_log_when_an_agent_idles_on_a_background_run`).

## What this session did {#did}

- **IMPRESSIONS fold** (`e7f1c8e`), bug-242 (truncated ledger bullets), bug-130 seen 2.
- **Plan-29 approved** (`b12724d`, L107-L111): specs 29.1-29.6 merged after ch-bsd r2-r4. User:
  **D19 confirmed** (store stays a module, L113); **D23 = (a) accept the recorded loss** (L115)
  after a read-only count: 3 attached learned rows + 1 protected entity on `cli.py`/`store.py`;
  15,965 already orphaned by bug-107 (`workflow/measurements/learned-rows-cli-store-2026-11-14.md`).
  Task 29.7 (re-key op) specced then dropped; branch `spec-29-7-learned-rekey` @ `a63d120` unmerged.
- **Bitmap materialisation measured** (perf-bitmap, read-only copy; `0a9ee08`,
  `workflow/measurements/bitmap-materialisation-2026-11-14/`).
- **Plan-30 approved** (`df75516` merge, `ce8141e`, L116-L117): adjacency + bitmap
  materialisation, 30.0-30.5, three releases (A 30.5; B 30.1-30.3, re-derives pagerank fleet-wide;
  C 30.4 daemon-held adjacency + `ppr_rank` op). User: D1 bounded-behind, D2 go, D3 move-not-delete.
  29.1's `sched-track` rule now accepts `P<n>`.
- **0.83.1 reviews:** ch-bsd r1 DIRTY 0B/2S/2M (L112 folded: GMD pass yields, failed GMD pass
  counted + `Error:`, file refusal before `_store`, `--source` docs); r2 MEH-only GO (L114: per-doc
  yield cadence, MCP job `error`). Branch full suite at `13ffd77`: 3 failed = baseline by E line.
- **Bugs logged:** bug-243 (hook PPR rebuilds adjacency per prompt → 30.4), bug-244 (list-valued
  frontmatter `id:` fails the whole GMD batch), bug-245 (self-caught GREEN regression), bug-246
  (`BitMap64` `len()` as emptiness guard → 30.5), bug-247 (log rebuild resurrects purged evidence),
  bug-248 (transaction rollback leaves log events + bitmap bits).
- **Memories:** `project_0831_ship_plan30_state`,
  `feedback_check_the_log_when_an_agent_idles_on_a_background_run`.

## Next {#next}

**The queue lives in the POP only:** [[plan-of-plans#queue]]. Ledgers: [[plan-of-plans#ledgers]]
(L125-L162 this session). Procedure: [[orchestration]]. 0.84.0 is deployed; nothing deploys
until R1's major release gate.

## Open {#open}

- **Agents in flight:** [[agent-briefs-inflight-2026-11-15b]] (green-t02, red-t03, green-t03,
  red-315, green-315). Check each one's queued test log yourself.
- **Questions:** none open (next id Q42).
- **Not pushed:** dev master is far ahead of `origin/main` (the user pushes).
- **Throwaway clones on `/Volumes/littlebig`:** many `refmatrix-*` clones from 2026-11-13..15;
  remove when no longer wanted (look first). Scratch store copies:
  `refmatrix-spec31b-scratch/`, `refmatrix-t56-fresh/.scratch/`.
- **User action pending (bug-261):** add `.refmatrix/` to atlftpd's `.gitignore`; merge the
  ignore branches in cliquet, atldb, prep_prolific.

## Resume {#resume}

1. `/recall-state`; read [[plan-of-plans#queue]] and [[plan-of-plans#ledgers]] (the state), then [[agent-briefs-inflight-2026-11-15b]].
2. `ListAgents`; collect agents in flight or re-dispatch from `workflow/agents/`.
3. Never run the dev-venv `rmx` against the live store with a bumped version.
