---
gmd: "0.1"
id: remedy-plan-12-r2
title: "Implementation summary: plan-12 ch-bsd round 2 remedy"
tags: [summary, plan-12, remedy, bsd]
metadata:
  node_type: summary
  task: plan-12-open-bug-remediation
  created: 2026-09-16
---

# Remedy: ch-bsd plan-12 round 2 (7 findings, 15 → 7) {#root}

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: amends -> [[remedy-plan-12]]

## The blocker, and why the round-1 test could not see it {#blocker}

`_handle` incremented `_pending` AFTER `_worker(role)` — which holds the server lock across client
creation and the version handshake, i.e. **6.6 s of cold model load**. A caller with two reranks
ahead therefore read `queue_depth: 0` during a cold start: the same off-by-an-instant as #b-1, one
scope out.

The round-1 test could not catch it because its stub worker answers `info` instantly, which stubs
out the very section that blocks. The new test makes the worker's **construction** block on an
event and asserts 2. Moving the join back below `_worker()` turns it RED. Fixed in `2af5014`,
before the report landed; `_drop_worker` now tolerates `w` being unbound when `_worker()` raised.

## The one I got wrong by assumption {#gate}

Round 1's alert gate fired on version inequality. ch-bsd measured the fleet: **34 version bumps in
ten days, 8 stores, 6 of them repos that never re-ingest.** Zero rows hot on ship day — then each
store stamps once, the next bump turns it hot, and about two days out all 8 rows alert several
times a day at roughly 1-in-34 signal. "Genuinely stale" was an unchecked assumption in my own
one-liner.

Hotness is now a **distance**: `derive_status.behind_code` is true when a pass's `derived_at`
predates the newest mtime among `ingest.py` / `ingest_gmd.py` / `store.py` — the code that actually
derives a graph. A deploy that does not touch ingest leaves every store cold. Version drift alone
is carried as `derive_version_drift` and stays cold; the human-facing `stale` line is unchanged,
because a human asking "which version built this" still deserves the answer.

## The rest {#rest}

| finding | what changed |
|---|---|
| partition walk untested | `test_op_derive_status_walks_every_partition` drives the REAL op against a real `Store` with a current default partition and a stale `memory-p`; deleting the branch turns it RED (it was the one surviving mutation of 13). |
| composite rebuilt #s-1 | the `all: True` composite no longer copies the default partition's fields. It answers only what is true of the whole store (`stale`, `stale_partitions`, `running_version`), so nothing can render `derive: 0.71.0 (running 0.71.0) — stale` again. |
| daemon-routed path unmarked | `phase_mark("daemon-ping")`, `("daemon-rpc")`, `("render")` on the branch that is the DEFAULT on a live machine — ~1.5 s of RPC used to land in `exit`. |
| in-process "dropped" | the log says what actually happens: our reference is released, the model stays resident until in-flight callers finish, and `worker_kinds()` flips to `shared` because that is what the NEXT call uses — not because the RSS came back. |
| mock registry | a row for `tests/test_rerank_window.py` (`_M`, `_C`, and the `Reranker._load` no-op). |
| harness arms | `--arms` with `head`, `anchor_only`, the `split<frac>` sweep and `shipped`. The arms that JUSTIFY the design are now in the repo, not in a scratch script. |

## One published number was wrong {#correction}

Re-running the committed harness reproduced 541 / 502 / 672 at 2048 and 509 at 700 exactly — and
showed the 700-char split at 0.5 covering **338, not 500**. The 500 was the **0.7** arm's number,
transcribed onto the 0.5 row: a 32% error in the figure that chose `WINDOW_MIN_CHARS`, sitting
under a comment that said "Measured, not chosen". It errs toward making the floor look *less*
justified than it is, and it was caught only because the harness is committed — which is the
argument for committing harnesses.

Corrected in `reranker.py`, the measurement, the task summary, the registry row and the test
docstring.
