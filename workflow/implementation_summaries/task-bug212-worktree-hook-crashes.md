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
