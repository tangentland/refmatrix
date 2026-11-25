---
gmd: "0.1"
id: agent-brief-p1b-proportionality-review
title: "Brief: P1 (b), the proportionality review of every plan and spec still on the queue"
tags: [agent-brief, p1, proportionality, specs, queue, read-only]
metadata:
  node_type: brief
  status: approved
  created: 2026-11-24
  author: ch-architect (Fable 5.2)
---

# P1 (b): the proportionality review {#root}

> Status: drafted for the spec window (L232, L233); the lead approves. Queue row P1, part
> (b). Read-only, P lane, on Fable (it judges specs). One agent; it edits no plan, spec or POP
> row and writes one report. **The user approves every cut before any spec is edited.**

rel: depends-on -> [[plan-of-plans#queue]]
rel: depends-on -> [[orchestration#planning]]
rel: depends-on -> [[orchestration#proportionate]]
rel: derives-from -> [[admitted-audit-2026-11-24#table]]
rel: derives-from -> [[test-suite-audit-2026-11-15#speed]]

## The ask {#ask}

L164 and L165 cut the ceremony for new work: specs are one page, no ch-bsd round on a spec,
one confirm trial per reproduced row, mutations on `src/` only, one ch-bsd pass on a large
change. Most specs on the queue were written before that and still carry the old load
(`task-23.1-queue-and-drain.md` is 2,103 lines, `task-29.5-split-giant-modules.md` 1,558).
Say, for each, what the old load would cost if it were followed, and what to cut, each cut
with a one-line reason. {#ask-body}

## Scope {#scope}

Every plan file and task spec behind a row of [[plan-of-plans#queue]] that is not done and
not post-mod, the L232 window's new specs included; [[admitted-audit-2026-11-24#table]] is
the list and gives each spec's approval and staleness. Not in scope: finished rows, post-mod
plans, ADRs, measurements, ch-bsd reports. {#scope-body}

## Method {#method}

1. **Inventory, by script.** For each file: lines; acceptance criteria; sections that are
   revision history, round folds or fold tables; planned review rounds (ch-bsd spec rounds,
   confirm-lites, "before RED" re-reads); proof bands (N-pass runs, repeated full suites);
   mutation rows, split into `src/` and test-side; its queue row and distance from the head.
   Commit the script beside the report. {#m-inventory}
2. **Price the old load.** A ch-bsd round is one agent run and a fold; a proof band is run
   time, priced from `tests/shard_weights.json` and
   [[test-suite-audit-2026-11-15#speed]]. Give each spec's cost if followed as written, in
   rounds and minutes, not adjectives. {#m-price}
3. **One verdict per file.** {#m-verdict}
   - `leave`: it is within the L165 shape, or its RED starts inside the current window and a
     rewrite would cost more than it saves.
   - `trim`: delete only history, fold tables and round ceremony; every requirement and
     acceptance criterion stays word for word.
   - `rewrite at entry`: the audit marks it `stale (revise)`; it is rewritten to one page
     when its row enters the spec window, not now.
   - `covered by rule`: its only excess is process text that
     [[orchestration#root]] already overrides ("where they say more, this file wins").
4. **Test the cheapest cut first** ([[orchestration#proportionate]]). Before proposing N
   edits, count how many specs need no edit at all if one ruling says: "an older spec's
   review rounds, proof bands and test-side mutations are replaced by
   [[orchestration#task]]". List the specs where that is not enough because the ceremony is
   written into an acceptance criterion. {#m-cheapest}
5. **What is never a cut.** A requirement, an acceptance criterion, a named mutation on
   `src/`, a user decision, or a measured band the user set (L204's 10 s, 31.5's capture
   size). If one of these looks excessive it goes in the questions list with the reason, and
   is not proposed as a cut. {#m-never}

## Rules {#rules}

Work in a littlebig clone at the lead's base sha, read-only against every live store:
lookups through `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master` read verbs or the
read-only refmatrix MCP tools, then `git log`, then raw reads. Never `find /`; never an
`rmx` write verb; never export `REFMATRIX_ROOT`. Status comes from the POP and its rulings,
never from a file's `metadata.status`. {#rules-body}

## Output {#output}

`workflow/measurements/proportionality-review-<date>.md` (GMD; an anchor on every heading;
`rel:` edges to the POP anchors cited), committed on the branch with its inventory script:
{#output-lead}

- one table, a row per file: row, file, lines, ACs, rounds planned, bands, mutation rows
  (`src/` and test-side), cost if followed, verdict, the cut in one line, its reason, what
  the cut puts at risk;
- totals: lines and rounds before and after, by verdict;
- the ruling text of step 4 and the specs it does not cover;
- the questions for the user, each with a recommendation;
- anything the audit's table now gets wrong.

Done means: the table's row count equals the inventory's file count; every `trim` names the
sections it deletes; no file was edited; `./scripts/lint-gmd.sh` exits 0. Report as text:
the counts per verdict, the totals, and the questions. {#done}

## What happens after {#after}

The lead puts the report's cuts and questions to the user. Approved `trim` cuts are applied
by one agent in one commit, checked by a script that shows each trimmed spec's requirement
and criterion text is unchanged. `rewrite at entry` specs are handled by the spec window as
their rows arrive. {#after-body}
