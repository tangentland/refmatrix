---
name: ch-review
description: Four-phase multi-agent review of the current change — code quality, architecture, tests, and gap/doc enforcement
argument-hint: [optional path or task name to scope the review]
allowed-tools: [Task, Read, Grep, Glob, Bash]
model: inherit
enabled: true
---

# Four-Phase Agent Review

Comprehensive review of the current change set, run as four phases. Dispatch the specialist
agents as background subagents (fire-and-continue); each writes its full report to
`workflow/review-output/<task>-<phase>-<reviewer>.md` and returns a pointer + headline counts.

Scope: the argument if given, else the current branch diff vs `main`
(`git diff --stat main...HEAD`).

## Phase 1 — Code & Architecture {#phase-1}

Dispatch in parallel:
- `ch-code-reviewer` — correctness, error handling, types, readability, security basics.
- `ch-architect` — does the implementation match the project's architecture docs, ADRs, and
  design principles? (post-implementation mode)

## Phase 2 — Tests {#phase-2}

- `ch-test-engineer` — coverage adequacy, mock governance, real-auth tests for new protected
  endpoints, contract tests for new UI-facing shapes.

## Phase 3 — Gaps & Concreteness {#phase-3}

- `ch-gap-master` — no mocks/stubs/workarounds in `src/`; `docs/architecture/todo.md` and
  `workflow/plan-of-plans.md` current; mock registry updated.

## Phase 4 — Documentation {#phase-4}

- `ch-doc-writer` — indexes accurate (`docs/architecture/ARCHITECTURE_INDEX.md`),
  `handoff.md` updated, docs suite current.

## Triage {#triage}

Collect all reports. Resolve by severity:
- **Critical / High** — address before proceeding.
- **Medium** — address, or document rationale.
- Log agent-surfaced issues to `docs/problem_log.md`.

Report a consolidated summary: per-phase counts, the report file paths, and the list of
Critical/High items that block completion.
