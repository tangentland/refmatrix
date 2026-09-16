---
gmd: "0.1"
id: remedy-plan-12
title: "Implementation summary: plan-12 ch-bsd round 1 remedy"
tags: [summary, plan-12, remedy, bsd]
metadata:
  node_type: summary
  task: plan-12-open-bug-remediation
  created: 2026-09-16
---

# Remedy: ch-bsd plan-12 round 1 (15 findings) {#root}

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: amends -> [[bsd-plan12-open-bugs-9494f1b]]

## The two blockers were the same defect twice {#blockers}

Both new instruments sampled a number at the wrong instant.

- **#b-1 `queue_depth`** was read in `_augment_info` AFTER `_handle`'s `finally` had drained
  `_pending`, then decremented again "for the caller being served". It reported the callers who
  arrived BEHIND the asker, minus one — **0** in the single-contender case the `(1 + queue_depth)`
  term exists for. Now sampled at ENQUEUE and passed in. The new test drives the REAL `_handle`
  over socketpairs with a blocking worker; restoring the old sampling makes it RED.
- **#b-2 phase labels** were shifted one interval, so the tool built to attribute 8.5 s billed
  `store-bind` for `build_context`'s seconds — and the measurement document told the reader to
  shift the labels instead of the code doing it. Now each interval is named by the phase that ends
  it, with `import` first and `exit` last; `test_each_interval_carries_the_phase_that_produced_it`
  pins costs in advance. The compensating sentence is gone and the figures were re-taken.

## The rest {#rest}

| finding | what changed |
|---|---|
| #b-3 alert gate | `derive_status` distinguishes `never_stamped` from stamped-and-different. The hub row is hot on `derive_stale` and on `private_workers`; `derive_unstamped` is carried and cold — on ship day every store is unstamped, and that state ends at the next ingest with no gate to remember. |
| #b-4 mock registry | 12 rows for the five new test files plus this remedy's, each naming what is replaced and its graduation trigger. `_wire_replica_leg` graduates when a test builds the reranker through the real `shared_reranker` — patching it is what hid #m-1. |
| #s-1 `oldest_version` | `_version_key` parses components; `min("0.9.0","0.71.0")` no longer prints `derived by the version you are running`. |
| #s-2 `derive_status` pool | added to `CLI_OPS`, and the unknown render carries `[UNVERIFIED]` like its neighbour. |
| #s-3 always-on claim | corrected in the measurement and the registry: `scan-prompt`'s leg IS windowed at 2048 and its ranking effect is unmeasured. |
| #s-4 in-process embedder | `worker_kinds()` reports `in-process`, `render_worker_split` and the hub row count it as a split, and `_maybe_adopt_shared` now heals it by dropping the resident model. |
| #s-5 registry columns | 12 short rows padded to the header width; bug-024 / bug-025 Status cells actually say `fixed`. |
| #s-6 deferral registry | both rows moved to the Graduation Log with their shipping commits. |
| #s-7 A/B harness | `eval/production/rerank_window_ab.py`, re-run: 541 / 672 at 2048 and 509 / 509 at 700, identical to the published table. |
| #m-1 deadline anchor | `shared_reranker` takes `t0` before the probe and passes an absolute deadline. |
| #m-2 renderers | `CliRunner` tests over `rmx hub queues` and `rmx daemon status`. Writing them caught a live defect BSD did not see: rich parsed `[memory-p]` as markup and deleted the partition name — the renderer class that ate every wikilink in bsd-plan7-10 r3. Now escaped. |
| #m-3 partitions | `derive_status all=True` walks every partition; `daemon status` renders per partition, so the memory corpus has a freshness signal. |
| #m-4 suite | the contaminated log is kept as `pytest-plan-12-CONTAMINATED.log` and the suite re-run from a clean tree. |

## Evidence {#evidence}

- Targeted: 85 passed across the seven plan-12 test files.
- Incident replay for #b-1: restoring the old sampling point fails
  `test_the_server_reports_the_callers_ahead_of_you`.
- Harness re-run reproduces the published A/B numbers exactly.
- Phase lines re-measured after the label fix, on both stores.
