---
gmd: "0.1"
id: handoff-007-plan14-grep-measured-plan15-derive
title: "Handoff 007 (archived): plan-14 measured the grep loop; grep drop-in family closed; plan-15 derive tracking"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-06 (session 3ef71120). Prior handoff archived at
`workflow/past_handoffs/006-grep-family-plan14-deploy_2026-10-05.md`.

rel: supersedes -> [[handoff-006-grep-family-plan14-deploy]]

## State {#state}

`master` = **42ae7fc**, clean tree, 42 ahead of `origin/main` (nothing pushed).
Deploy `~/refmatrix` = **0072f11 / 0.74.1**, fleet 8/8 + hub on 0.74.1, zero STALE.
**The deploy is 5 commits behind master** — plan 15 (15.1-15.3) is committed and NOT deployed, which
is why `rmx derive log` on the live store answers "no derive history yet": the live catalog has no
`derive_history` table until the next deploy runs `init`. {#state-body}

Full suite at the last complete run (`workflow/review-output/pytest-grep-family-full.log`):
**2348 passed, 3 failed** — all three are bug-069, pre-existing at this session's branch point.
GMD lint 0 errors / 539 docs. `rmx install-hooks --check` in sync. {#gates}

## What this session did {#did}

Started from one question — "do we have any measure of how effective the learning aspect of
funnelling grep through rmx is?" — and the answer was no. {#did-lead}

- **Plan 14 (complete)**: `answered_by` on every grep telemetry row, the `RMX_LEARN`/`learn.off`
  toggle across six learn sites plus the rewrite hook, and a two-arm replay of this project's real
  1,557-call grep history: **index share 18.5% → 31.7%**, precision median 1.000. The pre-registered
  negative threshold was not met. Report: `docs/measurements/grep-learning-replay.md`.
- **bug-067** — found BY that instrument: a learned `query/PATTERN` was unreachable by the query
  that created it (alias rows hold no evidence). Reachability 24/76 → 49/60; multi-word 0/18 → 14/15.
  The grep read SQL was in three divergent copies and is now one `Store.grep_evidence`.
- **The grep drop-in family closed**: bug-062, 063, 064, 066. Two of those rows' premises did not
  survive measurement — 062 needed no product decision (a bare command's fd 0 is CHR, a pipeline's
  is a FIFO), and 066's recommended fix would not have touched the failing case.
- **bug-071, my own regression**: that same fd-shape rule counted `S_ISSOCK`, so every BACKGROUNDED
  `rmx grep` hung. Caught minutes after deploying, hotfixed as 0.74.1.
- **bug-068**: the gmd linter's two hardenings had been silently reverted by an upstream sync.
  Restored here AND made canonical upstream (`~/claude_tools/gmd` `8a65aa2`) with fixtures that must
  fail. Also ported the SPEC's `#project-namespace`, `#declare` and `#fences` sections.
- **Plan 15 (15.1-15.3)**: per-pass derive identity with a scheme tag, `derive_history` + counts
  (18 ms on the real partition), and `rmx derive log | diff | status`.
- Deployed 0.74.0 then 0.74.1; hooks installed from the deployed build; the 12 agent-id namespacing
  edits and `tools/gmd/audit.py` committed; 4 dangling ADR wikilinks in memory retargeted.

## Next {#next}

1. **Deploy plan 15** — bump, ff `~/refmatrix`, `rmx hub relaunch-fleet`, then hub restart (the hub
   does NOT self-restart when it is OLDER than its workers; that had to be done by hand this
   session). After that the live store gains `derive_history` on init and `rmx derive log` has data.
2. **Task 15.4** — sessions/embed/pagerank never stamp, so this partition carries one row out of
   five. The spec pre-registers the trap: an unstamped pass must NOT read as `behind_code`.
3. **bug-070** — the precision cost of bug-067's canonical predicate on short punctuated patterns
   (`error:` 0 → 62 rows). Tightening it gives back the ingest-side gain, so it needs both numbers
   and a decision.
4. **bug-069** — the three federation/locate failures, logged undiagnosed. The locate one may be
   plan-3 r8 regressing or its test asserting something r8 never shipped; one of the two is wrong.
5. **bug-065** — `rmx save-state` writes memory rows `memory recall` cannot see (the bridge inserts
   without vectors). Still open, and it bites every save-state including this one.

## Open, not forgotten {#open}

- Nothing pushed to GitHub: refmatrix `master` is 42 ahead of `origin/main`, and
  `~/claude_tools/gmd` has one local-only commit (`8a65aa2`).
- `rmx hub launchctl status` reports plist drift on the hub's env `PATH` — pre-existing, untouched.
- `RMXGREP_MODE=rich` lives in `.claude/settings.local.json` (written by `install-hooks`); bug-066's
  config half is still the user's call.
- `docs/measurements/` and `workflow/measurements/` now both hold one report; the split wants a
  decision.

## Lessons recorded as memory {#lessons}

[[project_grep_learning_measured]], [[project_derive_impact_tracking]],
[[feedback_lsof_the_stuck_process]], [[feedback_clean_corpus_hides_a_dead_gate]].
