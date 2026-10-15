---
gmd: "0.1"
id: task-16.6-learned-row-validation
title: "Task 16.6 (Wave-1 slice): the learned-evidence sidecar (replayable from facts.log), THE re-run verifier and its line-set API, read-time marks with a named reader, and the provenance backfill (audit/prune/repair in plan-22; the learn-time write in 16.1)"
tags: [task, grep, learning, validation, provenance, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
  updated: 2026-10-15
---

# Task 16.6: the learned-evidence sidecar, its verifier, read-time marks and the backfill {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision round 14, 2026-10-15, d9ch (b): the dump's dead-end sidecar skip
> stated, [[#rev-round-14]]; revision round 11, 2026-10-15, answering the r11 diff check
> `bsd-plan16-22-spec-diffcheck-r11-d8188ee` s-1(i) and d9cc, [[#rev-round-11]]; revision round
> 10, 2026-10-15, answering the r10 diff check
> `bsd-plan16-22-spec-diffcheck-r10-451b505` s-1 (AC-9d check 2), s-3, m-3 and d9bz,
> [[#rev-round-10]]; revision round 9, 2026-10-15, answering the r9 diff check
> `bsd-plan16-22-spec-diffcheck-r9-29e335a` s-2, m-1, m-5 and d9bu, [[#rev-round-9]]; revision
> round 8, 2026-10-15, answering the r8 re-review
> `bsd-plan16-22-spec-rereview-r8-23ad703` b-1, m-1, m-3, m-5 and d9bl, [[#rev-round-8]]; revision
> round 7, 2026-10-15, answering the r7 re-review
> `bsd-plan16-22-spec-rereview-r7-331b414` b-1 (d9av) and d9ay, [[#rev-round-7]]; revision round 6,
> 2026-10-15, answering the r6 re-review
> `bsd-plan16-22-spec-rereview-r6-0e77da3` m-3 and m-6, [[#rev-round-6]]; revision round 5,
> answering the r4 re-review
> `bsd-plan16-22-spec-rereview-r4-878647c` and d9ab, [[#rev-round-5]]; revision round 3,
> answering the r3 re-review
> `bsd-plan16-22-spec-rereview-r3-6091648` and `plan-review-2026-10-14#t9-approvals` (d9k, d9o);
> [[#rev-round-3]]; round 2 in [[#rev-round-2]]).
> Revision 6 of plan-16's specs was the first revision of 16.6 after its first spec review (r5,
> `bsd-plan16-spec-review-r5-cd7c923`).
> The user asked for it on 2026-10-07: "rmx grep learning entries should be cullable and/or at
> least have a validation process to check for stale entries". The CULL half lives in plan-22
> ([[#split]]).
> **Wave:** 1, after plan-23's task 23.1 (`bind(partition_name)`, the durable queue and bounded drain), and
> before plan-22's 22.1a ([[plan-review-2026-10-14#t8-wave1]]).
> **Depends on:** plan-23 task 23.1 (queue + `bind(partition_name)` drain), plan-23 task 23.0 (the shared
> test sandbox). It does NOT depend on task 16.1 (d6d, [[plan-review-2026-10-14#t8-amendments]]).
> Task 16.1 depends on THIS task: its learn-time provenance write (16.1 R10) needs this table.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-16.1-argv-faithful-learner]]
rel: related-to -> [[project_global_relative_rows_repair]]
rel: amends -> [[plan-review-2026-10-07#contradictions]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: derives-from -> [[plan-review-2026-10-14#t9-approvals]]
rel: related-to -> [[task-22.6-removal-entry-points]]
rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: motivates -> [[plan-22-audited-removal-and-repair]]
rel: motivates -> [[task-22.1-audit-classes]]
rel: motivates -> [[task-22.2-repair-then-remove]]
rel: motivates -> [[task-22.3-bug-086-global-repair]]
rel: specifies -> [[task-22.1-audit-classes#r1-verify]]
rel: related-to -> [[task-23.4-option-a-measurement]]

## Revision round 14 (2026-10-15) {#rev-round-14}

Applies d9ch (b) ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its ch-bsd loop is
clean) where it reads this task. `src/` unchanged. Minimal: one stated rule in [[#r1d]].

| finding / decision | answered in |
|---|---|
| d9ch (b): does R1d's dump skip a sidecar row with a dead end? | YES, now stated in [[#r1d]] "The compactor keeps the sidecar": only the sidecar rows of dumped evidence rows are emitted (keyed by name, `ts` from the dumped append; a dead end has neither), counted `provenance_not_dumped`; the re-log on restore is [[task-22.2-repair-then-remove#r4-relink]] with 22.2 AC-4e's sidecar leg and its two mutations. AC-9b is unchanged (its fixture has no dead end; `provenance_not_dumped` is 0 there) |

rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]
rel: related-to -> [[task-22.2-repair-then-remove#r4-relink]]

## Revision round 11 (2026-10-15) {#rev-round-11}

Answers [[bsd-plan16-22-spec-diffcheck-r11-d8188ee]] where it touches 16.6 (s-1(i), the
`ROW_OPS` wording) under d9cc ([[plan-review-2026-10-14#t12-approvals]]; PROVISIONAL until its
ch-bsd loop is clean; d9cc SUPERSEDES d9cb(b)). `src/` unchanged since `23ad703`. Later rows win
over round 10.

| finding / decision | answered in |
|---|---|
| r11 s-1(i) / d9cc (the drop carries the matched append's entity end; the rebuild matches the full `row_key` plus `detail`) | [[#r1d-one-format]] "Spelling": "the one op whose entity end is null" removed, `row_event` raises on a None entity end for every op; "Key": `evidence_orphan_drop` matches the full `row_key` plus `detail` ("concept-side fields only" removed); AC-9d's builder clause raises on `e=None` for every op |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r11-d8188ee]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 10 (2026-10-15) {#rev-round-10}

Answers [[bsd-plan16-22-spec-diffcheck-r10-451b505]] where it touches 16.6 (s-1's AC-9d caller
list, s-3, m-3) and d9bz ([[plan-review-2026-10-14#t12-approvals]]). `src/` unchanged since
`23ad703`. Later rows win over round 9.

| finding / decision | answered in |
|---|---|
| r10 s-1 / d9bz (22.6's vacuum keys every orphan drop on the orphan's own appends) | [[#r1d-one-format]] "Resolver" names the vacuum scan as a `resolve_c_kind` caller; AC-9d check 2's caller list is Pass 2b, the row pass and the vacuum scan, and `vacuum` calls neither `_row_op_c_kinds` nor `names_from_log` |
| r10 s-3 (`FOLD_OPS` rows named no fold rule) | [[#files-to-modify]] `scripts/factslog-restore.py` row: `learned_provenance` and `learned_provenance_move` are count-neutral (sidecar only), named as ignored; 22.6 AC-6d checks fold == rebuild |
| r10 m-3 (AC-12's `tests/` scan could not see docstrings; self-check exercised one mode) | [[#r1f]]: the `tests/` AST scan also matches string constants, excluding the scan's own module; the text scan widened to `scripts/` and `eval/`; AC-12 adds the docstring mutation and a two-mode fixture-tree self-check |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r10-451b505]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan16-22-spec-diffcheck-r9-29e335a]] where it touches 16.6 (s-2, m-5) and d9bu
([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `428267f` (`src/` unchanged
since `23ad703`). Later rows win over round 8.

| finding / decision | answered in |
|---|---|
| r9 s-2 / d9bu (the incremental replay path has no caller, and the specs kept extending it) | NEW [[#r1f]]: this slice DELETES `Store.apply_log_delta`, `_apply_one_event`, `_apply_event_body` and `_replay_concept` (its only caller is `_apply_event_body`), the unused `daemon.REPLICA_REBUILD_DELTA_BYTES`, the test that drives the path, and every prose mention, with a scan that fails if any comes back (AC-12). Every clause extending the path is dropped: [[#r1d]] "both replay paths", the "two paths agree on KINDED events only" paragraph (bug-120 closes by removal), the incremental sentence of "The order, concretely", the incremental half of the resolver, `row_skips` "on both paths", AC-9's "same holds through `_apply_event_body`", AC-9d check 3's `_apply_event_body` half; [[#files-to-modify]]. The rebuild is the one replay path |
| r9 m-5 (two AC-9d clauses mis-fire on legitimate code) | AC-9d check 3 scoped to the link and row passes of `rebuild_index_from_log` (Pass 3's memory-body membership test named as allowed); check 4 states the parameters come from `row_key(ev)` (`k = row_key(ev)`, then `k[5]`, `k[6]`) |
| r9 m-1 (22.2's helper stops calling the legacy rule) | AC-9d check 2's caller list drops `_row_op_c_kinds`; that helper reads `edge_records.LEGACY_PREFERRED_KIND` (22.2 R3 makes the constant public) |
| ns17-r9-2 (coordinator: every new `facts.log` op this task adds is listed against 17.4's `scripts/factslog-restore.py` `FOLD_OPS`) | [[#files-to-modify]] `scripts/factslog-restore.py` row |

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan16-22-spec-rereview-r8-23ad703]] where it touches 16.6 (b-1, m-1, m-3, m-5) and
d9bl ([[plan-review-2026-10-14#t12-approvals]]). Code claims re-read at `23ad703` (0.78.3,
bug-117: `edge_records.py`, `c_kind` on every edge event, Pass 2b); `src/` is unchanged from
`23ad703` to the revision's HEAD. Later rows win over round 7.

| finding / decision | answered in |
|---|---|
| r8 b-1 / d9bl (the row ops predate bug-117: no `c_kind`; one format, one resolver) | [[#r1d]] `learned_provenance` and `learned_provenance_move` carry `c_kind` and are built by `edge_records.row_event`; [[#r1d-one-format]] (one builder `row_event` / `ROW_OPS`, one key `row_key`, one resolver `edge_records.resolve_c_kind` + `_replay_concept`, one counter `_row_skip` / `row_skips`); the compactor's `learned_provenance` carries `c_kind`; AC-9d (builder, Pass 2b feeding the row pass, five-part AST check) + five mutations; AC-10 list; [[#files-to-modify]] `edge_records.py` row |
| r8 m-1 (the row pass must keep Pass 2b and its counters; stale pins) | [[#r1d]] "The order, concretely": the row pass takes appends AFTER Pass 2b and keeps `evidence_unresolved` / `evidence_skipped_dead`; AC-9c's AST clause targets pass 3 only; [[#files-to-modify]] |
| r8 m-3 (legacy resolution differs between incremental and rebuild) | [[#r1d]] "The two paths agree on KINDED events only"; the bug-registry row is the orchestrator's (this revision touches plan files only) |
| r8 m-5 (line pins shifted under 0.78.3) | [[#r1d]] re-read at `23ad703` (`store.py:7941` sort; dump `ts` at `:7640`/`:7662`), cited by symbol |

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan16-22-spec-rereview-r7-331b414]] where it touches 16.6, and d9av/d9ay
([[plan-review-2026-10-14#t12-approvals]]). The r7 verdict made plan-16 approvable only together
with the lockstep R1d edit (b-1). Code claims re-read at `77ac38f`. Later rows win over round 6.

| finding / decision | answered in |
|---|---|
| r7 b-1 / d9av (the one pass replayed every row op after ALL `evidence` appends, so a rebuild deleted a row re-learned after its removal) | [[#r1d]] "ONE row pass, appends and row ops together, in TIMESTAMP order" (stable `ts` sort, ties by log position, `_row_pass_events`), the "Both replay paths" bullet, and the compactor's `learned_provenance` `ts`; AC-9c (order function + end to end) with two mutations; [[#files-to-modify]]; the same rule in [[task-22.2-repair-then-remove#r3]] |
| d9ay (16.6 R1c is a slot-merge path) | [[#r1c]] RETIRED, anchor kept, reason (writer rotation dropped; bug-113), history kept; AC-2 RETIRED, its `rowid` mutation moved to AC-1; AC-10 list; [[#r1]] keeps the collapse rule; [[#r6]]; [[#split]] row; [[#files-to-modify]] |
| r7 m-3 (a census has no "store's default" partition) | [[#r7]] `--census dangling-link` requires `--default-partition`, printed in the header |
| r6 b-1 row of round 6 ("no change here") | superseded by the b-1 / d9av row above |

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: derives-from -> [[plan-review-2026-10-14#t12-approvals]]

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan16-22-spec-rereview-r6-0e77da3]] where it touches 16.6 (verdict for plan-16:
APPROVABLE; only m-3's census name and m-6's line numbers reach this file). Later rows win.

| finding / decision | answered in |
|---|---|
| r6 m-3 (22.1a AC-8b has no census procedure) | [[#r7]] "The dangling-row census is named" (`--census dangling-link`, `--facts` required, `rmxd.log` read in place, no `Store`); [[#files-to-modify]] |
| r6 m-6 (unpinned line numbers ~300 lines off) | [[#r1d]], AC-9b and [[#files-to-modify]] cite `rebuild_index_from_log`, `_apply_event_body`, `dump_catalog_to_log`, `_compact_factslog_if_needed` by symbol; [[#r1e]] cites `purge_entity`, `purge_path`, `vacuum` by symbol; [[#why]]'s `daemon.py:4295` stays, pinned to `b1c4324` |
| r6 b-1 / d9aq (no id-keyed op) | no change here: 22.2's dangling removal adds no op, so [[#r1d]]'s one-pass list is unchanged ([[task-22.2-repair-then-remove#r3]]) |

rel: amends -> [[bsd-plan16-22-spec-rereview-r6-0e77da3]]

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan16-22-spec-rereview-r4-878647c]] where it touches 16.6, and d9ab
([[plan-review-2026-10-14#t11-approvals]]). Later rows win over round 3.

| finding / decision | answered in |
|---|---|
| r4 b-2 / d9ab companion 1 (compaction drops the sidecar's events; AC-9 never compacts) | [[#r1d]] "The compactor keeps the sidecar"; AC-9b + mutation; [[#files-to-modify]] `dump_catalog_to_log` |
| r4 b-1 (16.6 R4 / AC-4 vs 22.1 step 2) | unchanged here; [[task-22.1-audit-classes#r1]] now agrees with R4 (`changed` → `ok`) |
| r4 s-3 (`HOME` redirect empties the deny set and `home_base`) | [[#r7]] step 4 (real home from `pwd`, deny set before import, empty set is an error), step 5 (explicit classifier inputs); AC-5c two clauses + mutations |
| r4 m-1 (probe outside "the ONE procedure") | [[#r7]] `--census probe-reproduction` |
| r4 m-2 (compaction and the churn bound) | [[#r7]] step 4 header: log birth time and last compaction line; 22.1a AC-5b labels `C` |
| r4 m-3 (`UTF-8` locale; two shapes, one hash) | [[#r2]] `setlocale` probe in a child process; [[#r1]] `rules_sha` one serialization; AC-3i clauses |
| r4 m-4 (rg `-E`, `-j`) | [[#r2-argv]] rg keeps `-E/--encoding`, drops `-j/--threads`; AC-3b rows; [[task-16.1-argv-faithful-learner#r1-clusters]] |
| r4 m-5 (AC-11 will start failing) | AC-11 scope note; 22.6 rewrites its test |
| r3 s-6 (partial: census procedure) | closed by the s-3 row |

rel: amends -> [[bsd-plan16-22-spec-rereview-r4-878647c]]
rel: derives-from -> [[plan-review-2026-10-14#t11-approvals]]

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan16-22-spec-rereview-r3-6091648]] and d9k/d9o
([[plan-review-2026-10-14#t9-approvals]]). Later rows win over round 2 and revision 6.

| finding / decision | answered in |
|---|---|
| r3 s-1 (re-run ignores the locale; launchd daemons run in C) | R1 `locale` column, part of `rules_sha`; R2 `matching_lines` env pinned to the recorded locale, scrubbed of `GREP_*`; `locale-missing` reason; AC-3i + mutation |
| r3 s-2 (clusters; value arity in the token filter) | R2 [[#r2-argv]] arity walk (a value flag consumes its value); `match_argv` holds 16.1's EXPANDED tokens ([[task-16.1-argv-faithful-learner#r1-clusters]]); an unclassifiable token is `no-rules`; AC-3b arity rows + mutation |
| r3 s-3 ("rare by construction" is false) | R2 [[#r2-permissive]] sentence replaced by the measured counts (1,511 of 31,608 distinct rows here, 4.8%; 69 of 495 global `query/*` concepts) |
| r3 s-4 (the union AC cannot fail) | AC-3h: readings that DISAGREE (`-F` vs `-E`), reading order stated (ascending `rules_sha`), two sets so each order is exercised; mutations "first reading only" and "last reading only" |
| r3 s-5 → d9o (purges orphan the sidecar; who deletes it) | R1e [[#r1e]]: no path deletes a sidecar row silently; until 22.6 lands, orphaned sidecar rows are KEPT and counted; 22.6 owns the d9o paths; AC-11 |
| r3 s-6 (census "through a sandbox daemon" has no procedure) | R7 [[#r7]]: ONE census procedure (copy + `duckdb.connect(read_only=True)` + the production function; no `Daemon`, no `Store()`); R5 `backfill_selection`; AC-5b, AC-5c |
| r3 m-1 (one replay pass; AC-9's impossible state) | R1d one post-evidence pass over every row-level op in log order (the same list as [[task-22.2-repair-then-remove#r3]]); AC-9 seeds the evidence row at the new identity first |
| r3 m-2 (`--no-config`; `SidecarRow`/`Key`/`Verdict`; `no-rules` trigger; line splitting) | R2 contract block (types defined), rg drop list, `no-rules` triggers, `b"\n"` line split |
| r3 m-3 (`out-of-range` two predicates) | R2 `verify`: the per-row `out-of-range` verdict feeds R4's marks only; 22.1 labels leftover rows of its set rule ([[task-22.1-audit-classes#r1]]) |
| r3 m-6 (rg on PATH) | R1 `bin`: absolute PATH-resolved path recorded, never re-resolved; AC-3j + mutation |

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] (`#t9-fixes`).
Later rows win over the revision-6 table below.

| finding / decision | answered in |
|---|---|
| re-review b-1 (re-run calls matching rows stale: cutoffs, absolute-path `--exclude`, exit 2) / #t9-fixes "closes its three false-stale holes" | R2 [[#r2-argv]] (verify-time token filter), R2 exit-status bullet (`tool-error` → `unverifiable`); AC-3 d/e/f, AC-3b; mutations in AC-10 |
| re-review b-2 (sidecar has no `facts.log` form; rebuild erases it) / #t9-fixes "16.6 provenance gets a `facts.log` event" | R1d [[#r1d]] (`learned_provenance`, `learned_provenance_move`, both replay paths); R5 routes through it; AC-9 + two mutations |
| re-review b-3 (marks have no reader) | R4 [[#r4-reader]] (option (a): 22.1 reads them, [[task-22.1-audit-classes#r1-marks]]); [[#r4-lower-bound]] states the reading requirement |
| re-review b-4 (22.1's Python translation contradicts R2; R2 returns verdicts, not the line set) / #t9-fixes "22.1 calls 16.6's verifier, which returns the matching line set" | R2 [[#r2]] (the contract: `matching_lines`, `permissive_matching_lines`, `verify`, `hash_line`); AC-3 a/c; 22.1 [[task-22.1-audit-classes#r1-verify]] calls it |
| re-review s-3 (census ACs need live catalogs) / #t9-fixes "sandbox-safe catalog clones" | AC-5 split: 5a sandbox fixture, 5b operator census on a `cp` of `catalog.read.duckdb` (23.4 R1's procedure); [[#test-strategy]] |
| re-review s-5 (plan-22 repairs change the key columns) / #t9-fixes "22.2/22.5 update provenance keys" | R1 "Key-column updates belong to plan-22" + `move_learned_provenance`; R1d's move event |
| re-review m-1 (false dialect premise; dead `python` branch) | R1 `dialect` row (no `python`); R2 has no `python` branch; plan [[plan-16-invisible-grep-shim#open-after-revision]] item 3 closed |
| re-review m-4 (vocabulary drift; "22.1b"; `root` setter) | verdicts `stale-line`/`missing-file` (R2, R4, R1 `last_mark`); `UNVERIFIABLE_REASONS` is the one `unverifiable` definition; [[#split]] cites 22.1; R1 `root` row names 22.5's import |
| re-review m-5 (which reading defines the set) | R2 `verify` bullet: the union over readings, `none` read permissively; AC-3h |
| re-review m-6 (AC-6 count fails on correct code) | AC-6 counts DISTINCT evidence identities |
| r5 b-r5-1 (partial at the re-review) | closed by b-1, b-2, b-4 above |

## Revision 6 changelog {#revision-6}

Answers spec review r5 ([[bsd-plan16-spec-review-r5-cd7c923]]), the plan-22 review items that name
16.6, and the 2026-10-14 decision log ([[plan-review-2026-10-14]]) with its close-out.

| finding / decision | answered in |
|---|---|
| d6d (16.6 split by dependency; settles plan-16 dn-2 and plan-22 #b-7) | header (wave 1, after 23.1, no 16.1 dependency); [[#split]]; the learn-time write is 16.1 R10 |
| #t8-amendments d1c/d6d (16.6's leftover dependency on 16.1 removed; the Wave 1 slice is R4/R5 + sidecar) | header; [[#split]]; `rel:` edge to 16.1 is `related-to`, not `depends-on` |
| decision-log review #b-3 (16.6 header inverts Wave 1 → Wave 2) | header; plan [[plan-16-invisible-grep-shim#waves]] |
| plan-22 #b-7 / r5 s-r5-5 (16.6 has no wave; "(draft)" blocks `approved`) | header; "(draft)" removed from [[#requirements]] and [[#acceptance]]; R1b closes the legacy-writer window |
| r5 b-r5-1 / plan-22 #b-2 (provenance cannot replay the caller's rules; Python `re` is the only verifier) | R1 [[#r1]] (`tool`, `bin`, `dialect`, `match_argv`, `line_hash`); R2 [[#r2]] (the verifier re-runs the recorded tool, never Python `re` for those rows); AC-3 |
| #t6-fixes "16.6 records a line hash" / plan-22 #b-1 (no hash recorded) | R1 `line_hash`; R3 [[#r3]] |
| #t6-fixes "provenance carries tool + dialect + line hash" | R1 |
| #t6-fixes / r5 s-r5-3 (read-time marks record reader-rule drops as staleness) | R4 [[#r4]] (a reader-rule drop with an unchanged hash writes nothing); AC-4 + mutation |
| #t6-fixes / r5 s-r5-4 / plan-22 #s-6 (sidecar keyed on `evidence_rowid`, rewritten by `replica_merge`'s `SELECT DISTINCT`) | R1 key = `(entity_id, linkage_id, concept_id, file, line, rules_sha)`; R1c [[#r1c]] merge step; AC-2 + mutation |
| decision-log review #m-3 (`stale_seen` rides a coalescing, overflow-dropping queue) | R4 "lower bound" paragraph [[#r4-lower-bound]]; AC-8 |
| decision-log review #s-1 (only the sidecar got a `replica_merge` fix) | R1c covers the sidecar; the other tables are plan-23's (not edited here) |
| d1a/d1b (tests sandboxed by task 23.0) | [[#test-strategy]] |
| plan-22 #m-3 (plan line ~138 said 16.6 prunes) | plan [[plan-16-invisible-grep-shim#tasks]] row 16.6 (closed in r5; re-checked) |

## Revision 5 changelog (history) {#revision-5}

Applied the plan review's C1/C2/C3 ([[plan-review-2026-10-07#contradictions]]; user 2026-10-07:
"apply all the consolidations, don't delete moves repair them if possible"). Nothing was deleted:
every moved requirement and decision is kept below, marked with where it now lives.

| item | answered in |
|---|---|
| C1 the audit/prune engine moves to ONE audited removal plan | [[#split]]; plan-22 22.1/22.2 |
| C2 bug-086 has two vehicles | [[#split]]: plan-22 task 22.3 is the only one; R5 leaves global roots NULL for it |
| C3 `moved` rows deleted by default | [[#d-c]] amended (repair, never delete); [[#d-c-review]] closed by the user's answer |
| plan-16 header + table row (m-r4-1 family) | plan [[plan-16-invisible-grep-shim#tasks]] row 16.6 re-scoped |

## What stays in this task, what moved {#split}

d6d (user, 2026-10-14) splits 16.6 by DEPENDENCY, not by plan. Everything that needs no learner
change runs in Wave 1 after plan-23's 23.1; the learn-time provenance write moves into task 16.1
(Wave 2). plan-22's provenance-free classes (22.1a) and 22.3 do not wait for either.

| item | owner | where |
|---|---|---|
| R1 sidecar table `learned_evidence`, its key and its writer API | this task (Wave 1) | [[#r1]] |
| R1b legacy-writer rows until 16.1 lands | this task (Wave 1) | [[#r1b]] |
| R1c `replica_merge` carries the sidecar | RETIRED (d9ay): writer rotation is dropped and `replica_merge` is broken (bug-113) | [[#r1c]] |
| R2 the dialect-faithful verifier | this task (Wave 1) | [[#r2]] |
| R4 read-time `last_verified_at` / `stale_seen` marks, queued | this task (Wave 1), through plan-23's queue | [[#r4]] |
| R5 provenance backfill (project roots; global roots NULL) | this task (Wave 1) | [[#r5]] |
| R6 loud counting on every leg | this task (Wave 1) | [[#r6]] |
| the LEARN-TIME provenance write (tool, dialect, match tokens, line hash, `spawned_by`) | task 16.1 R10 (Wave 2), d6d | [[task-16.1-argv-faithful-learner#r10]] |
| the audit (`removal_audit`) and its classes (`ok`, `moved`, `ambiguous`, `stale-line`, `out-of-range`, `missing-file`, `duplicate`, `orphan-root`, `orphan-alias`, `empty-learned`) | plan-22 (22.1a provenance-free; 22.1 the flag-sensitive rest, which calls R2) | [[task-22.1-audit-classes]], [[task-22.1a-provenance-free-classes]] |
| repair then removal; manifest; row-level events; ablation gate | plan-22 | [[task-22.2-repair-then-remove]] |
| bug-086's global repair and the cross-store move | plan-22 | [[task-22.3-bug-086-global-repair]], [[task-22.5-cross-store-move]] |

rel: realizes -> [[plan-review-2026-10-07#contradictions]]
rel: realizes -> [[plan-review-2026-10-14#t6]]

## Why {#why}

Every grep-learned row is written by ONE writer, `_learn_grep_hits` (`daemon.py:4295` at
`b1c4324`). It is reached from three feeders:

- the RPC op `learn_from_grep` (`_op_learn_from_grep`);
- the learn-queue drain (`daemon.py:2135`);
- the daemon's context backstop (`daemon.py:4795-4806`), whose hits come from `rg -nH -i -F`
  (`context.py:915`).

Each feeder writes:

- a `query/<pattern>` concept, `protected=True`;
- an entity for each hit file, `protected=True`;
- a `mentions` link;
- one `linkage_evidence(file, line, detail="learned from grep '<pat>'")` row per hit (the
  pattern is `repr`-quoted). {#why-writes}

Nothing ever removes these rows, and nothing can tell they have gone stale:

1. **No provenance.** `linkage_evidence` is `(entity_id, linkage_id, concept_id, file, line,
   span_end, detail)` with no primary key (`duckdb_catalog.py:162`). It has no learned-at, source,
   root, tool, dialect or line-hash column. A learned file entity shares `UNIQUE(partition, kind,
   name)` with the ingester's entity, so learning a file the ingester owns PROTECTS the ingested
   row. Learned rows cannot be selected apart from ingested ones.
2. **Read-time verification sees staleness and forgets it.** `verify_evidence_rows`
   (`store.py:816`, called from `grep_evidence` at `store.py:3257`) drops a row whose file is
   unreadable, whose line is out of range, or whose line fails the READER's pattern, and counts it
   (`unreadable`, `dropped`). It writes nothing back, so the same dead row is re-read and
   re-dropped on every grep, forever. It also cannot tell "the line changed" from "the reader asked
   a different question" (s-r5-3).
3. **The only verifier speaks Python `re`.** `evidence_line_matches` (`store.py:759`) reads BRE
   `zzz\|alp` and `\(foo\)x` differently from BSD grep (probed in r5: grep matches `alpha` and
   `foox`; Python does not). A row taught correctly by a BRE grep re-verifies as stale under it
   (b-r5-1).
4. **`protected` blocks every reaper; `add_evidence` is an unconditional INSERT.** 16.1 adds
   store-side idempotence for NEW rows; the existing duplicates stay for plan-22. {#why-gaps}

Scale today: the global store holds 1,087 relative learned entities with 5,159 evidence rows, of
which about 700 read as unreadable on every global grep (bug-086). {#why-scale}

## Requirements {#requirements}

**R1. The sidecar `learned_evidence` (schema, key, writer API).** {#r1}

One row per (evidence row, reading). Columns:

| column | meaning |
|---|---|
| `entity_id`, `linkage_id`, `concept_id`, `file`, `line` | the evidence row's identity, the same five values as its `linkage_evidence` row (plan-22 #s-6's row identity) |
| `rules_sha` | sha256 hex of the canonical JSON `[tool, dialect, match_argv, locale]` (r3 s-1); the literal `none` when the row has no recorded rules (backfill, legacy writer). ONE serialization (r4 m-3): `json.dumps([tool, dialect, list(match_argv), locale], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`, where `locale` is the JSON object of exactly the three names `LANG`, `LC_ALL`, `LC_CTYPE` (a value or `null` each) for grep and `null` for rg; `Rules.locale`'s tuple is converted to that object before hashing, so the sha recomputed from the stored column equals the stored key |
| `origin` | `learner` (16.1 R10), `context-backstop` (16.1 R10), `legacy-writer` (R1b), `backfill` (R5) |
| `source` | `grep-learn` |
| `learned_at` | epoch seconds; NULL for `backfill` (unknown, never invented) |
| `root` | the absolute PROJECT root the row was learned under (the store root's parent); NULL in the global store. The only writer that sets it on a global-origin row is plan-22's 22.5 `learned_import`, which sets it to the TARGET project root as it copies the row (m-4) |
| `pattern` | the pattern as the tool received it |
| `tool`, `bin` | `grep` / `rg` and the absolute binary that produced the hit; NULL when unknown. `bin` is the PATH-resolved absolute path the learner exec'd (16.1 R1 `--bin`), recorded as is (not `realpath`'d, so a Homebrew upgrade that keeps the `bin` symlink keeps the row verifiable) and NEVER re-resolved through `PATH` at verify time (r3 m-6: the launchd `PATH` puts `/opt/local/bin` first, so re-resolving could pick another `rg`) |
| `locale` | grep rows: the learner's `LC_ALL`, `LC_CTYPE` and `LANG` as a JSON object of the three names (a value or `null` each), read from the learner's environment, which is the caller's (r3 s-1: BSD grep's `.`, `-i`, `-w` and POSIX classes follow `LC_CTYPE`; probed, `a.b` on `a—b`, `-i café` on `CAFÉ` and `na[[:alpha:]]ve` on `naïve` match under `en_US.UTF-8` and miss under C). rg rows: `null` (rg matched in both locales, probed). Part of `rules_sha`. NULL for `rules_sha=none` rows |
| `dialect` | `bre`, `ere`, `fixed` (grep), `rust`, `pcre2` (rg), `mixed` when the kept tokens name more than one; NULL when unknown. These are exactly the values 16.1 R10 writes; there is no `python` value (m-1). Informational: R2 always re-runs `tool` itself |
| `match_argv` | the kept MATCH-class and CUTOFF-class tokens verbatim, in order, as 16.1 R1's table kept them (JSON list). Recorded whole; R2 FILTERS it at verify time ([[#r2-argv]]) |
| `line_hash` | `learned_verify.hash_line(raw)` of the matched line's bytes as the tool printed them, without the line terminator ([[#r3]]); NULL when not recorded |
| `spawned_by` | `shim`, `grep-tool-hook`, `rmx-grep`, `context-backstop`; NULL for `backfill`/`legacy-writer` |
| `last_verified_at`, `stale_seen`, `last_mark` | R4's marks; `last_mark` in `missing-file`, `out-of-range`, `stale-line` (plan-22's class names, m-4) |

- **Primary key `(entity_id, linkage_id, concept_id, file, line, rules_sha)`.** It never uses
  DuckDB's `rowid`, which `replica_merge` rewrites (s-r5-4). Two readings of one row (`grep -i foo`
  and `grep foo` both teach `query/foo`) are two sidecar rows; R2 calls the row `ok` when ANY of
  its readings passes.
- **Writer API:** `Store.add_learned_provenance(rows, log=True)` inserts with `ON CONFLICT DO NOTHING` on the
  key, inside the caller's transaction, and logs one `learned_provenance` event per row it actually
  inserted ([[#r1d]]). `log=False` is the one non-logging call: its only caller is 22.2 R4's
  restore of a row re-inserted DANGLING, whose sidecar rows are catalog-only like the row
  ([[task-22.2-repair-then-remove#r4-reinsert-sidecar]]; d9cj). It is the only INSERT path of the table (R1c's merge step is RETIRED,
  d9ay); R4's drain updates only the mark columns. 16.1 R10 calls it from `_learn_grep_hits`; R1b and R5 call it
  here.
- **Key-column updates belong to plan-22 (s-5).** Every plan-22 primitive that changes a column of
  this key moves the sidecar row in the SAME transaction and logs it: 22.2's `repoint_evidence`
  (`line`), `rename_entity` merge (`entity_id`), `remove_evidence` (delete / collapse), and 22.5's
  `learned_import` (`entity_id`, `file`, `root` in the target store). The owner is named in
  [[task-22.2-repair-then-remove#r2]] and [[task-22.5-cross-store-move#r2]]; this task supplies the
  table, the key and the `Store.move_learned_provenance(old_identity, new_identity)` helper they
  call (an UPDATE of the key columns on every reading of that identity, plus one
  `learned_provenance_move` event). When the new key already exists, the two rows collapse:
  earlier `learned_at` wins the non-mark columns (NULLs last), `last_verified_at` = max,
  `stale_seen` = max, `last_mark` from the row with the later `last_verified_at` (the rule R1c
  stated for the merge, kept here when R1c was retired, d9ay).
- The DDL lives in `duckdb_catalog.py` beside `linkage_evidence`. `linkage_evidence` is untouched,
  so the migration is additive and reversible (d-a).

**R1d. The sidecar is replayable from `facts.log` (b-2).** {#r1d}
`Store.rebuild_index_from_log` unlinks the catalog and replays `facts.log` only; a table
with no event is wiped by every `rmx rebuild-index` and every `rebuild_index` daemon op. So:
- **Event `learned_provenance`**, keyed by NAME, never by id: `{linkage, c_kind, c, e_kind, e,
  file, line, rules_sha, origin, source, learned_at, root, pattern, tool, bin, dialect,
  match_argv, line_hash, spawned_by}`, built by `edge_records.row_event` ([[#r1d-one-format]]; r8
  b-1, d9bl). `c_kind` is the concept end's catalog kind, read at write time; for the learner's
  rows it is always `concept`, because `_learn_grep_hits` creates its `query/*` concept with
  `add_concept`. Written by `add_learned_provenance` through `_log_events` (one append per call,
  the same `_log_enabled()` switch every event has), after the evidence events of the same call.
- **Event `learned_provenance_move`** `{linkage, c_kind, c, e_kind, e, file, line, to: {e_kind, e,
  file, line, root}}` from `move_learned_provenance` (plan-22's repairs and import), built by the
  same `row_event`. The concept end does not move, so `to` carries no `c_kind`.
- **The rebuild applies them; it is the ONE replay path (d9bu).** `Store.rebuild_index_from_log`
  today collects `evidence` events in its pass 2, resolves their concept kind in Pass 2b
  (bug-117) and applies them in pass 3, after entities, protections and links. The two new ops
  join the `evidence` appends in the ONE row pass below, in timestamp order (d9av), resolving
  names to ids at apply time through the one resolver of [[#r1d-one-format]]. An event whose
  evidence row does not exist at apply time is counted `unresolved_provenance` and printed,
  never dropped silently. The incremental path (`apply_log_delta` → `_apply_one_event` →
  `_apply_event_body`) has no caller and is DELETED by this slice ([[#r1f]]); no op gets a
  branch there.
  - **One resolver, so legacy events resolve one way (r8 m-3, closed by d9bu).** Round 8 stated
    that a LEGACY event (an `evidence` append written before 0.78.3) resolved over the LOGGED
    kinds on a rebuild but over the LIVE kinds in `_replay_concept`. With `_replay_concept`
    deleted ([[#r1f]]), the only resolver left is `edge_records.resolve_c_kind` over Pass 2b's
    `kinds_by_name` (every kind LOGGED for the name in the partition, tombstoned keys included).
    bug-120 closes by removal of the second resolver.
- **The compactor keeps the sidecar (r4 b-2; d9ab companion 1).** The daemon's periodic
  `facts.log` compaction (`Daemon._compact_factslog_if_needed`, every 1,800 s
  once the log passes 256 MiB; this repo's log compacted three times on 2026-10-14) REPLACES the
  log with `Store.dump_catalog_to_log`'s snapshot, which today emits no
  sidecar event. So `dump_catalog_to_log` emits, per partition, one `learned_provenance` event per
  `learned_evidence` row (every non-mark column, keyed by name as above, built by `row_event`
  with the concept's catalog kind as `c_kind`, exactly as the dump's own `evidence` events carry
  it since 0.78.3), AFTER that partition's
  `evidence` events and with the `ts` of its own evidence row's dumped event (the dump's
  synthetic `GREATEST(c.updated_at, e.updated_at)`, re-read at `23ad703`), so in the timestamp-ordered
  row pass it ties with that append and follows it by log position (d9av). The snapshot holds current state,
  so no `learned_provenance_move` is needed: the dumped event already names the row's current
  key. **Only the sidecar rows of dumped evidence rows are emitted (round 14, stated; d9ch):**
  the dump's `evidence` query joins both ends to live entities, and a sidecar event is keyed by
  name and takes its evidence row's dumped `ts`, so a sidecar row whose evidence row has a dead
  end (an orphan [[#r1e]] keeps in place after a purge) has neither a name for that end nor a
  dumped append, and is not emitted; the dump's result counts it `provenance_not_dumped`, so the
  skip is never silent. A restore that later re-attaches such a row re-logs its
  `learned_provenance` event itself ([[task-22.2-repair-then-remove#r4-relink]]). Without this, the first `rebuild_index_from_log` after a compaction rebuilds an EMPTY
  sidecar, and every learner row loses its tool, argv, locale and hash for good.
- R4's marks (`last_verified_at`, `stale_seen`, `last_mark`) have NO event: they are derived,
  re-earned by later reads, and a rebuild resets them to NULL/0 (stated, counted in the rebuild's
  result as `marks_reset`).
- plan-22's `evidence_remove` replay removes the matching sidecar rows by the same identity
  ([[task-22.2-repair-then-remove#r3]]).
- **ONE row pass, appends and row ops together, in TIMESTAMP order (d9av; r7 b-1; replaces round
  3's "after the `evidence` appends, in log order").** The rebuild pass applies the `evidence`
  appends and every row-level op in ONE pass: `evidence`,
  `learned_provenance`, `learned_provenance_move` (this task), `evidence_remove`,
  `evidence_repoint`, `entity_rename` ([[task-22.2-repair-then-remove#r3]]) and
  `evidence_orphan_drop` ([[task-22.6-removal-entry-points#r5]]), ordered by `ts` with ties broken
  by log position. A row op at `T` therefore acts only on the copies appended at or before `T`:
  an `evidence_remove` at `T1` followed by an identical re-learned row at `T2` (a branch switch
  re-creates the file) leaves the `T2` row and its `learned_provenance` standing after a rebuild,
  as they stand live. Round 3's pass, which ran every row op after ALL appends, deleted the `T2`
  row on a rebuild and counted its provenance `unresolved_provenance` (r7 b-1).
  - *The order, concretely (re-read at `23ad703`, 0.78.3; r8 m-1, m-5).* `rebuild_index_from_log`
    already sorts every event by `ts` with a stable sort (`events.sort(key=lambda e:
    e.get("ts", 0))`, `store.py:7941`), so equal `ts` keep their log order. Pass 2 collects the
    `evidence` appends into `evidence_events`; **Pass 2b (bug-117) stays**: it resolves each
    legacy append's `c_kind` by the one legacy rule into `resolved_evidence`, counting
    `evidence_unresolved`. The row pass replaces only pass 3's per-partition `evidence_events`
    loop (the one that counts `evidence_skipped_dead`): per partition, ONE function,
    `Store._row_pass_events(events, partition)`, takes the appends AFTER Pass 2b's resolution
    (every item carries `c_kind`) plus the row ops, returns them in the sorted order, and pass 3
    applies them in that order (AC-9c), still counting `evidence_skipped_dead` for an append whose
    end does not resolve. There is no second ordering to keep in step: the incremental path is
    deleted ([[#r1f]], d9bu; writer rotation, its only reason, was dropped by d9ao). Cited by
    symbol; the line numbers are `23ad703`'s.
  - **One spelling, one key, one resolver, one counter (d9bl; r8 b-1).** {#r1d-one-format} Every
    row-level op plans 16 and 22 add is the same shape (an edge's two ends by name, plus a row
    identity), so it is built, keyed, resolved and counted by ONE function each, which this
    slice adds and plan-22 extends (user, 2026-10-15: converge repeated shapes into one
    function):
    - *Spelling.* `edge_records.ROW_OPS` (a frozenset, beside `EDGE_OPS`) and
      `edge_records.row_event(op, linkage, c_kind, c, e_kind, e, **extra) -> dict`, which
      returns `{"op": op, **edge_fields(linkage, c_kind, c, e_kind, e, **extra)}` and RAISES on
      an `op` not in `ROW_OPS` and on an empty `c_kind` (a row op is never written without
      `c_kind`). `edge_event` is not used for them: it accepts only `EDGE_OPS`. This slice puts
      `learned_provenance` and `learned_provenance_move` in `ROW_OPS`; 22.2 adds
      `evidence_remove` and `evidence_repoint`; 22.6 adds `evidence_orphan_drop`, which carries the
      matched append's entity end `(e_kind, e)` like every other row op (d9cc, r11 s-1: the
      append that wrote the copy names its entity by name, so no row op has a null entity end
      and `row_event` raises on `e_kind` or `e` None for every op). `entity_rename{kind, from, to, merged}` names no edge and stays
      outside `ROW_OPS`. A name-keyed `unlink` (22.2 R9) is an `EDGE_OPS` event, built by
      `edge_event("unlink", …)` with a non-empty `c_kind`.
    - *Key.* `edge_records.row_key(ev) -> (linkage, c_kind, c, e_kind, e, file, line)`, the ONE
      identity the row pass matches an op against the appends with, and the identity
      `add_learned_provenance` / `move_learned_provenance` name. An op that also matches on
      `detail` (`evidence_remove`, `evidence_orphan_drop`) compares the full `row_key` plus
      `detail` (d9cc: a drop never touches another entity's copy on the same key). The rebuild's link LWW key
      stays `(partition, linkage, c_kind, c, e_kind, e)`, Pass 2's, which is `row_key`'s first
      five fields.
    - *Resolver.* Rebuild: Pass 2b's per-event rule is extracted into ONE function,
      `edge_records.resolve_c_kind(c_kind, c, partition, kinds_by_name) -> str | None`
      (module-level, so 22.1a's census copy needs no `Store`): `c_kind` when present, else
      `resolve_legacy_kind(kinds_by_name.get((partition, c), ()))`, the kinds LOGGED for the name
      in that partition, tombstoned keys included. Pass 2b's link loop, its evidence loop, and the row pass for any
      row op that reaches it without `c_kind` (a hand-edited log) call it; the row pass then
      resolves ends with `name_to_id[(c_kind, c)]` and `name_to_id[(e_kind, e)]`, never a
      literal kind. There is no incremental resolver: `_replay_concept` is deleted with the
      path that called it ([[#r1f]], d9bu). Write side: plan-22's live primitives pick the
      kind(s) a row op names through ONE method, 22.2's `Store._row_op_c_kinds`
      ([[task-22.2-repair-then-remove#r3]]), which reads the constant
      `edge_records.LEGACY_PREFERRED_KIND` and does not call the legacy rule (r9 m-1); 22.6's
      `vacuum` keys each orphan drop on the orphan's own appends from its one log scan and
      resolves a legacy append's kind through `edge_records.resolve_c_kind` over the logged
      kinds it collects, Pass 2b's map ([[task-22.6-removal-entry-points#r5-own-appends]], d9bz;
      r10 s-1); this slice's learner rows are always `concept`.
    - *Counter.* Every row-pass skip of the rebuild is counted through ONE helper,
      `Store._row_skip(counts, op, reason)`, into one `row_skips: {op: {reason: n}}` dict
      (`reason` in `skipped_dead`, `unresolved`, `no_row`, `skipped_live`) that the rebuild
      returns beside bug-117's `links_*` / `evidence_*` counters. The rebuild is the only
      replay path (d9bu), so `row_skips` has one writer. The names the ACs print are views of it:
      `unresolved_provenance` = the `no_row` count of `learned_provenance` plus
      `learned_provenance_move`; `orphan_drop_skipped_live` = `evidence_orphan_drop`'s
      `skipped_live` (22.6 R5).
    - AC-9d is the mechanical check that no site bypasses these four.
  - Within one call, a primitive's sidecar event follows its evidence event (same `ts` from
    `_log_events`, or a later one), so the provenance still follows its row.
  - Never one pass per op family: a re-point replayed before its row's `learned_provenance` would
    leave that event no evidence row at the recorded line (`unresolved_provenance`), and the
    provenance would be lost (r3 m-1).
  A row-level evidence op moves or removes only `linkage_evidence` rows on replay, except
  `evidence_remove`, which also removes the identity's sidecar rows; sidecar KEY moves replay only
  from their own `learned_provenance_move` events, which the live primitive appends AFTER its
  evidence event in the same call.

**R1e. Purges never drop a sidecar row silently (r3 s-5, d9o).** {#r1e}
Today `Store.purge_entity` and `Store.purge_path` delete learned file
entities whatever `protected` says and leave their `linkage_evidence` rows behind (no FK,
`duckdb_catalog.py:162`); `Store.vacuum` step 3 then deletes those rows with no event. The user classified each path (d9o,
[[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]), and
[[task-22.6-removal-entry-points]] owns every one of them. This task's part:
- None of `purge_entity`, `purge_path`, `_bulk_purge_ids` or `vacuum` deletes a
  `learned_evidence` row in this slice. A sidecar row whose five identity columns join no
  `linkage_evidence` row is KEPT and counted `orphaned_provenance` by `rmx learn status` (R6),
  whatever made it so; it is never read as a verdict.
- 22.6 replaces that interim: the sync edit paths keep learned rows (so no orphan arises there),
  and the deleted/ignored-file purge and `vacuum`'s orphan-evidence delete write a manifest that
  carries the sidecar rows of every identity they remove, with a `facts.log` event.

**R1f. The incremental replay path is deleted; the rebuild is the one replay path (d9bu; r9
s-2).** {#r1f}
`Store.apply_log_delta` is the only caller of `Store._apply_one_event`, which is the only caller
of `Store._apply_event_body`, which is the only caller of `Store._replay_concept`; nothing in
`src/` calls `apply_log_delta` (re-read at `428267f`: its one remaining mention is the
`REPLICA_REBUILD_DELTA_BYTES` comment, `daemon.py:516`, which describes the writer rotation d9ao
dropped). Plans 16 and 22 kept adding branches to it, each new code on an unreachable path kept
alive only by tests, and its separate resolver read LIVE kinds where the rebuild reads LOGGED
kinds (bug-120). This slice, in the same commit as [[#r1d]]:
- **Deletes** `apply_log_delta`, `_apply_one_event`, `_apply_event_body` and `_replay_concept`
  from `store.py` (`_replay_concept` is d9bu's chain one level down: its only caller is
  `_apply_event_body`, and its `resolve_legacy_kind` call is the third of the three today);
  `REPLICA_REBUILD_DELTA_BYTES` and its comment from `daemon.py` (read nowhere; its env var
  `RMX_REPLICA_REBUILD_DELTA_BYTES` goes with it).
- **Deletes their tests:** `test_the_incremental_replay_resolves_non_concept_rows` in
  `tests/test_bug117_rebuild_non_concept.py` (the rebuild tests of that file stay unchanged).
- **Rewrites the prose that names them:** the `add_memory` comment ("Replayed by
  `_apply_one_event` + `rebuild_index_from_log`", `store.py:2531`) names `rebuild_index_from_log`
  only; the module docstring of `tests/test_memory_content_log.py` ("`apply_log_delta` /
  `rebuild_index_from_log` reconstruct bodies") names the rebuild only.
- **Adds no replacement.** A future incremental replay is a new design under a new decision,
  built on the rebuild's resolver and row pass, not a revival of this one.
- **A check that can fail (AC-12):** a test scans `src/refmatrix/**/*.py`, `scripts/**/*.py`
  and `eval/**/*.py` (not `eval/datasets/`; 0 hits in `scripts/` and `eval/` today, and the
  benchmark path is the production path) as TEXT (so a comment or docstring counts), and
  `tests/**/*.py` as AST for the names `apply_log_delta`, `_apply_one_event`,
  `_apply_event_body`, `_replay_concept`, `REPLICA_REBUILD_DELTA_BYTES`. The AST scan matches
  `Name` and `Attribute` nodes AND string `Constant` nodes containing a name (so a docstring
  or a re-added prose mention counts; r10 m-3), and excludes the scan's own module, whose
  name list is itself string constants. Any hit fails with its `path:line`. bug-120 closes as "retired by d9bu" in the registry (the orchestrator's row).

**R1b. No new evidence row without a sidecar row, from the day this slice lands (s-r5-5).** {#r1b}
Between this Wave-1 slice and 16.1, today's writer keeps teaching. So `_learn_grep_hits`, in the
same transaction as its `add_evidence` calls, calls R5's backfill routine for exactly the rows it
just inserted: `origin=legacy-writer`, `rules_sha=none`, `learned_at` = now, `root` = the
`project_root` argument, `pattern`, everything else NULL. This is not 16.1 R10's provenance (no
tool, dialect or hash is known on today's path); 16.1 R10 replaces this call. `legacy-writer` rows
are verified like backfilled rows (R2's `none` reading, `permissive_matching_lines`, [[#r2-permissive]]).

**R1c. `replica_merge` carries the sidecar (s-r5-4): RETIRED (d9ay).** {#r1c}
**RETIRED (d9ay, round 7; as d9ao retired 23.1 R8).** Nothing in this task implements or tests
this requirement, and `replica_merge.py` is not in this task's file list. Reason: writer rotation
is dropped (`Daemon._refresh_replica_now`, `daemon.py:2814` at `77ac38f`, is a no-op and the
refresh thread is not started), so no live path produces two diverged slots for a merge to
reconcile; and `replica_merge` is broken on every real store (bug-113, open: its target is built
by `duckdb_catalog.init_catalog`, which lacks `entities.vectors_partition`, and it merges an
explicit table list), so an AC built on `init_catalog` slots would pass while the production
command fails. The sidecar's key collapse rule that R1c stated lives on in [[#r1]]
(`move_learned_provenance`). If a later plan revives slot merging, it adds `learned_evidence` to
`merge_slots`' table list with its own AC through `_op_replica_merge` on `Store.init()` slots.
Original text, kept as history:
- `learned_evidence` is added to the merge's table lists (`replica_merge.py:88`, `:433`, `:530` at
  `b1c4324`).
- A new step after step 9 (`replica_merge.py:335-355`) rebuilds it from both slots with the SAME
  remap step 9 applies to `linkage_evidence` (`COALESCE(canonical_id, entity_id)` and
  `COALESCE(canonical_id, concept_id)` through `remap_a`/`remap_b`), then collapses on the key:
  `last_verified_at` = max, `stale_seen` = max (both slots share history before the split, so a
  sum would double count), `last_mark` from the row with the later `last_verified_at`; every other
  column from the earlier `learned_at` (NULLs last).
- After the merge, every sidecar row joins exactly one `linkage_evidence` row on the five identity
  columns; a sidecar row that joins none is counted (`orphaned_provenance`) and printed by the merge,
  never silently dropped.

**R2. The verifier re-runs the row's own tool; it is THE verifier for learned rows (b-r5-1,
#t6-fixes, b-1, b-4).** {#r2}
Module `src/refmatrix/learned_verify.py` (new). Plan-22's 22.1 and 22.1a call these functions and
carry no matcher of their own ([[task-22.1-audit-classes#r1-verify]]). The cross-plan contract,
exact names and signatures:

```python
@dataclass(frozen=True)
class Rules:                       # one sidecar reading
    tool: str                      # "grep" | "rg"
    bin: str                       # absolute path as recorded; never re-resolved via PATH
    dialect: str | None            # informational only
    match_argv: tuple[str, ...]    # as recorded (R1): 16.1's EXPANDED tokens
    pattern: str | None
    locale: tuple[tuple[str, str | None], ...] | None   # (("LANG", v), ("LC_ALL", v),
                                                        #  ("LC_CTYPE", v)); None for rg
    @property
    def rules_sha(self) -> str: ...  # sha256 of canonical JSON [tool, dialect, match_argv, locale]

Key = tuple[int, int, int, str, int]   # (entity_id, linkage_id, concept_id, file, line):
                                       # the evidence row's five identity columns

@dataclass(frozen=True)
class SidecarRow:                  # one learned_evidence row, every R1 column
    key: Key
    rules_sha: str                 # "none" when the row has no recorded rules
    rules: Rules | None            # None iff rules_sha == "none"
    pattern: str | None
    line_hash: str | None
    root: str | None

@dataclass(frozen=True)
class Unverifiable:
    reason: str                    # one of UNVERIFIABLE_REASONS

@dataclass(frozen=True)
class Verdict:                     # ONE per evidence row (Key): the union over its readings
    kind: str                      # "ok" | "stale-line" | "missing-file" | "out-of-range"
                                   # | "unverifiable"
    reason: str | None             # set iff kind == "unverifiable" (first reason, R2 order)
    readings: tuple[str, ...]      # the rules_sha values consulted, ascending

UNVERIFIABLE_REASONS = ("no-rules", "bin-missing", "timeout", "tool-error",
                        "permissive-subset", "unreadable", "locale-missing")

def verify_argv(tool: str, match_argv: tuple[str, ...]) -> tuple[str, ...] | Unverifiable: ...
def matching_lines(file_abs: Path, rules: Rules, *, timeout_s: float = 5.0
                   ) -> frozenset[int] | Unverifiable: ...
def permissive_matching_lines(file_abs: Path, pattern: str
                              ) -> frozenset[int] | Unverifiable: ...
def split_lines(data: bytes) -> list[bytes]: ...     # the ONE line split (b"\n"), 1-based use
def hash_line(raw: bytes) -> str: ...
def verify(rows: Iterable[SidecarRow], project_root: Path
           ) -> dict[Key, Verdict]: ...      # built on matching_lines
```

- **`no-rules` (r3 m-2)** is returned for a recorded-rules reading that cannot be replayed: its
  `pattern` is NULL and its filtered tokens carry no `-e`/`--regexp`, or `verify_argv` meets a
  token it cannot classify (an unexpanded short cluster, an unknown token). It is never returned
  for a `none` reading, which goes to `permissive_matching_lines`.
- **Line numbering, one rule (r3 m-2).** `split_lines` splits the file's BYTES on `b"\n"` only;
  a final `b"\n"` ends the last line and does not open an empty one; nothing else (`\x0c`,
  `\r`, `\x0b`, `\x1c-\x1e`, `\u2028`) splits. That is grep's numbering (probed: a file
  `one\x0ctwo\nthree target` is line 2 to grep and line 3 to `str.splitlines()`).
  `permissive_matching_lines`, `verify`'s `out-of-range` test, R4's current-line hash and
  plan-22's hash pairing all number lines through it; `str.splitlines()` is never used on a
  learned row's file.

Verdicts (one vocabulary with plan-22, m-4): `ok`, `stale-line`, `missing-file`, `out-of-range`,
`unverifiable` (with its reason).

- **`matching_lines` (b-4): the current matching LINE SET of one file under one reading.** It
  re-runs `bin` with the FILTERED tokens ([[#r2-argv]]), then the canonical tail (`-nH --null` for
  grep; `-nH --null --no-heading --color never --no-config` for rg), then `-e <pattern>` (omitted
  when the filtered tokens already carry `-e`/`--regexp`, as the context backstop's rows do), then
  `-- <file_abs>`, with `stdin=/dev/null`, `cwd` = the file's directory and a per-file timeout. It
  runs with a CONSTRUCTED environment, never the caller's (r3 s-1): exactly the recorded
  `locale` names that have a value (unset ones absent), plus `PATH=/usr/bin:/bin`; nothing else is
  inherited, so `GREP_OPTIONS`, `GREP_COLOR`, `GREP_COLORS` and `RIPGREP_CONFIG_PATH` can never
  reach the re-run. When a recorded locale value is one the C library will not load, the reading
  is `Unverifiable("locale-missing")`, because BSD grep would fall back to C silently. The test is
  `setlocale`, not `locale -a` (r4 m-3: `LC_CTYPE=UTF-8`, common in macOS Terminal and ssh
  sessions, is absent from `locale -a`'s 288 names, yet `/usr/share/locale/UTF-8` loads and
  `env -i LC_CTYPE=UTF-8 /usr/bin/grep -c 'a.b'` counts `a—b`, where C does not): each distinct
  recorded value is probed once per process in a child `python -I -c` that calls
  `locale.setlocale(locale.LC_CTYPE, value)`; `locale.Error` → `locale-missing` (probed
  2026-10-14: `UTF-8`, `en_US.UTF-8`, `C`, `C.UTF-8` load; `xx_YY.UTF-8` raises).
  `bin` is exec'd by its recorded absolute path (r3 m-6). It
  parses `file\0LINE:` records and returns every LINE. Python `re` is never used for a row with
  rules. `verify` calls it once per `(file, rules_sha)` and shares the set across that file's rows;
  22.1 classifies `moved`/`grown`/`shrunk` on the same set.
- **Verify-time token filter (b-1.1, b-1.2).** {#r2-argv} `match_argv` is recorded whole (R1), but
  only PATTERN-SEMANTICS tokens are replayed; the file was already selected and a cutoff only
  hides lines. `verify_argv` walks the tokens LEFT TO RIGHT with 16.1 R1's `value` column: a
  value-taking flag (kept or dropped) consumes its value token WITH it (`['-e','-r']` keeps both;
  `['--exclude','x']`, rg `['-g','!x']` and `['-m','1']` drop both), so a value is never
  classified as a flag (r3 s-2; probed: `grep -e -r` matches the line `-r here`). `match_argv`
  holds 16.1's EXPANDED tokens ([[task-16.1-argv-faithful-learner#r1-clusters]]), so no cluster
  reaches the filter; one that does is `Unverifiable("no-rules")`, never guessed:
  - grep keeps: `-i --ignore-case -y -w --word-regexp -x --line-regexp -F --fixed-strings -E
    --extended-regexp -G --basic-regexp -e PAT --regexp=PAT --regexp PAT -a --text -U --binary
    --binary-files=V --binary-files V`;
  - rg keeps: `-i --ignore-case -s --case-sensitive -S --smart-case -w --word-regexp -x
    --line-regexp -F --fixed-strings -e PAT --regexp=PAT -P --pcre2 -U --multiline
    --multiline-dotall -a --text --binary -E ENC --encoding=ENC --encoding ENC` (r4 m-4: the
    encoding decides which bytes the pattern sees, so it is pattern semantics);
  - everything else in `match_argv` is dropped: the cutoffs (`-m N`, `--max-count`, and `-l`
    recorded as `-m 1`) and every file-selection token (`-r -R --recursive -S -O -p` for grep, where
    `-S` is a symlink flag, `--include --exclude --exclude-dir --include-dir -d -D --directories
    --devices -I --mmap`; rg `-g --glob --iglob -t --type -T --type-not -u -uu -uuu --hidden
    --no-ignore* -L --follow -d --max-depth -j --threads` (r4 m-4: `-j N` is a value flag that
    changes no match), and `--no-config`, which the canonical tail always
    carries (r3 m-2)). The filter is per tool (grep `-S` is dropped, rg `-S` is kept). Without it, `-l` re-runs as `-m 1` and hides a still-matching later line, and
    BSD grep matches `--exclude` against the WHOLE absolute operand, so an exclude that names a
    parent directory prints nothing (both probed in the re-review, `#ev-verifier`).
  - The filter is a pure function `verify_argv(tool, match_argv) -> tuple[str, ...]`, unit-tested
    against 16.1 R1's table so every keep:match and keep:cutoff token is assigned to exactly one
    side (no token unclassified).
- **Exit status (b-1.3).** rc 0 → the parsed set; rc 1 with no output → the empty set; any other rc
  (2 = parse error, an upgraded or swapped `bin` that now rejects the pattern), a signal, or rc 0/1
  with unparsable output → `Unverifiable("tool-error")`, KEPT and counted, never `stale-line`.
  `bin` missing or not executable → `Unverifiable("bin-missing")`; the timeout →
  `Unverifiable("timeout")`.
- **`permissive_matching_lines`: the reading for rows WITHOUT rules** (`rules_sha=none`:
  `backfill`, `legacy-writer`). {#r2-permissive} A line is in the set when ANY of: a
  case-insensitive substring match; `evidence_line_matches(text, pattern, regex=True,
  ignore_case=True)` (`store.py:759`); `identifier_variant_regex(pattern)` (`store.py:786`) matches.
  This is not a dialect translation: it is today's reader, widened. It names its subset (r5's
  second fix): a pattern containing a BRE/POSIX/rg construct Python reads differently (`\|`,
  `\(`, `\)`, `\{`, `\}`, `\<`, `\>`, `[[:`, `\p{`, `\P{`) gets
  `Unverifiable("permissive-subset")`, because Python `re` COMPILES `[[:digit:]]` and `\<foo\>` and
  silently mis-matches them (`#ev-verifier`). Such rows are NOT rare (r3 s-3): 1,511 of the 31,608
  distinct `(file, line, pattern)` rows taught in this repo's `facts.log` (4.8%) and 69 of the 495
  global `query/*` concepts hold a subset construct (the r3 re-review's read-only parse). Some
  predate 0.65.1; others are later, because `cli.py:6168-6178` refuses `\[|(){}]` in substring
  mode only, never POSIX classes or `-E` escapes. They stay `unverifiable` (kept, counted by
  reason) until a re-teach records rules for them; the subset check over-flags ERE `\(`, which is
  conservative (kept, never removed). Every consumer treats `permissive-subset` as a KEEP verdict,
  never as "not verified" (22.1a `orphan-root:unverifiable`).
- **`verify`** decides `missing-file` (unreadable or missing; `Unverifiable("unreadable")` when
  the stat itself errors) and `out-of-range` (line > the `split_lines` count) before any re-run.
  That per-row `out-of-range` verdict is what R4's marks record; plan-22's 22.1 does not classify
  with it, it labels the leftover rows of its own set rule (r3 m-3,
  [[task-22.1-audit-classes#r1]]). Then a row is
  `ok` when its line is in the UNION of its readings' sets, `stale-line` when every reading
  returned a set and the line is in none, and `unverifiable` (first reason) when it is in none and
  at least one reading was `Unverifiable` (m-5's union rule, also used by 22.1). Readings are
  consulted in ascending `rules_sha` order, and the union does not depend on that order (r3 s-4);
  the order fixes only which `Unverifiable` reason is reported first. A `none` reading
  goes through `permissive_matching_lines`; a row whose only reading is `none` is therefore decided
  here too, not left to plan-22.
- The verifier is subprocess-bound, so it runs in R4's drain pre-step and in plan-22's audit,
  NEVER on the read path.

**R3. The line hash (#t6-fixes, plan-22 #b-1).** {#r3}
`line_hash` = `learned_verify.hash_line(raw)` = sha256 hex of the line's bytes without the line
terminator. ONE function: 16.1 R10 calls it on the bytes the tool printed at learn time, R4 on the
current line, and plan-22's 22.1 on the lines of `matching_lines`'s set when it pairs a hashed
`moved` set. Here it serves two readers: R4 compares it to the current line to tell `stale-line`
candidates from a reader-rule drop, and plan-22's per-`(concept, file)`-set repair (#t6-fixes
`#b-1`) may use it as an optional extra on rows that have it. A backfilled or legacy row has
`line_hash` NULL; nothing computes one from the current file (that would certify a possibly stale
line as current).

**R4. Read-time marks: staleness only, never the reader's own filtering (s-r5-3, d-b).** {#r4}
- `verify_evidence_rows`'s stats split today's `dropped` into `out_of_range` and `reader_rule`
  (the line was read and fails the READER's pattern, case or regex flag), and add `missing_file`
  (= today's `unreadable`). The existing keys stay for their readers: `unreadable` unchanged,
  `dropped` = `out_of_range` + `reader_rule`.
- For each LEARNED row the read touches (a sidecar join on the five identity columns), the read
  path enqueues at most one candidate, through plan-23's durable queue (no lock, no inline write):
  - kept by the reader, and `line_hash` equal or NULL → `seen`;
  - `missing_file` → `missing-file`; `out_of_range` → `out-of-range`;
  - current line hash ≠ `line_hash` (kept OR dropped by the reader) → `changed`;
  - **a `reader_rule` drop whose line hash equals `line_hash`, or whose `line_hash` is NULL,
    enqueues NOTHING.** The row is healthy; the reader asked a different question (16.1 R8:
    `-i`-taught rows are dropped for a case-sensitive `rmx grep` by design).
- **The drain** runs in plan-23's bounded `bind(partition_name)` drain (23.1). A pre-step OUTSIDE the lock
  re-checks each candidate: `missing-file`/`out-of-range` are re-stat'ed (a transient read error
  does not mark); `changed` candidates go through R2's `verify` under the row's OWN readings. Then,
  inside the batch: `seen` and a `changed` that R2 calls `ok` set `last_verified_at`; a
  re-confirmed `missing-file`, `out-of-range`, or a `changed` that R2 calls `stale-line` adds 1 to
  `stale_seen` and sets `last_mark` to that verdict. `unverifiable` writes nothing and is counted
  by reason.
- Nothing is deleted. `stale_seen` is never a removal trigger here.
- **The marks have a named reader (b-3, option (a)).** {#r4-reader} Plan-22's 22.1 READS them
  ([[task-22.1-audit-classes#r1-marks]]): it orders its re-verification so rows with
  `stale_seen > 0` or a non-NULL `last_mark` are verified first, lists each marked row with its
  `last_mark` and `stale_seen` in the plan manifest, and reports the `last_verified_at` age per
  class. A mark never decides a class: 22.1 re-verifies every row through R2 regardless, and the
  class comes from that run. `rmx learn status` prints the aggregate counts.
- **`stale_seen` is a LOWER BOUND (decision-log review #m-3).** {#r4-lower-bound} plan-23's queue
  coalesces by key and drops on overflow (with a counted overflow). A coalesced or dropped mark
  undercounts `stale_seen`, which can only DELAY a plan-22 removal, never cause one. The overflow
  count is printed by `rmx learn status` as `marks dropped (overflow): N`. The reading requirement
  on every consumer: `stale_seen` is used for ORDERING and REPORTING only, printed with the label
  "at least", never compared to a threshold, never an exact count; 22.1 states the same
  ([[task-22.1-audit-classes#r1-marks]]).

**R5. Provenance backfill (d6d Wave 1).** {#r5}
One idempotent routine, `backfill_learned_provenance(store, rows=None)`, run once as a migration
(a daemon op, through `bind(partition_name)` in bounded batches) and by R1b for the writer's own new rows.
Its selection is a pure read, `backfill_selection(conn, project_root: Path | None) -> list[Row]`
over a DuckDB connection, which the routine calls and the R7 census calls on a read-only copy
(r3 s-6):
- selects `linkage_evidence` rows with `detail LIKE 'learned from grep%'` that have no sidecar row;
- inserts, through `add_learned_provenance` (so each row also gets its `learned_provenance` event,
  R1d), `origin=backfill`, `source='grep-learn'`, `rules_sha=none`, `learned_at` NULL, `pattern`
  parsed from `detail` (`ast.literal_eval` of the `repr` tail; an unparsable detail is counted
  `unparsed_detail` and still gets a row with `pattern` NULL);
- sets `root` = the project root (the store root's parent) for project stores, and leaves it NULL
  in the global store. Repairing, moving or removing those rows (bug-086) is plan-22's (22.5 sets
  `root` on the rows it imports; 22.3 removes), not this task's;
- never computes `line_hash` (R3).
A second run inserts 0 rows and logs 0 events.

**R6. No silent failures.** {#r6} Every skipped, unreadable, unverifiable (per
`UNVERIFIABLE_REASONS`), unparsed, orphaned (`orphaned_provenance`, R1e), unresolved-on-replay or
overflowed row is counted per
reason and printed (`rmx learn status`, the backfill op's result, the rebuild's result; the
merge's result went with R1c, RETIRED by d9ay).
Project rule: memory-path discipline applies to the store.

**R7. The ONE census procedure (r3 s-6).** {#r7} Every operator census in plans 16 and 22 (16.6
AC-5b; 22.1a AC-5b/6b/7b, including its probe reproduction, and AC-8b's `dangling-link` census;
22.1 AC-6b; 22.3 R1's audit on a copy) uses this procedure and no other.
It is a read-only copy read by the PRODUCTION function; it never constructs `Daemon` or `Store`.
This task owns the script, `scripts/census_on_copy.py`, because 16.6 is the first census in the
wave order (`#t10-waves`).
1. `T=$(mktemp -d /tmp/rmxc-XXXXXX)`: short, and off every watched tree.
2. `cp -p <store_root>/catalog.read.duckdb "$T/catalog.duckdb"` (the lock-free read snapshot;
   never `catalog.A/B.duckdb`, never the `active` slot). When the census names causes from the
   log, also `cp -p <store_root>/facts.log "$T/facts.log"`. No `rmx` call, no socket, no
   `Store()` on the live root (23.4 R1's copy phase, [[task-23.4-option-a-measurement#r1]]).
3. `HOME="$T/home" RMX_HOME="$T/home/.refmatrix" .venv-eval/bin/python scripts/census_on_copy.py
   --census <name> --catalog "$T/catalog.duckdb" [--facts "$T/facts.log"]
   (--project-root P | --global) [census arguments] --out workflow/review-output/<name>.log`.
4. **The real home first (r4 s-3).** `HOME` is redirected by step 3, and `Path.home()` is bound
   at import by modules the deny set needs (`launchctl.LAUNCH_AGENTS_DIR`, `launchctl.py:20`, read
   by `discovery._roots_from_launchd`, `discovery.py:70-83`). So the script's FIRST statement
   reads the real home from `pwd.getpwuid(os.getuid()).pw_dir`, never from `HOME` or
   `Path.home()`, and derives the deny set from it BEFORE importing `refmatrix`: every store root
   named by a `com.refmatrix.daemon*.plist` under `<real home>/Library/LaunchAgents` (its
   `REFMATRIX_ROOT`; the glob is `launchctl.LABEL_PREFIX`, `launchctl.py:22`, copied as a literal
   so nothing is imported first), `<real home>/.refmatrix`, every rmx socket under those roots, and `:7777`.
   An empty deny set is an error (exit nonzero), never a pass. Then it installs 23.0's audit hook
   (23.4 R1: before 23.0 lands, the same hook copied into the script) with that deny set. It
   writes a header to the log: the source paths; the mtime, size and sha256 of each copy; the
   real home and the deny set; and, for a census that reads `facts.log`, the copied log's birth
   time and the last `facts.log compaction` line of `<store_root>/rmxd.log`, read in place
   (r4 m-2).
5. It opens `duckdb.connect("$T/catalog.duckdb", read_only=True)` ONCE and calls the census's
   production function on that connection: `backfill_selection` (16.6),
   `removal_audit.classify_provenance_free` (22.1a), `removal_audit.classify_flag_sensitive`
   (22.1). Files on disk (the project tree, the walked trees) are read in place, read-only.
   - **Classifier inputs are explicit (r4 s-3).** A `provenance-free` or `flag-sensitive` census
     REFUSES to run (exit nonzero) unless `--candidate-trees` and `--home-base` are given; it
     never takes 22.1a's `Path.home()`-relative defaults, which would point into the redirect.
     The operator passes the real home's trees and the real home. Both are printed in the
     header.
   - **The probe reproduction is a named census (r4 m-1).** `--census probe-reproduction` runs
     the committed `eval/spikes/global_relative_resolve_probe.py` rules
     ([[task-22.1a-provenance-free-classes#appendix-probe]]) on the copy, with `--home-base` as
     its `H`. It is the one census that is not a production function, and it is listed here so
     22.1a AC-5b runs inside this procedure, with this header and this audit hook.
   - **The dangling-row census is named (r6 m-3).** `--census dangling-link` calls
     `removal_audit._classify_dangling` (22.1a,
     [[task-22.1a-provenance-free-classes#r1-dangling]]) on the copy, so it REQUIRES `--facts`
     (the dead-end naming reads the copied `facts.log`; a missing `--facts` exits nonzero). It
     walks no tree, so `--candidate-trees` / `--home-base` do not apply; it REQUIRES
     `--default-partition` (the partition an event without a `partition` field belongs to, the
     store's bound partition; a census has no `Store` to read it from) and prints it in the
     header (r7 m-3; a missing value exits nonzero). It also reads
     `<store_root>/rmxd.log` in place, read-only, for the latest `repair_fragments dry_run=` line
     and prints that line with its timestamp beside the class counts (22.1a AC-8b). It
     constructs no `Store`: it never calls `repair_fragments`.
6. It prints the counts, writes them to `--out`, and exits nonzero on any error (counted and
   printed, never swallowed). `$T` is removed only after the log is written.

## Acceptance criteria {#acceptance}

1. **Key and readings.** A row taught under two readings (`-i` and none) has two sidecar rows with
   different `rules_sha`, both joining the one `linkage_evidence` row on the five identity
   columns. `add_learned_provenance` of the same key twice leaves one row and logs one event.
   Mutation "key the sidecar on `rowid`" (d-a's superseded shape) FAILS it: the sidecar row then
   carries no five identity columns, so the join on them finds nothing (moved here from AC-2 when
   AC-2 was retired, d9ay; a rebuild also renumbers `rowid`, so AC-9 fails under it too).
2. **RETIRED (d9ay) with R1c.** No test is written for it, and it is not in the test list.
   Reason: [[#r1c]] (rotation dropped, no producer of diverged slots; `replica_merge` broken,
   bug-113). Original text, kept as history: "Merge survival (s-r5-4). Two slots, each with
   learned rows, one of whose entities is deduplicated (remapped) by the merge. After
   `replica_merge`, every sidecar row joins exactly one `linkage_evidence` row, the sidecar row
   count equals the distinct-key count of both inputs, and `stale_seen` is the max of the two
   inputs. Mutation "key the sidecar on `rowid`" and mutation "leave `learned_evidence` out of the
   merge's table lists" each FAIL it."
3. **The re-run verifier (b-r5-1, b-1, b-4).** Sidecar rows recorded as 16.1 R10 records them
   (`tool=grep`, `bin=/usr/bin/grep`; rg rows with the `rg` on PATH, resolved to an absolute path).
   Each row below must verify as stated, and `matching_lines` must return the stated set:
   - a. BRE `zzz\|alp` on a line `alpha` → `ok`; BRE `\(foo\)x` on `foox` → `ok`;
   - b. `-i` with `ALPHA` on `alpha` → `ok`;
   - c. `[[:digit:]]` on `a1` → `ok`; `\<foo\>` on `foo bar` → `ok` (both compile in Python and
     mis-match there);
   - d. **cutoff:** `match_argv=['-m','1']` (from `-l`), row line 2; line 1 is then edited to
     match too → row `ok`, and `matching_lines` = {1, 2};
   - e. **absolute-path exclude:** `match_argv=['-r','--exclude=*<parent-dir-name>*']`, the
     fixture file under a directory whose name the glob matches → `ok`;
   - f. **tool error:** a grep row with pattern `a\{` and an rg row with pattern `a{` (both exit 2,
     no output) → `unverifiable` with reason `tool-error`, kept, counted;
   - g. a row whose `bin` does not exist → `unverifiable` (`bin-missing`), kept, counted;
   - h. **readings that disagree (r3 s-4).** Two sets, each row carrying two readings, `-F` and
     `-E`, of one pattern: set 1, pattern `a.c` on a line `abc` (only `-E` holds it); set 2,
     pattern `a+c` on a line `x a+c y` (only `-F` holds it). Both rows → `ok` (union). Readings
     are consulted in ascending `rules_sha`, so one set has its matching reading first and the
     other last; the test asserts that both orders occur. The `none` reading is NOT used here: it
     is case-insensitive and regex-or-literal, so it would hold both lines alone;
   - i. **locale (r3 s-1).** A grep row recorded with `locale={"LANG":"en_US.UTF-8", "LC_ALL":
     null, "LC_CTYPE": null}`, pattern `a.b`, on a line `a—b`, verified from a process whose
     environment has NO `LANG`/`LC_*` (the test deletes them, as launchd's plist sets only `PATH`)
     → `ok`; the same row with `locale` naming a locale `setlocale` will not load
     (`xx_YY.UTF-8`) → `unverifiable` (`locale-missing`), never `stale-line`; the same row with
     `LC_CTYPE="UTF-8"` (absent from `locale -a`, loadable) → `ok` (r4 m-3). A sha recomputed from
     the stored `rules_sha` inputs with R1's one serialization equals the stored key;
   - j. **bin pinned (r3 m-6).** An rg row recorded with the absolute `bin` of the real rg,
     verified with a `PATH` whose first `rg` is a fixture script that exits 2 → `ok`.
   Pre-registered mutations, each FAILS this AC: "verify with `evidence_line_matches`" (a, c
   become `stale-line`); "replay `match_argv` whole" (d, e become `stale-line`); "map rc 2 to the
   empty set" (f becomes `stale-line`); "`N` from the first reading only" and "`N` from the last
   reading only" (h: one of the two sets becomes `stale-line`); "inherit the verifier's
   environment" (i becomes `stale-line`); "re-resolve `bin` through `PATH`" (j becomes
   `unverifiable`). No row in a-j may ever classify `stale-line`.

   **3b. The token filter is total and consumes values.** `verify_argv` assigns every keep:match
   and keep:cutoff token of 16.1 R1's table, for both tools, to exactly one of keep/drop; an
   unassigned token fails the test. Arity rows, each verified end to end `ok` (r3 s-2): grep
   `match_argv=['-e','-r']`, pattern NULL, on a line `-r here`; grep `['--exclude','x']`; rg
   `['-g','!x']`; grep `['-m','1']` with a matching later line; rg `['-E','utf8']` (kept) and rg
   `['-j','4']` (dropped with its value) (r4 m-4). An unexpanded cluster `['-rn']` →
   `unverifiable` (`no-rules`). Mutations: "drop grep `-i` instead of `-S`" FAILS row
   b; "filter per token without consuming values" FAILS the `['-e','-r']` row (the pattern
   becomes the next token, rc 1, `stale-line`) and the `['--exclude','x']` row (`x` replayed as a
   pattern operand).

   **3c. The permissive reading names its subset.** A `none` row with pattern `foo\|bar` (or
   `[[:digit:]]`) → `unverifiable` (`permissive-subset`), never `stale-line`; a `none` row whose
   line holds `Foo_Bar` for the pattern `foo bar` → `ok` (identifier variant); a `none` row whose
   line no longer holds the text under any reading → `stale-line`. Mutation "drop the subset
   check" FAILS the first bullet.
4. **Reader-rule drops write nothing (s-r5-3).** An `-i`-taught row (`match_argv=['-i']`,
   `line_hash` = the current line's) read by a case-sensitive `grep_evidence` is dropped by the
   reader and enqueues NO candidate (queue file byte size unchanged). In the same fixture:
   - a row whose file was deleted → one `missing-file` candidate → after the drain
     `stale_seen == 1`, `last_mark = missing-file`;
   - a row whose line was edited but still matches its own rules → `changed` → after the drain
     `last_verified_at` set, `stale_seen == 0`;
   - a row whose line was edited so its own rules fail → `stale_seen == 1`, `last_mark =
     stale-line`.
   Mutation "mark every reader drop" FAILS the first bullet.
5. **Backfill (s-3: a sandbox test plus an operator census).**
   - **5a, sandbox test.** On a fixture store inside the 23.0 sandbox holding `learned from grep`
     rows, including a global-shaped fixture store (store root = the sandbox's redirected
     `~/.refmatrix`): the backfill leaves no learned evidence row without a sidecar row; the
     global fixture's rows have `root` NULL; every backfilled row has `line_hash` NULL; a second
     run inserts 0 and logs 0 events; an unparsable `detail` is counted, not skipped silently.
     Mutation "skip rows silently" FAILS it.
   - **5b, operator census (not a suite test; the 23.0 guard forbids a live store in pytest).**
     Through R7's procedure, on each target store's copy, `backfill_selection` reports the rows
     the backfill WOULD insert (learned evidence rows, distinct identities, `unparsed_detail`,
     global rows with `root` NULL) to `workflow/review-output/16.6-backfill-census.log`, cited in
     the implementation summary. The census is a measurement, not a gate.
   - **5c, the census reads like production (r3 s-6).** In the sandbox, R7's script run on a `cp`
     of a fixture store's `catalog.read.duckdb` reports the same counts the backfill daemon op
     then inserts on that store, and the audit hook's open log shows no open outside `$T`, the
     fixture tree and read-only imports. Mutation "the census re-implements the selection SQL
     with one predicate changed (`detail LIKE 'learned%'`)" FAILS it.
     **Inputs and deny set (r4 s-3).** Two more clauses, each with a mutation: (i) a
     `provenance-free` census run with the `HOME` redirect and no `--home-base` exits nonzero
     and writes no counts (mutation "default `home_base` to `Path.home()`" FAILS it); (ii) with a
     fixture `com.refmatrix.daemon.x.plist` naming a fixture store root under the REAL-home
     stand-in (the sandbox provides `pwd` home and `HOME` as two different dirs), the logged deny
     set holds that root and an open of it is refused (mutation "derive the deny set after
     `HOME` is redirected" FAILS it: the set is empty and the open succeeds).
6. **No window before 16.1 (R1b; m-6).** After this slice, a `learn_from_grep` op on a tmp store,
   run twice with the same hits, writes evidence rows (duplicates included: `add_evidence` is still
   an unconditional INSERT until 16.1) and one `legacy-writer` sidecar row per DISTINCT evidence
   identity (the five columns); a query for learned evidence identities with no sidecar row
   returns 0. Mutation "remove R1b's call" FAILS it.
7. **Bounded drain.** 1,000 marks drain in ⌈1000/N⌉ batches under plan-23's lock-hold probe
   (23.2's fixture), each hold within the bound. Mutation "write the mark inline under
   `_store_lock`" FAILS it (the probe sees a hold on the read path).
8. **Overflow is counted (#m-3).** Enqueueing past the queue cap leaves `rmx learn status` printing
   `marks dropped (overflow): N` equal to plan-23's overflow counter.
9. **Rebuild keeps provenance (b-2; r3 m-1).** Write learned rows with sidecar rows under two
   readings; seed a `linkage_evidence` row at the NEW identity through `add_evidence` (so its
   `evidence` event is logged; a sidecar row never sits on a key with no evidence row, R1), then
   apply `move_learned_provenance` to the old identity, then run `rebuild_index_from_log` on a
   sandbox COPY of the store: the sidecar after the rebuild equals the sidecar before it on every
   column except the three mark columns (which are NULL/0, counted `marks_reset`), and the moved
   row sits at its new identity (the rebuild is the one replay path, d9bu). Mutations "no
   `learned_provenance` event" and "no `learned_provenance_move` event" each FAIL it, and so does
   "replay the move events in their own pass before the `learned_provenance` events" (the moved
   reading is counted `unresolved_provenance`).

   **9b. Compact, then rebuild (r4 b-2).** On a sandbox store with sidecar rows under two
   readings, one of them moved by `move_learned_provenance`, run `dump_catalog_to_log` (the
   compactor's call, `Daemon._compact_factslog_if_needed`), then `rebuild_index_from_log` on a sandbox copy: the
   sidecar equals the pre-compaction sidecar on every column except the three mark columns,
   `unresolved_provenance` is 0, and the compacted log holds one `learned_provenance` event per
   sidecar row. Mutation "dump without `learned_evidence`" FAILS it (the rebuilt sidecar is
   empty).

   **9c. The row pass is one timestamp order (d9av; r7 b-1).** `Store._row_pass_events` on a
   fixture event list for one partition: `evidence` E1 (ts 1), `learned_provenance` P1 (ts 1,
   after E1 in the log), `learned_provenance_move` M1 (ts 2), `evidence` E2 (ts 3),
   `learned_provenance` P2 (ts 3), and an `evidence` E3 at ts 2 that the log holds AFTER E2 (a
   writer whose clock lagged). It returns exactly `[E1, P1, M1, E3, E2, P2]`: ts order, ties by
   log position, appends and row ops interleaved. An AST check asserts that pass 3 of
   `rebuild_index_from_log` applies its evidence appends and row ops only through
   `_row_pass_events` (no separate `evidence_events` loop is left IN PASS 3). The check targets
   pass 3 only: Pass 2b's resolution loop stays (r8 m-1), and the bug-117 tests
   (`tests/test_bug117_rebuild_non_concept.py`: the rebuild's `evidence_unresolved` /
   `evidence_skipped_dead`)
   still pass unchanged. Mutations, each
   FAILS it: "appends first, then the row ops" (round 3's pass: the function returns `[E1, E3,
   E2, P1, M1, P2]`); "file order, not `ts`" (E3 lands after P2); "keep the separate
   `evidence_events` loop" (the AST check). With this slice's ops alone the two orders rebuild
   the same state (no 16.6 op removes a row, and an append before its time can only resolve
   more provenance), so the end-to-end proof that the order matters is 22.2 AC-3d / AC-3e, which
   add `evidence_remove` to this pass and fail under "appends first".

   **9d. One spelling, one key, one resolver, one counter (d9bl; r8 b-1, m-1).**
   - *The builder.* `row_event` raises on `op="link"` (not a row op), on `c_kind=None` and on
     `c_kind=""`, and on `e=None` for every op, `evidence_orphan_drop` included (d9cc); it returns the
     `edge_fields` order for each op in `ROW_OPS`.
   - *Pass 2b feeds the row pass.* A sandbox log holds a LEGACY `evidence` append (no `c_kind`)
     for `(mentions, query/P, F, 12)`, written as a pre-0.78.3 log would hold it, followed by
     the kinded `learned_provenance` event for the same row. A rebuild on a copy holds the
     evidence row and its sidecar row, with `unresolved_provenance == 0` and
     `evidence_unresolved == 0`.
   - *The mechanical check (AST, over `src/refmatrix/`).* It iterates `edge_records.ROW_OPS`, so
     the ops 22.2 and 22.6 add are covered when they land:
     1. no dict display whose `"op"` key holds a constant in `ROW_OPS` exists outside
        `edge_records.row_event`;
     2. `resolve_legacy_kind` is called in `src/refmatrix/` only from
        `edge_records.resolve_c_kind`, and the callers of `resolve_c_kind` are exactly Pass 2b,
        the row pass and 22.6's `vacuum` log scan (r10 s-1, d9bz: the scan keys each orphan drop
        on the orphan's own appends); `_replay_concept` is deleted ([[#r1f]]); 22.2's
        `_row_op_c_kinds` reads the constant `edge_records.LEGACY_PREFERRED_KIND` and calls
        neither (r9 m-1), and `vacuum` calls neither `_row_op_c_kinds` nor 22.1a's
        `names_from_log`;
     3. scoped to the code that resolves EDGE ends (r9 m-5): inside the link pass and the row
        pass of `rebuild_index_from_log` (the `EDGE_OPS ∪ ROW_OPS` events), no call of
        `get_entity` and no `name_to_id` subscript or membership test whose kind element is a
        constant; the kind comes from the event (`c_kind` / `e_kind` after Pass 2b). Outside
        that scope by name, and allowed: Pass 3's memory-body block (`("memory", key[1]) not in
        name_to_id`), which resolves a `memory_content` body, not an edge end. There is no
        `_apply_event_body` half (deleted, [[#r1f]]);
     4. the row-op apply code calls `edge_records.row_key` and takes every identity value from
        it (`k = row_key(ev)`, then `k[5]`, `k[6]` for `file` and `line`, including the SQL
        parameter tuple `evidence_remove`'s DELETE needs); it reads no `"file"` or `"line"`
        subscript (or `.get`) of an event directly (r9 m-5);
     5. `row_skips` is written only inside `Store._row_skip`.
   - Mutations, each FAILS it: "the row pass reads the appends before Pass 2b" (the legacy
     append's `c_kind` is None, `row_key` differs, `unresolved_provenance` is 1); "a row-op site
     spells its event as a dict literal" (check 1); "a row op resolves `c` as kind `concept`"
     (check 3); "a second `resolve_legacy_kind` call in the row pass" (check 2); "a row-op
     branch keeps its own counter" (check 5).
10. Mutations that must FAIL a test, each with its AC above: sidecar on `rowid` (1; was 2);
    sidecar not merged (2: RETIRED with R1c, d9ay); Python `re` verifier (3);
    `match_argv` replayed whole (3); rc 2 read as no-match
    (3); first/last reading only (3h); inherited env (3i); `bin` re-resolved (3j); filter drops a
    pattern token (3b); filter ignores arity (3b); permissive subset check removed (3c); mark
    every reader drop (4); backfill skips silently (5a); census selection re-implemented (5c);
    remove R1b (6); inline mark (7); overflow uncounted (8); no provenance event (9); no move
    event (9); move events replayed in their own pass (9); appends first, then the row ops (9c);
    file order, not `ts` (9c); the row pass reads the appends before Pass 2b, a dict-literal
    row event, a row op resolving `c` as kind `concept`, a second legacy resolver, a per-branch
    counter (9d); dump without `learned_evidence` (9b);
    census defaults `home_base` / deny set derived after the redirect (5c); purge deletes or
    hides an orphaned sidecar row (11); keep any of the four incremental methods, a comment
    naming one, or the incremental test (12).
11. **Orphaned sidecar rows are kept and counted (R1e; r3 s-5).** On a sandbox store with a
    learned row and its sidecar row, `purge_path` of the file leaves the sidecar row in place
    and `rmx learn status` prints `orphaned_provenance: 1`; `vacuum` leaves it too. Mutation
    "`purge_entity` deletes the sidecar rows by `entity_id` without a manifest" FAILS it.
    **Scope (r4 m-5).** This AC states the Wave-1 slice's interim. When 22.6 R3/R5 land, a
    missing file's purge and `vacuum` move the sidecar row into a cleanup manifest instead
    (22.6 AC-4, AC-6), and 22.6 REWRITES this test
    ([[task-22.6-removal-entry-points#files-to-modify]]): it keeps the `orphaned_provenance`
    count for any orphan a non-routed path still leaves, and drops the "purge leaves the row"
    clause.
12. **The incremental replay path is gone (R1f; d9bu, r9 s-2; r10 m-3).** The scan of
    [[#r1f]] runs over `src/refmatrix/`, `scripts/` and `eval/` (text) and `tests/` (AST:
    names, attributes and string constants, its own module excluded) and finds none of `apply_log_delta`,
    `_apply_one_event`, `_apply_event_body`, `_replay_concept`, `REPLICA_REBUILD_DELTA_BYTES`;
    `tests/test_bug117_rebuild_non_concept.py`'s rebuild tests pass unchanged. Mutations, each
    FAILS it: "keep `apply_log_delta` (or any one of the four)" (the text scan names its `def`
    line); "delete the methods but leave the `add_memory` comment naming `_apply_one_event`"
    (the text scan); "keep the incremental test" (the AST scan names its `dst.apply_log_delta`
    attribute); "rewrite the methods away but leave `tests/test_memory_content_log.py`'s
    docstring naming `apply_log_delta`" (the AST scan's string-constant match). The
    fixture-tree self-check runs BOTH modes (r10 m-3): under `tmp_path`, a `src/` file holding
    `def apply_log_delta` must give a TEXT hit, and a `tests/` file holding
    `dst.apply_log_delta(...)` must give an AST attribute hit and one holding a docstring
    naming `_apply_one_event` an AST constant hit (a `def` is a `FunctionDef`, which the
    `Name` / `Attribute` match does not see, so the text mode carries that case).

The audit/prune/repair acceptance moved to plan-22. {#acceptance-moved}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/duckdb_catalog.py` | `learned_evidence` DDL + primary key |
| `src/refmatrix/store.py` | `dump_catalog_to_log` emits one `learned_provenance` event per sidecar row of a dumped evidence row after each partition's `evidence` events, with its evidence row's `ts`, and counts the dead-end rows it skips `provenance_not_dumped` (R1d, r4 b-2, d9av; round 14); `add_learned_provenance` (+ `learned_provenance` events); `move_learned_provenance` (+ `learned_provenance_move` event); DELETE `apply_log_delta`, `_apply_one_event`, `_apply_event_body`, `_replay_concept` and rewrite the `add_memory` comment that names them ([[#r1f]], d9bu); both ops in `rebuild_index_from_log`'s ONE timestamp-ordered row pass, which replaces pass 3's separate `evidence_events` loop and keeps Pass 2b (`_row_pass_events`, R1d, d9av; r8 m-1); Pass 2b calling `edge_records.resolve_c_kind`; `_row_skip` / `row_skips` ([[#r1d-one-format]], d9bl); `verify_evidence_rows` stats split (`missing_file`, `out_of_range`, `reader_rule`); `grep_evidence` enqueues R4 candidates for learned rows |
| `src/refmatrix/edge_records.py` | `ROW_OPS` (this slice's two ops), `row_event`, `row_key`, `resolve_c_kind` (Pass 2b's rule, extracted) ([[#r1d-one-format]], d9bl); 22.2 and 22.6 add their ops to `ROW_OPS` |
| `src/refmatrix/learned_verify.py` (new) | R2: `Rules`, `Unverifiable`, `UNVERIFIABLE_REASONS`, `verify_argv`, `matching_lines`, `permissive_matching_lines`, `hash_line`, `verify` |
| `src/refmatrix/replica_merge.py` | none: R1c is RETIRED (d9ay) |
| `src/refmatrix/daemon.py` | DELETE `REPLICA_REBUILD_DELTA_BYTES` and its comment ([[#r1f]], d9bu); R4 drain consumer (pre-step + batch apply) on plan-23's drain; R5 backfill op; R1b call in `_learn_grep_hits` |
| `src/refmatrix/cli.py` | `rmx learn status`: mark counts ("at least"), overflow, unverifiable-by-reason/unparsed counts, `orphaned_provenance` |
| `scripts/census_on_copy.py` (new) | R7: the ONE census procedure (real home from `pwd` first, deny set, copy header incl. log birth time and last compaction, audit hook, read-only connection, production functions, explicit classifier inputs, `probe-reproduction`, `dangling-link`) |
| `tests/test_learned_evidence.py` (new) | AC-1, AC-4..9, AC-9b, AC-9c, AC-9d, AC-11 (rewritten by 22.6, r4 m-5); AC-5c (AC-2 RETIRED, d9ay) |
| `tests/test_learned_verify.py` (new) | AC-3, AC-3b, AC-3c |
| `tests/test_bug117_rebuild_non_concept.py` | DELETE `test_the_incremental_replay_resolves_non_concept_rows` ([[#r1f]], d9bu); the rebuild tests stay unchanged |
| `tests/test_memory_content_log.py` | module docstring names `rebuild_index_from_log` only ([[#r1f]]) |
| `tests/test_incremental_replay_retired.py` (new) | AC-12: the text scan (`src/refmatrix/`, `scripts/`, `eval/`) + AST scan (`tests/`, names, attributes and string constants) and its two-mode fixture-tree self-check (r10 m-3) |
| `scripts/factslog-restore.py` (plan-17 task 17.4's) | `learned_provenance`, `learned_provenance_move` added to `FOLD_OPS`, each with its stated fold rule (r10 s-3): COUNT-NEUTRAL, named in `FOLD_OPS` as ignored for the `entities` / `links` / `evidence` counts, because both touch only the `learned_evidence` sidecar, which 17.4's count check does not compare; 22.6 AC-6d runs the fold-equals-rebuild check over logs holding them. In the same commit as the replay branch: 17.4's AST test pins `FOLD_OPS` to `rebuild_index_from_log`'s op set, and an op missing from it fails restore verification loudly (`unknown event op`) ([[task-17.4-factslog-backup-snapshot#r6-restore]]; ns17-r9-2) |

## Test strategy {#test-strategy}

- **Sandbox (d1a/d1b).** Every test runs inside task 23.0's shared sandbox: `$HOME`, the global
  root, the registry and the LaunchAgents dir point at a tmp dir before `refmatrix` is imported;
  store roots are injected; spawned `rmx` children refuse sockets outside the tmp dir; the conftest
  guard fails any test touching `~/.refmatrix` or a registered live store. Stores live under a
  SHORT `mkdtemp()` root.
- Real `Store`, real `Daemon`, real `/usr/bin/grep` and `rg` for R2 (skipped with a printed reason
  when absent). The rebuild AC runs on a COPY made inside the sandbox.
- **Census (s-3, r3 s-6).** No test reads a live catalog. AC-5b is an operator step through R7's
  procedure, logged under `workflow/review-output/`; AC-5c proves in the sandbox that the
  procedure reads through the production function. Every AC that gates is a sandbox test.
- The drain ACs use plan-23's 23.2 lock-hold fixture, not a timer.
- Pre-registered mutations: [[#acceptance]] item 9.

## Decisions {#decisions}

- **d-a. Provenance lives in a SIDECAR table** {#d-a}. AMENDED in revision 6 (s-r5-4, b-r5-1,
  #t6-fixes): the key is the evidence row's five identity columns plus `rules_sha`, and the
  columns are R1's. *Original (2026-10-07, superseded):* `learned_evidence(evidence_rowid, source,
  learned_at, root, pattern, flags, last_verified_at, stale_seen)`. Ingest's `linkage_evidence` is
  untouched either way, so the migration is cheap and reversible.
- **d-b. Audit and prune run on demand; read-time verification records marks** {#d-b}. AMENDED in
  revision 6 (s-r5-3): the marks record staleness under the row's OWN rules, never the reader's
  filtering (R4). Nothing deletes automatically: no scheduled prune.
- **d-c. (moved to plan-22, and AMENDED by the user 2026-10-07: "don't delete moves, repair them
  if possible").** `prune --apply` removes the non-`ok` classes EXCEPT `moved`, which is
  re-pointed. {#d-c}
- *(original d-c, superseded):* `prune --apply` removes every non-`ok` class by default: `moved`,
  `stale-line`, `out-of-range`, `missing-file`, `duplicate` and `orphan-root`. `--class` narrows
  it. The dry run remains the default.
- **d-d. Scope** {#d-d}. AMENDED by d6d (user, 2026-10-14): Wave 1, after plan-23's 23.1, with no
  dependency on 16.1; the learn-time write is 16.1 R10. *Original (2026-10-07, superseded):*
  "inside plan-16, after 16.1".

**For the spec review (ch-bsd r7 #m-5) — ANSWERED by the user 2026-10-07:** `moved` is the one
class whose row could be re-pointed instead of deleted. The user's answer ("don't delete moves,
repair them if possible") made re-pointing the DEFAULT and moved it, with the whole engine, to
[[task-22.2-repair-then-remove]] R1. Kept here as history. {#d-c-review}

The read-time marks (d-b) are writes on a READ path, so they never take `_store_lock` inline. They
go through plan-23's queue and its bounded drain (the 0.72.3 lesson in
`project_grep_learn_wall_and_queue`). {#d-b-write-path}
