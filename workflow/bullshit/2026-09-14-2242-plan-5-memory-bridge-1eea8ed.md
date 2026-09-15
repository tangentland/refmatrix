---
gmd: "0.1"
id: bsd-plan5-memory-bridge-1eea8ed
title: "ch-bsd — plan-5 memory bridge round 1: four live bridge runs wrote the catalog in-process under a busy daemon, then the ART index corrupted; MEMORY.md is now a memory"
severity: BULLSHIT
plan: plan-5-memory-bridge-complete
task: task-5.1-plan-5-memory-bridge-complete, task-5.2-plan-5-memory-bridge-complete, task-5.3-plan-5-memory-bridge-complete
tags: [bsd, plan-5, memory-bridge]
---

# ch-bsd findings — plan-5 memory bridge complete (round 1) {#root}

**Commit range:** 191e510..1eea8ed (task commits 3039d2e / c4e3707 / 4b0a08c, merges ea0dd35 / f8d0eef / 1eea8ed; the lead's `ebdd9c7..1eea8ed` only covers task 5.3 — 8469632 in between is the plan-1 r5 remedy)
**Date:** 2026-09-14 22:42
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 14 (src: cli.py, daemon.py, ingest_gmd.py; tests: test_memory_bridge.py, test_memory_recall_widen.py, test_save_state.py; docs/registry/plan bookkeeping)
**Deploy:** `~/refmatrix` at 1eea8ed (ff 22:28:59), `~/bin/rmx` 0.69.1, daemon pid 58440 imports `~/refmatrix/src` (crash-restart 22:34:47, NOT a relaunch — see #b-1)

rel: evidence-for -> [[plan-5-memory-bridge-complete]]
rel: derives-from -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[bsd-impressions]]

## What is real {#real}

Reproduced on scratch copies of the committed tree (PYTHONPATH-pinned; mutation c below proves the scratch code reaches the spawned daemon):

- Stem id rule is load-bearing: `memory_ids=as_memory` → `False` fails `test_bridge_ingests_gmd_and_plain_files` + `test_sync_disk_is_the_bridge` (2 failed).
- Lenient parse on the daemon path: `ingest_gmd_paths` computes `lenient or as_memory` itself, so a plain `.md` becomes a `curated` memory through the daemon's `ingest_gmd` body and the in-process fallback alike (scratch probe + live `MEMORY` row, `gmd_version: lenient`).
- Unparseable files are counted and named in the report and lifted into `_sync_memory_dir`'s result (scratch probe: `skipped_unparseable: 1` + path).
- The wait path is real on a live job: same-target job → its report, `waited=True`, `waited_job=<id>`; other-target job → own ingest after; 0.2 s budget → named error (5.2 tests, real 350-file jobs).
- `sync-disk` walker deleted (−129 lines), alias routes through `_sync_memory_dir`; README + ARCHITECTURE updated.
- 5.3 tests run `finalize_save_state` against a spawned daemon and read the row back; the lambda is gone; registry row graduated.
- Plan status honest: plan `in-progress`, plan-of-plans `in-progress`, tasks `complete`.

## Findings {#findings}

### BULLSHIT: the bridge under an alive-but-unresponsive daemon opens the writer slot in-process — four live runs did exactly that and the daemon fast-exited on a corrupted ART index {#b-1}

**File:** `src/refmatrix/cli.py:8386` (`_ingest_gmd_sync`: `if daemon_mod.ping(root):` else `_store()`), `src/refmatrix/cli.py:_store` (bare `ping` → `_store_rw()` direct writer), `src/refmatrix/cli.py:10500` (`memory_sync_disk` → `_sync_memory_dir`)
**What:** Task 5.2 makes the bridge survive the overlap the daemon *reports* ("ingest already active"). The overlap that happened live is the other one: daemon alive, not answering ping. `_ingest_gmd_sync` gates on a bare `ping`, falls to `_store()`, which gates on a bare `ping` again and returns a direct read-write `Store` on the active slot. The 5.1 rewrite of `memory sync-disk` deleted that command's own `daemon_up` gate and routed it into the same path.
**Why it's bullshit:** Live timeline from `.refmatrix/cli.log`, `rmxd.log`, `facts.log`, `daemon.stderr.log`:

| time | event |
|------|-------|
| 22:02:13 | daemon pid 30867 starts (code = 7b35e80, pre-plan-5) |
| 22:19:47 | last daemon log line before the crash |
| 22:28:59 | `~/refmatrix` ff → 1eea8ed (daemon NOT relaunched) |
| 22:30:11 | `ingest-gmd --as-memory <memdir>` exit 0, 8.4 s — **no ingest job in rmxd.log** |
| 22:31:22 / 22:33:48 / 22:34:04 | `memory sync-disk` ×3, exit 0, ~7.4 s each — **no ingest job in rmxd.log** |
| 22:31:28 / 22:33:54 / 22:34:10 | `facts.log`: `entity` + `memory_content` writes for `MEMORY` (three times) |
| 22:31–22:35 | `rmx daemon status` / `memory get`: "daemon busy pid=30867 (alive, not answering)" |
| 22:34:45 | daemon: `watch flush failed: FatalException('Corrupted ART index - likely the same row id was inserted twice into the same ART')` → fast-exit |
| 22:34:47 | pid 58440 respawned by launchd (`repaired idx_entity_links_lk_concept rows=303408`) |

Every daemon-run GMD ingest logs `ingest-progress` per file (see job 961a8791ca36 at 20:48, 209 lines). Four bridge runs over 209 files logged nothing → all four took the in-process branch and wrote `catalog.B.duckdb` directly while pid 30867 was alive. Two writers on one catalog is the documented origin of "same row id inserted twice" (memory: `project_daemon_index_drift_recurrence`, impressions `imp-index-drift`). The same shape is on record in `daemon.stderr.log` lines 74/153: daemon boots refused the slot because a CLI Python process (PIDs 24340, 19547) held the lock.

This is the fourth sighting of busy≠absent on a bare `ping` gate (plan-2 r2 `--detach`, plan-2 r3 `focus summarize`, plan-3 r2 `verbs._call`/`federated_locate`); the impressions ledger says "BULLSHIT on sight" and "grep the diff's file for every other `if daemon_mod.ping(root)`" — `_ingest_gmd_sync` is in this diff and `memory_sync_disk` was rewritten around it. It also violates CLAUDE.md "NEVER open `Store()` directly on a live `.refmatrix/`".
**Evidence:** `RMXGREP_MODE=plain grep -c "T22:3[0-3].*ingest-progress" .refmatrix/rmxd.log` → 0; `cli.log` lines 26906, 26967–26970, 27038–27046, 27055–27059; `facts.log` `"name": "MEMORY"` ×12 rows at 1789450288/1789450434/1789450450; `rmxd.log` lines 9054–9057.
**Fix:** `_ingest_gmd_sync` (and `_store(write=True)`) classify the daemon with `discovery.daemon_status(root)`: `up` → RPC; `busy` → return a named `error` ("daemon busy pid=N; bridge skipped, next save-state/SessionStart retries") and NEVER open the slot; only `absent` (no pid, no socket) → in-process. The bridge's own test needs the silent-socket simulation (`_SilentDaemon` from plan-2 r4) proving `_sync_memory_dir` returns `error` without touching `catalog.*.duckdb` (mtime unchanged). Relaunch the fleet on 1eea8ed for real — pid 58440 is a crash respawn, and `hub status` should say so.
**Pattern match:** YES — `imp-busy-absent-verb-layer` (4th), `imp-index-drift` (5th), `imp-fix-at-quoted-line`, `imp-two-paths`.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[feedback_store_calls_via_daemon]]

