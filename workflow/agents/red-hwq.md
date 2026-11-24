---
gmd: "0.1"
id: agent-brief-red-hwq
title: "RED brief: task-hook-writes-queue (23.1 R11 pulled forward on an interim spool)"
tags: [agent-brief, red, hook-writes, bug-309, bug-177]
metadata:
  node_type: brief
  created: 2026-11-24
---

# RED: hook writes enqueue and return {#root}

rel: implements -> [[task-hook-writes-queue]]

You are the RED test engineer for [[task-hook-writes-queue]] (read it first, then its contract
[[task-23.1-queue-and-drain#r11]], items 1-7). You write FAILING tests only; you change nothing
under `src/`. GREEN is a different agent and builds against your tests. {#role}

## Where {#where}

- Your clone: `/Volumes/littlebig/refmatrix-hwq-red`, branch `task-hook-writes-queue` (base
  `04c25731`). Commit there at natural points; never push, never touch the dev tree.
- Read-only against every live store (CLAUDE.md `#discovery-corpus`, Q15): look things up with
  `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master context|query|grep …` or the
  read-only refmatrix MCP tools. No `rmx sync/ingest/daemon/hub/memory add…` on any live store.
- Tests run in an isolated slot on a committed sha:
  `scripts/lane-local.sh /Volumes/littlebig/refmatrix-hwq-red <sha> <log-name> <files…>`
  (log lands in the clone's `workflow/review-output/<log-name>.log`). Never `find /`.

## What to write {#what}

One test per acceptance criterion AC-1..AC-8 of the spec, each through an entry point users call:
the generated Stop / PreCompact hook command (`hooks.py` renders it; `h.run_hook` in the existing
hook tests shows how), `rmx save-state`, `rmx memory get`, the daemon. Rules (CLAUDE.md
`#test-discipline`): {#what-lead}

1. **Extend existing files.** The promote / Stop-hook behaviour already has tests
   (`tests/test_hooks_reproducible.py`, `test_plan2_remedy.py`, `test_save_state.py`,
   `test_subject.py` … find the right home with `rmx-master context focus_summarize`). New file
   only for the new module: `tests/test_hook_writes.py` (`newest_by_ts`, the spool write shape,
   the unreadable-entry handling).
2. **Real held writer.** "Busy" is a REAL sandbox daemon whose `_store_lock` is held by a real
   op (find the gate/hold pattern already used in `tests/test_daemon_shutdown_drain.py` or
   `tests/test_context_rerank_off_the_writer_lock.py`), never a patched `ping`, `daemon.call`,
   `daemon_status` or a silent listener. AC-5's absent daemon is no daemon at all.
3. **No real waits.** Use test-sized budgets (`--timeout 2`); trigger the drain directly through
   the daemon's tick function or a test-sized `RMX_DAEMON_FLUSH_S`, never sit out 30 s. AC-2's
   daemon death is a real SIGKILL of the sandbox daemon, then a real start.
4. **Pin the interface GREEN must build,** by the spec's names: `src/refmatrix/hook_writes.py`
   (`enqueue`, `read_pending`, `newest_by_ts`, `drain`), spool dir `hook_writes.spool/` with
   `bad/`, `_store_health` keys `hook_writes_pending` / `hook_writes_bad`, `verbs.QUEUED_WRITE_MSG`,
   `_write_or_local(…, queue=, local=, deadline=)`, `Store.add_memory(…, updated_at=)`, the
   `memory_content` facts.log event's `updated_at`. Where the spec leaves a detail open, decide,
   say why in the test docstring, and list it in your report for the lead.
5. **Seen failing for the intended reason.** Run your set at base on the lane and keep each
   test's E line; a test that passes at base is not RED.
6. Every faked process boundary gets a row in `workflow/test_mock_registry.md`.

## Report (as text, to the lead) {#report}

Commit shas; the test names per AC; the lane log name and each test's E line at base; the open
details you decided; the mutation list GREEN's change must fail (from the spec's ACs). Do not
write report files beyond the tests, the registry row and your lane logs.
