---
gmd: "0.1"
id: impl-task-t0-6-plan7-dense-rerun
title: "T0.6: the plan-7 LongMemEval dense and fused re-run on 0.84.0"
tags: [implementation-summary, t0, t0-6, plan-7, longmemeval, eval, embed, bug-030, bug-300]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-23
---

# T0.6: the plan-7 LongMemEval dense and fused re-run {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-6]]
rel: realizes -> [[task-7.4-plan-7-longmemeval]]
rel: evidence-for -> [[longmemeval-report#embed]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

Branch `task-t0.6-plan7-dense-rerun` in `/Volumes/littlebig/refmatrix-t06`, base `33825985`. No
`src/` change. The run used the deploy build `~/bin/rmx` (refmatrix 0.84.0, deploy tree
`cab0a7dc`, read with `rmx version -v` before the run) through the harness only. {#lead}

## R6.2: backup, then open {#backup}

- **Free space before the copy:** 199 GiB available on `/Volumes/littlebig`; the store was 9.5 GB.
- **Backup:** `/Volumes/littlebig/longmemeval-store-backup-2026-11-23/.refmatrix`, 9.5 GB
  (9,945,432 KB, the same as the source; `ls -lR` size and name listing identical). Copy time
  4m39s. The 0.69.1 data-volume results were copied beside it as
  `/Volumes/littlebig/longmemeval-store-backup-2026-11-23/results-0.69.1-2026-09-15` (212 KB),
  because `run.py` rewrites `rank-*.json` and `summary.json` in place. Kept until T0.6's ch-bsd
  round closes. {#backup-path}
- **Open:** the 0.69.1 store opened read-only under 0.84.0 (`rmx stats`, 2.6 s: 19,829 memory,
  406,886 concepts). No migration error. **Path taken: opened, embed resumed; no rebuild.**
  {#store-path}

## R6.7: what the run touched outside the eval store {#r6-7}

- **Daemon: none.** `ingest.py` and `run.py` start no daemon, and no `rmx` verb they call spawns
  one (only `daemon start/restart`, `compact` and `repair-index` do, in the deploy `cli.py`).
  Every call ran daemonless: the embed opened the active slot in-process, each read opened
  `catalog.read.duckdb`. Before and after: no `rmxd.pid`, no socket, no launchd job for the store.
  There was no daemon pid to stop. {#daemon}
- **Model workers: the hub's shared pair** over `~/.refmatrix/models.sock` (`new_model_client`
  takes the shared worker when it answers; `RMX_SHARED_MODELS` unset). Embed pid 78831 and rerank
  pid 78880, both children of hub pid 78825, were the only workers in 20 of 21 two-minute
  samples (`/Volumes/littlebig/longmemeval/t06-workers-2026-11-23.log`). One sample
  (01:35:11Z, during `scan`) also caught an embed worker pid 87449 with parent 87446, age 0 s.
  The sampler did not record the parent's command line, so it cannot be attributed: this
  machine also runs the `rmxtest` lanes. The rerank worker's RSS went from 0.66 GB to
  1.42–1.53 GB during the `-rr` window (01:21Z–01:24Z). {#workers}
- **Window:** 2026-11-24T01:03:10Z to 01:43:19Z (2026-11-23 local), 40 min of shared-worker load:
  embed 997.4 s, compile preview 8.4 s, retrieval 1,400 s. {#window}
- **Hub:** `rmx hub status` before and after are byte-identical (hub pid 78825, 8 stores,
  `restarts=0`, v0.84.0). Saved as `/Volumes/littlebig/longmemeval/t06-hub-status-before.txt`
  and `t06-hub-status-after.txt`. No fleet daemon, hub, launchd job or hub config was touched.
  {#hub}

## R6.1, R6.3: the run {#run}

```
python3 ingest.py --rmx ~/bin/rmx --skip init --skip ingest-gmd
python3 run.py --rmx ~/bin/rmx --subset 20 --depth 50 --at 1,5,10,20 --workers 4 \
  --mode union --mode restricted --method recall --method recall-fuse \
  --method recall-rr --method recall-fuse-rr --method context --method scan
```

Run from `eval/production/longmemeval/`, logged to
`/Volumes/littlebig/longmemeval/t06-run-2026-11-23.log`, each step under a `timeout`.
`REFMATRIX_ROOT` was pinned per process by `paths.rmx_env`, never exported. **Embed wall time:
997.4 s** for 19,829 rows (78 batches), no failure. 0 failed questions on every surface. {#run-cmd}

## Results (one build, one run) {#results}

Restricted mode, depth 50, 120 questions; every row saturated (hit@5 = ceiling):

| surface | R@5 | hit@5 | MRR@20 | ceiling | union R@5 |
|---|---:|---:|---:|---:|---:|
| `context` | 0.605 | 0.683 | 0.679 | 0.683 | 0.411 |
| `scan` | 0.547 | 0.642 | 0.637 | 0.642 | 0.465 |
| `recall` | 0.515 | 0.608 | 0.596 | 0.608 | 0.239 |
| `recall-fuse` | 0.515 | 0.608 | 0.596 | 0.608 | 0.239 |
| `recall-rr` | 0.527 | 0.625 | 0.613 | 0.625 | 0.266 |
| `recall-fuse-rr` | 0.513 | 0.608 | 0.604 | 0.608 | 0.298 |

- `context` and `scan` reproduce the 0.69.1 restricted rows and per-type rows to three decimals.
  Both runs read the same 2026-09-15 read snapshot.
- `recall-fuse` = `recall`, 120 of 120 rankings (the lead's finding, bug-300: the memory BM25 leg
  returns [] on this corpus; bug-301: `content_terms` keeps trailing punctuation). The reports
  label it and make no fusion claim. `recall-fuse-rr` differs from `recall-rr` through the
  hybrid's wider dense pool.
- Dense wins preference (R@5 0.450 vs `context` 0.200), multi-session and temporal-reasoning; it
  loses knowledge-update (0.300 vs 0.925) and single-session-user (0.300 vs 0.500). {#results-lead}

## R6.4, R6.5: write-up and artifact {#writeup}

- `eval/production/longmemeval/results/summary-120-0.84.0.json`: run.py's `summary.json`
  verbatim (sha256 `8584b291a37df13d8bb08f3297b44131a094bc4b8534a79d9ff968e77f85f6ae`) plus a
  `_provenance` key (harness, commands, version, deploy sha, date, window, corpus size, store path
  taken, daemon and worker record). Rankings stay on the data volume: they hold ids only, but they
  are not needed to check a cited figure.
- `REPORT.md`: setup table (build, store path taken, embed wall time, daemon, workers, read
  snapshot), six-row `#restricted` and `#union` tables with a ceiling column, per-type for all six,
  a `#fusion` section for bug-300/301, `#embed` rewritten as the result, the 0.69.1 rows in
  `#history-0-69-1`, `#next` item 4 closed and a bug-300 item added.
- `README.md` and `docs/PERFORMANCE.md` (`#longmemeval`) cite the artifact path with one table,
  no fuse figure quoted as fusion.
- task-7.4 status drops "(symbolic only …)". Plan-7 closes on the T0.6 ch-bsd round and T0.7's
  deferral-row edit ([[task-t0-suite-trust-sweep#amend-8]]), not here. {#writeup-lead}

## AC-6.2: the test, RED then green, and M6.1 {#tests}

`tests/test_eval_artifact_cited.py` gains two cases: the artifact's provenance and 0 failed
questions per surface, and every cell (6 surfaces × 5 columns) of the cited table in BOTH docs
compared with the artifact.

- **RED** at `371d0677` (docs + test, no artifact), local lane slot rmxtest2:
  `....FF`, both new cases fail with `summary-120-0.84.0.json missing`
  (`workflow/review-output/t06-1-red.log`). The mini was unreachable (ssh timeout).
- **Green** after the artifact: 6 passed (local check, `t06-2-green-local.log`; lane run below).
- **M6.1:** README's `recall-rr` union R@5 edited 0.266 → 0.267: `1 failed, 5 passed`,
  `AssertionError: ('README.md', 'recall-rr', 'union R@5', '0.267', '0.266')`
  (`t06-m61-mutation.log`). README restored with `git checkout`. {#tests-lead}
