---
gmd: "0.1"
id: agent-brief-green-212r1
title: "Brief: green-212r1 — bug-212 remedy r1, GREEN (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-212r1 — bug-212 remedy r1, GREEN {#root}

Make the bug-212 r1 RED tests pass with concrete `src/` code. You write NO tests.

rel: depends-on -> [[agent-brief-green-251#hard-rules]]
rel: depends-on -> [[agent-brief-red-212r1]]

## Where {#where}

- Clone `/Volumes/littlebig/refmatrix-bug212`, branch `task-bug212-worktree-hook-crashes`, tip
  `62db88f`. Work and commit (pathspec) only here. Interpreter: the clone's `.venv-eval`; else
  `PYTHONPATH=/Volumes/littlebig/refmatrix-bug212/src` (absolute).

## Read first {#read-first}

1. `workflow/bullshit/2026-11-11-1342-bug212-r1-b024a95.md` (the audit, DIRTY 8).
2. `workflow/implementation_summaries/task-bug212-worktree-hook-crashes.md`: `#green` (the first
   fix), `#red-r1`, `#red-r1-a2`, `#red-r1-decisions` (lead decisions a1-a8).
3. `tests/test_bug212_r1_remedy.py` — at HEAD 37 failed / 24 passed across both bug-212 files
   (`workflow/review-output/bug212/red-r1-a2-head.log`).
4. `docs/INTEGRATION.md#git-integration`, `CLAUDE.md`, `workflow/TDD_GOVERNANCE.md`.

## Scope {#scope}

- **b-1:** the generated git-hook store gate passes only on a daemon socket OR a catalog that
  is present and NOT tracked by git (red-212r1 probed this gate: all 20 b-1 REDs + guards green).
- **a2:** an in-process `rmx sync` / `sync --since` whose target catalog is git-tracked refuses:
  one `Error:` line naming the file and both remedies (untrack / `rm --cached`, or start the
  daemon), non-zero exit, catalog bytes unchanged. A store outside any git repo, or with an
  ignored catalog, still writes. Lead decision: in the stale-socket hook case a silent skip is
  acceptable (a1, fail closed); the tests accept either.
- **s-1:** ONE shared cwd helper raising a named, non-OSError error that names the working
  directory; route every cwd reader the RED names through it (`discovery.partition_marker`,
  `discovery._cwd_root`, `cctree.resolve_path`, `mcp._resolve_root`, `sync.sync_since` /
  `sync_files`, and `cli.py:7109` `_grep_rg_fallback` as a census item, a6). Daemon-op cwd
  defaults are out of scope (a7). If `discover_roots` drops a vanished cwd rather than raising,
  it says so (a5; no silent failures).
- **m-3:** a root commit (no parent) syncs by diffing against the empty tree, not a loud failure.
- **s-3:** rewrite `docs/INTEGRATION.md#git-integration` to the new gate, the a2 refusal and the
  cwd error; anchored, GMD lint 0 errors.
- Regenerate the clone's committed hook config from the generator with the clone's interpreter
  if `test_repo_hooks_in_sync` needs it; never `rmx install-hooks` against a live store.
- Out of scope: bug-209 (`--check` vs `.git/hooks`), bug-215, other clones' code (25.1 edits
  hooks/recall/scan/verbs; 26.4 edits the bridge) — keep the diff to the gate, sync, discovery,
  cctree, mcp root resolution and the cli cwd paths.

## Verify and deliver {#deliver}

- Both bug-212 test files all pass; family run over hooks, sync, discovery, cctree, mcp, cli,
  telemetry tests; a wide run compared by E line against
  `/Users/tholley/claude_tools/refmatrix/workflow/review-output/release-0.82.0-full.log`.
- Mutations on each new guard (one at a time, restore in its own command, clear `__pycache__`).
- Commits: src, then `#green-r1` in the summary (signatures, runs + log paths, mutation table,
  flags). Text report: shas, counts, mutation results, flags for the lead.
