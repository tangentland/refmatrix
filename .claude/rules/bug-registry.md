---
description: Bug registry — read before fixing, log after fixing. Native replacement for the buglog.
globs: **/*
---

Bugs are tracked in `workflow/bug_registry.md` (a GMD registry, sibling to the mock and deferral
registries). The threshold to log is LOW — when in doubt, log it.

- BEFORE fixing any bug or error: read `workflow/bug_registry.md` for a known fix. If `rmx` is
  installed, also `rmx memory search "<symptom>"`.
- AFTER fixing any bug, failed test/build/lint, or user-reported problem: append a row to the
  registry with symptom (verbatim error), file(s), root cause, fix, tags, and status.
- If you edit the same file more than twice to get one thing right, that likely signals a bug —
  log it.
- If a bug reappears after a prior fix, bump its `Seen` count and set status `recurring` — it needs
  a durable root fix, not another patch.
