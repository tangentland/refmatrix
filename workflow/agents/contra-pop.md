---
gmd: "0.1"
id: agent-brief-contra-pop
title: "Brief: contradiction sweep for the 2026-11-13 plan-of-plans consolidation (contra-a..e)"
tags: [agent-brief, plan-review, contradictions]
metadata:
  node_type: brief
  created: 2026-11-13
---

# Contradiction sweep brief (contra-a .. contra-e) {#root}

The user, 2026-11-13: re-evaluate the plan-of-plans and consolidate, and "there have to be
contradictions". The lead's draft is `workflow/plan-review-2026-11-13.md` (read it first; its
track table names the clusters). Five read-only sweepers each take one cluster and hunt for
contradictions. Repo: `/Users/tholley/claude_tools/refmatrix` (dev master `0d2a270`).

rel: part-of -> [[plan-review-2026-11-13]]

## Rules {#rules}

- **READ-ONLY.** Do not edit, commit, run pytest, start daemons, or touch `.refmatrix/`. Do not
  write files; return the report as text (the lead persists it).
- Never search from `/`; scope every find/grep to the repo. Use `rmx context <id>` / `rmx grep`
  freely (read path). `git log` / `git show` on master are fine.
- **Every finding quotes both sides** with `path:line` (or commit sha) — no paraphrased
  contradictions. A finding you cannot quote is not a finding.
- Read identifiers (shas, statuses, ids) from the files at the time you cite them; never recall.

## What counts as a contradiction {#kinds}

| kind | meaning |
|---|---|
| K1 spec↔spec | two task specs / plans require incompatible behaviour, numbers, names or ownership of the same thing |
| K2 decision↔spec | a recorded decision (POP override paragraph, `plan-review-2026-10-07` / `-10-14` decision rows, `workflow/open-questions.md` answers, an Accepted/Proposed ADR, a user quote) that a spec never folded, or folded differently |
| K3 order↔dependency | POP / handoff order vs a spec's `Depends on`, cycles, a task gated on something sequenced after it |
| K4 status | plan/task frontmatter status vs POP row vs git reality (merged? released?) vs implementation summary |
| K5 premise↔measurement | a spec whose premise a later measurement (`workflow/measurements/`) or ch-bsd report refuted, still un-revised |
| K6 double ownership / orphan | one requirement owned by two tasks (both would build it), or a rider/fold that names a host that no longer carries it |

Skip pure wording nits. Prefer fewer, load-bearing findings over many weak ones.

## Report shape {#report}

```
## contra-<x>: <cluster>   (files read: N)
### C<x>-1 [K2] <one-line claim>
- side A: <path:line> "<quote>"
- side B: <path:line> "<quote>"
- why it matters: <what would be built wrong / which order breaks>
- proposed resolution: <which side should win and why, or "user decision">
...
### Clean areas
<what you checked and found consistent, one line each>
```

## Clusters {#clusters}

| agent | cluster | primary files |
|---|---|---|
| contra-a | memory organisation (T2) | `workflow/plans/plan-26-*`, `plan-27-*` + task dirs; `docs/adr/0005-memory-dir-layout.md`, `0002`; bug rows 206, 208, 210, 213 in `workflow/bug_registry.md`; `~/.claude/MEMORY-RULES.md`; POP `#override-2026-11-08b`, `#goal-2026-11-09` |
| contra-b | context delivery (T3) | plans 9, 10, 19, 21 (+ tasks incl. 21.5, 21.7), 24.6, 25.1-25.3; `docs/architecture/explorations/handhold-outcome-experiment.md` + `session-phased-context` exploration; `workflow/measurements/*2026-11-13*`; `workflow/open-questions.md` Q1-Q14; `plan-review-2026-10-14` decisions touching them |
| contra-c | write path + maintenance (T4) | plan-23 + tasks, `task-bug185-bulk-gmd-ingest.md`, plan-17, plan-18, plan-4 remnants, plan-22 (22.4 merge writes); bug rows 177, 182, 185, 097, 099, 136, 207; POP `#goal-2026-11-09-scope` |
| contra-d | grep surface + graph integrity (T5, T6) | plan-16 + tasks, 25.4, 25.5, `task-bug216-rule-docs-in-graph.md`, plan-22, plan-20, plan-13, `docs/adr/0004-unified-location-space-index.md`; bug rows 081, 086, 102, 106, 107, 167, 174, 180, 186, 218, 219 |
| contra-e | cross-cutting governance | `workflow/plan-of-plans.md` (every row + override paragraph), `plan-review-2026-10-07.md`, `plan-review-2026-10-14.md`, `handoff.md`, `workflow/deferral_registry.md`, `docs/architecture/todo.md`, every plan's frontmatter `status` vs `git log --merges master`; plan-24 vs everything that "retargets to" or "rides" it; the lead's draft `plan-review-2026-11-13.md` itself (its claims are checkable — check them) |
