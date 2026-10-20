---
gmd: "0.1"
id: handoff-016-wave0-close-plan-review
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

1. **Release 0.79.0 is BUILT, not landed.** Clone `/Volumes/littlebig/refmatrix-rel079`, branch
   `release-0.79.0`, head `0518113` (merges `74f8f98` bugs-112-113-118, `530660e` task-18.1,
   `bb0ed1f` wave0-spec-reviews; registry reconciled: the linkage merge-by-name bug is bug-128).
   Full suite: 0 regressions by error text (new failures = clone-only dev-tree checks, HF cache
   hidden by the temp HOME, or identical on master). Commit subject still says "bug-113/123" —
   should read bug-113/128. Landing needs the user: the classifier refused pushing the clone to the
   dev repo's `master`. Then deploy: `git -C ~/refmatrix pull --ff-only origin master`,
   `rmx daemon restart --relaunch` fleet-wide, hub `rmx hub stop` + one `launchctl kickstart`,
   verify `rmx version -v`, push to GitHub from dev.
2. 23.0 is CLEAN (ch-bsd r3, `d9ec741`; branch `task-23.0-test-sandbox` in the dev repo). Ship as
   0.79.1 after 0.79.0 lands (merge `--no-ff`, bump, full suite now sandboxed); then
   `scripts/sandbox-proof.sh` once on the main tree (d9cp). Tiers 1/2 need operator setup.
3. **User question open:** bump `.venv-eval` duckdb 1.5.2 -> 1.5.3.
4. Wave 1 implementation per d9bi: 21.1 -> 19.0/19.1 -> 19.2, 19.6; 23.1/23.3; 23.5 after 0.79.0
   lands (bug-112 merge gate).
5. Frozen inactive slot recovery needs bug-124 (merge leaves derived tables empty) first.

{#next-body}

## Lessons recorded {#lessons}

- `feedback_follow_approval_pattern_wave01`, `feedback_bsd_iterate_before_surfacing`,
  `feedback_converge_repeated_shapes`.
- PATTERN `workflow/bullshit/2026-10-15-PATTERN-prereg-check-unrun-census.md`: a bypass rule or
  mutation registered without running it against the code fails three rounds running.

{#lessons-body}
