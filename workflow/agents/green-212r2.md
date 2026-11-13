---
gmd: "0.1"
id: agent-brief-green-212r2
title: "Brief: green-212r2 — bug-212 r2 GREEN (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-212r2 — bug-212 r2 GREEN (ch-implementer) {#root}

Dispatched 2026-11-13 (session f0521bff) as `ch-implementer`. Make bug-212's r2 REDs pass; write no
tests.

- **Clone:** `/Volumes/littlebig/refmatrix-bug212`, branch `task-bug212-worktree-hook-crashes`, tip
  at dispatch `deafd6d` (r1 GREEN `faabdfe`; r2 RED `488a62d`).
- **Read:** the summary `#green-r1`, `#green-r1-flags`, `#red-r2`; `tests/test_bug212_r2_red.py`;
  `workflow/agents/red-212r2.md`; `workflow/agents/green-251.md#hard-rules`.
- **Scope (lead decisions):** move the tracked-catalog refusal into `cli._store_rw()` (one helper;
  ingest, memory add and `ingest-gmd --as-memory` refuse too); neutral wording ("refusing an
  in-process write to …"), one `Error:` line naming the target and both remedies; keep G3/E2
  (ls-files failure fail-closed and said), E1 (strip the hook's GIT_* env), W1/W2 (context-dependent
  remedies); keep all r1 behaviour.
- **Verify:** three bug-212 test files; family; full suite by E line (flag fixtures that `git add
  -A` a store and are now refused; do not edit tests); mutations on the control-point check. Tee to
  `workflow/review-output/bug212/`. Commits: src, `#green-r2`.
