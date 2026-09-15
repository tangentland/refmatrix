---
gmd: "0.1"
id: task-spec
title: "Task Spec Template"
tags: [template, planning]
metadata:
  node_type: template
---

# Task N.M: <Title> {#root}

> Plan: [<Plan Name>](../plans/<plan-name>.md)
> Status: Pending | In Progress | Complete
> Depends on: Task N.X, Task N.Y

## Requirements {#requirements}

<What this task must accomplish — acceptance criteria>

## Architecture References {#architecture-references}

| Topic | Source |
|-------|--------|
| <relevant topic> | <ADR or architecture doc> |

## Files to Create {#files-to-create}

| File | Purpose |
|------|---------|
| `src/{project_package}/module/file.py` | <description> |

## Files to Modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/{project_package}/existing.py` | <what changes> |

## Key Decisions (from plan discussion) {#key-decisions}

- <Decision that affects this task, with reference to proposed plan Q#>

## Implementation Notes {#implementation-notes}

<Any technical guidance, patterns to follow, gotchas>

## Test Strategy {#test-strategy}

- <What to test, what to mock, edge cases>
