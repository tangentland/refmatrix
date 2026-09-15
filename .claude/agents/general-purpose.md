---
gmd: "0.1"
id: general-purpose
title: "general-purpose — Project-level general-purpose agent"
tags: [agent, cat-herder]
metadata:
  node_type: agent
name: "general-purpose"
description: "General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks. When you are searching for a keyword or file and are not confident you will find the right match in the first few tries, use this agent to perform the search for you."
tools: ["*"]
model: inherit
enabled: true
---

Project-level `general-purpose` agent. Behavior matches the harness default (full toolset,
multi-step task execution, search / research / implementation work) plus the project conventions
below.

## When invoked for implementation work {#root}

- Tests run **in the Docker dev container only** — never on the host. Use the container venv
  Python path, e.g. `.venv-eval/bin/python -m pytest <targets>`.
- **No mocks, stubs, or placeholder logic in `src/`** — production code is fully concrete or it
  does not exist yet. Mocks belong only in `tests/` (see `workflow/test_mock_registry.md`).
- **No silent errors** — every `except` either logs and re-raises or surfaces a structured error.
- **Reviews persist to disk** — if the task is a review (architect, test-engineer, code-reviewer,
  gap-master, etc.), write the full report to `workflow/review-output/<plan>-<phase>-<reviewer>.md`
  BEFORE returning a chat summary. Chat is a pointer + headline counts only.

## When invoked for research / exploration {#research-exploration}

- Use existing indexes first, in this order (the discovery ladder): `rmx context <symbol>` →
  `tldr` call-graph → `rmx grep`. Fall back to raw `grep`/`Glob` only when those miss. Also
  consult `docs/architecture/ARCHITECTURE_INDEX.md` and
  `workflow/plan-of-plans.md`.
- Read large files with `offset`/`limit` — never load 2000+ lines when 200 will do.
- Don't duplicate what a parallel agent is doing — if another agent is mutating a file, work
  elsewhere.

## Orientation docs {#orientation-docs}

Read only what's relevant to the task; do not load all of these unconditionally.

- `CLAUDE.md` (root) — operating instructions, hard rules, work process
- `docs/architecture/ARCHITECTURE_INDEX.md` — architecture navigation
- `rmx context <symbol>` / `rmx grep` — code navigation
- `workflow/QUICK_REFERENCE.md` — fast pattern + command lookup
- `docs/gmd/SPEC.md` — Graph Markdown spec (this project authors docs as GMD)
