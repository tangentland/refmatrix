---
gmd: "0.1"
id: bsd-plan22-spec-review-3104a81
title: "plan-22 spec review: `moved` has no key on real data, existing rows have no flags to re-verify under, row-level repairs and removals have no replay form, and the ablation gate measures stores the candidates are not in"
severity: BULLSHIT
plan: plan-22-audited-removal-and-repair
task: spec-review-22.1-22.4
round: 1
tags: [bsd, audit, spec-review, removal, repair, grep-learning, concepts, bug-086, bug-088, global-store]
---

# ch-bsd spec review of plan-22, round 1 (pre-implementation) {#root}

**Commit reviewed:** `3104a81` (plan-22 and task specs 22.1-22.4, all `drafting`/`pending`/`blocked`).
HEAD moved to `03bd532` while I worked. `git diff --stat 3104a81..HEAD` = `handoff.md` only, so the
reviewed specs are byte-identical at HEAD. Branch `wave0-spec-reviews`.
**Written:** 2026-10-14T11:13:20-0700.

**Method:** I read the plan, the four task specs, task-16.6 (the plan-16 revision-5 agent owns it;
not edited), the plan review's C1/C2/C3 and wave order, ADR-0004 `#rule-no-delete`, the concept
exploration (`concept-similarity-cull-merge.md` `#data`, `#option-b`), the storage exploration
(`storage-concurrency-redesign.md` `#option-a`, `#recommendation`), plan-23 and its concurrent
review (`bsd-plan23-spec-review-3104a81`), and the memories `project_global_relative_rows_repair`
and `feedback_decay_never_loses_knowledge`. I checked every mechanism against `src/` at HEAD:
- `store.py`: `evidence_line_matches`, `verify_evidence_rows`, `add_evidence`, `forget_by_selector`
  / `_bulk_purge_ids`, `_apply_event_body`, the `rebuild_index_from_log` LWW pass, and
  `_canonical_for_kind`;
- `daemon.py`: `_learn_grep_hits`, `_op_learn_from_grep`, the learn drain, `_op_rebuild_index`;
- `cli.py`: `_broker_learn_from_grep` and its callers;
- `ingest.py` `_bulk_add_concepts`; `duckdb_catalog.py` (the `linkage_evidence` DDL);
- `eval/production/*.py`.

**Live evidence, read-only:** the project `.refmatrix/facts.log` and the global
`~/.refmatrix/facts.log` were parsed with Python (logs, not catalogs). I also read
`workflow/review-output/global-relative-resolve-probe.log`. **One limit:** cloning the two
`catalog.read.duckdb` snapshots into my scratchpad was DENIED by the auto-mode classifier. So the
catalog counts (9,182, 747, 5,159) are taken from their source documents and NOT re-measured. Each
finding says which numbers come from the log and which from a document.

Nothing in `src/`, `tests/`, any store, INDEX.md, IMPRESSIONS.md, last_run.log or any plan file was
touched. No `rmx` write, no `Store()` open, no suite run.

rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: related-to -> [[bsd-plan23-spec-review-3104a81]]
rel: related-to -> [[plan-review-2026-10-07]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: related-to -> [[project_global_relative_rows_repair]]

## Verified facts {#verified}

| claim (where) | status | evidence |
|---|---|---|
| 1,087 relative learned entities in global (22.3 #why, 16.6 #why-scale) | **confirmed (probe log)** | `global-relative-resolve-probe.log`: `entities: 1087` |
| ~700 unreadable on every global grep (bug-086) | **confirmed** | probe `exists@0: 695` |
| 476 repairable / 611 forgettable (22.3, plan table) | **confirmed, with a composition the plan contradicts** | probe `verified@1: 476`, `verified@2: 48`, `verified@0: 563`. 611 = 563 + **48 ambiguous** ([[#b-4]]) |
| "The 8 registered roots alone verify only 362" (memory) | **confirmed, and they are all `$HOME`** | probe `unique verified, by root: {'/Users/tholley': 362}`. The current producer writes global rows relative to `Path(root).parent` = `$HOME` (`cli.py:667`, `daemon.py:2136`), and `grep_evidence` reads them against `$HOME`. **Those 362 already read correctly today** |
| 5,159 evidence rows on those 1,087 entities | **not re-measured** (catalog clone denied) | the global facts.log has 65,621 relative `evidence` events, counting re-learns. Not comparable |
| 9,182 orphan aliases; 747 "empty" protected `query/*` (plan d-3, 22.1 AC-4) | **sourced, not re-measured** | exploration `#data` :83-87. **747 is "protected `query/*` with df ≤ 1"**, which is a different predicate from 22.1 R2's `empty-learned` ([[#b-6]]) |
| `evidence_line_matches` is the one verifier (22.1 R1) | **confirmed** | `store.py:759`; `verify_evidence_rows` at :816 |
| a recorded line content hash exists for `moved` (22.1 R1) | **FALSE** | `linkage_evidence` = `(entity_id, linkage_id, concept_id, file, line, span_end, detail)` (`duckdb_catalog.py:162`). 16.6 d-a's sidecar has no hash column either ([[#b-1]]) |
| "the row's recorded flags" (22.1 R1) | **FALSE for every existing row** | `_broker_learn_from_grep(root, pattern, hits)` sends no flags. `query/{pattern}` is not keyed by flags. 16.6 R5's backfill records `source` and root only ([[#b-2]]) |
| tombstones make an apply replay (plan #principles 4) | **FALSE at row level** | facts.log has entity-level `tombstone` only. `evidence` events are append-only, with no delete, update or rename op. `rmx rebuild-index` / `_op_rebuild_index` replay them ([[#b-3]]) |
| the ablation runs on `eval/production` with candidates excluded (22.2 R3) | **no such mechanism; wrong stores** | the harnesses build their own stores (`csn_code.py:100`, `run.py:239`, `grep_learning_replay.py:439`). No `exclude`/`ablat` code exists in `eval/production/` ([[#b-5]]) |
| plan-22 runs in wave 1 (plan review `#order`) | **contradicted by its own dependency** | 22.1 depends on 16.6 R1/R5. 16.6 depends on 16.1 (wave 2) and is listed in NO wave ([[#b-7]]) |
| tests do not write the live global store | **FALSE** | the global facts.log holds 143,108 events on 1,655 `pytest-of-tholley` tmp paths (`query/ERROR` 138,342, `query/alpha` 1,456), 2026-09-23 00:17 → 2026-10-07 15:12, with 0 tombstoned ([[#b-8]]) |

{#verified-body}

### Learned-row shape, measured from the project facts.log {#ev-shape}

- 49,601 `learned from grep` evidence events, 42,554 of them with a relative `file` (relative to the
  project root by design: `daemon.py:4317`).
- 1,589 `(concept, entity)` pairs. **914 (57.5%) carry more than one distinct line.**
- 29,625 distinct `(concept, entity, line)` rows. **28,950 of them (97.7%) sit in a multi-line
  pair.**
- 10,151 triples were logged more than once (19,976 extra events). That is the `duplicate`
  class's raw material, at least in the log.

{#ev-shape-body}

## Findings {#findings}

### BULLSHIT b-1: `moved` keys on a hash nobody records, and its uniqueness test fails for 97.7% of real rows {#b-1}

**Spec:** 22.1 R1 `moved`, AC-1, AC-2; 22.2 R1, AC-1; plan d-2.

**What:** `moved` = "the matching text is on EXACTLY ONE other line … and the content hash of that
line equals the recorded one".
- **No hash is recorded.** `linkage_evidence` has no hash column, and neither does 16.6 d-a's
  sidecar. Rows learned before any future column can never have one.
- **The learner writes a row for EVERY hit line** (`_learn_grep_hits`, `per_file[f].append(ln)`).
  So a file with hits at 10 and 20 that gains two lines at the top now matches at 12 and 22. Row 10
  sees two other matching lines, so it classifies `ambiguous`, not `moved`. On the project log,
  97.7% of distinct learned rows sit in such a multi-line pair ([[#ev-shape]]).
- `ambiguous` is "kept and reported", so in practice nearly every shifted row is KEPT. It is then
  re-read and re-dropped on every grep, forever. That is 16.6 `#why-gaps` defect 2, which this
  plan exists to close.

AC-2 ("a file edit that moves a matched line by N lines turns that row `moved`") passes on a
single-hit fixture and says nothing about the 97.7%.

**Why it is bullshit:** the plan's headline repair (d-2, the user's "repair them") is defined on an
input that does not exist, and on a uniqueness rule that real data almost never satisfies. Every AC
can pass while the repair does nothing.

**Fix:**
- Classify and repair per `(concept, file)` SET, not per row. Re-run the pattern over the file under
  the verification rule ([[#b-2]]), and replace the old line set with the current matching set.
  That is exactly what the learner writes today for the same pattern and file, so nothing is
  guessed. The pair is `moved` when the old and new sets have the same size. When they differ, the
  extra lines are reported (`grown`/`shrunk`), and only lines with no match left are removed.
- Drop the hash clause, or make it an optional extra that 16.6 R1 records at learn time and that
  only applies to rows that have it.
- AC: a two-hit fixture where both lines shift. Both rows must end re-pointed, with 0 `ambiguous`.
- Mutation: a per-row uniqueness rule must FAIL that AC.

**Pattern match:** YES (`#imp-existence-check-tests`: a fixture shaped to the spec, not to the
data).

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### BULLSHIT b-2: existing rows have no flags, so re-verification "under the row's recorded flags" deletes `-i`/regex knowledge {#b-2}

**Spec:** 22.1 R1 (first sentence); 22.2 R2 (`stale-line` removal); 16.6 R5.

**What:** every row in both stores predates 16.6 R1.
- `_broker_learn_from_grep(root, pattern, hits)` (`cli.py:613`) sends no flags. The context
  backstop (`cli.py:604`) learns from a context `ref`, not even a grep pattern.
- `query/{pattern}` is shared by `rmx grep -i foo`, `rmx grep foo` and `rmx grep -E 'f.o'`.
- 16.6 R5 backfills `source` and root, not flags.

So an implementer verifies these rows under the defaults (case-sensitive literal). Rows learned
under `-i` or a regex then classify `stale-line`, and 22.2 R2 removes them: knowledge lost because
of a missing column. No AC uses a pre-provenance row.

**Why it is bullshit:** this is a destructive misclassification on the bulk of the data, and the
spec reads as if the information exists.

**Fix:**
- R1: a row with no recorded flags is verified under the MOST PERMISSIVE reading: case-insensitive,
  literal OR regex, plus `identifier_variant_regex`. It is `stale-line` only if every reading fails.
- AC: a pre-provenance row whose line matches only case-insensitively must classify `ok`, not
  `stale-line`.
- Mutation: verifying under the defaults must FAIL that AC.

### BULLSHIT b-3: row-level repairs and removals have no replay form; "tombstones so it replays" is false and restore cannot be checked {#b-3}

**Spec:** plan `#principles` 4; 22.2 R1, R4, AC-3; 22.3 R3.

**What:** the facts.log replay (`_apply_event_body` at `store.py:7467` and the LWW pass at :7650)
knows `entity`, `tombstone` (entity-level, which calls `purge_entity`), `protect`, `noise`, `link`,
`unlink`, `evidence` (append-only), `track`, `untrack` and `memory_content`. There is no event for:
- deleting one evidence row (`stale-line`, `duplicate` collapse);
- changing an evidence row's `line` (`moved`);
- renaming an entity (`orphan-root` → absolute path, [[#s-3]]).

`rmx rebuild-index` (`cli.py:9755`) and the daemon op `rebuild_index` (`daemon.py:6149`) are
production paths. They would resurrect every removed evidence row, revert every re-point, and
recreate the old relative names.

**AC-3 cannot see any of this.** It compares `(linkage, concept, entity, weight)` tuples:
- evidence rows, `protected`/`noise`, sidecar rows and Lance vectors are all outside the tuple;
- a restored entity gets a new autoincrement id, so a by-id comparison FAILS on correct code, and a
  by-name comparison is never stated;
- R4's `restore` "re-inserts removed rows" and never reverts a repair. Yet AC-3 claims the result
  is the "pre-apply graph", which holds only because the tuple ignores lines.

**Why it is bullshit:** recoverability is the condition the user put on any removal
([[feedback_decay_never_loses_knowledge]]: "removal only through an explicit audited dry-run →
apply path"). The spec asserts it through a mechanism that does not exist at row level, and through
an AC that cannot fail on the gap.

**Fix:**
- New log ops (`evidence_remove`, `evidence_repoint`, `entity_rename`), applied in BOTH replay
  paths.
- AC: `--apply` then `rebuild_index_from_log` gives the post-apply state, evidence rows included.
- Restore compares by NAME and covers the evidence rows (`file`, `line`, `detail`), the flags, the
  sidecar and the vector presence. It also REVERTS repairs.
- Mutation: an apply that skips the log events must FAIL.

### BULLSHIT b-4: bug-086's 611 contains the 48 ambiguous rows the plan swears to keep, and "candidate root" is undefined {#b-4}

**Spec:** plan `#principles` 3, table row 22.3; 22.1 R1 `orphan-root`; 22.2 R2 ("`ambiguous` is
never removed"); 22.3 #why, R1, AC-1.

**What:**
- **The 48.** The probe splits 611 into 563 with no verifying file and 48 that verify under two
  roots, i.e. `ambiguous`. 22.3 removes 611. 22.2 R2 and principle 3 keep all 48. Implemented as
  written, 22.3's dry run reports 563, not 611, and its AC ("matches the catalog copy") cannot say
  which number is right.
- **The candidate set.** 22.1 says "where exactly one candidate root makes it verify" and never
  names the candidates. With the registered roots as candidates, all 362 unique hits are `$HOME`,
  and those rows ALREADY read correctly today. The repair would fix 0 of the ~700 unreadable rows
  and remove 725. The decided 476 exists only under the probe's suffix walk over `~/github`,
  `~/claude_tools` and `~/enduris` (972,849 files), which the spec does not name. The walk's
  exclusions are not named either: does it skip the `~/refmatrix` deploy tree, `.venv*`, worktrees
  and `node_modules`?
- **Units.** The probe and 22.3 count ENTITIES. 22.1's classes are per evidence ROW. The spec has no
  rule for an entity whose rows split.

**Why it is bullshit:** this is a destructive apply whose expected count contradicts the plan's own
principle, and whose most natural implementation deletes 114 more entities than the user approved
while fixing none of the symptom.

**Fix:**
- The user rules on the 48 ([[#decisions]]).
- 22.1 R1 names the candidate-root procedure exactly (the probe's suffix walk, its roots and its
  exclusions) and states the entity rule (an entity is repairable iff ALL its rows verify under one
  root).
- 22.3 AC: the dry run reproduces the probe's 476 / 48 / 563 split on the copy, ± the drift
  explained.

**Pattern match:** YES (`#imp-cap-in-the-wrong-unit`).

### BULLSHIT b-5: the ablation gate runs on stores the candidates are not in, so it can never refuse {#b-5}

**Spec:** 22.2 R3, AC-4; plan d-3.

**What:** "The apply first runs the production eval path (`eval/production`: MemAware, CSN,
cliquedb) with the candidates excluded."
- Those harnesses ingest their own datasets into their own stores (`csn_code.py:100`, `run.py:239`).
  The candidates are rows of THIS store (partition `refmatrix`) or the global store.
- Grep-learned `query/*` rows never exist in an eval store. Excluding them there changes nothing,
  by construction.
- Orphan aliases may exist in eval stores, but they are different rows. Recomputing the predicate
  there is a proxy, and the spec does not say so.
- No exclusion flag exists (`exclude`/`ablat` has no hits in `eval/production/`), and "beyond
  noise" has no definition.

AC-4 uses "a fixture eval where removing a candidate changes hit@k", so it passes while the real
gate is vacuous.

**Why it is bullshit:** the gate is the condition d-3 places on the 9,182 + 747 culls, and it
cannot fail for them.

**Fix:**
- Gate on THIS store's own retrieval: a frozen query set replayed from its `query.log` (or 16.10's
  frozen NL set), the paired per-query delta with the candidates masked at read time, and the noise
  defined (for example, a paired bootstrap 95% CI excluding 0).
- Or state the proxy explicitly (the predicate recomputed per eval store) and justify it.
- AC: a mutation that runs the gate on a store without the candidates must FAIL.

**Pattern match:** YES (`#imp-harness-env-decides`, memory `feedback_measure_the_path_users_run`).

### BULLSHIT b-6: "`empty-learned` ≤ 747" counts a different predicate and passes at 0 {#b-6}

**Spec:** 22.1 R2 `empty-learned`, AC-4; plan d-3; plan #why ("a df≤1 `query/*` row with one valid
evidence row classifies `ok`").

**What:**
- The 747 is "protected `query/*` with **df ≤ 1**" (exploration `#data` :83), i.e. "nearly empty".
  22.1 defines `empty-learned` as "all learned evidence non-`ok`", which is a different set. "≤ 747"
  is satisfied by 0.
- C1's actual point was the df≤1 row WITH a valid evidence row, which 16.6's classes could not
  express. It is still unexpressed. The plan's #why quotes it as the reason for the new class, and
  the new class then defines it away.
- Culling verified knowledge by df is removal on a counter threshold, which the user's rule forbids
  ("never from a counter threshold").

**Why it is bullshit:** a renamed number with an upper-bound AC that cannot fail. It hides that C1's
class was dropped.

**Fix:**
- Remove "747" from d-3 and AC-4. Measure and report the defined predicate's count on the copy.
- State in #why that df≤1-with-a-valid-row is NOT a cull class under
  [[feedback_decay_never_loses_knowledge]], or put it to the user ([[#decisions]]).

### BULLSHIT b-7: plan-22 is wave 1, but its first task depends on 16.6, which no wave schedules; bug-086 is deferred behind it {#b-7}

**Spec:** 22.1 "Depends on: 16.6 R1/R5"; plan-review `#order` (wave 1: "the C1/C2 removal engine,
with bug-086 its first apply"; wave 2: "16.1 → 16.2 ∥ 16.3 → 16.5"); 16.6 "Depends on: 16.1".

**What:** 16.6 appears in no wave. It depends on 16.1 (wave 2), which sits behind plan-16's
revision-5 review loop. So 22.1 → 22.2 → 22.3 cannot start in wave 1. bug-086 was decided on
2026-10-07 to run "after the remedy deploys" (that deploy has happened: 0.77.x). It is now parked
behind a task with no slot.

**Why it is bullshit:** this is rule 9a. A decided repair is deferred to work that is not
scheduled. And the bug-086 slice does not need provenance: `orphan-root`, `missing-file` and
`duplicate` are decidable without 16.6 (the probe did it).

**Fix:**
- Split the dependency. 22.1's provenance-free classes (`orphan-root`, `missing-file`,
  `duplicate`, `orphan-alias`) and 22.3 run in wave 1, after plan-23.
- The flag-sensitive classes (`ok`/`moved`/`stale-line`/`out-of-range` under [[#b-2]]'s rule)
  wait for 16.6.
- Give 16.6 an explicit wave in `plan-review-2026-10-07` / `plan-of-plans`.

### BULLSHIT b-8: the suite already writes learned rows into the LIVE global store, and the removal specs carry no sandbox clause {#b-8}

**Spec:** 22.1-22.3 (no isolation clause); 22.3 scope (relative rows only); bug-088.

**What:** the global facts.log records 143,108 events on 1,655 entities whose paths are
`/private/var/folders/…/pytest-of-tholley/pytest-N/<test>/…`.
- Concepts: `query/ERROR` 138,342 and `query/alpha` 1,456.
- Tmp dirs: `test_explicit_file_paths_are_n…` 68,911; `test_a_truncated_result_set_sa…` 68,408;
  `test_count_across_two_files_ke…` 728; and others. These match `tests/test_grep_dropin_contract.py`
  and `tests/test_grep_output_shape.py`, which patch `daemon.ping` but not `_root()`.
- Span: 2026-09-23 00:17 → 2026-10-07 15:12. **0 tombstoned.**

bug-088 records only READS (6 federated reads, 66 `models.sock`) and one dry run. This is the WRITE
class, unlogged. Nothing has written the global log since 2026-10-07 15:12, so whether the leak is
still live is unverified.

Consequences for plan-22:
1. A removal-engine test with the same leak would DELETE from global.
2. 22.3 covers only the relative rows. These 1,655 absolute, missing-file, protected entities stay,
   and keep producing `unreadable` on global `ERROR`/`alpha` greps. "bug-086 fixed" would then be
   declared over a store that still shows the symptom.

**Why it is bullshit:** the destructive member of the plan family has the leak history most likely
to cost data, and its specs never mention it.

**Fix:**
- Log the write sighting now (bug-088, 3rd sighting, write class; or a new row).
- Each 22.x spec states the sandbox:
  - in-process `Daemon` + `Store` on a short `mkdtemp`;
  - `_root` patched and `REFMATRIX_ROOT`/`HOME` set;
  - no `rmx` subprocess;
  - the recorder count unchanged.
- The apply op refuses a root that is not the one named explicitly on the command line.
- 22.3 removes the pytest-tmp `missing-file` rows in the same audited apply, and its AC measures
  global `unreadable` TOTAL, not "for those rows" ([[#s-7]]).

**Pattern match:** YES (memory `project_suite_reaches_live_sockets`; plan-23 review `#s-7`).

### SKETCHY s-1: the apply yields between batches with no partition rule (bug-098, destructive variant) {#s-1}

**Spec:** 22.2 R5; 22.3 (partition `global`); plan `#principles` 6.

Plan-23's drain releases the writer between batches. The concurrent plan-23 review's `#b-1` shows
how the shared mutable binding re-creates bug-098 at every release. Plan-22 is the one consumer for
which that means deleting or re-pointing rows in the WRONG partition (project stores carry
`<project>` and `sessions-<project>`).

**Fix:** each batch binds its partition inside its own hold, through plan-23's `bind(batch)` seam.
Add a plan-22 AC: two partitions, a competitor binds the other partition between batches, and 0
rows of the other partition change.

### SKETCHY s-2: an apply is not queue-shaped; overflow, crash and staleness all break the manifest {#s-2}

**Spec:** 22.2 R4, R5; 22.3 R1-R3; memory `project_global_relative_rows_repair` `#how`.

**What:** plan-23's queue coalesces by key and caps with a counted OVERFLOW. A dropped repair is
silent loss inside an "audited" apply. The plan-23 review covers the rest:
- `#b-2`: exactly-once fails with a marker outside the transaction, so a crash leaves the manifest
  and the store disagreeing;
- `#b-3`: there is no finalize step, so "one Lance delete per kind" becomes one per batch.

22.2 also applies the `--json` plan from an earlier audit, which may have run on a copy. The memory
says the apply must "re-check each id is still relative" and "re-run the probe immediately before
applying"; the spec says neither.

**Fix:**
- The apply is a bounded step loop over an in-memory plan (plan-23 `#s-3`'s non-queue shape).
- The manifest is an intent log written BEFORE each batch, with a commit marker after it; restore
  handles a partial apply.
- Each row is re-classified inside its batch hold, and a row whose class changed is skipped and
  counted.
- One post-loop Lance finalize per kind.

### SKETCHY s-3: "rewrite to the absolute path" is an entity rename that collides, has no API, and writes code entities into the memory-only store {#s-3}

**Spec:** 22.2 R1 (`orphan-root`), 22.3 R3.

**What:**
- Entities are `UNIQUE(partition, kind, name)`. A relative entity rewritten to an absolute name
  collides with any existing absolute entity for the same file. The global log shows 1,682
  absolute learned entities, 1,655 of them pytest tmp paths ([[#b-8]]), so few collisions today.
  But the rule must exist, because project-store repairs will hit it. The spec needs MERGE
  semantics.
- There is no rename API, and no rename log event ([[#b-3]]).
- The global store is memory-only by design (`is_memory_only_root`, c62f4d7). It has twice been
  drained of foreign code paths (memories `project_global_memory_only_guard_shipped` and
  `project_global_store_foreign_tree_recurrence`: "code paths in global = untrack, never sync").
  Repairing 476 code/doc entities INTO it re-creates that class through a sanctioned path.

**Fix:**
- Specify merge-on-collision.
- The user re-confirms the target ([[#decisions]]): rewrite in global; MOVE into the owning project
  store (the store whose root contains the resolved path, through its daemon); or forget.

### SKETCHY s-4: "only learned protection changes" cannot be computed {#s-4}

**Spec:** 22.2 R6; plan `#principles` 5.

The learner's protection (`upsert_entity(protected=True)` → `protect` event, `store.py:2183`) and a
user's `rmx protect` (`set_flag_by_selector`) write identical events with no source. 16.6's sidecar
records EVIDENCE provenance, not protection provenance.

**Fix:**
- Never unprotect an entity that is ingested or has any non-learned link, or record a protection
  source in the sidecar.
- AC: a user-protected entity that also carries learned rows stays protected after the apply.

### SKETCHY s-5: the `orphan-alias` repair looks up the wrong column and can re-link to a different concept {#s-5}

**Spec:** 22.2 R1 ("whose canonical can be found by `canonical_name`").

**What:**
- `canonical_name` is `canonicalize_name()`: lowercased, with camelCase and `_-` folded
  (`store.py:36`). `Foo_Bar`, `foo_bar` and `FooBar` all share one value. Those are exactly the
  exploration's traps (`Store` vs "store").
- The alias row already names its canonical: `_bulk_add_concepts` writes the description
  `alias of '<canonical>'` (`ingest.py`).
- If that canonical was pruned or marked noise (likely, since `phrase/*` expansion minted aliases
  and the 28,285 noise rows are all `phrase/*`), "restoring" the edge re-links to noise, or
  recreates a pruned concept.

**Fix:**
- Repair only through the description's exact name, and only when that canonical exists and is not
  noise.
- Otherwise the row is a removal candidate.
- AC: a case-variant canonical must not be chosen.

### SKETCHY s-6: no removal primitive is specified, and the only existing one destroys ingest-owned state {#s-6}

**Spec:** 22.2 R2, R6.

**What:**
- `linkage_evidence` has no primary key.
- The only removal primitive, `_bulk_purge_ids` (`store.py:6032`), is ENTITY-level. It deletes
  `tracked_files` and ALL `entity_links` of the id, ingest links included. Reusing it for a
  `missing-file` row on a shared learned+ingested file entity violates R6.
- 16.6 d-a keys the sidecar by `evidence_rowid`. DuckDB documents no stable `rowid` identity, and
  `replica_merge` rewrites the table ("UNION DISTINCT with remap").

**Fix:**
- Define row identity as `(linkage, concept, entity, file, line)` and spec the DELETE/UPDATE.
- Entity purge happens only when the entity has no remaining link of any kind.
- AC: the ingest links and the `tracked_files` row of a shared entity are unchanged.

### SKETCHY s-7: 22.3's verification is scoped so it cannot fail on the bug's symptom {#s-7}

**Spec:** 22.3 R4, AC-2; plan table row 22.3.

"0 unreadable **for those rows**" measures only the rows the apply touched. bug-086's symptom is the
global grep's `unreadable` count. That count also comes from:
- the 48 kept ambiguous rows;
- the 1,655 pytest rows ([[#b-8]]);
- the 362 `$HOME`-relative rows, which read fine and should not change.

**Fix:** measure the total global `unreadable` count for a fixed pattern set before and after, and
explain every residual row by class.

### MEH m-1: AC-4's numbers cannot fail {#m-1}

22.1 AC-4: "class counts are reported" (cannot fail); "≈ 9,182" (no tolerance, and the store has
drifted since the exploration's copy); "covers the 1,087" (≥). Give a tolerance and a
recompute-on-the-copy rule.

### MEH m-2: "read-only" is undefined on a store with a draining queue {#m-2}

22.1 R3 / AC-3 says "catalog hash unchanged", but R3 allows queued marks, and the daemon tick drains
them into the catalog. Name the read surface (replica vs daemon op), and pause or exclude the drain
in the AC.

### MEH m-3: plan-16's task table still says 16.6 prunes every non-`ok` class {#m-3}

`plan-16-invisible-grep-shim.md:138`: "`rmx learn prune` … removes every non-`ok` class". That
contradicts 16.6's move to plan-22 and amended d-c. Left for the revision-5 agent; not edited.

### MEH m-4: the global facts.log is not a faithful recovery source {#m-4}

The global facts.log names 2,997 relative learned entities and tombstones none. The probe saw 1,087
in the catalog. The difference is unexplained, and a `rebuild-index` of global would not reproduce
the catalog. So the manifest, not the log, must be plan-22's recovery mechanism, and `restore` must
not depend on replay.

### MEH m-5: 22.4 blocks on a plan that does not exist, and plan-22's close is undefined {#m-5}

The ADR-0004 helix plan is listed under "No plan yet" (`plan-review-2026-10-07` `#gaps`). Say
whether plan-22 can reach `completed` with 22.4 handed to the helix plan, or stays open until
wave 5.

### MEH m-6: command and verb surface undecided {#m-6}

- The spec says "`rmx learn audit` / `rmx audit`". `rmx learn` exists (status/on/off). There is no
  `rmx audit` group; `audit-same-as` is a top-level command. Concept classes do not belong under
  `learn`.
- `rmx removal restore` is a new group.
- No verb is named. No removal verb exists today (28 verbs). State whether audit is a verb and the
  apply is CLI-only on purpose.

### MEH m-7: "one removal path" is scoped, but the ADR says "only" {#m-7}

`forget`, `prune-noise --drop` (a df threshold), `vacuum`, `memory bulk-forget` and `untrack` all
remain. Plan-22 d-1 scopes "one path" to learned rows, free culls, bug-086 and merges. ADR-0004
`#rule-no-delete` reads "Removal goes only through the ONE explicit, audited path". Align the
wording.

{#findings-body}

## Option A (storage exploration): fold into plan-22? {#option-a}

**Recommendation: do NOT fold Option A into plan-22. Consume plan-23's `bind` seam, and add the
destructive AC from [[#s-1]].**
- Option A is a ~7k-line refactor of every `_partition_id` read. Its deciding measurement (#4,
  concurrency and ART risk) has not run, and the exploration is "In progress … nothing measured
  yet". Folding it would put the bug-086 repair, which is already decided, behind an unmeasured
  refactor.
- The overlap is narrow and is exactly the bug-098 surface: an apply that yields between batches
  while a mutable binding is shared. Plan-23's review recommends a `bind(batch) -> handle` seam.
  Plan-22's apply should be written against that handle, so that under A it becomes a per-op cursor
  with no change to plan-22's code.
- "A first … absorbs parts of plans 22 and 23" conflicts with the wave order. The plan-23 review
  already puts that to the user. For plan-22 the answer can be the same: A's seam yes, A's refactor
  no.

{#option-a-body}

## User decisions needed {#decisions}

1. **The 48 ambiguous global entities** ([[#b-4]]): keep them, as principle 3 and 22.2 R2 say, or
   forget them, as the 2026-10-07 "611" decision implied?
2. **Where the 476 go** ([[#s-3]]): rewrite them to absolute paths INSIDE the memory-only global
   store; move them into the owning project's store; or forget them?
3. **df≤1 `query/*` rows with a valid evidence row** ([[#b-6]]): confirm they are NOT a cull class
   (the decay rule), or authorize an ablation-gated cull?
4. **Sequencing** ([[#b-7]]): split 22.3 and the provenance-free classes into wave 1 without 16.6,
   and give 16.6 a wave?
5. **The 1,655 pytest-tmp rows in global** ([[#b-8]]): log the write sighting and remove them under
   22.3's audited apply?
6. **Verb exposure** ([[#m-6]]): should the audit be an MCP verb, with the apply CLI-only?

{#decisions-body}

## Verdict {#verdict}

**NEEDS-REVISION.** 22 findings: 8 BULLSHIT (b-1 … b-8), 7 SKETCHY (s-1 … s-7), 7 MEH (m-1 …
m-7).

The plan's direction is right: one audited path, repair before removal, ambiguous kept, a manifest
and a restore. The specs still assume three things the code does not have:
- a line hash;
- recorded flags;
- row-level replay events.

On top of that, `moved` per row is unsatisfiable on 97.7% of real rows, the gate measures the wrong
stores, and the first apply's count contradicts its own principle.

{#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

| 3104a81 (plan-22 spec review r1, pre-implementation; HEAD 03bd532 handoff-only; written 2026-10-14T11:13:20-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 22 (8B/7S/7M) | [[bsd-plan22-spec-review-3104a81]] — `moved` keyed on an unrecorded hash, per-row uniqueness fails 97.7% of real rows; no flags on existing rows; no row-level replay events; gate on eval stores without the candidates; 611 includes 48 ambiguous; 16.6 unscheduled; 1,655 pytest rows written into live global |

last_run.log line:

`2026-10-14T11:13:20-0700 commit=3104a81 verdict=DIRTY findings=22 (8B/7S/7M) report=2026-10-14-1113-plan22-spec-review-moved-has-no-key-and-repairs-do-not-replay-3104a81.md`

IMPRESSIONS.md bullets:

- **The repair that never fires** {#imp-repair-on-a-uniqueness-the-data-lacks}: a repair class
  defined per row ("exactly one other line") on data the producer writes per SET (the learner writes
  every hit line) classifies almost everything as the safe fallback. The AC fixture has one hit per
  file. Measure the producer's shape before accepting a per-row class.
- **The recovery primitive is assumed** {#imp-recovery-primitive-assumed}: "tombstones so it
  replays" and "restore" were asserted for row-level edits on a log that has only entity-level
  tombstones. Check the replay op list before believing any recoverability claim.
- **Logs carry what the catalogs hide** {#imp-the-log-names-the-leak}: the global facts.log named
  1,655 pytest tmp entities written into the live store, which bug-088's read-only recorder never
  saw. When a store is off-limits, parse its log.
