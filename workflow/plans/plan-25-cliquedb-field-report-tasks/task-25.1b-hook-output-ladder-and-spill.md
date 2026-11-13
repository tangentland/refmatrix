---
gmd: "0.1"
id: task-25.1b-hook-output-ladder-and-spill
title: "Task 25.1b: every generated hook command's stdout stays under 9,500 B through a degrade ladder and a per-session spill page, with the clamp as a counted safety net; plus bug-182's per-leg scan-prompt timing and conditional wall bound, and plan-2's two recall-budget riders (25.1 rev 8, split out by D-Q2)"
tags: [task, plan-25, hooks, budget, pack, ladder, spill, scan-prompt, bug-182, bug-164, plan-2-riders]
metadata:
  node_type: task
  status: drafting
  plan: plan-25-cliquedb-field-report
  created: 2026-11-13
  updated: 2026-11-13
---

# Task 25.1b: hook output ladder, spill page and hard cap {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Drafting (2026-11-13, spec wave G12; ch-bsd spec review next; NOT approved). Its five
> open decisions were ruled by the lead on 2026-11-13 ([[#open-decisions]]).
> Bugs: the hard-limit half of bug-164's report (the user, Q14); bug-182 (R0 + R15, under L44's
> band); plan-2's three riders: r9 #s-2 / #m-4 (R16, R17) and r5's scan-prompt rerank rate
> (19.5 `#w1c-rider`, closed by R0).
> Depends on: [[task-25.1-recall-hook-byte-budget]] MERGED (revision 7, released in 0.83.0: the
> one budget module `hook_budget`, `fit_blocks`, the verb-side `recall_pack.pack`, R11's
> recall-state entry); [[task-10.3-plan-10-injection-dedup]] MERGED (the compaction marker
> `stm.last_marker` and the `stm/<session>.emitted/` directory helper); 21.1's events. It does NOT
> depend on [[task-10.6-injection-presentation]]: 10.6 adds kind labels to every tier later
> ([[#k4]]).
> Builds: 25.1's revision 8 (R12-R14, AC-16-AC-18), moved here by the user's D-Q2; the 19.1 folded
> riders #w1c-s2 / #w1c-m4 (D-Q6) and 19.5's folded rider #w1c-rider (lead, O4); bug-182's
> measurement and its conditional fix (L39, L44).
> Install: regenerates every hook command, so it ships in a user-gated `install-hooks` window
> (plan review G31).

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-10.6-injection-presentation]]
rel: related-to -> [[task-10.2-plan-10-injection-dedup]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r3]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r8]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#r9]]
rel: amends -> [[task-25.1-recall-hook-byte-budget#acceptance]]
rel: realizes -> [[task-19.1-pack-recall-under-budget#w1c-riders]]
rel: realizes -> [[task-19.5-measure-delivery#w1c-rider]]
rel: implements -> [[plan-review-2026-11-13#d-q2]]
rel: implements -> [[plan-review-2026-11-13#d-q6]]
rel: implements -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[open-questions]]
rel: derives-from -> [[bsd-pop-r1-c56782f#s5]]
rel: derives-from -> [[bsd-pop-r3-b19f583#r11]]
rel: derives-from -> [[bsd-plan2-hooks-reproducible-r9-ffed3df]]
rel: derives-from -> [[bug_registry#registry]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: depends-on -> [[feedback_errors_fail_loudly_on_the_console]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]

## Why {#why}

25.1 (revision 7) fits each rmx producer to a per-channel byte budget and drops what does not fit,
naming the rest on a `+N more` trailer. The user then set a hard limit on what any hook may print
("hard limit of 9.5k on outputs", 2026-11-13) and chose how to live inside it: degrade items
instead of dropping them, and spill what still does not fit to a page the agent can pull. The
clamp at 9,500 B stays as a counted safety net (Q14 = a, [[open-questions]]). That was written as
revision 8 of 25.1 on the 25.1 branch (`69da299`). The user's D-Q2 shipped revision 7 alone in
0.83.0, so revision 8 becomes this task ([[plan-review-2026-11-13#d-q2]]). {#why-lead}

Three more items share the same budget module and the same hook window, so they ride here:

- **bug-182.** `scan-prompt --timeout 5` overran its 5 s on 36 of 101 runs (24 over 10 s), and
  `--timeout` bounds only the rerank. Which leg spends the time was never measured. The user's
  2026-11-09 order for it was "measure first". L39 hosts the fix here as R15. L44 pre-registers the
  band that decides whether R15 is built ([[#r0]], [[#r15]]).
- **plan-2 r9 #s-2 and #m-4** ([[task-19.1-pack-recall-under-budget#w1c-riders]]): rerank can spend
  the global leg's share of recall's time budget, and the degrade line calls the 1.5 s daemon
  slice "the budget". 25.1 built 19.1 but left both riders behind as time budgets. D-Q6 closes
  plan-2 when they land here.
- **The "still in play" line** (L15, contra-b CB-1): 25.1's revision 8 and plan-10's 10.2 both
  wrote a names line with that label and with different members. This task owns it ([[#k2]]).

Code read at the 25.1 branch HEAD `69da299` (unmerged; line numbers move at its merge, so symbols
are cited, not lines): the global leg is in `verbs.memory_recall` (its "global rows omitted"
warnings, which are warned and not counted); the 1.5 s slice is `cli.RECALL_DAEMON_SLICE_S`, passed
to the verb as `timeout`, whose busy message reads "recall not confirmed within {timeout}s".

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| k1 | Own task id, own branch `task-25.1b-hook-output-ladder-and-spill`, cut from `master` after 25.1 and 10.3 merge | D-Q2; L15 (`depends-on 10.3`); L30 (only 10.3 builds early) |
| k2 | **This task owns the ONE names line**, labelled `still in play`. It is ONE line: the 25.1 `+N more` trailer is folded into it, and it ends with the spill page's fetch command. One cap of 15 names is shared across both member kinds, the bytes are reserved before the fit, and `(+N)` overflow goes to the spill page. Members are of two kinds: OVER-BUDGET (this task: items the ladder put at tier 4) and HELD (10.2, later). The ONE renderer (`recall_pack`, the only place the literal appears in `src/`) takes both kinds; the held kind is empty until 10.2 builds. 10.2 sets the member order (one rank order across both kinds); whether held members carry a marker is 10.2 `#open-held-mark`, for the lead. 10.6 labels each member later, where it stands (no regrouping, 10.6 p2). 10.2 is re-specced against this task, not the other way round. {#k2} | L15; contra-b CB-1; both 25.1 rev 8 R13 and 10.2 h10 state the cap of 15 |
| k3 | **One pack call, one order, TIER-PINNED:** (1) the ladder runs over ALL retrieved rows in rank order, the `full` run ([[#r13]]); (2) held rows (10.2; the empty set until 10.2 builds) leave the tier the full run gave them and become HELD members of the names line, which degrades them to the names tier by dedupe; (3) non-held rows keep their full-run tier, and the bytes held rows free are never re-spent on promoting other rows; (4) the bodies of every row below tier 1, held rows included, and the names-cap overflow are written to the spill page ([[#r14]]); (5) the clamp runs on the whole command's stdout ([[#r12]]). The payload is never larger than the full run's. {#k3} | CB-1 ("the order … is stated explicitly"); 10.2 h9 / the user's Q13 (freed bytes are not re-spent: the replay lost a use exactly by re-spending); agreed with spec-t3b 2026-11-13 |
| k4 | **Kind labels are not built here.** Each tier is rendered by its own function in `recall_pack`. 10.6 later decorates every tier's line with `telemetry.kind_label` (10.6 p1), and every tier carries a label from then on. Revision 8's "Kind labels (10.6) apply at every tier" is restated this way, so this task has no edge to 10.6. {#k4} | L15 (CB-5 restatement); bsd-pop-r1 S5 |
| k5 | **`form` on delivered events:** `full` (tier 1), `excerpt` (tier 2), `pointer` (tier 3), `names` (a names-line member). It joins `telemetry.RECALL_EVENT_FIELDS_V1` as a nullable field, and `v` stays 1. 10.2 R6 planned the same field; it now exists from this task and 10.2 reuses it. {#k5} | CB-2 ("Excerpt counts as a form in the delivered event") |
| k6 | Spill pages live under `stm/<session>.emitted/spill/`, one file per hook call, written only by that call {#k6} | L16's home rule for per-session emitted state; 10.2 h6 / 19.6 split: one writer per file |
| k7 | "Removed at compaction" means a page written before `stm.last_marker(root, session).ts` is gone. The fetch reports it in one `Error:` line, and the next spill write deletes those pages (the spill writer is the only deleter). The marker writer moves nothing else (10.3 R3 stays true). An unreadable marker counts as "marker now", so every older page is gone (10.3 f5, the safe direction) {#k7} | 25.1 rev 8 R14; L15 (the marker is 10.3's) |
| k8 | R15 is built only in the band L44 pre-registered; R0's table and the decision row are written before any R15 code | L44; [[feedback_go_no_go_ranges_not_predrop]] |
| k9 | The three plan-2 riders are carried with their own ACs and re-read against 25.1's code, not re-derived: #s-2 (R16), #m-4 (R17), and 19.5's #w1c-rider (the scan-prompt rerank rate, R0) {#k9} | D-Q6; [[task-19.1-pack-recall-under-budget#w1c-riders]]; lead O4 |

## Requirements {#requirements}

Numbering continues 25.1's (R12-R14 and AC-16-AC-18 are revision 8's ids, kept so the plan
review's citations stay valid). R0 is this task's own measurement step (L44 names it R0).
{#requirements-lead}

0. **R0 Per-leg scan-prompt timing (bug-182's measurement).** scan-prompt's `query.log` row gains
   `legs_ms`: a map from leg name to wall milliseconds, for every leg the call ran. The legs are
   envelope parse + session resolve, replica open/read, concept match, content leg (BM25), rerank,
   composite, helix, grep floor, fit/render, telemetry write, and, as separate legs, any wait for a
   lock or the daemon (`lock_wait`, `daemon_wait`). Each leg also records `ran` / `skipped_budget`
   / `not_attempted`. A leg not run is absent, never 0. The sum of `legs_ms` and the row's total
   wall are both recorded.
   - **Venue (lead, O3):** `legs_ms` lands as this branch's FIRST commit. It is merged to `master`
     and deployed ahead by fast-forward + `rmx daemon restart --relaunch`, a lead deploy step and
     not user-gated: it is a `query.log` field, not an argv change, so no hook is regenerated.
     ≥ 100 live production hook runs are collected while R12-R14 are built, and R15 is decided
     before this task's GREEN closes.
   - **Report:** commit `workflow/measurements/task-25.1b-scan-prompt-legs.md` with per-leg p50 /
     p95 / max, and for every run over 5 s its DOMINANT leg (the leg with the largest wall). Counts
     only, no prompt text.
   - **The third plan-2 rider (lead, O4):** the report also gives the rerank leg's ran /
     skipped_budget / not_attempted rate over the same runs, beside plan-2 r5's 28/28 skipped. That
     closes 19.5's `#w1c-rider` ([[task-19.5-measure-delivery#w1c-rider]]). As the rider says, no fix
     is assumed: the number decides whether a follow-up task is opened. {#r0}
12. **R12 Hard output cap** (25.1 rev 8, restated as the safety net). Every hook command the
    generator emits passes its stdout through ONE shared emitter at `hook_budget.HOOK_HARD_CAP_BYTES
    = 9_500` (UTF-8 bytes; a UTF-8 byte count is never below the UTF-16 unit count Claude Code
    measures against its 10,000 cap). That covers SessionStart, UserPromptSubmit, PreCompact
    (including 10.3's `compact-marker` entry), Stop, 25.1 R11's recall-state entry, and any future
    entry. The cap applies on top of the per-channel budgets, never instead of them. The clamp cuts
    at whole-block boundaries (never mid-line) and appends one line `+N more (output capped at
    9,500 B): <the producer's full-output command>`, and the result, that line included, never
    exceeds 9,500 B. It records `capped: true` and the dropped byte count in the call's telemetry
    row and exits 0. `rmx telemetry --context` prints every firing on the console. A command whose
    producers already fit is byte-identical before and after. No environment variable or flag
    raises the cap. With the ladder working it fires only on a defect. {#r12}
13. **R13 Degrade ladder inside the pack.** When a payload does not fit its channel budget, items
    are degraded in rank order instead of dropped:
    - tier 1: the full body (25.1 R3's whole body);
    - tier 2: a short excerpt, the item's first lines (its `lead` text), at most 3 lines and 300 B,
      ending on a whole line;
    - tier 3: a one-line pointer (name, scope-correct fetch command per 25.1 R6);
    - tier 4: a member of the single names line ([[#k2]]).

    The pack fills top-down. As many tier-1 items as fit are placed, while leaving room for every
    remaining item at a lower tier; then tier 2, and so on. Every retrieved item stays visible at
    some tier unless the names cap is reached; past the cap, items are counted `(+N)` and spilled
    ([[#r14]]). Tiers are monotone in rank: an item never sits at a higher tier than an item ranked
    above it. Kind labels: [[#k4]]. `Packed` reports, for every retrieved row, its full-run tier
    (`full` / `excerpt` / `pointer` / `names`, the [[#k5]] values, or `overflow` for `(+N)`) and
    its rendered tier after held removal. The caller (10.2's `stm.record_full`) records state from
    these, never from telemetry events (10.2 h7). {#r13}
14. **R14 Spill to pull.** The bodies of degraded items (tiers 2-4) and the items past the names cap
    are written to the call's spill page (`stm/<session>.emitted/spill/`, [[#k6]]; no page when
    nothing was degraded). The names line ends with the fetch command for that page. The fetch
    returns exactly the spilled items with their bodies, in rank order, through the recall verb's
    `page` parameter (CLI and MCP, verb parity).
    - **The command (lead, O1):** `rmx memory recall --page <token>`, over verb
      `memory_recall(page=…)`, the verb that made the pack. Not `rmx recall`, which is the graph
      hybrid retrieval.
    - **The token (lead, O2):** `<session[:8]>-<seq>`, printed on the names line and resolved by
      prefix under `stm/` to `stm/<session>.emitted/spill/<seq>`. An ambiguous prefix gives one
      `Error:` line naming the candidates' count. The fetch never falls back to the newest session
      (bug-100).

    A missing, compacted ([[#k7]]) or unreadable page gives one clean `Error:` line, exits non-zero
    and prints no traceback. With no session (no envelope
    session), no page is written, and the names line says `(+N not paged: no session)`. {#r14}
15. **R15 scan-prompt wall bound per leg (bug-182), built only in L44's band.** After R0, the lead
    writes the decision row against L44 before any R15 code:
    - **build:** if the overrun sits in a leg the budget module controls (concept match, content
      leg, rerank, composite, helix, grep floor, fit/render), each such leg gets a wall bound in
      `hook_budget.LEG_WALL_S` (the one budget module, L39). A leg that reaches its bound returns
      what it has or nothing, is recorded as `capped` in `legs_ms`, and the call exits 0 within
      the hook's 5 s. `--timeout` keeps bounding the rerank, and its help text says so.
    - **not built:** if the overrun sits in `lock_wait` or `daemon_wait`, R15 is dropped, and
      bug-182 moves to the T4 backlog with R0's table cited in its row.

    **How "sits in" is decided (lead, O5):** classify each run over 5 s by its dominant leg.
    - If ≥ 50% of them are dominated by controllable legs, R15 bounds every controllable leg that
      dominates ≥ 10% of them.
    - If ≥ 50% are dominated by `lock_wait` / `daemon_wait`, R15 is not built.
    - A split result builds the bounds for the controllable share and also lists bug-182's wait
      share on the T4 backlog. {#r15}
16. **R16 The global leg keeps its share** (plan-2 r9 #s-2, [[task-19.1-pack-recall-under-budget#w1c-s2]]).
    In `verbs.memory_recall` on `scope=both` under a deadline, the global leg gets a reserved share
    of the call's time budget, `hook_budget.GLOBAL_LEG_RESERVE_S`, that the project leg's rerank
    cannot spend. Its value is the global leg's p95 wall on the production hook path, measured in
    R0's runs and rounded up to 0.25 s, and recorded beside the constant. A global leg that is
    still omitted is COUNTED on the recall row (`global_omitted: "<reason>"`) as well as warned.
    {#r16}
17. **R17 The degrade line names both numbers** (plan-2 r9 #m-4, [[task-19.1-pack-recall-under-budget#w1c-m4]]).
    The busy / degrade line a hook-mode recall prints names the daemon slice and the total budget
    separately, each labelled. For example: `recall not confirmed within the 1.5 s daemon slice (hook
    budget 5 s) — daemon busy; the hook skipped this turn`. {#r17}

### Amendments to 25.1, by name {#amends}

The ladder changes four rules 25.1 states. Each is amended here, and nothing else in 25.1 moves
(contra-b CB-2). {#amends-lead}

- **25.1 R3** ("whole bodies only, greedily in rank order; a `+N more: <cmd>` trailer"): bodies
  that fit are still whole (tier 1). Items that do not fit degrade per [[#r13]] instead of being
  dropped. The `+N more` trailer is replaced by the names line ([[#k2]]), which ends with the spill
  page's fetch command. {#amend-r3}
- **25.1 R8** ("distinct named hits + trailer N = hits retrieved; bodies ⊆ named; a body never
  counts as a second named hit"): items at tiers 1-3 + names-line members + `(+N)` overflow = hits
  retrieved. Tier-1 bodies ⊆ items at tiers 1-3. An excerpt is that item's rendering, never a
  second named hit. Spilled items are counted once, at the tier where they are visible, or in
  `(+N)`. {#amend-r8}
- **25.1 R9** ("spans … never for a trimmed hit"): every item at tiers 1-3 emits a `delivered`
  event whose span is its rendering, with `form` per [[#k5]]. A names-line member emits a
  `delivered` event with `form: "names"`, and its span is the names line. A `(+N)` item emits a
  `retrieved` event only and is counted. {#amend-r9}
- **25.1 AC-9 and AC-14** ("a cut body" is a mutation that must fail): the mutation becomes "a
  tier-1 body cut, or an excerpt cut mid-line or over 300 B / 3 lines". A tier-2 excerpt is the
  intended rendering, not a cut body. AC-9's "whole bodies" assertion becomes "tier-1 bodies whole;
  tier-2 excerpts within their cap and ending on a whole line". {#amend-ac9-ac14}

## Acceptance criteria {#acceptance}

All ACs run in 23.0's sandbox on 25.1's frozen fixture through the GENERATED hook commands
(`hooks._claude_hook_block(...)`, the entry under test run with `bash -c`, the envelope on stdin,
the sandbox `HOME`). Unit tables over `recall_pack` and the emitter are in addition, never instead
([[feedback_measure_the_path_users_run]]). {#acceptance-lead}

rel: depends-on -> [[feedback_measure_the_path_users_run]]

- **AC-16 (R12).** A test enumerates EVERY hook command the generator emits and, with each producer
  forced to emit 20 KB, asserts: stdout ≤ 9,500 B; it ends on a whole line; it carries the `+N
  more` line; a `capped` telemetry row is written. A command that fits is unchanged byte for byte.
  With the ladder on, the clamp does not fire on the AC-17 fixture. With the ladder disabled by
  mutation it fires, is counted, and `rmx telemetry --context` prints it. Mutations: clamp
  mid-line; the cap read from an env var; one hook command bypassing the shared emitter; a firing
  not counted. {#ac-16}
- **AC-17 (R13).** 40 retrieved items at 20 KB total and a 9,000 B budget. Every item is visible at
  some tier, tiers are monotone in rank, the payload is ≤ budget, and the tier-1 count is maximal
  for the room left. Mutations: drop instead of degrade; an excerpt longer than its cap; tiers out
  of rank order. {#ac-17}
- **AC-18 (R14).** The names line's fetch command returns exactly the spilled items with their
  bodies, in rank order (verb, CLI and MCP agree). After a compaction marker (10.3's generated
  PreCompact entry run first), the same fetch gives one `Error:` line naming compaction, exits
  non-zero, and the next spill write leaves no page older than the marker. A corrupt page gives one
  `Error:` line and no `Traceback`. With no envelope session, no page is written and the names line
  says so. The token resolves by prefix: with two sessions whose ids share the first 8
  characters, the fetch gives one `Error:` line and no page. `rmx memory recall --page` and
  `memory_recall(page=…)` return the same items. Mutations: page kept after the marker; a
  traceback on a bad page; the newest-ring session used when the envelope has none (bug-100's
  shape); an ambiguous prefix resolved to the first match. {#ac-18}
- **AC-19 (amended R8, AC-9).** On every AC-17 payload: items at tiers 1-3 + names members + `(+N)`
  = retrieved. Tier-1 bodies are whole. Every excerpt is ≤ 300 B and ≤ 3 lines and ends on a whole
  line. Mutations: a body counted as a second named hit; a spilled item counted twice. {#ac-19}
- **AC-20 (amended R9, `form`).** On a pack with items at all four tiers and a `(+N)` overflow,
  each tier-1..3 item has one `delivered` event with the matching `form` and a span that slices
  exactly its rendering out of the payload bytes. Each names member has a `form: "names"` event
  whose span is the names line. Each `(+N)` item has a `retrieved` event and no `delivered` one.
  21.5's reader and the hook-cost report run clean over a file that mixes `form`-less 25.1 rows
  with the new ones. Mutation: a `delivered` event for a `(+N)` item. {#ac-20}
- **AC-21 (R0, R15).** (a) The generated scan-prompt command writes `legs_ms` with every leg it ran
  and the ran / skipped / not-attempted outcome. A leg that did not run is absent, not 0. (b) R0's
  measurement file exists with ≥ 100 live runs, the dominant-leg table, O5's classification, and
  the rerank leg's ran / skipped / not-attempted rate (19.5's rider). The decision row against L44
  precedes the first commit that touches a leg bound (commit order checked), and the `legs_ms`
  commit is the branch's first commit. (c) If built: on a
  fixture where one bounded leg is slow on real data (e.g. the grep floor over a large generated
  tree under the sandbox root, not a patched function), the generated command exits 0 within 5 s,
  `legs_ms` marks that leg `capped`, and the other legs' output is kept. If not built: bug-182's
  row cites R0's table and sits on the T4 backlog line. Mutation (if built): a leg bound read from
  outside `hook_budget`. {#ac-21}
- **AC-22 (R16).** `scope=both` under a hook deadline, with the project leg's rerank made to use the
  whole budget. The stand-in for the slow rerank is a test double registered in
  `workflow/test_mock_registry.md`, because the reranker is internal. The global leg still answers
  within `GLOBAL_LEG_RESERVE_S`, or the recall row carries `global_omitted` with a reason.
  Mutations: the reserve not subtracted from the project leg's time; the omission warned but not
  counted. {#ac-22}
- **AC-23 (R17).** A hook-mode recall whose daemon slice expires prints a line that contains both
  the slice and the total budget, each labelled. Mutation: the slice printed as "the budget".
  {#ac-23}
- **AC-24 Generator, isolation, parity.** `rmx install-hooks --check` is clean after `--apply` in
  the sandbox. The recall verb's `page` parameter has its CLI twin in `tests/test_verb_parity.py`.
  23.0's guard records 0 connects to any live socket. {#ac-24}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/hook_budget.py` | `HOOK_HARD_CAP_BYTES`, the shared emitter, `GLOBAL_LEG_RESERVE_S`, `LEG_WALL_S` (only if R15 is built) |
| `src/refmatrix/recall_pack.py` | the ladder (one render function per tier), the names line with its member-kind slot, `Packed` gains per-item tier and `form` |
| `src/refmatrix/stm.py` | spill page write, read and prune under 10.3's `.emitted` directory helper; reads `stm.last_marker` |
| `src/refmatrix/hooks.py` | every generated command passes through the shared emitter |
| `src/refmatrix/verbs.py` (`memory_recall`) | the `page` parameter; the global leg's reserve and `global_omitted`; the degrade wording (R17) |
| `src/refmatrix/cli.py` | `rmx memory recall --page <token>`; scan-prompt's `legs_ms`; the R17 wording around `RECALL_DAEMON_SLICE_S` |
| `src/refmatrix/scan.py` | per-leg timing; leg bounds (only if R15 is built) |
| `src/refmatrix/telemetry.py` | `form`, `capped`, `dropped_bytes`, `legs_ms`, `global_omitted`; `rmx telemetry --context` prints clamp firings |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated from Python in the task's clone, never by `rmx install-hooks` against a live store |
| `tests/test_task25_1b_ladder_spill.py` (new) | AC-16..AC-24 |
| `tests/test_verb_parity.py` | the `page` twin |
| `workflow/measurements/task-25.1b-scan-prompt-legs.md` (new) | R0's table and the L44 decision row |
| `workflow/test_mock_registry.md` | AC-22's rerank double |
| `workflow/bug_registry.md` | bug-182 (fixed by R15, or moved to the T4 backlog with R0's numbers); bug-164's row names this task for the hard cap |

## Test strategy {#test-strategy}

- RED first, at `master` after 25.1 and 10.3 merge: AC-16 (no shared emitter), AC-17 (25.1 drops
  instead of degrading), AC-18 (no page), AC-21 (a) (no `legs_ms`), AC-22, AC-23. Each red run is
  recorded. A RED that passes at HEAD is not a RED ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the emitter, the generator, STM or telemetry. The one stand-in is AC-22's
  rerank double, which is registered.
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]].

rel: depends-on -> [[feedback_red_test_must_fail_at_head]]
rel: depends-on -> [[feedback_commit_before_mutation_revert]]
rel: depends-on -> [[feedback_clear_pycache_after_mutation]]

## Decisions taken by the lead (2026-11-13) {#open-decisions}

The five open decisions of the first draft were ruled by the lead on 2026-11-13, each on the
recommended option. Each ruling is folded into the requirement it names. {#open-decisions-lead}

| # | decision | ruling | folded into |
|---|---|---|---|
| O1 | The fetch command's spelling: rev 8's `rmx recall --page` named the graph hybrid retrieval, not memory recall | `rmx memory recall --page <token>`, verb `memory_recall(page=…)` | [[#r14]], AC-18 |
| O2 | Page addressing: the agent's Bash call has no session id, and the newest-ring fallback is bug-100's defect | token `<session[:8]>-<seq>`, resolved by prefix under `stm/`; an ambiguous prefix gives one `Error:` line | [[#r14]], AC-18 |
| O3 | Where R0's ≥ 100 runs come from | `legs_ms` is the branch's first commit, deployed ahead by fast-forward as a lead deploy step (not user-gated; no hook regeneration); live runs collected while R12-R14 build; R15 decided before GREEN closes | [[#r0]], AC-21 |
| O4 | 19.5's #w1c-rider sat in frozen 19.5, so plan-2 could not close | R0 records the rerank leg's outcome and closes it here, as the third plan-2 rider | [[#r0]], [[#k9]], AC-21 |
| O5 | How "sits in" is decided for L44 | dominant leg per > 5 s run; ≥ 50% controllable → bound every controllable leg dominating ≥ 10%; ≥ 50% waits → not built; split → both | [[#r15]] |

## Q8 {#q8}

Holds under Q8 a and c, and under b: per-prompt recall excludes `session/*` in hook modes, so the
ladder and the spill page never carry a save-state under any option. Nothing here is a `#q8-b`
line. {#q8-body}

## Definition of done {#done}

- R0's measurement and the L44 decision row committed before any R15 code; RED and GREEN runs
  recorded; the mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-25.1b-hook-output-ladder-and-spill.md`.
- Committed on branch `task-25.1b-hook-output-ladder-and-spill` and merged `--no-ff` to `master`.
  The `install-hooks` window is the user's (G31), batched with any window that falls together (C11).
- With this task merged, plan-2's three riders are landed: #s-2 and #m-4 (D-Q6) and 19.5's
  #w1c-rider (lead, O4).
