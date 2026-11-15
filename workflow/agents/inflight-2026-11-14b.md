---
gmd: "0.1"
id: agent-briefs-inflight-2026-11-14b
title: "Briefs for the agents in flight at the 2026-11-14 evening save-state (session a9b75923)"
tags: [agent-brief, in-flight, handoff]
metadata:
  node_type: brief
  created: 2026-11-14
---

# Agents in flight at the 2026-11-14 evening save-state {#root}

Condensed from the lead's messages; the rulings cited (L105, L106 in
`workflow/plan-review-2026-11-13.md#lead`) are the authority. If an agent is gone, re-dispatch a
fresh one of the same type from its section, adding "resume from <branch>@<tip>; inspect the
clone's uncommitted work first". Planning authors run with `model: fable` (memory
`feedback_planning_runs_on_fable`).

rel: supersedes -> [[agent-briefs-inflight-2026-11-14]]
rel: depends-on -> [[plan-review-2026-11-13#lead]]
rel: related-to -> [[plan-29-code-quality]]

## green-216 (ch-implementer) — 0.83.1 GREEN {#green-216}

Clone `/Volumes/littlebig/refmatrix-bug241`, branch `task-bug241-rule-docs-gmd-on-reingest`
(base master `78c0c11`, 0.83.0). RED by red-216: bug-241 `a2ac833` (+ logs `8f99332`), bug-240
`36341f5` then r2 `7145c19`. Tip `7145c19` at save time, uncommitted src edits in the tree.

- **bug-241:** `ingest._ingest_path_inner` runs `_ingest_tree` only when the tldr pass returned
  nothing, and `_ingest_tree` is the only code+docs pass that routes `.md` to
  `ingest_gmd_paths`; with a `.tldr` cache no markdown is GMD-parsed. Fix: GMD routing of
  markdown on every code+docs ingest whatever source answered, through the same
  `should_ignore` and `ingest_gmd_paths` (one routing); write the `gmd` stamp; say what an
  explicit `--source` does for markdown. Out of scope: the plain relpath row beside the GMD row.
- **bug-240 (REFUSE):** one shared helper raising "rmx ingest takes a directory; for one file use
  rmx sync -f <file>", called at three entry points: the `rmx_ingest` verb before
  `require_daemon`, `_op_ingest_path_start` at start, and `ingest_path` / `_op_ingest_path`; CLI
  one `Error:` line, MCP isError; directory ingest unchanged.
- Runs: bug-241 + bug-240 files, the bug-216 family + ingest/gmd/reingest/sync/watch files, the
  full suite once (E lines vs `release-0.83.0-full.log`); mutations (the `n == 0` gate for
  markdown; markdown around should_ignore; drop the refusal; refusal without `rmx sync -f`; no
  verb check; no start check). Summary `workflow/implementation_summaries/bug-241-reingest-gmd-pass.md`.
- **Next after GREEN:** ch-bsd → merge → release 0.83.1 → deploy → re-run R4's
  `rmx reingest --force --no-sessions` (backup first) → recount; AC-6 needs `claude` /
  `project-profile` unresolved = 0. Then upgrade `.venv-eval` duckdb to 1.5.3 (L106).

## spec-29a (ch-architect, Fable) — plan-29 specs r2 {#spec-29a}

Clone `/Volumes/littlebig/refmatrix-spec-plan29a`, branch `spec-plan29a`, tip `bdd9cd8` at
save time (uncommitted revision work in the tree). Revise 29.1 / 29.4 / 29.5 per ch-bsd r1
(`workflow/bullshit/2026-11-14-2040-plan29-spec-r1.md`) and L105: B1 (the three phase-0b
functions stay in `cli/__init__.py`; handoff's import is a declared layering exception), B2
(G4 = every name src or tests read still resolves), B3 (new `task-29.6-citation-and-pin-repoint.md`),
S1 (the 29.5 merge as a user-gated store event with counted learned rows), S2, S5-S8, M1-M4,
M8-M12; the S2 extension (sixth criterion: no `_DERIVE_PASS_MODULES` module split in 29.5);
L106 decisions (plan-29 D17 = default; plan-review-fable D3 = (a) as 29.4's stage-4 gate; D4
standing go excludes store-changing releases; 29.5 R5 still needs one re-stamp); bug-096 →
`scheduled` in 29.1; two new items for 29.1 `#homes` (a `legs_ms` task, a cross-partition
`rel:` probe). Expected artifact: commits on `spec-plan29a` + a fold table.

## spec-29b (ch-architect, Fable) — plan-29 specs r2 {#spec-29b}

Clone `/Volumes/littlebig/refmatrix-spec-plan29b`, branch `spec-plan29b`. Round 2 (L105) folded at
`6089b46` (after the save); still to fold: L106's plan-29 D4 = (c) (the normalised-AST derive hash as
a 29.2 requirement — `6089b46` still calls (c) "a separate task") and plan-review-fable-store D5 as
decided. Open with spec-29a: 29.5 excludes `typing_store.py` from its `store_*` rules and accepts the
`TYPE_CHECKING` host base; 29.4 AC-11 admits a keyword-argument bound for `feature-bound` tests. Revise 29.2 / 29.3 per ch-bsd r1 and L105: S3
(embed/pagerank/compile pass modules; AC-18 provably fails), S4 (29.2 AC-7 RED at its start;
29.3(b) AC), M5, M6 (three seams, coordinated with spec-29a), M7 (outcome checks, not
wall-clock), M9; the B1 extension (`#needs-295` rewritten: the three functions do not move);
L106: plan-29 D4 = (c) — a normalised-AST `derive_code_hash` requirement in 29.2 landing before
the annotation/comment edits, with RED and a must-fail mutation. Expected artifact: commits on
`spec-plan29b` + a fold table.

**After both:** ch-bsd plan-29 spec r2 over both tips; then merge both branches to master
(convert cross-branch code-span citations to wikilinks; apply T0's ten amends lines from 29.4
`#fold-deltas`; plan-29 file: the 29.6 step, release points, corrected baseline 4,883 tests,
order 29.3 a/b before 29.2) and set plan-29 `approved`.
