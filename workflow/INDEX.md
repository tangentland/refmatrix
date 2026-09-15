---
gmd: "0.1"
id: WORKFLOW_INDEX
title: "Workflow Index"
tags: [reference]
metadata:
  node_type: index
---

# Workflow Index {#root}

Map of the `workflow/` process tree. `docs/` holds knowledge (architecture, guides,
reference); `workflow/` holds process (plans, governance, templates, audits, summaries).

## Planning {#planning}

| Path | Purpose |
|------|---------|
| `plan-of-plans.md` | Plan index + sequenced execution order (Status column) — source of truth |
| `plans/` | All plans, permanently + `<plan>-tasks/` spec dirs; stage = `metadata.status` (`drafting` → `approved` → `in-progress` → `completed`) |
| `specs/` | Per-feature SDD artifact chain (`NNN-slug/{spec,plan,tasks}`) — see `specs/README.md` |
| `constitution.md` | Governing principles; the SDD gate `/ch-plan` re-checks |
| `PLANNING_WORKFLOW.md` | How to plan, explore, and gate approval |
| `PLAN_GOVERNANCE.md` | Lifecycle, staleness, question-forcing |
| `TDD_GOVERNANCE.md` | RED-first, mutation-gated test contract |

## Reference {#reference}

| Path | Purpose |
|------|---------|
| `QUICK_REFERENCE.md` | Fast pattern/command lookup |
| `PATTERNS.md` | Copy-paste code patterns |
| `TECH_STACK_DECISIONS.md` | Approved libraries + rationale |
| `development_resources.md` | Available infrastructure inventory |
| `test_mock_registry.md` | Mock governance registry |
| `deferral_registry.md` | Deferred production functionality registry |
| `bug_registry.md` | Known bugs, root causes, and fixes |
| `templates/` | Document templates (task-spec, proposed-plan, exploration, handoff) |

## Audit & Output {#audit-output}

| Path | Purpose |
|------|---------|
| `bullshit/` | @ch-bsd runtime-integration audit memory (INDEX, IMPRESSIONS, findings) |
| `implementation_summaries/` | Per-task implementation summaries |
| `session-summaries/` | Per-session summaries |
| `review-output/` | Agent review reports (gitignored — runtime) |
| `functional-tests/` | Functional/E2E test inventory |
| `validation/` | Validation artifacts |
| `change_sets/` | Grouped change records |
| `past_handoffs/` | Archived session handoffs |
