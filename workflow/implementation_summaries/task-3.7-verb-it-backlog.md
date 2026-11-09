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

## Remedy round 1 {#remedy-r1}

rel: implements -> [[task-3.7-verb-it-backlog#remedy-r1]]
rel: derives-from -> [[bsd-plan3-task37-impl-41c3568]]

Decisions from the spec's [[task-3.7-verb-it-backlog#remedy-r1]] table (`6fd9b7c`); RED
`56a5815` (`red-remedy-r1.log`). {#remedy-r1-lead}

| row | GREEN commit | what changed |
|-----|--------------|--------------|
| R-B2 | `68df326` | `discovery.resolve_partition` (flag → `$RMX_PARTITION` → marker → store name), shared by `cli._resolve_partition` and `verbs.project_partition`; `rmx_focus` takes `partition` |
| R-S1, R-RM1, R-RM2, R-RM4, R-H1 | `7e20c4a` | link / unlink / canon link send names, and the ops resolve them under the writer; `ann_search` takes a store getter resolved in the lock; `graph_recall` uses `d.partition`; canon link uses `_matrix_write`; one embed client per process |
| R-B1, R-M2, R-OBJC, R-L (fsync) | `cae4373` | hooks run `curator status` without `--drain`; `--drain` drains only fully-printed files; raw-path legacy lines are `reason: legacy`; `HOOK_ENV` exports the fork-safety env; `write_spool` fsyncs the directory |
| R-RM5, R-RM6, R-RM7, R-L | `c29b4b6` | forget preview 600 s; taxonomy OSError named; dead code deleted (except `cli._concept_files`, which tests/test_concept_timeline.py imports); one `session_title`; `session show` refuses an ambiguous prefix; hints; the `--via-replica` deprecation warning |
| R-M1 | `364a90e` | bug-155 / bug-156 (base failures, open); bug-157..160 (fixed) |
| R-L (test), R-RM7 (alias) | `1df6c25` | the spool test asserts file fsync → rename → dir fsync, each fsync identified by `fstat` (three mutations RED); `tests/test_concept_timeline.py` imports `graphread.concept_files`, and `cli._concept_files` is deleted |
| R2-S1 (remedy r2) | `4643541` | `_process_embed_client` drops a handed-out hub-shared client that reports `alive()` False (the hub died), closes it, counts it in `_EMBED_CLIENT_REBUILDS`, logs it, and builds a fresh client (a private worker while the hub is down). A private worker is never rebuilt. One atexit closer for the cached client (bug-171; RED `0359858`) |
| R2-M1, R2-M2, R2-M3 (remedy r2) | `c47f79f` | `curator status --drain` prints a counted stderr notice for every spool file it keeps (`kept N spool file(s) ... --limit`). The gmd-curator template and the repo copy no longer say a hook drains. A non-JSON spool line counts as a legacy path only if it is path-shaped (no whitespace, and it has a `/` or a suffix); any other line is counted as unparseable (RED `8961c9c`) |
| S-1, M-1, M-2 (remedy r3) | `e60033e` | `recall.reprobe_shared_client` is the ONE hub re-probe + backoff (`RMX_SHARED_REPROBE_S` / `_MAX_S`), used by `Daemon._maybe_adopt_shared` (swap only) and by `_process_embed_client`, which re-probes while its client is private and swaps + retires the private worker when the hub answers. Without an injected `log` the rebuild notice (`rebuild #N`) and the in-process fallback notice go out at WARNING on `refmatrix.recall` (stderr via lastResort). `_embed_client_is_dead` drops the `_EMBED_CLIENT_ISSUED` conjunct, and the global is gone: `3670f35` dropped the r1/r2 rigs' resets of it and `b0cc89b` deleted it (corrected per ch-bsd r3 #m-2; this row first said it stayed unread). bug-173 (a private worker that cannot spawn loads a fresh in-process `Embedder()` on every daemonless call), first parked here as open, is fixed in remedy r4 (ch-bsd r3 #b-1; RED `4e46ca0`) (bug-171; RED `d02739e`) |
| B-1, S-1 (remedy r4) | `d093f65` | bug-173: a daemonless worker that cannot serve gets ONE in-process model, cached as the stand-in for the cached client (`_load_process_inproc_standin`) and dropped when the hub is re-adopted or the client is rebuilt. A build that went private SETS the re-probe throttle (`hold_reprobe`). The request-path re-probe runs outside `_EMBED_CLIENT_LOCK` behind `_EMBED_REPROBE_INFLIGHT` and is bounded by `modelsrv.REQUEST_PROBE_TIMEOUT_S` (`RMX_SHARED_REQUEST_PROBE_TIMEOUT_S`, 1.0 s) via `reprobe_shared_client(probe_timeout=)`. The daemon keeps `PROBE_TIMEOUT_S`. r4 8/8; related 329 passed; full suite 2 failed (bug-155/156), 3721 passed. M11 killed. The in-flight check survives mutation (spec `#remedy-r4-green`) (RED `4e46ca0`) |
{#remedy-r1-table}

Behaviour changes users will see:
- The prompt / session-start curator line no longer drains. It keeps showing the count
  until the gmd-curator runs `drain --token`.
- `rmx -p X focus composite` reads X.
- An `add concept` followed at once by `link` works on a live daemon.
- `session show <ambiguous prefix>` exits 1 with "matches N sessions".
- `--via-replica` on neighbors / describe prints a deprecation note.
- Hook commands export `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` and
  `TOKENIZERS_PARALLELISM=false`, so a hook-run `rmx` does not re-exec on macOS.

Deploy adds nothing beyond the steps in [[#deploy]]: `rmx install-hooks --apply`
re-applies the changed hook commands. {#remedy-r1-behaviour}

### Remedy r1 verification {#remedy-r1-verify}

- **Targeted set** (`green-remedy-r1-1.log`): all task3_7 files, test_refine_cli,
  test_verb_parity, test_task3_6_r9_remedy, test_docs_generated, test_hooks and
  test_concept_timeline gave 505 passed, 1 failed. The failure is
  `test_task3_7_curator.py::test_write_spool_is_tmp_fsync_rename_and_never_visible_half_written`.
  It pins the os-level events to exactly `["fsync", "rename"]`, while R-L adds the
  directory fsync after the rename. This is a test conflict with the R-L decision,
  routed to the test engineer.
- **Full suite** (`suite-remedy-r1.log`): 3694 passed, 6 failed.
  - Three are the known failures: bug-155, bug-156 and `test_watch` (bug-091).
  - One is the fsync conflict above.
  - `test_plan4_remedy::test_graceful_stop_on_a_live_daemon_returns_quickly` is a load
    flake. Stop waits for the model warm-up in both trees; alternating samples measured
    HEAD 5.06–5.32 s vs 591a2fb 5.25–5.69 s against an 8 s bound
    (`r1-stopprobe-samples.log`).
  - `test_task21_1_used_events::test_ac11a_memory_get_by_name…` is a cold-start flake.
    Run alone it fails identically at 591a2fb ("fixture: recall did not deliver: []",
    `r1-ac11a-bisect2.log`). It passes when another daemon test warmed the models first.
- The spec status stays `in-progress` until the fsync test conflict is resolved.
{#remedy-r1-verify-list}