### BULLSHIT: MEMORY.md — the flat index — is now a curated memory in the live store {#b-2}

**File:** `src/refmatrix/ingest_gmd.py:783` (`parse_gmd(..., lenient=lenient or as_memory, memory_ids=as_memory)`), `src/refmatrix/ingest_gmd.py:collect_gmd_files` (`*.md` rglob, no exclusion), `tests/test_memory_bridge.py:62` (seeds `MEMORY.md`, asserts nothing about it)
**What:** Q1 chose "lenient parse: one bridge, one identity rule". The walker it deleted carried `if path.name == "MEMORY.md": skipped … "index file (MEMORY.md)"`. The replacement has no exclusion, so the only non-GMD file in the live memory dir (219 files, 1 non-GMD — the "21" from the e2e report has since been backfilled) became a memory: live `rmx memory get MEMORY` → `id=3171951 mtype=curated`, source `ingest_gmd_as_memory`, `gmd_version: lenient`, body = the 200-line index. MEMORY-RULES: "NEVER reference `MEMORY.md` as a node — it is a flat index, not graph-addressable." An index that names every memory title is also the worst possible BM25/dense neighbour for every recall query.
**Why it's bullshit:** Cheap fix / scope shrunk: the exclusion existed, the rewrite dropped it, and the covering test seeds exactly that file and never asserts it is skipped or counted — a mutation that ingests MEMORY.md (the shipped behaviour) passes.
**Evidence:** `~/bin/rmx memory get MEMORY` (above); scratch probe on a tmp Store: `MEMORY row: MEMORY curated`; `git show 3039d2e -- src/refmatrix/cli.py` lines `-        if path.name == "MEMORY.md":`.
**Fix:** The bridge skips index files by name (`MEMORY.md`, and anything the memory rules mark as index) and COUNTS them (`skipped_index: 1`, named); `test_bridge_ingests_gmd_and_plain_files` asserts `_get(root, "MEMORY") is None` and `skipped_index == 1`; the live row `MEMORY` (id 3171951) is forgotten after the fix deploys.
**Pattern match:** YES — cheap-fix rule 10 (interface narrowed / scope shrunk), `imp-existence-check-tests`.

