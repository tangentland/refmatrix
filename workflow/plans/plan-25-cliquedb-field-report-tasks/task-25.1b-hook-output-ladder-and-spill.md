---
gmd: "0.1"
id: task-25.1b-hook-output-ladder-and-spill
title: "Task 25.1b: every generated hook command's stdout stays under 9,500 B through a degrade ladder and a per-session spill page, with the clamp as a counted safety net; plus bug-182's per-leg scan-prompt timing and conditional wall bound, and plan-2's three recall-budget riders (25.1 rev 8, split out by D-Q2)"
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
rel: depends-on -> [[feedback_injection_presentation_rules]]

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
| k2 | **This task owns the ONE names line**, labelled `still in play`. It is ONE line: the 25.1 `+N more` trailer is folded into it, and it ends with the spill page's fetch command. One cap of 15 names is shared across both member kinds, the bytes are reserved before the fit, and `(+N)` overflow goes to the spill page. Members are of two kinds: OVER-BUDGET (this task: items the ladder put at tier 4) and HELD (10.2, later). The ONE renderer (`recall_pack`, the only place the literals `still in play` and `·held` appear in `src/`) takes both kinds; the held kind is empty until 10.2 builds. Members are in ONE rank order across both kinds. **A held member prints as `<name>·held`** (10.2 h16); the suffix's bytes count inside the line's reservation; an over-budget member is unmarked. 10.2 only supplies the held flag, through `pack(held=…)` ([[#k3]]). 10.6 labels each member later, where it stands (no regrouping, 10.6 p2). **Position:** the line is LAST in the payload, after every hook line and every body or excerpt, and it ends with the spill page's fetch command (the user-agreed presentation rule: most important first, [[feedback_injection_presentation_rules]]). scan-prompt's held line (10.2 R4) sits last in scan's payload by the same rule. 10.2 is re-specced against this task, not the other way round. {#k2} | L15; contra-b CB-1; both 25.1 rev 8 R13 and 10.2 h10 state the cap of 15; L52 and L54 (B1, S2) adopt 10.2 h16's marker |
| k3 | **One pack call, one order, TIER-PINNED:** (1) the ladder runs over ALL retrieved rows in rank order, the `full` run ([[#r13]]); (2) `pack` computes `telemetry.item_key(row)` for EVERY row, and a row for which `held.covers(item_key(row), full_run_tier)` answers True (10.2's rule; nothing until 10.2 builds) leaves the tier the full run gave it and becomes a HELD member of the names line, which degrades it to the names tier by dedupe; a row `covers` answers False for keeps its tier; (3) non-held rows keep their full-run tier, and the bytes held rows free are never re-spent on promoting other rows; (4) the bodies of every row below tier 1, held rows included, and the names-cap overflow are written to the spill page ([[#r14]]); (5) the clamp runs on the whole command's stdout ([[#r12]]). The payload is never larger than the full run's. **This task is the ONE owner of `pack(held=…)`** (L59; bsd-spec-t3ab r2 S1). `held` is a protocol, not a key collection: `recall_pack.Held` (a `typing.Protocol`) with `covers(key, full_run_tier) -> bool`. `recall_pack.pack(..., held: "Held | None" = None)` performs steps 1-4 in ONE call, because each row's full-run tier is known only inside `pack`; `held=None` covers nothing. 10.2 supplies the implementation (its `HeldSet`, with h15's tier-aware rule) and never re-implements the removal. **The key is ONE function this task builds:**
`telemetry.item_key(row)` = `(scope, entity_id)`, else `(scope, kind, name)` (10.2 h8, moved here
from 10.2's Files; bsd-spec-t3ab r3 S5). Two code symbols with one name in two files are two
keys. 10.2's state, both renderers and 10.5's replay call the same function. {#k3} | CB-1 ("the order … is stated explicitly"); 10.2 h9 / the user's Q13 (freed bytes are not re-spent: the replay lost a use exactly by re-spending); agreed with spec-t3b 2026-11-13 |
| k4 | **Kind labels are not built here.** Each tier is rendered by its own function in `recall_pack`. 10.6 later decorates every tier's line with `telemetry.kind_label` (10.6 p1), and every tier carries a label from then on. Revision 8's "Kind labels (10.6) apply at every tier" is restated this way, so this task has no edge to 10.6. {#k4} | L15 (CB-5 restatement); bsd-pop-r1 S5 |
| k5 | **`form` on delivered events:** `full` (tier 1), `excerpt` (tier 2), `pointer` (tier 3), `names` (a names-line member). It joins `telemetry.RECALL_EVENT_FIELDS_V1` as a nullable field, and `v` stays 1. 10.2 R6 planned the same field; it now exists from this task, and 10.2 adds one value, `held`, for a held member on the line (10.2 R6). {#k5} | CB-2 ("Excerpt counts as a form in the delivered event") |
| k6 | Spill pages live under `stm/<session>.emitted/spill/`, one file per hook call, written only by that call {#k6} | L16's home rule for per-session emitted state; 10.2 h6 / 19.6 split: one writer per file |
| k7 | "Removed at compaction" means a page written before `stm.last_marker(root, session).ts` is gone. The fetch reports it in one `Error:` line, and the next spill write deletes those pages (the spill writer is the only deleter). The marker writer moves nothing else (10.3 R3 stays true). An unreadable marker counts as "marker now", so every older page is gone (10.3 f5, the safe direction) {#k7} | 25.1 rev 8 R14; L15 (the marker is 10.3's) |
| k8 | R15 is built only in the band L44 pre-registered; R0's table and the decision row are written before any R15 code | L44; [[feedback_go_no_go_ranges_not_predrop]] |
| k9 | The three plan-2 riders are carried with their own ACs and re-read against 25.1's code, not re-derived: #s-2 (R16), #m-4 (R17), and 19.5's #w1c-rider (the scan-prompt rerank rate, R0) {#k9} | D-Q6; [[task-19.1-pack-recall-under-budget#w1c-riders]]; lead O4 |
| k10 | **Spill page ids and retention.** `<seq>` is the page's write time in milliseconds, base 36: monotonic, never reused after a prune (so a stale token never resolves to a newer page). The file is created exclusively, and a collision takes `+1`. Every spill write prunes, as the only deleter: (a) this session's pages older than the marker ([[#k7]]); (b) this session's pages beyond its newest 50; (c) any other session's `spill/` directory whose newest page is older than 7 days. Each prune is counted on the call's row (`spill_pruned`). The 50 / 7-day values are DECIDED (lead, L58) and recorded beside the constants {#k10} | bsd-spec-t3ab M5 (no retention rule; `<seq>` unspecified); values decided by the lead, L58 |

## Requirements {#requirements}

Numbering continues 25.1's (R12-R14 and AC-16-AC-18 are revision 8's ids, kept so the plan
review's citations stay valid). R0 is this task's own measurement step (L44 names it R0).
{#requirements-lead}

0. **R0 Per-leg timing of the two per-prompt hooks (bug-182's measurement; R16's instrument).**
   - **scan-prompt:** its `query.log` row gains `legs_ms`, a map from leg name to wall
     milliseconds for every leg the call ran: envelope parse + session resolve, replica open/read,
     concept match, content leg (BM25), rerank, composite, helix, grep floor, fit/render, telemetry
     write, and, as separate legs, any wait for a lock or the daemon (`lock_wait`, `daemon_wait`).
   - **the per-prompt recall** (bsd-spec-t3ab S4): its `prompt_recall` row gains the same
     `legs_ms` field: session resolve, project leg (replica or daemon RPC, named), project rerank,
     global leg, pack/render, telemetry write, `daemon_wait`. R16's reserve is measured on its
     global leg.
   - On both rows, each leg also records `ran` / `skipped_budget` / `not_attempted`. A leg not run
     is absent, never 0. The sum of `legs_ms` and the row's total wall are both recorded.
   - **Venue (lead, O3; L54 S3):** the branch's FIRST TWO commits are the RED for AC-21 (a) and
     the `legs_ms` GREEN that turns it green. A ch-bsd lite round reviews that pair before
     anything merges. The lead then merges the pair to `master` and deploys it ahead by
     fast-forward + `rmx daemon restart --relaunch`, a lead deploy step and not user-gated (a
     `query.log` field, not an argv change, so no hook is regenerated). Live production hook runs
     are collected while R12-R14 are built, pooled over every store the deploy reaches (decided by
     the lead, L58; each store
     reported apart). The collection window runs from the early deploy until R12-R14 are GREEN,
     and R15 is decided at the window's end, before this task's GREEN closes.
   - **Fallback (L54 S3):** if fewer than 100 scan-prompt hook runs are collected in the window,
     R15 is NOT built and bug-182 moves to the T4 backlog (L44's no-build branch), with the
     counts collected cited in its row. R16's reserve is still set from whatever recall runs
     accrued, and the count is recorded beside the constant.
   - **Report:** commit `workflow/measurements/task-25.1b-scan-prompt-legs.md` with per-leg p50 /
     p90 / p95 / max for both hooks, and, for every scan-prompt run over 5 s, its DOMINANT leg (the
     leg with the largest wall). Counts only, no prompt text.
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
    raises the cap. With the ladder working it fires only on a defect.
    - **There is no single emit point today** (green-251c, reading `hooks.render_managed` at the 25.1
      branch's `23caf45`). So the shared emitter is ONE function, `hook_budget.emit(text, *,
      command, channel)`, and every rmx stdout writer that a generated hook command runs calls it.
      These are nine writer entries, which are nine functions; `cli.curator_status` runs in two
      commands, and scan-prompt and curator status share one command:
      - capped today, each by its own writer: `cli._echo_pack` (the three `memory recall --pack`
        hooks); `cli.recall_state` (`recall-state --max-bytes 9000`); `cli.scan_prompt_cmd` and
        `cli.curator_status` in UserPromptSubmit's `scan_cmd` (one command, two writers, 4,500 B /
        500 B shares); `cli.curator_status` in SessionStart's `startup|resume` command (`sess_cmd`,
        `hooks.py:208-215` on the 25.1 branch: the backgrounded primer `; rmx curator status`),
        where it is that command's only stdout writer; `cli.focus_context` (1,500 B);
      - UNCAPPED today, and reaching the agent: `cli.focus_hook` on `--event session-start` (all
        four SessionStart matchers); `rmx focus summarize --promote` (PreCompact `--timeout 30`,
        Stop `--timeout 5`; it prints the full STM digest); `rmx ingest-gmd --as-memory --detach`
        (SessionStart); `cli.save_state` (PreCompact).
    - **Shares.** A writer's share is its `hook_budget.HOOK_COMMAND_CHANNELS` share. A writer that
      is its command's only stdout writer gets the command's whole 9,500 B. Where one command holds
      several writers, their shares are listed in `HOOK_COMMAND_CHANNELS` and sum to ≤ 9,500 B, so
      the command's stdout is ≤ 9,500 B with no cross-process coordination. Each `emit` call that
      cuts writes its `capped` row, with the command id and the dropped bytes.
    - **curator status uses its FIXED `curator_status` share (500 B) in every command** (the lead,
      on bsd-spec-t3ab r2 S4). No argv identifies the command, and none is added. In SessionStart's
      `startup|resume` command, the rest of that command's 9,500 B is unused headroom.
    - **Silent by code** (they write stdout only on `session-start`, so they print nothing; their
      generated commands redirect only stderr): `focus hook` on `--event tool`, `tool-pre`, `input`
      and `say`, and 10.3's `focus hook --event compact-marker` entry. AC-26 runs each one and
      asserts empty stdout.
    - **Redirected to `/dev/null`:** `sync --flush-queue` and the backgrounded primer.
    - **Not rmx:** the PostToolUse inline python and the grep scripts.
    - A later hook command whose rmx stdout reaches the agent joins the writer list through the same
      function. {#r12}
13. **R13 Degrade ladder inside the pack.** When a payload does not fit its channel budget, items
    are degraded in rank order instead of dropped. The tier shapes (L54 S1) keep 25.1 R3 / J5's
    "every hook line before any body":
    - tier 1: the item's 25.1 hook line + its full body (25.1 R3's whole body);
    - tier 2: the item's 25.1 hook line + an excerpt, the item's first lines (its `lead` text), at
      most 3 lines and 300 B, ending on a whole line;
    - tier 3: hook line (which carries its `(rmx memory get …)` fetch pointer). That pointer is
      the scope-correct fetch address of 25.1 R6, the trailing `(rmx memory get <name>[ --scope
      global])` of `recall_pack.hook_line`;
    - tier 4: the name as a member of the single names line ([[#k2]]).

    The curated hook text (25.1 R4's lookup) is never dropped at tiers 1-3. **Layout:** the header;
    then the hook lines of every tier-1..3 item in rank order; then the bodies (tier 1) and excerpts
    (tier 2) in rank order; then the names line, last ([[#k2]]).

    The pack fills top-down. As many tier-1 items as fit are placed, while leaving room for every
    remaining item at a lower tier; then tier 2, and so on. Every retrieved item stays visible at
    some tier unless the names cap is reached; past the cap, items are counted `(+N)` and spilled
    ([[#r14]]). Tiers are monotone in rank: an item never sits at a higher tier than an item ranked
    above it. Kind labels: [[#k4]]. A tier-1 or tier-2 item renders in two places (its hook line
    and its body or excerpt block), so it has two spans ([[#amend-r9]]). `Packed` reports, for every retrieved row, its full-run tier
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
      (bug-100). `<seq>` and retention: [[#k10]].

    A missing, compacted ([[#k7]]) or unreadable page gives one clean `Error:` line, exits non-zero
    and prints no traceback. With no session (no envelope
    session), no page is written, and the names line says `(+N not paged: no session)`. {#r14}
15. **R15 scan-prompt wall bound per leg (bug-182), built only in L44's band.** After R0, the lead
    writes the decision row against L44 before any R15 code:
    - **build:** if the overrun sits in a leg the budget module controls (concept match, content
      leg, rerank, composite, helix, grep floor, fit/render), each such leg gets a wall bound in
      `hook_budget.LEG_WALL_S` (the one budget module, L39). **The bounds, pre-registered (L54
      S5):** with T = the hook's timeout (5 s) and p90ᵢ = R0's scan-prompt p90 for each bounded leg
      i, the scale is s = min(1, (T − 0.5 s) / Σ p90ᵢ) and the bound is `LEG_WALL_S[i]` = s × p90ᵢ.
      So the bounded legs plus a 0.5 s margin fit the timeout. The p90s, s and the bounds are
      recorded beside the constant. A leg that reaches its bound returns
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
    cannot spend. Its value is the global leg's p95 wall on the production hook path, measured on
    R0's per-prompt recall rows (their `legs_ms` global leg), rounded up to 0.25 s, and recorded
    beside the constant with the run count. A global leg that is
    still omitted is COUNTED on the recall row (`global_omitted: "<reason>"`) as well as warned.
    {#r16}
17. **R17 The degrade line names both numbers** (plan-2 r9 #m-4, [[task-19.1-pack-recall-under-budget#w1c-m4]]).
    The busy / degrade line a hook-mode recall prints names the daemon slice and the total budget
    separately, each labelled. For example: `recall not confirmed within the 1.5 s daemon slice (hook
    budget 5 s) — daemon busy; the hook skipped this turn`. {#r17}

### Amendments to 25.1, by name {#amends}

The ladder changes four rules 25.1 states. Each is amended here, and nothing else in 25.1 moves
(contra-b CB-2). {#amends-lead}

- **25.1 R3** ("one hook line per named hit, ALL before any body; whole bodies only, greedily in
  rank order; a `+N more: <cmd>` trailer"): the layout survives. Every tier-1..3 hook line comes
  before any body or excerpt ([[#r13]]). Bodies that fit are still whole (tier 1). Items that do
  not fit degrade per [[#r13]] instead of being dropped. The `+N more` trailer is replaced by the
  names line ([[#k2]]), which sits last and ends with the spill page's fetch command. {#amend-r3}
- **25.1 R8** ("distinct named hits + trailer N = hits retrieved; bodies ⊆ named; a body never
  counts as a second named hit"): items at tiers 1-3 + names-line members + `(+N)` overflow = hits
  retrieved. Tier-1 bodies ⊆ items at tiers 1-3. An excerpt is that item's rendering, never a
  second named hit. Spilled items are counted once, at the tier where they are visible, or in
  `(+N)`. {#amend-r8}
- **25.1 R9** ("spans … never for a trimmed hit"): every item at tiers 1-3 emits ONE `delivered`
  event, with `form` per [[#k5]]. Its hook-line span slices its hook line, and a tier-1 or tier-2
  item also has a body span that slices its body or excerpt block (25.1's two-span shape; null
  body fields at tier 3). A names-line member emits a
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
- **AC-26 Every writer goes through the one emitter** (R12's writer list). The test renders every
  generated hook command (`hooks.render_managed` / `hooks._claude_hook_block`) and, for each rmx
  producer in it, forces the producer to emit 20 KB on a fixture and runs the command with `bash
  -c`. For every command: stdout ≤ 9,500 B; a `capped` row carries that command's id; each writer's
  output is within its `HOOK_COMMAND_CHANNELS` share. A structural check parses `src/refmatrix/` and
  fails if any of the nine writer functions named in R12 writes to stdout other than through
  `hook_budget.emit`. Both curator-status commands are covered: UserPromptSubmit's `scan_cmd`, and
  SessionStart's `startup|resume` command, where curator status alone is ≤ 500 B (its fixed share)
  and the command's stdout is ≤ 9,500 B. The five silent-by-code commands (`focus hook` on
  `tool`, `tool-pre`, `input`, `say`, `compact-marker`) are each run with an envelope and print
  empty stdout. `sync --flush-queue` and the backgrounded primer are asserted to redirect stdout to
  `/dev/null`. The four writers uncapped today are RED at HEAD. Mutations: one of the four
  uncapped writers (e.g. `focus summarize --promote`) prints directly, bypassing the emitter
  (FAIL: its command exceeds 9,500 B and the structural check fires); two writers of one command
  given shares that sum over 9,500 B; a cut with no `capped` row; a silent-by-code command that
  prints (e.g. `--event input` echoing its envelope; FAIL: non-empty stdout); curator status
  emitting the whole command budget in SessionStart (FAIL: > 500 B). {#ac-26}
- **AC-27 Spill ids and retention ([[#k10]]).** On a sandbox `stm/`, through the recall verb's
  spill writer:
  - session S holds 55 pages; one more spill write leaves exactly the newest 50 plus the new page's
    effect (the newest 50 overall), and the call's row carries `spill_pruned` with the count;
  - another session's `spill/` whose newest page is 8 days old is removed, and one whose newest
    page is 6 days old is kept, both counted;
  - a token issued for a page that a later prune removed gives one `Error:` line and never
    resolves to a page written after the prune; `<seq>` values are strictly increasing across the
    prune.

  Mutations: a prune that keeps a 51st page; a token resolving to a page written after a prune
  (`<seq>` reused); a prune not counted on the row; the other-session sweep at 6 days. {#ac-27}
- **AC-17 (R13).** 40 retrieved items at 20 KB total, with 25.1-shaped hook lines of 250-370 B, at
  a 9,000 B budget. Every item is visible: at tiers 1-3 (its hook line printed, carrying its curated
  hook), as a names-line member, or, past the cap of 15, counted in `(+N)` and on the spill page.
  Tiers are monotone in rank. The payload is ≤ budget. The tier-1 count is maximal for the room
  left. The layout is header → hook lines → bodies / excerpts → names line, in that order.
  Mutations: drop instead of degrade; an excerpt longer than its cap; tiers out of rank order; a
  tier-3 item printed without its hook text; a body printed before the last hook line. {#ac-17}
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
  each tier-1..3 item has one `delivered` event with the matching `form`. Its hook-line span
  slices exactly its hook line out of the payload bytes, and at tiers 1-2 its body span slices
  exactly its body or excerpt block (null at tier 3). Each names member has a `form: "names"`
  event whose span is the names line, the payload's last line. Each `(+N)` item has a `retrieved` event and no `delivered` one.
  21.5's reader and the hook-cost report run clean over a file that mixes `form`-less 25.1 rows
  with the new ones. Mutations: a `delivered` event for a `(+N)` item; a tier-2 event whose body
  span covers the hook line. {#ac-20}
- **AC-21 (R0, R15).** (a) The generated scan-prompt command and the generated per-prompt recall
  command each write `legs_ms` with every leg they ran and its ran / skipped / not-attempted
  outcome; the recall row names its global leg. A leg that did not run is absent, not 0. (b) R0's
  measurement file exists with the run counts, the per-leg table for both hooks, the dominant-leg
  table, O5's classification, the rerank leg's ran / skipped / not-attempted rate (19.5's rider),
  and, if built, R15's p90s, scale and bounds. The branch's first two commits are the AC-21 (a)
  RED and the `legs_ms` GREEN, and a ch-bsd lite report over them is dated before the early merge.
  The decision row against L44 precedes the first commit that touches a leg bound (commit order
  checked). With < 100 scan-prompt runs, the decision row says "not built (fallback)". (c) If
  built: on a
  fixture where one bounded leg is slow on real data (e.g. the grep floor over a large generated
  tree under the sandbox root, not a patched function), the generated command exits 0 within 5 s,
  `legs_ms` marks that leg `capped`, and the other legs' output is kept. If not built: bug-182's
  row cites R0's table and sits on the T4 backlog line. Mutations: a skipped leg written as 0
  (AC-21 a); the `legs_ms` GREEN committed before its RED (AC-21 b, commit order); (if built) a leg
  bound read from outside `hook_budget`; a bound not equal to s × p90 (AC-21 b checks the recorded
  values against the constant); R15 built on < 100 runs (a leg-bound commit present while the
  recorded scan-prompt count is < 100: AC-21 b fails). {#ac-21}
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
  23.0's guard records 0 connects to any live socket. Mutation: the `--page` click option removed
  (the parity test fails). {#ac-24}
- **AC-25 The held marker and `Packed`'s tiers** (L54 B1; L55; bsd-spec-t3ab M4). Unit table over
  `recall_pack.pack` on the AC-17 fixture:
  - with `held` empty: every row's rendered tier equals its full-run tier, and every `(+N)` row
    reports `overflow`;
  - with a test `Held` (a small concrete class in the test file implementing the protocol; it
    stands in for 10.2's `HeldSet` and is registered in `workflow/test_mock_registry.md`, see
    [[#files]]) whose `covers` is True at every tier for a tier-1 row r and a tier-3
    row q: r and q render as `r·held` and `q·held` on the names line, in one rank order with the
    over-budget members, which are unmarked; r's and q's rendered tier is `names` and their
    full-run tiers are unchanged; every other row keeps its full-run tier (tier-pinned, [[#k3]]);
    the payload is ≤ the full run's and ≤ budget; the names line is the last line;
  - **`covers` false at the full-run tier:** a `Held` that knows row p but answers `covers(p,
    tier)` True only for `pointer` or poorer, with p's full-run tier `full`. p keeps tier 1 (hook
    line + body, no `·held`), and its rendered tier equals its full-run tier;
  - **same name, two files:** two rows named `x` from `src/a.py` and `src/b.py` (distinct
    `entity_id`s, so distinct `telemetry.item_key`s), and a `Held` whose `covers` is True only for
    the `src/a.py` key. Only that row moves to the names line; the `src/b.py` row keeps its tier.

  Mutations: marker missing on a held member; marker on an over-budget member; the marker's bytes
  left out of the line's reservation (the payload exceeds the budget on a fixture sized to the
  byte); the rendered tier reported as the full-run tier; a non-held row promoted into freed
  bytes; the names line placed above the hits; membership used instead of `covers` (a row moves
  to the line whenever `held` knows its key, whatever its full-run tier: p goes to the line and
  the covers-false leg FAILS); `pack` keys rows by name instead of `telemetry.item_key` (both `x`
  rows move: the same-name leg FAILS). {#ac-25}

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/hook_budget.py` | `HOOK_HARD_CAP_BYTES`, the shared emitter, `GLOBAL_LEG_RESERVE_S`, `LEG_WALL_S` (only if R15 is built) |
| `src/refmatrix/recall_pack.py` | the ladder (one render function per tier), the `Held` protocol (`covers(key, full_run_tier) -> bool`) and `pack(held=…)` with tier-pinned removal (the ONE owner; 10.2 passes its `HeldSet`), the names line (the only home of `still in play` and `·held`), `Packed` gains per-row full-run and rendered tier and `form` |
| `src/refmatrix/stm.py` | spill page write, read and prune ([[#k10]]) under 10.3's `.emitted` directory helper; reads `stm.last_marker` |
| `src/refmatrix/hooks.py` | `HOOK_COMMAND_CHANNELS` shares for every generated command with rmx stdout (via `hook_budget`) |
| `src/refmatrix/cli.py` (the nine writer functions, [[#r12]]) | `_echo_pack`, `recall_state`, `scan_prompt_cmd`, `curator_status`, `focus_context`, `focus_hook` (session-start), `focus summarize`, `ingest-gmd --as-memory --detach`, `save_state` write through `hook_budget.emit` |
| `src/refmatrix/verbs.py` (`memory_recall`) | the `page` parameter; the global leg's reserve and `global_omitted`; the degrade wording (R17) |
| `src/refmatrix/cli.py` | `rmx memory recall --page <token>`; `legs_ms` on scan-prompt's and the per-prompt recall's rows; the R17 wording around `RECALL_DAEMON_SLICE_S` |
| `src/refmatrix/scan.py` | per-leg timing; leg bounds (only if R15 is built) |
| `src/refmatrix/telemetry.py` | `item_key` (the ONE item key, 10.2 h8; built here, [[#k3]]); `form`, `capped`, `dropped_bytes`, `legs_ms`, `global_omitted`; `rmx telemetry --context` prints clamp firings |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated from Python in the task's clone, never by `rmx install-hooks` against a live store |
| `tests/test_task25_1b_ladder_spill.py` (new) | AC-16..AC-27 |
| `tests/test_verb_parity.py` | the `page` twin |
| `workflow/measurements/task-25.1b-scan-prompt-legs.md` (new) | R0's table and the L44 decision row |
| `workflow/test_mock_registry.md` | AC-22's rerank double; AC-25's test `Held` class, standing in for 10.2's `HeldSet` (`internal-pending` at this task's build, because `HeldSet` is not built yet; it becomes `internal-active` when 10.2 lands; graduation: replaced by `stm.HeldSet` in 10.2's AC-2) |
| `workflow/bug_registry.md` | bug-182 (fixed by R15, or moved to the T4 backlog with R0's numbers); bug-164's row names this task for the hard cap |

## Test strategy {#test-strategy}

- The branch opens with its own micro-cycle: AC-21 (a) RED (no `legs_ms`), then the `legs_ms`
  GREEN, then a ch-bsd lite round over the pair, then the lead's early merge and deploy ([[#r0]]).
- Then RED, at `master` after 25.1, 10.3 and that pair: AC-16 (no shared emitter), AC-17 (25.1
  drops instead of degrading), AC-18 (no page), AC-22, AC-23, AC-25. Each red run is recorded. A RED that passes at HEAD is not a RED ([[feedback_red_test_must_fail_at_head]]).
- No mock of the pack, the emitter, the generator, STM or telemetry. The one stand-in is AC-22's
  rerank double, which is registered.
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]].

rel: depends-on -> [[feedback_red_test_must_fail_at_head]]
rel: depends-on -> [[feedback_commit_before_mutation_revert]]
rel: depends-on -> [[feedback_clear_pycache_after_mutation]]

## Decisions taken by the lead (2026-11-13) {#open-decisions}

The five open decisions of the first draft were ruled by the lead on 2026-11-13, each on the
recommended option, and the lead accepted two of the writer's later calls as decided (L58). Each
ruling is folded into the requirement it names. {#open-decisions-lead}

| # | decision | ruling | folded into |
|---|---|---|---|
| O1 | The fetch command's spelling: rev 8's `rmx recall --page` named the graph hybrid retrieval, not memory recall | `rmx memory recall --page <token>`, verb `memory_recall(page=…)` | [[#r14]], AC-18 |
| O2 | Page addressing: the agent's Bash call has no session id, and the newest-ring fallback is bug-100's defect | token `<session[:8]>-<seq>`, resolved by prefix under `stm/`; an ambiguous prefix gives one `Error:` line | [[#r14]], AC-18 |
| O3 | Where R0's ≥ 100 runs come from | `legs_ms` lands as the branch's first TWO commits (its AC-21 a RED, then GREEN), reviewed by a ch-bsd lite round, then deployed ahead by fast-forward as a lead deploy step (not user-gated; no hook regeneration); live runs collected while R12-R14 build; R15 decided at the window's end, before GREEN closes; < 100 runs → R15 not built (L54 S3) | [[#r0]], AC-21 |
| O4 | 19.5's #w1c-rider sat in frozen 19.5, so plan-2 could not close | R0 records the rerank leg's outcome and closes it here, as the third plan-2 rider | [[#r0]], [[#k9]], AC-21 |
| L58-a | Spill retention values ([[#k10]]) | newest 50 pages per session; another session's `spill/` directory is dropped once its newest page is older than 7 days | [[#k10]] |
| L58-b | R0's run set ([[#r0]]) | the ≥ 100 runs are pooled over every store the early deploy reaches, and each store is reported apart | [[#r0]], AC-21 |
| O5 | How "sits in" is decided for L44 | dominant leg per > 5 s run; ≥ 50% controllable → bound every controllable leg dominating ≥ 10%; ≥ 50% waits → not built; split → both | [[#r15]] |

## Q8 {#q8}

Holds under Q8 a and c, and under b: per-prompt recall excludes `session/*` in hook modes, so the
ladder and the spill page never carry a save-state under any option. Nothing here is a `#q8-b`
line. {#q8-body}

## Definition of done {#done}

- The `legs_ms` RED/GREEN pair, its ch-bsd lite report, and the early deploy, in that order. R0's
  measurement and the L44 decision row committed before any R15 code; RED and GREEN runs
  recorded; the mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-25.1b-hook-output-ladder-and-spill.md`.
- Committed on branch `task-25.1b-hook-output-ladder-and-spill` and merged `--no-ff` to `master`.
  The `install-hooks` window is the user's (G31), batched with any window that falls together (C11).
- With this task merged, plan-2's three riders are landed: #s-2 and #m-4 (D-Q6) and 19.5's
  #w1c-rider (lead, O4).

## Revision round 1 (2026-11-13, ch-bsd joint spec review r1; lead ruling L54) {#rev-round-1}

Folds [[bsd-spec-t3ab-ff1d453-369e0b5]] (DIRTY 1B/10S/10M) for this file, on the lead's rulings
L54 and L55. {#rev-round-1-lead}

rel: derives-from -> [[bsd-spec-t3ab-ff1d453-369e0b5]]
rel: implements -> [[plan-review-2026-11-13#lead]]

| finding | change | anchor |
|---|---|---|
| B1 the `·held` marker left open here | adopts 10.2 h16: the renderer prints `<name>·held`, inside the line's reservation; over-budget members unmarked; one rank order; `pack(held=…)` performs the tier-pinned removal; AC-25 + mutations | [[#k2]], [[#k3]], AC-25 |
| S1 tier shapes and layout undefined | tier 1 / 2 / 3 = 25.1 hook line + body / excerpt / nothing (the hook line carries the pointer); tier 4 = the name; header → hook lines → bodies → names line; two spans at tiers 1-2; AC-17 and AC-20 re-derived | [[#r13]], [[#amend-r3]], [[#amend-r9]], AC-17, AC-20 |
| S2 the line's position | last in the payload, ending with the fetch command; scan-prompt's held line likewise | [[#k2]], AC-20, AC-25 |
| S3 `legs_ms` first vs RED-first; no review; no fallback | the first two commits are its RED and GREEN; a ch-bsd lite round before the early merge; < 100 runs → R15 not built; store set and window named | [[#r0]], AC-21, [[#test-strategy]], [[#done]] |
| S4 R16 had no instrument | R0 times the per-prompt recall's legs too; R16 reads its global leg | [[#r0]], [[#r16]], AC-21 |
| S5 R15's bounds had no rule | s = min(1, (T − 0.5 s) / Σ p90ᵢ); bound = s × p90ᵢ | [[#r15]], AC-21 |
| M3 title said two riders | three | title |
| M4 ACs without mutations; `Packed` tiers unpinned | AC-21, AC-24 mutations; AC-25 pins full-run / rendered tiers and `overflow` | AC-21, AC-24, AC-25 |
| lead input (green-251c on `hooks.render_managed` at `23caf45`): no single emit point | R12 names all eight stdout writer entries, nine functions (four entries capped, four uncapped), the share rule and the out-of-scope list; AC-26 with a bypass mutation | [[#r12]], AC-26 |
| M5 spill retention and `<seq>` | `<seq>` = write ms base 36, exclusive create; prune at marker, beyond the newest 50, and other sessions' dirs older than 7 days (values decided by the lead, L58) | [[#k10]] |
| `form` value `held` (M2's 25.1b half) | `#k5` names it | [[#k5]] |

## Revision round 2 (2026-11-13, ch-bsd joint spec review r2; lead ruling L59) {#rev-round-2}

Folds the r2 report (DIRTY 0B/2S/8M; every r1 B/S closed) for this file. {#rev-round-2-lead}

rel: implements -> [[plan-review-2026-11-13#lead]]

| finding | change | anchor |
|---|---|---|
| S1 two specs built `pack(held=…)` with incompatible types | this task is the ONE owner; `held` is the `Held` protocol with `covers(key, full_run_tier) -> bool`; one pack call; AC-25 gains a "`covers` false" leg and the mutation "membership used instead of `covers`" | [[#k3]], [[#files]], AC-25 |
| m1 retention labelled PROVISIONAL; untested | the labels already read DECIDED (L58) since `72d578e`; AC-27 tests `#k10` with four mutations | [[#k10]], [[#r0]], AC-27 |
| m2 O3 row stale | refreshed: two commits, the ch-bsd lite round, the < 100 fallback | [[#open-decisions]] |
| m3 tier-3 wording | "hook line (which carries its `(rmx memory get …)` fetch pointer)", the exact text 10.2 and 10.6 match | [[#r13]] |
| m7 AC-21's fallback had no mutation | "R15 built on < 100 runs" | AC-21 |
| r3 S5 nobody owned the key `pack` passes to `covers` | this task builds `telemetry.item_key` (10.2 h8, moved from 10.2's Files); `pack` calls it for every row; AC-25 same-name leg and the mutation "pack keys by name" | [[#k3]], [[#files]], AC-25 |
| r3 m1 tier-3 wording | this task's string is canonical (lead); 10.2 and 10.6 copy it verbatim | [[#r13]] |
| r3 m3 AC-25's test `Held` unregistered | registered via the Files row, with its graduation | [[#files]], AC-25 |
| S3 (r2, on `b032f24`) the out-of-scope list called silent commands `/dev/null` | silent by code: `focus hook` `tool` / `tool-pre` / `input` / `say` and 10.3's `compact-marker` (AC-26 asserts empty stdout, with a mutation); `/dev/null` kept only for `sync --flush-queue` and the primer | [[#r12]], AC-26 |
| S4 (r2, on `b032f24`) curator status runs in two commands | SessionStart's `startup|resume` command named; curator status uses its fixed 500 B share everywhere, with no new argv; AC-26 covers both commands, with a mutation | [[#r12]], AC-26 |
