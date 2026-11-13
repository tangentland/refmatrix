---
gmd: "0.1"
id: impl-task-bug212-worktree-hook-crashes
title: "bug-212: the git hooks crash in throwaway worktrees -- RED and GREEN"
tags: [implementation-summary, bug-212, hooks, git, worktree, sync, loud-failure]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-11
---

# bug-212: git hooks in throwaway worktrees {#root}

Branch `task-bug212-worktree-hook-crashes`, base `f7c0d39` (deployed 0.82.0 + docs). RED commit
`defd9e3`: 17 tests fail at HEAD, 2 guards pass and are proven by mutation. The bug, verbatim
symptoms and proposed fix are in the `bug-212` row of the bug registry.

rel: implements -> [[bug_registry]]
rel: depends-on -> [[test_mock_registry]]

## RED {#red}

File `tests/test_bug212_hooks_in_worktrees.py`. Log `workflow/review-output/bug212-red.log`
(`17 failed, 2 passed in 21.58s`). Real git, the GENERATED hook bodies
(`hooks._install_git_hooks`) in tmp repos under a short `/tmp` mkdtemp root; the fleet layout
(`.refmatrix/CLAUDE.md` tracked, the rest of `.refmatrix/` ignored, a real store in the main
checkout). The one stand-in is a recording `rmx` PATH shim that execs this checkout's real
`cli_entry` (mock registry row, `external`). `GIT_TRACE` proves each hook fired, so "the hook ran
no `rmx`" is never vacuous.

### Contract 1: no store, no sync {#red-c1}

`test_a_checkout_without_a_store_of_its_own_runs_no_sync[<hook>-<worktree|clone>]` -- 8 cases,
one per generated hook (post-commit: a commit; post-checkout: a real branch switch; post-merge: a
merge; post-rewrite: `commit --amend`), each in a `git worktree add` checkout and in a
`git clone` (hooks installed into the clone). Asserts exit 0, no shim call, no traceback, the
checkout's `.refmatrix/` holds exactly `CLAUDE.md`, and the main store has no path under the
checkout. RED line (every case): `<hook> in a <where> with no store of its own ran rmx:
[('<co>', 'sync --since ...')]`. At HEAD the sync REFUSES there (`Error: no refmatrix at
<co>/.refmatrix. Run rmx init first`) rather than creating a store, so the no-store-created and
main-store assertions are guards, not the RED driver.

### Contract 2: an initial checkout is not a branch switch {#red-c2}

`test_post_checkout_with_a_null_previous_head_runs_no_sync_and_prints_nothing` -- the installed
post-checkout invoked as git invokes it (`$1` = 40 zeros, `$3` = 1) in the MAIN checkout, which
has a store. RED line: `post-checkout with a null previous HEAD ran rmx: [('<proj>', 'sync
--since 0000000000000000000000000000000000000000..<sha>')]`.

### Contract 3: a ref git rejects is a clean error {#red-c3}

`test_sync_since_a_ref_git_rejects_is_a_clean_error_in_process[<ref>]` and
`..._through_the_daemon[<ref>]`, refs `no-such-ref-bug212` and `<null>..HEAD`. git's own message
is read by running the same `git diff --name-only <ref>` (not hardcoded); the `Error:` line must
name the ref and contain it (the `fatal: ` prefix may be dropped). RED lines: in-process
`` [in-process] `rmx sync --since <ref>` failed as a raw traceback `` (CalledProcessError); daemon
`` [daemon] no `Error:` line naming the ref <ref> and git's message ... `` -- HEAD prints
`Error: daemon sync_since failed: Command '[...]' returned non-zero exit status 128.`, which drops
git's stderr. The daemon leg also asserts the daemon survives.

### Contract 4: a vanished cwd is a clean error {#red-c4}

`test_rmx_started_in_a_vanished_cwd_is_a_clean_error[sync-since|stats|version]` -- a shell `cd`s
into a tmp dir, removes it, execs `rmx`; no `REFMATRIX_ROOT`. Asserts non-zero exit, no
traceback, an `Error:` line mentioning the directory / cwd. RED line (each): `` `rmx <argv>` in a
vanished cwd crashed with a raw traceback `` (`FileNotFoundError` from `Path.cwd()` in
`cli_entry`). `version` is included because the lead's contract says "any rmx command".

