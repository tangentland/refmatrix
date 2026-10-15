---
gmd: "0.1"
id: impl-bug-115-116-daemon-liveness
title: "bug-115/116: liveness off the work pool, expired reads dropped, no re-send after a sent request times out"
tags: [implementation-summary, bug-115, bug-116, daemon, liveness, heartbeat, timeout, hooks]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-10-15
  updated: 2026-10-15
---

# bug-115/116: daemon liveness under hook load {#root}

rel: implements -> [[bug_registry#registry]]

## What happened {#incident}

2026-10-15 00:13:18 the hub watchdog SIGTERMed the refmatrix daemon ("not answering ping",
heartbeat > 60 s, three `stats` still in flight). At 00:16:52-00:17:44 a second 52 s stall
recovered on its own. Seven agents were running; cli.log for the hour: 945 `focus hook`, 245
`grep` (the PreToolUse rewrite), 165 `sync --flush-queue`, `memory recall` p50 1.5 s,
`scan-prompt` p50 4.1 s / p95 18.6 s against its own `--timeout 5`, and `focus summarize
--promote` exiting 1 at 5.03 s on 7 of 11 Stops.

## Mechanism, as far as it is measured {#mechanism}

- `ping` is in `CLI_OPS`, so it queued FIFO on the 4-worker cli pool; the heartbeat is a no-op on
  the same pool. Both liveness signals waited behind reads.
- 16 cli ops take `_store_lock` (AST scan of `CLI_OPS` handlers). A long write therefore parks every
  cli worker. ch-bsd 23/17 r7 tied the 52 s stall to two concurrent post-commit `sync --since
  HEAD~1` runs (80 s, 110 s), and measured the 00:11:15 facts.log compaction at 6.1 s on a copy, so
  the compaction was not the 2-minute hold. What held the lock 00:11:15-00:13:16 is NOT named.
- `daemon.call` retried a socket timeout after the request had been sent: three copies of the work,
  three times the wait (`--timeout 5` measured 15-18 s).

## The fix {#fix}

- `Daemon._handle` answers `ping` on the dispatcher thread. A deadlocked cli pool is still visible:
  the heartbeat only ticks on cli-pool completions.
- Every cli-pool future touches the heartbeat when it completes, so a draining queue beats however
  deep it is.
- Requests carry `deadline_s` (set by `call` to its `timeout`). A cli READ still queued past its
  deadline is refused with `DeadlineExceeded`, counted, and logged at most once a minute
  (`dropped expired read(s): total=N`). Writes are never dropped.
- `call` retries only before the request is sent (connect refused/backlog, reset, empty reply).
- The Grep-tool teach hook honours `learn.off` and `RMX_LEARN` (user, 2026-10-15: the grep->graph
  loop is off until plan 16's passive shim exists; `rmx learn off --global` was set live, and the
  project's `enforce-rmx-grep.sh` stands down while the marker exists).

## The compaction floor {#compaction}

A PRODUCTIVE facts.log compaction that still leaves the log over the 256 MiB gate now re-arms the
floor at `new_size * 1.25`. Before, only an unproductive one did, so refmatrix (minimal log about
265-277 MB) rewrote its whole log under `_store_lock` every 30 minutes; the 00:43 hold cost a
Stop-hook promote its 5 s reply.

## Not fixed here {#not-fixed}

The read stall itself: a writer holding `_store_lock` for tens of seconds still blocks every
lock-taking read. Bounding writer holds is 23.3 (sync yields between files) and 23.1; the
non-harness holders (`_op_stats` and the other lock-taking cli reads, the compaction tick) are
plan 23's by d9az, specified as task 23.5.

## Verification {#verification}

- RED at `c7129e6`: `tests/test_bug115_liveness_under_load.py`, 6 of 7 fail for the named reason,
  the control passes (`workflow/review-output/bug115-red.log`).
- GREEN: 18 of 18 across `test_bug115_liveness_under_load.py` and `test_factslog_compaction.py`
  (`bug115-green3.log`). Mutations M1-M9 all killed (`bug115-mutations.log`).
- Full suite, 4 shards, compared against `master` `c7129e6` by ERROR TEXT (not by name): 43 vs 43,
  identical messages, 0 new. The 43 are environmental at both commits (clone-only failures and
  tests that read the real `~/.refmatrix/learn.off`, set live 2026-10-15).
- **A process failure, recorded:** `5a8619f` says it holds the compaction floor fix but carries
  only the tests. The mutation restore (`git checkout -- daemon.py`) reverted to a commit made
  before the fix was committed. The comparison above caught it (the two new tests failed with the
  RED error); `1c86d9c` re-applies it. Feedback memory `feedback_mutation_commit_must_hold_the_fix`.
- Also in `1c86d9c` (ch-bsd 23/17 r7): `CLI_WRITE_OPS` (`partition_add`, `partition_rename`,
  `stop`) are exempt from the deadline drop; M9 kills it.
