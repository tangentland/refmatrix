---
gmd: "0.1"
id: pop-2026-11-13-contra-c
title: "contra-c: write path + store maintenance (T4)   (files read: 31)"
tags: [plan-review, pop-2026-11-13, report]
metadata:
  node_type: report
  created: 2026-11-13
---

## contra-c: write path + store maintenance (T4)   (files read: 31) {#root}

Files read: brief; draft; POP; plan-23 and tasks 23.0-23.5; task-bug185; task-bug216 (only the parts that touch `ingest_gmd`); bug_registry rows 093/097/099/112/136/177/182/185/186/207; plan-17 and its 17.1-17.4 headers; plan-18 and its 18.1-18.3 headers; plan-22 and task-22.4; plan-4 frontmatter; task-26.6 R3 residual; the 26.5/26.7/26.8/26.9 headers; deferral_registry; the d9b* rows in plan-review-2026-10-14; the 25.1 grep. I checked every prerequisite sha with `git merge-base --is-ancestor` on master `0d2a270`. 91ddbe0, 76ec748, 9b2c4ac, 05164ce, 078c951, 8a867bc, 0c74872, d4bf001 and 74f8f98 are all ancestors.

### Cc-1 [K1] bug-185 locks in today's target resolution order, and bug-216 (in flight, lands first) changes it
- side A: `workflow/plans/task-bug185-bulk-gmd-ingest.md:103` "in HEAD's precedence `concept`, `doc`, `memory`, at most one statement per kind". At `:109`: "a target that misses the store but was MINTED EARLIER IN THE SAME DOCUMENT by a ref's `add_concept` … resolves to that concept". At `:136`: "R3 Semantics unchanged: the equivalence contract … compared with HEAD".
- side B: `workflow/plans/task-bug216-rule-docs-in-graph.md:148-151` "R6 Bare doc-id targets bind the doc. For a target with no `#anchor`, resolution order is `doc`, `memory`, then `concept` … The batch dict (`eid_by_name`) obeys the same rule". At `:191`: "(b) GMD ingest maintains it: ingesting a doc or memory with id X links every concept named X … to it". bug-216 also names the cause bug-185 reproduces, at `:142-145`: "a same-named concept (minted by the plain-wikilink `mentions` branch, `store.add_concept(target_doc)` …) wins over the doc."
- why it matters:
  - bug-216 is in T1 (draft queue step 1) and bug-185 is in step 3.
  - If bug-185 is built from its spec as written, its batched read and its "minted earlier" rule put back the concept-first misbinding that bug-216 fixes. Its AC-2 golden would then lock that misbinding in as "HEAD semantics", and bug-216's AC-7 mutation ("restore concept-first for bare ids") would be reintroduced as a feature.
  - bug-185 also does not know about bug-216's new per-document `denotes` writes, which bug-185 R1 would have to keep at a constant count per document.
  - bug-216 says "Depends on: none" and never mentions bug-185.
  - Three more merges have edited `ingest_gmd.py` since bug-185 was written (26.3 `3733dab`, 26.4 `1a1f189`, 26.6 `d77dd68`). bug-185 knows only 26.1 and 26.2.
- proposed resolution: bug-216 wins. Before RED, bug-185 needs a freshness revision on the post-bug-216 tree:
  - R2.2's precedence becomes R6's rule (anchored targets concept-first, bare targets doc-first).
  - R2.3's "minted earlier" rule must not bind a concept when a doc or memory of that name exists.
  - The `denotes` maintenance joins R1's constant per-document writes.
  - The AC-2 golden is regenerated from post-bug-216 HEAD.
  - bug-216's spec gets a `related-to` / order edge to bug-185.