### Contract 5: end to end {#red-c5}

`test_worktree_add_commit_remove_prints_no_traceback_and_leaves_the_main_store_alone` -- hooked
`git worktree add`, a commit in the worktree whose backgrounded post-commit is left running while
`git worktree remove` runs, then the commit's pipes are drained to EOF. Asserts no traceback in any
stderr, no `rmx sync FAILED` line, the worktree is gone, and the main store has no worktree path.
RED line: `raw traceback(s) during ['commit']` -- the post-commit's `FileNotFoundError` (bug (b));
the worktree add stderr also shows `Error: no refmatrix at <wt>/.refmatrix` + `post-checkout rmx
sync FAILED` (bugs (a)/(c)).

### Guard: the main checkout still syncs {#red-guard}

`test_the_main_checkout_with_a_store_still_syncs[post-commit|post-checkout]` -- passes at HEAD.
Proven by the mutation `[ -d "$ROOT/.refmatrix" ] || exit 0` -> `exit 0` in all four
`GIT_HOOK_SCRIPTS` bodies: both cases fail (`<hook> in the main checkout (store present) ran no
sync there: []`, log `workflow/review-output/bug212-mutation-gate.log`); restored with
`git checkout -- src/refmatrix/hooks.py` in its own command, `git status --short src` empty,
`__pycache__` cleared. A fix that silences the hooks everywhere fails it.

### Not covered {#red-gaps}

The daemon-down-but-launchd-installed branch of `rmx sync --since` (`changed_since` called
outside the `_store()` path; catches only `RuntimeError`) is not driven: it needs a supervised
store. The GREEN fix to `changed_since` covers it by construction; say so in GREEN.

## GREEN {#green}

Fix commit `b6357ca` (src only, by pathspec). The RED file is 19/19 green; no test was edited
by the implementer (the test engineer's `591e8c5` relaxed the `version` case of contract 4 to
"may succeed or fail cleanly" while GREEN was in progress, and it is in the run).

### What changed {#green-changes}

- `src/refmatrix/store.py` -- `WRITER_CATALOG_FILES: tuple[str, ...] = ("catalog.A.duckdb",
  "catalog.B.duckdb", "catalog.duckdb", "catalog.db")`: THE definition of "this `.refmatrix/`
  is a store" (a file a writer may hold). Reader files (`catalog.read.duckdb`,
  `read_only.duckdb`) never make a store alone. `verbs._writer_catalog_files(root)` now reads
  it (was the same four names retyped), and the hook gate is rendered from it, so the shell and
  Python cannot disagree.
- `src/refmatrix/hooks.py` -- `_store_gate() -> str` renders
  `[ -e "$ROOT/.refmatrix/<name>" ] || ... || exit 0` over `WRITER_CATALOG_FILES`;
  `GIT_HOOK_SCRIPTS: dict[str, str]` substitutes it (`@STORE_GATE@`) into all four bodies in
  place of `[ -d "$ROOT/.refmatrix" ] || exit 0` (contract 1). post-checkout adds
  `case "$1" in *[!0]*) ;; *) exit 0 ;; esac` after the `$3` check: an all-zeros (or empty)
  previous HEAD exits 0 silently; the pattern also covers a SHA-256 repo's 64 zeros
  (contract 2).
- `src/refmatrix/sync.py` -- `class GitRefError(RuntimeError)` with
  `__init__(self, git_ref: str, returncode: int, stderr: str)` (attributes `git_ref`,
  `returncode`, `stderr`); message `sync --since <ref> failed: git diff exited <N>: <git's
  stderr on one line>`. `changed_since(project_root: Path, git_ref: str) -> list[Path]` (same
  signature) runs git without `check=True` and raises `GitRefError` on a non-zero exit
  (contract 3).
