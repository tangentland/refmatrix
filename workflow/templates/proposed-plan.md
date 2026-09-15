---
gmd: "0.1"
id: proposed-plan
title: "Proposed Plan Template"
tags: [template, planning]
metadata:
  node_type: template
---

# Proposed Plan: <Topic> {#root}

**Date:** YYYY-MM-DD
**Status:** In Discussion | Accepted | Revised | Abandoned
**Location:** `workflow/plans/<topic>.md` — permanent home; lifecycle stage is the `metadata.status`
frontmatter field (`drafting` → `approved` → `in-progress` → `completed`); the file never moves

## Context {#context}
<Why this plan is needed>

## Proposed Approach {#proposed-approach}
<The plan itself>

## Open Questions {#open-questions}

### Q1: <Question title> {#q1}
**Status:** OPEN | RESOLVED
**Options:**
- A: <option> — <trade-offs>
- B: <option> — <trade-offs>

**Decision:** <filled in when resolved>
**Rationale:** <filled in when resolved>

#### Discussion {#q1-discussion}
<Notes from user exploration, added incrementally>

### Q2: ... {#q2}

## Decisions Log {#decisions-log}
| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | ... | ... | ... |

## Task Breakdown {#task-breakdown}
<After all questions resolved, list tasks that will become individual task specs>

| Task ID | Title | Depends On |
|---------|-------|------------|
| 1.1 | ... | — |
| 1.2 | ... | 1.1 |
