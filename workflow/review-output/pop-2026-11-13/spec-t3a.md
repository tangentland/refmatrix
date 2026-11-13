---
gmd: "0.1"
id: pop-2026-11-13-spec-t3a
title: "spec-t3a report: plan-25 + plan-19 spec wave"
tags: [plan-review, pop-2026-11-13, report]
metadata:
  node_type: report
  created: 2026-11-13
---

# spec-t3a report — spec wave, plan-review-2026-11-13 rev 6 {#root}

Clone `/Volumes/littlebig/refmatrix-spec-t3a`, branch `spec-wave-t3a`, cut from `1cf3b9f`. Spec
text only: no src, no tests, no live store. Every touched file lints with 0 errors
(`python3 tools/gmd/lint.py`). The only warnings are dangling-doc ones for docs outside the scanned
set. No status was set to `approved`.

## Commits

| sha | what |
|---|---|
| `89bddda` | plan-25 side: G3 (the 25.1 waiver), G12 (new task 25.1b), G13 (25.2, 25.3), G24's plan-25 side |
| `de74c97` | G28 + L14 + L26: plan-19 main file and 19.0-19.5; 21.2; 21.4 |
| `841ca70` | 25.1b `#k2` / `#k3` agreed with spec-t3b: one names line (25.1's trailer folded in), one cap of 15 across both member kinds, and TIER-PINNED held removal (10.2 h9 / Q13: freed bytes are never re-spent) |

## Per G-row

### G3 — 25.1 waiver (D-Q2)

The edit is on this branch's copy of 25.1, which is at rev 5. The 25.1 branch is at rev 8, so the
lead reconciles the two at merge.

- `task-25.1-recall-hook-byte-budget.md`:
  - "Depends on" (`:22-24`): 26.4 is merged (`0c74872`); 26.7 and plan-27 are NOT awaited (D-Q2).
    R4's lookup already reads both key shapes, and 26.7 carries the AC that protects the lookup.
  - `:34`: `rel: depends-on -> task-26.7` is now `related-to`.
  - Deltas row "folded riders #w1c-s2, #w1c-m4": hosted by 25.1b (D-Q6).
  - New section `#rev-dq2`: records the waiver, rev 8 moving to 25.1b, the riders moving to 25.1b,
    and that bug-164 closes for the overflow at this task's merge with the hard cap left to 25.1b.
    A `#q8-b` note: under Q8 b, R2b's packed-path exclusion has no save-states left to exclude.
- `plan-25-cliquedb-field-report.md`:
  - `#ordering`: a new amended diagram and bullets. The 2026-11-09 order is kept below as history.
  - New `#approval-order-amended`, plus revision round 6 (`#rev-round-6`).
- POP row 25 is not mine (G27).

### G12 — new task `task-25.1b-hook-output-ladder-and-spill` (drafting)

File: `workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1b-hook-output-ladder-and-spill.md`.

- **Depends on:** 25.1 merged (rev 7, 0.83.0) and 10.3 merged (the marker), per L15. There is NO
  edge to 10.6: per `#k4`, 10.6 adds kind labels to every tier later (CB-5 restatement,
  bsd-pop-r1 S5).
- **Carried from rev 8:** R12, R13 and R14, and AC-16, AC-17 and AC-18, taken from the 25.1 branch
  at `69da299`. R12 is restated as the counted safety net.
- **Amends 25.1 by name** (`#amends`, with `rel: amends` edges):
  - R3: the trailer is folded into the names line, and items degrade instead of being dropped.
  - R8: the arithmetic is tiers 1-3 + names-line members + `(+N)` = hits retrieved.
  - R9: delivered events carry `form` (full / excerpt / pointer / names); a `(+N)` item emits a
    `retrieved` event only.
  - AC-9 / AC-14: "a cut body" becomes "a tier-1 body cut, or an excerpt over its cap or cut
    mid-line".
- **`#k2`, the names line (L15, CB-1):** one `still in play` line with two member kinds,
  over-budget (this task) and held (10.2), and one shared cap of 15. The renderer lives in
  `recall_pack` and is the only place the literal appears in src. The placement and marking of held
  members is 10.2's call.
- **`#k3`, the order, tier-pinned:**
  1. the ladder runs over ALL rows;
  2. held rows leave their tier and go to the names line;
  3. non-held rows keep their tier;
  4. freed bytes are never re-spent;
  5. everything below tier 1 spills;
  6. the clamp runs last.
- **`#k6` / `#k7`:** spill pages live under `stm/<session>.emitted/spill/`. A page older than
  `stm.last_marker` counts as gone, and the spill writer is the only deleter.
- **R0:** per-leg timing on scan-prompt's `query.log` row (`legs_ms`, with a
  ran / skipped / not-attempted outcome per leg), then ≥ 100 runs and a dominant-leg table.
