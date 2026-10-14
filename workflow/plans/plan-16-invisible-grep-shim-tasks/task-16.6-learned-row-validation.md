---
gmd: "0.1"
id: task-16.6-learned-row-validation
title: "Task 16.6 (Wave-1 slice): the learned-evidence sidecar, a dialect-faithful verifier, read-time marks and the provenance backfill (audit/prune/repair moved to plan-22; the learn-time write moved to 16.1)"
tags: [task, grep, learning, validation, provenance, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 16.6: the learned-evidence sidecar, its verifier, read-time marks and the backfill {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision after the 2026-10-14 decision log). Revision 6 of plan-16's specs; the
> first revision of 16.6 after its first spec review (r5, `bsd-plan16-spec-review-r5-cd7c923`).
> The user asked for it on 2026-10-07: "rmx grep learning entries should be cullable and/or at
> least have a validation process to check for stale entries". The CULL half lives in plan-22
> ([[#split]]).
> **Wave:** 1, after plan-23's task 23.1 (`bind(batch)`, the durable queue and bounded drain), and
> before plan-22's 22.1a ([[plan-review-2026-10-14#t8-wave1]]).
> **Depends on:** plan-23 task 23.1 (queue + `bind(batch)` drain), plan-23 task 23.0 (the shared
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
rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: motivates -> [[plan-22-audited-removal-and-repair]]
rel: motivates -> [[task-22.1-audit-classes]]
rel: motivates -> [[task-22.2-repair-then-remove]]
rel: motivates -> [[task-22.3-bug-086-global-repair]]

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
| R1c `replica_merge` carries the sidecar | this task (Wave 1) | [[#r1c]] |
| R2 the dialect-faithful verifier | this task (Wave 1) | [[#r2]] |
| R4 read-time `last_verified_at` / `stale_seen` marks, queued | this task (Wave 1), through plan-23's queue | [[#r4]] |
| R5 provenance backfill (project roots; global roots NULL) | this task (Wave 1) | [[#r5]] |
| R6 loud counting on every leg | this task (Wave 1) | [[#r6]] |
| the LEARN-TIME provenance write (tool, dialect, match tokens, line hash, `spawned_by`) | task 16.1 R10 (Wave 2), d6d | [[task-16.1-argv-faithful-learner#r10]] |
| `rmx learn audit` and its classes (`ok`, `moved`, `ambiguous`, `stale-line`, `out-of-range`, `missing-file`, `duplicate`, `orphan-root`, `orphan-alias`, `empty-learned`) | plan-22 (22.1a provenance-free; 22.1b the rest) | [[task-22.1-audit-classes]] |
| repair then removal; manifest; row-level events; ablation gate | plan-22 | [[task-22.2-repair-then-remove]] |
| bug-086's global repair | plan-22 | [[task-22.3-bug-086-global-repair]] |

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
| `rules_sha` | sha256 hex of the canonical JSON `[tool, dialect, match_argv]`; the literal `none` when the row has no recorded rules (backfill, legacy writer) |
| `origin` | `learner` (16.1 R10), `context-backstop` (16.1 R10), `legacy-writer` (R1b), `backfill` (R5) |
| `source` | `grep-learn` |
| `learned_at` | epoch seconds; NULL for `backfill` (unknown, never invented) |
| `root` | the absolute project root the row was learned under; NULL in the global store until plan-22's 22.3 |
| `pattern` | the pattern as the tool received it |
| `tool`, `bin` | `grep` / `rg` and the absolute binary that produced the hit; NULL when unknown |
| `dialect` | `bre`, `ere`, `fixed`, `python` (the decision log's four), plus `rust` and `pcre2` for rg rows and `mixed` when the kept tokens name more than one; NULL when unknown. Informational: R2 always re-runs `tool` itself |
| `match_argv` | the kept MATCH-class and CUTOFF-class tokens verbatim, in order, as 16.1 R1's table kept them (JSON list) |
| `line_hash` | sha256 hex of the matched line's bytes as the tool printed them, without the line terminator; NULL when not recorded |
| `spawned_by` | `shim`, `grep-tool-hook`, `rmx-grep`, `context-backstop`; NULL for `backfill`/`legacy-writer` |
| `last_verified_at`, `stale_seen`, `last_mark` | R4's marks; `last_mark` in `gone-file`, `out-of-range`, `changed-line` |

- **Primary key `(entity_id, linkage_id, concept_id, file, line, rules_sha)`.** It never uses
  DuckDB's `rowid`, which `replica_merge` rewrites (s-r5-4). Two readings of one row (`grep -i foo`
  and `grep foo` both teach `query/foo`) are two sidecar rows; R2 calls the row `ok` when ANY of
  its readings passes.
- **Writer API:** `Store.add_learned_provenance(rows)` inserts with `ON CONFLICT DO NOTHING` on the
  key, inside the caller's transaction. It is the only writer of the table besides R4's drain and
  R1c's merge. 16.1 R10 calls it from `_learn_grep_hits`; R1b and R5 call it here.
- The DDL lives in `duckdb_catalog.py` beside `linkage_evidence`. `linkage_evidence` is untouched,
  so the migration is additive and reversible (d-a).

**R1b. No new evidence row without a sidecar row, from the day this slice lands (s-r5-5).** {#r1b}
Between this Wave-1 slice and 16.1, today's writer keeps teaching. So `_learn_grep_hits`, in the
same transaction as its `add_evidence` calls, calls R5's backfill routine for exactly the rows it
just inserted: `origin=legacy-writer`, `rules_sha=none`, `learned_at` = now, `root` = the
`project_root` argument, `pattern`, everything else NULL. This is not 16.1 R10's provenance (no
tool, dialect or hash is known on today's path); 16.1 R10 replaces this call. `legacy-writer` rows
are verified like backfilled rows (R2's `unverifiable` branch; plan-22's most-permissive rule).

**R1c. `replica_merge` carries the sidecar (s-r5-4).** {#r1c}
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

**R2. The verifier speaks the row's own dialect (b-r5-1, #t6-fixes).** {#r2}
`learned_verify.verify(rows, project_root) -> {key: verdict}` in `src/refmatrix/learned_verify.py`
(new). Verdicts: `ok`, `stale`, `gone-file`, `out-of-range`, `unverifiable`.
- **Rows with recorded rules** (`tool` and `bin` set): re-run `bin` with `match_argv`, then the
  canonical tail (`-nH --null` for grep; `-nH --null --no-heading --color never --no-config` for
  rg), then `-e <pattern>` (omitted when `match_argv` already carries `-e`/`--regexp` tokens, as
  the context backstop's rows do), then `-- <file>`, on that ONE file (absolute, from `root` + `file`), with
  `stdin=/dev/null` and a per-file timeout. `ok` when `line` is in the output. One run per
  `(file, rules_sha)`, shared by all of that file's rows. Python `re` is NEVER used for these rows.
- `bin` missing or not executable, or a timeout → `unverifiable` (KEPT, counted by reason).
- **`dialect=python`** rows are evaluated with `evidence_line_matches`. No plan-16 writer produces
  them after 16.5; the branch exists so the enum has no unverifiable member by construction.
- **Rows with no rules** (`rules_sha=none`: `backfill`, `legacy-writer`) → `unverifiable` HERE.
  plan-22's 22.1 re-checks them under the most permissive reading (case-insensitive, literal OR
  regex, plus `identifier_variant_regex`; #t6-fixes, plan-22 #b-2); this verifier does not decide
  them.
- `gone-file` (unreadable or missing) and `out-of-range` (line > file length) are decided before
  any re-run.
- The verifier is subprocess-bound, so it runs in R4's drain pre-step and in plan-22's audit,
  NEVER on the read path.

**R3. The line hash (#t6-fixes, plan-22 #b-1).** {#r3}
`line_hash` is written at learn time by 16.1 R10 from the bytes the tool printed. Here it serves
two readers: R4 compares it to the current line to tell `changed-line` from a reader-rule drop, and
plan-22's per-`(concept, file)`-set repair (#t6-fixes `#b-1`) may use it as an optional extra on
rows that have it. A backfilled or legacy row has `line_hash` NULL; nothing computes one from the
current file (that would certify a possibly stale line as current).

**R4. Read-time marks: staleness only, never the reader's own filtering (s-r5-3, d-b).** {#r4}
- `verify_evidence_rows`'s stats split today's `dropped` into `out_of_range` and `reader_rule`
  (the line was read and fails the READER's pattern, case or regex flag), and add `gone_file`
  (= today's `unreadable`). The existing keys stay for their readers: `unreadable` unchanged,
  `dropped` = `out_of_range` + `reader_rule`.
- For each LEARNED row the read touches (a sidecar join on the five identity columns), the read
  path enqueues at most one candidate, through plan-23's durable queue (no lock, no inline write):
  - kept by the reader, and `line_hash` equal or NULL → `seen`;
  - `gone_file` → `gone-file`; `out_of_range` → `out-of-range`;
  - current line hash ≠ `line_hash` (kept OR dropped by the reader) → `changed`;
  - **a `reader_rule` drop whose line hash equals `line_hash`, or whose `line_hash` is NULL,
    enqueues NOTHING.** The row is healthy; the reader asked a different question (16.1 R8:
    `-i`-taught rows are dropped for a case-sensitive `rmx grep` by design).
- **The drain** runs in plan-23's bounded `bind(batch)` drain (23.1). A pre-step OUTSIDE the lock
  re-checks each candidate: `gone-file`/`out-of-range` are re-stat'ed (a transient read error does
  not mark); `changed` candidates go through R2 under the row's OWN rules. Then, inside the batch:
  `seen` and a `changed` that R2 calls `ok` set `last_verified_at`; a re-confirmed `gone-file`,
  `out-of-range`, or a `changed` that R2 calls `stale` adds 1 to `stale_seen` and sets
  `last_mark`. `unverifiable` writes nothing and is counted.
- Nothing is deleted. `stale_seen` is an input to plan-22's audit, never a removal trigger here.
- **`stale_seen` is a LOWER BOUND (decision-log review #m-3).** {#r4-lower-bound} plan-23's queue
  coalesces by key and drops on overflow (with a counted overflow). A coalesced or dropped mark
  undercounts `stale_seen`, which can only DELAY a plan-22 removal, never cause one. The overflow
  count is printed by `rmx learn status` as `marks dropped (overflow): N`. Consumers must not read
  `stale_seen` as an exact count (listed for plan-22 in the plan's `#open-after-revision`).

**R5. Provenance backfill (d6d Wave 1).** {#r5}
One idempotent routine, `backfill_learned_provenance(store, rows=None)`, run once as a migration
(a daemon op, through `bind(batch)` in bounded batches) and by R1b for the writer's own new rows:
- selects `linkage_evidence` rows with `detail LIKE 'learned from grep%'` that have no sidecar row;
- inserts `origin=backfill`, `source='grep-learn'`, `rules_sha=none`, `learned_at` NULL,
  `pattern` parsed from `detail` (`ast.literal_eval` of the `repr` tail; an unparsable detail is
  counted `unparsed_detail` and still gets a row with `pattern` NULL);
- sets `root` = the project root for project stores, and leaves it NULL in the global store.
  Repairing or removing those rows (bug-086) is plan-22's 22.3, not this task;
- never computes `line_hash` (R3).
A second run inserts 0 rows.

**R6. No silent failures.** {#r6} Every skipped, unreadable, unverifiable, unparsed, orphaned or
overflowed row is counted per reason and printed (`rmx learn status`, the backfill op's result, the
merge's result). Project rule: memory-path discipline applies to the store.

## Acceptance criteria {#acceptance}

1. **Key and readings.** A row taught under two readings (`-i` and none) has two sidecar rows with
   different `rules_sha`, both joining the one `linkage_evidence` row on the five identity
   columns. `add_learned_provenance` of the same key twice leaves one row.
2. **Merge survival (s-r5-4).** Two slots, each with learned rows, one of whose entities is
   deduplicated (remapped) by the merge. After `replica_merge`, every sidecar row joins exactly one
   `linkage_evidence` row, the sidecar row count equals the distinct-key count of both inputs, and
   `stale_seen` is the max of the two inputs. Mutation "key the sidecar on `rowid`" and mutation
   "leave `learned_evidence` out of the merge's table lists" each FAIL it.
3. **Dialect-faithful verification (b-r5-1).** Sidecar rows recorded as 16.1 R10 records them
   (`tool=grep`, `bin=/usr/bin/grep`, `dialect=bre`, `match_argv=[]`): pattern `zzz\|alp` on a line
   `alpha`, and pattern `\(foo\)x` on a line `foox`. Both verify `ok`. A third row, `-i` with
   pattern `ALPHA` on `alpha`, verifies `ok`. Mutation "verify with `evidence_line_matches`" makes
   the first two `stale` and FAILS the AC. A row whose `bin` does not exist is `unverifiable`, kept,
   counted.
4. **Reader-rule drops write nothing (s-r5-3).** An `-i`-taught row (`match_argv=['-i']`,
   `line_hash` = the current line's) read by a case-sensitive `grep_evidence` is dropped by the
   reader and enqueues NO candidate (queue file byte size unchanged). In the same fixture:
   - a row whose file was deleted → one `gone-file` candidate → after the drain `stale_seen == 1`;
   - a row whose line was edited but still matches its own rules → `changed` → after the drain
     `last_verified_at` set, `stale_seen == 0`;
   - a row whose line was edited so its own rules fail → `stale_seen == 1`, `last_mark =
     changed-line`.
   Mutation "mark every reader drop" FAILS the first bullet.
5. **Backfill on a catalog COPY.** On a copy (inside the 23.0 sandbox) of a store holding `learned
   from grep` rows, the backfill leaves no learned evidence row without a sidecar row; the global
   copy's rows have `root` NULL; every backfilled row has `line_hash` NULL; a second run inserts 0;
   an unparsable `detail` is counted, not skipped silently. Mutation "skip rows silently" FAILS it.
6. **No window before 16.1 (R1b).** After this slice, a `learn_from_grep` op on a tmp store writes
   evidence rows and the same number of `legacy-writer` sidecar rows; a query for learned evidence
   rows with no sidecar row returns 0. Mutation "remove R1b's call" FAILS it.
7. **Bounded drain.** 1,000 marks drain in ⌈1000/N⌉ batches under plan-23's lock-hold probe
   (23.2's fixture), each hold within the bound. Mutation "write the mark inline under
   `_store_lock`" FAILS it (the probe sees a hold on the read path).
8. **Overflow is counted (#m-3).** Enqueueing past the queue cap leaves `rmx learn status` printing
   `marks dropped (overflow): N` equal to plan-23's overflow counter.
9. Mutations that must FAIL a test, each with its AC above: sidecar on `rowid` (2); sidecar not
   merged (2); Python `re` verifier (3); mark every reader drop (4); backfill skips silently (5);
   remove R1b (6); inline mark (7); overflow uncounted (8).

The audit/prune/repair acceptance moved to plan-22. {#acceptance-moved}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/duckdb_catalog.py` | `learned_evidence` DDL + primary key |
| `src/refmatrix/store.py` | `add_learned_provenance`; `verify_evidence_rows` stats split (`gone_file`, `out_of_range`, `reader_rule`); `grep_evidence` enqueues R4 candidates for learned rows |
| `src/refmatrix/learned_verify.py` (new) | R2 verifier |
| `src/refmatrix/replica_merge.py` | table lists + the sidecar step (R1c) |
| `src/refmatrix/daemon.py` | R4 drain consumer (pre-step + batch apply) on plan-23's drain; R5 backfill op; R1b call in `_learn_grep_hits` |
| `src/refmatrix/cli.py` | `rmx learn status`: mark counts, overflow, unverifiable/unparsed counts |
| `tests/test_learned_evidence.py` (new) | AC-1..8 |

## Test strategy {#test-strategy}

- **Sandbox (d1a/d1b).** Every test runs inside task 23.0's shared sandbox: `$HOME`, the global
  root, the registry and the LaunchAgents dir point at a tmp dir before `refmatrix` is imported;
  store roots are injected; spawned `rmx` children refuse sockets outside the tmp dir; the conftest
  guard fails any test touching `~/.refmatrix` or a registered live store. Stores live under a
  SHORT `mkdtemp()` root.
- Real `Store`, real `Daemon`, real `/usr/bin/grep` and `rg` for R2 (skipped with a printed reason
  when absent). The backfill AC runs on a COPY made inside the sandbox, never on a live
  `.refmatrix/`.
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
