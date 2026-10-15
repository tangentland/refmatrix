---
gmd: "0.1"
id: bsd-plan16-22-spec-diffcheck-r10-451b505
title: "plan-16 + plan-22 spec diff check r10: round 9 (451b505) closes 7 of the 8 r9 findings. 16.6 R1f's deletion list is complete and AC-12 can fail. r9 s-1's prescription was wrong: names_from_log cannot name a both-dead orphan's concept, so 22.6 AC-6c(a) cannot pass. The dead-at-T rule misses re-creation before the vacuum. The FOLD_OPS rows do not say how each new op is folded."
severity: SKETCHY
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-diffcheck-r10-16.3-16.6-22.2-22.6
round: 14 (plan-16) / 10 (plan-22)
tags: [bsd, audit, spec-review, diff-check, removal, replay, vacuum, orphan-drop, d9bu, d9bk, fold-ops, bug-118, bug-120]
---

# ch-bsd r10 diff check: plans 16 and 22 after revision round 9 (`451b505`) {#root}

**Commit reviewed:**
- The round-9 revision is `451b505` on `wave0-spec-reviews`. I diffed it against `29e335a` for `workflow/plans/plan-16-*` and `plan-22-*`.
- HEAD moved to `c8ff69d` during the run. That commit only adds ledgers: no file of plan-16, plan-22, task 17.4 or `src/` changed.
- `src/` is unchanged since `23ad703`.

**Written:** 2026-10-15T04:08-0700.

**Method (read-only):**
- I checked every r9 finding against the text at HEAD.
- I swept `src/`, `tests/`, `scripts/`, `eval/`, `docs/` and `.claude/hooks/` at HEAD for each name 16.6 R1f deletes.
- I read the bug-118 branch at `462bd0b` (`/Volumes/littlebig/refmatrix-bugs112-118`; its tree is clean).
- I read these anchors: 22.1a `#r1-dangling`, `#r1-covering`; 22.2 `#r9-dangling`; 17.4 `#r6-restore`.
- New probes are in `scratchpad/r10/`, run with the DEPLOY interpreter (`~/refmatrix/.venv/bin/python -I`, Python 3.14.5, DuckDB 1.5.3) on scratch copies:
  - `facts.log` copies taken at 04:01: refmatrix 350 MB, cliquedb 202 MB;
  - the r6 cliquedb catalog copy;
  - the 00:25 refmatrix catalog+log pair.
  - DuckDB was opened `read_only`.
- The probes:
  - `scan.py`: the cost of the vacuum's log scan;
  - `bothdead.py`, `liveend.py`, `revive.py`: whether a both-dead orphan can be named;
  - `reborn_e.py`, `excess.py`: the dead-at-T rule against today's orphans.
- GMD lint on the 15 plan-16/22 files: 0 errors.

**Severity scale:** SKETCHY is this ledger's word for SUSPICIOUS.

**Nothing changed:** no store or socket was opened, no spec or source was edited, and nothing was committed.

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-both-dead]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-timeline]]

## Round-9 findings: status {#prior-status}

