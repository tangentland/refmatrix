---
gmd: "0.1"
id: bsd-plan18-r4-closing-diffcheck-c4ef0a8
title: "ch-bsd plan-18 r4 closing diff check (1318b30..c4ef0a8): every r3 fix landed; the two-leg rule is exact as written (10 constants, 9 functions); 18.2 CLEAN; 18.3 carries one clause of my own r3 text with no producer"
tags: [ch-bsd, plan-18, task-18.2, task-18.3, spec-review, diff-check, closing]
severity: SKETCHY
plan: plan-18-duckdb-store-maintenance
task: task-18.2-catalog-maintain-step + task-18.3-offline-reclaim
round: 4
---

# ch-bsd plan-18 r4: closing diff check of `1318b30..c4ef0a8` {#root}

**HEAD:** `c4ef0a8` on `wave0-spec-reviews`, confirmed with `git log -1`.
**Scope:** `git diff 1318b30 HEAD -- 'workflow/plans/plan-18-*'`. Two files changed: 18.2
(+26/-6) and 18.3 (+66/-29). The plan file and 18.1 did not change.
**Probes:** `/private/tmp/claude-501/p18r4/`, run with `~/refmatrix/.venv/bin/python -I`.

- `census3.py` / `census3.log`: the two-leg rule exactly as R11 now words it. Leg 2 matches ANY
  f-string literal part. r3's `census2.py` matched only the first part.
- `mut/` / `mut.log`: the AC-17 mutations planted on a copy of the `b381b6d` source.

The source snapshot `p18r3/src_b381b6d/src/refmatrix` matches `git show b381b6d` for `store.py`.

