---
gmd: "0.1"
id: plan-29-code-quality
title: "Plan 29: code quality — triage the backlog, gate the types, converge repeated shapes, heal the suite, split the giant modules"
tags: [plan, code-quality, refactor, typing, tests, registry, cli]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-11-14
  updated: 2026-11-14
---

# Plan 29: code quality {#root}

**Date:** 2026-11-14. **Status:** approved (2026-11-14): six task specs under
`workflow/plans/plan-29-code-quality-tasks/`, authored by ch-architect on Fable 5.2 and reviewed
by ch-bsd in four rounds to MEH-only GO ([[bsd-plan29-spec-r4]]; rulings L105-L111 in
[[plan-review-2026-11-13#lead]]).
**Origin:** the user asked for the lead's code-quality assessment of 2026-11-14 to be written as a
plan. That assessment drew on the 0.83.0 review rounds (bug-212, bug-216/227, bug-225, bug-230,
25.1), a reading of `query.py` prompted by an external model's review (bug-234..bug-238), and the
measurements in [[#baseline]].
**Sequencing:** after the 0.83.0 deploy and the seven frozen spec-branch merges. The user placed it
first, before queue item 2 ([[#decisions]] D2).

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[bug_registry#registry]]
rel: related-to -> [[feedback_converge_repeated_shapes]]
rel: related-to -> [[feedback_measure_the_outcome_not_the_wall]]
rel: related-to -> [[feedback_review_clones_cannot_see_dev_tree_failures]]
rel: catalogs -> [[task-29.1-registry-triage]]
rel: catalogs -> [[task-29.2-mypy-gate]]
rel: catalogs -> [[task-29.3-converge-shapes]]
rel: catalogs -> [[task-29.4-suite-health]]
rel: catalogs -> [[task-29.5-split-giant-modules]]
rel: catalogs -> [[task-29.6-citation-and-pin-repoint]]
rel: evidence-for -> [[bsd-plan29-spec-r4]]

## Why {#why}

The process is strong: incident-named docstrings, a 237-row bug registry, RED-first tests proven
by mutation, ch-bsd review until GO, more test code than source. The code has outgrown its shape:

- **Giant modules.** Every 0.83.0 merge conflicted in `cli.py`, `verbs.py` or `mcp.py`; size hides
  sibling call sites and makes each review round expensive.
- **The same defect class returns.** Each 0.83.0 fix took 3-7 review rounds, and the findings
  repeated shapes: one site fixed and its siblings missed (busy vs absent; a git failure read as
  "not found"), one check shared by callers with different needs (bug-232), a silent empty result
  (bug-234). That is a missing common function, not care.
- **Rigor is uneven.** The watched paths are solid; `query.py`'s PQL has no argument types
  (`Count(foo)` → 3, bug-238) and returns empty for unknown terms without a word (bug-234).
- **Types are unchecked.** No mypy/ruff gate is wired; `cast()` hides real types
  (`run_pql` → bug-235's crash; `_DaemonWriter` passed as a `Store`).
- **The suite is slow and leaky.** About 50 minutes; wall-clock bounds fail under load (bug-228,
  bug-231); a test daemon outlived its test by 20 h (bug-229); hand-picked families miss what only
  the full suite or the dev tree shows (bug-230).
{#why-list}

## Baseline (measured 2026-11-14 at `0db6314`) {#baseline}

| Measure | Value |
|---|---|
| `cli.py` / `store.py` / `daemon.py` / `verbs.py` lines | 15,212 / 9,246 / 7,355 / 3,653 |
| `src/refmatrix/*.py` total lines | 75,255 |
| test lines / test files / tests | 96,762 / 357 / ~4,480 |
| full suite wall time | ~47-57 min (load-dependent) |
| `except Exception` sites in `src/refmatrix/` | 388 |
| bug-registry rows / not fixed | 237 / 80 |
| type or lint gate | none |

Every task re-measures its own rows before and after. {#baseline-rule}

## Tasks {#tasks}

Task specs: [[task-29.1-registry-triage]], [[task-29.2-mypy-gate]], [[task-29.3-converge-shapes]], [[task-29.4-suite-health]], [[task-29.5-split-giant-modules]], [[task-29.6-citation-and-pin-repoint]]. Each spec is authoritative over the summary below. {#task-specs}

### 29.1 Triage the open registry {#t1}

Each of the 80 not-fixed rows ends in exactly one of: scheduled (names the task or plan that fixes
it), deferred (reason + a review date), or closed (evidence it no longer reproduces, or that it
was fixed elsewhere: the fixing sha). Docs-only; runs any time.
**Acceptance:** no row left in a bare `open`; a triage table in the task's summary with counts per
outcome; every `scheduled` names a real task. {#t1-acceptance}

### 29.2 A type-check gate on the public surfaces {#t2}

Add a type checker (mypy or pyright, [[#decisions]] D1) as a commit gate beside
`./scripts/lint-gmd.sh`, strict on the public API of `verbs`, `query`, `store`, `handoff`, `mcp`;
everything else on a recorded baseline that may only shrink. Replace the `cast()`s that hide a real
type: `QueryEngine.run_pql` returns a typed result (fixes bug-235), `_DaemonWriter` and `Store` meet
one `Protocol`.
**Acceptance:** the gate FAILS on a must-fail fixture ([[feedback_clean_corpus_hides_a_dead_gate]]);
zero errors in the strict modules; the baseline file's error count recorded and only falling;
bug-235 closed. {#t2-acceptance}

### 29.3 Converge the repeated shapes {#t3}

From the ch-bsd ledger, list the finding classes seen more than twice; give each ONE helper and a
census test that fails on a synthetic bypass, as the catalog-opener census does. First three:

- **git runner:** one `run_git(repo, *args, timeout)` returning `(rc, out, err)` with the
  "not found = exit 1, empty stderr" rule (bug-225 r3), used by `handoff`, `sync`, `hooks` and the
  STM milestone capture (bug-233).
- **query term resolution:** unresolved concepts and unknown linkages are collected and surfaced
  (bug-234); PQL arguments are typed (bug-236, bug-238).
- **broad excepts:** classify the 388 `except Exception` sites as re-raised, counted-and-surfaced,
  or justified-in-a-comment; a census test fails on a new bare `except Exception:` whose body
  neither re-raises nor counts/logs.

**Acceptance:** each helper's census test fails on its synthetic bypass and passes on the tree;
the listed bugs closed; the except census's three counts recorded. {#t3-acceptance}

### 29.4 Heal the test suite {#t4}

- Replace wall-clock bounds with outcome checks (the stop op answered and the pid exited; the row
  was written), starting with bug-228 and bug-231; a grep census forbids new `< N.0` wall-clock
  asserts outside a named allow list.
- A session-scoped reaper in `tests/conftest.py` stops every daemon a test spawned and FAILS the
  session naming each one it had to kill (bug-229).
- Test families for a change are derived from imports of the touched modules, not hand-picked
  (bug-230's lesson), and the merged dev tree runs them before any merge commit.
- Measure, then shard the full suite (the old `scripts/ptest.sh` four-shard runner is the
  starting point); target at most 20 minutes wall time at normal load.

**Acceptance:** the reaper's must-fail fixture; bug-228/229/231 closed; the wall-clock census
green; full-suite wall time measured before and after, with the same failures by E line.
{#t4-acceptance}

### 29.5 Split the giant modules {#t5}

`cli.py` becomes a package (`refmatrix/cli/`), one module per command group (memory, daemon, hub,
query, ingest, hooks, session, focus, …); `refmatrix.cli:cli_entry` and the click tree stay
byte-identical. Mechanical moves only, one command group per commit, no behaviour change. Then
`store.py` by concern (fragments/bitmaps, vectors, catalog and slots, memory), behind the existing
census tests. `daemon.py` is assessed after, not split by default.
**Acceptance:** the generated CLI tree, verb parity, the census tests and the full suite are equal
by E line before and after each commit; no `src/refmatrix` module over the size target
([[#decisions]] D3); private cross-module calls listed and each either made public or removed.
**Constraint:** runs alone, in a window where no feature branch touches `cli.py` or `store.py`,
announced first, so the move does not set off a merge-conflict storm. {#t5-acceptance}

### 29.6 Re-point the specs {#t6}

Added at spec review r1 (B3, L105). After 29.2 and 29.3, every `cli.py` / `store.py` line citation in
an unbuilt spec becomes a symbol (resolved at the oldest commit that added the token), with
`daemon.py` / `verbs.py` / `mcp.py` citations converted too (plan-29 D25), and a census forbids dead
file citations from then on (plan-29 D26). Spec: [[task-29.6-citation-and-pin-repoint]].
**Acceptance:** as the spec states; the census is green at its merge. {#t6-acceptance}

## Order {#order}

**29.4's runner first** (the user, 2026-11-15, Q29 = a: its stages 0-5 — R0, T0.1', the
reaper and sandbox roots, the flaky fixes, tiers and the sharded runner — move ahead of 29.1;
29.4f / R6 still waits for 29.5) → 29.1 (docs only, informs the rest) → 29.5
(the split, alone, while nothing else is in flight) → 29.2 ∥ 29.3 (types and helpers land in the
final modules) → 29.6 (citations and pins). 29.2 R7's release is one announced window: deploy A
(R7 + R8, then `rmx derive rehash --apply`), deploy B (every real pass-file edit, then a forced
re-derive of exactly the affected passes); `consolidate.py` is not edited by plan-29 (plan-29 D27,
L109, L110). Each task runs RED → GREEN → ch-bsd as usual ([[#decisions]] D2). {#order-list}

## Non-goals {#non-goals}

No behaviour change in 29.5; no formatter gate; no rewrite of a working subsystem; no new feature
rides on these tasks. {#non-goals-list}

## Decisions (user, 2026-11-14) {#decisions}

1. **D1 = Q20: mypy** ("d1-mypy"). Per-module strictness and a shrinking baseline file.
2. **D2 = Q19: all of it first** ("q19 - first"): right after the 0.83.0 deploy and the
   spec-branch merges, before queue item 2 of [[plan-review-2026-11-13#queue]], in the order
   29.1 → 29.4 → 29.5 → 29.2 ∥ 29.3, so the split's equal-by-E-line runs use the healed suite and
   the new helpers and annotations land in their final modules. The user's reason: waiting makes
   the follow-on work slower.
3. **D3 = Q21: about 3,000 lines** per `src/refmatrix` module after 29.5 ("d3 - agree").
{#decisions-list}

4. **plan-29 D4 = (c)** (The user, 2026-11-14: "go with your recommendations on all of them".): `store.derive_code_hash` ignores comments, docstrings and annotations (a normalised AST of each pass module), landed in 29.2 BEFORE its annotation and 29.3's comment edits, so neither flips the fleet to `behind_code`. Superseded in part: 29.5's module-list change flips no stamp (L108, ch-bsd r2's correction), so it carries no re-stamp unless R0 finds a stamp under an unmapped pass name.
5. **plan-29 D17 = the default** (same quote): assess daemon.py, verbs.py, ingest.py by fixed criteria (incl. the sixth: no `_DERIVE_PASS_MODULES` module is split in 29.5), split those that pass, dated exceptions with owner tasks for the rest.

6. **Decisions taken in the specs** (registered at the merge, L105 M11 / L107 item 9), each with its text in the owning
   spec: plan-29 D7, D8, D9 ([[task-29.1-registry-triage#decisions]]); D10-D15, D20
   ([[task-29.4-suite-health#decisions]]); D16, D18, D19, D21, D22 ([[task-29.5-split-giant-modules#decisions]]);
   D24, one copy of the CLI under `python -m` (lead, L107); D25, D26 ([[task-29.6-citation-and-pin-repoint#decisions]]).
7. **plan-29 D27 = (a)** (lead, L109): R7's release re-derives the passes a real pass-file edit
   leaves behind, in deploy B under its own go ([[task-29.2-mypy-gate#d27]]); `consolidate.py`'s rows
   and its one silent handler are held ([[task-29.3-converge-shapes#c-pass-rows-held]], L110).
8. **plan-29 D23 decided (user, 2026-11-14): (a) accept the loss, recorded** (L115, which replaced
   L113's (b) after the count: 3 attached learned rows + 1 protected entity on `cli.py` / `store.py`;
   15,965 already orphaned by bug-107, [[measurement-learned-rows-cli-store-2026-11-14]]). 29.5 exports
   them in full before the merge and records the loss. No task 29.7. **plan-29 D19 confirmed by the
   user** (L113): `store` stays a module ([[task-29.5-split-giant-modules#decisions]]).

Recorded as L104-L111 in [[plan-review-2026-11-13#lead]]. Next: 29.4 stage 2. {#decisions-next}
