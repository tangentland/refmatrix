---
gmd: "0.1"
id: plan-review-fable-2026-11-14-queue
title: "Plan review (Fable), 2026-11-14: the whole post-0.83.0 queue — staleness, order, plan-29 interactions, ownership, readiness"
tags: [plan-review, queue, plan-29, consolidation, architecture]
metadata:
  node_type: review
  status: drafting
  created: 2026-11-14
  reviewer: ch-architect (Fable 5.2)
---

# Plan review (Fable): the whole post-0.83.0 queue {#root}

Read-only review at dev master `f3709d2` (repo `/Users/tholley/claude_tools/refmatrix`), with the frozen T0 spec read from `/Volumes/littlebig/refmatrix-spec-t0` (`spec-wave-t0` @ `fa1227d`). Nothing was edited or committed, and no suite was run. Anchors that exist only on unmerged branches are written as code spans, not links.

rel: derives-from -> [[plan-review-2026-11-13]]
rel: derives-from -> [[plan-29-code-quality]]
rel: related-to -> [[plan-of-plans]]
rel: related-to -> [[task-compaction-as-handoff]]
rel: related-to -> [[task-agent-start-context]]
rel: related-to -> [[task-linked-readonly-store]]
rel: related-to -> [[plan-24-mod-transport]]
rel: related-to -> [[plan-20-concept-similarity-eval]]
rel: related-to -> [[bug_registry]]

## Verdict {#verdict}

Placing plan-29 first is workable, but five things must be settled before 29.5 starts:

