---
gmd: "0.1"
id: PLANNING_WORKFLOW
title: "Planning & Exploration Workflow"
tags: [planning, workflow]
metadata:
  node_type: doc
---

# Planning & Exploration Workflow {#root}

This document contains the full planning workflow, exploration workflow, and plan approval
gate. Referenced from CLAUDE.md.

## Write Decisions Immediately (CRITICAL) {#write-decisions-immediately}

**Architectural discussions and decisions MUST be written to files as they happen — not
deferred to task completion or session end.** Context compaction can erase unwritten
discussion at any time.

**Rules:**
- When an architectural decision is reached in conversation, **immediately** write it to the
  relevant architecture doc, ADR draft, or `docs/architecture/explorations/` file
- When discussing trade-offs between approaches, write a brief summary to a file **before**
  continuing to the next topic
- Do NOT accumulate decisions in conversation context expecting to write them later

**What to capture immediately:**
- Technology choices (write to `docs/architecture/todo.md` or create ADR draft)
- Design decisions (write to relevant architecture doc)
- Rejected alternatives and why (write to ADR or exploration doc)
- User preferences and directives (write to `handoff.md` User Preferences section)

**Pattern:** Discussion → Decision → Write to file → Continue discussion

## Status-Tracked Plan Lifecycle {#status-tracked-plan-lifecycle}

All plans live permanently in `workflow/plans/`. A plan never moves between directories — its
stage is recorded ONLY by the `metadata.status` field in its GMD frontmatter:

| Status | Location | Meaning |
|--------|----------|---------|
| **`drafting`** | `workflow/plans/<plan-name>.md` | Design in progress, no task specs yet |
| **`approved`** | `workflow/plans/<plan-name>.md` + `workflow/plans/<plan>-tasks/` | Task specs written, ready to implement |
| **`in-progress`** | `workflow/plans/<plan-name>.md` | Implementation underway |
| **`completed`** | `workflow/plans/<plan-name>.md` | Implementation done and verified (file stays put) |

**Meta index:** `workflow/plan-of-plans.md` is the single index + sequenced execution order (with
a Status column) — the source of truth for what comes next.

## Exploration Workflow {#exploration-workflow}

Explorations are **research documents** that investigate a design space before decisions are
made. They precede proposals in the pipeline:

```
Exploration (research) → Proposed Plan (decisions) → ADR (if architectural) → Task Specs (implementation)
```

Not every change needs an exploration — straightforward tasks go directly to proposed plans
or implementation. Use an exploration when:

- The design space is unclear or has multiple valid approaches
- Research is needed before options can be evaluated
- The topic is large enough to warrant structured analysis before deciding
- The user explicitly asks to explore a topic

### Creating an Exploration {#creating-an-exploration}

1. **Create the file** at `docs/architecture/explorations/<topic>.md`
2. **Write findings incrementally** as research proceeds — same compaction-safety rules apply

### Exploration Lifecycle {#exploration-lifecycle}

| Status | Meaning |
|--------|---------|
| `In Progress` | Research ongoing, findings being written |
| `Research Complete` | Analysis done, not yet transitioned to proposal |
| `Transitioned to Proposal` | Transition Summary written, proposed plan created |
| `Promoted to ADR-NNNN` | Decisions made, captured in an ADR |

Explorations are **never deleted** — they serve as the research record for why decisions
were made.

### Transitioning from Exploration to Proposal {#transitioning-from-exploration-to-proposal}

When research is sufficient to frame decisions, create an explicit **Transition Summary**
in the exploration document before creating the proposed plan.

**Steps:**

1. Write the Transition Summary in the exploration file (What Survived, What Was Eliminated,
   Key Constraints, Open Questions, What Is NOT Moving Forward)
2. Update the exploration status to `Transitioned to Proposal`
3. Create the proposed plan at `workflow/plans/<topic>.md` with `status: drafting`
4. Update `workflow/plan-of-plans.md` with the exploration → proposal link
5. Follow the Planning Mode Workflow below

## Planning Mode Workflow (CRITICAL) {#planning-mode-workflow}

**All proposed plans MUST be written to disk BEFORE presenting questions to the user.**

### Before Asking Questions {#before-asking-questions}

1. **Write the proposed plan to disk** at `workflow/plans/<topic>.md` with `status: drafting`
   - Include: context, options considered, proposed approach, open questions
   - Each open question gets its own numbered section with options
   - Mark all questions as `**Status: OPEN**`

2. **Append a reference** to `handoff.md`:
   ```
   **Active Proposed Plan:** [<topic>](workflow/plans/<topic>.md) — <n> open questions
   ```

3. **Then** present the plan and questions to the user

### When the User Answers a Question {#when-the-user-answers-a-question}

After **each individual answer** from the user:

1. **Update the proposed plan file** — change question status from OPEN to RESOLVED,
   record the decision and rationale
2. **Continue** to the next question or topic

**Pattern:** Ask question → User answers → Write answer to plan file → Continue

### When the User Explores a Tangent {#when-the-user-explores-a-tangent}

1. **Write exploration notes** to the proposed plan file (add a `### Discussion` subsection)
2. **Do NOT wait** for the tangent to resolve before writing — write incrementally

### When All Questions Are Resolved {#when-all-questions-are-resolved}

1. Update the plan file's discussion status to `Accepted` (or `Revised` if approach changed)
2. Update `handoff.md` reference from "Active" to "Completed"
3. Update `workflow/plan-of-plans.md` with the plan's status
4. **Immediately create ALL task spec files** in `workflow/plans/<plan>-tasks/` (see Plan
   Approval Gate below)
5. Set the plan's frontmatter `status: approved` (the file stays at `workflow/plans/<plan-name>.md`)
6. Then proceed to implementation

## Plan Approval Gate (CRITICAL) {#plan-approval-gate}

**After a plan is approved, ALL task spec files MUST be created BEFORE any implementation
begins.**

### Workflow: Plan Approved → Tasks Created → Implementation {#workflow-plan-approved-tasks-created-implementation}

1. **Create ALL task spec files** for the plan immediately after approval:
   - Location: `workflow/plans/<plan>-tasks/task-N.M-description.md`
   - Use the task spec template (see `workflow/templates/task-spec.md`)
   - Reference specific decisions from the proposed plan discussion
   - Capture dependencies between tasks

2. **Promote the plan** by editing its frontmatter `status: drafting` → `status: approved`
   (the file stays at `workflow/plans/<plan-name>.md` — it does NOT move):
   - Plan file: `workflow/plans/<plan-name>.md`
   - Task specs: `workflow/plans/<plan>-tasks/`
   - Verify task count matches

3. **Update tracking files**:
   - `workflow/plan-of-plans.md` — set the plan's Status to `approved`
   - `handoff.md` — note that task specs are ready for implementation

4. **Gate**: Do NOT start implementing Task N.1 until all task specs exist on disk

### Why This Matters {#why-this-matters}

Task specs serve as **self-contained implementation briefs**. When a new session starts
Task N.3, the task spec file contains everything needed — requirements, architecture
references, decisions, files to touch — without needing to reconstruct planning context.

## Templates {#templates}

All templates are in `workflow/templates/`:

| Template | Purpose |
|----------|---------|
| [task-spec.md](templates/task-spec.md) | Individual task specification |
| [proposed-plan.md](templates/proposed-plan.md) | Proposed plan with open questions |
| [exploration.md](templates/exploration.md) | Design space research document |
| [handoff-session.md](templates/handoff-session.md) | Session handoff format |
