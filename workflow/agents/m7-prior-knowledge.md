---
gmd: "0.1"
id: agent-brief-m7-prior-knowledge
title: "Brief: M7, per ch-bsd finding, what was already known and whether it reached the author (Q92 = a, L259)"
tags: [agent-brief, measurement, m-lane, ch-bsd, injection, labelling]
metadata:
  node_type: brief
  created: 2026-11-25
---

# M7: what should the author have known? {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: depends-on -> [[bsd-closed-findings]]

**Why.** The user (Q92 = a): for each ch-bsd finding, measure what could have been injected that
would have prevented it. The `question` column names the self-audit CHECK that would have caught
a finding (27 of 37 BULLSHIT rows are `unnamed`); this measures the KNOWLEDGE. Subagents get no
prompt-scan or SessionStart injection today: their brief, their agent definition and overlay, and
what they read are all they had. {#why}

## The rows {#rows}

Every closed row in `workflow/bullshit/CLOSED.md` whose level is BULLSHIT, SKETCHY → BULLSHIT
(F8), or any GATE (about 51). Each row names its report; the report names the commit range, the
clone, and usually the brief.

## The labels, per row {#labels}

Write one JSON object per row to `labels-<you>.jsonl`:

- `id`: the row id.
- `prior`: the earliest artifact that already covered the defect BEFORE the range's base commit
  date, as `<doc-id>#<anchor>` (a memory, a ch-bsd impression, a bug-registry row, a
  `.claude/rules/` file, an ADR or spec anchor, `CLAUDE.md` / `PROJECT_PROFILE.md` anchor), or
  `none`. "Covered" means a reader who had it would have avoided this defect. Check the date
  with `git log --diff-filter=A --format=%ad -- <file>` (or the memory's `created:`).
- `prior_kind`: memory | impression | bug-row | rule | adr | spec | claude-md | none.
- `reach`: where the author could have met it: `brief` (the agent brief for that work quotes or
  links it), `definition` (the agent's `.claude/agents/<name>.md` or `.local.md`), `read` (the
  author's transcript shows a Read or recall of it), `injected` (a hook delivered it; rare for
  subagents), `not-reached`, or `n/a` when `prior` is `none`.
- `class`: `retrieval-miss` (prior exists, not reached), `salience-miss` (reached, still made),
  `check-gap` (knowledge existed only as prose that no check enforces, and it was reached or the
  author was the lead), or `novel` (prior `none`).
- `confidence`: high | medium | low, and `why`: one sentence, repo text only.

{#labels-body}

Author transcripts, when needed for `read`: the session's subagent transcripts under
`~/.claude/projects/-Users-tholley-claude-tools-refmatrix/` (read-only; search by the brief's
path or the branch name; never copy their text into the repo). If you cannot find the author's
transcript, say `reach: unknown-transcript` rather than guess.

## Two labellers, then a reconciler {#process}

Two labellers work independently from this brief; neither reads the other's file. Each commits
`workflow/measurements/prior-knowledge-2026-11-25/labels-<a|b>.jsonl` on its own branch. The
reconciler (a third step) reports: agreement on `class` (Cohen's κ with interval) and on `prior`
(exact match, and same-artifact match), the class shares with Wilson intervals over the agreed
rows, the disagreements listed, and for every agreed `retrieval-miss` the recall test: does
`scripts/rmx-master memory recall "<the brief's first 300 words>" --k 10` (or `rmx-master
context`) return the prior today? The share it does is the estimate of what agent-start context
(I1.g) would have prevented. Write `docs/architecture/explorations/prior-knowledge.md` (GMD).
{#process-body}

## Rules {#rules}

Read-only against every live store; `rmx-master` read verbs and the read-only MCP tools only.
Copies only for any log. Nothing raw in the repo: no transcript text, no prompt text; ids,
anchors, counts and one-sentence reasons in your own words. Never `find /`, never export
`REFMATRIX_ROOT`, never push, never touch the dev tree. Work in your own littlebig clone from the
dev tree's `master`. `./scripts/lint-gmd.sh` zero errors. Report the sha and the counts.
{#rules-body}