### Cc-2 [K3] The draft queues 23.5 before 26.7, but 23.5 R9/AC-9 measures a hold that only exists after 26.7
- side A: `workflow/plan-review-2026-11-13.md:148` "3. T4 — bug-185 → 23.2 → 23.1 (bug-177) → 23.3 ∥ 23.5." and `:150` "5. T2 — 26.7 → 26.8 → 26.9 → plan-27." `workflow/plans/plan-23-bounded-write-harness.md:146` "23.5 R9 runs after 26.6 is merged." The POP row 23 (`workflow/plan-of-plans.md:46`) says the same: "with 23.5 R9 after 26.6".
- side B: `workflow/deferral_registry.md:54` "task 26.7 merged; built as [[task-26.6-compile-subject-hygiene#r3-residual]], 26.6 completes then; 23.5 R9/AC-9 depends on it". `workflow/plans/plan-26-memory-organisation-tasks/task-26.6-compile-subject-hygiene.md:235-237` "R3 residual: compile regenerates the index, after 26.7 … rel: depends-on -> [[task-26.7-memory-index-by-subject]]", and `:254-255` "Task 23.5 R9/AC-9 reads R3's index write inside the compile hold". On the 23.5 side, `task-23.5-read-path-and-holder-bounds.md:588-591`: "PLUS, on a memory root carrying the `.memory-layout` marker, 19.4 R3's in-hold reads of subjects, members and scores for the `MEMORY.md` render (26.6 … R3 row; marker-gated)".
- why it matters:
  - "26.6 merged" (`8a867bc`) is true, but 26.6 is not complete. Its header (`task-26.6…:16`) says "r1 remedy and the R3 residual open".
  - AC-9's K is a ratchet ("pre-registered RATCHET", `:893`). Measured before the R3 render exists, K equals K_off.
  - When 26.6 R3 later puts the `MEMORY.md` render inside the hold, AC-9 fails or K has to be re-measured.
- proposed resolution: user decision between two options:
  - (a) Split 23.5. R1-R8 stay at step 3, and R9/AC-9 runs after 26.7 plus the 26.6 R3 residual.
  - (b) Move 26.7 and the 26.6 R3 residual into step 2 next to 26.5.

  Either way, plan-23 `#merge-order` and the POP should say "after 26.6 R3 residual (after 26.7)", not "after 26.6 merged".

### Cc-3 [K6] bug-186 is fixed inside bug-185, but the draft also schedules it on its own in T6
- side A: `workflow/plans/task-bug185-bulk-gmd-ingest.md:24` "Also fixes: bug-186 (facts.log replay drops link weights), `#r6`." `workflow/bug_registry.md:237` (bug-186 row): "planned, owner [[task-bug185-bulk-gmd-ingest#r6]], decided in its revision round 1: fixed IN bug-185".
- side B: `workflow/plan-review-2026-11-13.md:112` "T6 Graph integrity | bug-218, bug-219, bug-186, bug-119-121, bug-124; plan-22 …". At `:152`: "7. T6 — bug-218, bug-219, bug-186, then plan-22." `:86-87` (F7) also lists bug-186.
- why it matters: two tracks each own the fix to `Store.bulk_link` logging and the `rebuild_index_from_log` fold. T4 lands it at step 3. T6 at step 7 would either rebuild it or find it already done and waste a slot.
- proposed resolution: bug-185 wins (decided in its r1, with AC-8 RED/GREEN). Remove bug-186 from T6 and F7, and list it under T4 as "fixed by bug-185 R6".

### Cc-4 [K6] bug-182 has no owner: three documents disown it, and the draft takes away its only queue slot
- side A: `workflow/plan-of-plans.md:58` "**bug-177** … with **bug-182** (the scan-prompt overrun; measure first) as part of bug-177's original scope". `workflow/plans/plan-23-bounded-write-harness-tasks/task-23.1-queue-and-drain.md:1266` "**The scan-prompt overrun is not 23.x's.**", and `:1273-1275` "It is its own bug row, **bug-182** … in the pre-plan-24 queue as the half of bug-177's original scope that R11 does not cover." `workflow/bug_registry.md:233` "Not a writer-lock wait … so plan-23 does not own it … a hook-budget item beside plan-25, not inside it".
- side B: `workflow/plan-review-2026-11-13.md:110` lists bug-182 under "T4 Write path" holds, but the T4 queue line `:148` ("bug-185 → 23.2 → 23.1 (bug-177) → 23.3 ∥ 23.5") does not include it. `:133` (P4) says: "the 'everything before plan-24' goal of 2026-11-09 is replaced by the queue."
- why it matters:
  - bug-182's only slot was the pre-plan-24 goal, which P4 removes.
  - The draft puts it in the write-path track, which 23.1 explicitly says is the wrong track: scan-prompt reads the lock-free replica.
  - No task spec in `workflow/plans` names it apart from 23.1 (as a non-goal) and the plan-23 fold table.
  - 25.1 caps hook output size in bytes, not wall time, so it does not cover bug-182 either.
- proposed resolution: move bug-182 to T3, which owns the UserPromptSubmit hook budget. Its first step (per-leg timing in `query.log`) is a measurement, so it fits P5's measurement lane. Whether the wall bound folds into 25.1 rev 8 is a user decision with a Q-id.

