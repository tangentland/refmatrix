---
gmd: "0.1"
id: agent-brief-green-hwq
title: "GREEN brief: task-hook-writes-queue (23.1 R11 pulled forward on an interim spool)"
tags: [agent-brief, green, hook-writes, bug-309, bug-177]
metadata:
  node_type: brief
  created: 2026-11-24
---

# GREEN: hook writes enqueue and return {#root}

rel: implements -> [[task-hook-writes-queue]]

You are the GREEN implementer for [[task-hook-writes-queue]]. Read the spec, its contract
[[task-23.1-queue-and-drain#r11]] items 1-7, and RED's tests at `fbb9fd9d`. You change `src/`
(and docs the change requires) to make RED's 28 failing tests pass. You write NO tests and edit
none of RED's; if a test looks wrong, stop and report it to the lead with the reason. {#role}

## Where {#where}

- Your clone: `/Volumes/littlebig/refmatrix-hwq-green`, branch `task-hook-writes-queue` at
  `fbb9fd9d`. Commit there at natural points; never push, never touch the dev tree.
- Read-only against every live store; look things up with
  `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master …` or the read-only refmatrix MCP
  tools. Never `find /`.
- Tests only through `scripts/lane-local.sh /Volumes/littlebig/refmatrix-hwq-green <sha>
  <log-name> <files…>` on a committed sha.

## RED's decisions you build to (accepted by the lead) {#decisions}

1. `hook_writes.enqueue(root, entry) -> Path` (the final spool file).
2. `Daemon._drain_hook_writes() -> dict` (`applied`, `superseded`, `bad`) is the one entry point
   for the flush tick and the boot drain.
3. `superseded` counts entries, including one folded into a newer queued entry.
4. An empty spool takes no `_store_lock`; a non-empty drain takes it exactly once, then requests
   a snapshot after a committing drain.
5. `hook_writes_pending` counts every `*.json` waiting, malformed ones included until moved.
6. An entry missing `name`, `partition` or `args` is unreadable → `bad/`.
7. `origin`: `stop-hook` for `focus summarize --promote`, `save-state` for `_promote_digest`.
8. `rmx daemon status` prints a line containing `hook_writes`, `bad` and the count when non-zero.
9. `_promote_digest` derives its deadline from its own `timeout` argument (default 30.0).
10. `verbs.ENQUEUE_RESERVE_S = 1.0`, `verbs.MIN_DIAL_S = 0.5`, `verbs.QUEUED_WRITE_MSG` per R11.4.
11. `focus_summarize` computes its deadline first and drops its own `daemon_status` probe.

## Rules {#rules}

- `src/` fully concrete; no silent failure on this memory path (an enqueue failure, a bad entry,
  a drain error: each counted and loud). Docstrings say WHY and name bug-309 / L212 / the date.
- The store edits are R11.3's exactly: `add_memory(updated_at=)` guard, the `memory_content`
  event carries `updated_at` (also in `reclassify_memories`, `retag_memory`,
  `dump_catalog_to_log`), both replay paths pass it, the rebuild's winner is picked by
  `ev.get("updated_at", ts)`; no bare `con.commit()` on the drain path.
- Run RED's five files plus every test file importing a changed module plus the repo guards
  (`test_tmp_root_census`, `test_suite_discipline`, `test_docs_generated`,
  `test_mock_registry_coverage`, `test_deferrals_clean`, `test_wallclock_census`,
  `test_budget_outcome_census`, `test_verb_parity`, `test_bug212_r4_red`). If `hooks.py`'s
  generated output changes, regenerate what `test_docs_generated` checks.
- Add the D5 deferral row to `workflow/deferral_registry.md` (the spool re-bases on 23.1 R3).
- Write a short implementation summary `workflow/implementation_summaries/task-hook-writes-queue.md`
  (GMD; what changed, the verify runs, a self-audit per `workflow/SELF_AUDIT.md`).

## Report (as text, to the lead) {#report}

Commit shas, the lane log names with pass/fail counts, any test you believe is wrong (unchanged,
with the reason), and anything in the spec you could not satisfy.
