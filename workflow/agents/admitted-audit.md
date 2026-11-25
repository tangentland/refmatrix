---
gmd: "0.1"
id: agent-brief-admitted-audit
title: "Brief: admitted-audit — every item admitted before the mod, checked for its plan, spec and approval"
tags: [agent-brief, audit, pop, freeze, read-only]
metadata:
  node_type: brief
  created: 2026-11-24
---

# admitted-audit {#root}

rel: depends-on -> [[plan-of-plans#freeze]]
rel: depends-on -> [[plan-of-plans#queue]]

The user, 2026-11-24: "we should review all of the admitted items to make sure they have specs
and approvals." Read-only audit; one table; no plan, spec or POP edits. {#ask}

## What "has a spec and approval" means here {#standard}

Q55 = a (L221, 2026-11-24): a plan is `approved` when the plan itself is approved and its NEXT
task has an approved one-page spec (L165, just in time). Later tasks are not required to be
specced. So for each admitted item check:

1. **Admission:** the L-row (or freeze-list item) that admits it. None found = `unadmitted`.
2. **Plan:** the plan file exists and its approval is recorded — by an L-row, a ch-bsd GO the POP
   cites, or the user's words in a ruling. `metadata.status` alone is NOT evidence: statuses lag
   decisions (triage from the latest consolidation and rulings, never from file status).
3. **Next task:** which task is next (from `#queue` order and what has merged — check
   `git log --oneline master` and `workflow/pop-finished.md`), and whether its spec exists and is
   approved, with the evidence.
4. **Stale:** a spec older than code it depends on that has since changed (name the change), or a
   spec that cites superseded rulings (`rel: supersedes` / later L-rows). Report, do not fix.
5. **Item with no plan by design** (a probe, a confirm round, a bug fix): record that and whether a
   brief or registry row stands in for the spec.

## Scope {#scope}

Every row of `workflow/plan-of-plans.md` `#queue` and every item the `#freeze` list, its L128
amendment and later L-rows admit (L195 C1, L212 C2, L214 I1 and H1, L226's re-triage moves
including I1.a-I1.i and H1.a-H1.g, L229's practice pack). Include items marked done only to
confirm they are in `pop-finished.md`; do not audit them further. {#scope-list}

## How {#how}

Work in the dev tree read-only (no clone needed; you write one file only, see below). Lookups:
`/Users/tholley/claude_tools/refmatrix/scripts/rmx-master context|query|where|locate …` or the
read-only refmatrix MCP tools, then `git log`, then raw reads. Never `find /`; never run `rmx`
write verbs; never export `REFMATRIX_ROOT`. {#how-rules}

## Output {#output}

Write `workflow/measurements/admitted-audit-2026-11-24.md` (GMD: frontmatter with `gmd: "0.1"`,
`id: admitted-audit-2026-11-24`, title, tags; an anchor on every heading; `rel:` edges to the POP
anchors you cite). One table, one row per item:

| item | POP row | admitted by | plan (file, approval evidence) | next task | its spec (file, approval evidence) | stale? | verdict |

Verdict is one of: `ready` (plan approved, next task specced and approved), `needs-spec` (next
task unspecced), `needs-approval` (spec exists, approval not found), `needs-plan`, `stale`,
`unadmitted`, `no-plan-by-design (ok)`, `done`. Then a short list grouped by verdict, and any
contradiction you hit between the POP and the files. Lint it with `./scripts/lint-gmd.sh`
(0 errors). Do NOT commit; the lead commits. Report as text: the counts per verdict and the
non-`ready` rows. {#output-shape}