### Cc-5 [K3] The draft queues plan-22 before plan-16, but plan-22 depends on 16.6
- side A: `workflow/plan-review-2026-11-13.md:152` "7. T6 — bug-218, bug-219, bug-186, then plan-22." and `:153` "8. T5 — plan-16 with 25.4/25.5."
- side B: `workflow/plans/plan-22-audited-removal-and-repair.md:199-200` "after 23.1: **16.6 Wave-1 slice → 22.1a → 22.2 (with 22.6 R6) →". At `:206`: "22.1a needs: 23.0 (sandbox), 16.6's Wave-1 slice". At `:208-211`: "22.2 needs: 22.1a …, 16.6's Wave-1 slice … 23.1 …, 23.2". The POP row 22 (`workflow/plan-of-plans.md:45`) has "Depends on | 16.6, 23". plan-23 `:160` says the same.
- why it matters: queue step 7 cannot start plan-22 because its first task, 22.1a, needs 16.6's slice, which is in step 8.
- proposed resolution: the dependency wins. Split T6: bug-218 and bug-219 stay at step 7, and plan-22 moves after T5's 16.6 Wave-1 slice. Alternatively, put 16.6's slice ahead of step 7.

### Cc-6 [K6] Task 23.4 is pending, has no queue slot, and plan-17 still waits on its verdict
- side A: `workflow/plans/plan-23-bounded-write-harness.md:85` "Order: **23.0 ∥ 23.4 → 23.2 → 23.1 …". `task-23.4-option-a-measurement.md:16` "Status: Pending", and `:28` "Feeds: the d2b revisit (plan-17's per-dataset Lance lock; whether Option A becomes a plan)". `workflow/plans/plan-17-nightly-store-maintenance.md:157` "**Option A revisit** … is triggered by task 23.4's verdict", and `:195-196` "Trigger: task 23.4's verdict … If 23.4 returns GO for Option A, 17.1 is re-opened".
- side B: `workflow/plan-review-2026-11-13.md:148` (T4 queue: "bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5") and `:154` "9. T4 tail — plan-17, plan-18." 23.4 appears in neither.
- why it matters: plan-17 is queued (step 9), but the measurement that can reopen 17.1 is not. Either 17.1 gets built and later reopened, or 23.4 stays pending with nobody scheduling it.
- proposed resolution: user decision. Either place 23.4 (read-only, on a cliquet copy) in the measurement lane before step 9, or retire it with a stated reason and drop the 17.1 reopen trigger.

### Cc-7 [K3] The "plan-26 merged" gate in bug-185 (and in 23.1/23.2's stated order) is not met when the draft schedules them
- side A: `workflow/plans/task-bug185-bulk-gmd-ingest.md:20-22` "Depends on: bug-178 merged to `master` … AND plan-26 merged to `master` (26.1 and 26.2 edit `ingest_gmd.py` …)". `task-23.2-lock-hold-fixture.md:26` "**Merge order (m6):** 3.7 → bug-178 → plan-26 → **23.2** → 23.1". POP `:46` "build order 3.7 → bug-178 → plan-26 → bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5".
- side B: `workflow/plan-review-2026-11-13.md:147-150`: step 2 is "T2 26.5", step 3 is "T4 — bug-185 → 23.2 …", step 5 is "T2 — 26.7 → 26.8 → 26.9 → plan-27". `:36` "Not started from the queue: 26.5, 26.7, 26.8, 26.9".
- why it matters:
  - Read literally, bug-185 and 23.2 are gated on all of plan-26, which will not be merged until step 5.
  - The reasons given only need 26.1 and 26.2 (and 26.6 for the compile hold). All three are on master: `9b2c4ac`, `05164ce`, `8a867bc`.
  - 23.1's own header (`task-23.1…:49-52`) already gives the narrow gate correctly: "plan-26 task 26.2 MERGED".
  - Without a fix, an implementer or ch-bsd round will treat the literal gate as a blocker.
- proposed resolution: the narrow gate wins. Restate bug-185's dependency, 23.2's merge order and the POP line as "26.1 + 26.2 merged (satisfied)". This leaves Cc-2's 23.5 R9 caveat as the only real plan-26 dependency left in T4.

