---
gmd: "0.1"
id: impl-summary-task-3.7-verb-it-backlog
title: "Implementation summary — task 3.7: the verb-it backlog (49 paths, 45 verbed, 4 re-decided)"
tags: [implementation-summary, plan-3, task-3.7, verbs, parity]
metadata:
  node_type: implementation-summary
  task: task-3.7-verb-it-backlog
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 3.7 — implementation summary {#root}

rel: implements -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bsd-plan3-task37-spec-7d6c418]]
rel: derives-from -> [[bsd-plan3-task37-spec-r2-15232c5]]
rel: derives-from -> [[bsd-plan3-task37-spec-r3-090eb5e]]
rel: derives-from -> [[bsd-plan3-task37-spec-r4-1c501a4]]
rel: derives-from -> [[bsd-plan3-task37-spec-r5-925f121]]
rel: derives-from -> [[bsd-plan3-task37-spec-r6-5fc593e]]

Every one of the 49 `verb-it` CLI paths is either the twin of a verb or re-decided into
another category, with the reason checked against the code. The `verb-it` category is
gone, and `LEGACY_UNPAIRED` went 140 → 92. Eight MCP tools are new, and `rmx_focus` gained
an `action`. Built in one clone (`/Volumes/littlebig/refmatrix-task-3.7`, branch
`task-3.7-verb-it-backlog`) in three batches, each RED (ch-test-engineer) before GREEN
(ch-implementer). {#lead}

## Batches {#batches}

All logs are under `workflow/review-output/task-3.7/`. {#batches-lead}

| batch | RED | GREEN commits | GREEN logs |
|-------|-----|---------------|------------|
| A — infra, focus, curation, taxonomy, curator, R52, R53 | `a4cb9df`, `91f221d`; `red-batch-a.log` | `d21c1b4` infra, `8e01d11` focus, `1085cf6` curate / taxonomy / curator, `fd83733` R53, `c148bea` maps, `c736a11` bugs, `2bc1405` R53 follow-up | `green-a-3.log` (294 passed), `suite-batch-a.log` |
| B — graph-read, canon | `ef6925a`, `31c06f9`, `ab9dfe5` (spec decision `b12c0ed`); `red-batch-b.log` | `05a8ce3` embedder seam + `graph_recall`, `08c63cd` rmx_graph / rmx_canon, `a3c5d94` maps, `ee12ebd` bugs | `green-b-final.log` (402 passed), `suite-batch-b.log` |
| C — matrix-edit, session, refine, AC-G1..G6 | `aef4a95`, fixes `eda626a`; `red-batch-c.log` | `c7285a5` op partition + dead ops, `7995a1a` rmx_matrix / rmx_session / rmx_refine, `98fa994` maps, `098dbbb` curator hook stderr, `0de5c72` registries, `cb6fe62` `list_linkages` op removed | `green-c-final.log` (464 passed), `suite-final.log` |

**Final full suite** (`suite-final.log`): 3666 passed, 3 failed, 19 skipped. The 3 failures fail identically at 591a2fb (`final-failures-at-591a2fb.log`; the E lines differ only in the tree path): the GMD lint gate, the AC-6 fixture, and `test_watch` "watcher did not fire" (file events on this host). {#final-suite}

## Shared infrastructure {#infra}

- `verbs.snapshot_read(root, fn, *, partition)` (C3) opens `catalog.read.duckdb`
  read-only for each call and never caches it (bug-136). It refuses a replica that is a
  writer file. A daemon that is up or busy with no snapshot raises `VerbBusyError`
  worded as a read. A truly absent daemon reads the primary read-only in-process.
- `verbs.local_write` (C4a) is the one in-process writer, and runs only on
  `VerbAbsentError`. `_write_or_local` is one classified write (`_call(write=True)`).
- `verbs.ACTION_DEFAULTS` and `action_default` resolve per-action defaults (C6).
- `recall.shared_embedder(root)` is the one embedder seam; `Daemon._embedder` delegates
  to it. `recall.graph_recall` and `recall.ann_search` are each one algorithm, run by the
  daemon op and, with no daemon, in-process by the verb.
- `graphread.py` holds the describe, neighbors, co-occur, top and timeline legs, plus
  the session-card metadata readers.
- `verbs.session_memories` / `session_memory_get` read session cards through the daemon
  ops, or read-only in-process when no daemon exists.
{#infra-list}

## The 49-path decision table, as built {#decisions}

| family | paths | outcome |
|--------|-------|---------|
| focus | tail, topics, show, subject, subjects, clear-subject, composite, detour, detours, return, clear (+ `export`) | actions on `rmx_focus` |
| curation | protect (twin), unprotect, noise, unnoise, forget | `rmx_curate` |
| taxonomy | list (twin), add, remove | `rmx_taxonomy` |
| refine / curator | curator drain (+ `curator status` twin) | `rmx_curator` |
| graph-read | neighbors (twin), co-occur, top, describe, recall, search-dense, concept timeline (+ `stats`) | `rmx_graph` |
| graph-read | pairs show | re-decided `harness` (debug view of `pairs compile`) |
| canon | canon find (twin), siblings, link | `rmx_canon` |
| matrix-edit | add concept (twin), add entity, add linkage-type, link, unlink, list entities, list linkages, list queries, run, save-query | `rmx_matrix` |
| session | session list (twin), recall, show | `rmx_session` |
| session | session stats | re-decided `harness` (reads through the list action) |
| refine | refine list (twin), show | `rmx_refine` |
| refine | refine accept, reject | re-decided `operator` (the human approval gate) |

45 verbed + 4 re-decided = 49. The 48 paths that gained twins (the 45, plus
`curator status`, `stats` and `focus export`) left `LEGACY_UNPAIRED`: 140 → 92. {#decisions-count}

## Bugs {#bugs}

- **Fixed:**
  - bug-139 focus clear wrong ring.
  - bug-140 focus subjects partition / refusal.
  - bug-141 focus composite session.
  - bug-142 taxonomy corrupt-file overwrite and read-writes.
  - bug-143 curator queue parser format.
  - bug-144 curator drain loss / swallow.
  - bug-145 search-dense partition.
  - bug-146 timeline silent passes + session writer-slot open.
  - bug-147 neighbors write accessor.
  - bug-148 add_concept / upsert_entity partition.
  - bug-149 session readers.
  - bug-150 refine list hub `ok:false`.
- **Open (operator paths, logged not fixed):**
  - bug-151 accept KeyError on a gmd-curator candidate.
  - bug-152 reject has no pending check.
  - bug-153 accept writes to `store_name`, not `memory_partition`.
  - bug-154 per-process `hash()` candidate ids.
{#bugs-list}

## Deferral rows resolved (AC-G3) {#deferrals}

Three rows in `workflow/deferral_registry.md` are now RESOLVED, each with a
graduation-log row:
- "The 49 `verb-it` CLI paths".
- "`tests/transport_guard.py` fixed-point loop unpinned by plant order" (R52).
- "Two transport handlers render the raw exception outside the one classifier" (R53).
{#deferrals-list}

## Behaviour changes users will see {#behaviour}

- `rmx focus show N` with an out-of-range line exits 1 (a `VerbArgsError`); before, it
  printed a yellow note and exited 0.
- `rmx focus clear` resolves the session like every STM write (unresolved ⇒ exit 2),
  names the ring it cleared, and gains `-s/--session`.
- `rmx session list --limit 0` now means every card; `session stats` uses it.
- `Store.with_partition` on a read-only store no longer INSERTs the partition row, and a
  missing partition reads as empty (id -1). The one existing caller this changes is
  `cli._derive_status_for` on the no-daemon branch: a partition other than the bound one
  now answers from the snapshot instead of raising a read-only error.
- The curator queue is a spool directory, `.refmatrix/curator.spool/`, with one
  tmp → fsync → rename file per watcher flush. `curator status --json` emits a token;
  `curator drain --token <names|@file>` deletes exactly those files.
  - A pre-3.7 `curator.queue` is adopted into the spool by `status` with one rename.
  - A daemon still on old code keeps appending to the legacy file until it restarts.
- `rmx recall` / `search-dense` with no daemon run in-process and spawn a model worker
  (the hub's shared worker when it is up). In-process dense does not rerank, and says so
  in `warnings`.
- The curator hook segments keep their stderr: `2>/dev/null` is dropped, `|| true` is
  kept.
- Timeline legs that fail or are skipped show up in `warnings`. The CLI prints them on
  stderr, and `--json` carries them.
{#behaviour-list}

## Deploy steps {#deploy}

1. `rmx install-hooks --apply` in each project: the generated curator segments changed
   (`rmx install-hooks --check` is red until then).
2. `rmx daemon restart --relaunch` for every store. That loads the spool writer, the
   startup `*.tmp` sweep, the `graph_recall` op, the op partition fixes and the removed
   dead ops. Release note: an old-code daemon's appends to `curator.queue` stop at its
   restart.
3. `/mcp` reconnect in every client, to load the 8 new tools: `rmx_curate`,
   `rmx_taxonomy`, `rmx_curator`, `rmx_graph`, `rmx_canon`, `rmx_matrix`,
   `rmx_session`, `rmx_refine` (plus the new `rmx_focus` actions).
{#deploy-list}

## Known limits {#limits}

- `rmx_focus` has no `partition` param, because the PAIRING row for `focus context`
  forbids one. Its `composite` action reads `$RMX_PARTITION`, else the store name.
- `composite.build_topic_composite` still falls back to `latest_session` when called
  without a session. The verb always passes the resolved one; `scan-prompt`'s own call is
  unchanged.
- bug-151 to bug-154 stay open on the operator `refine accept` / `reject` paths.
- CLI writers other than `init`, `session ingest` and the derive stamp still hold their
  writer until the process exits. A later read-only open in the same process can then hit
  bug-135's handle conflict; a separate CLI invocation is unaffected.
{#limits-list}