- `src/refmatrix/cli.py` -- `_cwd_gone_message() -> str`; `_cwd() -> Path` (`Path.cwd()`, or a
  `click.ClickException` naming `$PWD` when `os.getcwd()` itself fails: FileNotFoundError with
  no filename; any other FileNotFoundError re-raises); every former `Path.cwd()` in cli.py (7
  sites, including `_root()` and the four in `sync`) goes through it.
  `_root_without_cwd() -> Path` (`REFMATRIX_ROOT`, else the global store) files ONLY the
  telemetry row of a cwd-less run. `cli_entry()` records `cwd: null` + `cwd_error` instead of
  crashing, then runs the command: one that needs a project fails at its first `_cwd()` with
  `Error: the working directory no longer exists (<PWD>); cd to a project, or set
  REFMATRIX_ROOT` (exit 1); `rmx version` prints the version (exit 0). The in-process `sync`
  adds `except syncmod.GitRefError` -> `ClickException(str(exc))` beside the
  `MemoryOwnershipError` handler (contract 4).
- `src/refmatrix/telemetry.py` -- `log_cli_invocation(..., cwd: "str | None", ...,
  cwd_error: "str | None" = None)`; the row carries `cwd_error` when set.

### The three `--since` routes {#green-since-routes}

In-process: `GitRefError` -> `Error: sync --since <ref> failed: git diff exited 128: fatal:
...`. Daemon: `_op_sync_since` raises it, the op dispatcher replies `ok:false` with its text
(the daemon logs `op sync_since raised` and keeps serving; the test pings it after), the CLI
prints `Error: daemon sync_since failed: sync --since <ref> failed: ...`. Daemon down but
launchd-installed: that branch catches `RuntimeError` and `GitRefError` IS one, so it prints the
same line with no new handler -- covered by construction, not driven by a test (it needs a
supervised store; see [[#red-gaps]]).

### Runs {#green-runs}

- `workflow/review-output/bug212-green.log` -- the RED file + `test_sync_fails_loudly_r1/r2`,
  `test_hooks*.py`, `test_repo_hooks_in_sync`, `test_sync*.py`, `test_docs_generated`,
  `test_cli*.py`: **110 passed, 1 skipped**.
- `workflow/review-output/bug212-green-wide.log` -- the above plus `test_bridge_move_safety_r1`,
  the telemetry files, `test_verb_parity`, `test_verbs_migrated`, task 3.7 infra/remedy/graph,
  `test_sandbox_redirect`, `test_v2_features`, `test_memory_bridge`, `test_task_cli_session`,
  `test_task4_6_r5_remedy`, `test_plan5_remedy`, `test_bug162_163_worker_qos_hook_path`:
  **592 passed, 1 skipped** in 530 s.
- The one skip in both is `test_repo_hooks_in_sync::test_installed_hooks_match_generated`
  ("hooks belong to another checkout of this commit"), and the SkipGate reports it UNPINNED:
  this clone's `.venv-eval` is a symlink to the main tree's, so `conftest.ALLOWED_SKIPS` treats
  the clone as the main tree and drops `_CLONE_ONLY_SKIPS`. A clone-environment artifact, not
  this change (`hooks.check` compares `.claude/settings.json`, not git hooks). No other failure:
  the known bug-170/127/168/196 rows did not reproduce in these files.

### Mutations {#green-mutations}

Against `b6357ca`, log `workflow/review-output/bug212-mutations.log`, RED file per mutation;
each restored with `git checkout -- <file>` in its own command, `__pycache__` cleared, the fix
grepped back, `git status --short src` empty. Post-restore the file is 19 passed.

| id | mutation | failed |
|----|----------|--------|
| g | `_store_gate` returns `[ -d "$ROOT/.refmatrix" ] \|\| exit 0` | 9: all 8 contract-1 cases + the end-to-end |
| z | post-checkout's null-sha `case` line removed | 1: the null-previous-HEAD test |
| c | `changed_since` back to `check=True` (CalledProcessError escapes) | 4: both refs x in-process + daemon |
| w | `_cwd()` returns `Path.cwd()` unguarded | 3: sync-since, stats, version (vanished cwd) |

### The new hook bodies {#green-hook-bodies}

What `rmx install-hooks --apply --force` writes from `b6357ca` (the release re-installs them
fleet-wide). Nothing generated pins the old text (`scripts/gen-cli-tree.py` renders no hook
bodies; no doc quotes the gate).

```bash
# post-commit
#!/usr/bin/env bash
# refmatrix: refresh after each commit
set -e
ROOT="$(git rev-parse --show-toplevel)"
# no store of its own (a worktree or clone with only the tracked .refmatrix/CLAUDE.md): nothing to sync
[ -e "$ROOT/.refmatrix/catalog.A.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.B.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.db" ] || exit 0
( cd "$ROOT" && rmx sync --since HEAD~1 >/dev/null || echo "refmatrix: post-commit rmx sync FAILED (exit $?); its error is above" >&2 ) &
disown

# post-merge
#!/usr/bin/env bash
# refmatrix: refresh after merge
set -e
ROOT="$(git rev-parse --show-toplevel)"
# no store of its own (a worktree or clone with only the tracked .refmatrix/CLAUDE.md): nothing to sync
[ -e "$ROOT/.refmatrix/catalog.A.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.B.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.db" ] || exit 0
( cd "$ROOT" && rmx sync --since ORIG_HEAD >/dev/null || echo "refmatrix: post-merge rmx sync FAILED (exit $?); its error is above" >&2 ) &
disown

# post-checkout
#!/usr/bin/env bash
# refmatrix: refresh after checkout (only branch switches, $3==1)
set -e
[ "$3" = "1" ] || exit 0
# an initial checkout (git clone, git worktree add) has a null previous HEAD: not a branch switch
case "$1" in *[!0]*) ;; *) exit 0 ;; esac
ROOT="$(git rev-parse --show-toplevel)"
# no store of its own (a worktree or clone with only the tracked .refmatrix/CLAUDE.md): nothing to sync
[ -e "$ROOT/.refmatrix/catalog.A.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.B.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.db" ] || exit 0
( cd "$ROOT" && rmx sync --since "$1..$2" >/dev/null || echo "refmatrix: post-checkout rmx sync FAILED (exit $?); its error is above" >&2 ) &
disown

# post-rewrite
#!/usr/bin/env bash
# refmatrix: refresh after rebase/amend
set -e
ROOT="$(git rev-parse --show-toplevel)"
# no store of its own (a worktree or clone with only the tracked .refmatrix/CLAUDE.md): nothing to sync
[ -e "$ROOT/.refmatrix/catalog.A.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.B.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.duckdb" ] || [ -e "$ROOT/.refmatrix/catalog.db" ] || exit 0
# Read rewritten oid pairs from stdin; sync from the oldest old-oid.
OLD=$(awk '{print $1; exit}')
[ -z "$OLD" ] && exit 0
( cd "$ROOT" && rmx sync --since "$OLD" >/dev/null || echo "refmatrix: post-rewrite rmx sync FAILED (exit $?); its error is above" >&2 ) &
disown
```

### For the reviewers {#green-flags}

- A project whose `.refmatrix/` holds only a `partition` file and whose store is a shared one
  named by `REFMATRIX_ROOT` no longer syncs from its git hooks: it has no store of its own. That
  is the lead's contract 1 as decided; no such project is known in the fleet, but it is a
  behaviour change.
- `docs/INTEGRATION.md#git-integration` describes the hooks (table + "All hooks run `rmx` in
  the background") without the store gate or the null-sha skip; left for the doc writer.
- A cwd-less run's telemetry row goes to `REFMATRIX_ROOT` or the global store's `cli.log`. One
  manual probe of `rmx version` in a deleted scratch dir appended one such row (`cwd: null`,
  `cwd_error` set) to `~/.refmatrix/cli.log` -- a JSONL append, no store open.
- The pre-existing `except Exception: pass` around `log_cli_invocation` in `cli_entry` is
  unchanged (accounting never fails the command); the cwd-less case no longer reaches it.
- The bug-212 registry row is still `open`; flipping it is for the commit that merges this.

## RED r1 (remedy for ch-bsd r1, DIRTY 8) {#red-r1}

Test commits `277ce60` and `b0a0604` (a2) on top of `7537965` (tests + mock registry only; no
`src/`). File `tests/test_bug212_r1_remedy.py`. At `7537965`: **31 failed, 4 passed** in 32 s
(`workflow/review-output/bug212/red-r1-head.log`). The 4 passes are guards, each proven by a
mutation below. Real git and the GENERATED hook bodies (`hooks._install_git_hooks`) in tmp repos
under a short `/tmp` mkdtemp root; the bug-212 recording `rmx` shim; `GIT_TRACE` proves each
hook fired. Scope per the brief: b-1, s-1, m-1, m-2, m-3 (s-2 = bug-209, s-3 docs and bug-215
are out of scope).

rel: derives-from -> [[bsd-bug212-r1-b024a95]]
rel: depends-on -> [[agent-brief-red-212r1]]

### b-1: a repo that tracks its catalog {#red-r1-b1}

Fixture `tracked_repo`, two committed layouts from the 2026-11-11 fleet survey: `slots`
(catalog.A/B.duckdb + `active` + catalog.duckdb, cliquet/atldb) and `legacy` (catalog.duckdb only,
prep_prolific). Nothing under `.refmatrix/` is ignored; the fixture asserts the catalogs are
tracked and the main checkout's `.refmatrix/` is clean before any hook runs.

- `test_a_checkout_of_a_repo_that_tracks_its_catalog_runs_no_sync[<layout>-<hook>-<worktree|clone>]`
  -- 16 cases: all four hooks, in a `git worktree add` and in a `git clone`. Asserts that no rmx
  call is made, no traceback or FAILED line appears, `git status --porcelain --untracked-files=all
  -- .refmatrix` is empty, and (worktree) a plain `git worktree remove` succeeds. RED line (each):
  `[<layout>] <hook> in a <where> of a repo that TRACKS its catalog ran rmx: [('<co>', 'sync
  --since ...')]`. The same message carries the status at HEAD: ` M .refmatrix/catalog.A.duckdb`
  (slots) or ` M .refmatrix/catalog.duckdb` (legacy), plus `?? cli.log / sync.log / facts.log`.
  That is the audit's tracked binary being written.
- `test_the_main_checkout_of_a_repo_that_tracks_its_catalog_runs_no_in_process_sync[<layout>-post-commit|post-checkout]`
  -- 4 cases: the main checkout, catalog tracked, no daemon. RED line: `[<layout>] <hook> in the
  main checkout (catalog tracked, no daemon) ran rmx: [('<proj>', 'sync --since ...')]`. See
  ambiguity a1.
- GUARD `test_a_repo_that_tracks_its_catalog_still_syncs_through_a_live_daemon[<layout>]` -- 2
  cases. A real daemon (`spawn_daemon_subprocess`) runs on the tracked store. post-commit must
  sync in the main checkout, and the file must be in the store after the daemon stops. Passes at
  HEAD. Killed by G1 (gate = `exit 0`) and by G2 (the gate reduced to "a catalog git does not
  track", dropping the socket half): `ran no sync: []`, 2/2 each.
- The existing guard `test_bug212_hooks_in_worktrees.py::test_the_main_checkout_with_a_store_still_syncs`
  already covers "a primary checkout with an untracked store still syncs". It was not changed.

### s-1: a vanished cwd at every cwd reader {#red-r1-s1}

- `test_a_vanished_cwd_with_refmatrix_root_set_is_a_clean_error[sync-since|stats|grep|context|query]`
  -- `REFMATRIX_ROOT` set to a throwaway store, cwd deleted before exec. Must exit non-zero with
  no traceback and an `Error:` line that says the working directory is gone. RED line (each):
  `` `rmx <argv>` (REFMATRIX_ROOT set) in a vanished cwd crashed with a raw traceback ``. The
  frames are `discovery.resolve_partition:296` -> `discovery.partition_marker:269`.
- `test_a_vanished_cwd_is_a_clean_error_outside_root_resolution[cctree|hub-pause]` -- no
  `REFMATRIX_ROOT`. Must exit non-zero with no traceback and an `Error:` line. RED lines: `rmx
  cctree` crashed (`cctree.resolve_path:1297`); `rmx hub pause nosuch-bug212` crashed
  (`discovery.discover_roots:121` -> `_cwd_root:100`).
- `test_an_mcp_tool_call_in_a_vanished_cwd_names_the_working_directory` -- `rmx mcp` over stdio
  with `rmx_query` and no root/project. Must return `isError` with text that says the working
  directory is gone, and must still answer a ping after. RED line: `... failed without saying the
  working directory is gone: 'FileNotFoundError: [Errno 2] No such file or directory'`
  (`mcp._resolve_root:63`).
- `test_sync_library_entries_in_a_vanished_cwd_raise_the_named_cwd_error[sync_since|sync_files]`
  -- `sync.sync_since` (sync.py:163) and `sync.sync_files` -> `_sync_paths` (sync.py:283), with no
  `project_root`. Each must raise a non-OSError whose message says the working directory is gone.
  The class name is the implementer's choice. RED line: `sync.<fn> in a vanished cwd raised
  FileNotFoundError: '[Errno 2] No such file or directory' -- not the named cwd error`.

### m-1, m-2, m-3 {#red-r1-m}

- m-3, RED: `test_a_root_commit_is_synced_not_reported_as_a_failure`. A fresh repo with an
  ignored store and the hooks installed. The first commit must print no FAILED or `Error:` line,
  must run a sync, and must index the root commit's file. RED line: `post-commit on a root commit
  (no HEAD~1) reported a failure`, with stderr `Error: sync --since HEAD~1 failed: git diff exited
  128: fatal: ambiguous argument 'HEAD~1' ...` and `refmatrix: post-commit rmx sync FAILED (exit
  1)`.
- m-1, GUARD: `test_a_cwd_less_run_writes_one_telemetry_row_naming_the_lost_cwd`. `rmx version`
  runs in a vanished cwd with no `REFMATRIX_ROOT`, a fresh `RMX_HOME`, and telemetry on. It must
  write exactly one `cli.log` row with `argv ["version"]`, `cwd: null`, and a `cwd_error` naming
  the directory. Mutation A (row filed through `_root()`) kills it: `expected exactly one cli.log
  row in RMX_HOME, got []`. Mutation B (drop `record["cwd_error"]`) kills it: `the cwd-less row's
  cwd_error does not name ...`.
- m-2, GUARD: `test_sync_since_a_bad_ref_on_a_supervised_store_with_the_daemon_down_is_a_clean_error`.
  A placeholder plist FILE sits at `launchctl.plist_path(root)` inside the sandbox; the test
  refuses any path outside `RMX_SANDBOX_ROOT`. The real `is_installed` therefore answers True.
  There is no daemon. A control call with `--since HEAD` must print `daemon down`, which proves the
  branch is reachable. Then `--since no-such-ref-bug212` must be a clean `Error:` naming the ref
  and git's message. Mutation D (`GitRefError(Exception)`) kills it: `[daemon-down+launchd] ...
  failed as a raw traceback` (`refmatrix.sync.GitRefError: ...`).

### Mutations and the satisfiability probe {#red-r1-mutations}

Every mutation ran on `277ce60` against the whole new file. Each was restored in its own command
with `git checkout -- <file>`, the fix was grepped back, and `git status --short src` was empty.
`__pycache__` was cleared after the batch. After the restore, the new file plus the prior bug-212
file give 31 failed, 23 passed (`red-r1-post-restore.log`): the same 31 REDs, 4 guards, and the
19 prior tests.

| id | mutation | killed | log |
|----|----------|--------|-----|
| G1 | `_store_gate` returns `exit 0` | live-daemon guard 2/2 | `red-r1-mut-G1-gate-exit0.log` |
| G2 | gate = presence AND `git ls-files` empty (no socket half) | live-daemon guard 2/2; all 20 b-1 REDs pass under it | `red-r1-mut-G2-untracked-only.log` |
| D | `class GitRefError(Exception)` | m-2 guard | `red-r1-mut-D-gitreferror-base.log` |
| A | telemetry row filed via `_root()` | m-1 guard | `red-r1-mut-A-telemetry-via-root.log` |
| B | `record["cwd_error"]` not written | m-1 guard | `red-r1-mut-B-no-cwd-error.log` |

The satisfiability probe was not committed and was restored like a mutation. It applied the
audit's prescribed gate, `[ -S "$ROOT/.refmatrix/rmxd.sock" ] || { <presence> && [ -z "$(git -C
"$ROOT" ls-files -- <WRITER_CATALOG_FILES>)" ]; } || exit 0`, rendered from
`WRITER_CATALOG_FILES`. Result: all 20 b-1 REDs, both live-daemon guards, and the 19 prior bug-212
tests pass. The 11 that still fail are s-1 and m-3, which no gate can fix
(`red-r1-probe-full-gate.log`). The b-1 contract can be met with a shell gate alone.

### a2: an in-process sync never writes a git-tracked catalog {#red-r1-a2}

This was added on the lead's decision a2 (2026-11-13). Test commit `b0a0604`. At `52e6b72` it adds
**6 RED and 1 guard**. Both bug-212 files together give **37 failed, 24 passed**
(`red-r1-a2-head.log`; after the mutation restore, `red-r1-a2-post-restore.log` gives the same
counts).

- `test_an_in_process_sync_refuses_to_write_a_git_tracked_catalog[<layout>-files|since]` -- 4
  cases. `rmx sync --files <f>` and `rmx sync --since HEAD~1` run in the main checkout of
  `tracked_repo`, with cwd resolution, no `REFMATRIX_ROOT`, and no daemon. Required: no traceback;
  the sha256 of every catalog file is unchanged; exit non-zero; exactly ONE `Error:` line that
  names the target file (`catalog.A.duckdb` for slots, `catalog.duckdb` for legacy) and contains
  both remedies (`untrack` or `rm --cached`, and `daemon`); `git status` shows no catalog file
  modified. RED line: `[<layout>] in-process `rmx sync ...` wrote the git-tracked catalog
  ['<target>'] (exit 0)`.
- `test_post_commit_with_a_stale_socket_on_a_tracked_catalog_refuses_loudly[<layout>]` -- 2
  cases. A unix socket file with no listener sits at `.refmatrix/rmxd.sock` (bound, then closed
  without unlinking), so the socket half of the gate passes. The GENERATED post-commit then runs.
  Required: the git op exits 0; no traceback; the tracked catalog is byte-identical. If the hook
  ran `rmx`, stderr must also carry the one refusal `Error:` line and the hook's `rmx sync FAILED`
  line. RED line: `[<layout>] post-commit beside a stale socket wrote the git-tracked catalog
  ['<target>']`.
- GUARD `test_an_in_process_sync_of_a_store_outside_any_git_repo_still_writes` -- a store that is
  not inside any git repo, where `git rev-parse` fails. `rmx sync --files` in-process must exit 0
  and index the file. Passes at HEAD. Mutation R, every in-process `rmx sync` raising before
  `_store()`, kills it (`red-r1-mut-R-refuse-all.log`). The a2 REDs stay red under R because they
  require the message to name the file and the remedy. The ignored-store case, where a git repo
  does not track the catalog, is already guarded:
  `test_bug212_hooks_in_worktrees.py::test_the_main_checkout_with_a_store_still_syncs` syncs
  in-process with `.refmatrix/*` ignored.

### Lead decisions on a1-a8 (2026-11-13) {#red-r1-decisions}

- **a1 accepted.** A tracked catalog with no daemon gets no sync; the gate fails closed. The trunks
  lose their tracked catalogs when they merge bug-214's untrack commits.
- **a2 → RED added** in [[#red-r1-a2]]. The CLI refuses an in-process write to a tracked catalog,
  and the stale-socket path is covered through the generated post-commit.
- **a3 accepted.** A worktree whose own store is untracked (it ran `rmx init` itself) syncs. Not
  pinned.
- **a4 accepted.** With `REFMATRIX_ROOT` set and the cwd gone, the command fails. It never picks
  a partition silently.
- **a5 accepted.** cctree and hub-pause: non-zero exit plus an `Error:` line is enough.
- **a6 accepted.** `cli.py:7109` (`_grep_rg_fallback`'s `os.getcwd()`) is a census item for the
  implementer. It is unreachable from the CLI in a vanished cwd, so it has no RED.
- **a7 accepted, out of scope.** The `Path.cwd()` defaults inside daemon ops (`daemon.py`
  3475/3496/3582/4002/4563) read the DAEMON's cwd. They are not part of this remedy.
- **a8 accepted.** The library-level s-1 tests pin a behaviour (a non-OSError naming the working
  directory), not a class.
