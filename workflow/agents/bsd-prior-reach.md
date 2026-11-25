---
gmd: "0.1"
id: agent-brief-bsd-prior-reach
title: "Brief: forward prior/reach columns for ch-bsd findings (Q92 = a, L259), small fix"
tags: [agent-brief, small-fix, ch-bsd, ledger, bsd-tally]
metadata:
  node_type: brief
  created: 2026-11-25
---

# Forward `prior` / `reach` on every ch-bsd finding {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: amends -> [[bsd-open-findings#question-column]]

**Why.** The user (Q92 = a): beside the self-audit `question`, every BULLSHIT-level and GATE row
records what was already known (`prior`) and whether it reached the author (`reach`), so the
ledger tallies retrieval misses, salience misses, check gaps and novel defects going forward.
M7 labels the closed rows retrospectively ([[agent-brief-m7-prior-knowledge#labels]] has the
value sets; use them verbatim). {#why}

## Change {#change}

1. `workflow/bullshit/OPEN.md` and `CLOSED.md`: two columns after `question`: `prior` and
   `reach`. Existing rows get `pending (M7)` in BULLSHIT-level and GATE rows, `-` elsewhere. The
   `#question-column` paragraph gains one sentence for each, with the value sets.
2. `scripts/bsd-tally.py`: tallies `class` (derived from `prior` + `reach` per the M7 rules) for
   BULLSHIT-level and GATE rows, alongside the question tally; exits 1 on an empty or `-` cell in
   such a row (as it does for `question`); `pending (M7)` is counted and printed, not an error.
3. `.claude/agents/ch-bsd.md` (the report format section) and `ch-bsd.local.md` if it restates
   the format: each BULLSHIT and GATE finding gains a `**Prior knowledge:**` line naming the
   artifact (`<doc-id>#<anchor>` with its date, or `none`) and where the author could have met it
   (the brief, the definition, a read; ch-bsd reads the brief named in its dispatch), and the
   report's "For the lead to persist" OPEN rows carry both cells.

4. **Lead amendment (2026-11-25, bsd-prior's question):** `class` cannot be derived from
   `prior` + `reach` (a reached prior is a salience miss or a check gap). So a third column,
   `class`, follows `reach`, with M7's value set; the tally reads it, and checks consistency
   (`novel` iff `prior` is `none`; `retrieval-miss` iff `reach` is `not-reached`), exiting 1 on a
   contradiction. Rows before M7 get `pending (M7)` in all three.

{#change-list}

## How {#how}

Small-fix path: one agent, test seen failing first. Extend `tests/test_bsd_findings_ledger.py`
(parametrize): the new columns parse; an empty `prior` in a BULLSHIT row exits 1 naming the row;
`pending (M7)` is counted; the class tally matches a planted table. Run `scripts/bsd-tally.py`
on the real files after the change. Work in `/Volumes/littlebig/refmatrix-bsd-prior`, branch
`bsd-prior-reach` from the dev tree's `master`. Verify on a lane: the touched tests plus the
repo guards (`test_docs_generated`, `test_suite_discipline`, `test_deferrals_clean`,
`test_bug212_r4_red`, `test_tmp_root_census`). `./scripts/lint-gmd.sh` zero errors. Never touch
the dev tree, never push; read-only on every live store. Report: shas, E lines, lane counts.
{#how-body}