rel: derives-from -> [[bsd-plan18-r3-spec-diffcheck-1318b30]]
rel: contradicts -> [[task-18.3-offline-reclaim#ac-4]]

## r3 closures verified {#closures}

- **N3-B2 is closed, verbatim** (18.2 R11). The two-leg rule, the op-name sentence, the census
  sentence ("exactly 10 constants in these 9 functions") and the AC-17 mutation are all
  present. 18.3 AC-14 inherits the rule by name.
  - `census3` at `b381b6d`: leg 1 = 10, leg 2 = 10, union = 10, and they sit in 9 functions.
    These are R11's sites: `cli.compact`, `cli.merge_verb_aliases`,
    `_bootstrap_rotation_if_needed` ×2, `_snapshot_catalog`, `serve_forever`, `_op_checkpoint`,
    `_op_replica_merge`, `replica_merge.merge_slots` and `Store.rebuild_entities_indexes`.
  - No op-name constant is flagged, and nothing is flagged at module level. Six constants would
    be caught only by a single case-insensitive leg: `cli.checkpoint` ×2, `cli.schedule_add`,
    the `daemon` module-level `OPS` key, the `scheduler` module-level `ALLOWED_OPS`, and
    `_snapshot_catalog:2705`. Neither leg flags them.
  - Widening leg 2 from the first f-string part to any part (as the rule is now written)
    changes nothing at `b381b6d`.
- **The AC-17 mutations can fail** (`mut.log`):
  - `self._conn.execute("checkpoint")` added to a `Store` method is caught by leg 2 only
    (`store.Store._mut_ckpt`, L2). It is on neither exemption list, so the check is red.
  - `con.execute("CHECKPOINT")` in a `backend.py` function is caught by both legs.
- **N3-B1 is closed, verbatim.**
  - AC-6 (fwd-I4): the fixture-proof paragraph is gone, and the replacement says the point
    kills nothing on its own.
  - The AC-6 mutation bullet is deleted.
  - AC-4's mutation is re-pointed to (b), and AC-17 now reads → AC-4 (b).
  - I10 is corrected, and the round-3 "not yet run" line is corrected in place.
- **The re-pointed kill can fail** (evidence from the r3 probes):
  - **Spec order:** `p2` b/spec reads `after step 2: slot.wal=None moved=None`, so (b)'s
    "no `reclaim-failed-<run_id>.duckdb.wal`" holds on correct code.
  - **Mutation (verify after `init()`):** `p1` reads `after init() via cached old instance
    slot.wal 1175` on all three fixtures. R6 B step 2 requires the file to be absent or 0
    bytes and otherwise `os.replace`s it into `backups/…reclaim-failed-<run_id>.duckdb.wal`,
    so the file exists and (b) is red.
- **R4 step 10 is aligned with I10.** It now reads "runs `init_catalog`, and every writer open
  writes a WAL (I10; the `linkage_types` UPDATE is not the writer)". The cached-instance
  consequence that follows it is unchanged and still true.
- **N3-M1 is closed** (R5 sequences bullet: the last dotted identifier, unquoted, with an
  unresolved `nextval(` failing closed; AC-2 seq-b: the identical text
  `nextval('seq_entities_id')`, with the columns leg asserted equal before the compare).
- **N3-M2 is closed.** The R6 invariant is scoped to `open_duckdb` connections, and the
  unregistered-holder window is stated as detected but not crash-safe.
- **N3-M3 is closed.** R8 says `verify` runs once and `_connect` clears it after the first
  successful run, which agrees with the Files table's "one-shot".
- **N3-M4 is closed.** In the R8 Ports init-rebind bullet, a `close_writer()` error logs
  HEAD's `close failed` line and the reopen is still attempted. The "behaviour is unchanged"
  sentence now names that path.
- **GMD lint:** 18.2 and 18.3 each have 0 errors (rc 0). The warnings are cross-doc dangles
  from linting one file at a time.

## Findings {#findings}

### SKETCHY N4-S1: AC-4 (b) asserts "the rollback's log line reports a foreign WAL of 0 bytes", but R6 B emits that line only when it moves a non-empty WAL {#n4-s1}

**Where:** 18.3 AC-4 (b), the sentence added this round (line ~978). The text is MY r3
replacement, applied verbatim.

**What R6 B step 2 says:** "Require `<slot>.wal` to be absent or 0 bytes. If it is not,
`os.replace(…)` BEFORE the restore, with one log line naming its size." That line is the only
log line in R6 B. A grep of 18.3 for "log line" finds no other rollback line that reports a
foreign WAL size.

**Why it fails:** in (b), on correct code, step 2 finds no WAL (`p2` b/spec), so it logs
nothing. The AC asks for a line that the requirement never emits. A build that follows R6 B
exactly fails AC-4 (b) on that clause. The alternative is that the implementer invents an
unspecified "0 bytes" log line to make it pass.

**The kill is unaffected.** The file-absence assertion carries the verify-after-`init()` kill
on its own (see [[#closures]]).

**Fix (replacement text):** in AC-4 (b), replace "and the rollback's log line reports a foreign
WAL of 0 bytes" with:

> and R6 B step 2 emitted no foreign-WAL log line

This needs no requirement change, and the parenthetical stays as it is. (The other option is to
make R6 B step 2 always log the size, including 0. That changes the requirement to suit a test
clause, so it is not recommended.)

**Pattern match:** YES. A pre-registered assertion was written without being read against the
requirement that must produce it, and the author was the reviewer. It is the sibling of
[[bsd-pattern-prereg-check-unrun-census]].

rel: contradicts -> [[task-18.3-offline-reclaim#r6-rollback]]

### MEH N4-M1: R6 B step 1 still attributes the reopen's WAL to `init()`, which the corrected I10 now denies {#n4-m1}

**Where:** 18.3 R6 B step 1 says "(its close checkpoints and removes the WAL that `init()` wrote,
I10)". This round's I10 edit says the `linkage_types` UPDATE in `Store.init()` is not the
writer. The r3 `p1d` probe placed the 1,175 bytes "elsewhere in the open path".

**Status:** the line is outside the diff, but the diff made it inconsistent with I10.

**Fix:** "(its close checkpoints and removes the WAL the open wrote, I10)".

## Verdict {#verdict}

**2 findings (0 BULLSHIT, 1 SKETCHY, 1 MEH).**

- **18.2: CLEAN. It is approval-ready.** The two-leg rule is exact as written at `b381b6d`
  (10 constants, 9 functions, no op-name or module-level hits), and its new mutation fails.
- **18.3: approval-ready once N4-S1's one-clause replacement is applied verbatim.** N4-M1 can
  be folded in the same edit, as one word. Every r3 BULLSHIT is closed, and every re-pointed
  mutation can fail. Neither fix touches a mechanism. A re-check of that one sentence is
  enough, with no new probe.
- **PATTERN filed:** [[bsd-pattern-prereg-check-unrun-census]].

rel: contradicts -> [[task-18.3-offline-reclaim#ac-4]]
