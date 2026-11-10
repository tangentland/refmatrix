---
gmd: "0.1"
id: bsd-plan24-spec-review-r6-34fedb1
title: "Plan-24 spec review r6: facts.log is appended after the commit, not in the transaction; the key event must ride the effect's own append batch"
tags: [bsd, plan-24, spec-review, idempotency, facts-log]
severity: SKETCHY
plan: plan-24-mod-transport
task: task-24.2
---

# ch-bsd findings — plan-24 spec review r6 at 34fedb1 {#root}

**Commit:** 34fedb1 (3e7b938 re-hashed the probe logs), branch wave0-spec-reviews
**Date:** 2026-10-20T12:20:15-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator (spec author)
**Scope:**
- the rev-r6 changes in 24.2 and 24.2a;
- `eval/mod_probe` logs;
- the facts.log writer, compaction and rebuild in src at HEAD;
- DuckDB 1.5.2 (dev) and 1.5.3 (deploy), and SQLite 3.53.1, tested in-memory.

rel: evidence-for -> [[plan-24-mod-transport]]
rel: derives-from -> [[bsd-plan24-spec-review-r5-0109574]]

## r5 closure {#r5-closure}

- **s1:**
  - (a) DDL in `duckdb_catalog.py` plus the SQLite mirror;
  - (b) rebuild, dump and `replica_merge` are covered;
  - (c) the check-and-insert happens inside the op;
  - (d) each op gets its own key, `<key>#<op-index>`.

  All four are closed in design; see s1 below for how the log append is described.
- **s2:** closed. No `*_sha256=` token in the logs is followed by text.
- **m1:** closed. The three callers are listed.

`INSERT … ON CONFLICT (key) DO NOTHING RETURNING` returns the row on the first insert and `[]` on
a conflict, on DuckDB 1.5.2, DuckDB 1.5.3 and SQLite 3.53.1. The SIGABRT history
(`project_daemon_sigabrt_diagnosed`) was `DO UPDATE` under heavy upsert churn on `entities`'
UNIQUE index. A low-volume `DO NOTHING` on fresh keys, serialized under `_store_lock`, is not
that pattern.

Compaction (`dump_catalog_to_log`, the size-rotation tick at daemon.py:2484) keeps keys younger
than 7 days by d16. That holds only if the key's original `ts` is carried (m1).

## Findings {#findings}

### SKETCHY s1: "in the same transaction" cannot be built; the property that matters is unstated {#s1}

d16 says the `idempotency` event is "appended in the same transaction as the effect".
`Store._log_event` / `_log_events` (store.py:1119-1152) append to `facts.log` AFTER the commit,
in a plain file write outside DuckDB.

The property that actually holds against a crash: the key's event goes in the SAME `_log_events`
batch (one write) as the effect's own events. Then after a crash both are in the log or neither
is.

If the key is logged by a separate `_log_event` call, a crash between the two calls leaves the
effect in the log and the key out of it. The next rebuild then re-runs the write.

**Fix:**
- Reword d16 / R8 to "in the effect's own post-commit `_log_events` batch".
- `Store.record_idempotency` returns the key's record for the op to add to its batch, never
  writing it alone.
- AC-17 adds a crash between the commit and the append, rebuilds, and checks: the re-submit runs
  exactly once. This holds because the effect and the key are absent from the log together.

### MEH m1: dump and replay must preserve each key's own `ts` {#m1}

`dump_catalog_to_log` and its replay must write each key's recorded `ts`, not the dump time.
Otherwise every compaction re-dates the keys and the 7-day window never closes. AC-17's 6-day /
8-day case should run through a dump and a rebuild.

Two side notes:
- Dev runs DuckDB 1.5.2 and deploy runs 1.5.3; this is pre-existing, so pin it in the AC
  environment notes.
- The index-repair tick (daemon.py:2388) need not cover the new primary key unless it shows
  drift.

## Verdict {#verdict}

2 findings (0 BULLSHIT, 1 SKETCHY, 1 MEH).

rel: contradicts -> [[plan-24-mod-transport#decisions]]
