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

## GREEN r1 (remedy for ch-bsd r1: b-1, a2, s-1, m-3, s-3) {#green-r1}

Fix commit `faabdfe` (src only, by pathspec); docs commit `69333d2` (`docs/INTEGRATION.md`). No
test was edited. Both bug-212 test files: **61 passed, pytest exit 0**
(`workflow/review-output/bug212/green-r1.log`; at `62db88f` they were 37 failed / 24 passed).

rel: derives-from -> [[bsd-bug212-r1-b024a95]]
rel: depends-on -> [[agent-brief-green-212r1]]
rel: implements -> [[#red-r1]]

### What changed {#green-r1-changes}

- **b-1** `src/refmatrix/hooks.py` -- `_store_gate() -> str` now renders, for all four hooks:
  `if [ ! -S "$ROOT/.refmatrix/rmxd.sock" ]; then <a WRITER_CATALOG_FILES file present> || exit
  0; TRACKED="$(git -C "$ROOT" ls-files -- <those names>)" || { echo "refmatrix: ${0##*/}: git
  ls-files failed; not syncing" >&2; exit 0; }; [ -z "$TRACKED" ] || exit 0; fi`. The socket
  name comes from `daemon.SOCKET_NAME`, the catalog names from `store.WRITER_CATALOG_FILES`.
- **m-3** `hooks.GIT_HOOK_SCRIPTS["post-commit"]` -- `SINCE=HEAD~1; git rev-parse -q --verify
  HEAD~1 >/dev/null || SINCE="$(git hash-object -t tree /dev/null)"`, then `rmx sync --since
  "$SINCE"`. `hash-object` gives the empty tree in the repo's own hash (SHA-1 or SHA-256).
- **a2** `src/refmatrix/store.py` -- `git_tracked_catalogs(root: Path) -> list[str]` (the
  tracked `WRITER_CATALOG_FILES` names under `root`). It returns `[]` when git is missing, when
  `root` is not a dir, or when `root` is in no work tree. It raises
  `TrackedCatalogCheckError(RuntimeError)` when `ls-files` fails inside a repo. It drops the
  repo-local `GIT_*` variables (`_GIT_LOCAL_ENV_VARS`), so the hook's repository cannot answer
  for the store's. `src/refmatrix/cli.py` -- `_refuse_in_process_write_to_tracked_catalog(root:
  Path) -> None` raises one `ClickException` that names the target file (the active slot, else
  the legacy catalog), the tracked names and both remedies. The `sync` command calls it when
  `daemon.ping` fails, before `_store()` opens the catalog. `-i` can reach `_store()` with a
  daemon up, and `_store()` then returns the daemon writer, so the ping gate keeps that path
  unrefused.
- **s-1** `src/refmatrix/workdir.py` (new, stdlib only):
  - `class WorkingDirectoryGone(RuntimeError)`, `__init__(self, remedy: str | None = None)`.
  - `cwd_gone_message(remedy: str | None = None) -> str` names `$PWD`. Its default remedy is
    "cd to a project, or set REFMATRIX_ROOT"; with `REFMATRIX_ROOT` already set it is "cd to an
    existing project directory (REFMATRIX_ROOT is set, but this command also reads the working
    directory)".
  - `current_dir(remedy: str | None = None) -> Path` translates only `Path.cwd()`'s
    `FileNotFoundError`.
  - Routed through it: `cli._cwd()` (now `-> Path`, raising `WorkingDirectoryGone`),
    `discovery._cwd_root`, `discovery.partition_marker`, `sync.sync_since`, `sync._sync_paths`
    (remedy "pass project_root ..."), `mcp._resolve_root` (remedy names `root`/`project`/
    `REFMATRIX_ROOT`), `cctree._project_base(args) -> Path` (new; the five former
    `Path.cwd()` fallbacks; remedy "pass --project <dir>"; the standalone `__main__` prints
    `cctree: <msg>`), and `cli._grep_rg_fallback` (a6 census).
  - `class _RmxGroup(click.Group)` (`main` is now `cls=_RmxGroup`) turns `WorkingDirectoryGone`
    into one `Error:` line, exit 1, for every command.
  - `cli_entry` catches `WorkingDirectoryGone` for the cwd-less telemetry row.
  - `cli._cwd_gone_message` is gone, and with it the old `_cwd()`'s unreachable
    `exc.filename` branch (m-1, mutation E).
  - `discover_roots` raises on a vanished cwd rather than dropping it (a5): dropping it would
    answer without the store the caller stands in, silently.
- **s-3** `docs/INTEGRATION.md#git-integration` -- rewritten: `#hooks-installed` (was the
  line-range anchor `#hooks-installed-hooks-py-23-59`; nothing linked it), `#store-gate`,
  `#hook-failures`, `#sync-tracked-catalog`, `#vanished-cwd`, `#rmx-sync-since-ref`. GMD lint:
  0 errors (3 single-file `dangling-doc` warnings, pre-existing).

### Runs {#green-r1-runs}

- `bug212/green-r1.log` -- both bug-212 files at `faabdfe`: 61 passed, exit 0.
- `bug212/green-r1-family.log` -- 52 files (hooks, sync, discovery/hub, cctree, mcp, cli,
  telemetry, launchctl, bridge-move-safety, docs_generated, verb_parity; list in
  `green-r1-family.files`): **780 passed, 1 skipped, pytest exit 1**. The skip is the SkipGate
  UNPINNED `test_repo_hooks_in_sync::test_installed_hooks_match_generated`, the clone artifact
  from ch-bsd r1 m-4. One src edit (the ping gate around the a2 refusal) landed while this run was
  in flight; the wide run below is the authoritative one on the committed code. An earlier family
  run was killed and discarded, because a `git stash` for a lint comparison briefly reverted src
  under it.
- `bug212/green-r1-wide.log` -- the full suite at `faabdfe`: **4 failed, 4340 passed, 1
  skipped, pytest exit 1**, in 45 min. Compared by E line against `release-0.82.0-full.log`:
  - `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon` -- same E
    (`Could not set lock on file .../catalog.A.duckdb`).
  - `test_task21_1_agent_usage_report` x2 -- same E lines.
  - `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate` --
    the first E line differs from 0.82.0's: `docs/INDEX.md` / `docs/adr/*` dangling ids, not
    the 0.82.0 ledger reference. That is clone scope. The test copies no memory dir for a clone
    slug, so memory refs dangle "as the script intends", and the branch tree differs from
    0.82.0's. It is not this change: `./scripts/lint-gmd.sh` gives 1049 errors both with this
    diff and with it stashed, and the changed docs lint at 0 errors.
  - The 0.82.0 bug-168 rewriter x9 and the `test_installed_hooks_match_generated` failure did not
    reproduce. The latter is a skip here (m-4).

### Mutations {#green-r1-mutations}

Against `faabdfe`, each run over both bug-212 files. The driver
`scratchpad/mut212.py` (not committed) applied one exact single-occurrence replace, ran pytest
to `bug212/green-r1-mut-<id>.log`, then ran `git checkout -- <file>` as its own subprocess,
then checked that `git status --short src` was empty and that the fix text was back. Batch log
`bug212/green-r1-mutations.log`. `__pycache__` was cleared after the batch, and src == HEAD.

| id | mutation | result |
|----|----------|--------|
| G1 | gate: socket half dropped (`if true; then`) | killed: live-daemon guard 2/2 |
| G2 | gate: `[ -z "$TRACKED" ] \|\| exit 0` removed | killed: 20 (16 worktree/clone + 4 main checkout) |
| G3 | gate: ls-files failure branch made a silent `:` | **survived** 61/61 |
| Z | post-commit: empty-tree fallback removed | killed: root-commit test |
| R1 | refusal disabled (`if True: return`) | killed: a2 4 + stale socket 2 |
| P1 | ping gate inverted | killed: same 6 |
| E1 | `git_tracked_catalogs` keeps the hook's `GIT_*` env | **survived** 61/61 |
| E2 | `ls-files` failure read as untracked | **survived** 61/61 |
| E3 | outside a repo read as tracked | killed: outside-git guard + vanished-cwd `sync --since` |
| C1 | `_RmxGroup` converts nothing | killed: 9 (s-1 CLI x7 + contract-4 x2) |
| C2 | `partition_marker` raw `Path.cwd()` | killed: REFMATRIX_ROOT s-1 x5 |
| C3 | `_cwd_root` raw `Path.cwd()` | killed: hub-pause |
| C4 | `mcp._resolve_root` raw `Path.cwd()` | killed: MCP test |
| C5 | `cctree._project_base` raw `Path.cwd()` | killed: cctree |
| C6 | `sync.sync_since` raw `Path.cwd()` | killed: lib `sync_since` |
| C7 | `sync._sync_paths` raw `Path.cwd()` | killed: lib `sync_files` |
| C8 | `current_dir` translates nothing | killed: 14 |
| C9 | `cli_entry` does not catch the cwd error | killed: 12 (incl. the m-1 telemetry guard) |
| W1 | remedy ignores `REFMATRIX_ROOT` (always "set REFMATRIX_ROOT") | **survived** 61/61 |

Not mutated: `_grep_rg_fallback`'s `_cwd()`, which is unreachable in a vanished cwd (a6) and
therefore an equivalent mutant.

### For the lead, the test engineer and the reviewers {#green-r1-flags}

- **Survivors are findings for the test engineer, not papered over.** G3 and E2 are both
  fail-closed `ls-files` failure paths (shell and Python), and no test makes `ls-files` fail; a
  corrupt `.git/index` would. E1: the env strip matters only when the store's repository is not
  the hook's, for example `REFMATRIX_ROOT` naming a store in another repo while a hook runs with
  `GIT_DIR` set (a worktree hook exports an absolute `GIT_DIR`, measured). In the main checkout,
  git's relative `GIT_INDEX_FILE=.git/index` still resolves, because git changes to the top level
  first; that is why E1 survives the current fixtures. W1: no test reads the remedy text, which
  is the very finding behind ch-bsd's "an error message's remedy is a test case".
- **The daemon route still writes a tracked catalog.** With a live daemon the gate passes and
  the daemon writes `catalog.<active>.duckdb`, which git tracks, so `git status` shows it
  modified. That is lead decision a1/a2 as written: the live-daemon guard requires the sync.
  Only bug-214's untracking removes it.
- **a2 covers `rmx sync` only.** Other in-process writers (`rmx ingest`, `memory add`, the
  bridge, ...) reach `_store_rw()` on a tracked catalog unrefused. Putting the check in
  `_store_rw()` would cover them all; that is out of this brief's scope and needs a decision.
