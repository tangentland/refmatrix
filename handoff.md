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

1. Collect green-216 (or re-dispatch from the briefs file); check its L114 mutation table.
2. **Ship 0.83.1:** merge `--no-ff` → bump `pyproject.toml` + `__init__.py` → full suite on master
   (log, E lines vs `release-0.83.0-full.log`) → deploy (ff, `daemon restart --relaunch`,
   `version -v`, `relaunch-fleet`, hub stop + ONE kickstart if stale, `install-hooks --check`) →
   back up `catalog.read.duckdb` + `facts.log` + `active` → `rmx reingest --force --no-sessions` →
   `scripts/check-rel-landing.py` until `claude` / `project-profile` unresolved = 0.
3. `.venv-eval` duckdb → 1.5.3 (L106).
4. **Plan-29:** 29.1 → 29.4 → 29.5 (ADR 0006 first; store event with D23 = (a)) → 29.2 ∥ 29.3 → 29.6.
5. **Plan-30** after plan-29.
6. Unowned: bug-107 (28,164 orphaned learned evidence rows, 26%), bug-244, bug-247, bug-248; a
   `legs_ms` task, a cross-partition `rel:` probe, linked-store usage (L106).

## Open {#open}

- **Questions:** none open (next id Q23). No plan decision open.
- **Not pushed:** dev master ~380 commits ahead of `origin/main` (the user pushes).
- **Throwaway clones on `/Volumes/littlebig`:** `refmatrix-bug212-mut4`, `bsd216-r3..r6`,
  `bsd230-r1`, `refmatrix-bsd241-r1`, `refmatrix-bsd30-r1`, `refmatrix-plan30`,
  `refmatrix-spec-29-7`, plan-29 spec clones; remove when no longer wanted (look first).
- **curator queue:** 46 files pending a gmd-curator pass.

## Resume {#resume}

1. `/recall-state`; read this file, `workflow/agents/inflight-2026-11-15.md`, memory
   `project_0831_ship_plan30_state`.
2. `ListAgents`; collect green-216 or re-dispatch.
3. Never run the dev-venv `rmx` against the live store with a bumped version.
