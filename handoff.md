---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-15 (session d6dcee49). Prior handoff archived at
`workflow/past_handoffs/015-0781-0783-release-wave0-r6-r7_2026-10-15.md`.

rel: supersedes -> [[handoff-015-0781-0783-release-wave0-r6-r7]]
rel: depends-on -> [[plan-review-2026-10-14]]

## State {#state}

- **Wave 0 is CLOSED.** Every Wave 0-1 plan is APPROVED after its ch-bsd loop (rounds 8-15):
  plans 16 (d9ck), 17 + 23 (d9cn), 19 + 21 (d9ce), 22 (d9cm), plan-18 specs (d9co; 18.1
  COMPLETED). Decisions d9be-d9cp in `workflow/plan-review-2026-10-14.md`; settled ones CONFIRMED.
- **Branch:** `wave0-spec-reviews` (NOT pushed; merges `--no-ff` to master with the release).
  `master` = `origin/main` = deploy = `b381b6d` (0.78.3). Nothing deployed this session.
- **Code ready or in flight (littlebig clones; branches pushed to the dev repo when clean):**
  - `task-18.1-catalog-measurement` (`8281a7f`) — ch-bsd r3 CLEAN; in dev repo; merges with release.
  - `bugs-112-113-118` (`/Volumes/littlebig/refmatrix-bugs112-118`, `a2911a3` + MEH remedy in
    flight) — ch-bsd r3 mergeable/deployable; 3 MEH being fixed (m-r3-1 facts.log compaction
    after copy2 swap failure — do not ship without it). Includes cherry-pick of 0611d2f.
  - `task-23.0-test-sandbox` (`/Volumes/littlebig/refmatrix-task-23.0`, `ccdefef` + r1 remedy in
    flight) — ch-bsd r1 DIRTY 2B (shutil relative-path bypass; 18 silent skips); merges on tier 0
    + decoy evidence once clean (d9cp).
- `learn.off` global marker still SET (d9bj: off until 16.2+16.3 deploy; no `rmx learn on`).

{#state-body}

## Next {#next}

1. Finish the two remedies above, re-review each to CLEAN (ch-bsd), then ONE release: merge
   bugs-112-113-118 + task-23.0 + task-18.1 into master (`--no-ff`), reconcile registry numbering
   (main tree has bug-119..128; the bug branch numbered 122/123 directly after 118), bump version,
   full suite in the main tree (now sandboxed — should lose the 32 baseline failures), run
   `scripts/sandbox-proof.sh` once (d9cp/S5), deploy (user approved: ff ~/refmatrix,
   `rmx daemon restart --relaunch`, hub `rmx hub stop` + one `launchctl kickstart`), push.
2. **User question open:** bump `.venv-eval` duckdb 1.5.2 -> 1.5.3 (pyproject pins >=1.5.3;
   1.5.2 crashed on a stale-reader close before the drain fix).
3. Wave 1 implementation per d9bi: 21.1 -> 19.0/19.1 -> 19.2, 19.6 (helix substrate); 23.1/23.3;
   23.5 after bug-112 merges.
4. Frozen inactive slot recovery (atldb/refmatrix/viascope) — needs bug-125 (merge leaves
   derived tables empty) fixed first; then dry-run on littlebig copies.
5. 23.0 tiers 1/2 (rmxtest user, Tart VM) need operator setup.

{#next-body}

## Lessons recorded {#lessons}

- `feedback_follow_approval_pattern_wave01`, `feedback_bsd_iterate_before_surfacing`,
  `feedback_converge_repeated_shapes`.
- PATTERN `workflow/bullshit/2026-10-15-PATTERN-prereg-check-unrun-census.md`: a bypass rule or
  mutation registered without running it against the code fails three rounds running.

{#lessons-body}