- **R15:** per-leg wall bounds in `hook_budget.LEG_WALL_S`, built only in L44's band. The decision
  row is written before any R15 code. If the band says "not built", bug-182 moves to the T4
  backlog.
- **R16:** plan-2 r9 #s-2. The global leg gets a reserved share, `GLOBAL_LEG_RESERVE_S`, set to the
  measured p95 rounded up to 0.25 s. An omission is counted (`global_omitted`) as well as warned.
- **R17:** plan-2 r9 #m-4. The degrade line names both the slice and the total budget.
- **ACs:** AC-16 through AC-24, with named mutations.
- **Install:** a user-gated window (G31).

### G13 — 25.2 and 25.3

- **25.2, revision round 4:**
  - R0 replays g4 with a standalone script over the delivering prompts of the labelled
    CAUSED / INFORMED uses on prompt channels (11 of 13) and the 16 R12 explicit uses. Counts only.
  - Band (L34): PASS iff 0 and 0 dropped. FAIL takes L43's branch: not built, bug-165 to the T3
    backlog, 25.3's helix half drops, Q10's rule stands.
  - It is re-run if G32 changes the labels.
  - AC-7b: parity with the shipped `terms.prompt_gate`.
  - 10.2 R5's clause about 25.2 holds only on PASS.
  - `#q8-b`: under b, bug-165's save-state noise source is gone, and AC-1's fixture would need
    another kind of noise row.
- **25.3, revision round 4:**
  - R7's repeat memory moves to `stm/<session>.emitted/helix.json`. A key marked before
    `stm.last_marker(...).ts` suppresses nothing, and an unreadable marker resets.
  - The helix half depends on 10.3 and drops with 25.2 if L43 fires.
  - The STM half always builds, and 19.0's remainder waits only on it.
  - AC-11's path is updated; new AC-12b and four mutations.
  - CB-6's "better still" (a suppressed note moves to the names line) is NOT adopted, because no
    L-row decides it.

### G24 — plan-25 side

- 25.4 / 25.5 are marked closed, superseded by 16.5 (L42), in the principle bullet, the non-goals
  and the task table. The L24 premise note is in revision round 6.
- `#acceptance-amended` gives the new `fixed` list:
  - 164, 181 and 166's STM half;
  - 165 and 166's helix half only on L34's PASS;
  - 182 per L44;
  - 167 and 174 close when 16.5 lands.
  It also adds a cliquedb bus reply to `ae9c57ed7f13` when 16.5 ships.
- q6 is amended for L16. `#approval-order-amended` names 25.4/25.5 closed, 25.1b added, and plan-24
  read as plan-24's re-plan (bsd-pop-r4 X4).
- The closing lines in task-25.4 and task-25.5 themselves belong to spec-t56.

### G28 — 19.0 rest, 21.2, 21.4; L14 realized-by lines; L26 freeze