1. `store.py` is one 7,968-line class, so 29.5's "mechanical moves only" cannot produce ~3,000-line modules without a design choice ([[#b1]]).
2. `cli.py`'s import and monkeypatch surface is not covered by 29.5's acceptance ([[#b2]]).
3. T0 and 29.4 are one job split in two, with a circular closure ([[#b3]]).
4. bug-216 is not correct on the live store: bug-241 was found after the deploy and has no queue slot ([[#b4]]).
5. The three "right after 0.83.0" tasks have no position relative to plan-29, and two of them have design defects ([[#b5]], [[#b6]]).

The queue text, the G table, the POP and the handoff all describe a pre-0.83.0 world ([[#stale]]).

## 1. What is stale {#stale}

### SHOULD-FIX: `#queue` no longer states the order {#st-1}

`workflow/plan-review-2026-11-13.md#queue` is still "rev 4":

- **Item 1** is done. Backups and logs confirm the deploy, fleet hooks, R4 reingest and Q2: `~/.refmatrix/backups/hooks-0.83.0`, `refmatrix-reingest-0.83.0-20261114-112859`, `q2-claude-md-ignore-20261114-113138`; the deploy tree is at `2aab81a`.
- **Item 2** still reads "26.5 ∥ T0", which L104 displaces. Plan-29 itself appears nowhere in the list.
- **Item 4** opens with "plan-10 rev 5 ch-bsd spec review → revival branch merged (L23)". `spec-wave-t3b` already contains the revival (`dee6f07` merges `c04c9b9`), so the T3b merge is that step.
- **Item 7** still says the experiment "runs ≥ 14 days in the background". L83 removed the live leg.
- **G22** (the D-Q1 task) has no item, although L61 M6 promised one and L54 S6 keys 10.2's v3 re-run to G22 deploying.
- **bug-218's** live re-orientation repair (L49 O-2, user-gated) is not marked on item 9.
- **Item 9** still carries "D-Q1's live purge, if Q8 makes it one". Q8 a + Q9 made it no purge.

### SHOULD-FIX: `#spec-gaps` and `#goal-horizon` are wholly stale {#st-2}

- G1-G3 read "in build / rev"; all three shipped.
- Every "new" or "rev" row (G4-G30) now exists, approved, on one of seven unmerged branches cut at `1cf3b9f`.
- G32 (the m1 r2-lite confirm) has no row in `workflow/bullshit/INDEX.md`, so it has not run.
- `#goal-horizon` precondition 1 ("Q8 is answered") is met. The L77 delegation is consumed. The horizon omits plan-29, bug-241 and the three drafting tasks.
- Frontmatter still says "rev 6, provisional until ch-bsd r5", `updated: 2026-11-13`, under rulings dated 11-14.

### SHOULD-FIX: superseded L-rows not marked {#st-3}

| Row | Superseded by |
|---|---|
| L20 (≥ 14-day A/B) | L83 |
| L45 (experiment start user-gated; "randomises live sessions") | L78 / L83 |
| L53 P-items on the session leg | L56 / L83 |
| L79 and L82 m2 (3-day period, `end` rule) | L83 |
| L23 | folded into the T3b merge |
| L85 (1) "offer is verified after the next Claude Code start" | now verified: this review agent was offered and used `mcp__refmatrix__rmx_memory_recall`; `.claude/PROJECT_PROFILE.md:99` still says "unverified" |

### SHOULD-FIX: POP rows {#st-4}

In `workflow/plan-of-plans.md#plans`:

- No rows for plan-28 or plan-29, nor for the standalone tasks (bug-185, bug-218, dq1, T0, the three drafting tasks).
- Rows 3 and 9 are still `in-progress`; D-Q6 said "close now".
- Row 10 ("closes into 19.6") is superseded by Q10/Q13.
- Row 21 says AC-6 is "BLOCKED on the user's cut"; it merged at `69ecb21` and is now RED only on bug-196.
- Row 24 still says hook-shaped work "retargets to it"; D-Q5 superseded that.
- Row 25 says "not started"; 25.1 shipped, and 25.4/25.5 are superseded (L42).
- Row 26 says `approved`; 26.0-26.4 and 26.6 have shipped.
- `#sequence` names `plan-review-2026-10-14#t11-folded-waves` as the current order.
- `#queue-bug174-remeasure` is not repointed to 16.4 (L52).
- `spec-wave-t3b` edits this file, so the POP rewrite must follow that merge.

### SHOULD-FIX: registry and frontmatter drift {#st-5}

- bug-164 and bug-181 read `open`. 25.1 shipped both: `VerbUnknownProjectError` is in `verbs.py` and `mcp.py`.
- bug-085 and bug-087 read "fix on branch (undeployed)" from October.
- Frontmatter: `task-25.1` and `task-26.1` say `pending`; `task-bug178` and `task-bug216` say `approved`; plan-25 and plan-26 say `approved`.
- Plan-29's baseline (237 rows / 80 not fixed) is now 238 on master (bug-240), plus bug-241 in a clone.
- Test-suite figures: `CLAUDE.md:54` ("~13 min") and `.claude/PROJECT_PROFILE.md:43` ("~1380 tests, ~13 min") against the release log's 4,883 tests in 58:37. bug-239 covers only the README.

### SHOULD-FIX: plan-24 carries none of D-Q5 {#st-6}

`workflow/plans/plan-24-mod-transport.md`:

- `#decisions` D1 and `#phase-held` still say hook-shaped work is "kept as records, not built".
- `#phase-now` still says 24.0/24.1 "start now".
- `updated: 2026-10-20`.
- The amends notes (L38, G27) and the 24.8 R5 rows for plan-10 and 25.1-25.3 are unwritten. That list now also needs 25.1b, 10.3, 10.4, compaction-as-handoff and agent-start.

### NOTE: handoff and working tree {#st-7}

- `handoff.md#deploy` is still "next action", and its header says deployed is 0.82.0.
- `#open` names "T56 before T3a" for the ADR-0004 conflict. The overlapping pairs are T3c × T56 (`docs/adr/0004-…`) and T3a × T3b (`task-19.6`).
- `.claude/rmx-hooks.json` (`"version": "0.83.0"`) is modified and uncommitted.
- bug-230 has no implementation summary, and bug-155 has none of its own.
- Project-local `save-state.md` / `recall-state.md` remain in `bdep/cliquet` and `bdep/thiquet`. The memory `project_deploy_removes_fleet_handoff_commands` tied their removal to a deploy; nothing in the queue owns the residue.

### SHOULD-FIX: T0.1 was approved before bug-155 shipped differently {#st-8}

`task-t0-suite-trust-sweep.md` `#t0-1` "Closes: bug-155" via R1.3 and R1.4.

- R1.3 shipped verbatim (`988e96d`).
- R1.4 shipped as bash in `scripts/lint-gmd.sh:49-62` (`44d1a34`), testing only `[[ ! -d "$MEMDIR" ]]`.
- That is the defect T0's own r2 s-1 predicted: an empty auto-created own-slug `memory/` defeats the fallback.
- The slug logic is now duplicated in the test (`tests/test_gmd_lint_requires_version.py:125-136`).
- AC-1.5's "RED at base" and mutations M1.3/M1.4 no longer hold at any current base.

Fix before merge: R1.4 becomes "converge the shipped fallback onto one resolver, with the populated check and canonicalisation"; AC-1.5's RED is the empty-dir case; the bug-155 row gains that residual.

### SHOULD-FIX: wrong premises in two drafting specs {#st-9}

- `task-compaction-as-handoff.md` (status note) says 25.1 "drops the PreCompact recall command". It did not: `src/refmatrix/hooks.py:476-483` keeps `memory recall --recent … --pack`. PreCompact has three stdout writers today (digest, recall, save-state checkpoint).
- `task-linked-readonly-store.md` cites "branch `task-bug212-worktree-hook-crashes`". That is merged (`cc061f4`); the hook to name is `store.refuse_tracked_catalog_open` (`store.py:161`).

## 2. Is the order right {#order}

### BLOCKER: bug-216 is not live-correct; bug-241 has no slot {#b4}

After the deploy and the forced reingest, `workflow/review-output/r4-recount-refmatrix.log` shows:

- `target_unresolved` — `claude: 234`, `project-profile: 38`
- `misbound: 928`

AC-6 requires 0. The row exists only in `/Volumes/littlebig/refmatrix-bug241` (`78c0c11`), not on master.

"bug-216 live" is a stated precondition of plan-28 (L78; `plan-28-handhold-outcome-experiment.md:30` on `spec-wave-t3c`), G30 (L29) and G22 (L60). None may start on today's store.

bug-240 (`rmx ingest <FILE>` exits 0 and ingests nothing) is the same rule-doc family. It is a silent failure on an ingest path and has no owner.

**Do:** one hotfix branch for bug-241 + bug-240, released as 0.83.1 before 29.5; re-run R4's recount; land the row on master now.

### BLOCKER: T0 and 29.4 are one job with a circular closure {#b3}

- L104 leaves T0 at item 2, behind all of plan-29.
- 29.5's acceptance ("full suite equal by E line before and after each commit", `plan-29-code-quality.md#t5-acceptance`) is run against a suite that fails 14 tests today: 9 bug-168, 1 bug-170, 1 bug-127, 2 bug-196, 1 bug-231.
- T0's clean-suite gate (`#r7-4`) stops on any failure no T0 row owns (`#ruling-o5`). bug-228 and bug-231 are owned only by 29.4.
- T0.3's `--durations=0` run and 3-process load harness are the same measurement as 29.4's "measure, then shard".
- T0.4 deletes `duckdb_view.py` and the `_read_via_duckdb` state in `store.py`. T0.5 edits `cli.py`, `verbs.py` and `mcp.py`. That is feature work on the two files 29.5 needs quiet.

**Do:** T0 becomes 29.4's body (see [[#recommended-queue]] step 3). bug-228 and bug-231 join T0.3's harness and bands; bug-229's reaper joins T0.2. T0.4 → T0.5 land before the split, so dead code is deleted before it is moved. T0.7's clean run on the sharded runner is 29.5's baseline.

### SHOULD-FIX: L104 does not place the three Q15-Q17 tasks {#ord-3}

L85, L88 and L90 each say "queued right after 0.83.0". L104 says plan-29 is first, "before queue item 2". Neither names the other.

- All three touch `cli.py` or `store.py`: the recall/recall-state CLI paths, the root resolver, the write check.
- All three are `drafting` with no ch-bsd round.
- Two need a fleet install window that neither `#queue` nor G31 lists.

→ `plan-review-fable D1`.

### SHOULD-FIX: both hook tasks belong in item 4's install window {#ord-4}

Four tasks edit the same generated PreCompact and SessionStart `compact|clear` entries:

- 10.3 adds its own PreCompact entry and rides the SessionStart focus entry.
- 25.1b puts every hook command behind one emitter (R12) and tests "PreCompact still prints its pack" (AC-28 d/e, L70).
- compaction-as-handoff R2 requires PreCompact stdout to be exactly one instruction.
- agent-start `#depends` wants 25.1b's emitter and R18 skip line.

Built "right after 0.83.0", compaction-as-handoff is re-touched twice and costs two extra install windows. Its R2 also contradicts 25.1b AC-28 as approved.

**Order:** 10.3 → 25.1b → compaction-as-handoff → agent-start, one window. Reconcile R2 with AC-28 in the spec round: either the pack moves to SessionStart `compact`, or AC-28 (e) is amended by name.

### SHOULD-FIX: start the clocks during plan-29 {#ord-5}

P5 allows one measurement lane. These items are read-only or tiny, block later items, and nothing schedules them:

- 25.1b's `legs_ms` field (L51, L54 S3): it deploys ahead and needs ≥ 100 hook runs before R15 is decided. It rides 0.83.1 and must merge before 29.5.
- G32, the m1 confirm.
- 23.4.
- L17's Table A.
- L34's 25.2 scoring.
- The 10.5 read-back probe.
- agent-start R0 (the SubagentStart probe).
- A probe of the PreToolUse envelope's agent field (see [[#b5]]).
- T0.6's dense re-run.

### SHOULD-FIX: plan-29 names no release points, gates or docs {#ord-6}

Add to `plan-29-code-quality.md`:

- Release points: after 29.4; 29.5 alone; after 29.2/29.3.
- T0's `#r0-7` rule ("no change may make `install-hooks --check` drift") applied to all five tasks.
- A `/mcp` reconnect note. `.mcp.json` runs `.venv-eval/bin/rmx mcp`, a dev-code process that straddles the split and will fail lazy `from refmatrix.cli import …` afterwards.
- Docs deliverables for 29.5: `docs/ARCHITECTURE.md` module layout, `PROJECT_PROFILE.md#layout`, `CLAUDE.md`.

Deploy authority → `plan-review-fable D4`.

### NOTE: 29.1 and 29.5 commit shape {#ord-7}

- 29.1 rewrites `bug_registry.md`, one of the large GMD files whose post-commit re-ingest holds the store lock (bug-177's row, "seen again 2026-11-10"). Batch it into few commits.
- 29.5's "one command group per commit" re-syncs `cli.py` on every commit. Expect bug-177-class Stop-hook errors. The size is not measured.
- 29.1 must run after the seven spec merges. Its "every `scheduled` names a real task" check points at tasks (25.1b, bug-218, T0, plan-28) that exist only on those branches.

## 3. Plan-29 interactions {#p29}

### BLOCKER: `store.py` is one class {#b1}

`class Store` spans `store.py:1279` and is 7,968 lines, with 191 methods (7,712 lines). `#t5` says "store.py by concern … mechanical moves only, no behaviour change" and "no module over the size target". A class cannot be split by moving text.

The acceptance also contradicts itself: "`daemon.py` is assessed after, not split by default", yet `daemon.py` is 7,355 lines, `verbs.py` 3,653 and `ingest.py` 3,144.

**Architect's ruling (no user decision needed):**

- 29.5 splits `Store` into mixin classes in sibling modules. `Store` inherits them. Call sites, `_DaemonWriter`, the `Store(` census and every test patch stay unchanged.
- An ADR records that this is a file-size split, not a decomposition. Composition is a later decision that 29.2's `Protocol` informs.
- The size acceptance reads "no module produced by the split over target", with `daemon.py`, `verbs.py` and `ingest.py` listed as assessed exceptions.

### BLOCKER: `cli.py`'s compatibility surface is unspecified {#b2}

Measured on master:

- 185 `monkeypatch.setattr(cli, …)` sites in 64 test files; 159 patch `_root`.
- 49 distinct private `cli._x` names used by tests; 140 test files import `refmatrix.cli`.
- `python -m refmatrix.cli` is spawned at `daemon.py:7059`, `scheduler.py:131`, `ui/server.py:191` and `:578`.
- `handoff.py:669`, `:699` and `telemetry.py:1011` lazy-import cli privates. That is an engine → adapter inversion.
- `cli.py` holds 84 commands directly on `main` (3,493 lines) and 144 private helpers (4,458 lines). "One module per command group" does not partition either.

After a package split, a patch on `refmatrix.cli._root` stops reaching moved commands.

**The 29.5 spec must state:**

- `cli/__main__.py` exists.
- Shared helpers live in one module and are resolved by attribute at call time. Any test edit is a patch-target rename only (the L64 "wrap only" precedent).
- A function called from outside the CLI package moves down to its owning layer, not into `cli/<group>.py`.
- Every filename-keyed census (bug-212's `Store(`/opener census, `test_deferrals_clean`; 31 test files name `cli.py` or `store.py`) is re-proven to fail on its synthetic bypass after the split. An allowlist keyed on a file that no longer exists passes vacuously.
- A published old→new symbol map.

### SHOULD-FIX: spec line citations — count and procedure {#p29-3}

**Method:** regex `(cli|store)\.py:N` over the effective copy of every `workflow/plans/**` doc whose frontmatter status is not complete/completed/superseded. The effective copy is the spec-branch version where one exists, else master. Scripts are in the session scratchpad, uncommitted.

**Count:**

- 53 docs carry 280 citations: 148 `cli.py:N`, 132 `store.py:N`.
- Removing three shipped specs with stale frontmatter (25.1, 26.1, bug-178) leaves 50 docs and 249 citations.
- All 121 unbuilt docs together also carry 142 `daemon.py:N`, 58 `verbs.py:N` and 9 `mcp.py:N`.

| Plan | Citations (task specs + plan doc) |
|---|---|
| plan-23 | 52 |
| plan-22 | 44 |
| plan-19 | 43 + 1 |
| plan-25 | 28 + 3 (19 are shipped 25.1's) |
| plan-17 | 19 + 5 |
| plan-16 | 20 + 1 |
| plan-18 | 10 |
| plan-26 | 10 + 1 |

Heaviest specs: 23.1 (35), 19.0 (32), 22.6 (27).

They are already stale. The branches were cut at `1cf3b9f` and master is 302 commits ahead: `cli.py` ±1,209 lines, `store.py` +774, `verbs.py` +660.

**Do:**

1. Do not hand-repoint. Lines move again in 29.2 and 29.3.
2. 29.5 publishes the symbol map. One script rewrites each cite to `module.py::symbol` (the form `docs/architecture/todo.md` G12 already uses) and lists the unresolvable ones.
3. A cite-only rewrite needs no ch-bsd re-approval. A spec whose requirement depends on location gets an owner freshness check — for example 26.5 "wrap `run` at daemon.py:3376" (L63), or 23.1's 33 `store.py` sites.
4. T0's `#r0-1` (re-verify cited sites at the branch base) becomes a queue-wide rule.

### SHOULD-FIX: what plan-29 makes cheaper or invalidates {#p29-4}

- **29.4's import-derived families.** Nearly useless before the split (140 of 357 test files import `refmatrix.cli`), precise after. Move that bullet after 29.5, or re-baseline it there.
- **29.3's except census.** It will flag sites approved specs already own: bug-223 (bug-218), bug-123 (18.3 R8), bug-119 (17.4 R6). Rule: allowlist each with its owning task id and do not pull it in. 29.3 fixes only the unowned ones (bug-096, bug-240 if 0.83.1 has not).
- **29.3's term-resolution fix (bug-234).** It changes what G22's frozen query sets and 21.2/21.4 measure. G22's BEFORE/AFTER must both be taken after 29.3.
- **29.2's writer `Protocol`.** It becomes the checkable form of Constitution VII. Add one rule: every later write method (23.1's queue, bug-185's batched writes, 26.5's reroute, 22.x ops) joins the Protocol.
- **29.2 ∥ 29.3 is not parallel on `query.py`.** bug-235 sits against bug-234/236/238. Order: 29.3's query half, then 29.2's strict `query`.
- **Dead code scheduled for deletion.** `duckdb_view` (T0.4), `brief.parse_gmd` (T0.5), and `apply_log_delta` / `_apply_event_body` (68 + 105 lines, 16.6 per L50) should go before the move where separable. The 1,255 lines of grep code that 16.5 later guts move verbatim as one module.
- **24.2a.** "Hook paths become verbs" gets cheaper if 29.5's private-call list marks which cli helpers are logic rather than adapter.

## 4. Duplication and unowned work {#dup}

### SHOULD-FIX: four mechanisms for "subagents get the graph" {#dup-1}

The MCP read tools in agent definitions (shipped; now verified), `scripts/rmx-master`, the linked store and the SubagentStart push all serve one need. The Q15 measurement (522 of 662 calls were `rmx grep`) predates the first.

Agent-start is also a new push channel. The cluster's own finding is that push is mostly unused (F4), and D-Q3 froze push refinement. If plan-28's paired agents are subagents, deploying agent-start mid-series is a treatment change (L87 m3).

→ `plan-review-fable D2`.

### SHOULD-FIX: overlaps to merge {#dup-2}

- **bug-240 → bug-241.** One branch.
- **bug-232** (per-caller refusal remedies) and **bug-125** (resolved vs unresolved path in `_root_from_projects_slug`) → `task-linked-readonly-store`. Its R2 adds a fourth caller class to the same check; its R1 hinges on the same unresolved-path comparison.
- **Linked-store R5** (schema skew) and **24.1's** `.refmatrix/identity.json`: one version record, not two.
- **compaction-as-handoff R3b** needs subagent differentiation in hook envelopes. That is 19.0 R2 / bug-103. It should depend on it, not rebuild it.
- **T0.7 `#r7-8`** re-owns four plan-7 deferral rows to "plan-20 evals". W4-a says "scheduled with" (`plan-review-2026-10-14.md:529`), and plan-20's three tasks hold none of them. Write "no host plan; backlog (L33)", as L22 did for 22.4, or plan-7 closes onto a phantom owner.

### SHOULD-FIX: open rows no task owns (29.1 input) {#dup-3}

| Rows | Suggested home |
|---|---|
| 240, 241 | 0.83.1 |
| 096, 201 | 29.3 (silent/incorrect outcome class) |
| 188 | 29.3 as a fourth shape (`envknob`) |
| 233 | 29.3 git runner (already named) |
| 237 | 29.3 query half (named nowhere in `#t3`) |
| 239 + CLAUDE.md / PROFILE figures | 29.1 |
| 194, 203, 207, 097, 226 | T4, with 23.5 / bug-185 |
| 169 | the item-4 install window |
| 151-154 | deferral row: operator path, no consumer |
| 055, 075, 089, 124, 161, 189 | a deferred-with-date decision |

bug-088 and bug-101 stay user-deferred — but see D3.

## 5. Readiness {#readiness}

### NOTE: approved specs {#rdy-1}

| Spec | Ready? |
|---|---|
| T2 (26.5 …) | After merge, the cite pass and a freshness read against shipped bug-212 names |
| T4 (bug-185) | After 0.83.1, since bug-241 touches the same ingest path |
| T3a (25.1b) | After `legs_ms` data |
| T3b (plan-10) | After G22 for the v3 re-run |
| T3c (plan-28) | Not startable: bug-216 not live, G32 not run, 10.2 unbuilt |
| T56 (G22, bug-218, plan-16, plan-22) | G22 and G30 wait on 0.83.1 |
| T0 | Not as frozen ([[#st-8]], [[#b3]]) |

All line cites are stale. No spec is "ready" in the goal sense until merged and repointed.

### BLOCKER (for approval): `task-compaction-as-handoff` {#b5}

1. **R3b's gate hits subagents.** PreToolUse/PostToolUse fire for subagent tool calls under the parent session (bug-103's row is the evidence). The gate would deny every running teammate's calls after a lead compaction, and a subagent's read would lift it without the lead having read anything. Scope it to the main loop. That needs an R0 envelope probe; whether shell-hook envelopes carry an agent id is unprobed here.
2. **No stand-down when the Read itself is permission-denied.** That traps the session.
3. **No latency bound** for a hook on every tool call. The fast path must be a generated shell check of a marker, not a Python spawn.
4. **R1/R2 against shipped reality.** The checkpoint already exists (`--no-promote --no-sync`). R1's "with promote" must say whether the 30 s bridge runs at compaction. R2 must name which of the three stdout writers go silent, and amend 25.1 R7 and 25.1b AC-28 by name.
5. **No user-gate line** for its install window.

### BLOCKER (for approval): `task-linked-readonly-store` {#b6}

1. **R1's second clause is over-broad.** "Resolved store dir lies outside the project root that found it" also matches `REFMATRIX_ROOT` (`cli.py:130`, which `rmx-master` uses) and the memdir slug route (`cli.py:161`, the SessionStart bridge; L71 relies on it). Both would become read-only.
2. **A clone can commit the link.** `.gitignore:18` is `.refmatrix/`, a directories-only pattern that does not match a symlink. `git add -A` (which `save-state --commit` runs) would stage it.
3. **"Never writes" omits side files:** `query.log`, `cli.log`, STM rings, the learn queue and `PRIMER.md` regeneration, all of which land in the live store dir through the link. AC-2 checks only the catalog and `facts.log`.
4. **R3 forbids the hub**, so dense and rerank legs have no model workers. State what a linked read loses against `rmx-master`, and test it.
5. **No path-base rule.** Hits carry master's lines for files the clone has changed.
6. **Interaction with bug-230's sandbox allow** (`tests/sandbox_site/rmx_sandbox.py:272`) is unspecified. Add an AC: the suite in a linked clone equals the unlinked clone by E line.
7. **The store gains a third access mode.** That needs an ADR decision-log line, plus the `CLAUDE.md` / `PROJECT_PROFILE.md#corpus` "never symlink" text amended in the same change.

### SHOULD-FIX: `task-agent-start-context` {#rdy-4}

- R0-first is right.
- Add `depends-on` 25.1b R12/R18, not "if it has landed".
- State the per-spawn recall load under bursts. bug-224 shows recall returning empty at load ~33.
- Derive R2 (a)'s header from the store instead of the literal "`master` of the dev tree"; this hook ships fleet-wide.
- Name plan-28 as the reader of R4's telemetry, or drop the claim.

### SHOULD-FIX: plan-29 before approval {#rdy-5}

[[#b1]], [[#b2]], [[#b3]], [[#ord-6]] and [[#p29-4]], plus one ADR, "module layout and import layering" (cli → verbs → engine; the engine never imports cli). I author it at 29.5's crucible. 29.2 or an import census enforces it.

### NOTE: plan-24 and plan-20 {#rdy-6}

- **plan-24** stays deferred to G18. Write the amends notes now ([[#st-6]]).
- **plan-20:** 20.1 (labels, with the user's 50-pair review) can run any time in the lane. 20.2 must wait for G22 and for bug-216 to be live. Both change the co-occurrence inputs that the 2026-10-07 figures in `#why` were measured on. `#drift-2026-10-14` still cites 19.2 counters (frozen, D-Q3) and "Wave 4".

## Recommended queue {#recommended-queue}

1. **Bookkeeping now.** Commit `rmx-hooks.json`, the handoff and the bug-241 row. Amend T0 ([[#st-8]], [[#b3]]). Merge the seven spec branches (T56 before T3c). Then G27 and the POP rewrite with rows 28 and 29. Reason: 29.1 and every later step read these.
2. **0.83.1:** bug-241 + bug-240 + `legs_ms`. Deploy and recount. Reason: makes "bug-216 live" true and starts 25.1b's data clock.
3. **29.1 → 29.4 with T0 folded in.**
   - T0.1' first.
   - Then T0.2 (+ the bug-229 reaper) ∥ T0.3 (+ bug-228 and bug-231) ∥ T0.8.
   - Then T0.4 → T0.5.
   - Then sharding.
   - Then T0.7's clean run.

   Reason: one trusted, fast baseline before the split.
4. **ADR (layout + layering) → 29.5.** `cli` first, then `Store` mixins. Run alone and release alone.
5. **29.3 (query half first) → 29.2.** Then the import-derived families, then the cite-repoint pass. Reason: helpers and types land in final modules; specs are repointed once.
6. **T2:** 26.5 → 26.7 → 26.6 R3 → 26.8 → 26.9 ∥ plan-27. The user's order is unchanged.
7. **G22 ∥ bug-218, then G30.** Reason: G22 gates 10.2's v3 re-run and plan-20; all three need 0.83.1.
8. **Hook window (one install):** 10.3 → 25.1b → compaction-as-handoff → agent-start (if R0 passes). Then 25.2 (per L34) → 25.3 → 19.0 rest.
9. **T4:** bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5, adopting bugs 194, 203 and 207.
10. **T3:** 10.5 → 10.6 → 10.4 → 10.2; then 21.2 → 21.4.
11. **G32 → 21.5 phase M → 28.1-28.4 → 28.5** (paired series). G18 is the stop.
12. **T4:** 23.4 → 16.6 slice → 17.1 → 17.2 → 17.4 → 17.3.
13. **T6:** 22.1a → 22.2 → 22.5 ∥ 22.6 → 22.3.
14. **T5:** 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4; then 22.1.
15. **plan-18.**

**Measurement lane during steps 3-5:** [[#ord-5]].

**Drop:**
- T0 R1.3 (shipped).
- The `task-plan10-revival` clone branch (contained in T3b).
- The "live purge" clause of item 9.

**Merge:**
- T0 → 29.4.
- bug-240 → bug-241.
- bug-125 + bug-232 → the linked store.
- Both hook tasks → step 8.

**Defer:**
- plan-24 (G18).
- plan-20's 20.2 and 20.3 (after step 7).
- The linked store (per D2).
- Any `daemon.py` split.

## Decisions for the user {#decisions-for-the-user}

- **plan-review-fable D1.** Does "plan-29 first" (Q19) also come ahead of the three Q15-Q17 tasks that L85, L88 and L90 queued "right after 0.83.0"? I recommend yes, with compaction-as-handoff and agent-start built in the step-8 hook window: one install, no rework against 25.1b and 10.3. The alternative is compaction-as-handoff now, alongside 29.1/29.4. That gives the benefit sooner but costs an extra fleet install window and a re-touch.
- **plan-review-fable D2.** The linked read-only store (Q16 a) was decided while the MCP offer to subagents was unverified. It is now verified. Build as decided, or first re-measure agent usage on this session's transcripts with go/no-go bands? I recommend measuring first; the spec needs [[#b6]] fixed either way.
- **plan-review-fable D3.** 29.4 shards the suite about 4×, which multiplies its reach to live sockets (bug-088 and bug-101, deferred by you).
  - (a) Shard only once the conftest recorder fails the session on any live touch — recommended.
  - (b) Shard as is and record the counts.
  - (c) Un-defer both bugs fully into 29.4.
- **plan-review-fable D4.** Plan-29 needs about three deploys (after 29.4; 29.5 alone; after 29.2/29.3), none changing hooks or the store on disk. Give a standing go when the suite equals baseline by E line, told first (the L78 pattern), or a per-release go? I recommend the standing go.
