---
gmd: "0.1"
id: admitted-audit-2026-11-24
title: "Admitted-items audit 2026-11-24: every pre-mod item checked for admission, plan, next-task spec and approval"
tags: [audit, pop, freeze, queue, specs, approvals, read-only]
metadata:
  node_type: measurement
  created: 2026-11-24
  author: admitted-audit (read-only agent)
  base: 0a87563b
---

# Admitted-items audit, 2026-11-24 {#root}

The user, 2026-11-24: "we should review all of the admitted items to make sure they have specs
and approvals." Read-only audit at `master` `0a87563b`, per [[agent-brief-admitted-audit]]. No
plan, spec or POP file was edited. {#purpose}

rel: implements -> [[agent-brief-admitted-audit#output]]
rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[plan-of-plans#freeze]]
rel: depends-on -> [[plan-of-plans#freeze-amended]]
rel: depends-on -> [[plan-of-plans#rulings]]
rel: depends-on -> [[plan-32-retriage-2026-11-24#rows]]
rel: evidence-for -> [[plan-of-plans#queue-stale]]

## Method {#method}

- **Standard:** Q55 = a (L221). A plan is ready when the plan is approved and its NEXT task has an
  approved spec. Later tasks are not required. `metadata.status` was read but never counted as
  evidence; every approval below names an L-row, a ch-bsd GO the POP cites, or the user's words.
- **Next task** from [[plan-of-plans#queue]] order, `git log --oneline master` and
  [[pop-finished]].
- **Stale** names the code change or the later ruling. Two kinds are kept apart in the verdict:
  `stale (RED)`, where the RED author's R0 re-verify absorbs it ([[plan-of-plans#queue-stale]]),
  and `stale (revise)`, where the spec says something that is now wrong or a held revision is
  unmerged, so it needs a spec edit before RED.
- Code facts were read from the tree at `0a87563b` (line counts, function names, branch heads);
  the held revisions from their littlebig clones' `HEAD`. {#method-list}

## The table {#table}

| item | POP row | admitted by | plan (file, approval evidence) | next task | its spec (file, approval evidence) | stale? | verdict |
|---|---|---|---|---|---|---|---|
| Compaction as a handoff | C1 | L195 (Q54 = b) | single-task spec `task-compaction-as-handoff.md`, approved by L195 ("`drafting` → `approved` as it stands") | none to build: merged `641401c4`, released 0.85.0 `0a9896eb`, deployed 2026-11-24 (L201, L208). Residue: `/mcp` reconnect, the live `/goal` record shapes. The fleet `CLAUDE.md` line the row keeps as a deferral is dropped by L226 (re-triage `#rows`) | — | its live defect bug-318 is in flight but unadmitted (row below) | **done**. Still on `#queue`, not in `pop-finished.md` |
| Hook writes enqueue and return | C2 | L212 | single-task spec `task-hook-writes-queue.md`, approved by L212 (commit `04c25731`) | RED converts the 2 old-contract tests and runs the mutation pass on GREEN `b0b05bd8`, then one ch-bsd pass (L165) | same file, L212; L215 settles RED's reading of a queued PreCompact promote | no (written 2026-11-24, after everything it depends on). bug-248 Seen 2 (`526ad536`: the drain is a new `Store.transaction()` caller; bug-248 is post-mod) is a risk for the bsd pass to weigh | **ready** (in build) |
| ch-bsd consequence package | B1 | L213 | no plan by design: a process package L213 orders (package, then re-probes, then F4 and F7) | F4 (the leaderboard becomes a tally by self-audit question), F7 (`IMPRESSIONS.md`'s pointer list to its own file) | no spec or brief. `ch-bsd-assessment-2026-11-23.md` `#f4` and `#f7` each hold a one-paragraph proposal L213 adopts. Done so far: package `d0598dc9`, re-probes `bsd-reprobe-c7550ad5`, ledger L216/L218 | L226 gives B1's severity text one home, the `bsd-pass` skill (I1.d); F4's tally should land there or be re-pointed when I1.d builds. The open GATE `t05-c2-MB1d` (bug-295, L218) has no queue row | **no-plan-by-design (ok)**; a brief for F4/F7 is owed at dispatch |
| Plan-32 instruction architecture | I1 | L214 (plan approved); L220, L221, L226 | `plan-32-instruction-architecture.md`, approved by L214; ADR 0007 Accepted by L226 (Q60 = a); task list = re-triage `#i1-tasks`, accepted by L226 | I1.a (the contradiction edits, docs; waits on nothing) and I1.b (the substrate, probes P1-P10, 10.3; waits on nothing, merges before row 4's sha or after 29.5) | none. `workflow/plans/plan-32-tasks/` holds only the re-triage. I1.a's content is listed in ADR 0007 `#contradictions` plus L221, I1.b's in the ADR, but plan-32 `#steps` 5 and re-triage `#i1-tasks-lead` require a one-page spec for each. Later tasks (I1.c to I1.i, including L225's review as I1.i) are unspecced and not required yet | no | **needs-spec** (I1.a, I1.b) |
| cat-herder into templates, agent composition | H1 | L214 (merge ruled); L219; L226 (H1.a to H1.g) | no plan file. The plan is re-triage `#h1-tasks` plus ADR 0007 `#composition` and `#distribution`, both accepted by L226; input `cat-herder-merge-2026-11-24` | H1.a, reconcile the 9 doubly-shipped files. The POP's waits are met (B1's package `d0598dc9`; the ADR Accepted, L226) | none | the POP row still reads `admitted` with the pre-L226 scope (no H1.a to H1.g) | **needs-spec** (H1.a) |
| TDD practice pack `practice/tdd` | none (inside I1, H1) | L229 (Q64 = a), L230 | ADR 0007 `#practice-packs` (amended `cdffa9ec`, merged `0f9f2752`); re-triage `#i1-tasks` / `#h1-tasks` L229 amendments | its first units (R047, R048, R065) are authored in the pack during I1.c; selection and stance render in H1.c | none. Not required yet: I1.c waits on I1.b, H1.c on I1.b | no | **needs-spec** (via I1.c and H1.c; not next) |
| Lean reset follow-through | P1 | L164, L165, L166 | no plan file; the POP row defines (a) to (c). L226 moves (c) onto I1.e | (b), the proportionality review of every plan and spec on the queue (P lane, read-only) | none (no brief). (a) is done: `test-suite-audit-2026-11-15.md` | its target list has grown since L164: C1, C2, I1, H1, A1, W1, E1, T1 and T0.9 joined; 29.5's spec is 1,558 lines | **needs-spec** ((b) needs a brief) |
| Test isolation | T0.9 | L170 (Q46 = a) | `task-t0.9-test-isolation.md` (one spec, four parts), approved by L171; D2 to D4 by the user ("d2-4 agree", POP row) | (a), the Docker probe | same file `#a-probe`, L171 | yes. (b) says `ptest.py` "is 29.4's runner, started here" and adds `lane_of` before 29.4 stage 4's `tier_of`, but stage 4 merged first (`bfc34358`: `scripts/ptest.py`, `tests/tiering.py::tier_of`, no `lane_of`). L226 moves (b)'s docker install to pack detection and its lane text to the `lane-verify` skill (I1.d), "which should land first". (d) is partly overtaken by `scripts/lane-mini.sh` / `lane-local.sh`, and the mini has been unreachable since 2026-11-24 | **stale (revise)** for (b) to (d); (a) can be dispatched as written |
| Agent messaging | A1 | L179 (Q50) | no plan file. L179 sets the shape: "spec just in time, one page" | (b), the agent→lead post, re-specced by L226 as the first route of 24.3's hub HTTP socket. (c) is post-mod (L226) | none | the POP row is not rewritten: it still says "(c) is live again" | **needs-spec** ((b)) |
| Model workers | W1 | L180 (Q51) | none. L180: "(d) → (c) as a plan after R1", spec just in time; no plan file | (d), the models move to their own launchd service | none | "waits on R1": part of R1 shipped in 0.85.0 (L201). The rest of R1 (T0.7; 31.3, 31.4, 31.1, 31.6) is unbuilt, so the wait needs restating | **needs-plan** |
| Environments from the lock | E1 | L172 (Q47 = d) | no plan by design: a lead environment step | rebuild `.venv-eval` from `requirements-dev.lock` while no agent is mid-run | none; L172 and the POP row stand in | the mini's venv, the canary and python3.10 all wait on the mini (unreachable since 2026-11-24) and on the user's setup | **no-plan-by-design (ok)** |
| Test hygiene | T1 | L168 (Q43 = a, Q44 = a) | no plan file. The plan is `test-suite-audit-2026-11-15.md` plus L168; isolated small-fix agents cleared by L174, L176 | step (2), the cheap waits. Step (3) follows; step (4) needs T0.9 (c). bug-305 (L197) is also T1's | no brief for (2). Its input is the audit's `#speed` table | the `#speed` table (2026-11-15) predates 29.4 stage 4's `timing` tier, T0.3's wall-clock census and the `with_budget` knobs (L141, L159); re-measure before acting | **needs-spec** ((2) needs a brief) |
| 29.4 stage 5: T0.7 | 4 | freeze item 1; L104, L106, L118 (Q29 = a) | plan-29: L104, L106; its specs merged and approved (`pop-finished` `#finished-compiled-table`: `33d85bb` + `d227cc6`, `b12724d`); the T0 spec by L122, L123 (`0e55687`) | T0.7 + 29.4d: the r13 remedy and the clean full suite. Its waits (2, 3, M1) are all done | `task-t0-suite-trust-sweep.md` `#t0-7`; `task-29.4-suite-health.md` R8, R9, `#ac-7`; approved by L122, L123 | yes, absorbed at RED. The cited sites moved (`REFILL_TIMEOUT_S` use now `subproc.py:471`; the test now at `:1008`), which R0 re-verifies. 29.4 `#r10`'s "one release point after stage 5" is amended by L201, and its "one ch-bsd round per sub-task range" predates L165. The POP row omits 29.4d | **stale (RED)** |
| Plan-31 early items | 5 | freeze item 3; L125 | plan-31 approved on ch-bsd MEH-only GO (L125): L140 for 31.5 / 31.3 / 31.4, merged `606c0c83`; L149 for 31.1 / 31.6 / 31.2, merged `662abfa8` | 31.3 (31.5 step 0 is done: release A `655fad9f`, shipped in 0.85.0). Then 31.4 → 31.1 → 31.6 (L139 order) | `task-31.3-ledger-anchor-guard.md`, approved by L140; D7's precondition applied (`a5a43161`) | yes, absorbed at RED. 31.3 and 31.4 both edit `scripts/lint-gmd.sh`, which T0.2 changed after their approval (`78489af0`: the `RMX_DEV_PYTHON` switch, L142). The re-triage's "keep (merged)" is wrong for 31.3, 31.4, 31.1 and 31.6: only their specs merged, and their code is unbuilt | **stale (RED)** |
| 29.1 registry triage | 6 | freeze item 1 | plan-29 (above) | not next in plan-29 (waits on 4) | `task-29.1-registry-triage.md`, approved with plan-29's specs | minor: the registry has grown to bug-318; the triage counts at run time | **ready** |
| 29.5 split the giant modules | 7 | freeze item 1; L105, L108, L113, L115 | plan-29 | not next (waits on 4 and 6; S1 is done) | `task-29.5-split-giant-modules.md`, approved with plan-29's specs | yes. Its census and layout tables use `cli.py` 15,212 and `store.py` 9,246 lines (now 15,653 and 8,915), and still place `migrate-to-duckdb` in `cli/catalog_cmds.py`, although S1 deleted it (L182, merged). C1 and C2 added code to `cli.py`, `verbs.py`, `daemon.py` and `handoff.py`. ADR 0006, its first step, does not exist yet (`docs/adr/` has 0000-0005 and 0007) | **stale (revise)** |
| 29.3 ∥ 29.2 → 29.4f → 29.6 | 8 | freeze item 1; L108-L111 | plan-29 | not next (waits on 7) | 29.3, 29.2 (amended for S1, `#r7-s1-sqlite`, L191 b-2, `f7737a5e`), 29.4f and 29.6, all approved | built on the split tree; 29.6 re-points them by design | **ready** |
| 31.2 (with 22.6 R4) | 9 | freeze item 3, item 4 (22.6 R4 folded) | plan-31 (L149) | not next (waits on 7) | `task-31.2-learned-evidence-agreement.md`, approved by L149; D14 reading (a) by Q38 (L162) | the known points in `#queue-stale`: `#r7-line` takes (a) at RED; 22.6 R4's fixtures predate `clear_rel_evidence`. "Approved and merged" refers to the spec; the code is unbuilt | **ready** |
| Plan-30 with G22 and G30 | 10 | freeze item 2; L128 (G22, G30) | plan-30 approved by L117 (`df75516`); G22 `task-dq1-operational-content-out-of-graph.md` met the bar by L69 / L74; G30 `task-bug216-denotes-fold-evaluation.md` approved, folded into 30.6 | 30.0 ∥ 30.5 (waits on 8) | `task-30.0-disk-tier-probe.md`, `task-30.5-load-bitmap-row-read.md`, approved by L117. 30.6 is unspecced, but it is not next | no named change (30.5 is written against the post-split `store_fragments.py`) | **ready** |
| Cross-partition `rel:` probe | M2 | L128 | no plan by design: one read-only probe | the probe. L138 P2 says it runs before 26.5's RED | no spec, no brief. The question is in `plan-review-fable-2026-11-14-memory` `#s10` | no | **no-plan-by-design (ok)**; a brief is owed at dispatch |
| T2 memory organisation | 11 | freeze item 4 (Q28 = a); L1, L9-L13, L37, L47, L55, L63-L66, L78 | plan-26 (`in-progress`) and plan-27; specs approved in spec-wave-t2 (`0fd8a2f3`, approval rows after bsd-spec-t2 r8 MEH-only, L66), merged `3be7676` as "actionable still" (the user, `#freeze-specs`) | 26.5 (waits on 8 and M2) | `task-26.5-memory-organise-verb.md`, approved as above | yes. The freshness revision `spec-t2-fresh` `3a4d430` is held unmerged in `/Volumes/littlebig/refmatrix-t2-fresh`, waiting for a ch-bsd confirm-lite before RED (L138) that has not run; P7 and P9 are open; the `plan-26 · 26.5 split` decision has no ruling. L226 amends 26.7's render (ADR 0007 `#memory-index`) and, with L222, 26.8 AC-8's MEMORY-RULES text | **stale (revise)** |
| G32, the m1 r2-lite confirm | M3 | L128 | no plan by design: a ch-bsd confirm round over `4b57796..` | the round. 25.2's R0 and 21.5 phase M wait on it | none; the POP row names the range | no | **no-plan-by-design (ok)** |
| Hook-side items | 12 | freeze item 4; L16, L19, L30, L34, L41, L43, L54 | plan-10 approved (rev 5, `e2010bd`); plan-25 `in-progress`; 25.2 / 25.3 specs approved in spec-wave-t3a (`769439e6`, after bsd-spec-t3ab r4 CLEAN) | 25.3's STM half (waits on 8). 10.3 has moved into I1.b (L226), and 25.2 waits on M3 | `task-25.3-stm-ref-admission-and-helix-repeat.md`, approved as above | yes. 25.3 cites `stm.pre_prompt_state` (`stm.py:1815`, `:2008`), which bug-285 changed (`d9ca8031`). 10.3 rides "TODAY's installed SessionStart focus entry", which C1 replaced (`e671f36c`, `8daaa0aa`), and its R4 exit-code point is still open (`#queue-stale`). 25.2's R0 must report guardrail-memory uses separately (re-triage `#r12`), and its spec does not. The POP row is not rewritten for L226 | **stale (revise)** for 10.3 and 25.2; 25.3 at RED |
| T4 bounded writes, then bug-218 | 13 | freeze item 4; L1, L3, L4, L31, L46, L49, L50, L52, L57, L62, L69, L74 | plan-23 (`in-progress`); spec-wave-t4 met the bar (`b409d987`, after bsd-spec-t4 r3 + r4-lite, L62); spec-wave-t56 (L74) | bug-185 (waits on 8) | `task-bug185-bulk-gmd-ingest.md`, approved (L62) | yes. The L136 / L144 / L145 notes ("R10 is already built by 31.6", AC-11's relpath assumption, AC-15's "exactly one entry" false at RED) are owed "at its build", but 31.6 is unbuilt. bug-309's measured holder is `ingest_gmd_paths`' per-concept upsert (`0c7c967c`), which is bug-185's target. The 23.1 split is decided but not amended. L183 / L184 widen 23.1c R11 and are not written in. C2 built R11 on an interim spool (a re-base deferral). bug-218's revision `b2e2451` is held unmerged in `/Volumes/littlebig/refmatrix-t56-fresh` (L137) | **stale (revise)** |
| 31.5 steps 1-3 → 21.2 → 21.4 | 14 | freeze items 3 and 4 (Q27 = b) | plan-31 (L140); plan-21 `in-progress`; 21.2 / 21.4 in spec-wave-t3a (`769439e6`) | 31.5 steps 1-3 (S0b / S1 measure, then S2 cut), once the capture reaches 400 prompts | `task-31.5-scan-prompt-block-measure.md`, approved by L140; default capture mode `names` (L158) | yes. L226 puts 31.5 S2's prompt-recall-channel cut after I1.h and moves 21.4 R4 into I1.h; neither spec says so. The regime marks at each I1 install window (re-triage, row 5) are not in 31.5 | **stale (revise)** for S2 and 21.4 R4; S0b and S1 can be dispatched |
| 21.5 phase M | 15 | freeze item 4 | plan-21; 21.5 rev 4 approved (L35, L53, D-Q4; `b1be2e4`) | the R12 re-measure (waits on M3 and 14) | `task-21.5-tool-used-signal.md` `#r14` | no named change | **ready** |
| Plan-24 freshness revision | 16 | freeze item 5; L128, L129 | `plan-24-mod-transport.md` is `drafting`: ch-bsd r6 DIRTY, the r7 fold never confirmed. This row is its approval step | the revision itself | no brief | yes. D1 is listed in force (superseded by D-Q5); `#phase-now` and `#phase-held` contradict L128; the probes ran on 2.1.304; L226 adds ADR 0007 as a fourth input. The POP row still says "then ch-bsd spec rounds", where L226 says none | **needs-approval** (the item is the approval; a brief is owed) |
| Mod start | 17 | L128 | plan-24 (`drafting`) | 24.0 ∥ 24.1 | `task-24.0-hook-cost-baseline.md`, `task-24.1-store-runtime-identity.md` (2026-10-20), not approved | follows 16 | **needs-approval** |
| Post-mod re-evaluation | 18 | L127, L129 | no plan by design: a review step | runs after the mod's initial work | none (not due) | — | **no-plan-by-design (ok)** |
| bug-309 holder hunt | none (C2's evidence) | L211, L212 | no plan by design: a measurement | measured: the holder is `ingest_gmd_paths`' per-concept upsert inside the sync (`0c7c967c`). No ruling yet on the fix route (bug-185, row 13; or L205's "sync yields every N", held "until measured") | registry row bug-309 | — | **no-plan-by-design (ok)**; a routing ruling is owed |
| bug-318: compaction handoff over the Read cap | none | none: no L-row, no POP row | small fix, no plan; brief `workflow/agents/fix-handoff.md`, registry row bug-318 | the fix on `fix-bug318-handoff-size` (`9954e391`, unmerged) | the brief and the registry row stand in | no | **unadmitted**. It probably qualifies under `#freeze-rule` (a partial Read satisfies C1's gate, a live defect), but it needs a POP row |
| Queue rows 1, 2, 3, S1, M1 | — | freeze item 1; L182 | — | — | — | — | **done**. In `pop-finished.md`: row 1 (stage 2) in `#finished-compiled-table`; rows 2 and S1 in `#queue-finished-2026-11-19`; M1 and row 3 in `#queue-finished-2026-11-24` |
| bug-300, bug-301, bug-302 | inside T1 | L193, L209, L210 | `task-bug300-memory-body-bm25.md` (L193); bug-301 and bug-302 small fixes | — | — | — | **done** (merged `09175133`, `334da62f`, `6c6aa048`; released 0.85.1 `69e10ffd`). Not in `pop-finished.md` |
| Indexer stagger | R0 | L206 | small fix | — | — | — | **done** (`2d7e41f6`, shipped in 0.85.0). Not in `pop-finished.md` |

{#audit-table}

## By verdict {#by-verdict}

34 items. {#by-verdict-count}

- **ready (6):** C2; 6 (29.1); 8 (29.3, 29.2, 29.4f, 29.6); 9 (31.2); 10 (plan-30, G22, G30);
  15 (21.5 phase M). {#v-ready}
- **stale (8):** the RED author can absorb 4 (T0.7) and 5 (31.3 first). These need a spec edit
  or an unmerged revision first: T0.9 ((a) is dispatchable), 7 (29.5), 11 (T2), 12 (10.3, 25.2),
  13 (bug-185, bug-218) and 14 (31.5 S2, 21.4 R4; S0b and S1 are dispatchable). {#v-stale}
- **needs-spec (6):** I1 (I1.a, I1.b), H1 (H1.a), `practice/tdd` (via I1.c and H1.c, not next),
  P1 ((b)), A1 ((b)), T1 (step 2). {#v-needs-spec}
- **needs-plan (1):** W1. {#v-needs-plan}
- **needs-approval (2):** 16 (plan-24 freshness revision), 17 (mod start). {#v-needs-approval}
- **unadmitted (1):** bug-318. {#v-unadmitted}
- **no-plan-by-design (ok) (6):** B1 (F4 and F7 need a brief at dispatch), E1, M2 (brief owed),
  M3, 18, the bug-309 holder hunt (routing ruling owed). {#v-no-plan}
- **done (4):** C1; queue rows 1, 2, 3, S1, M1; bug-300/301/302; the indexer stagger. {#v-done}

## Contradictions between the POP and the files {#contradictions}

1. **L226's queue rewrite has not happened.** L226 says "the POP queue rows are rewritten to the
   re-triage in the next POP commit". There have been eight POP commits since `7220e1dd`, and rows
   H1, P1, T0.9, A1, 12, 14 and 16 still read as they did before L226: 10.3 is still in row 12,
   21.4 is still whole, A1 (c) is still "live", and H1 has no H1.a to H1.g. {#c-l226}
2. **Finished work is still in place.** C1 is released and deployed but is still on `#queue`.
   bug-300, bug-301 and bug-302 (0.85.1) and L206's stagger have no `pop-finished.md` entry.
   Q54 to Q64 are answered but still in `#questions`. {#c-finished}
3. **"Approved" is defined two ways.** POP `#notes` and `#status-lifecycle` say a plan is
   approved only when every task has a spec. Q55 = a (L221) says the next task is enough. I1.a
   rewords `CLAUDE.md` and `PLAN_GOVERNANCE`, not the POP's own text. Plan-30 (`approved`, 30.6
   unspecced) is right under Q55 and wrong under `#notes`. {#c-approved}
4. **`#freeze-specs` is out of date.** It says "every freeze item except 30.6 and plan-31 now has
   an approved spec". Plan-31 was approved by L140 and L149. {#c-freeze-specs}
5. **Q41 and L165 disagree on frozen tracks.** `#queue-stale` (Q41 = a, L162) requires an
   architect re-read and a ch-bsd confirm-lite before the RED of a frozen track. L165 (later the
   same day) says no ch-bsd on specs. That governs the held revisions for T2 (L138) and bug-218
   (L137), and rows 11, 12 and 13. It needs a ruling on which applies. {#c-q41-l165}
6. **"Merged" means two things for plan-31.** POP row 5 says "approved and merged", and the
   re-triage marks rows 5 and 9 "(merged)". Only the specs merged (`606c0c83`, `662abfa8`); no
   code for 31.1, 31.2, 31.3, 31.4 or 31.6 is on `master`. {#c-merged}
7. **`#queue-releases` R1 is out of date.** It still lists T0.2-T0.6, S1, the Stop-hook bound
   and the storage caps, which shipped in 0.85.0 (L201). W1 "waits on R1". {#c-r1}
8. **Row 4 names only T0.7.** The spec's stage 5 is T0.7 + 29.4d (`task-29.4-suite-health`
   stage table). {#c-row4}
9. **Row 16 still says "then ch-bsd spec rounds".** L226 decided none (re-triage
   `#row16-note`). {#c-row16}
10. **Open registry rows with no route.** bug-317 (a plain `memory dedup` would fold 403
    body-term concepts) is `open`. It is neither admitted nor marked `post-mod`, which
    `#freeze-rule` requires for a bug found during the frozen work. The open GATE
    `t05-c2-MB1d` (bug-295) has no queue owner. {#c-unrouted}

rel: evidence-for -> [[plan-of-plans#notes]]
rel: evidence-for -> [[plan-of-plans#status-lifecycle]]
rel: evidence-for -> [[plan-of-plans#freeze-specs]]
rel: evidence-for -> [[plan-of-plans#queue-releases]]
rel: evidence-for -> [[plan-of-plans#questions]]
rel: depends-on -> [[pop-finished#finished-compiled-table]]
rel: depends-on -> [[pop-finished#queue-finished-2026-11-19]]
rel: depends-on -> [[pop-finished#queue-finished-2026-11-24]]
rel: depends-on -> [[refmatrix/adr-0007-instruction-architecture#practice-packs]]
rel: depends-on -> [[plan-32-retriage-2026-11-24#i1-tasks]]
rel: depends-on -> [[plan-32-retriage-2026-11-24#h1-tasks]]
