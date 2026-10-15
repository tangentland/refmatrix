---
gmd: "0.1"
id: bsd-bug105-hotfix-r4-fb285cc
title: "bug-105 hotfix r4: #s3-1 (collision-bit remap) and #m3-2 are closed and both-halves / chain / remap-only cases are correct, but moving the rebind into the FINAL hold opened a window in which every op queued behind the merge tail runs bound to the just-dropped SRC partition (a regression; my r3 prescription was narrower than the defect), saved bindings are restored over the rebind (pre-existing), and the r2 survivors M1/M11/M12/M14 are alive a third time"
severity: BULLSHIT
plan: bug-105
task: hotfix-fb285cc-r4
tags: [bsd, audit, bug-105, fragments, bitmap, partition, repair, merge, lock, binding, mutation]
---

# ch-bsd findings r4: bug-105 r3 remedies (fc4c8d1 + fb285cc) {#root}

**Commit:** fb285ccec95d89bb956553580c49c04967938c3e (with fc4c8d11a0bb26cf3e34c6f8d6f30582467dea7c)
- Range under audit: 27b3653..fb285cc. Base of the hotfix: a434f51.
- Clone: `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`.

**Date:** 2026-10-14 (written 2026-10-14T14:43:50-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (27b3653..fb285cc):** 4
- Source: store.py (rebind moved into the final hold, `repair_fragments(id_map=)`), daemon.py (`_merge_repair_line`, sync + async `merge-done` lines).
- Tests: `tests/test_fragment_repair_audit_r3.py` (P1-P3, P5-P8).
- Docs: the r3 report.

rel: amends -> [[bsd-bug105-hotfix-r3-27b3653]]
rel: amends -> [[bsd-bug105-hotfix-r2-4fb803b]]

## Evidence base {#evidence}

All logs are under `workflow/review-output/` in the clone.

- **Interpreter:** `.venv-eval/bin/python` with `PYTHONPATH=<clone>/src` prepended. Probe Q0 prints `refmatrix.__file__` = `/Volumes/littlebig/refmatrix-bug105/src/refmatrix/__init__.py`.
- **Families at HEAD:** 528 passed, 4 skipped (`bsd-bug105-r4-families-head.log`; the r3 family list plus `test_fragment_repair_audit_r3.py`). This matches the claimed `bug105-r4-families.log`.
- **Mutation family:** 94 passed at HEAD (`bsd-bug105-r4-family-head.log`). It is 12 files: the r3 nine, plus `_r3`, `test_duckdb_fragments` and `test_verb_alias`.
- **Probes** (`bsd-bug105-r4-probe-tests.py.txt`; results in `bsd-bug105-r4-probes.log`): 4 pass, 4 fail. The probes were copied into `tests/` only for the run and then removed.
  - Comparison trees, exported with `git archive` to the scratchpad: `bsd-bug105-r4-probes-at-27b3653-run{1,2,3}.log` and `bsd-bug105-r4-probes-q5-q7-at-bases.log` (27b3653 and a434f51).
  - Q4 repeated 5 times at HEAD: `bsd-bug105-r4-probe-q4-repeat.log`.
- **Mutations:** 17 mutants, 7 killed, 10 survive (`bsd-bug105-r4-mutations.log`, script `bsd-bug105-r4-mutate.py.txt`). Survivors N1 and N2 are killed by my probes Q1, Q2 and Q3 (`bsd-bug105-r4-probe-mutants.log`), so neither is an equivalent mutant.
- **Restore:** every mutant was restored with `git checkout -- <file>` and `__pycache__` was cleared after each one. The loop printed `RESTORED clean`. The tree is at fb285cc with a clean `git status`, and no `__pycache__` is left under `src/` or `tests/`.
- **Isolation:** the adopted daemon tests ran under `/tmp/r3b-*` with HOME, RMX_HOME and the model socket isolated. Afterwards no `r3b-` process or directory remains. No live store, live socket, main-tree file or the bug109 clone was touched.

## r3 status {#r3-status}

| r3 id | Status | Evidence |
|-------|--------|----------|
| #b3-1 merge rebinds home outside the lock | **closed as written; regression introduced** | The rebind now runs in the final `with _lk:` hold (store.py:1962-1965). P3 is adopted, and M30 is killed by it. But a separate hold reopens the bug in a worse form: see [[#b4-1]]. |
| #s3-1 collision bits not remapped | **closed** | `id_map` remaps both halves (store.py:4393-4402), and merge passes the collision map (:1966-1969). M31 and M32 are killed by P7. My Q1 (both halves collided), Q2 (entity half only) and Q3 (remap-only change in an unmoved row) all pass at HEAD. At 27b3653, Q3 reported `dropped_dead_concept=1` with a manifest. Residual: N1 and N2 survive the family, so the remap is half-pinned ([[#s4-1]]). |
| #s3-2 r2 survivors + unpinned prints | **partial** | P5, P6 and P8 are adopted: M22, M23, M33 and N3 are killed. But M1, M11, M12 and M14 survive for a third round, and M5, M24 and M25 survive too. fc4c8d1 marks #s3-2 as addressed and does not mention the four carry-overs. See [[#b4-2]]. |
| #m3-1 SQLite merge strands a SRC file | **open (accepted by design)** | Unchanged. DuckDB is production. Stays MEH. |
| #m3-2 rmxd.log silent; stale docstring | **closed (MEH residual)** | There is one `merge-done … fragments_repair moved=… dropped_dead_concept=… links_skipped=… manifest=…` line per merge, sync and async (daemon.py:4107, :4128). M33 and N3 are killed. The docstring now says the lock is NOT re-entrant and lists `fragments_repair`. Residual: the `manifest=` field is unpinned (N4 survives) ([[#m4-1]]). |

**r2 carry-over mutants** (against the 94-test family):

| Mutant | Status |
|--------|--------|
| M1 (tick guard reads `_dirty_fragments`) | **open**: survives, 94 passed |
| M11 (`links_skipped` never incremented) | **open**: survives |
| M12 (SQLite unlink-all) | **open**: survives |
| M14 (no `_canonical_verb` on `linkage_types`) | **open**: survives |

## Answers to the four questions {#questions}

**Does `id_map` handle a bit whose concept AND entity both collided?** Yes.
- Both halves go through `id_map.get(x, x)` in one pass.
- Q1 shows it: a fragment-only `(src_k, src_o.md)` lands as `_pack(dst_k, dst_o.md)` in DST's row, with `dropped_dead=0` and `dropped_dead_concept=0`.
- Unpinned: N1 (remap the concept half only) passes all 94 family tests and fails Q1 and Q2.

**Can a chain occur, where a DST id is also a key in the map?** No.
- Keys come from `s.partition_id = src_id` and values from `d.partition_id = dst_id`.
- `entities.id` is the primary key, with exactly one `partition_id`, so the key set and the value set are disjoint.
- `UNIQUE(partition_id, kind, name)` (store.py:272) makes the map a function, and also injective.
- A single non-transitive pass is therefore correct.
- Bits left over from merges that ran before this fix still name SRC ids whose rows are gone. No map exists for them; `repair-index --fragments` drops them into the manifest. They were already unreachable, so nothing new is lost.

**Does the remap change the "changed rows" set so that a remap-only change is still written?** Yes.
- `changed` compares against `old_for_change`, the un-remapped rows.
- Q3 shows it. SRC has no fragment rows at all. The only stale bit, `_pack(src_k, x)`, sits in DST's row. After the merge that row holds `_pack(dst_k, x)` and not the src bit (`rows_changed=1`), and `load_bitmap('mentions', dst_k)` finds x.
- Under N2 (compute `changed` from the remapped rows), nothing is written. The stale bit stays, the remapped bit never lands, and Q3 fails. N2 passes the whole family.
- Report gap: a remapped bit is counted `kept` (Q3: `kept=1 moved=0`). The report cannot show that a remap happened ([[#m4-1]]).

**Does a partition binding move outside a lock anywhere else?** Yes. It also gets restored stale across lock holds. See [[#b4-1]].
- The merge's own rebind is now under a lock, but in the wrong hold.
- `_partition_keeping_yield` (daemon.py:3313) and `Store.with_partition` (store.py:1995-2026) save a binding before releasing the lock and restore it afterwards, which overwrites the merge's rebind.
- Other binding writes I checked are held or scoped to a non-writer store:
  - `rename_partition` runs under `_store_lock` (`_op_partition_rename`).
  - Daemon lines 4925, 4946 and 4964 are the mirror store under `acquire_use`, a private snapshot store, and the writer under `_writer_lock`.
  - Store line 2075 is `_ensure_partition`, which runs at open.

## Findings {#findings}

### BULLSHIT (regression, binding class #8): the rebind's separate hold hands the lock to every queued op while home is bound to the dropped SRC partition {#b4-1}

**File:** src/refmatrix/store.py, between the tail `with _lk:` (it ends with `DELETE FROM partitions WHERE id=src` at :1946) and the final `with _lk:` (:1962). That window includes `con.commit()` at :1948, which runs unlocked.

**What:**
- fc4c8d1 moved the three rebind lines into the final hold. That is what my r3 fix text prescribed.
- But the final hold is a NEW acquisition. `_FairLock` is strict FIFO and hands the lock to the next queued waiter on release.
- So every op that queued during the tail hold now runs BEFORE the merge rebinds. Each one sees `_partition_id` = the SRC id whose `partitions` row the tail just deleted.
- At 27b3653 the unlocked rebind ran on the merge thread right after the release and beat the woken waiter.

**Evidence (Q4; home bound to SRC; one writer queued at the tail release):**

| Tree | Binding seen by the queued op | Where its new entity lands | `partitions` afterwards | Repair report |
|------|-------------------------------|----------------------------|-------------------------|---------------|
| fb285cc (5/5 runs, `-q4-repeat.log`) | `('src', 2)` | partition 2 | `[(1, …), (3, 'dst')]` | `rows_after=2`: it wrote a fragment row for the dropped pid 2 |
| 27b3653 (3/3 runs) | `('dst', 3)` | partition 3 | | |

At fb285cc the entity is an orphan: no partition query can reach it, and every later `repair-index --fragments` keeps rewriting its row under pid 2.

**Siblings (pre-existing at a434f51 and 27b3653, same root: the home binding is lock-holder state that other holders save and restore):**
- **Q5:** an ingest yielding through the real `_partition_keeping_yield` while the merge completes.
  - After the merge, the binding is `('dst', 3)`.
  - After the ingest reacquires, it is `('src', 2)` again. The ingest's next entity lands in dropped partition 2, and home stays bound to it until the daemon restarts.
- **Q6:** an op inside `with_partition('other')` yields while the merge's final hold runs.
  - The merge sees `_partition_name == 'other'` and skips the home rebind altogether.
  - The scope exit then restores `('src', 2)`.

**Why it's bullshit:**
- This is the bug-098 shape for the 8th time, and this time the fix made it deterministic: under the production FIFO lock every queued writer hits the window.
- I own the prescription. "Move the three lines inside the final `with _lk:` block" was narrower than the defect. The rebind has to be atomic with the `DELETE FROM partitions`, not merely locked.

**Fix:**
1. In `_op_partition_merge`, refuse a merge whose SRC is the daemon's home partition. Return an error such as "restart the daemon bound to another partition first". This closes Q4, Q5, Q6 and #b3-1 at the only place they are reachable. It is about 5 lines.
2. If merging home must stay possible, two changes are needed together:
   - Move the rebind and `con.commit()` into the tail hold, directly after `DELETE FROM partitions`.
   - Make `_partition_keeping_yield` and `with_partition`'s exit re-validate that the saved partition id still exists before restoring it.
3. Adopt Q4, Q5 and Q6.

**Scope:** reachable only through `rmx partition merge` (sync or `--async`) with SRC = the daemon's home partition. It does not touch `rmx repair-index --fragments`.

**Pattern match:** YES. The binding class (`#imp-binding-is-every-cache`), 8th instance. Also the 0916 pattern, "a prescription narrower than the defect", in my own r3 text.

### BULLSHIT (escalated, third sighting): M1, M11, M12 and M14 survive a third round, and #s3-2 is reported addressed without them {#b4-2}

**File:**
- M1: the daemon tick guard (`has_dirty_fragments`).
- M11: `links_skipped` (store.py:4380).
- M12: the SQLite `_write_all_fragment_rows` unlink loop.
- M14: `_canonical_verb` on the `linkage_types` names (:4366).

**What:**
- r2 reported these four survivors, each with a one-test fix.
- r3 re-reported them and wrote: "If they are still unaddressed at r4, they become a third sighting, and the finding escalates to BULLSHIT."
- fc4c8d1's message lists "#s3-2: the auditor's probes P1-P3 and P5-P8 are adopted" and says nothing about the four. All four still pass the full 94-test family (`bsd-bug105-r4-mutations.log`).
- Three more survive: M5 (no pre-flush, near-equivalent per r3), M24 (`repair-index` drops `unread_dirs`) and M25 (the rmxd.log repair line loses `dropped_dead_concept`, `links_skipped` and `unread_dirs`). P8 was adopted but it PRINTS rmxd.log rather than asserting on it, and it never constructs an unread dir.

**Why:** this is a cheap fix by silent scope shrink (rule 10). The id was closed by doing its easy half. Each of the four guards a destructive repair:
- M11 makes a skipped link uncounted. That breaks the memory-path no-silent-failure rule.
- M12 lets the SQLite repair delete files it never read.
- M14 lets raw-named linkage types escape canonical folding, so their bits land under a second key.
- M1 makes the tick flush miss a non-home dirty binding.

**Fix:** four tests, as prescribed in r2:
- a tick-body test where only a non-home binding is dirty (M1);
- an `entity_links` row whose entity is missing, asserting `links_skipped == 1` (M11);
- a SQLite store with an unread foreign-partition `.rb64` file, asserting it survives (M12);
- a raw-named linkage type such as `related_to`, asserting a single canonical row (M14).

Change P8 to assert on the rmxd.log `dropped_dead_concept=`, `links_skipped=` and `unread_dirs=` fields, and add one unread dir (M24, M25).

**Pattern match:** YES. "Prescriptions narrower than the defect" / the 0916 note. The r3 escalation rule applies.

### SKETCHY (pre-existing, gates live merge): a write that names SRC during a live merge creates an orphan entity {#s4-1}

**File:**
- src/refmatrix/store.py:1694-1949: classification (:1729-1744) runs once, up front.
- `Store.with_partition` (:1995-2026).

**What:**
- Between chunks, any op that runs `with_partition(src)` creates SRC entities that are in neither `collisions` nor `reparents`.
- The tail deletes the SRC `partitions` row, and those entities keep `partition_id = src`.

**Evidence (Q7):**
- An entity written from a progress tick lands in partition 2, while `partitions` = `{1, 3}`.
- The same result at a434f51 and at 27b3653 (`-q5-q7-at-bases.log`).
- Home is neither SRC nor DST in this probe. Any daemon is exposed, including during the `memory-<project>` → `<project>` consolidation if anything still writes to `memory-<project>`.

**Why SKETCHY, not MEH:** r2 #m2-1 listed "merge atomicity" as a known layout gap. This is the first concrete orphaning reproduction, and it decides whether a live merge is safe.

**Fix:** in the tail hold, before the DELETE, re-run the collide/reparent classification for any SRC entity that appeared after the first pass (same SQL, same hold). Refuse `with_partition(src)` writes while a merge of SRC is running, or let them land in DST.

**Remap pinning (folded in here, not counted separately):**
- N1 (concept half only) and N2 (`changed` from remapped rows) both survive the family.
- My Q1, Q2 and Q3 kill them (`-probe-mutants.log`). Adopt them.

### MEH: the remap is invisible in the repair report, and the log's manifest field is unpinned {#m4-1}

- A bit moved by `id_map` is counted `kept` or `moved` like any other bit. In Q3 the report reads `kept=1 moved=0 rows_changed=1`, with no sign that a remap happened.
- Add `remapped=<n>` to the report, to the CLI line and to `_merge_repair_line`.
- N4 (the `manifest=` field dropped from the merge log line) survives. Assert that it is present in P5.

### MEH: no implementation summary or bug-registry row on the branch {#m4-2}

- `git log a434f51..fb285cc -- workflow/implementation_summaries workflow/bug_registry.md` is empty, and no bug-105 summary file exists in the clone.
- CLAUDE.md task step 8 makes the summary mandatory before commit. It may be planned for master, but nothing on this branch records the 6-commit fix or its open residuals.

## Verdict {#verdict}

**DIRTY: 5 findings (2 BULLSHIT, 1 SKETCHY, 2 MEH).**
- r3's 5 ids:
  - 2 closed: #s3-1, and #m3-2 (with a MEH residual).
  - 1 closed as written but regressed: #b3-1, now [[#b4-1]].
  - 1 partial: #s3-2, now [[#b4-2]].
  - 1 open by design: #m3-1.
- r2 carry-over mutants M1, M11, M12, M14: all 4 open.
- Mutations this round: 17 run, 7 killed.

**Is merge → deploy → per-store backup → dry run → apply safe?** YES, for the `rmx repair-index --fragments` path. This is unchanged from r3, and nothing in fc4c8d1 or fb285cc touches it:
- `_op_repair_fragments` holds `_store_lock`;
- `repair-index` passes no `id_map`;
- the dry run does not write;
- the corrected predicate is pinned (M20 killed in r3);
- the CLI counters are pinned (M23 killed; P8).

Caveats:
- [[#b4-2]]'s survivors mean `links_skipped`, the SQLite unlink scope and the canonical folding are unguarded against FUTURE regressions. They are correct at fb285cc.
- Back up the ACTIVE slot first. The manifest records drops only.
- Expect pre-fix historical merge bits under dead SRC ids to appear in `dropped_dead` and `dropped_dead_concept`. Their map no longer exists.

**Is a live `rmx partition merge` now safe?** NO.
- With SRC = the daemon's home partition it is now WORSE than at 27b3653: every op queued behind the tail binds to the dropped partition, deterministically ([[#b4-1]]).
- With any SRC, a write naming SRC during the merge orphans its entity ([[#s4-1]]).
- Safe only under both of these conditions:
  - the daemon is restarted bound to a partition other than SRC;
  - nothing writes to SRC during the merge. For `memory-<project>`, stop the hooks or run the merge offline (`lock=None`, daemon down).
- Collided bits are now remapped correctly in either case.

rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[claude#before-commit]]
rel: contradicts -> [[claude#task-completion-workflow]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T14:43:50-0700 commit=fb285cc verdict=DIRTY findings=5 (2B/1S/2M) report=2026-10-14-1443-bug105-hotfix-r4-rebind-hold-opens-dropped-partition-window-fb285cc.md
```

INDEX.md row:

```
| fb285cc (27b3653..fb285cc, bug-105 hotfix r4: fc4c8d1 + fb285cc; written 2026-10-14T14:43) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 5 (2B/1S/2M); r3 5: 2 closed / 1 closed-but-regressed / 1 partial / 1 open-by-design | [[bsd-bug105-hotfix-r4-fb285cc]]. #s3-1 closed: id_map remaps both halves (Q1 both-collided, Q2 entity-only, Q3 remap-only unmoved row all pass; chain impossible, keys=src ids, values=dst ids, PK + UNIQUE(partition_id,kind,name)). #m3-2 closed (sync+async merge-done lines, M33/N3 killed). B (regression, binding #8): rebind in a SEPARATE final hold -> FIFO hands the lock to every op queued behind the tail while home = dropped SRC id: Q4 5/5 at fb285cc entity in partition 2 (absent) + fragment row for pid 2, vs 27b3653 3/3 ('dst',3); siblings pre-existing at a434f51: _partition_keeping_yield (Q5) and with_partition exit (Q6) restore ('src',2) over/around the rebind; my r3 prescription was narrower than the defect. B (escalated, 3rd sighting): M1/M11/M12/M14 survive, #s3-2 marked addressed without them; M5/M24/M25 too. S: SRC write between merge chunks orphans the entity (Q7, pre-existing). M: remap invisible in report (counted kept), N4 manifest field unpinned; no implementation summary / bug row on branch. 17 mutants, 7 killed; N1/N2 survive family, killed by Q1-Q3. Families 528 passed. repair-index deploy sequence SAFE; live partition merge NOT safe (refuse src == home, re-classify late SRC rows in the tail hold). |
```

IMPRESSIONS.md bullets:

```
- "Under the lock" is not "atomic with the state change": moving a rebind into a LATER hold of a FIFO lock hands the lock to every queued op while the binding names a partition the previous hold already deleted. Prescribe the SAME hold as the mutation it follows, and probe with a waiter queued at the release (bug-105 r4 #b4-1; my r3 fix text caused it).
- Saved-binding restore is a second write path for the binding: _partition_keeping_yield and with_partition's exit put back whatever they captured, so any op that moves the home binding mid-flight is overwritten (bug-105 r4 Q5/Q6). Audit every save/restore pair, not only the assignments.
- An id marked "addressed" with only its new half done: #s3-2 adopted the probes and dropped the four r2 survivors without a word, three rounds running (bug-105 r4 #b4-2). Re-run the carry-over mutants every round; the commit message is not evidence.
```
