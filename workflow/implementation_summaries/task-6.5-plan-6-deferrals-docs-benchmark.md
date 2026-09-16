---
gmd: "0.1"
id: task-6.5-summary
title: "Task 6.5 — the user-global rewriter names no tree (bug-008)"
tags: [implementation, plan-6, hooks, bug-008]
metadata:
  node_type: implementation-summary
  status: complete
  date: 2026-09-16
---

# Task 6.5 — the user-global rewriter names no tree {#root}

rel: implements -> [[task-6.5-plan-6-deferrals-docs-benchmark]]
rel: related-to -> [[bug-registry#registry]]

## What changed {#changes}

`~/.claude/hooks/rmxgrep-rewrite.py` is shared by every project on the machine and was rendered
with `RMXGREP = "<generator tree>/bin/rmxgrep"`. Any `install-hooks --apply` from a dev venv — a
test without the `RMX_CLAUDE_HOOKS_DIR` redirect, an audit probe in a throwaway project —
overwrote the live hook with dev-tree paths. Seen twice; `--check` was the only tripwire.

Two independent defences, because either alone leaves a hole: {#two-defences}

- **Runtime resolution.** `RMXGREP` / `RMXRG` became functions that resolve from the tree owning the
  `rmx` on PATH (sibling of `which rmx` → that tree's `bin/` → PATH → `~/bin` → bare name). The
  rendered bytes no longer depend on which tree rendered them, so the drift has nowhere to enter.
- **Entitlement.** `install_search_hooks(apply=True)` REFUSES to write the user-global dir when
  `upgrade.runtime_identity()["venv_tree"]` differs from `path_rmx_tree()`, naming both trees and
  the `RMX_CLAUDE_HOOKS_DIR` escape. A redirected dir is nobody else's, so any tree may write it.

## Proof, not just green tests {#proof}

Rendered from the DEV tree and executed, the script resolves the DEPLOY wrapper: {#live-probe}

```
echo '{"tool_input":{"command":"grep -rn foo src/"}}' | python3 <rendered>
-> /Users/tholley/refmatrix/.venv/bin/rmxgrep -rn foo src/
```

That is the whole bug inverted: the generating tree no longer decides the path. `ast.parse` on the
rendered script passes (129 lines) and `/refmatrix/bin/` does not appear in it.

## TDD record {#tdd}

RED `workflow/review-output/pytest-task-6.5-red.log` — 6 failed, 18 passed.
GREEN `pytest-task-6.5-green.log` — 24 passed.

Mutations, each killing its test: re-bake a generator path into the render → `test_rewriter_bakes_no_tree_path`
fails; drop the foreign-tree refusal → `test_install_refuses_user_global_dir_from_a_foreign_tree` fails. {#mutations}

## NOT verified, and why {#not-verified}

The task's third requirement — *"`rmx install-hooks --check` stays clean after a deploy regen"* —
**cannot be checked from here**. `rmx` on PATH is 0.69.1 (the deploy build) and does not contain this
change; it reports `hooks in sync` about the OLD render. The live
`~/.claude/hooks/rmxgrep-rewrite.py` still carries `RMXGREP = "/Users/tholley/refmatrix/bin/rmxgrep"`.

That baked path currently points at the DEPLOY tree, so it is correct today, not drifted — the
hazard is latent, not active. It converts to the runtime-resolving form on the next deploy +
`install-hooks --apply --force`, and only then can the criterion be read. Stated rather than
claimed. {#deploy-gate}