- **Daemon-op cwd defaults** (`daemon.py`, a7) still read `Path.cwd()` raw. They are out of scope
  as decided.
- The SkipGate UNPINNED skip (m-4) still turns every clone run into pytest exit 1. There is no
  registry row yet.
- Not touched: bug-209, bug-215, `search_hooks.py:254` (`_os.getcwd()`, the 25.1 clone's file),
  `telemetry.py:595/1317` (each already catches `OSError` on its own `os.getcwd()`).

## RED r2 (GREEN r1's survivors G3/E1/E2/W1; a2 at the write control point) {#red-r2}

Test commit `488a62d`, a new file `tests/test_bug212_r2_red.py` (no `src/` change, no existing
test edited). At `b20f338` (src identical to `faabdfe`): **8 failed, 19 passed**
(`bug212/red-r2-head.log`); with both earlier bug-212 files, **8 failed, 80 passed**
(`bug212/red-r2-head-all3.log`; the 61 r1 tests unchanged). The 8 failures are the a2 REDs below,
each for the right reason; every survivor-killing test passes at HEAD.

rel: depends-on -> [[agent-brief-red-212r2]]
rel: amends -> [[#green-r1-mutations]]
rel: derives-from -> [[#green-r1-flags]]

### The survivors, killed {#red-r2-survivors}

Each test passes at `faabdfe` and fails under its mutation (driver `scratchpad/mut212r2.py`, the
GREEN driver retargeted at the new file; restore by `git checkout -- <file>` in its own command,
src checked clean and the fix text back after each; `__pycache__` cleared after the batch).

| id | test(s) | under the mutation |
|----|---------|--------------------|
| G3 | `test_a_hook_whose_git_ls_files_fails_says_so_and_does_not_sync[<4 hooks>]` | 4 failed: `<hook>: git ls-files failed and the hook did not say ... on stderr` |
| E2 | `test_git_tracked_catalogs_raises_when_ls_files_fails`; `test_an_in_process_sync_refuses_when_git_ls_files_fails` | `git_tracked_catalogs returned [] on a corrupt index`; ``rmx sync` wrote ['catalog.duckdb'] although git could not say whether it tracks them` |
| E1 | `test_git_tracked_catalogs_ignores_a_foreign_git_dir_in_the_environment`; `test_a_worktree_hook_of_one_repo_cannot_vouch_for_a_store_in_another` | `answered from the hook's repository (GIT_DIR in the env)`; `the in-process sync wrote B's git-tracked ['catalog.duckdb']` |
| W1 | `test_the_cwd_gone_remedy_depends_on_refmatrix_root`; `test_a_vanished_cwd_error_offers_refmatrix_root_only_when_unset[root-set]` | `with REFMATRIX_ROOT already set the remedy still says to set it` (function and `rmx stats` end to end) |
| W2 (new) | `test_cctree_in_a_vanished_cwd_says_pass_project[root-set,root-unset]` | cctree's remedy dropped to the default: `cctree's remedy is not pass --project` |

Batch log `bug212/red-r2-mutations.log`, per-mutation `bug212/red-r2-mut-<id>.log`. Each run also
shows the 8 standing a2 REDs; nothing else failed.

- G3/E2 fixture `corrupt_index_repo`: the store is COMMITTED (b-1 shape), then `.git/index` is
  overwritten with non-index bytes; the fixture proves `ls-files` fails and
  `rev-parse --show-toplevel` still works. A commit/checkout/merge cannot run on a corrupt index,
  so the G3 test executes the installed GENERATED hook file directly, as git does (cwd = top
  level; post-checkout gets `<prev> <head> 1`, post-rewrite gets `<old> <new>` on stdin).
  Required: exit 0, no traceback, the exact line `refmatrix: <hook>: git ls-files failed; not
  syncing` on stderr, no `rmx` call (shim), catalog bytes unchanged.
- E1 fixture `two_repos`: repo A (store ignored) with a linked worktree holding its own ignored
  store (so the generated gate passes), repo B with a committed `catalog.duckdb`. The commit in
  A's worktree runs with `REFMATRIX_ROOT=<B store>`; a shim variant records `$GIT_DIR`, and the
  test REQUIRES it absolute and under `/worktrees/` (the E1 shape, observed, not assumed).
  Required: B's catalog byte-identical, one refusal `Error:` naming `catalog.duckdb` plus the
  hook's `rmx sync FAILED` line.

### a2 at the write control point {#red-r2-a2}

- `test_every_in_process_writer_refuses_a_git_tracked_catalog[<slots|legacy>-<ingest|memory-add|bridge>]`
  -- 6 RED. `rmx ingest <dir>`, `rmx memory add <name> -c <body>`, `rmx ingest-gmd --as-memory
  <memdir>`, cwd = `tracked_repo`'s main checkout, no daemon, no `REFMATRIX_ROOT`. Required: no
  traceback; catalog sha256 unchanged; exit non-zero; exactly ONE `Error:` line, and it names the
  target (`catalog.A.duckdb` / `catalog.duckdb`) and both remedies (`untrack`/`rm --cached`, and
  `daemon`) -- the r1 `_refusal_lines` predicate, which does not require the word "sync";
  `git status` clean. HEAD line: `[<layout>] in-process `<writer>` wrote the git-tracked catalog
  ['<target>'] (exit 0)`.
- `test_the_write_control_point_itself_refuses_a_git_tracked_catalog[<layout>]` -- 2 RED. Calls
  `cli._store_rw()` in-process (`REFMATRIX_ROOT` = the tracked store): it must raise
  `ClickException` naming the target, catalog unchanged. HEAD line: `DID NOT RAISE`. This pins
  the lead's decision that the check lives IN `_store_rw()`, not per command.
- GUARD `test_every_in_process_writer_still_writes_an_untracked_catalog[<no-repo|ignored>-<writer>]`
  -- 6, pass at HEAD: exit 0, no `Error:` line, the writer's row is in the catalog. Proven by
  mutation O (`_store_rw()` raises unconditionally): all 6 guards fail
  (`bug212/red-r2-mutations-O.log`).

### For the implementer and the lead {#red-r2-flags}

- Moving the check into `_store_rw()` runs `git rev-parse` + `git ls-files` on every in-process
  write. Suite fixtures that `git add -A` a store (e.g. `test_bridge_move_safety_r1`'s
  `gitproj`) would now be refused -- the GREEN family/wide run will show whether any do.
- The sync refusal text says "refusing an in-process sync"; for `ingest`/`memory add`/the bridge
  that verb is wrong. The tests do not pin the verb, so a neutral wording is free.
- `memory add` reaches `_memory_intent` (a `cli.log` intent row) before the store; that file is
  not a catalog and the tests do not count it.
- Not covered: a corrupt index for the non-sync writers (same function after the move), and the
  daemon-route write to a tracked catalog (lead decision a1/a2: bug-214's untracking).

## GREEN r2 (the refusal at the write control point; RED r2 green) {#green-r2}

Fix commit `ed36b6a` (src only, `src/refmatrix/cli.py`, by pathspec). No test was edited. All
three bug-212 files: **88 passed** (`bug212/green-r2.log`; at `deafd6d` they were 8 failed /
80 passed, `bug212/red-r2-head-all3.log`).

rel: implements -> [[#red-r2]]
rel: amends -> [[#green-r1-changes]]
rel: depends-on -> [[agent-brief-red-212r2]]

### What changed {#green-r2-changes}

- `cli._store_rw() -> Store` now ends its path resolution with
  `_refuse_in_process_write_to_tracked_catalog(s.root, s.db_path)`. That happens after the
  `no refmatrix at ...` check and before anything connects. `Store(...)` only resolves paths
  (`select_backend` only tests whether files exist), so nothing has touched the catalog when
  the refusal raises. `_store_rw()` is the one in-process write control point, so `rmx sync`,
  `rmx ingest`, `rmx memory add`, `ingest-gmd --as-memory`, `tldr-warm`, the repair commands
  and the `_read_store` fallback all reach it (see the flags).
- `cli._refuse_in_process_write_to_tracked_catalog(root: Path, target: Path) -> None`. The new
  `target` parameter is the caller's resolved `db_path`, the file the write would land in. It
  replaces r1's re-derivation from `_active_slot_path()` and the legacy names. The wording is
  now neutral, and each failure prints one `Error:` line:
  - tracked: `refusing an in-process write to <target>: git tracks this store's catalog
    (<names>), and the write would modify a committed file. Untrack it (git rm --cached
    .refmatrix/catalog*, then ignore .refmatrix/ catalog files), or start the daemon (rmx
    daemon start) so the write goes through it`;
  - `ls-files` failed: `refusing an in-process write to <target>: cannot tell whether git
    tracks the catalog under <root>: git ls-files exited N: <git's stderr>; untrack the
    catalog (git rm --cached) if git tracks it, or start the daemon ...`.
- `rmx sync` no longer calls the helper itself, and its `daemon_mod.ping` gate is gone (no
  per-command copy). With a daemon up, `_store()` returns the `_DaemonWriter`, never reaches
  `_store_rw()`, and so is not refused: the same split r1's ping gate made. A stale socket is
  `VerbAbsentError` (`require_daemon`), so it reaches `_store_rw()` and is refused (r1
  stale-socket tests green).
- The survivors keep their r1 code, unchanged and now under test: G3 is the shell gate's
  ls-files branch, E2 the `TrackedCatalogCheckError` raise, E1 the `_GIT_LOCAL_ENV_VARS` strip,
  and W1/W2 the remedy text.

### Runs {#green-r2-runs}

- `bug212/green-r2.log`: the three bug-212 files at `ed36b6a`, **88 passed**.
- `bug212/green-r2-family.log`: 88 files (r1's 52 plus every ingest/memory/cli/discovery/
  cctree/mcp/telemetry/bridge/bug212 file; list in `green-r2-family.files`), **1 failed, 1249
  passed, 1 skipped**. The skip is the SkipGate UNPINNED `test_installed_hooks_match_generated`
  (m-4). The failure is `test_tldr_warm` (below).
- `bug212/green-r2-wide.log`: the full suite at `ed36b6a`, **5 failed, 4366 passed, 1
  skipped**, 46m42s. That is r1's 4340 passed plus the 27 r2 tests, minus the one new failure.
  Compared by E line against `release-0.82.0-full.log` and `green-r1-wide.log`:
  - `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon`: same E
    (`Could not set lock on file .../catalog.A.duckdb`).
  - `test_task21_1_agent_usage_report` x2: same E lines.
  - `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate`:
    the GMD error lines are identical to r1's wide run (clone scope, as r1 recorded).
  - **NEW, caused by this change:**
    `test_sync_and_extras::test_tldr_warm_invokes_binary_and_ingests`. E: `exit_code 1 ...
    AttributeError("'R' object has no attribute 'stdout'")`. The test monkeypatches the
    GLOBAL `subprocess.run` with a fake whose result has only `returncode`. `tldr-warm` then
    ingests through `_store(write=True)` -> `_store_rw()`, whose tracked-catalog check runs
    `git rev-parse` through that fake. Probe `bug212/green-r2-tldr-warm-probe.log` records the
    fake's calls: `[<tldr bin> warm ...], ['git', '-C', <store>, 'rev-parse',
    '--is-inside-work-tree']`. The defect is the over-broad mock, not the product: the store
    is in no repo, and the real git answers `[]`. Not edited (no test edits); see the flags.
  - No suite fixture that `git add -A`s a store was refused. `test_bridge_move_safety_r1`'s
    `gitproj` ignores `.refmatrix/`. `test_verbs_migrated` runs `add -A` before it creates the
    store, and `test_upgrade` / `test_stm_rationale_capture` have no store in the repo.

### Mutations {#green-r2-mutations}

Against `ed36b6a`, each run over all three bug-212 files. Driver
`scratchpad/mut212g2.py` (not committed): every replace is an exact single occurrence; the
driver ran pytest to `bug212/green-r2-mut-<id>.log`, then `git checkout -- src/refmatrix/cli.py`
as its own subprocess, then checked `git status --short src` empty and the control-point call
back. Batch log `bug212/green-r2-mutations.log`. `__pycache__` cleared after the batch, src ==
HEAD.

| id | mutation | result |
|----|----------|--------|
| K1 | the `_store_rw()` call removed (no check anywhere) | killed: 16 (r1 sync x4, stale socket x2, E2 sync, E1, a2 writers x6, control point x2) |
| K2 | r1 shape: check removed from `_store_rw()`, ping-gated copy back in `sync` only | killed: 8 (a2 writers x6, control point x2) |
| K3 | `if not tracked: return` -> `if True: return` | killed: 15 |
| K4 | `TrackedCatalogCheckError` swallowed (`return`) | killed: 1 (`test_an_in_process_sync_refuses_when_git_ls_files_fails`) |
| K5 | `s._connect()` before the refusal (the catalog opens first) | killed: 14 (catalog bytes change). The direct control-point test alone does not see it |
| K6 | tracked line drops `to {target}` | **survived** 88/88 |
| K7 | tracked line drops the untrack remedy | killed: 13 |
| K8 | ls-files-failure line drops `to {target}` | **survived** 88/88 |
| K9 | check asks `Path.cwd()`, not the store root | killed: 15 |

### For the lead, the test engineer and the reviewers {#green-r2-flags}

- **K6 survives (test engineer).** `_refusal_lines` requires the target's BASENAME in the line,
  but the tracked list `(catalog.A.duckdb, ...)` contains that basename too. So a line that
  drops the write target still passes. A predicate on the target's full path (or `to <path>:`)
  would kill it.
- **K8 survives (test engineer).** No test requires the target on the `ls-files`-failure line,
  though the lead's wording decision asks for it there too (the E2 sync test checks
  `ls-files` + remedies only).
- **K5 is killed only end to end.** The direct `_store_rw()` test cannot tell "refused before
  open" from "refused after open", because a bare connect does not change the bytes. The
  subprocess writers catch it.
- **`test_tldr_warm_invokes_binary_and_ingests` now fails (test engineer, mock registry).** The
  global `subprocess.run` fake also answers the store's git probe. The fix belongs in the test:
  scope the fake to the tldr binary and delegate other argv to the real `subprocess.run`, and
  filter `invoked`. Do not reshape src around the mock.
- **Reads can be refused now (lead decision needed?).** `_read_store()` falls to `_store()` ->
  `_store_rw()` when there is no `catalog.read.duckdb` and no daemon. On a tracked store that
  read now gets the write refusal, which is worded as a write. That path opens the writer slot
  read-write (and `close()` flushes), so refusing it is fail-closed. A fleet store normally has
  a replica once its daemon has run. No test covers it.
- **Cost:** every in-process write now runs `git rev-parse` + `git ls-files` (two subprocesses)
  before it opens the catalog. Daemon-routed writes pay nothing.
- **Docs (ch-doc-writer):** `docs/INTEGRATION.md#sync-tracked-catalog` still describes the
  refusal as sync-only and quotes `refusing an in-process sync into <file>`. It needs the
  writer-wide scope and the new wording. Not edited here.
- Unchanged from r1: the daemon route still writes a tracked catalog (a1/a2, bug-214), the
  daemon-op cwd defaults (a7), and the SkipGate UNPINNED skip (m-4).

## RED r3 (GREEN r2's K5/K6/K8, the tldr fake, the read path) {#red-r3}

Test commit `3f84c59` (tests and mock registry only). The 3 bug-212 files plus
`tests/test_sync_and_extras.py` at `ed36b6a`: **18 failed, 99 passed**
(`bug212/red-r3-head.log`). Every E line is the wording: stderr carries the GREEN r2 line
`refusing an in-process write to <path>`, and the new contract is
`refusing to open <full target path> read-write in-process: ...` (lead ruling, 2026-11-13).

rel: derives-from -> [[#green-r2-mutations]]
rel: derives-from -> [[#green-r2-flags]]

### What changed {#red-r3-changes}

- `_refusal_head(target)` and `_refusal_lines(stderr, target: Path)`
  (`tests/test_bug212_r1_remedy.py`) require the FULL target path inside the head. The basename
  alone also appears in the tracked-names list, which is why K6 survived. Every refusal
  assertion uses them: r1 sync x4, stale socket x2, E1, writers x6, and read x2. The E2 sync test
  requires the head plus `ls-files exited` (K8). The direct `_store_rw()` test requires the
  head.
- K5. The direct `_store_rw()` test wraps `Store._connect` with a RECORDER that calls the real
  method, and it requires no connect to this store's catalog before the refusal. New
  mock-registry row: `internal-active (observer)`, a collaborator double, not a SUT double.
- Read path (flag 5). Measured at `ed36b6a`: "no `catalog.read.duckdb`" alone does NOT reach
  `_store_rw()`. `_replica_reader_path()` falls back to the INACTIVE slot or the legacy
  `catalog.duckdb` and opens that file read-only. In `tracked_repo`'s two layouts, `pairs show`
  exits 0 and `memory get` answers "no memory matching". The fall-through needs every reader
  file absent. So the RED `test_a_read_with_no_replica_on_a_tracked_catalog_is_refused_as_an_open`
  uses `slot_only_tracked_repo`: `active` = A, only `catalog.A.duckdb`, which is committed. It
  runs `pairs show` and `memory get`: ONE refusal line, no "in-process write", bytes unchanged.
  GUARD `test_a_read_on_a_tracked_store_with_a_reader_file_is_served_not_refused` (both layouts)
  passes at `ed36b6a`.
- `test_tldr_warm_invokes_binary_and_ingests`: the `subprocess.run` fake answers only the fake
  tldr binary's argv and delegates every other argv to the real `subprocess.run`. `invoked`
  records only tldr calls, and the test asserts exactly one. Its registry row is updated. It
  passes at `ed36b6a`.

### Satisfiability and mutation probe {#red-r3-probe}

Driver `scratchpad/probe212r3.py` (not committed). It applies W (the lead's wording on both
lines, as GREEN will), then W+K, over the 4 files. src is restored by `git checkout --` in its
own subprocess after each run, src is checked clean, and `__pycache__` is cleared after the
batch. Log: `bug212/red-r3-probe.log`.

| run | result |
|-----|--------|
| W | 117 passed: the contract is satisfiable by a wording-only change |
| W+K5 (`s._connect()` before the refusal) | 18 failed, incl. control point x2: `` `_store_rw()` connected to [...catalog.A.duckdb] BEFORE refusing `` |
| W+K6 (tracked line drops the target) | 17 failed |
| W+K8 (`ls-files` line drops the target) | 1 failed: the E2 sync test, `the refusal does not start ...` |

## GREEN r3 (the open-wording contract; RED r3 green) {#green-r3}

Fix commit `cd3abe8` (`src/refmatrix/cli.py` + `docs/INTEGRATION.md`, by pathspec). No test
was edited. The 3 bug-212 files plus `tests/test_sync_and_extras.py`: **117 passed**
(`bug212/green-r3.log`; at `ed36b6a` they were 18 failed / 99 passed, `bug212/red-r3-head.log`).

rel: implements -> [[#red-r3]]
rel: amends -> [[#green-r2-changes]]

### What changed {#green-r3-changes}

- `cli._refuse_in_process_write_to_tracked_catalog(root: Path, target: Path) -> None` (same
  signature): only the two f-string heads changed. Both are now
  `refusing to open {target} read-write in-process: ...`, where `target` is `_store_rw()`'s
  resolved full `db_path`. The text after the colon is unchanged, and the `ls-files` variant
  keeps `git ls-files exited N`. No other src changed.
- `docs/INTEGRATION.md#sync-tracked-catalog` (anchor kept; heading "No command opens a tracked
  catalog read-write in-process") now covers:
  - every writer behind `_store_rw()`;
  - the read fall-through (a reader file serves the read; only with none of
    `catalog.read.duckdb` / `read_only.duckdb` / inactive slot / legacy `catalog.duckdb`, and
    no daemon, does a read reach the refusal);
  - the live-daemon case;
  - the new wording of both lines.
  GMD lint: 0 errors, 3 pre-existing single-file `dangling-doc` warnings.

### Runs {#green-r3-runs}

- `bug212/green-r3.log`: 117 passed. This includes the read-path RED
  (`slot_only_tracked_repo`, `pairs show` / `memory get`) and the guard
  `test_a_read_on_a_tracked_store_with_a_reader_file_is_served_not_refused`.
- `bug212/green-r3-wide.log`: the full suite at `cd3abe8` (`__pycache__` cleared first),
  **4 failed, 4371 passed, 1 skipped**, 46m35s. The skip is the SkipGate UNPINNED (m-4). By E
  line against `green-r2-wide.log` (normalised for tmp dirs, pids, addresses;
  `bug212/green-r3-wide-elines.txt`):
  - gone: `test_sync_and_extras::test_tldr_warm_invokes_binary_and_ingests` (the fake is now
    scoped to the tldr binary, `3f84c59`);
  - new: none;
  - SAME E lines: `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon`,
    `test_task21_1_agent_usage_report` x2, and
    `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate`.
    These match 0.82.0 / r1 as recorded in `#green-r2-runs`.

### For the lead and the reviewers {#green-r3-flags}

- The function's docstring still says the refusal "is worded for any write, not a sync" (r2).
  Under the r3 contract it is worded as an open. The brief said to change no other src, so it
  was left. It is a one-sentence docstring fix for the next src touch.
- The text after the colon still says "the write would modify a committed file" and "so the
  write goes through it", even when the caller is a read that fell to `_store_rw()`. That is
  per the brief (after the colon unchanged), and the RED r3 read test passes with it (it
  forbids only "in-process write").
- No mutation batch this round. The change is wording only, and RED r3's probe already ran W,
  W+K5, W+K6 and W+K8 on this exact wording (`#red-r3-probe`).

## RED r4 (ch-bsd r2 at 67f55cb: b-1, m-1, m-3, m-4; ruling L72) {#red-r4}

The test commit is `1c7cf4c`. It adds the new file `tests/test_bug212_r4_red.py` and edits one
assertion in `tests/test_bug212_r2_red.py` for m-1. Results at `67f55cb`:

- r4 file: **30 failed, 6 passed** (`bug212/red-r4-head.log`).
- The 4 earlier files: **2 failed, 115 passed** (`bug212/red-r4-head-prior4.log`). The 2
  failures are the m-1 read pair.

Every RED fails for the reason it names. The E lines are below.

rel: derives-from -> [[bsd-bug212-r2-67f55cb]]
rel: amends -> [[#red-r3]]

### RED at 67f55cb, by item {#red-r4-items}

| item | test(s) | E line at 67f55cb |
|------|---------|-------------------|
| b-1 CLI | `test_every_cli_writer_outside_store_rw_refuses_a_git_tracked_catalog[<slots/legacy>-<add-concept, add-entity, protect, noise, focus-change-subject, init, partition-drop>]` (14) | `` `rmx <argv>` wrote the git-tracked catalog ['catalog.A.duckdb' / 'catalog.duckdb'] (exit 0) `` |
| b-1 MCP | `test_the_mcp_memory_add_fallback_refuses_a_git_tracked_catalog[slots, legacy]` | `MCP rmx_memory_add wrote the git-tracked catalog [...]: '{"id": 1}'` |
| b-1 promote | `test_the_save_state_promote_fallback_refuses_a_git_tracked_catalog[slots, legacy]` | `the promote wrote the git-tracked catalog [...]: {'name': 'focus_summary_…', 'id': 1}` |
| b-1 AST | `test_no_read_write_store_open_outside_the_allowlist` | `cli:init (951)`, `cli:partition_drop (4266)`, `handoff:_promote_digest (381)`, `mcp:_t_memory_add (121)`, `verbs:change_subject (1574)` |
| b-1 AST | `test_both_checked_openers_call_the_one_store_level_check` | `store.py has no function that calls git_tracked_catalogs` |
| m-1 | `test_bug212_r2_red.py::test_a_read_with_no_replica_on_a_tracked_catalog_is_refused_as_an_open[pairs-show, memory-get]` | `a READ's refusal claims a write: "... and the write would modify a committed file ..."` |
| m-3 | `test_a_hanging_git_raises_the_check_error_within_the_timeout[<layout>-<rev-parse-hangs, ls-files-hangs>]` (4) | `git_tracked_catalogs did not return within 45s with git hanging` |
| m-3 | `test_an_in_process_writer_with_a_hanging_git_fails_loudly[slots, legacy]` | `` `rmx sync --files` with git hanging did not finish within 45s: a silent hang `` |
| m-4 | `test_a_failing_rev_parse_inside_a_repository_raises[slots, legacy]` | `git_tracked_catalogs returned [] with a corrupt .git/HEAD` |
| m-4 | `test_an_in_process_writer_in_a_repository_with_a_corrupt_head_refuses[slots, legacy]` | `the in-process sync wrote the tracked catalog (corrupt HEAD read as 'not a repository')` |

The six passing tests:

- **GUARDs** that pass at `67f55cb`:
  - `test_a_foreign_git_dir_in_the_env_does_not_hide_a_tracked_catalog[slots, legacy]`;
  - `test_a_writer_with_a_foreign_git_dir_in_the_env_still_refuses[slots, legacy]`.

  HEAD already strips the env on both calls, so these cannot be RED there. Mutation X3 proves
  them: X3 keeps `os.environ` on the `rev-parse` call, and all 4 fail with "the check answered []"
  / "wrote the git-tracked catalog" (`bug212/red-r4-mut-X3.log`, 34 failed). src was restored with
  `git checkout --` in its own command and checked clean, and `__pycache__` was cleared.
- **Scanner guards:**
  - `test_the_census_scanner_sees_the_known_openers`: the scanner is shown to FIND opens;
  - `test_the_allowlist_names_no_site_that_no_longer_opens`: stale allowlist entries fail.

### Design notes {#red-r4-notes}

- The census is alias-aware: `Store` under any name bound in the module, `<mod>.Store`, and
  `X = Store`. It found a fifth hand-rolled writer that ch-bsd r2 did not list:
  `cli.partition_drop` opens `Store` imported as `_Store` and DELETEs a partition row. It got
  a CLI RED of its own (`partition-drop`), seeded with an empty partition.
- The allowlist has two parts:
  - CHECKED: `cli:_store_rw` and `verbs:local_write`.
  - UNCHECKED, each with a reason: `daemon:Daemon._reopen_writer`, `Daemon.serve_forever` and
    `Daemon._bootstrap_rotation_if_needed` (the daemon is the accepted writer, a1/bug-214);
    `hub:_bootstrap_global_store`; `store:Store.link_canon`.
- "One store-level check" means a function in store.py, other than `git_tracked_catalogs`
  itself, that calls `git_tracked_catalogs`. Each checked opener must call it directly or
  through one wrapper. A CLI wrapper that turns the refusal into a `ClickException` therefore
  passes; the name of the check is not pinned.
- m-3's bound is 45 s against L72's fixed `timeout=10`. No override is exposed, so it is a
  timing test. At HEAD the 6 hang tests cost about 4.5 min, because each runs to the bound.
  After the fix they should cost about 10 s each. The shim is registered as `external`.

### For the implementer and the lead {#red-r4-flags}

- `cli.partition_drop` is a fifth bypass. L72 names four. It needs routing too; the AST test
  already fails on it.
- `sync.changed_since` runs `git diff` with no timeout. The post-commit hook's `rmx sync
  --since` calls it before any store opens, so a hanging git still hangs that background sync.
  This is outside L72's m-3 scope (which covers `git_tracked_catalogs` only); it is a
  candidate row.
- `_promote_digest` keeps its "never raises, returns {error}" contract, and the test pins the
  refusal inside `error`. Whether `rmx save-state` prints that error loudly is not tested here.
- `rmx focus change-subject` has no `VerbError` -> `ClickException` translation. Once
  `change_subject` routes through `local_write`, the CLI must still print exactly one `Error:`
  line, not a traceback (the test requires one).

### L82 additions {#red-r4-l82}

Two more RED tests, ordered by ruling L82 on 2026-11-13, are in `tests/test_bug212_r4_red.py`.
Run at `67f55cb`, the r4 file gives **34 failed, 6 passed** (`bug212/red-r4b-head.log`). The 30
earlier r4 REDs are unchanged.

- `test_save_state_whose_promote_is_refused_says_so_on_stderr_and_exits_non_zero[slots, legacy]`.
  It runs `rmx save-state -s <s> --memory-dir <tmp> --no-sync --no-lint` with no daemon, on a
  tracked catalog. `--no-sync` leaves the promote as the only store write.
  - Required: the handoff file is written, the catalog bytes are unchanged, the refusal head
    appears on STDERR, and the exit is non-zero.
  - HEAD line: `save-state's promote wrote the git-tracked catalog [...]`. The stdout shows
    `promoted focus_summary_… (id=1)`.
  - A promote error is printed today as `promote skipped:` on stdout, with exit 0. That is the
    silent path this test closes.
- `test_changed_since_with_a_hanging_git_diff_raises_within_the_bound`, run with the `git` shim
  in `diff` mode on a repo whose store is ignored.
  - Required: `sync.changed_since` raises a `RuntimeError` naming the timeout within 45 s. It must
    be a `RuntimeError` because every `--since` caller turns one into a single `Error:` line; a
    bare `TimeoutExpired` would surface as a traceback.
  - HEAD line: `did not return within 45s with git diff hanging`.
- `test_sync_since_with_a_hanging_git_diff_fails_loudly` covers the post-commit path end to end:
  `rmx sync --since HEAD~1`.
  - Required: one `Error:` line naming the timeout, and a non-zero exit, within 45 s.
  - HEAD line: `did not finish within 45s: a silent hang`.

## GREEN r4 (one store-level check, two openers; rulings L72 + L82) {#green-r4}

Fix commits `8b23c5a` (src + `docs/INTEGRATION.md`) and `ef8b38c` (the `create=True` fixup the
family run asked for). No test was edited.

- The r4 file plus the 4 earlier bug-212-related files (`test_bug212_hooks_in_worktrees`,
  `_r1_remedy`, `_r2_red`, `test_sync_and_extras`): **157 passed** at `8b23c5a`
  (`bug212/green-r4-first.log`). At `f7578dd` the r4 file alone was 34 failed / 6 passed.
- The AST bypass guard is green with the test's allowlist unchanged. So are its census-sees
  and stale-allowlist guards.

rel: implements -> [[#red-r4]]
rel: implements -> [[#red-r4-l82]]
rel: amends -> [[#green-r3-changes]]

### What changed {#green-r4-changes}

- `store.py` (the one store-level check, L72 b-1):
  - `class TrackedCatalogRefused(RuntimeError)`;
  - `refuse_tracked_catalog_open(root: Path, target: Path) -> None`. It raises the refusal
    line `refusing to open <target> read-write in-process: ...`. The tail is now neutral (m-1):
    "...and opening it read-write would modify a committed file. Untrack it (...), or start
    the daemon (rmx daemon start) so the daemon opens it instead". No "the write" remains.
  - `git_tracked_catalogs` now runs both git calls through
    `_run_git_check(args, *, root, env)`, with `timeout=GIT_CHECK_TIMEOUT_S` (10). A timeout
    raises `TrackedCatalogCheckError` ("git <call> timed out after 10s") (m-3).
  - A `rev-parse` failure is `[]` only when `_git_dir_at_or_above(root)` finds no `.git` at
    `root` or any parent; otherwise it raises (m-4). The env strip covers both calls (X3).
- The two checked openers both call that function and translate its refusal:
  - `cli._store_rw()` turns `TrackedCatalogRefused` into a `ClickException`. The cli-level
    `_refuse_in_process_write_to_tracked_catalog` is gone; its r3 docstring flag is closed with
    it.
  - `verbs.local_write(root, fn, *, partition: str | None, create: bool = False)` raises it
    as a `VerbError` before `fn` runs. `partition=None` gives the store's default partition.
    `create=True` allows a missing catalog.
- The five bypasses route through `local_write`:
  - `cli.init` (`create=True`; a missing store dir answers `[]` without running git);
  - `cli.partition_drop` (`partition=None` keeps the hand-rolled open's ACTIVE partition;
    `create=False`);
  - `mcp._t_memory_add`'s no-daemon fallback (a refusal is `{"error"}`, which becomes
    `isError`);
  - `handoff._promote_digest` (a refusal is `{"error": "VerbError: refusing ..."}`);
  - `verbs.change_subject`.

  The last three pass `create=True` (`ef8b38c`). Their hand-rolled `Store(root)` created a
  missing catalog, and the family run caught `local_write` refusing that:
  `test_mcp_session_pointer::test_every_stm_write_verb_reports_its_source[change_subject]`,
  E `no refmatrix catalog ... run rmx init first`.
- L82:
  - `rmx focus change-subject` turns a `VerbError` into one `Error:` line.
  - `sync.changed_since` runs `git diff` with `timeout=GIT_DIFF_TIMEOUT_S` (10) and raises
    `GitTimeoutError(RuntimeError)`: `sync --since <ref> failed: git diff timed out after 10s
    in <project>`. `rmx sync`'s in-process route catches it next to `GitRefError`.
  - `rmx save-state` with a promote error prints `promote FAILED ...` on stdout, finishes (the
    handoff is already written; the bridge and `--commit` still run), then raises one
    `Error: save-state wrote <target> but its promote failed: <error>` on stderr, exit 1. This
    applies to every promote error, not only refusals.
- `docs/INTEGRATION.md#sync-tracked-catalog` now covers:
  - both openers and who reaches each, and the AST census;
  - the real reader order (with an `active` marker, only the inactive slot; without one,
    legacy `catalog.duckdb`) (m-2);
  - the measured cost;
  - the unknown-answer cases (ls-files failure, rev-parse failure under a `.git`, 10 s
    timeout);
  - the bounded `--since` diff.

  GMD lint: 0 errors.

### Runs {#green-r4-runs}

- `bug212/green-r4-family.log`: 107 files (r2's list plus every save-state, handoff, focus,
  partition, init, subject, verb, matrix, stm, promote, recall-state, protect and noise file;
  `green-r4-family.files`), at `8b23c5a`. Result: **1 failed, 1574 passed, 1 skipped**. The
  failure is `test_mcp_session_pointer[change_subject]`, above, and it is fixed in `ef8b38c`.
  `bug212/green-r4-fixup.log` (`test_mcp_session_pointer.py` + the r4 file at `ef8b38c`): **102
  passed**.
- `bug212/green-r4-check-cost.log`: `refuse_tracked_catalog_open` on a small repo, n=20. Median
  23.8 ms tracked and 27.0 ms ignored. INTEGRATION.md states "about 25 ms on a small idle
  repository, roughly 30-100 ms on a large or busy one".
- `bug212/green-r4-wide.log`: the full suite at `ef8b38c` (`__pycache__` cleared), **5 failed,
  4410 passed, 1 skipped**, 58m01s. The machine was loaded (r3 took 46m35s). The skip is the
  SkipGate UNPINNED (m-4). By E line (`green-r4-wide-elines-vs-0820.txt`, `-vs-r3.txt`):
  - SAME E lines as 0.82.0: `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon`,
    and `test_task21_1_agent_usage_report` x2.
  - `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate`:
    the E lines differ from 0.82.0's (clone scope: `docs/INDEX.md` / `docs/adr/*` dangling ids,
    as r1-r3 recorded) and are IDENTICAL to green-r3's (22/22).
  - 0.82.0's bug-168 rewriter x9, `test_env_assignments_survive_in_place` and
    `test_installed_hooks_match_generated` do not fail here; the last is the clone's skip.
  - **NEW vs r3:** `test_task21_1_recall_skip::test_ac2b_live_daemon_recall_writes_one_ok_recall_row`,
    E `assert 'skipped_budget' == 'ok'`, a live-daemon recall over its 5 s budget. Re-run
    alone at `ef8b38c` it is **8 passed** (`bug212/green-r4-recall-skip-rerun.log`). The test
    goes through no in-process opener (the file names none of `local_write`, `_store_rw` or the
    check). Read as load, not this change: one rerun, not proven.

### Mutations {#green-r4-mutations}

The spot-checks ran in a THROWAWAY clone, `/Volumes/littlebig/refmatrix-bug212-mut4`, at
`8b23c5a`. `ef8b38c` touches none of the mutated lines. The driver was `scratchpad/mut212g4.py`
(not committed). For each mutation it applied every replace as an exact single occurrence, ran
pytest to `bug212/green-r4-mut-<id>.log`, restored each file with `git checkout --` in its own
command, then checked `git status --short src` empty and the fix text back. The batch log is
`bug212/green-r4-mutations.log`. The copy's `__pycache__` was never imported by the real
clone, and the real clone's was cleared before the wide run.

| id | mutation | result |
|----|----------|--------|
| N1 | `local_write` skips the check | killed: 21 (CLI writers x14, MCP x2, promote x2, save-state x2, both-openers AST) |
| N2 | `_store_rw` skips the check | killed: 13 (both-openers AST, sync hang/GIT_DIR/corrupt-HEAD x6, r1 sync/stale-socket x6) |
| N3 | no git timeout in the check | killed: 6 (hang tests, each at the 45 s bound) |
| N4 | rev-parse failure always `[]` | killed: 4 (corrupt-HEAD x4) |
| N5 | env strip dropped | killed: 2 (GIT_DIR guards) |
| N6 | the tail says "the write" again | killed: 2 (r2 read pair) |
| N7 | save-state promote error not raised | killed: 2 |
| N8 | `changed_since` unbounded | killed: 2 |
| N9 | change-subject CLI translates nothing | killed: 2 |
| N10 | `init` with `create=False` | killed: 9 (`test_session_cli` / `test_v2_features`) |
| N11 | `GitTimeoutError` uncaught in `rmx sync` | killed: 1 |

11 of 11 killed.

### For the lead and the reviewers {#green-r4-flags}

- **The throwaway mutation clone was not removed.** `rm -r /Volumes/littlebig/refmatrix-bug212-mut4`
  was blocked by a safety check that flags top-level paths on a mounted drive. It is a clean
  clone at `8b23c5a` with a `.venv-eval` symlink. Delete it by hand.
- **`create=True` at the three bootstrap fallbacks** keeps their old behaviour on a store
  with no catalog: they create one. Whether `change-subject`, an MCP memory add or a promote
  should ever create a catalog is a separate question; "store creation is explicit (`rmx
  init`)" says no. `partition_drop` keeps `create=False`, so on a missing catalog it is now
  `Error: no refmatrix catalog ...` instead of silently creating one.
- **The save-state promote failure is loud for EVERY promote error** (busy daemon, refused,
  crash), not only the tracked-catalog refusal. A busy-daemon promote now exits 1 where it
  printed `promote skipped:` and exited 0. No test pinned the old line. MCP `rmx_save_state`
  still returns `promoted.error` inside a non-error reply. That path is not covered by L82.
- **`change_subject` sets the STM subject before the store write.** A refused subject write
  leaves the session's STM subject set and the durable subject row absent, with one `Error:`
  line saying so.
- **`partition_drop` and `init` still gate on `daemon_mod.ping`, not `require_daemon`.** A
  busy daemon (alive, not answering) still sends them to the in-process route. That route is
  now checked for tracking, but it still opens the writer slot under a busy daemon. This is
  pre-existing and out of the rulings' scope.
- The recall-skip flake: one rerun passed; it was not re-run in a full suite.

## RED r5 (ch-bsd r4 at 03d7b27: b-1, s-1, m-1..m-5; ruling L95) {#red-r5}

The test commit is `076d861`. It adds the new file `tests/test_bug212_r5_red.py`. In
`tests/test_bug212_r4_red.py` it rewrites the census and adds a `--commit` parameter to the
L82 save-state test. At `03d7b27`, the r4 and r5 files together give **14 failed, 48 passed**
(`bug212/red-r5-head.log`). Each RED fails for the reason it names. Every test that passes at
`03d7b27` is either a GUARD that its ch-bsd r4 mutation kills, or a census self-check.

rel: derives-from -> [[bsd-bug212-r4-03d7b27]]
rel: amends -> [[#red-r4]]

### RED at 03d7b27 {#red-r5-red}

| item | test(s) | E line at 03d7b27 |
|------|---------|-------------------|
| b-1 (i) | `test_compact_refuses_a_git_tracked_catalog[slots, legacy]` | `` `rmx compact` rewrote the git-tracked catalog ['catalog.A.duckdb', 'catalog.duckdb'] (exit 0) ``; legacy: `['catalog.duckdb']` |
| b-1 (ii) | `test_compact_refuses_before_it_stops_a_running_daemon[slots, legacy]` | `` `rmx compact` on a tracked catalog stopped the running daemon (pid N -> None, answering=False) `` |
| b-1 (iii) | `test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog` | `` `rmx migrate-to-duckdb --overwrite` rewrote the git-tracked catalog ['catalog.duckdb'] (exit 0) `` |
| b-1 (iv) | `test_bug212_r4_red.py::test_every_checked_opener_calls_the_one_store_level_check` | `checked openers that do not call the store-level check ['refuse_tracked_catalog_open'] ...: ['cli:compact', 'cli:migrate_to_duckdb']` |
| s-1 | `test_save_state_whose_memory_bridge_is_refused_says_so_on_stderr_and_exits_non_zero[slots, legacy]` | `the bridge refusal (`refusing to open …catalog.A.duckdb read-write in-process: ...`) is not on stderr` |
| m-3 | `test_mcp_save_state_with_a_refused_promote_is_an_error_reply[slots, legacy]` | `MCP rmx_save_state with a refused promote did not reply as an error carrying the refusal: isError=False body='{"mem_id": …` |
| m-4 | `test_a_refused_change_subject_leaves_the_stm_subject_unchanged_and_says_so[slots, legacy]` | `a refused change-subject switched the STM subject to 'bug212 r5 new subject'` |
| m-5 | `test_init_and_partition_drop_refuse_the_in_process_route_under_a_busy_daemon[init, partition-drop]` | `` `rmx init --no-hooks --no-agents` took the in-process route under a busy daemon (exit 0) ``; `partition drop` the same |

### The census, keyed on the resource {#red-r5-census}

The census is `_scan_source` / `_census` in the r4 file. It records three families:

- `store`: a read-write `Store(`, under any alias.
- `raw`: an `open_duckdb(` or `duckdb.connect(` call whose path is not the literal `":memory:"`
  and which does not pass `read_only=True`.
- `move`: `.rename` / `.replace` / `.unlink` / `os.*` / `shutil.move` on a writer-catalog path.
  A writer-catalog path is a catalog name, a slot f-string, a `db_path`,
  `_active_slot_path()` / `_replica_file()`, or a local variable bound to one of these. The read
  replica `catalog.read.duckdb` is not counted.

Checked openers (they must call the store-level check):

- `cli:_store_rw`
- `verbs:local_write`
- `cli:compact`
- every caller of the library opener `migrate:migrate_catalog`, found by a census of its call
  sites; today that is `cli:migrate_to_duckdb`.

Allowed without a check:

- the three daemon writer sites
- `daemon:_op_replica_merge`
- `daemon:Daemon._repair_missing_slot_locked`
- `replica_merge:merge_slots`, which a test shows is called only from daemon.py
- `hub:_bootstrap_global_store`
- `store:Store.link_canon`
- `store:Store.rebuild_index_from_log`
- `backend:_open_write`
- `backend:DuckDBBackend.connect`

Self-checks, all passing:

- the "sees" guard, one site per family: `cli:_store_rw`, plus `cli:compact` for both `raw` and
  `move`, plus `migrate:migrate_catalog`;
- the synthetic module, which carries a positive and a negative per family (Y6);
- stale allowlist entries fail;
- a library opener's caller is found;
- daemon-only sites have only daemon callers.

### GUARDS, each proven by its mutation (`bug212/red-r5-mutations.log`) {#red-r5-guards}

Each mutation was applied as one exact, single-occurrence replace. src was restored with
`git checkout --` in its own command, src and tests were checked clean with the original text
back, and `__pycache__` was cleared afterwards.

| mutation | guard | under the mutation |
|----------|-------|--------------------|
| Y2: `local_write` checks only if the file exists | `test_a_deleted_tracked_catalog_is_refused_and_not_recreated[slots, legacy]` (`rmx init`, every tracked catalog ` D`) | 2 failed: `` `rmx init` re-created the tracked ['catalog.duckdb'] `` |
| Y5b: MCP fallback `create=False` | `test_the_mcp_memory_add_fallback_creates_a_missing_catalog` | 1 failed: `{"error": "no refmatrix catalog … run rmx init first"}` |
| Y5c: promote `create=False` | `test_the_save_state_promote_creates_a_missing_catalog` | 1 failed: `VerbError: no refmatrix catalog …` |
| Y7: promote raise only without `--commit` | `test_save_state_whose_promote_is_refused_…[commit]` (both layouts) | 2 failed: `the promote refusal … is not on stderr` |
| Y6: `_store_aliases` returns `{"Store"}` (test code) | `test_the_census_scanner_finds_every_family_in_a_synthetic_module` | 1 failed: `the scanner missed [('aliased_assign', 'store'), ('aliased_import', 'store')]` |

### For the implementer and the lead {#red-r5-flags}

- The guards and census self-checks pass at `03d7b27` by design: L95 asks for pins of
  behaviour that r4 shipped and ch-bsd verified. They are kept and labelled GUARD, with
  mutation evidence. The lead may drop any of them.
- m-4 wording contract: the one `Error:` line must carry the refusal head AND say the subject
  was left alone: `subject` plus one of `unchanged`, `not changed`, `not set` or `kept`.
- m-5 contract: one `Error:` line containing `busy`, a non-zero exit, catalog bytes unchanged,
  and the partition still registered.
- m-3 contract: the reply has `isError` set, carries the refusal head, and the handoff is still
  written. That matches the CLI, which writes the handoff and then exits 1.
- What a static census cannot see: a catalog path produced by a helper the regex does not
  name. The behaviour tests are the backstop. `sqlite3.connect` is not scanned, per L95's
  list. Its src uses are the SQLite backend's own connect and the hub bus database.
- The MCP-server half of the m-3 fix only works if the verb or the adapter marks the reply
  `isError`. The dispatcher sets it only for a top-level `error` key.

## GREEN r5 (ruling L95: compact, migrate, save-state errors, change-subject, busy gate) {#green-r5}

Fix commit `a1bde19` (`src/refmatrix/cli.py`, `src/refmatrix/verbs.py`,
`docs/INTEGRATION.md`, by pathspec). No test was edited. One existing test now contradicts the
L95 contract; it is flagged below and was not edited.

rel: implements -> [[#red-r5]]
rel: derives-from -> [[bsd-bug212-r4-03d7b27]]
rel: amends -> [[#green-r4-changes]]

### What changed {#green-r5-changes}

- **b-1.** `cli._refuse_tracked_catalog_open(root: Path, target: Path) -> None` is the CLI's
  one wrapper over `store.refuse_tracked_catalog_open`, turning the refusal into a
  `ClickException`. It is called by:
  - `_store_rw()`, which before r5 had its own try/except;
  - `compact`, right after it resolves the writer slot and BEFORE `daemon.ping` /
    `stop_daemon` (target: the slot, or the legacy `catalog.duckdb`);
  - `migrate_to_duckdb`, before `migrate.migrate_catalog` unlinks and rebuilds the
    destination (target: `dst`).
  INTEGRATION.md's heading claim is true again. The section names the daemon (its writer, its
  slot merge and repair) and the hub's global store as the unchecked exception, and describes
  the resource-keyed census.
- **s-1 + m-3: one mechanism, in the verb.**
  - New `verbs.SaveStateIncompleteError(VerbError)`, `__init__(self, message: str, result:
    dict)`.
  - `verbs.save_state` raises it AFTER the handoff is written and finalize has run, when the
    promote or the memory bridge failed. The message is `save-state wrote <target> but its
    promote failed: ...`, or `... its memory bridge failed: ...`, or both joined by `; and `.
  - The CLI catches it, renders `e.result` (stdout says `promote FAILED` / `memory bridge
    FAILED -- the error follows on stderr`), runs `--commit`, then raises `str(e)` as its one
    `Error:` line, exit 1.
  - The CLI no longer builds the line itself (r4's `promote_error` is gone).
  - MCP's `_verb_tool` turns the VerbError into `{"error"}`, which the dispatcher replies as
    `isError`.
- **m-4.** `verbs.change_subject` writes the durable subject row first (daemon
  `subject_upsert`, or `local_write` when absent) and calls `Stm.set_subject` only after it
  lands. Any `VerbError` from the write is re-raised with the same type, with `; the session's
  subject is unchanged (still '<old>')` (or `(none set)`) appended. The CLI's existing
  translation prints it as one `Error:` line.
- **m-5.** `init` and `partition_drop` classify the daemon with `verbs.require_daemon`, not
  `daemon.ping`:
  - up keeps the daemon route (`partition_drop`'s RPC; `init`'s "reusing");
  - busy is one `Error: daemon busy pid=... -- \`rmx <cmd>\` will not open the catalog
    in-process under it`;
  - absent keeps the in-process route.

### Runs {#green-r5-runs}

- `bug212/green-r5-r4r5.log`: the r4 and r5 files at the working tree that became `a1bde19`,
  **62 passed**. At `03d7b27` it was 14 failed / 48 passed. Every GUARD (Y2, Y5b, Y5c, Y7, Y6)
  stays green.
- `bug212/green-r5-prior.log`: `test_bug212_hooks_in_worktrees`, `_r1_remedy`, `_r2_red`,
  `test_mcp_session_pointer` and `test_sync_and_extras`, **179 passed**.
- `bug212/green-r5-family.log`: r4's 107 files plus the r5 file (`green-r5-family.files`), at
  `a1bde19`. Result: **1597 passed, 1 skipped**, no failure. Pytest exits 1 for the SkipGate
  UNPINNED skip (m-4 of r1).
- `bug212/green-r5-wide.log`: the full suite at `a1bde19` (`__pycache__` cleared), **5
  failed, 4432 passed, 1 skipped**, 47m35s. By E line against `green-r4-wide.log`
  (`green-r5-wide-elines-vs-r4.txt`):
  - SAME E lines: `test_brief_real_daemon` (1/1), `test_task21_1_agent_usage_report` x2
    (29/29, 16/16), and `test_gmd_lint_requires_version` (22/22). The last is bug-155, fixed on
    master; this branch predates the fix. Reported, not counted.
  - Gone: `test_task21_1_recall_skip::test_ac2b_live_daemon_recall_writes_one_ok_recall_row`
    (bug-228, the flake) did not recur.
  - **NEW, caused by this change, a test that contradicts L95:**
    `test_plan3_remedy_r3.py::test_promote_digest_reports_busy_and_never_opens_the_store`, at
    line 45. E: `SaveStateIncompleteError: save-state wrote .../mem/savestate_s1.md but its
    promote failed: VerbBusyError: daemon busy pid=... (alive, not answering ...)`.
    - The test calls `verbs.save_state` under a busy daemon and expects a RETURNED result whose
      `promoted.error` says busy (lines 45-47).
    - L95's contract is that the verb RAISES once the handoff is written. Its message carries
      the busy error, and `e.result["promoted"]["error"]` holds the same dict the test reads.
    - The test's other half passed before line 45: `_promote_digest` reports busy and opens no
      catalog (line 44).
    - The family list did not include `test_plan3_remedy_r3.py`; the wide run found it.

### Mutations {#green-r5-mutations}

The spot-checks ran in the throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4`, moved to
`a1bde19` by fast-forward. The driver was `scratchpad/mut212g5.py` (not committed); every mutant
was compiled before the batch. Each mutation ran against the r4 + r5 files and was logged to
`bug212/green-r5-mut-<id>.log`. Every touched file was restored with `git checkout --` in its
own command, then `src` was checked clean with the fix text back. `__pycache__` was cleared in
the copy and in the clone afterwards. Batch log: `bug212/green-r5-mutations.log`.

| id | mutation | result |
|----|----------|--------|
| P1 | `compact` without the check | killed: 5 (compact x2, compact-with-daemon x2, every-opener census) |
| P2 | `compact` checks only AFTER pinging/stopping the daemon | killed: 2 (`test_compact_refuses_before_it_stops_a_running_daemon` x2) |
| P3 | `migrate-to-duckdb` without the check | killed: 2 (migrate, every-opener census) |
| P4 | a bridge failure is not raised (s-1) | killed: 2 (the bridge test x2) |
| P5 | `init`: busy treated as absent | killed: 1 (`[init]`) |
| P6 | `partition drop`: busy treated as absent | killed: 1 (`[partition-drop]`) |
| P7 | a promote failure is not raised (m-3) | killed: 6 (the L82 CLI test x4 incl. `--commit`, the MCP test x2) |
| P8 | STM subject set before the store write (m-4) | killed: 2 |

8 of 8 killed.

### For the lead, the test owner and the reviewers {#green-r5-flags}

- **`test_plan3_remedy_r3::test_promote_digest_reports_busy_and_never_opens_the_store`
  (test owner).** Lines 45-47 pin the pre-L95 contract, "save_state returns `promoted.error`".
  Under L95 they become:
  `with pytest.raises(verbs.SaveStateIncompleteError) as ei: verbs.save_state(...)`, then
  `"busy" in ei.value.result["promoted"]["error"]` and `"busy" in str(ei.value)`, with the
  no-catalog assertion unchanged. Not edited here.
- **A memory-bridge failure is now an MCP `isError` too, not only a promote failure.** L95
  named the promote for MCP and the bridge for the CLI. One verb-level mechanism makes both
  surfaces agree on both failures. Before r5, MCP callers saw `sync.error` as data inside a
  success reply.
- **Every promote or bridge error raises**, not only the tracked-catalog refusal: a busy
  daemon, a missing memory dir and a crash all do. That is the r4 CLI behaviour, now shared
  with MCP.
- **`migrate-to-duckdb --out <elsewhere>`** is still refused when the store's catalogs are
  tracked, although it would write a file outside the store. The check asks about the store,
  not the destination. This fails closed; it may be over-strict for that rare flag.
- **`change_subject`** re-raises with the original `VerbError` subclass (busy stays
  `VerbBusyError`), so the MCP and CLI paths keep their classification.
- The throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4` is still in place (r4's
  safety-check block on removing a top-level littlebig path). It is clean at `a1bde19`.

## RED r6 (ch-bsd r5 at 355eb1f: s-1, m-1..m-3; ruling L98) {#red-r6}

The test commit is `96c1dbe`. It adds the new file `tests/test_bug212_r6_red.py` and puts the
copy family into the census in `tests/test_bug212_r4_red.py`. At `c854bad` (src as `355eb1f`),
the r4, r5 and r6 files together give **6 failed, 66 passed** (`bug212/red-r6.log`). The 6
failures are the r6 REDs, and each fails for the reason it names.

rel: derives-from -> [[bsd-bug212-r5-355eb1f]]
rel: amends -> [[#red-r5]]

### RED at c854bad {#red-r6-red}

| item | test | E line at c854bad |
|------|------|-------------------|
| s-1 (a) | `test_migrate_out_into_another_repos_tracked_catalog_is_refused` (ignored store A, `--out <repo B>/.refmatrix/catalog.duckdb --overwrite`) | `` `--out` into repo B's tracked catalog rewrote it ['catalog.duckdb'] (exit 0) `` |
| s-1 (b) | `test_migrate_out_to_an_untracked_path_from_a_tracked_store_is_allowed` | `` `migrate-to-duckdb --out <untracked path>` from a tracked store was refused or failed ``; stderr: `Error: refusing to open …/x.duckdb read-write in-process: git tracks this store's catalog (catalog.duckdb, catalog.db)…` |
| m-1 | `test_mcp_save_state_error_reply_carries_the_result` (`busy_store`) | `the isError reply dropped ['lint', 'promoted', 'remove_failed', 'target'] of the result: '{"error": "save-state wrote … VerbBusyError: daemon busy …"}'` |
| m-2 verb | `test_a_deferred_bridge_is_not_a_failed_save_state_verb` | `Failed: a bridge only deferred behind running job <id> failed the save: … ingest job <id> still running after 0.2s …` |
| m-2 CLI | `test_a_deferred_bridge_is_a_stderr_warning_and_exit_0` | `a bridge deferred behind running job <id> failed the save` (exit 1, `Error: … its memory bridge failed: ingest job <id> still running after 0.2s …`) |
| m-2 MCP | `test_a_deferred_bridge_is_not_an_mcp_error` | `a bridge deferred behind running job <id> replied isError` |

- **m-2 setup.** The ingest job is REAL: `ingest_gmd_start` runs over 1500 as-memory docs on the
  `live` daemon from `tests/test_memory_bridge.py`. The bridge wait is shortened through the
  existing `RMX_BRIDGE_WAIT_S=0.2`, so nothing is patched and no mock is added.
- **m-2 contracts.** The verb must return `sync.deferred == {"job": <id>, "reason": <contains
  "running">}` with `sync.error` empty. The CLI must exit 0, print the job id on stderr, and
  print no `Error:` line. MCP must reply without `isError` and carry `sync.deferred.job`.
- **GUARD** `test_a_refused_bridge_still_fails_the_save_verb_and_mcp[slots, legacy]` passes at
  `c854bad`. A bridge refused on a tracked catalog still raises `SaveStateIncompleteError`
  ("memory bridge failed", with no `deferred`), and MCP still replies `isError`. The CLI
  exit 1 for the same case is the r5 s-1 test.
  - It catches a fix that reads every bridge error as a deferral. There is no deferral code at
    `c854bad` to mutate, so GREEN's mutation batch should kill it.
- **s-1 (c).** The default destination from a tracked store is still refused. The r5 test
  `test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog` already pins this; it is
  unchanged and passes.

### m-3: the census copy family (test code, no src) {#red-r6-census}

- **New family `copy`.** It flags `shutil.copy` / `copy2` / `copyfile` / `copyfileobj` keyed on
  the DESTINATION argument, and `<catalog path>.write_bytes(`. `os` and `shutil` now count under
  any import alias (`import shutil as _shutil`), for the move family too.
- **Synthetic test** `test_the_census_scanner_finds_the_copy_family_on_the_destination`:
  - positives: `copy2` onto a slot, `copy` onto a slot f-string, aliased `copyfile`,
    `copyfileobj` into `open(catalog.db, "wb")`, `write_bytes`, and aliased `move` /
    `os.replace`;
  - negatives: a copy FROM a catalog, a copy onto `catalog.read.duckdb`, and `write_bytes`
    elsewhere.
- **Sees guard** `test_the_census_sees_the_daemons_slot_copies` covers `_op_replica_merge`
  (daemon.py:5912) and `Daemon._bootstrap_rotation_if_needed` (:3066-3067). Their allowlist
  reasons now name the copies.
- **RED, then green.** Against the old scanner both tests fail: the scanner missed every
  positive, and the census did not see `('daemon:_op_replica_merge', 'copy')`
  (`bug212/red-r6-census-old-scanner.log`). With the extended scanner all 9 census tests pass,
  and the real tree has no stray site (`bug212/red-r6-census-new-scanner.log`).
- **GREEN has nothing to build for m-3.**

## GREEN r6 (ruling L98: migrate's destination, the MCP result body, a deferred bridge) {#green-r6}

Fix commit `ebe9fc2` (`src/refmatrix/cli.py`, `src/refmatrix/mcp.py`, `docs/INTEGRATION.md`,
by pathspec). No test was edited. One pre-existing test contradicted L98 m-2. It was reported
to the lead during the run, and the test owner updated it in `eb97445`.

rel: implements -> [[#red-r6]]
rel: derives-from -> [[bsd-bug212-r5-355eb1f]]
rel: amends -> [[#green-r5-changes]]

### What changed {#green-r6-changes}

- **s-1.** `migrate_to_duckdb` calls `_refuse_tracked_catalog_open(dst.parent.resolve(),
  dst.resolve())`, which asks about the directory of the file `migrate_catalog` replaces, not
  the source store. The default `dst` (`<root>/catalog.duckdb`) keeps the refusal. `--out` into
  another repo's committed catalog is refused. `--out` to an untracked path runs from a tracked
  store.
- **m-1.** `mcp._verb_tool` catches `SaveStateIncompleteError` before `VerbError` and returns
  `{**e.result, "error": str(e)}`. The dispatcher replies `isError` on the `error` key, so the
  body is the full result (`target`, `promoted`, `sync`, `lint`, `remove_failed`, ...). Other
  VerbErrors still return `{"error"}` only.
- **m-2, a typed deferral.** The bridge result (`cli._sync_memory_dir`) always carries a
  `deferred` field, `None` by default. `_bridge_wait_for_active_job` sets
  `out["deferred"] = {"job": <id>, "reason": "ingest job <id> still running after Ns ..."}`
  and leaves `error` unset ONLY when the other job is still `running` at the end of the wait.
  Nothing matches on message text.
  - Every other bridge outcome still sets `error`: no job id in the refusal, a failed status
    call, the other job ended non-done, the bridge refused, or any exception.
  - `verbs.save_state`'s failure rule is unchanged (`sync.error`), so a deferral does not
    raise.
  - `rmx save-state` and `rmx memory sync-disk` print `warning: memory bridge deferred:
    <reason>` on stderr and exit 0. `sync-disk` would otherwise have echoed an empty report
    for a deferral.
  - MCP replies normally, carrying `sync.deferred`.
- **INTEGRATION.md#sync-tracked-catalog** now covers the migrate destination check, the census
  copy family, the MCP result body and the deferral. GMD lint: 0 errors.
- **Merge prep, not changed here.** Master's `VerbUnknownProjectError` docstring
  (`verbs.py:55` on master) still says "`mcp._t_memory_add`'s in-process `Store` open". After
  the merge it should read "`mcp._t_memory_add`'s no-daemon fallback through
  `verbs.local_write`". This is a one-phrase edit, left for the merge as the lead ruled.

### Runs {#green-r6-runs}

- `bug212/green-r6-r4r5r6.log`: the r4, r5 and r6 files at the tree that became `ebe9fc2`,
  **72 passed**. At `c854bad` it was 6 failed / 66 passed. The refused-bridge GUARD stays
  green.
- `bug212/green-r6-prior.log`: `test_bug212_hooks_in_worktrees`, `_r1_remedy`, `_r2_red`,
  `test_plan3_remedy_r3`, `test_memory_bridge` and the 9 MCP files. Result: **1 failed, 236
  passed**.
  - The failure was `test_memory_bridge.py::test_bridge_reports_a_wait_that_ran_out` (line
    143), E `assert (None)`. It asserted the plan-5 contract: a timed-out wait is
    `out["error"]`. L98 makes it `deferred` with `error` empty, and the r6 RED asserts
    exactly that.
  - Reported to the lead mid-run and updated by the test owner in `eb97445`. Re-run at
    `eb97445`: `bug212/green-r6-memory-bridge-at-eb97445.log`, **22 passed**.
- `bug212/green-r6-family.log`: r5's 108 files plus the r6 file and `test_plan3_remedy_r3`
  (`green-r6-family.files`, 110 files). Result: **1 failed, 1616 passed, 1 skipped**. The
  failure is the same `test_memory_bridge` test, collected before `eb97445`.
- `bug212/green-r6-wide.log`: the full suite at the tree with `ebe9fc2` src (the run collected
  `eb97445`'s test update; `__pycache__` cleared). Result: **4 failed, 4443 passed, 1
  skipped**, 47m58s. The skip is the SkipGate UNPINNED clone artifact. By E line:
  - Against `release-0.82.0-full.log` (`green-r6-wide-elines-vs-0820.txt`):
    `test_brief_real_daemon` and `test_task21_1_agent_usage_report` x2 have the SAME E lines.
    `test_gmd_lint_requires_version` differs: it is bug-155, fixed on master, and this branch
    predates the fix. Reported, not counted. Nothing failed here that did not fail in 0.82.0.
  - Against `green-r5-wide.log` (`green-r6-wide-elines-vs-r5.txt`): the 4 match, all E lines
    the same. r5's `test_plan3_remedy_r3` failure is gone (the test followed L95 in
    `f58ac6b`). Nothing new.
  - bug-228 (`ac2b_live`) did not recur.

### Mutations {#green-r6-mutations}

The spot-checks ran in the throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4`,
fast-forwarded to `ebe9fc2`. The driver was `scratchpad/mut212g6.py` (not committed); every
mutant was compiled before the batch. Each mutation ran the r5 + r6 files and was logged to
`bug212/green-r6-mut-<id>.log`. Each touched file was restored with `git checkout --` in its
own command, then `src` was checked clean with the fix text back. `__pycache__` was cleared in
the copy afterwards and in the clone before the full suite. Batch log:
`bug212/green-r6-mutations.log`.

| id | mutation | result |
|----|----------|--------|
| Q1 | migrate check aimed back at the source store (`root`) | killed: 2 (`--out` into repo B refused; `--out` untracked allowed) |
| Q2 | MCP returns only `{"error"}` for `SaveStateIncompleteError` | killed: 1 (`test_mcp_save_state_error_reply_carries_the_result`) |
| Q3 | every bridge error read as deferred (the ClickException branch sets `deferred`) | killed: 4, incl. the GUARD `test_a_refused_bridge_still_fails_the_save_verb_and_mcp` x2 and the r5 bridge test x2 |
| Q4 | a deferral raises again (`sync.deferred` joins the failure rule) | killed: 3 (the m-2 verb, CLI and MCP tests) |

4 of 4 killed.

Follow-up batch, run after `eb97445`. The copy was at `282589b`, with the r6 file and
`tests/test_memory_bridge.py`; the log is `bug212/green-r6-mutations-followup.log`. The batch
checks the lead's expectation that "deferral raises again" also fails the updated
memory_bridge test:

| id | mutation | result |
|----|----------|--------|
| Q4b | Q4 again (`sync.deferred` joins `verbs.save_state`'s failure rule) | killed: 3 (the r6 verb, CLI and MCP deferral tests). `test_bridge_reports_a_wait_that_ran_out` PASSES under it: that test calls `cli._sync_memory_dir` directly, below the verb's rule |
| Q5 | the deferral written as `out["error"]` too (`_bridge_wait_for_active_job`) | killed: 4 (`test_memory_bridge::test_bridge_reports_a_wait_that_ran_out`, plus the 3 r6 deferral tests) |

So the updated memory_bridge test pins the bridge layer (Q5). The verb layer is pinned by the
r6 tests (Q4/Q4b).

### For the lead and the reviewers {#green-r6-flags}

- **The migrate check is still name-based.** `git_tracked_catalogs(dst.parent)` asks whether
  git tracks a `WRITER_CATALOG_FILES` name in that directory. A `--out` onto a committed file
  with another name (`--out <repo>/x.duckdb`, where `x.duckdb` is tracked) is not refused. A
  `--out foo.duckdb` beside a tracked `catalog.duckdb` IS refused (fail closed). The ruling
  prescribed exactly this call.
- **`deferred` is also the outcome for `rmx memory sync-disk`** (stderr warning, exit 0),
  matching save-state. Before r6 a run-out wait counted as a failed path there, with exit 1.
- The throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4` is still present (the r4
  safety block). It is clean at `ebe9fc2`.

## GREEN r7 (ruling L102: migrate asks git about the file it replaces) {#green-r7}

Fix commit `9ed0d6b` (`src/refmatrix/store.py`, `src/refmatrix/cli.py`,
`docs/INTEGRATION.md`, by pathspec). The RED is `436fff9` + `dd36472` (`tests/test_bug212_r7_red.py`;
this summary has no `#red-r7` section). No test was edited. m-2 needs no code: the r7 GUARD
`test_memory_sync_disk_deferred_behind_a_running_job_warns_on_stderr` passes, as at `bcd861c`.

rel: derives-from -> [[bsd-bug212-r6-282589b]]
rel: amends -> [[#green-r6-changes]]

### What changed {#green-r7-changes}

- `store.git_tracked_catalogs(root, names=WRITER_CATALOG_FILES) -> list[str]` asks `git
  ls-files -- *names` in `root` and returns the tracked ones in `names`' order.
- `store.refuse_tracked_catalog_open(root, target, names=WRITER_CATALOG_FILES)` passes `names`
  to `git_tracked_catalogs`.
- `cli._refuse_tracked_catalog_open(root, target, names=WRITER_CATALOG_FILES)` threads it
  through to the store check.
- The default keeps every existing caller unchanged: `_store_rw`, `local_write`, `compact`,
  the hooks' Python check.
- `migrate_to_duckdb` calls `_refuse_tracked_catalog_open(dst.parent.resolve(), dst.resolve(),
  names=(dst.name,))`.
  - A committed `x.duckdb` is refused.
  - An untracked `foo.duckdb` beside a tracked `catalog.duckdb` is allowed.
  - The default `dst` (`<root>/catalog.duckdb`) keeps the refusal (r5 test green).
- `docs/INTEGRATION.md#sync-tracked-catalog`: migrate asks about the destination file itself.
  GMD lint: 0 errors.

### Runs {#green-r7-runs}

- `bug212/green-r7.log`: the r7 file, **3 passed**. At `bcd861c` it was 2 failed / 1 passed.
- `bug212/green-r7-r4tor7.log`: the r4, r5, r6 and r7 files, **75 passed**.
- `bug212/green-r7-family.log`: r6's 110 files plus the r7 file (`green-r7-family.files`), at
  `9ed0d6b`. Result: **1620 passed, 1 skipped**, no failure. The skip is the SkipGate
  UNPINNED clone artifact.
- `bug212/green-r7-wide.log`: the full suite at `9ed0d6b` (`__pycache__` cleared). Result: **5
  failed, 4445 passed, 1 skipped**, 57m21s. It ran at load 12-20, beside bsd216-r6's
  mergesim suite and a leaked bug212-clone test daemon from an earlier run (bug-229, stopped by
  the lead). By E line:
  - Against `green-r6-wide.log` (`green-r7-wide-elines-vs-r6.txt`): `test_brief_real_daemon`
    (1/1), `test_task21_1_agent_usage_report` x2 (29/29, 16/16) and `test_gmd_lint_requires_version`
    (22/22; bug-155, fixed on master, which this branch predates; reported, not counted) have
    the SAME E lines.
  - Against `release-0.82.0-full.log` (`green-r7-wide-elines-vs-0820.txt`): the same three
    match; gmd_lint differs (clone scope, bug-155).
  - **NEW vs r6 and 0.82.0, timing-bound:**
    `test_plan4_remedy.py::test_graceful_stop_on_a_live_daemon_returns_quickly`. E:
    `assert (667488.70560075 - 667478.654565041) < 8.0`: `hub.graceful_stop` on a freshly
    spawned daemon took 10.05 s against the test's 8 s bound.
    - Re-run of the file alone after load dropped (load ~6, the other suites done): run 1
      `bug212/green-r7-plan4-rerun1.log` gave **16 passed**, with the test's whole call
      (spawn + stop) taking 5.29 s. Run 2 `bug212/green-r7-plan4-rerun2.log` gave **16
      passed** at 5.27 s.
    - r7's diff cannot reach it. `9ed0d6b` changes only `store.git_tracked_catalogs`,
      `refuse_tracked_catalog_open`, the CLI wrapper and the migrate call. `hub.py` names
      none of them, and the test spawns a daemon and stops it through `hub.graceful_stop`.
      Read as load: two clean reruns, and no code path from the diff.

### Mutations {#green-r7-mutations}

The spot-checks ran in the throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4`,
fast-forwarded to `9ed0d6b`. The driver was `scratchpad/mut212g7.py` (not committed); every
mutant compiled. Each mutation ran the r5, r6 and r7 files, logged to
`bug212/green-r7-mut-<id>.log`. Each touched file was restored with `git checkout --` in its
own command, then `src` was checked clean with the fix text back, and `__pycache__` was cleared
in the copy. Batch log: `bug212/green-r7-mutations.log`.

| id | mutation | result |
|----|----------|--------|
| R1 | migrate back to the default name list (no `names=`) | killed: 2 (the r7 migrate tests (a) and (b)) |
| R2a | `refuse_tracked_catalog_open` ignores `names` (calls `git_tracked_catalogs(root)`) | killed: 2 (same) |
| R2b | `git_tracked_catalogs` ignores `names` (ls-files and the result use `WRITER_CATALOG_FILES`) | killed: 2 (same) |

3 of 3 killed. The r5/r6 migrate tests (the default dst is refused; s-1 (a)/(b)) pass under
all three, as expected: for those fixtures the default name list and `(dst.name,)` give the
same answer.

### For the lead and the reviewers {#green-r7-flags}

- **Leftover processes after the run: none.** No process matches `refmatrix-bug212/src/
  refmatrix/cli.py daemon` or the `-mut4` clone, none has a cwd in either clone, and no Python
  process has either clone's `src/refmatrix/` open. The bug-229 daemon the lead stopped
  (pid 89734, `/private/tmp/r1-hcn81cf7`) predates this run.
- **The refusal wording on a non-store destination.** For `--out <repo>/x.duckdb` the line
  says "git tracks this store's catalog (x.duckdb) ... Untrack it (git rm --cached
  .refmatrix/catalog*, ...)", which reads oddly for a file outside any store. The head (target
  path) and both remedies are right. Not changed (out of L102's scope).
- The throwaway clone `/Volumes/littlebig/refmatrix-bug212-mut4` is still in place (the r4
  safety block on removing it). It is clean at `9ed0d6b`.