- **`plan-19-adaptive-memory-budget.md`:**
  - Body status line fixed. It said "Drafting" under `status: approved`; see contradictions.
  - The d9bi header is marked narrowed by D-Q3.
  - A tasks pointer, and the 19.0 dependency row now reads "after 25.3's STM half" (L41).
  - New `#rev-2026-11-13`:
    - `#realized-by` (L14 plus bsd-pop-r1 M3):
      - 19.1 R1-R8 → 25.1; the 19.1 riders → 25.1b; 19.5 R1 → 25.1 R0; 19.4 AC-4's recall leg → 25.1 AC-6;
      - 19.0 R1 → 25.3 R1-R5; 19.3 → 26.7 (virtual scores until 19.2);
      - 19.4's rest → 26.6 (merged `8a867bc`; R3 residual open; the R1 tick goes to 17.2 per L28);
      - 19.6 R8a → 10.3; 19.6 R5 for the composite → 10.6 (after L17's Table A);
      - 19.6 R5/R6 for the per-prompt payloads → nobody (Q11).
    - `#remaining`:
      - 19.0's remainder goes in item 4, and bugs 100, 103 and 104 ride it;
      - 19.1 has nothing left to build;
      - 19.2 is frozen;
      - 19.5 R2-R4 and its rider are frozen (L26);
      - 19.6's phasing, cache and Table C are frozen, and Table C later counts only R12 explicit
        uses plus `cited_in_answer` (L18).
    - `#d9bi-narrowed`: the four helix interfaces and their states; D1 superseded.
- **19.0-19.5:** each gets a short record-only `#rev-2026-11-13` section and a status line:
  - 19.0: L41 order and bug ownership;
  - 19.1: fully realized, do not build;
  - 19.2: frozen;
  - 19.3: built by 26.7;
  - 19.4: built by 26.6, 25.1 and 17.2;
  - 19.5: R1 done, R2-R4 frozen, the rider pending O4.
- **19.6 NOT edited.** plan-10's revival branch edits that file (`#split-plan-10`) and would
  conflict. L18 is recorded in the plan-19 main file only and should be written into 19.6 after
  plan-10 merges.
- **21.2 and 21.4:** each gets `#rev-2026-11-13`: D-Q5 (plan-24 D1's hold dropped), D-Q3 (queue
  item 6), and a re-read against bug-216's GREEN `37d99a0`, read with `git show`.
  - 21.2:
    - R6 only touches GMD targets, so the 9 code-symbol gold is unaffected;
    - R9's transparent hop applies only to doc and memory anchors;
    - no `LINKAGE_LABELS` entry is added;
    - the baseline is taken post-bug-216.
  - 21.4:
    - the doc gold's anchor semantics are unchanged;
    - R2 and every R3 candidate run on ONE catalog copy taken after bug-216's live re-derive;
    - bug-216 R11 makes CLAUDE.md a ranked doc, which does not conflict with R4.
  - **21.4 `#q8`:** doc-stratum gold is drawn only from outside `workflow/`, so the set holds under
    Q8 a and c (the brief's rule). It can be lifted at the set's approval if Q8 = c.

## Open decisions (recommendation first)

### In 25.1b `#open-decisions`

1. **O1 — the fetch command's spelling.** Rev 8 wrote `rmx recall --page <n>`, but `rmx recall` is
   the graph hybrid retrieval (`cli.recall_cmd`), not memory recall. The spilled items are
   `memory_recall`'s.
   - **a (recommended):** `rmx memory recall --page <token>`, the verb `memory_recall(page=…)`.
   - b: a new `rmx recall-page` command and verb.
2. **O2 — page addressing.** The agent's Bash call has no session id (`HOOK_ENV` exports none), and
   the newest-ring fallback is bug-100's defect.
   - **a (recommended):** the token encodes the session, `<session[:8]>-<seq>`, resolved by prefix
     under `stm/`. An ambiguous prefix gives one `Error:` line.
   - b: the full session id in the token (about 30 B more per paged payload).
3. **O3 — where R0's ≥ 100 runs come from.**
   - **a (recommended):** `legs_ms` lands as the branch's first commit and is merged and deployed
     ahead by fast-forward. It is a `query.log` field, not an argv change, so there is no hook
     regeneration. Live runs are collected while R12-R14 are built, and R15 is decided before
     GREEN closes.
   - b: replay on a catalog copy in the dev tree. There is no live contention there, so L44's
     lock/daemon branch can't show; the result is biased toward "build".
   - c: decide R15 after the whole task deploys. R15 changes no argv, so L39's one hook window
     still holds, but bug-182 stays open longer.
4. **O4 — 19.5's `#w1c-rider`** (plan-2 r5: rerank never ran on scan-prompt at 5 s, 28/28 skipped).
   It sits in 19.5's frozen remainder (L26), and D-Q6 names only #s-2 and #m-4, so plan-2 cannot
   close.
   - **a (recommended):** R0 records the rerank leg's outcome anyway, so it reports the rate and
     closes the rider.
   - b: leave it frozen; plan-2 stays open until the handhold experiment reports.
5. **O5 — how "sits in" is decided for L44.**
   - **a (recommended):** classify each > 5 s run by its dominant leg.
     - ≥ 50% controllable: bound every controllable leg that dominates ≥ 10% of those runs.
     - ≥ 50% `lock_wait` / `daemon_wait`: R15 is not built.
     - A split: bound the controllable share, and list the wait share on the T4 backlog.
   - b: total wall share by class over the > 5 s runs, at the same 50% line.

### In 21.4 / 21.2

6. **21.4 O-a.** R1's drafting agent may not read "the ranking code" (`context.py`, `reranker.py`,
   the rerank ops in `daemon.py`). bug-216 R9 makes the `denotes` walk and the PageRank fold part
   of ranking.
   - **Recommended:** add that code (the typed-edge expansion and the PageRank edge set bug-216
     names) to the forbidden list, by d4c's own rule.
7. **21.4 O-b.** C9 makes 21.4's set THE ranking-eval harness, but L29's fold evaluation (G30,
   spec-t3c) runs in the measurement lane "after bug-216 is live", before 21.4 exists (item 6).
   - **Recommended:** G30 uses its own pre-registered per-type bands and records that C9's harness
     didn't exist yet; 21.4's harness re-scores the fold once frozen.
8. **21.4 O-c.** R4's regenerated `.refmatrix/CLAUDE.md` ships in a C11 install window. Its batch
   partner 21.3 is frozen, and G31 lists no window for 21.4.
   - **Recommended:** name it in G31 and ride the first user-gated window after R4 lands (10.4's in
     item 6, else 16.3's in item 10).
9. **21.2 AC gap.** After bug-216, an entity can be reached twice on a doc or memory anchor (from
   the doc's rows and from a denoting concept's rows). R2 dedupes it as written, but AC-4 covers
   only the 9 code names.
   - **Recommended:** add one fixture row: doc B, concept `b-doc` denoting it, and X linked from
     both, asserting X appears once.

### Plan level

10. **L43 vs 25.3's helix half.** The helix half needs 25.2 only so its ACs use prompts that pass
    the gate; with no gate, every prompt passes.
    - **Recommended:** keep L43 as decided, but note that the helix half could build without 25.2
      if the lead prefers.
    - Also: the queue's backlog line ("T3 196 (+ 165 if L43 fires)") omits bug-166's helix half;
      add it.

## Contradictions the plan review missed

1. **plan-19's body status said "Drafting" under `status: approved`.** It is not in L25's or
   Cc-9 / CD-9's lists (plans 16, 17, 18, 22, 23). Fixed in `de74c97`.
2. **Rev 8's `rmx recall --page` names the wrong command** (`rmx recall` is the graph hybrid
   search). → O1.
3. **Rev 8's spill page has no session addressing** for the agent's Bash call; it would fall into
   bug-100's newest-ring shape. → O2.
4. **19.5's `#w1c-rider` is a third plan-2-derived rider**, left in frozen 19.5. D-Q6's "plan-2
   closes when its riders land in 25.1b" names only two. → O4.
5. **L44's band has no operational rule for "sits in"**, and its ≥ 100 runs need deployed timing
   fields, a sequencing gap against L39's "one hook window". → O3, O5.
6. **10.3 R2 named only 10.2 and 19.6 as `stm.last_marker` callers** ("nothing else reads the
   file"); 25.1b and 25.3 R7 now call it too. spec-t3b agreed to add both.
7. **10.2 conflicted with 25.1b in three places:**
   - R3 said "the trailer format … untouched";
   - R6 added `form`;
   - the removal order would have re-spent freed bytes against h9 / Q13.
   Converged with spec-t3b on tier-pinned removal, one line, one cap of 15, and `form` from 25.1b
   (`841ca70`, plus spec-t3b's 10.2 re-spec). spec-t3b first cited the id
   `task-25.1b-hook-output-ladder`; the real id is `task-25.1b-hook-output-ladder-and-spill`, and
   spec-t3b will sed it.
8. **G31 lists no install window for 21.4's briefing.** → O-c.
9. **L29's `denotes` fold evaluation and C9's single ranking harness are ordered inconsistently.**
   → O-b.
10. **The queue's backlog line omits bug-166's helix half for when L43 fires.** → item 10.
11. **26.7 builds 19.3 with virtual scores, and the real score source is frozen 19.2 (D-Q3).** So
    19.3's value fold stays virtual for the whole goal. This is a consequence to state, not a
    defect.
12. **`PROJECT_PROFILE.md:79` (L24's premise correction) is in no wave agent's ownership.** The lead
    or its owner needs to edit it.

## Notes for the merge

- My 25.1 edits are on rev 5 text (header `:22-24`, `:34`, the deltas row, and a new `#rev-dq2`).
  The branch's rev 6-8 sections sit beside them. Rev 8's text leaves the branch at merge (D-Q2);
  25.1b holds it now.
- plan-25 keeps `rel: depends-on -> plan-27` at plan level, because D-Q2 waives the order for 25.1
  only.
- 25.1b and 25.3 link `[[task-10.3-plan-10-injection-dedup]]`. On master that id is still the old
  10.3 until plan-10 rev 5 merges (L23), which comes first in the queue.
