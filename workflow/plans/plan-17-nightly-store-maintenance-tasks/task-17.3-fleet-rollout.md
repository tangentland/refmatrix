---
gmd: "0.1"
id: task-17.3-fleet-rollout
title: "Task 17.3: roll maintenance out to the 8 registered daemons by hand — dry run, backup, run, arm — measure before and after, and document it"
tags: [task, rollout, measurement, docs]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-15
---

# Task 17.3: fleet rollout {#root}

> Plan: [plan-17-nightly-store-maintenance](../plan-17-nightly-store-maintenance.md)
> Status: Pending (revision round 7, 2026-10-15: nm17-r7-3's hold bound from the watchdog and
> nm17-r7-1's runbook text, see [[#rev-round-7]]; revision round 6, 2026-10-15: ns17-r6-1's third restore scenario, see
> [[#rev-round-6]]; revision round 5, 2026-10-14: ns17-r4-2's runbook text, see [[#rev-round-5]];
> revision round 3: ns17-r3-2, nm17-r3-2, nm17-r3-4; see [[#rev-round-3]]. Round 2: ns17-3, ns17-5, ns17-6, d9c; see [[#rev-round-2]])
> Depends on: 17.1, 17.2, 17.4; deployed

rel: part-of -> [[plan-17-nightly-store-maintenance]]
rel: depends-on -> [[task-17.1-vectors-maintain-op]]
rel: depends-on -> [[task-17.2-hub-nightly-tick]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81#s-4]]
rel: derives-from -> [[plan-review-2026-10-14#t3]]
rel: depends-on -> [[task-17.4-factslog-backup-snapshot]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06#ns17-6]]
rel: implements -> [[plan-review-2026-10-14#t9]]
rel: related-to -> [[feedback_generated_data_off_watched_tree]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r3-6091648#nm17-r3-4]]
rel: related-to -> [[feedback_external_calls_policy]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nm17-r7-3]]
rel: derives-from -> [[bsd-plan23-17-spec-rereview-r7-331b414#nm17-r7-1]]
rel: related-to -> [[task-23.5-read-path-and-holder-bounds]]

## Why {#why}

After 17.2 deploys, every store is unarmed, so the hub only dry-runs it (decision d3d). The real
nightly op starts store by store, when this task arms it by hand after a dry run and a backup. The
2026-10-07 hand compaction covered refmatrix, viascope and cliquedb; refmatrix has regrown
(17-261 versions per dataset, 150 MB, spec review #verified), and the stores it skipped have never
been compacted. {#why-body}

## Requirements {#requirements}

1. **R1 By hand, every registered daemon** (decision d3d; spec review #s-4, #s-6). {#r1-hand-run}
   For each of the 8 stores in the registered daemon list (cliquet, global, thiquet, atldb,
   viascope, refmatrix, orderly, cliquedb), through the deployed `rmx` and its daemon only:
   1. `rmx vectors maintain --dry-run`; read the report (orphans, `missing`, cap refusals);
   2. back up `vectors/` with an APFS clone (`cp -c -R`) to `vectors.bak-<date>-maintain`;
   3. `rmx vectors maintain`; read the report; an `ok:false` (a fingerprint mismatch, a failure)
      stops the rollout for that store and is reported to the user before anything else;
   4. a `refused:orphan_cap` dataset is expected on at least this repo (the plan's own 559 of
      5,495, 10.2 %, is above the 5 % cap, ns17-3). Compaction still ran (17.1 R6). Each capped
      dataset, its orphan count and ITS dry-run `orphan_list_sha` are shown to the user; ONLY
      after the user confirms, `rmx vectors maintain --confirm-orphans <sha> [--confirm-orphans
      <sha> …]` (one per confirmed dataset) is run by hand (d9c). It reaps the confirmed ids that
      are still orphans (17.1 R6's intersection, ns17-r3-2); orphans new since the dry run are
      named in the outcome and follow the cap, so no re-confirmation loop arises;
   5. `rmx hub maintain arm --root <root> --step vectors_maintain --run-id <the run_id of step
      3's (or step 4's) successful hand run>` (17.2 R7; the gate also finds step 1's earlier
      successful dry run in `runs.jsonl`, nm17-r3-2). Only steps this task hand-ran are armed:
      `factslog_backup` needs no arming (17.2 R7 table); 19.4's and plan-18's steps are armed by
      their own rollouts;
   6. after the store's first `factslog_backup` copy exists and is no older than one day,
      `sudo tmutil addexclusion -p <store>/facts.log` (17.4 R7; the user runs the `sudo`).

   A store whose daemon does not answer is skipped and counted; it is not run in-process.
   Backups are deleted only after the user confirms (this replaces the old "after N days").
2. **R2 Measure** (spec review #s-4; decision #t3-fixes "17.3 latency on refmatrix, cliquedb,
   thiquet"). {#r2-measure}
   - **Every store, before/after:** vectors bytes, versions per dataset, orphans reaped, `missing`,
     per-dataset hold seconds, `check_s`.
   - **Real stores give the before/after table only.** No live store will have ≥ 10,000
     `code.lance` versions at rollout (the fleet was compacted on 2026-10-07 and regrows at about
     25-37 versions per day per busy dataset), and no 2026-10-07 `vectors.bak-*` backup exists
     (the re-review's `find` under cliquedb, viascope, this repo and `~/refmatrix` returned none,
     ns17-6). thiquet (≤ 5 versions) is the small-store control: its maintenance must take the
     17.1 R5 skip path, and its `check_s` is recorded. The global store is memory-only, so it gets
     no latency leg.
   - **The synthetic clone is the stated default for the latency, no-match and hold legs**
     (ns17-6, #t9-fixes). `scripts/plan17-versioned-clone.py`, run with the DEPLOY interpreter:
     1. `mkdtemp(prefix="rmx17-", dir="/tmp")`, a short root OFF every watched tree;
     2. copy this repo's lock-free read snapshot (`catalog.read.duckdb`) and `vectors/` into it
        (`cp -c -R`, read-only on the source), laid out as a store whose active slot is the
        snapshot copy;
     3. commit 30,000 single-row upsert / delete cycles to the clone's `code.lance` with `lance`
        directly (no `Store`, no daemon), and record the version count (≥ 30,000);
     4. start a throwaway daemon on the clone with `rmx daemon start --standalone --no-watch`
        (never launchd: `--standalone` forks a plain process and never defers to a LaunchAgent,
        `cli.py:2930-2962`) and `HOME`, `RMX_HOME`
        and `REFMATRIX_ROOT` inside the tmp dir (off the live hub and registry), through the
        deployed `rmx`, same version, so no version handshake fires; it is stopped before the
        clone is deleted.
     5. **Models (nm17-r3-4).** A tmp `HOME` moves the model cache path, and models load from the
        local cache only (`feedback_external_calls_policy`; `models_local.py:50` sets
        `HF_HUB_OFFLINE=1`). The clone daemon therefore runs with NO model: `RMX_NO_EMBED_WARMUP=1`
        (`daemon.py:1161`) and `HF_HOME` left inside the tmp dir, so it can neither download nor
        write into the real cache. The timed re-sync measures the purge / Lance delete path (the
        bug-085 cost this plan bounds), not embedding; an embed attempt fails offline and is
        counted in the log, which states "no model". There is no "embedding off" switch at HEAD
        (`5a8bf29`); if the re-sync turns out to wait on an embed, that is a gap reported to the
        user, not worked around.
     6. **Build time, stated (nm17-r3-4).** 30,000 single-row Lance commits are expected to take
        on the order of tens of minutes (each commit writes a manifest; the 2026-10-07 store grew
        ~61k versions over weeks of normal use); the script logs its rate every 1,000 commits and
        the total. The AC FAILS rather than being shortened: no smaller clone is substituted.
   - **Latency (on the clone):** one re-sync of `src/refmatrix/store.py` (copied into the clone's
     project tree) through the throwaway daemon, timed before and after `rmx vectors maintain`
     on the clone, with `code.lance`'s version count recorded at each timing.
   - **No-match re-sync** (17.1 R9, on the clone): a re-sync of a file whose ids carry no vector
     commits 0 Lance versions.
   - **Hold bound** (spec review #s-1; nm17-r7-3): the clone's largest dataset step, and every
     real store's steps, hold `_store_lock` for less than
     `HOLD_BOUND_S = HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S` (50 s at the defaults,
     `daemon.py:63`, `:66`), read from the op report's `hold_s`. The bound comes from the
     watchdog, not a round number. The coupling, at HEAD `77ac38f`: the heartbeat is a no-op
     submitted to the 4-worker cli pool and the file is touched only when it completes
     (`daemon.py:1319-1337`); cli reads such as `stats` take `_store_lock` unbounded
     (`daemon.py:3732`), so four of them queued behind one maintenance hold stop the beat for
     the whole hold; the hub restarts after `WATCHDOG_GRACE_MISSES` (3) missed pings AND a
     heartbeat older than `HEARTBEAT_STALE_S` (60 s) (`hub.py:305-317`). Round 6's "< 60 s"
     equalled the stale threshold with no margin: a 59.9 s hold under hook load (17.2's catch-up
     runs at wake, not only at 03:30) crosses it by the next 5 s tick, and the watchdog
     restarts the daemon mid-step. Two heartbeat intervals of margin cover one tick of skew on
     each side. 0.78.2 (bug-115/116: `ping` on the dispatcher thread, a beat on every cli
     completion) narrows the restart to a saturated dispatcher but does not remove it, and
     23.5 removes the reads' wait on the lock ([[task-23.5-read-path-and-holder-bounds#r6]]);
     until 23.5 is deployed fleet-wide this bound is the margin, and after it the bound is kept
     because 17.1's holds still serialize every writer. The script computes `HOLD_BOUND_S` from
     the deployed daemon's constants (env overrides included) and prints it beside the
     holds.
   - The clone is deleted at the end of the task; its version count, timings and the script's
     log go to `workflow/review-output/plan17-rollout-clone.log`.
3. **R3 Docs.** {#r3-docs}
   - `docs/PERFORMANCE.md` gets the maintenance section (schedule, arming, the tag rollback
     point, the orphan list and `rmx vectors restore`, including `id_map` for restores with new
     ids).
   - The `facts.log` restore runbook documents 17.4 R6's three scenarios
     ([[task-17.4-factslog-backup-snapshot#r6-restore]]; ns17-r4-2, ns17-r6-1) and its
     classification (daemon refusal first; read-only catalog probe, a lock error, told by its
     message "Could not set lock on file", = daemon up; live-log parse probe): (a) a damaged
     live log under a healthy catalog is fixed by `rmx compact-log --force`, never by the
     backup; a daemon crash-looping on a catalog that still OPENS (the 2026-09-14 ART-index
     shape, `project_refmatrix_entities_index_crashloop_0914`) is also class (a) and is fixed
     by the offline table rebuild, never by a restore or a compaction (nm17-r7-1); (c) a lost
     or unopenable catalog with an intact, parsing live log is rebuilt from the LIVE log (the
     backup only if that rebuild fails verification; the script prints the source); (b) a
     lost catalog AND a missing or unparseable live log is restored
     from the backup copy by `scripts/factslog-restore.py` (daemon stopped; throwaway rebuild
     and verify first; existing files moved aside, never overwritten; the verified catalog
     promoted into the live root's writer slot and the source installed as its log), then the
     daemon start and the re-embed. It also documents the backup-age alarm (17.2 R8).
   - `docs/INDEX.md` and the ARCHITECTURE index.
   - The plan-17 decisions (d-1..d-4, d2b, d3a..d3e) are recorded in the implementation summary.
4. **R4 Watch one night.** After the first scheduled 03:30 run with the fleet armed, `hub.log` and
   the `global:queues` summary are read: every store `ok` or `skipped`, the tags held per dataset,
   and no `cli.log` row with `lance_retries > 0` that is unexplained. The result goes into the
   implementation summary.

## Acceptance criteria {#acceptance}

1. The before/after table for all 8 stores is in the implementation summary.
2. On the synthetic clone (≥ 30,000 pre-run `code.lance` versions, recorded), the after-run
   re-sync latency is ≤ 1/5 of the before-run latency. Fails if maintenance did not compact; a
   clone with fewer than 30,000 versions fails the AC instead of being waived.
3. The no-match re-sync on the clone commits 0 Lance versions (version count before = after).
4. Every reported hold is < `HOLD_BOUND_S` (50 s at the defaults; computed and printed by the
   script, nm17-r7-3); any hold ≥ `HOLD_BOUND_S` is a finding in the summary, not averaged
   away. A hold of 55 s FAILS this AC (it passed round 6's "< 60 s").
5. Each store is armed only after its dry run, backup and hand run succeeded (order visible in the
   rollout log), and each arm names the `run_id` of that hand run (17.2 R7 refuses otherwise).
   Every `--confirm-orphans` run is preceded in the log by the user's confirmation.
6. One scheduled night observed and reported.
7. Backups removed only after the user confirms.
8. No store's `facts.log` is excluded from Time Machine before its `backups/facts.log.daily`
   exists and is no older than one day (17.4 R7).

## Test strategy {#test-strategy}

This task runs no new test suite; it is a rollout on live stores through the DEPLOYED `rmx` and the
daemons, never a dev-venv `rmx`. Any re-run of 17.1/17.2's suites during the rollout uses the 23.0
sandbox (decisions d1a/d1b). Every measurement command's output is captured to
`workflow/review-output/plan17-rollout-*.log`.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| 17 #s-4 (latency cannot fail, global, store list, backups) | [[#r1-hand-run]], [[#r2-measure]], AC-2, AC-7 |
| 17 #s-6 (8 stores) | [[#r1-hand-run]] |
| 17 #s-1 (numeric hold bound) | [[#r2-measure]], AC-4 |
| 17 #b-6 (61k-clone measurement) | [[#r2-measure]], AC-3 |
| 17 #s-8 (no in-process run) | [[#r1-hand-run]] |
| d3d (arm by hand after dry run + backup) | [[#r1-hand-run]], AC-5 |
| #t3-fixes (latency on refmatrix, cliquedb, thiquet) | [[#r2-measure]] |
| d3c (reader retries observed) | R4 |
| d1a/d1b (23.0) | [[#test-strategy]] |

## Revision round 2 (2026-10-14) {#rev-round-2}

| finding / decision | answered at |
|---|---|
| ns17-6 (latency and no-match ACs had no input), #t9-fixes "17.3 ACs on a synthetic 30k-version clone" | [[#r2-measure]], AC-2, AC-3 |
| ns17-3, d9c (the cap trips on this repo; release by `--confirm-orphans`) | [[#r1-hand-run]] step 4, AC-5 |
| ns17-5 (arm only what was hand-run, by `run_id`) | [[#r1-hand-run]] step 5, AC-5 |
| nm17-4 / 17.4 R7 (Time Machine exclusion after the copy exists) | [[#r1-hand-run]] step 6, AC-8 |
| ns17-2 (hold seconds from 23.1's `hold_s`) | [[#r2-measure]] hold bound |

## Revision round 3 (2026-10-14) {#rev-round-3}

Source: [[bsd-plan23-17-spec-rereview-r3-6091648]].

| finding / decision | answered at |
|---|---|
| ns17-r3-2 (per-dataset sha; intersection release) | [[#r1-hand-run]] step 4 |
| nm17-r3-2 (arm gate needs the earlier dry run) | [[#r1-hand-run]] step 5 |
| nm17-r3-4 (clone daemon with tmp `HOME`; build time; no shortening) | [[#r2-measure]] steps 5-6 |
| ns17-r3-4 (restore runbook order) | [[#r3-docs]] (the runbook documents 17.4 R6's script) |

## Revision round 5 (2026-10-14) {#rev-round-5}

Source: [[bsd-plan23-17-spec-rereview-r4-878647c]].

| finding / decision | answered at |
|---|---|
| ns17-r4-2 (the runbook restored the wrong thing; offsets unread) | [[#r3-docs]] (both scenarios; no offset step) |

## Revision round 6 (2026-10-15) {#rev-round-6}

Source: [[bsd-plan23-17-spec-rereview-r6-0e77da3]].

| finding / decision | answered at |
|---|---|
| ns17-r6-1 (a lost catalog with an intact live log was routed to the day-old backup) | [[#r3-docs]] (three scenarios and the classification) |

## Revision round 7 (2026-10-15) {#rev-round-7}

Source: [[bsd-plan23-17-spec-rereview-r7-331b414]]. Code facts re-read at HEAD `77ac38f`; 0.78.2
read on its branch (`607d759`). The round-6 table above is unchanged history.

| finding / decision | answered at |
|---|---|
| nm17-r7-3 (the < 60 s hold bound equals the heartbeat-stale threshold; the heartbeat is a no-op on the 4-worker cli pool) | [[#r2-measure]] hold bound (`HOLD_BOUND_S = HEARTBEAT_STALE_S − 2 × HEARTBEAT_INTERVAL_S`, 50 s; the coupling cited in code; what 0.78.2 and 23.5 change), [[#acceptance]] AC-4 (55 s now FAILS) |
| nm17-r7-1 (the ART-index precedent misfiled under (c); the lock discriminator unnamed) | [[#r3-docs]] (lock error told by its message; the crash-loop shape is class (a), fixed by the offline table rebuild; (b) covers an unparseable live log); the script side is [[task-17.4-factslog-backup-snapshot#rev-round-7]] |
