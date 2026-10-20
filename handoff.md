---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-20 (session 47bc8f5e). Prior handoff archived at
`workflow/past_handoffs/017-wave1-releases-0801-ac6_2026-10-19.md`.

rel: supersedes -> [[handoff-017-wave1-releases-0801-ac6]]

## State {#state}

- **Deployed: 0.80.1** — unchanged this session. `master` = `origin/main` = deploy = `8824ae2`.
- **Dev tree** `wave0-spec-reviews`: docs/plan commits only this session (plan-24, explorations,
  probes); not merged to master, not pushed. Untracked: `tests/fixtures/` (the RAW AC-6 cut, 24 MB —
  never `git add -A`; move it off the tree once AC-6 merges) and `eval/spike_hypertree/` (the M1-M7
  spike, in flight).
- **Background work at save time:** all agents finished. Only the hypertree M6 timing run for
  viascope then refmatrix is still running as a plain process (`m6_placement_write.py`); it writes
  `eval/spike_hypertree/results/m6_{viascope,refmatrix}.json` — commit those two files when they
  appear and fill the doc's NOT FINISHED rows.

## Task 3.7 — verb-it backlog {#t37}

Clone `/Volumes/littlebig/refmatrix-task-3.7`, branch `task-3.7-verb-it-backlog`, HEAD `364a90e`
(+ an uncommitted summary edit by the implementer).

- Spec rewritten into a buildable per-family spec through 6 ch-bsd spec rounds: 45 verbed + 4
  re-decided of 49; curator queue became a spool dir; stats + focus export verbed.
- Batches A/B/C built TDD (RED by test engineer, GREEN by implementer): 8 new MCP tools
  (`rmx_graph`, `rmx_canon`, `rmx_matrix`, `rmx_curate`, `rmx_session`, `rmx_refine`,
  `rmx_curator`, `rmx_taxonomy`) + `rmx_focus` actions; LEGACY_UNPAIRED 140 → 92; `verb-it`
  category gone. Final batch suite: 3666 passed / 3 failed, all three identical at base `591a2fb`.
- Post-build ch-bsd (2B/2S/2M, mutations 16/18) + code review (1H/8M) → **remedy r1** decided in the
  spec `#remedy-r1`, RED `56a5815` (28 failing), GREEN `68df326`..`364a90e`, summary `4c98e3c`
  (incl. the user's OBJC fork-safety fix in `HOOK_ENV`). Clone clean at `4c98e3c`.
  Remedy suite: 3694 passed / 6 failed — 3 known base failures (bug-155 GMD gate, bug-156 AC-6,
  bug-091 test_watch), 2 load/cold-start flakes (plan4 graceful_stop; 21.1 ac11a), and 1 TEST
  conflict. **Next, in order:** (1) test engineer: `test_write_spool_is_tmp_fsync_rename` must allow
  the directory fsync after the rename (R-L), and point `tests/test_concept_timeline.py` at
  `graphread` so the kept `_concept_files` alias in cli.py can be deleted (R-RM7); (2) ch-bsd
  re-audit of `6fd9b7c..HEAD`; (3) spec status → completed; merge `--no-ff` to master, release,
  deploy.
- **Deploy steps for 3.7:** `rmx install-hooks --apply` (curator hook lines + OBJC env), restart
  daemons (spool writer), `/mcp` reconnect (8 new tools).
- Bugs: fixed bug-139..150 + 155-160 range per the summary; OPEN bug-151..154 (refine
  accept/reject operator paths).

## Plan-24 — mod transport (decided, specced) {#p24}

`workflow/plans/plan-24-mod-transport.md` (drafting). The user decided the move for tighter
integration (not spawn cost). Specs 24.0-24.8 + 24.2a written and reviewed through ch-bsd r6
(findings 9 → 17 → 11 → 5 → 3 → 2, last two rounds 0 BULLSHIT). r6's 2 findings are folded
(24.2 rev-r7, committed with this handoff). **Next:** one confirming ch-bsd round (r7), then ask the user to
approve plan-24. 24.0 + 24.1 can start in Wave 1; 24.2a/24.2/24.4 need 3.7 merged.

Probes (two batches, `eval/mod_probe/`, plan `#probes`/`#probes-batch2`): subagents get and call
mod tools and share `$.state`; `prompt.compose` skips subagents; fetch aborts at 30 s; `/clear`
wipes `$.state`. Memory: [[reference_claude_code_mod_probe_facts]].

## Hypertree — associative power {#hypertree}

`docs/architecture/explorations/hypertree.md`. The user: the goal is maximum associative power,
not endorsing an implementation. **M1-M7 spike done** (`5518a87`,
`docs/measurements/hypertree-spike-2026-10-20.md`): the cross-cutting incidence graph carries the
association (concepts are not tree-coherent; tree-scoped recall loses hits; tree render saves only
3.4%); bands imply **Option B scoped** — `gmd` section + `code` def placements written in the
entity transaction for in-file addressing; no LCA band, tree render, subject tree (except viascope
in principle) or Dewey ids. Open: whether same-file proximity helps as a RANKING feature (the spike
measured it only as a scope). Next: walk the exploration's open questions with the user.

## Other explorations this session {#explorations}

- `docs/architecture/explorations/claude-code-mod-transport.md` — the mod exploration (facilities
  table, HTTP tiers, verb host, distribution).

## Waiting on the user {#user}

- Approve plan-24 (after the r7 fold + confirm round).
- Hypertree open questions (after the spike).
- Unchanged: 19.5 R1 (now held for plan-24), 20.1 gold labels, 21.4 question set, 19.6 tables.

## Open bugs / notes {#open}

- AC-6 clone `/Volumes/littlebig/refmatrix-ac6` still waits on its GREEN (renumber its registry row
  from bug-137 to bug-138 at merge).
- bug-136 rider on 23.5; IMPRESSIONS.md over its line cap; GMD repo-scope gate (pre-existing
  errors in an old ch-bsd ledger).
