---
gmd: "0.1"
id: plan-review-fable-2026-11-14-memory
title: "Plan review (Fable), 2026-11-14: memory and context tracks T2/T3 against 0.83.0"
tags: [plan-review, spec-review, plan-26, plan-27, plan-25, plan-10, plan-19, plan-21, plan-29, t2, t3]
metadata:
  node_type: review
  reviewer: ch-architect (fable-rev-memory)
  created: 2026-11-14
  master: f3709d2 (0.83.0 release af83867)
  branches: "spec-wave-t2 0fd8a2f; spec-wave-t3a 8e8e307; spec-wave-t3b 5559d20"
---

# Plan review (Fable), 2026-11-14: memory and context tracks {#root}

rel: derives-from -> [[plan-review-2026-11-13]]
rel: depends-on -> [[plan-29-code-quality]]
rel: related-to -> [[plan-26-memory-organisation]]
rel: related-to -> [[plan-27-memory-fleet-rollout]]
rel: related-to -> [[plan-25-cliquedb-field-report]]
rel: related-to -> [[plan-10-injection-dedup]]
rel: related-to -> [[plan-19-adaptive-memory-budget]]
rel: related-to -> [[plan-21-agent-context-usage]]
rel: evidence-for -> [[bug_registry]]

## Summary {#summary}

