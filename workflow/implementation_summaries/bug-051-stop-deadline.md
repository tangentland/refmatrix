---
gmd: "0.1"
id: impl-bug-051-stop-deadline
title: "bug-051: one stop deadline every shutdown stage spends from"
tags: [implementation-summary, ch-bsd, daemon, shutdown, launchd]
metadata:
  node_type: implementation-summary
  status: complete
  audit: bsd-bug-041-042-043-00d0ded
  finding: s-1
  created: 2026-09-20
---

# bug-051: one stop deadline every shutdown stage spends from {#root}

rel: derives-from -> [[bsd-bug-041-042-043-00d0ded]]
rel: amends -> [[impl-remedy-bsd-0916-blockers]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]
rel: reinforces -> [[feedback_no_silent_failures]]

## The finding {#finding}

`@ch-bsd` #s-1 of the 2026-09-16 post-deploy audit: the bug-041 remedy raised
`RMX_DAEMON_FLUSH_BUDGET_S` from a hard-coded 5 to 15, and nobody added the shutdown stages up
against the supervisor. The degraded stop is a SUM — `10+10+10` (three pool drains) `+ 3+3+3+3`
(watcher, flush, repair and replica joins) `+ 15` (final flush) `+ 5` (bounded store close) =
**59 s** — against `EXIT_TIMEOUT_S = 45`, the `ExitTimeOut` in the live plist. Past that launchd
SIGKILLs, and a SIGKILL mid-close is the documented cause of the entities ART-index corruption and
the 2026-09-14 crash loop. {#finding-lead}

The evidence that made it real: the two stops bug-041 itself reproduced took **39 s** and **38 s**.
Both fitted inside 45 before the bump. With a flat 15 s flush they become 49 s and 48 s — over.

## Why a smaller constant was the wrong fix {#why-not-a-constant}

The audit offered two remedies: derive the flush budget from what is left, or cut
`RMX_DAEMON_SHUTDOWN_TIMEOUT_S` so the sum fits. Cutting a constant restores the invariant exactly
once. The next person who moves a stage budget breaks it again, silently, in the one path the suite
does not exercise — which is precisely how this got here: bug-041's remedy was correct about the
defect and never re-derived the sum it changed. {#why-not-a-constant-lead}

So the stages no longer own their time. `_StopDeadline` owns it, and they ask:

```python
_stop_dl = _StopDeadline(stop_grace_s())          # one budget for the whole stop
...
self._drain_pool(name, pool, _stop_dl.budget(shutdown_timeout, reserve=_close_reserve))
...
self._final_flush(elapsed_s=time.monotonic() - _stop_t0)
```

`budget(want, reserve=)` grants `want`, or what is left minus what the LATER stages are owed,
whichever is smaller, never negative. `reserve` is the bounded store close: a drain that spends it
strands the catalog file lock, the stranding PID 79273 showed. `now` is injectable, so the
arithmetic is tested without sleeping.

## What shipped {#shipped}

| where | change |
|---|---|
| `daemon.py` | `SHUTDOWN_EXIT_MARGIN_S`, `_StopDeadline`, `flush_budget_ceiling_s()`, `store_close_budget_s()`, `remaining_flush_budget_s()` |
| `daemon.py` `serve_forever` | every stage — watcher join, three drains, three periodic joins, final flush, store close — draws from the one deadline |
| `daemon.py` `_final_flush` | takes `elapsed_s`, derives its own budget, and on a zero budget SKIPS and logs why (the skip is the "relational tables ahead of the bitmaps" surface that wedged viascope; skipping it silently is what this repo bans) |
| `launchctl.py` | the `EXIT_TIMEOUT_S` comment named a "~50 s" drain and a bound that had moved |

The stale comment the audit also flagged — *"5s budget is generous"*, still sitting above a 15 s
call — is gone with it.

## Gates {#gates}

- RED: `workflow/review-output/pytest-bug051-red.log` — 12 failed (no `_StopDeadline`).
- GREEN: `workflow/review-output/pytest-bug051-green.log` — 12 passed.
- Regression: `workflow/review-output/pytest-bug051-shutdown.log` — 46 passed
  (`test_daemon_shutdown`, `test_daemon_shutdown_drain`, `test_plan4_remedy_r3`, `test_watch`).
- Full suite: `workflow/review-output/pytest-bug051-full.log`.

## What this does NOT fix {#open}

The other eight findings of that audit are still open — **#s-2** (`_inflight_ops` keyed by op NAME)
and **#m-5** (the suite cannot run against a detached checkout of its own commit) are the ranked
next two. {#open-lead}