### Cc-8 [K6] Task 22.4 (concept merge writes) is handed to a plan that does not exist, and the draft keeps both of its gates parked
- side A: `workflow/plans/plan-22-audited-removal-and-repair-tasks/task-22.4-merge-writes.md:16-21` "BLOCKED until ADR-0004's helix implementation plan defines the term-space alias map, and plan-20 recommends a merge rule. That helix plan does not exist yet … plan-22 may close with this task handed to the future ADR-0004 helix implementation plan". `plan-22…:120-121`: `fold_concept_dups` and `merge_partition` are "plan-22 entry point owned … by the helix plan".
- side B: `workflow/plan-review-2026-11-13.md:112` "T6 … plan-22; plan-20 (dormant)", and `:118-119` (P2) "plan-13 and plan-20 stay dormant; plan-11 stays superseded."
- why it matters:
  - Closing plan-22 under T6 hands 22.4 and two live merge entry points (`rmx memory dedup`, `merge_partition`) to a host that does not exist.
  - The other gate, plan-20, is kept dormant by the same draft.
  - Merge writes would then have no owner on the audited path, which goes against plan-22 d-1's "one removal path … and merges".
- proposed resolution: user decision. Either record 22.4 and the two merge entry points as deferral rows under T6 that say "no host plan; plan-20 dormant", or have P2 name the helix plan as a dormant placeholder that owns them.

### Cc-9 [K4] Status lines in the T4 files contradict their own frontmatter and the confirmed decisions
- side A: `plan-17-nightly-store-maintenance.md:8` `status: approved` vs `:15` "Status: DRAFTING, revision round 9". `plan-18-duckdb-store-maintenance.md:8` `status: approved` vs `:15` "Status: DRAFTING. 18.1 ran 2026-10-15 and is IN-PROGRESS", and `:102` "18.3 | IN-DAEMON reclaim (d9bf, amended by d9bp; PROVISIONAL)". `plan-23-bounded-write-harness.md:8` `status: in-progress` vs `:15` "Status: Drafting (revision round 12". `plan-23…:155-157` "bug-112 FIXED and reachable from `master` … OPEN at `b84fd8d`". `task-23.5…:27` "PROVISIONAL until its ch-bsd loop is clean".
- side B: `task-18.1-catalog-measurement.md` `status: completed`, merged `530660e`. `workflow/plan-review-2026-10-14.md:385/395/397` give d9bf, d9bp and d9br as "**CONFIRMED**", and `:393` gives d9bn as "**CONFIRMED (plan-23/17 r10)**". `plan-23…:87-88` "That gate is SATISFIED: merge `74f8f98`, 0.79.0".
- why it matters: the draft's rationale (`:156-157`) says "T4 has no open spec questions". The substance supports that, since the decisions are all confirmed. But a reader of plan-17, plan-18 or 23.5 sees DRAFTING or PROVISIONAL and will reopen them. This is F1's staleness, inside T4.
- proposed resolution: fix the body status lines to match the frontmatter and the CONFIRMED decision rows. Strike the "OPEN at b84fd8d" clause in plan-23's dependencies. No change in substance.

### Clean areas
- **bug-177 ownership:** a single owner, 23.1 R11 / AC-21. It agrees across plan-23 `#consumers` (`:126`), the registry row 228, POP goal item 6, and 23.3/bug-178/21.5, which only mention it. No second builder.
- **bug-185 ownership:** owned by its own task. 23.3 consumes its R7 entry points (23.3 `:22-24`, bug-185 R7). They do not overlap.
- **The holders bug-177's queue does not cover** (sync, compaction, compile apply) are assigned to 23.3, 23.5 R5 and 23.5 R9 consistently in 23.1 `#non-goals` and plan-23 `#consumers`.
- **The draft's T4 order is consistent with every Depends-on line except Cc-2 and Cc-7:**
  - 23.1's gates (23.0, 23.2, the bug-105 hotfix, 3.7, 26.2) are all met or ordered before it.
  - 23.3's gates (23.1, 23.2, bug-185) and 23.5's (23.0, 23.1, 23.2, bug-112, bug-115/116) are too.
- **bug-099** is owned by 23.1 R3 and **bug-136** rides on 23.5 (`#bug136-rider`). Both are consistent with the registry.
- **23.2's header** leaves bug-185 out of its order. That is harmless: neither depends on the other, and bug-185 says it "needs neither the harness nor the recorder".
- **plan-17/18's internal dependencies** (17.1 → 23.1/23.2, 18.x → 17.2, 18.3 → bug-112 + 23.1 R1.6) are compatible with "T4 tail" at step 9.
- **plan-4** is `completed` and has no open deferral riding a 23.x task.
- **23.1 R11's producer code path** (`handoff.py::_promote_digest`) is unchanged since its cited HEAD `9901589`; the only handoff.py diffs since are the 26.3 save-state commits.
- **bug-097 and bug-207** have no owner today. The draft's T4 placement is the only one, so that is not a contradiction, though bug-097 is a shared embed-worker timeout rather than a writer-lock wait.
