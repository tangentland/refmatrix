---
gmd: "0.1"
id: impl-task-26.2-bridge-move-safety
title: "Task 26.2 GREEN: the bridge refreshes a moved memory through its recorded source_path, and refuses two files claiming one id"
tags: [implementation-summary, plan-26, bridge, ingest-gmd, memory, identity, move]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# Task 26.2 GREEN: bridge move-safety {#root}

rel: implements -> [[task-26.2-bridge-move-safety]]
rel: implements -> [[refmatrix/adr-0005-memory-dir-layout]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: related-to -> [[task-26.3-savestate-subfolder]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_no_silent_failures]]

## Why {#why}

The bridge's resume gate skipped a memory file when the stored `gmd_content_hash` for its NAME
matched. A file moved with unchanged bytes was skipped, so its row kept `source_path=<old>` and
its `x#anchor` concepts kept `path=<old>`. A later `rmx sync` of the old path then purged those
anchors (AC-5, #rd-ac5-defect). Organising a memdir (26.5) moves every file, so this had to be
fixed before 26.5 ships. The RED group is `27e21dc` + `75cd42e`
(`tests/test_bridge_move_safety.py`, 25 tests). {#why-lead}

## What changed {#changes}

- **One classifier** (`ingest_gmd._memory_gate`) runs in both the bridge and `--dry-run`.
  {#c-gate}
  - Hash-only gate (HEAD's rule): files in an un-organised memdir (AC-3b).
  - Path-aware gate: files whose nearest ancestor has a readable `.memory-layout`
    (`_OrganisedDirs` → `memory_layout.is_organised`), and every `--dry-run`. The file is skipped
    only when the hash matches AND the stored `source_path` is *literally* equal to the resolved
    path (#rd-literal).
  - When the paths disagree, the row lands in exactly one term, chosen by the shape of the
    stored path (r5 m3): a missing or symlink-form path is `stale_before`, any other path is
    `moved`.
  - An unreadable marker is never read as "not organised", and it never fails the ingest. The
    path-aware rule applies there and the problem is named as a `marker_error:` line. This keeps
    26.6's "the memories are SAVED" twins green.
- **AC-1b, one logged write.** {#c-legacy}
  - Every other memory row on a moved file's old path is refreshed by
    `Store.refresh_memory_source_path`. Rows are matched on the resolved old path, and the id
    rows of the current walk are excluded.
  - That call and the id-row `add_memory` run inside one `store.transaction()`.
    `Store.add_memory` now commits through `_maybe_commit`.
  - Each legacy refresh logs a full `memory_content` event that carries the stored
    `updated_at`, which is not bumped, so `rebuild --from-log` restores the new path.
  - The refreshed rows are counted as `moved_legacy`. A lazy `_SourcePathIndex` supplies the
    rows, so an unchanged run pays no scan.
- **AC-4, parse then write.** {#c-dup}
  - Memory files are all parsed before anything is written (`_parse_memory_walk`).
  - `split_claims` refuses an id that two or more files claim, and writes neither file.
  - The refusals are carried by `IngestStats.duplicate_ids`, by `_bridge_stats` (all three
    legs, including the waited job) and by the report line `duplicate_ids: N` with every path.
    `save-state` prints that report.
  - The `savestate_*` top-level/`savestates/` pair (#rd-262-263) never reaches `split_claims`:
    26.3 resolves it in the walk (`memory_layout.iter_memory_files`, spec #ac-4c-combined), so
    no exemption lives in 26.2. The combined AC-4c test belongs to whichever of 26.2 / 26.3
    merges second.
- **AC-3, the measurement.** `rmx ingest-gmd --as-memory --dry-run` calls
  `plan_memory_refresh`, which only reads the store. It prints `refresh_pending` and the four
  terms. {#c-dry}
  - `--store-snapshot F` opens a copied catalog in-process and read-only. The branch runs
    before `_root()`, so there is no `daemon_mod` call and no hub contact. It needs `-p`, and
    that partition must exist in the copy.
  - `--path-map FROM=TO` rewrites stored paths before they are compared.
  - Misuse is refused: either flag without `--dry-run`, a dry-run without `--as-memory`, or a
    dry-run combined with `--prestage`/`--detach`.
- **Two supporting fixes, both found by the RED group.** {#c-support}
  - `_write_content_hash` writes nothing when the marker is already current. Before, it bumped
    `entities.updated_at` on every pass-2 run, which re-staled the vector of a moved, unchanged
    file (`vectors_updated_at` moved).
  - The daemon-down `_ingest_gmd_sync` now closes its writer, the same pattern as the session
    ingest in task 3.7. The open writer had kept DuckDB's lock and an un-checkpointed WAL for
    the whole life of the process (save-state from the MCP server), so a copied catalog was
    missing the rows just written.

## Verification {#verify}

- RED file: 25/25 (`workflow/review-output/plan26/26.2-green.log`).
- Family (`test_bridge_move_safety`, `test_memory*`, `test_ingest_gmd*`, `test_save_state*`,
  `test_bug111*`, `test_sync*`, `test_verb_parity`, `test_docs_generated`): 645 passed
  (`26.2-green-family.log`). The first family run caught the two 26.6 unreadable-marker twins;
  they are fixed by the non-fatal marker rule in [[#c-gate]].
- Full suite: `26.2-green-full.log`.
- Mutations: 9 run, 9 killed, each restored in its own command (`26.2-mutations.log`).

| mutation | killed by |
|---|---|
| gate never path-aware (marker ignored → hash-only) | AC-1 in-process, AC-1b |
| gate always path-aware (marker ignored → on) | AC-1b marker-off twin |
| gate drops the path term | AC-1, AC-3 missing path, AC-3 dry-run |
| duplicate check dropped | AC-4 in-process, AC-4 stats |
| waited-job result drops `duplicate_ids` | AC-4 waited |
| anchors keep the old path (AC-5 purge restored) | AC-5 |
| `--store-snapshot` opens the live store | AC-3 daemonless, AC-3 relocated twin |
| id row refreshed only | AC-1b |
| legacy `memory_content` event dropped | AC-1b rebuild-from-log |

## Open points {#open}

- `forced` is printed and carried, but nothing in 26.2 increments it. 26.5 AC-5 owns the
  forcing. Flagged so ch-bsd reads it as a declared seam, not a placeholder. {#o-forced}
- AC-5 is fixed by the refresh: after the bridge, the anchors carry the new path. A watcher
  `sync` of the old path that runs BEFORE the bridge, or a move in an un-organised dir (where
  anchors keep the old path by design, AC-3b), still purges a memory's anchor concepts.
  `purge_path` has no guard for memory anchors. This is not pinned by a test and is not built
  here; it is a follow-up candidate. {#o-ac5-window}

## Remedy r1 RED: tests for ch-bsd r1 b-1, s-1, m-3, m-4 {#remedy-r1-red}

ch-bsd r1 on 8a867bc..90abc72 returned DIRTY 6 (1B/1S/4M). The tests for its b-1, s-1, m-3
and m-4 are in `tests/test_bridge_move_safety_r1.py`. That file imports the helpers and the
`inproc` / `snapshot_env` fixtures from `tests/test_bridge_move_safety.py`. m-1 and m-2 are
registry and spec edits, so they get no tests. Nothing is mocked and no fake is added, so the
mock registry needs no new row.

The b-1 tests build a real git repo under a short `mkdtemp(dir="/tmp")` root. The memdir sits
at `<proj>/.claude/projects/slug/memory`, as viascope's does. The root is RESOLVED. If it were
not, the marker-off anchors would keep a `/var/...` path that the resolved purge never matches,
and the edit loss would stay hidden. The post-commit leg runs `rmx sync --since HEAD~1` through
the CLI against a spawned daemon. The daemon's ping is the route check, because rich markup
removes the CLI's own `[daemon]` suffix from the report. {#r1-red-fixture}

| Test | Finding | At HEAD 90abc72 |
|------|---------|-----------------|
| `test_b1_post_commit_sync_since_after_a_move_keeps_the_new_anchors` | b-1 (i) | RED: `x's anchors after the post-commit sync of the move: []` |
| `test_b1_post_commit_sync_since_after_an_edit_keeps_the_anchors[marker-on]` | b-1 (ii) | RED: `x's anchors after the post-commit sync of the edit: []` |
| `test_b1_post_commit_sync_since_after_an_edit_keeps_the_anchors[marker-off]` | b-1 (ii), pre-existing | RED: same line |
| `test_b1_sync_of_the_current_path_keeps_the_anchors[-i]` | b-1 (iii) | RED: ``x's anchors after `rmx sync -i <current path>`: []`` |
| `test_b1_sync_of_the_current_path_keeps_the_anchors[-f]` | b-1 (iii), `-f` twin | RED: ``x's anchors after `rmx sync -f <current path>`: []`` |
| `test_m3_ancestor_marker_does_not_turn_on_the_path_aware_gate` | m-3 | RED: `an ancestor's marker turned the path-aware gate on` (`moved: 1`) |
| `test_s1_unreadable_marker_refreshes_the_move_and_names_the_marker` | s-1 | passes; kills mutations A and B |
| `test_m4_store_snapshot_with_an_absent_partition_is_refused` | m-4 | passes; kills mutation M4 |

{#r1-red-table}

The b-1 tests pin behaviour only. After the sync, x's three anchors are at the file's current
path. The next bridge then reports `skipped_unchanged: 2`, and the anchors are still there. The
tests do not pin how the fix decides that the bridge owns a row. A gate that only re-creates
anchors on the next bridge still fails, because the anchors are checked before that
bridge. {#r1-red-contract}

Mutation proofs ran on clean GREEN src. Each mutation was restored with its own
`git checkout`, then `__pycache__` was cleared, the line was grepped back, and
`git status --short src` was confirmed empty. {#r1-red-mutations}

- A: `ingest_gmd.py:1471`, `stats.marker_errors.extend(...)` -> `pass`. Killed:
  ``no `marker_error:` line in the bridge report``.
- B: `ingest_gmd.py:936`, `result = True` -> `result = False`. Killed: `the move under an
  unreadable marker was not refreshed` (`skipped_unchanged: 2`, no `moved`).
- M4: `cli.py:10498`, `if row is None:` -> `if False:`. Killed: `--store-snapshot -p
  no-such-partition-r1 ran`. The dry run reported `refresh_pending: 0` against a partition
  that does not exist, which is the misleading answer the refusal prevents.

Logs are in `workflow/review-output/plan26/`: `26.2-r1-red.log`,
`26.2-r1-mut-A-marker-error-dropped.log`, `26.2-r1-mut-B-unreadable-as-unorganised.log`,
`26.2-r1-mut-M4-absent-partition-refusal-dropped.log`, and `26.2-r1-restored.log` (s-1 and m-4
green again after the restores). This RED makes [[#o-ac5-window]] obsolete: b-1 (iii) pins the
current-path sync. {#r1-red-logs}

**Follow-up: tests that kill the GREEN survivors.** Mutations b and b2 of the `purge_path`
guard survived the tests above ([[#r1-green-survivors]]). Three tests were added to
`tests/test_bridge_move_safety_r1.py` to kill them. All three pass on `497f7f0` (11/11 in
`26.2-r1-guard-green.log`). {#r1-red-survivor-kills}

- (b) `test_b1_guard_keeps_anchors_whose_source_path_is_a_symlink_form_of_the_purged_path`.
  The bridge writes the anchor path and `source_path` from one string, so the test seeds the
  older-store shape with `_set_source_path`: a `source_path` in the symlink form of the memdir,
  as viascope's pre-26.2 rows hold it. It then runs `sync -f <resolved path>`. Mutation b (the
  guard compares paths literally only) is killed with ``x's anchors after `sync -f <resolved
  path>` with source_path in symlink form: []`` (`26.2-r1-mut-b-guard-unresolved-killed.log`).
- (b2) `test_b1_guard_purges_a_dropped_anchor_left_on_the_old_path`. This is a bridge-only
  history in an un-organised dir: x is moved, and the edit drops `{#two}`. The re-ingest leaves
  x#two on the old path while `source_path` names the new one, and `sync -f <old>` must purge
  it. It is a real case where the anchor path and `source_path` differ without any seeding.
- (b2) `test_b1_guard_purges_a_project_docs_anchors_that_share_a_memory_id`. A project doc
  with GMD id `x` re-points the `x#...` concepts. After the doc is deleted and its path is
  synced, the concepts must go.
- Mutation b2 (`if True:`, so any memory with the id keeps the anchors) is killed by both b2
  tests: `the stranded x#two on <old> survived the purge` and `the deleted doc's anchors
  survived the purge` (`26.2-r1-mut-b2-guard-ignores-source-path-killed.log`).
- Each mutation was applied at `store.py:6435` and restored in its own `git checkout`.
  `__pycache__` was cleared, the guard line was grepped back, `git status --short src` was
  empty, and `git diff 497f7f0 -- src` was empty.

**Follow-up: the rest of the implementer's scenarios, and the fail-closed branch.** Three more
tests in `tests/test_bridge_move_safety_r1.py` cover the implementer's remaining scenarios.
{#r1-red-addendum}

- `test_b1_guard_purges_anchors_when_the_memorys_source_path_names_another_file` sets x's
  `source_path` to y.md. After `sync -f a/x.md`, x's anchors are gone.
- `test_b1_forgetting_the_memory_releases_its_anchors_to_the_purge` runs
  `rmx memory forget x`, then `sync -f`. The orphaned anchors are purged.
- `test_b1_guard_fails_closed_on_unreadable_memory_metadata` sets x's metadata to
  `'{not json'`. `sync -f` then exits non-zero, names memory x, and the anchors are still there.
- All three pass on `497f7f0`. Mutation fc changes the parse-error `raise` to `continue`. It
  kills the fail-closed test (`the sync succeeded over unreadable metadata`) and the three
  passing loud tests below (`26.2-r1-mut-fc-parse-error-swallowed.log`, 4 failed).

**RED: a sync that stops in an error fails loudly.** This is a user requirement from
2026-11-10: "if the sync stops in an error, it needs to fail loudly on the commandline or
console, not just logs". The tests are in `tests/test_sync_fails_loudly_r1.py` and use the
fail-closed raise above as the error. Log: `26.2-r1-loud-red.log` (6 failed, 17 passed at
`497f7f0`). {#r1-red-loud}

| Surface | Test | At `497f7f0` |
|---------|------|--------------|
| in-process CLI `sync -f` / `-i` | `test_in_process_sync_error_exits_nonzero_and_names_it_on_stderr[-f,-i]` | passes: an uncaught traceback ending in `ValueError: ... memory 'x' ...` on stderr, exit 1; killed by fc |
| daemon-routed `sync --since` | `test_daemon_routed_sync_error_is_an_error_reply_and_a_loud_cli_exit` | passes: the reply is `ok: false`, and the CLI prints `Error: daemon sync_since failed: ... memory 'x' ...`, exit 1; killed by fc |
| generated git hooks (4) | `test_generated_git_hook_does_not_discard_the_sync_failure[*]` | RED: `post-commit discards the sync's error: ['( cd "$ROOT" && rmx sync --since HEAD~1 >/dev/null 2>&1 \|\| true ) &']`, and the same for post-merge, post-checkout and post-rewrite |
| installed post-commit | `test_installed_post_commit_hook_leaves_a_failing_sync_on_the_terminal` | RED: `the post-commit sync failed silently: nothing naming memory x on the terminal` (the commit's stderr is empty) |
| daemon watcher | `test_failed_watch_flush_is_printed_by_daemon_status_until_a_good_flush` | RED: `` `rmx daemon status` does not print the failed watch flush naming memory x `` (the `rmxd.log` line exists and names x) |

{#r1-red-loud-table}

Notes for GREEN. {#r1-red-loud-notes}

- The installed-hook test puts a launcher named `rmx` on PATH that execs this checkout's CLI.
  It is a PATH shim around the real sync, not a mock, so no mock-registry row is needed. The
  test reads the committing terminal's stderr. If the channel records the error elsewhere
  instead, the test's oracle has to change with it.
- The watcher test cannot use the memdir, because the watcher drops hidden segments. Its
  trigger is a project doc `docs/x.md` with GMD id `x`. Its setup runs through a non-watching
  daemon: an in-process `rmx sync` never closes its store, so the test process keeps the
  catalog and the watching daemon cannot start. This is a pre-existing CLI handle leak.
- The in-process surface is already loud, but only as a raw traceback. If the user wants a
  clean `Error:` line rather than a traceback, that is a separate pin.

## Remedy r1 GREEN: purge keeps bridge-owned anchors; marker walk bounded {#remedy-r1-green}

rel: implements -> [[bsd-task-26.2-r1-bridge-move-safety-90abc72#b-1]]
rel: implements -> [[bsd-task-26.2-r1-bridge-move-safety-90abc72#m-3]]

Fix commit `497f7f0` on `task-26.2-bridge-move-safety`. It changes `store.py`, `sync.py`,
`cli.py`, `ingest_gmd.py` and `daemon.py`, and corrects `plan-26-memory-organisation.md`'s
watcher-only premise for `purge_path`. No tests were authored in this step. {#r1-green-scope}

### b-1: the mechanism and why {#r1-green-b1}

`Store.purge_path(abs_path)` now keeps the anchor concepts that the memory bridge owns. An
anchor is owned when it is a `kind=concept` row named `<doc_id>#<anchor>` at `abs_path`, and a
`kind=memory` row named `<doc_id>` in the active partition has a
`memory_content.metadata.source_path` that equals `abs_path`. The comparison is made both
literally and after `os.path.realpath`. Kept ids are counted on `Store.memory_anchors_kept`.
The memory row itself has a NULL `path`, so `purge_path` never selected it. {#r1-green-mechanism}

The guard reads `source_path` instead of stamping the anchors, for four reasons, each tied to a
`purge_path` caller: {#r1-green-why}

- **Live stores.** Every memory already bridged has a `source_path`, so its anchors are
  protected as soon as this code is deployed. A stamp would leave every existing anchor
  unprotected, and the gate never re-bridges an unchanged file to add one.
- **Forget still works.** `rmx forget` (`forget_by_selector`) and `forget_memory` both go
  through `purge_entity` / `_bulk_purge_ids`, which this guard does not touch. Once a memory is
  forgotten, its row no longer claims the path, so the next path purge (`sync -f/-i`, the
  missing-path branch) removes the orphaned anchors. A stamp would protect orphans forever.
- **The guard sits in `purge_path` itself.** Every per-path purge goes through it:
  - the four `_sync_paths` sites, which serve the watcher, `--since`, `-f` and `--flush-queue`;
  - `sync -i`, which calls `purge_path` directly at the CLI;
  - `ingest.py`'s legacy-doc purge.

  `vacuum` and `untrack_by_path` purge through `_purge_paths` / `_bulk_purge_ids` and are left
  as they were. The bridge never calls `mark_tracked`, so vacuum never reaches a memory file.
- **The memory decides.** A row whose `source_path` names another file does not own anchors at
  this path, so a project doc's anchors are purged as before.

If the metadata of a memory row named like an anchor's doc id cannot be parsed, the purge
RAISES. Ownership cannot be decided in that case, and on a memory path neither a silent delete
nor a silent keep is acceptable. {#r1-green-fail-closed}

The declined anchors are reported (#no-silent-failures): {#r1-green-report}

- `_sync_paths` takes the delta of `memory_anchors_kept` and adds it to its report as
  `memory_anchors_kept`. The daemon `sync_*` ops return that report unchanged, and the sync
  log line carries ` memory_anchors_kept=N`.
- `cli._say_memory_anchors_kept(result)` prints `memory_anchors_kept: N (...)` at the daemon
  `synced` line, the in-process `synced` line and `rmx watch`'s batch line.
- `-i` prints its own delta.
- In the b-1 probes each sync printed `memory_anchors_kept: 3`.

### m-3: bounded marker walk {#r1-green-m3}

`_OrganisedDirs(roots)` now stops at the bridge's target dir, because ADR-0005 puts the marker
at `<memdir>/.memory-layout`. Each file is bounded by the deepest target dir that contains it. A
file under no target dir is bounded by its own directory. That covers a file target and a
direct `ingest_gmd_paths` call with no roots. As a result, a target that is a subdir of an
organised memdir does not see the memdir's marker, and it keeps the hash-only rule. That is
the pre-26.2 behaviour, so the bound never causes a wrong refresh. The cache key is
`(dir, bound)`. `ingest_gmd_paths(..., marker_roots=)` is passed by three callers:
`_ingest_gmd_in_process` (`resolved`), `daemon._run_ingest_gmd_body` (`args["targets"]`,
resolved) and the sessions ingest (`[cards_dir]`). {#r1-green-m3-bound}

### Signatures {#r1-green-signatures}

- `Store.purge_path(self, abs_path: str) -> int` keeps its signature and return value (the
  number of entities removed). It now also increments `self.memory_anchors_kept`.
- `Store._memory_owned_anchor_ids(self, abs_path: str, found: list[tuple[int, str, str]]) -> set[int]`
  is new.
- `ingest_gmd_paths(..., marker_roots: Iterable[Path] | None = None) -> IngestStats` gains the
  `marker_roots` argument.
- `_OrganisedDirs.__init__(self, roots: Iterable[Path] | None = None)` is new, and
  `_OrganisedDirs._bound(self, rp: Path) -> Path` is new.
- `cli._say_memory_anchors_kept(result) -> None` is new.
- The `_sync_paths` report gains `memory_anchors_kept: int`.

### Verification {#r1-green-verify}

- `26.2-r1-green.log`: `tests/test_bridge_move_safety_r1.py` and `tests/test_bridge_move_safety.py`
  pass 33/33 (8 + 25).
- `26.2-r1-green-run1-pre-lockfix.log` is the first run (17:24), against the RED test file as
  it stood before `41048a5`: 3 failed / 30 passed. The three daemon-leg b-1 tests passed their
  post-sync anchor assertion. They then failed in `_assert_next_bridge_skips`, where `Store(root)`
  hit `Conflicting lock is held ... (PID <the restarted daemon>)`, because the test read the
  store while the restarted daemon was still up. The family run collected the same pre-fix file
  and failed the same way. `41048a5` (17:27, test side) stops the daemon before that read. Every
  run after it, including `26.2-r1-green.log` and `26.2-r1-green-rerun.log`, passes those three
  tests. This was a test defect fixed in the test, not a flake. {#r1-green-flake}
- `26.2-r1-green-family.log` covers 54 files: the family globs plus every `tests/test_*.py` that
  names `purge_path`, `forget` or `vacuum`. Result: 1009 passed, 3 failed. All 3 failures are the
  pre-`41048a5` lock defect above, with the identical `E` line, and they pass at `497f7f0` in
  `26.2-r1-green.log`. None of the known pre-existing rows fell in this set.
- GMD lint on this summary and on plan-26 shows 0 errors.

### Mutations against `497f7f0` (`26.2-r1-mutations.log`) {#r1-green-mutations}

Each mutation was restored with its own `git checkout`. After each restore, `__pycache__` was
cleared, the fix line was grepped back, and `git status --short src` was confirmed empty.

| # | Mutation | Result |
|---|----------|--------|
| a | `purge_path`: `kept = set()` (guard removed) | KILLED: 5 b-1 tests, `x's anchors after ...: []` |
| b | guard compares `sp == abs_path` only (resolution dropped) | SURVIVED: 8/8 |
| b2 | guard keeps the anchors whenever a memory row with that doc id exists, ignoring `source_path` | SURVIVED: 33/33 |
| c | `_OrganisedDirs`: `if d == bound: break` removed (walk unbounded) | KILLED: `test_m3_...`, `an ancestor's marker turned the path-aware gate on` |

b and b2 survive because no history the bridge writes can separate them from the fix. The
bridge writes the anchors' `path` and the row's `source_path` from the same string in the same
pass, and the CLI and daemon resolve their targets. {#r1-green-survivors}

- **b.** Literal and resolved forms differ only when another writer has re-pointed the anchors.
  One case is a non-memory GMD ingest of a file with the same id. Another is a pre-26.2 row in
  symlink form whose anchors were later rewritten in resolved form.
- **b2.** `source_path` names another file only in an id collision between a memory and a
  project doc.
- **Tests that would kill them** (for the test engineer):
  - (b): bridge, then set the row's `source_path` to a symlink form of the same file and run
    `sync -f <resolved path>`. The anchors must survive.
  - (b2): bridge, then point the row's `source_path` at another file and run `sync -f
    <anchor path>`. The anchors must go.
  - (b2), second form: `rmx memory forget x`, then `sync -f <path>`. The orphaned anchors must
    go. b2 does not change that outcome on its own, but it pins the forget path.

### Open {#r1-green-open}

- A `bug_registry` row is still owed for the pre-existing EDIT loss: marker-off edit, bridge,
  commit, `sync --since` left the anchors at `[]`. This fix covers it, and the marker-off test
  pins it.
- Pre-existing, not changed here: with a daemon up, `rmx sync -i` calls `purge_path` on the
  `_DaemonWriter` proxy. That proxy has no `purge_path`, so `__getattr__` sends the call to the
  lock-free READER Store. The `-i` daemon route is a separate defect and needs its own row.
