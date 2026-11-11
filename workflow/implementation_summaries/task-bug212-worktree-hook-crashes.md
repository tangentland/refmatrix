---
gmd: "0.1"
id: impl-task-bug212-worktree-hook-crashes
title: "bug-212: the git hooks crash in throwaway worktrees -- RED (GREEN appended by the implementer)"
tags: [implementation-summary, bug-212, hooks, git, worktree, sync, loud-failure]
metadata:
  node_type: implementation-summary
  status: red
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

(appended by the implementer)