| r9 id | status | evidence at HEAD |
|---|---|---|
| s-1 (both-dead orphan has no name) | **answered, but the prescription was MINE and it is wrong** | 22.6 `#r5-both-dead` routes both-dead orphans through 22.1a `names_from_log`, as my r9 fix text said. That function cannot name them ([[#s-1]]). Reopened as r10 s-1. |
| s-2 (uncalled incremental path) | **closed** | <ul><li>16.6 [[task-16.6-learned-row-validation#r1f]] deletes the path, and AC-12 checks it.</li><li>Every clause that extended the path is gone from 16.6 R1d / AC-9 / AC-9d, 22.2 R3 / AC-3f, and 22.6 `#r5-timeline`.</li><li>bug-120's Planned cell now names d9bu + 16.6. That is a real owner, so the row is no longer an unanchored deferral.</li><li>[[#r1f-verify]] has the details.</li></ul> |
| m-1 (live kinds in `_row_op_c_kinds`) | **closed** | <ul><li>The constant `LEGACY_PREFERRED_KIND` replaces the legacy rule.</li><li>AC-3f run 3 is added, with the mutation "the helper reads LIVE kinds through the legacy rule".</li><li>I traced run 3: the legacy append resolves to `concept` (it is logged). The re-created concept materializes the copy, and the `(concept, keep 0)` op at `T` deletes it. The copy then equals live.</li><li>Residue: [[#m-2]].</li></ul> |
| m-2 (`keep = n`) | **closed** | <ul><li>The helper returns `(c_kind, keep)` pairs; `n` is 0 or 1, and `n >= 2` is counted `legacy_misresolved`.</li><li>AC-3f run 2 and its two-copy variant are present, with the mutation "`keep: 0`".</li><li>`linkage_evidence` has no uniqueness key (`store.py:396`), so copies really multiply and `keep` is meaningful.</li></ul> |
| m-3 (16.3 vs bug-118) | **closed** | <ul><li>On `462bd0b`, `_add_enforce_entries` renders `("enforce-test-to-file.sh", "enforce-rmx-grep.sh")` through `_optional_project_hook` (`hooks.py:395-397`). Removing one name from that tuple is the whole change, as R5 says.</li><li>The test's `SCRIPTS` (`:26`) edit is listed.</li><li>The prose sweep matches every hit in `src/` and `.claude/hooks/` ([[#hook-hits]]).</li><li>AC-10's note is rewritten.</li><li>The "no `rmx learn on` in any scope" line is in `#learn-flip`. The global `learn.off` marker is present (00:29), and there is no project marker.</li><li>Residue: [[#m-4]].</li></ul> |
| m-4 (partition field) | **closed in the text** | 22.6 R5 "The partition field" and the AC-6b partition variant are present. The scan's lookup key and load shape are unnamed ([[#m-1]]). |
| m-5 (AC-9d mis-fires) | **closed** | Check 3 is scoped to the link and row passes, and the memory-body test is allowed by name. Check 4 takes its values from `row_key`. |
| m-6 (registry wording) | **closed** | bug-121 reads "10 covering names (21 store-wide)". |

**Totals:** 7 of 8 closed. r9 s-1's answer follows my prescription, and the prescription does not work.

## Verified facts {#facts}

### 16.6 R1f's deletion list against HEAD {#r1f-verify}

**Is anything else using the deleted names?** No. Each has no caller or reader outside the chain itself:

| name | every hit at HEAD (`src/ tests/ scripts/ eval/ docs/ .claude/hooks/`) |
|---|---|
| `apply_log_delta` | its `def` (`store.py:7696`); the `daemon.py:516` comment; `tests/test_bug117_rebuild_non_concept.py:112,121` (the one test R1f deletes); the `tests/test_memory_content_log.py:7` docstring |
| `_apply_one_event` | its `def` (`:7765`); its one call (`:7755`, inside `apply_log_delta`); the `add_memory` comment (`:2531`) |
| `_apply_event_body` | its `def` (`:7792`); its two calls (`:7772-7773`, inside `_apply_one_event`); the test docstring (`:112`) |
| `_replay_concept` | its `def` (`:7775`); three calls (`:7842,7849,7856`), all inside `_apply_event_body` |
| `REPLICA_REBUILD_DELTA_BYTES` / `RMX_REPLICA_REBUILD_DELTA_BYTES` | the definition (`daemon.py:522-523`) and nothing else, including `~/Library/LaunchAgents/*.plist` and the shell env |

**What survives the deletion:**
- `_replay_mode` is also set by `rebuild_index_from_log` (`:8082`, `:8184`) and read by eight loggers, so it stays live.
- The `resolve_legacy_kind` import is still used by Pass 2b (`:8045`, `:8061`).
- Every Store method `_apply_event_body` calls (`upsert_entity`, `add_linkage_type`, `mark_tracked`, `add_memory`, `with_partition`, `purge_entity`, `link`/`unlink`/`add_evidence`) has production callers elsewhere.
- So the deletion orphans nothing.

**Coverage check:**
- R1f's list (four methods, the constant and its env var, the test, the `add_memory` comment, the module docstring) covers every hit.
- d9bu named only the first three methods. The reviser's additions (`_replay_concept`, the constant, the test, the comments) are each confirmed to have no other caller.

**AC-12 can fail:**
- The text scan over `src/` catches the comment mutation and any surviving `def`.
- The AST scan over `tests/` catches `dst.apply_log_delta`.
- The fixture-tree self-check proves the scan is not vacuous.
- Residue: [[#m-3]].

### `LEGACY_PREFERRED_KIND` rename {#rename}

- `_LEGACY_PREFERRED_KIND` is referenced only at `edge_records.py:33,57,58`. No test and no other module names it.
- Making it public breaks nothing.
- The helper's `(c_kind, keep)` contract and AC-9d check 2's caller list ("Pass 2b and the row pass", `_row_op_c_kinds` reading the constant) are consistent with each other.

### 16.3 R5 against bug-118's renderer {#hook-hits}

**Every `enforce-rmx-grep` hit and where R5 covers it:**

| hit | where R5 covers it |
|---|---|
| `hooks.env:10`, `hooks.env.example:11` | prose sweep |
| `cli.py:9321` | `install-hooks --help` |
| `hooks.py:94` | docstring |
| `hooks.py:374` (branch) | `_optional_project_hook`'s docstring |
| `hooks.py:396` (branch) | the tuple |
| `hooks.py:1158` / `:1166` (branch) | `_RMX_HOOK_SIGNATURES`, the one allowed hit |
| `telemetry.py:192` | docstring |

No `src/refmatrix/templates/` file names the script, so AC-7's scan (`src/refmatrix/` + `.claude/hooks/`, one allowed hit) is achievable.

### The vacuum's `facts.log` scan, measured (22.6 R5) {#scan-cost}

**What the probe does.** `scan.py` mirrors the minimal production shape:
1. It loads the step-3 orphans read-only.
2. It streams `facts.log` once, with a substring prefilter for `"op": "evidence"` (every writer uses `json.dumps(sort_keys=True)` with default separators, `store.py:1131,1149`).
3. It runs `json.loads` on hits only, and does a set lookup on `(linkage, file, line, detail)`.

**Results, deploy interpreter:**

| store | log | lines | evidence events | orphan rows / keys | scan wall | total wall | peak RSS |
|---|---|---|---|---|---|---|---|
| cliquedb | 192 MiB | 983,678 | 66,100 | 7,599 / 4,404 | 0.4 s | 0.5 s | 107 MiB |
| refmatrix (00:25 log) | 253 MiB | 1,181,474 | 253,023 | 834,201 / 66,239 | 1.0 s | 2.1 s | 1,020 MiB |
| refmatrix (04:01 log) | 334 MiB | 1,524,838 | 271,352 | 834,201 / 66,239 | 1.1 s | 2.2 s | 1,026 MiB |

**Verdict:**
- **Bounded:** it is linear in the log. The compactor caps the log near 256 MiB plus growth between its 1,800 s checks.
- **Streaming:** line iteration; the hit dict is bounded by matched appends.
- **Acceptable inside `_op_vacuum`'s `d._store_lock` hold:** about 1 s per pass.

**The memory caveat.** The 1 GiB peak is not the scan. It is loading 834k orphan ROWS as Python tuples. Loading only the distinct keys (`GROUP BY` over the same join) takes 0.07 s and peaks at 371 MiB in the whole process, DuckDB included (`keyload.log`). The vacuum docstring itself records a jetsam kill mid-vacuum, so the spec should name the key-only load ([[#m-1]]).

**What the scan finds today:**
- cliquedb: 2,221 of 4,404 orphan keys have a matching append; 4,057 orphan rows have none.
- refmatrix: 4,216 of 66,239 keys have one; 765,682 rows have none.
- Every hit key carries 1 to 3 distinct partition fields.

## New findings {#findings}

### SKETCHY s-1: `names_from_log` cannot name a both-dead orphan's concept, so 22.6 AC-6c(a) cannot pass, and the rows it misses are the ones a rebuild resurrects {#s-1}

**The spec.** 22.6 [[task-22.6-removal-entry-points#r5-both-dead]]:
> It is named by 22.1a's dead-id naming … the same `names_from_log` 22.2 R9 uses, never a second naming.

r9 s-1 prescribed this. That prescription was wrong.

**Why `names_from_log` cannot do it.** It is defined at [[task-22.1a-provenance-free-classes#r1-dangling]], and 22.2 [[task-22.2-repair-then-remove#r9-dangling]] restates it. A key qualifies only if:
- (i) it has an `entity` event and **no tombstone at or after its latest one**;
- (ii) it has no catalog row;
- (iii) it covers EVERY row of `D` **whose other end is alive**.

`unnamed:reborn` also requires a key "that covers one of `D`'s live-end rows". It was built for bug-111's raw deletes (alive in the log, gone from the catalog), not for purged concepts.

**Problem 1: AC-6c(a)'s own fixture fails clause (i).** Its concept is "a DOC `N` whose `entity` event is in `facts.log`, then tombstoned, so 22.1a names it". A tombstoned key fails (i), so `N` is `unnamed:none` and no event is logged. The copy step then re-creates `N` and the entity end, and the rebuild materializes the old append: the copy holds the row and live does not. So the AC fails against the rule it cites. An implementer will either use a second naming (which the spec forbids) or bend the AC.

**Problem 2: most both-dead concept ids have no live-end row** (`liveend.py`):

| store | dead concept ids of both-dead orphans | with no live-end row (vacuous (iii), no reborn label) |
|---|---|---|
| cliquedb | 2,401 | 1,536 |
| refmatrix | 1,403 | 616 |

22.2 R9's own measurement agrees: **0** of cliquedb's 4,778 evidence-side dead concept ids are NAMED.

**Problem 3: the premise of "nameless logs no event" is false here.** The premise is "no logged name lets a rebuild re-attach the row". That holds for 22.2 R9's dangling rows. It does not hold for a vacuum orphan, because the orphan's OWN `evidence` append names both ends by name.

`revive.py` counts both-dead orphan rows whose matching appends name a concept key AND an entity key that both hold a catalog row now, so a rebuild materializes them:

| store | such rows | of which the dead concept id has no live-end row (so `names_from_log` returns nameless) |
|---|---|---|
| cliquedb | 3,333 | 1,893 |
| refmatrix | 1,099 | 616 |

(How many of these copies exceed what live holds is [[#s-2]]'s question; today the excess is small. Both this finding and the AC-6c contradiction stand regardless.)

**Fix (22.6 R5, replacing both bullets of "The concept end is keyed by exactly one of two rules"):**
> **One keying rule for every orphan, live or dead concept: the orphan's own appends.** The vacuum's one log scan ([[#m-1]]) collects, per orphan key `(linkage, file, line, detail)`, the `evidence` appends that match it and pass [[#s-2]]'s revivable predicate. Each drop is keyed on one distinct `(partition field, c_kind, c)` among them. `c_kind` is the append's own, or for a legacy append `edge_records.resolve_c_kind(None, c, p, kinds_by_name)` over the kinds LOGGED for `c` in `p` (the same scan collects the `entity` events' kinds, exactly Pass 2b's `kinds_by_name`). That is the key a rebuild holds the copy under, by construction.
>
> - Neither `names_from_log` nor `_row_op_c_kinds` is used by `vacuum`. (That also removes the undefined `n` of an orphan whose entity end has no name; see [[#m-2]].)
> - A legacy append the rule resolves to None is counted `orphan_drop_unresolved` and logs nothing.
> - An orphan key with no revivable append is counted `orphan_drop_unlogged` and logs nothing.
> - `orphan_drop_nameless` is retired.

**Also update:**
- 16.6 AC-9d check 2: add the vacuum scan to the `resolve_c_kind` callers.
- d-30: re-word it to match.

**AC-6c rewrite:**
- **(a)** Tombstoned doc `N`: exactly one drop, keyed `(doc, N)` from its own append. The copy step (re-create `N` and the entity end, then rebuild) holds no row.
- **(b)** `Z`, written with logging off: `orphan_drop_unlogged: 1`.
- **(c)** A LEGACY append whose name has two non-concept kinds logged: `orphan_drop_unresolved: 1`.
- **Mutations:**
  - "name a both-dead concept through `names_from_log`" FAILS (a): no event, and the copy revives;
  - "key the drop on the catalog kind" FAILS a variant where concept `N` is also logged and the append is legacy;
  - "skip without a count" FAILS (b) and (c).

rel: contradicts -> [[task-22.6-removal-entry-points#r5-both-dead]]
rel: contradicts -> [[bsd-plan16-22-spec-diffcheck-r9-29e335a#s-1]]

### SKETCHY s-2: the dead-at-`T` rule misses re-creation BEFORE the vacuum, and today it would turn every logged drop into `orphan_drop_skipped_live` noise {#s-2}

**The spec.** 22.6 [[task-22.6-removal-entry-points#r5-timeline]] (d-28, d9bk): a copy is dropped iff its entity key is DEAD at `T`, meaning its latest tombstone at or before `T` is at or after its latest `entity` event at or before `T`.

**Case 1: re-creation before the vacuum.** AC-6b orders vacuum (T2) before re-creation (T3). The everyday order is the reverse:
1. `purge_path(D)` tombstones `D`;
2. the file comes back (a branch switch) and is re-ingested, re-creating `D` and appending the identical row;
3. the nightly `vacuum` deletes the old incarnation's orphan.

At `T`, `D`'s key is ALIVE, so the drop skips the T0 copy. The rebuild then holds 2 copies on `D`; live holds 1. That is AC-6b's doubling, with the steps swapped.

**Case 2: today's orphans.** `reborn_e.py` checks the appends that match current orphans:
- **0** of cliquedb's 2,387 and **0** of refmatrix's 55,242 have a tombstone of their entity key after them.
- All of them name an entity key that is live now.

They are the live holders' own rows, which share the orphan's `(linkage, file, line, detail)` (an orphan's dead entity has no name to tell them apart). `excess.py`: for these identities, live holds 3,394 / 55,845 copies against 2,387 / 55,242 appends. The excess a rebuild would add is at most 51 copies on cliquedb and 0 on refmatrix.

Under R5 as written, the vacuum would log drops for all of them. Each would then be counted `orphan_drop_skipped_live` on every rebuild: about 2.4k on cliquedb, about 55k on refmatrix. And `orphan_drop_unlogged` would undercount, because a live holder's append counts as "logged".

**Fix (amends d-28; needs an orchestrator note against d9bk):**
> A copy appended at log position `a` is dropped by `evidence_orphan_drop` at `T` iff its entity key `(partition, e_kind, e)` has a `tombstone` AFTER `a` and at or before `T`, in the row pass's `(ts, log position)` order. That is: the incarnation that appended the copy was later purged.
>
> - This is the same per-key `ts` lists Pass 2 already keeps; nothing new is read.
> - The vacuum scan applies the SAME predicate with `T` = now when it collects appends ([[#s-1]]). So a drop is logged only for a copy a rebuild would otherwise revive.
> - A matching copy with no tombstone after it is a live holder's row or bug-111's raw-delete shape. It is not this op's and is not counted `orphan_drop_skipped_live`. That counter keeps the meaning "a logged drop met a copy whose entity was not purged after it", and it stays 0 in every AC.

**AC-6b additions:**
- **Swapped variant:** purge `D`, re-ingest `D`, `vacuum`, then rebuild a copy. The copy holds 1 copy, equal to live. The mutation "dead-at-`T` by latest-tombstone-versus-latest-entity" (today's d-28) FAILS it: the copy holds 2.
- **Today's shape:** an orphan whose only matching append is a live holder's (logged before the orphan's entity was raw-deleted). `vacuum` logs no drop and prints `orphan_drop_unlogged: 1`.

rel: contradicts -> [[task-22.6-removal-entry-points#r5-timeline]]

### SKETCHY s-3: the new `FOLD_OPS` rows say "with its fold handling" but no fold rule, and 17.4's fold must EQUAL the rebuild's counts {#s-3}

**The rows.** 16.6, 22.2 and 22.6 each add a `scripts/factslog-restore.py` row (ns17-r9-2): `learned_provenance` / `learned_provenance_move`; `evidence_remove` / `evidence_repoint` / `entity_rename`; `evidence_orphan_drop`.

**The 17.4 contract** ([[task-17.4-factslog-backup-snapshot#r6-restore]] step 3):
- the rebuilt `entities` / `links` / `evidence` counts must equal an INDEPENDENT fold;
- an op may be "folded into the counts or explicitly ignored for them";
- the AST test pins only the op SET.

**The gap.** An implementer who adds `evidence_remove` and `evidence_orphan_drop` to `FOLD_OPS` as "ignored" passes the set test. Their restore verification then fails the count check on every real log after the first plan-22 removal. It fails loudly, but at restore time, which is the worst moment to find out. No row states what the fold does, and no AC compares fold and rebuild on a log that holds the new ops.

**Fix:** each row states its fold rule:

| op | fold rule |
|---|---|
| `evidence_remove` | reduces the copies of its key appended at or before it to `keep` |
| `evidence_orphan_drop` | removes the copies [[#s-2]]'s predicate selects |
| `evidence_repoint`, `learned_provenance*` | count-neutral (ignored, named as such) |
| `entity_rename` | renames the key, and merges on a collision as R2 does |

Add one AC in 22.6, the last of the three to land: `factslog-restore.py`'s fold counts equal `rebuild_index_from_log`'s counts on the AC-3d, AC-3f and AC-6b(+swapped) fixture logs. The mutation "fold ignores `evidence_remove`" FAILS it.

rel: depends-on -> [[task-17.4-factslog-backup-snapshot#r6-restore]]

### MEH m-1: name the scan's lookup key and the key-only load {#m-1}

22.6 R5 says "ONE read-only scan of `facts.log` for the orphan identities (a set lookup per line)". But an orphan identity carries a dead entity id the log never names.

**Fix:** state that
- the lookup key is `(linkage, file, line, detail)`;
- the orphan set is loaded as DISTINCT keys (`GROUP BY` in DuckDB), never as rows. Measured: 66,239 keys in 0.07 s and a 371 MiB process peak, against 1.0 GiB for 834k rows ([[#scan-cost]]);
- the scan collects the `entity` / `tombstone` timelines [[#s-1]] and [[#s-2]] need in the same pass;
- the cleanup manifest of step 3 is written streaming. On refmatrix it holds 834,201 rows inside the lock hold.

### MEH m-2: `_row_op_c_kinds`'s `n` lost its partition {#m-2}

**Partition.** Round 8 said "the live partition". Round 9 says "the LIVE entity of that kind and name". With `UNIQUE(partition, kind, name)`, `n` must be counted on the concept of that name **in the row's partition**. Say so.

**Orphans.** For an orphan row, "identical (same `e_kind`, `e`)" is undefined, because the entity end has no name. With [[#s-1]]'s fix the vacuum stops calling the helper, so delete 22.6's "the helper's `concept` pair always has `n = 0`" sentence along with the live-concept bullet.

### MEH m-3: AC-12's test-side AST scan cannot see docstrings {#m-3}

**The gap.** R1f rewrites `tests/test_memory_content_log.py`'s module docstring. But the `tests/` scan matches Name / Attribute nodes only, so that rewrite (and any re-added docstring mention) is unenforced.

**Fix:**
- Scan `tests/` string constants too, excluding the scan's own module.
- Say that the fixture-tree self-check runs BOTH modes. It needs a text hit, plus an attribute hit in a test file under `tmp_path`, because a `def apply_log_delta` is a FunctionDef, which the Name/Attribute scan does not see.
- Optionally widen the text scan to `scripts/` and `eval/`. There are 0 hits there today; the benchmark path is the production path.

### MEH m-4: 16.3 merge order, the test half {#m-4}

"Whichever lands second resolves to the tuple without the name" covers `hooks.py`. If 16.3 lands first, `tests/test_bug118_optional_hook_exit.py` does not exist on master yet, so bug-118's merge must make the `SCRIPTS` edit and add the not-rendered assertion. Add "and the test edit" to that sentence. bug-118 is not merged; master is `b381b6d`.

## Per-task verdict {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1 | **ready** | none |
| 16.2 | **ready** | none |
| 16.3 | **ready** | [[#m-4]] (one clause, optional) |
| 16.4 | **ready** | none |
| 16.5 | **ready** | none |
| 16.6 | **ready after a small edit** | [[#m-3]]; [[#s-3]] (fold rule for its two ops); AC-9d check 2's caller list once [[#s-1]] lands. R1f itself is clean. |
| 22.1 | **ready** | none |
| 22.1a | **ready** | none (its naming is correct for ITS classes; [[#s-1]] stops 22.6 from borrowing it) |
| 22.2 | **ready after a small edit** | [[#m-2]]; [[#s-3]] (fold rules for its three ops) |
| 22.3 | **ready** | none |
| 22.4 | **ready** | none |
| 22.5 | **ready** | none |
| 22.6 | **needs an edit pass** | [[#s-1]] (one keying rule from the orphan's own appends; AC-6c rewrite); [[#s-2]] (tombstone-after-append; swapped AC-6b; amends d-28 / d9bk); [[#s-3]] (fold rule plus the fold-equals-rebuild AC); [[#m-1]] |

**One orchestrator ruling is needed:** [[#s-2]] amends d-28 (d9bk). It changes "dead at `T`" to "a tombstone of the key after the copy and at or before `T`". Everything else is text.

## Verdict {#verdict}

DIRTY: 7 findings (0 BULLSHIT, 3 SKETCHY, 4 MEH). r9: 7 of 8 closed.

- **16.6 R1f's deletion list is complete:**
  - every name has no other caller;
  - nothing it calls is orphaned;
  - the env var has no consumer;
  - AC-12 can fail.
- **The vacuum scan is cheap:** about 1 s per pass, streaming, bounded by compaction. It needs a key-only load to keep RSS near 370 MiB rather than 1 GiB.
- **Plan-16:** approvable after the 16.6 edits.
- **Plan-22:** approvable after one 22.6 edit pass and the d-28 ruling.
