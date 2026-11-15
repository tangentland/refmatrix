---
gmd: "0.1"
id: impl-task-t0-1-skip-gate-memdir
title: "T0.1' GREEN: per-condition skip pins, exact-reason SkipGate, one memory-dir resolver (bug-215, bug-155 residual, bug-254)"
tags: [implementation-summary, t0, task-29.4, skipgate, gmd-lint, bug-215, bug-155, bug-254]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-15
---

# T0.1' GREEN: skip gate and memory-dir resolver {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-1]]
rel: implements -> [[task-t0-suite-trust-sweep#r1-1]]
rel: implements -> [[task-t0-suite-trust-sweep#r1-2]]
rel: implements -> [[task-t0-suite-trust-sweep#r1-4]]
rel: derives-from -> [[task-t0-suite-trust-sweep#amend-1]]

Plan-29 task 29.4, stage 1. Branch `task-t0.1-skip-gate-memdir` in
`/Volumes/littlebig/refmatrix-t01-green`. RED tip `abe09eb` (RED author's commits `0d97bed`,
`abe09eb`). GREEN commit `de4531c`. No test was authored or edited by GREEN. Mutations
M1.1-M1.11 are the lead's and are not recorded here. Rulings: L122, L123, L124.

## What changed {#changes}

- `scripts/gmd_memdir.py` (new, stdlib only, runs under `python3`):
  - `slug(path) -> str` (public per L124);
  - `memdir_for(home, checkout) -> Path`;
  - `canonical_origin(url: str, checkout: Path) -> Path`;
  - `resolve_memdir(root, home) -> tuple[Path | None, str]`;
  - `main(argv: list) -> int`: the chosen dir goes to stdout, and the note goes to stderr as one
    `lint-gmd: …` line.

  A dir counts only if it holds at least one `*.md`. An origin with a scheme or in scp form is
  non-local. Local origins are made absolute, `resolve()`d and stripped of a `.git` component or
  suffix. The walk follows them hop by hop and has a visited-path guard and `BOUND = 5`. A path
  is a checkout only when `git rev-parse --show-toplevel` names that path. `remote get-url` exit
  2 means "no origin". Any other git failure raises, and the script turns that into exit 2.
- `scripts/lint-gmd.sh`: the bash fallback block (lines 42-64 at base) is replaced by one
  `python3 "$RESOLVER" "$ROOT" "$HOME"` call. A missing resolver gives `not found at`, exit 2.
  A resolver failure also gives exit 2. The script has no slug or origin logic left (AC-1.7).
  The `DEVPY` lookup is untouched (bug-253, stage 2).
- `tests/conftest.py`: `allowed_skips(checkout) -> dict` replaces the single `is_dir()` switch.
  The 18 venv pins apply only while `<checkout>/.venv-eval/bin/rmx` is missing. The hooks pin
  applies only when `hooks.installed_root(checkout)` is not None and differs from the resolved
  checkout. Each value is the test's own `reason=` verbatim. `ALLOWED_SKIPS = allowed_skips(_REPO)`.
  The `_CLONE_*` strings are removed.
- `tests/sandbox_site/rmx_sandbox.py`: `SkipGate.reason(why) -> str` strips one `Skipped: `.
  `SkipGate.unexpected()` reports an unknown nodeid. It also reports a pinned nodeid whose reason
  is not EQUAL to its pin, as `… (pinned reason: '<pin>'; actual: '<reason>')`.

## R0: cited sites re-read at base `9a5a98a` {#r0}

| finding | status | where |
|---|---|---|
| single `is_dir()` switch over all pins | holds | `tests/conftest.py:286` |
| `SkipGate` matches by nodeid only | holds | `tests/sandbox_site/rmx_sandbox.py:1160-1161` |
| the 19 pinned reasons ([[task-t0-suite-trust-sweep#t0-1-skip-reasons]]) | holds | pinned verbatim; checked by `test_every_pin_is_its_tests_own_reason_verbatim` |
| bash fallback, `-d` test, one hop | holds | `scripts/lint-gmd.sh:42-64` (spec: 49-64 at `f45b9a3`) |
| test-side copy of the slug/origin logic | changed | `tests/test_gmd_lint_requires_version.py:125-140` at base; the RED commit replaced it with a `resolve_memdir` call |
| R1.3 `project: refmatrix` | closed | `.gmd/config.yml:7` (`988e96d`) |
| bug-254 third slug copy | changed | `tests/test_bug179_anchor_parity.py` `_memdir()`; the RED commit `abe09eb` replaced it (L124) |

{#r0-table}

Verify-set grep (`ALLOWED_SKIPS|SkipGate|lint-gmd|gmd_memdir` under `tests/`) at the branch:
`conftest.py`, `sandbox_site/rmx_sandbox.py`, `test_bug179_anchor_parity.py`,
`test_bug216_rev4.py`, `test_bug216_scope_parity.py`, `test_bug230_repo_scope_gate.py`,
`test_gmd_lint_requires_version.py`, `test_lint_gmd_memdir_fallback.py`,
`test_plan7_10_remedy_r4.py`, `test_sandbox_hardening.py` and `test_t0_skip_gate.py`.
{#r0-grep}

## Acceptance, node by node {#acceptance}

All logs are under `workflow/review-output/t0.1/`. The interpreter is the main tree's
`.venv-eval/bin/python` with `PYTHONPATH=<clone>/src`. Every run is at `de4531c`.

| AC | node(s) | log | result |
|---|---|---|---|
| AC-1.1 | `tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated` (symlinked clone) | `green-ac1.1-hooks-symlinked-clone.log` | **exit 0**. 1 collected, 1 skipped (`hooks belong to another checkout of this commit`). No `SkipGate`/`SKIPPED-UNPINNED` line. Base: exit 1 (`base-ac1.1-hooks-symlinked-clone.log`) |
| AC-1.1 in-session | `test_this_sessions_allowed_set_is_the_builder_on_this_checkout` | `green-verify-set-symlinked-clone.log` | pass |
| AC-1.2 | `test_the_allowed_set_follows_each_skips_own_condition[*]` (9 layouts), `test_the_hooks_pin_is_decided_the_way_the_hooks_test_decides_it` | same | pass (10) |
| R1.2 | `test_every_pin_is_its_tests_own_reason_verbatim` | same | pass |
| AC-1.3 | `test_a_pinned_nodeid_skipping_for_another_reason_fails_the_session`, `test_a_substring_or_near_match_is_not_a_pinned_reason[*]` (3), `test_sandbox_hardening.py` SkipGate test | same | pass (5) |
| AC-1.4 | the seven pinned files, no-venv clone `/Volumes/littlebig/refmatrix-t01-novenv` | `green-ac1.4-seven-pinned-files-novenv-clone.log` | **exit 0**. 47 collected, 28 passed, 19 skipped, all pinned. No `SKIPPED-UNPINNED` |
| AC-1.5 case 1 | `test_gmd_lint_requires_version.py::test_the_repo_scope_is_clean_under_the_stricter_gate` in the clone of a clone `/Volumes/littlebig/refmatrix-t01-cofc` | `green-ac1.5-case1-and-case2-clone-of-clone.log` | **exit 0**, pass. A direct script run with a decoy home (`green-ac1.5-case1-script-clone-of-clone.log`) exits 0 with 0 errors. Its line names both hops: `memory dir for …-t01-cofc absent (…); origin /Volumes/littlebig/refmatrix-t01 absent (…); using origin /Users/tholley/claude_tools/refmatrix (…)`. Base: exit 1, 1,235 `dangling-doc` |
| AC-1.5 case 2 | `test_an_empty_own_slug_memory_dir_falls_back_through_the_real_script` | cofc log above + `green-verify-set-symlinked-clone.log` | pass in both clones. Its own RED is M1.6 (L123), which the lead runs |
| AC-1.5 characterization | the repo-scope test in the symlinked clone (origin = dev tree) | `green-verify-set-symlinked-clone.log` | pass |
| AC-1.6 | the 14 resolver nodes in `tests/test_lint_gmd_memdir_fallback.py`: populated, empty, absent, spellings, 3 non-local, chain, chain-empty, cycle, bound, fifth, no origin, not a checkout | both logs | pass (14) |
| AC-1.7 | `test_the_script_calls_the_resolver_under_python3`, `test_the_script_holds_no_slug_derivation`, `test_the_script_reads_no_origin` | both logs | pass (3) |
| bug-254 | `test_bug254_the_scope_carries_the_memory_dir_the_gate_scans`, `test_bug254_a_scope_with_no_memory_dir_fails_loudly` + AC-5/5b/6 scope tests | `green-verify-set-symlinked-clone.log` | pass |

{#acceptance-table}

## Verify set ([[task-t0-suite-trust-sweep#t0-1-verify]]) {#verify}

Symlinked clone, `green-verify-set-symlinked-clone.log`. The run covers the seven pinned
files, the two new files, `test_gmd_lint_requires_version.py`, the seven `test_sandbox_*.py`
files, and `test_bug179_anchor_parity.py`, `test_bug216_rev4.py`, `test_bug216_scope_parity.py`,
`test_bug230_repo_scope_gate.py` and `test_plan7_10_remedy_r4.py`.

- **pytest exit 1**; collected 267; **265 passed / 1 failed / 1 skipped**. The skip is pinned,
  and the log has no `SkipGate` line. sha `de4531c`.
- The one failure is
  `tests/test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`, with
  E line `_duckdb.IOException: IO Error: Could not set lock on file
  "/private/tmp/bd.<x>/.refmatrix/catalog.A.duckdb": Conflicting lock is held in …/Python (PID
  <n>)`. This is bug-127's E line (T0.2's), the one the RED report predicted for a symlinked
  clone. It is not T0.1's.

No-venv clone (AC-1.4): exit 0, 47 collected, 28 passed / 0 failed / 19 skipped (all pinned).
Clone of a clone (AC-1.5 case 1 + the memdir file): exit 0, 19 collected, 19 passed.
{#verify-body}

**First draft (not committed).** The first verify run of the uncommitted fix,
`green-verify-set-symlinked-clone-pre.log`, gave exit 1 with 9 failed / 257 passed / 1
skipped. Eight failures were in the gate-root tests of bug-179, bug-216 and bug-230, plus one
bug-127. The E line was `RuntimeError: git remote get-url origin failed in /private/tmp/b179…
(exit 128): fatal: not a git repository`, and then `lint-gmd.sh exited 2`. Those roots carry an
empty `.git` marker dir. The draft decided "is a checkout" by `.git` existing, so git's 128
reached the raise. The fix asks git (`rev-parse --show-toplevel` must name the path). A
non-checkout now stops the walk with `not a checkout (git: <git's first line>)` in the note.
{#first-draft}

## For the lead {#for-lead}

- **R1.5 is not done.** The bullet for `workflow/TDD_GOVERNANCE.md` is outside the three paths
  GREEN was given, so it is left to the lead.
- **Summary name.** The spec's `#t0-1-files` names
  `task-t0.1-skip-gate-checkout-identity.md`. This file uses the brief's name.
- **Mutation sites.**
  - M1.1: `allowed_skips` in `tests/conftest.py`.
  - M1.2: `SkipGate.unexpected` (`self.reason(v) != self.allowed[k]`).
  - M1.4: the origin step in `resolve_memdir`.
  - M1.5 (AC-1.6 reads the returned note, so silence it in `resolve_memdir`, not in `main`).
  - M1.6: `_state`.
  - M1.7: `canonical_origin`.
  - M1.8: `scripts/lint-gmd.sh`.
  - M1.9: the `while` loop (stop after the first origin).
  - M1.10: the `nxt in visited` guard.
  - M1.11: `BOUND`.
- **Not run.** The main-tree branch of the case 2 node (non-local origin) was not run: the dev
  tree is not GREEN's to touch. Its unit half (the three non-local cases) passes.

{#for-lead-body}