rel: contradicts -> [[project-profile#constraints]]

### SKETCHY: the wait path takes ANY finished job over the memory dir as the bridge's report — a plain doc ingest counts {#s-3}

**File:** `src/refmatrix/cli.py:_bridge_wait_for_active_job` (`covered = any(me == t or me.startswith(...))`)
**What:** Coverage is decided on `args.targets` only; `args.as_memory` and `args.partition` are in the job record and ignored.
**Why it's sketchy:** Probe on a spawned daemon: `ingest_gmd_start` over `memdir` with `as_memory=False, partition="proj"`, then `_sync_memory_dir(memdir)` → `error: None`, `waited: True`, report "ingested 350 doc(s)", and `memory_get("memory_doc0001")` → None. The bridge reports success with zero memory rows: a silent failure on a memory path. Realistic trigger: a hand `rmx ingest-gmd <memdir>` (no `--as-memory`) or a `-p` override racing the SessionStart catch-up.
**Evidence:** scratch `tests/test_probe_coverage.py` output: `OUT: {... 'error': None, 'waited': True, 'waited_job': '11ccd7780096'}` / `memory_doc0001 as memory row: False`.
**Fix:** `covered` requires `args.as_memory` truthy AND `args.partition == partition` in addition to the target match; otherwise fall through to "run our own once the slot is free" (already written). Add the probe as a test.
**Pattern match:** YES — `imp-silent-memory` (success reported, nothing landed).

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY: `memory sync-disk --mtype` is a dead flag and the docstring describes the deleted walker {#s-4}

**File:** `src/refmatrix/cli.py:10446–10472`
**What:** `--mtype/default_mtype` is still declared and documented ("mtype assigned to memories whose frontmatter does not carry `metadata.type`") and never read: `_sync_memory_dir` has no mtype parameter, `_ingest_gmd_sync` defaults `memory_mtype="curated"`. The docstring still promises `name` as an id fallback, `metadata.title` stashing, `source_mtime`, and a `--dry-run` that now raises.
**Why it's sketchy:** `rmx memory sync-disk --mtype feedback <dir>` silently files everything as `curated`. Second dead-flag sighting (plan-2 `--enforce`) → escalated MEH→SKETCHY.
**Evidence:** `RMXGREP_MODE=plain grep -n default_mtype src/refmatrix/cli.py` → declaration + signature only.
**Fix:** Either thread `memory_mtype` through `_sync_memory_dir` → `_ingest_gmd_sync`, or drop the option and rewrite the docstring to the three lines that are true (alias, deprecated, runs the bridge).
**Pattern match:** YES — `imp-dead-flag` (2nd).

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY: `skipped_non_gmd` can never be nonzero on the bridge path, and no test fails when the counter or the daemon's `lenient=` arg is deleted {#s-5}

**File:** `src/refmatrix/ingest_gmd.py:793`, `src/refmatrix/daemon.py:2865`, `tests/test_memory_bridge.py:70` (`assert "skipped_non_gmd: 0"`)
**What:** With `as_memory=True`, `parse_gmd(lenient=True)` never returns None, so `skipped_non_gmd` is 0 by construction on every bridge run; the headline counter of #bs-1 reports a number that cannot move. The daemon body's new `lenient=bool(args.get("as_memory"))` is redundant with `lenient or as_memory` inside `ingest_gmd_paths`.
**Why it's sketchy:** Mutation a (delete `stats.skipped_non_gmd += 1` AND the daemon `lenient=` line): `tests/test_memory_bridge.py` + `test_ingest_gmd_root_rel_mirror.py` + `test_sync_gmd_routing.py` + `test_save_state.py` → 37 passed. The strict-mode counter (where it CAN count) has no test at all; the bridge test's `skipped_non_gmd: 0` assertion is an existence check on a constant.
**Evidence:** scratch log `m-a.log`: `37 passed, 3 deselected`.
**Fix:** One strict-mode test: `ingest-gmd docs/` over a dir with one plain `.md` asserts `skipped_non_gmd: 1`. Drop the redundant daemon kwarg or make `ingest_gmd_paths` stop deriving it (one place decides). If #b-2's `skipped_index` lands, the bridge report has a counter that can actually move.
**Pattern match:** YES — `imp-existence-check-tests`.

### SKETCHY: new deferral — "kept as an alias for one release" / Q2 "delete in 0.68" — the deploy is 0.69.1 and nothing schedules the deletion {#s-6}

**File:** `src/refmatrix/cli.py:10477`, `workflow/plans/plan-5-memory-bridge-complete.md` Q2
**What:** The alias is deferred to a release that already shipped before the alias was written (pyproject `0.69.1`). No task spec under `workflow/plans/plan-5-memory-bridge-complete-tasks/` covers removal; `workflow/deferral_registry.md` has no row.
**Why it's sketchy:** Rule 9 — a new deferral in the diff (SKETCHY on first occurrence) whose target is not concrete (rule 9a: "one release" names no plan/task; "0.68" is in the past).
**Fix:** Either delete the alias now (the walker is already gone; the alias is 30 lines) or file a deferral-registry row naming the release/task that removes it, and fix Q2's number.
**Pattern match:** YES — `imp-registry-row-deferral`.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY: `waited` / `waited_job` are written for "save-state and MCP" and rendered by nothing {#s-8}

**File:** `src/refmatrix/cli.py:8475–8476`, `src/refmatrix/cli.py:10934–10943` (save-state print block), `src/refmatrix/cli.py:10500–10506` (sync-disk print block)
**What:** Both CLI renderers print `error` or `report` only; a bridge that took another job's report prints as if it ran. `verbs.save_state` passes the dict through, so MCP callers can read it; no CLI user can.
**Why it's sketchy:** Third sighting of a diagnostic key with no reader (`identity_error` r3, `filed_subject_error` r4) → escalated. Not BULLSHIT: an actual failure still reaches `error`, which IS printed.
**Fix:** One line in each renderer: `waited for ingest job {id}` when `waited`.
**Pattern match:** YES — `imp-unread-diagnostic-field` (3rd).

### MEH: `_parse_bridge_report` misfiles `unresolved refs` lines as unparseable files {#m-7}

**File:** `src/refmatrix/cli.py:_parse_bridge_report`
**What:** When `skipped_unparseable > 0`, every report line that starts with two spaces and contains `": "` is treated as `path: error` — the `unresolved refs` block (`  path:line: [[ref]]`) matches. Probe: 1 unparseable + 2 unresolved → 3 entries. The docstring says callers get the counters "without scraping text"; the function scrapes text.
**Fix:** Put `skipped_non_gmd` / `skipped_unparseable` on the daemon result dict (next to `docs`/`nodes`/`unresolved`) and on the in-process return, and read them structurally.

### MEH: bookkeeping — todo G4 stale, registry file list, live requirement proved by the old walker's row {#m-9}

- `docs/architecture/todo.md:29` G4 still `Planned … plan 3`; it is plan 5 and shipped.
- `workflow/test_mock_registry.md:31` `cli._root` row lists neither `tests/test_memory_bridge.py` nor `tests/test_memory_recall_widen.py` (both patch it via fixture).
- Task 5.1's live requirement (`rmx memory get feedback_no_silent_failures` resolves) is met by a row whose meta says `source: memory_sync_disk` — written by the deleted walker in plan-1 r3, skipped unchanged by the bridge's hash gate. It proves nothing about plan-5 code; the only row plan-5 code created live is `MEMORY` (#b-2). Also: the deploy tree was fast-forwarded at 22:28:59 but the daemon that served the 22:30 run started 22:02:13 — "fleet relaunched" had not happened when the live check ran.

## Environment note (not a plan-5 finding) {#env}

The 22:34:45 ART corruption is the fifth index-drift incident in the ledger. Plan 4 task 4.2 repaired `idx_entity_links_lk_concept` on the respawn; the root cause (#b-1: a second writer) is a plan-5 path. Do not run the bridge from a CLI until #b-1 is fixed unless `rmx daemon status` says `running`.

## Verdict {#verdict}

**DIRTY — 9 findings (2 BULLSHIT, 5 SKETCHY, 2 MEH).** Plan-5 may NOT flip to `completed`.

Blockers: #b-1 (bridge writes the live slot in-process under a busy daemon — reproduced by the live incident), #b-2 (MEMORY.md ingested as a memory — live row 3171951). Fix both, add the silent-socket bridge test and the index-exclusion assertion, relaunch the fleet on the fixed sha, then re-review. #s-3 should land in the same remedy (same function, same probe).

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[feedback_store_calls_via_daemon]]
rel: contradicts -> [[project-profile#constraints]]
