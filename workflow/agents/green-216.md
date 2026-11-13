---
gmd: "0.1"
id: agent-brief-green-216
title: "Brief: green-216 — bug-216 GREEN (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-216 — bug-216 GREEN (ch-implementer) {#root}

Dispatched 2026-11-13 (session f0521bff) as `ch-implementer`. Make the bug-216 RED tests pass with
concrete `src/` code; write no tests.

- **Clone:** `/Volumes/littlebig/refmatrix-bug216`, branch `task-bug216-rule-docs-in-graph`, tip at
  dispatch `f1aa796` (RED `a08d80b`, `4c28cbb`, `4b3a4e4`; red-216's merge `280afc4`). First merge
  dev master (docs only). Do NOT use red-216's scratch reference implementation.
- **Read:** `workflow/plans/task-bug216-rule-docs-in-graph.md` (R1-R12, revisions 2-4,
  `#rev-3-contracts`; AC-1..AC-13; AC-6 is the lead's live check), the implementation summary
  `#red`, bug-216/218/219 rows, CLAUDE.md, the project profile, TDD governance, and
  `workflow/agents/green-251.md#hard-rules`.
- **Build:** R1 `!path` re-include (never over INGEST_IGNORE_DIRS); R2 one `should_ignore`; R3 scope
  parity in `check-gmd-parity.py`; R5/R8 `check-rel-landing.py` (live-edge join, stale, binding
  classes); R6 bare doc ids bind doc → memory → concept; R7 `denotes` (OPS `denotes_link`, ingest
  maintenance, purge; same_as variants; not same_as); R9 walkers treat `denotes` as transparent; R10
  pending refs re-resolve on ingest; R11 built-in include of GMD CLAUDE.md and the profile; R12 one
  ignore list; `ingest-gmd <subdir>` walks up to `.refmatrix/`; INTEGRATION.md; a migration path for
  existing stores.
- **Verify:** all bug-216 files + workflow_ignore + bug179; family; full suite by E line vs
  `release-0.82.0-full.log`; `lint-gmd.sh` exit 0; mutations R6, R7, R9, R10, R11. Tee to
  `workflow/review-output/bug216/`. Commits: src, docs, `#green`. Text report.