Four findings block a step, 32 should be fixed before the affected task goes RED, and 7 are
notes. No frozen spec re-plans something 0.83.0 already shipped wholesale. The damage is
narrower: specs that assume pre-0.83.0 behaviour, one shipped fix that is not live (bug-241), and
a merge set that cannot land the way the queue describes it. {#summary-lead}

The brief called 25.1 "recall-hook byte budget (hook output ladder)". The ladder is 25.1b's
content and is not in 0.83.0. Master has the per-channel budgets, `fit_blocks`, `recall_pack.pack`
and `--max-bytes`; it has no `HOOK_HARD_CAP_BYTES`, `emit`, degrade tiers, spill pages or R18 skip
line. {#summary-ladder}

## Method and limits {#method}

- Read-only. Nothing was edited, committed, checked out or run except `git` read commands,
  `git merge-file -p` into the scratchpad, and greps. {#method-readonly}
- The spec volume is about 18,000 lines, so three parallel readers took T2, T3a and T3b. I then
  re-read the lines behind every BLOCKER and most SHOULD-FIX items. Each finding is marked
  **(V)** where I read the cited line myself, or **(R)** where a delegated reader read it and I
  did not re-read it. {#method-marks}
- Not read in full: 19.0's AC text (lines 384-688), 21.5 rev 4's body on `spec-wave-t3c`, and
  the 26.5 review-round history. `spec-wave-t3c` was outside the brief but turned out to be a
  merge dependency ([[#b1]]). {#method-gaps}
- Paths: `T2/`, `T3a/`, `T3b/`, `T3c/` mean
  `/Volumes/littlebig/refmatrix-spec-<t>/workflow/plans/`; `M/` means
  `/Users/tholley/claude_tools/refmatrix/`. {#method-paths}

## Blockers {#blockers}

- **BLOCKER: the T3 spec branches cannot merge the way queue item 4 says.** {#b1}
  - `spec-wave-t3b` carries `rel:` edges to `task-25.1b-hook-output-ladder-and-spill`
    (`T3b/plan-10-injection-dedup.md:44,91`; `task-10.2…:34,86,403`; `10.3:149`; `10.4:29`;
    `10.5:65`; `10.6:27,165`) and to `task-28.2-…` / `task-28.4-…` (`task-10.2…:446,487,488`)
    (V). 25.1b exists only on t3a and plan-28 only on t3c (V). Cross-doc dangling refs are
    errors at repo scope (`M/tools/gmd/lint.py:391-403`, V).
  - Two textual conflicts (V, `git merge-file`): task-19.6 between t3a and t3b (both append a
    section after the r12 table), and the 25.1 spec between master (+133 lines) and t3a.
  - The "revival branch" of L23 is already inside t3b (merge `dee6f07` of `c04c9b9`, V). The
    clone `/Volumes/littlebig/refmatrix-plan10` (`task-plan10-revival`, 0.82.0 base) is
    superseded.
  - Queue item 4's head must say: merge t3a, t3c and t3b in one window, t3b last; keep both
    appended 19.6 sections; in the 25.1 spec keep master's rounds 6-8 and the branch's header and
    `#rev-dq2`; never merge `task-plan10-revival` on its own; run `./scripts/lint-gmd.sh` at repo
    scope after the three.
- **BLOCKER (21.2, 21.4, L29): bug-216 is not live, and nobody owns the follow-up.** {#b2}
  - `M/workflow/bug_registry.md:292` (bug-241, V): after the 0.83.0 deploy, R4 and
    `rmx reingest --force`, `CLAUDE.md` and `.claude/PROJECT_PROFILE.md` hold only plain doc
    rows, with no GMD row and no anchors. AC-6 requires 0 unresolved and shows 234 and 38, plus
    928 misbound. The cause is not measured.
  - `M/handoff.md:43-45` still says "the forced re-ingest has not run" (V). The registry is
    newer.
  - 21.2's baseline row and 21.4's `#q8-copy-order` need a catalog copy taken after bug-216's
    live re-derive (R). L29's fold evaluation needs the same.
  - Required: a bug-241 task (RED on a repo-shaped throwaway store, then the live reingest and
    `denotes_link` per partition). 21.2 and 21.4 gain a stated precondition: "bug-241 fixed,
    AC-6 = 0 live, catalog-copy sha recorded". See [[#memory-d1]].
- **BLOCKER (27.1): AC-0 orders a tree walk the user forbade.** {#b3}
  - `T2/plan-27-memory-fleet-rollout-tasks/task-27.1-fleet-inventory.md:35-37` `#ac-0` finds
    repos by marker "over `~/github`, `~/claude_tools` and `~/enduris`" (V).
  - Memory `feedback_fleet_discovery_known_list_no_tree_walk#rule` (user, 2026-11-14, V): known
    candidate list only, never walk `~/github` or `~/enduris`.
  - AC-0 must start from `project_fleet_roster_1114#roster` (8 repos), plus
    `discovery.discover_roots()`, plus the direct children of `~/claude_tools`. Its "bdep/thiquet
    and atlftpd were missed" line and plan-27 `#facts-hooks-0820` are stale for the same reason.
- **BLOCKER (10.6): p1 and AC-6 name a function that does not exist.** {#b4}
  - `T3b/plan-10-injection-dedup-tasks/task-10.6-injection-presentation.md:129,143` say
    `composite._kind_of_type` calls `telemetry.kind_label` (V).
  - The only `_kind_of_type` is `M/src/refmatrix/memory_index.py:158` (V), which maps to
    MEMORY.md index classes for 26.7's index. It is a different map with a different consumer.
  - p1 and AC-6 must name the real second map, or say none exists and that
    `memory_index._kind_of_type` is untouched.

## Stale after 0.83.0 {#stale}

- **SHOULD-FIX: the 25.1 spec record.** `M/…/task-25.1-recall-hook-byte-budget.md:8` is still
  `status: pending` and `:772` still carries `#rev-round-8`, whose fetch is `rmx recall --page N`
  (`:808`, `:819`, V). 25.1b O1 says `rmx memory recall --page <token>` (`T3a/…/task-25.1b…:221`,
  V). D-Q2 said rev 8 leaves 25.1. Set status completed (0.83.0) and mark round 8 superseded by
  25.1b. Registry rows bug-164 and bug-181 still read `open` (V). {#s1}
- **SHOULD-FIX: 25.1b R12 contradicts the shipped budget table.** `T3a/…/task-25.1b…:148-183`
  `#r12` gives a sole writer "the command's whole 9,500 B" and lets shares sum to 9,500 (V).
  `M/src/refmatrix/hook_budget.py:33,106-111` raises at import when a command's channels exceed
  9,000 (V). R12 must state the relation between the two numbers, name channels and event
  placement for the four uncapped writers, and extend `telemetry.hook_producer` (R:
  `telemetry.py:1030-1052`). {#s2}
- **SHOULD-FIX (layering): `hook_budget.emit` breaks the module's stated purity.** The module
  docstring says "no I/O … no telemetry, no store" (`hook_budget.py:22`, V), and
  `telemetry.summarize_context` imports `hook_budget` (`telemetry.py:1140`, V). R12 has `emit`
  write the `capped` row. Either `emit` returns the cut and the CLI's existing telemetry row
  records it, or R12 amends the contract by name. I recommend the first. {#s3}
- **SHOULD-FIX: R12's clamp against bug-212's save-state contract.** `cli.save_state` is one of
  the four writers to be clamped. A head-kept cut can drop a trailing `promote FAILED` /
  `memory bridge FAILED` line that `hooks.py:488-493` says must reach the transcript (V), and
  R12's "exits 0" must not override `SaveStateIncompleteError`'s exit 1 (bug-212 summary
  `#green-r5-changes`, V). R12 must say both, and whether the clamp applies only under hook
  source. {#s4}
- **SHOULD-FIX: two specs each add a transport classifier.** 25.1b `#r18` puts an
  exception-to-cause function in `cli.py`, and 26.5 `#r-220c` (rev 10 w4) maps `ReplyTimeout`
  itself (R). `M/src/refmatrix/verbs.py:239-241` is documented as "THE one place" (V). Both must
  derive from `classify_transport_error`. This is a 29.3 class and should join its list. {#s5}
- **SHOULD-FIX: 19.0 still plans what 21.1 shipped.** `T3a/…/task-19.0…:698` says the snapshot
  code is "built here or by 21.1, whichever merges first" (V). Master has it: `stm.py:1337,
  1779, 1796, 1893`, `verbs.py:863, 874` (V). Still unconverted are the `latest_session`
  fallbacks at `scan.py:537`, `helix.py:96`, `composite.py:103`, `promote.py:161` (V). R5 and R7
  become caller conversion only. Every AC marked RED must be re-run at HEAD, because the ones
  covering shipped parts pass. Queue item 4's "R2-R7" overstates the scope. {#s6}
- **SHOULD-FIX: no T2 spec handles a deferred bridge.** Since bug-212, a bridge that waits out
  another ingest job returns `deferred` with no error and exit 0 (summary `#green-r6-changes`,
  V). The word appears in no T2 spec (V, grep = 0). 26.8 AC-4's "zero errors" passes with
  nothing bridged. 26.5 AC-5, 26.8 AC-2/AC-4 and the 27.x applies must treat `deferred` as "not
  proven" and re-run. {#s7}
- **SHOULD-FIX: the tracked-catalog refusal is unaccounted for.** 26.5 `#r-220c` opens
  `_store_rw()` in a close callback with no refusal branch, and 27.4 `#test-strategy` says
  "in-process only when there is no daemon" (R). `_store_rw()` now refuses a git-tracked catalog
  (bug-212 b-1, V). Count it as `rerouted_failed`; 27.4 starts the daemon first. bug-232 (wrong
  remedy text) is open. {#s8}
- **SHOULD-FIX: recall absence of stale subjects is now assertable.** `T2/…/task-26.8…:134`,
  `task-26.6…:49,104`, `plan-26…:217,235` defer it to "25.1 AC-6" (V). It shipped
  (`--include-subjects`, 25.1 summary `#green-signatures`, V). 26.8 AC-6 and 27.6 AC-1 must
  assert it, with and without the flag. {#s9}
- **SHOULD-FIX: 26.5's twin purge drops `rel:` edges under bug-216's doc-first binding.** A bare
  id now binds the `kind=doc` twin first (`ingest_gmd.py:490-523`, V). The twin drop only purges
  (R: `ingest_gmd.py:1467-1496`), and citers are hash-skipped. R-220c must re-pend each inbound
  `rel:` before the purge and AC-220(e) must assert the edge is pending or rebound. See
  [[#memory-d3]]. {#s10}
- **SHOULD-FIX: `rmx_memory_organise` and MCP `project`.** 25.1 R10 made `project` the transport
  target and an unknown one `isError`. 26.5 AC-1 targets the memdir's store regardless (R). The
  spec must say a `project` naming another store is a `VerbArgsError`, and that AC-8's
  `organise --check` line also prints on the `SaveStateIncompleteError` path. {#s11}
- **SHOULD-FIX: 26.8 AC-0's baseline.** It treats "the deploy" as the first release of 26.1-26.4
  and runs the dev build (R). Those are live since 0.82.0, and `--store-snapshot` is deployed.
  The baseline is deployed 0.83.x and the deployed `rmx`. {#s12}
- **SHOULD-FIX: 27.3 is half done.** Its ACs assume `~/enduris/thiquet` is supervised (R). The
  LaunchAgent was uninstalled on 2026-11-14 (`project_fleet_roster_1114#enduris-thiquet`, V).
  AC-4 becomes: verify the label is gone, tar `.refmatrix/`, tombstone, confirm the hub line
  clears. {#s13}
- **SHOULD-FIX: 25.3 R8's hub degree predates `denotes`.** R8 counts `entity_links` rows naming
  the entity (R). bug-216 added `denotes` rows that `context.py` and `query.py` exclude from
  counted linkages. R8 must say whether they count. {#s14}
- **SHOULD-FIX: 10.5 R1b may not exercise the ladder.** It replays prompt calls from windows
  when the hook ran `--k 5 --json` (R). The hook now runs `--k 12 --pack`
  (`hooks.py:452-455`, V). R1b must say whether rows are re-retrieved at k=12. {#s15}
- **SHOULD-FIX: 10.6 p3 guards the wrong row.** It cites `cli.py:9567` as the `rmx context` row
  (`T3b/…/task-10.6…:53`, V). The line is now `cli.py:9818` and sits in `scan_prompt_cmd` (V).
  R2's new header would zero every scan-prompt row's `cardinality`. AC-2 must assert it is
  unchanged. {#s16}
- **SHOULD-FIX: 10.6 R1 changes 25.1's hook-line format without amending it.** The one parser
  (`tests/task21_1_support.py:243`, R) would read `[rule]` as the name. R1 needs
  `rel: amends` to 25.1 R3 and the parser in Files. 10.6 also has no test-strategy section. {#s17}
- **SHOULD-FIX: tier legs are unreachable on the per-prompt hook.** Master never puts bodies on
  `prompt_recall` (`recall_pack.py:232-235`, V). 10.2 AC-2's "body at prompt 2" and 10.6 AC-1's
  "every tier at 4,000 B" (R) must name their channel, or 25.1b must state the tiers on
  `prompt_recall`. {#s18}
- **SHOULD-FIX: 10.3 R4 exits non-zero on SessionStart.** Claude Code drops a SessionStart
  command's stdout when it exits non-zero (`hooks.py:254-256`, V), so R4's "surfacing still
  prints" is lost. R4 and AC-5 must cover that and the session-less envelope. {#s19}
- **SHOULD-FIX: stderr assertions cannot be observed on the scan leg.** Generated `scan_cmd`
  ends `2>/dev/null || true` (`hooks.py:338`, V). 10.2 AC-10, AC-11's `Error:` line and 10.6
  AC-5 (R) must assert the row field, or the spec changes the redirect. {#s20}

## Contradictions {#contradictions}

- **SHOULD-FIX: 26.5 AC-1 "never from the cwd" is false at its own resolver.**
  `_root_from_projects_slug` (`cli.py:161-180`, V; spec cites `:113`) matches against
  `discover_roots()`, which adds the cwd root (`discovery.py:115-131`, V). An unregistered store
  resolves only when the caller stands in it. AC-1 must state the candidate set and make an
  existing unregistered store a named error. {#s21}
- **SHOULD-FIX: 26.9 AC-1 is not RED.** `T2/…/task-26.9…:149` claims a scoped `--apply` unlinks
  every project subject's leaves at HEAD (V). 26.6 built the pattern scope
  (`consolidate.py:86-93`, V). Restate AC-1 as a guard plus the planted-family measurement. {#s22}
- **SHOULD-FIX: 19.6 disagrees with 25.1b and 10.6 after the merge.** t3b's appended section says
  "plan-10 adds the nullable event field `form`" (V). 25.1b k5 owns `form` and 10.2 adds only
  `held` (`T3a/…/task-25.1b…:103`, V). The split table's "19.6 keeps R5 / R6 for the composite
  blocks" also conflicts with 10.6 p6 (R), and R8a's body still says "this task adds" the marker
  writer. {#s23}
- **SHOULD-FIX: 10.6 R3 / AC-4 ignore the composite cadence.** The composite prints only when
  `turn % every == 0` (`composite.py:110-112`, V) and the hook passes `--composite-every`
  (`hooks.py:334-335`, V). "Second prompt prints `rev 1 unchanged`" cannot happen on consecutive
  turns. 10.4 n7 stops non-human turns incrementing the turn (R), which changes the cadence
  10.6 R0 measures. {#s24}
- **SHOULD-FIX: no spec names the session that keys `stm/<session>.emitted/`.** 10.2, 10.4 and
  10.6 leave it open (R). The composite still reads `latest_session` (`composite.py:103`, V;
  bug-100, owned by 19.0). Each must say "the envelope session id", and 10.6 needs
  `depends-on` 19.0. {#s25}
- **SHOULD-FIX: marker and `session_start` record race on `/clear`.** Both entries fire in one
  event and 10.2 h1 / AC-3 do not order them (R; the race itself is inferred). h1 needs a
  rule. {#s26}
- **SHOULD-FIX: 10.2 R7's bands can hardly produce a verdict.** 28.4 on t3c says the nested
  reading sees only first-prompt dedupe (R), so the "under 30% byte cut" row is near-certain.
  Read bytes from live R6 telemetry and keep the paired series for the used rate. Leftover live
  wording: `task-10.2…:375`, `plan-10…:195,239,281` (R). R7 and Files also disagree on where
  `arms.cell()` is called. {#s27}
- **SHOULD-FIX: 25.1b AC-17 cannot run through the generated commands.** It needs 40 retrieved
  items (R); generated `--k` is 12, 12 and 30 (`hooks.py:453,483`, V). State its venue. {#s28}
- **SHOULD-FIX: 25.1b AC-20 asserts a frozen reader.** "21.5's reader runs clean" (R) names
  phase B, which D-Q4 freezes. Name an existing reader. {#s29}
- **SHOULD-FIX: plan-27 uses a drift check that cannot see git hooks.** 27.6 AC-3 and 27.1 AC-2
  rely on `rmx install-hooks --check` (R). bug-209 is `recurring`: it compares only the Claude
  settings block (V). Both ACs need the byte compare against `GIT_HOOK_SCRIPTS`. {#s30}
- **SHOULD-FIX: 21.2's frozen gold files do not survive 29.5.** Three of nine gold files are
  `cli.py` or `store.py` (R). Key gold on the unique definition, or re-freeze after 29.5. {#s31}
- **SHOULD-FIX: `task-compaction-as-handoff.md` overlaps 10.3 and 25.1b unlinked.** It adds a
  per-session marker and a per-prompt pointer re-injection (`:62-64,90`, V) with no edge to
  either (V). Its header says 0.83.0 "drops the PreCompact recall command" (`:16`, V), which is
  false (`hooks.py:476-484`, V). {#s32}

## Plan-29 interactions {#plan-29}

`cli.py` changed by about 1,200 lines and `store.py` by 774 since the spec base `1cf3b9f`, so
every line citation is already stale before 29.5 moves it. Spot checks (R): 19.0, 5 of 12 hold
and all four `cli.py` cites are stale; 25.3, 5 of 14 hold. L104 already orders the re-point after
29.5. {#plan-29-lead}

| spec | `cli.py:` cites | `store.py:` cites | plans code in `cli.py` |
|---|---|---|---|
| 26.5 | 5 | 0 | yes (organise, `_sync_memory_dir(root=)`, root `main`) |
| 26.6 | 0 | 2 | residual only |
| 26.7, 27.0 | 0 | 0 | yes (`--check-reach`; `--merge-from`) |
| 26.8, 26.9, 27.1-27.6 | 0 | 0 | no |
| 25.1b | 3 | 0 | yes (three Files rows) |
| 25.2 | 0 | 0 | yes |
| 25.3 | 6 | 0 | yes |
| 19.0 | 32 | 0 | yes |
| 21.2 / 21.4 | 0 / 2 | 0 | 21.2 yes |
| 21.5 (t3c) | 4 | 0 | yes, and `store.py` |
| 10.2, 10.3 | 0 | 0 | yes |
| 10.4 | 2 | 0 | yes |
| 10.6 / 19.6 | 1 / 1 | 0 | 19.6 yes; 10.6 depends on `cli.py:9818` |

{#plan-29-table}

- **29.5:** two private cross-module calls need a library home before 26.5 builds:
  `handoff → cli._sync_memory_dir` (R: `handoff.py:669`) and `_root_from_projects_slug`. 25.1b
  AC-26's check over "the ten writer functions" must resolve by name across the package. {#p29-5}
- **29.3 `run_git`:** 26.5 AC-4 and 27.0 AC-8 (R). **Transport classification:** [[#s5]].
  **Except census:** 26.5 rewrites two broad-except sites; 19.0 R5's `scan.py` conversion and
  25.3 R7 overlap it (R). Query-term resolution is used by no T2/T3 task. {#p29-3}
- **29.4:** 25.1b AC-28 leaves a SIGSTOPped daemon the reaper will fail on, and AC-21(c) is a
  wall-clock assert (R). 26.5 AC-220's bounds should use the reaper. Generated-command
  `bash -c` tests belong in the slow tier. {#p29-4}
- **NOTE:** 29.5's acceptance says no module over the target, while `daemon.py` (7,355) is "not
  split by default" and `verbs.py` is 3,653 (V). Five specs add `.emitted` state to `stm.py`
  (2,033). One `.emitted` module with a single owner, defined before 10.3 builds, is the cleaner
  shape. {#p29-note}

## Readiness {#readiness}

All build tasks also wait on the spec merges and plan-29 (L104).

| task | verdict | what, or blocked on | user gate marked | RED-first |
|---|---|---|---|---|
| 26.5 | needs revision | [[#s5]], [[#s7]], [[#s8]], [[#s10]], [[#s11]], [[#s21]]; re-read after bug-241 | yes | yes |
| 26.6 R3 residual | ready | after 26.7 | n/a | yes |
| 26.7 | ready | after 26.5; D-Q2's AC-E present and correct (R) | n/a | yes |
| 26.8 | needs revision | [[#s7]], [[#s9]], [[#s12]]; needs 26.5-26.7 released | yes | n/a (live) |
| 26.9 | needs revision | [[#s22]] | yes | AC-1 no |
| 27.0 | ready | re-point after 29.5 | yes | yes |
| 27.1 | needs revision | [[#b3]], [[#s30]] | n/a | n/a |
| 27.2a, 27.2 | ready | 27.1; 27.0 | yes | 27.2a yes |
| 27.3 | needs revision | [[#s13]] | yes | n/a |
| 27.4 | needs revision | [[#s7]], [[#s8]], [[#s21]] | yes | n/a |
| 27.5 | ready with edits | name the 0.83.0 hook command; AC-5 can fail on bug-206 (R) | yes | n/a |
| 27.6 | needs revision | [[#s9]], [[#s30]] | yes | n/a |
| 25.1b | needs revision | [[#s2]], [[#s3]], [[#s4]], [[#s5]], [[#s28]], [[#s29]]; blocked on 10.3 and R0's 100 runs | yes | yes |
| 25.2 | R0 ready; build blocked | m1 confirm (L36), then L34's bands; L43 if it fails | none needed | yes |
| 25.3 STM half | ready | re-point after 29.5 | none needed | yes |
| 25.3 helix half | blocked | 25.2 built, 10.3; [[#s14]] | none needed | yes |
| 25.4, 25.5 | closed | closing text is only on `spec-wave-t56` | n/a | n/a |
| 19.0 | needs revision | [[#s6]]; remainder after 25.3's STM half | R0 probe step unmarked | no, as written |
| 21.2 | blocked | [[#b2]]; [[#s31]] | bug-216 live step unmarked | yes |
| 21.4 | blocked | 21.2; [[#b2]]; question-set approval | yes | yes |
| 21.5 | not on t3a | rev 4 is on t3c; phase B frozen (D-Q4) | on t3c | measurement |
| 10.3 | needs revision (small) | [[#s19]] | yes | yes |
| 10.5 | needs revision | [[#s15]]; after 25.1b | FAIL route only | yes |
| 10.6 | needs revision | [[#b4]], [[#s16]], [[#s17]], [[#s24]], [[#s25]] | none needed | not stated |
| 10.4 | needs revision (small) | stale cites; RED base needs 25.1b and 10.3 (R) | yes | yes, wrong base |
| 10.2 | needs revision | [[#s18]], [[#s20]], [[#s25]], [[#s26]], [[#s27]]; no 10.2 code exists anywhere | plan-28's | yes |
| 19.6 | frozen (D-Q3) | [[#s23]] at merge | n/a | n/a |

{#readiness-table}

## Duplicates and gaps {#gaps}

- **Unowned, open:** bug-241 ([[#b2]]); bug-240 (`rmx ingest <FILE>` ingests nothing; 26.5's
  route table omits a file argument); bug-232; bug-169 (install-hooks partial write, a natural
  rider for 25.1b's install window); bug-209 (recurring; plan-27 depends on it, [[#s30]]). {#gap-unowned}
- **Stale rows (29.1 input):** bug-164 and bug-181 read `open` after shipping; bug-100 says "no
  owner yet" though L41 gives it to 19.0 R5; bug-165 and bug-166 show no fix owner though 25.2
  and 25.3 own them (V for the row text). {#gap-stale-rows}
- **No registry row:** the scan leg's `2>/dev/null || true` hiding failure lines ([[#s20]]). {#gap-no-row}
- **Process gaps:** `plan-of-plans.md` has no plan-29 row (V), and the `#queue` text does not
  carry L104. Queue item 6's "10.2 (built; …)" should read "to be built". {#gap-process}

## Notes {#notes}

- **NOTE:** Every "Q8 is open" `#q8-b` section (26.5, 26.8, plan-27, 27.5) is void: D-Q1 is
  final (V). {#n1}
- **NOTE:** ADR-0005 is still Proposed with 26.1-26.4 deployed on it (R). I will move it to
  Accepted when the T2 branch merges. ADR-0004 is edited by both t3c and t56 (V); check that
  merge. {#n2}
- **NOTE:** L34 says 25.2 "is re-specced" on failure; L43 says "not built". L43 is later and
  wins; L34 is not annotated (V). {#n3}
- **NOTE:** 25.2's empty payload on a gated ack is not an R18 skip; neither spec says so (R). {#n4}
- **NOTE:** bug-225 and bug-227 touch no T2/T3 requirement. {#n5}
- **NOTE:** The 26.5 reroute adds a hard failure to every sync route for an edge that bug-216's
  hidden-dir prune made hard to reach (R). ch-bsd accepted it; I flag the cost only. {#n6}

## Recommended order {#recommended-order}

1. Correct `handoff.md` on the reingest and settle [[#memory-d1]]. Reason: 0.83.0's headline fix
   is not live and three baselines wait on it. {#o1}
2. Merge the spec branches with t3a, t3c, t3b as one window ([[#b1]]). Reason: the only
   lint-clean route. {#o2}
3. During plan-29, read-only lane: 26.8 AC-0's fleet `MEMORY.md` backup, 25.2 R0 replay after
   the m1 confirm, 10.6 R0 (Table A), 19.0 R0. Reason: none needs code, and each decides
   whether something is built. {#o3}
4. After 29.5, one freshness revision per track (T2, T3a, T3b) with the line re-point, each
   through one ch-bsd round. Reason: stops wrong RED tests. {#o4}
5. T2: 26.5, then 27.0, 26.7 and 26.6 R3 in one release; then 26.8 (gated); then 27.1 beside
   26.9; then 27.2a, 27.2, 27.3, 27.4, 27.5, 27.6. I would split 26.5 into the verb (bug-208,
   bug-213) and the bug-220 reroute so the rollout does not wait on the reroute. That amends
   L37, a lead ruling. {#o5}
6. T3: 25.3 STM half; 10.3; 19.0 remainder; 25.1b; 25.2 and 25.3's helix half only on PASS.
   Reason: 10.3's marker and 19.0 R2 unblock the most. {#o6}
7. T3 later: 10.5, 10.6, 10.4, 10.2 per L30; 21.2 then 21.4 once bug-241 is live. {#o7}

## Decisions for the user {#decisions-for-the-user}

- **plan-review-fable-memory D1: does bug-241 go ahead of plan-29?** L104 puts all of plan-29
  first on your word. I recommend the exception: measure and fix bug-241 before 29.5's freeze.
  The catch is a code change ahead of the split, though its likely site is `ingest.py`, not
  `cli.py` or `store.py`. {#memory-d1}
- **plan-review-fable-memory D2: land 25.1b's `legs_ms` timing pair before 29.5?** R0 needs 100
  runs and as written cannot start until plan-29, the merges and 10.3 are done. Landing the
  telemetry-only pair first lets the window accrue during plan-29. It touches `cli.py` and
  `scan.py`, so it must land before 29.5 starts. I recommend yes. {#memory-d2}
- **plan-review-fable-memory D3: should a project doc's `rel:` to a memory id bind across
  partitions?** `get_entity` is partition-scoped (R), so such an edge likely cannot bind today.
  You said memories should be bridged into the graph; 26.5's twin purge ([[#s10]]) needs the
  intended answer. This rests on an inference, so one probe should precede the decision. {#memory-d3}
