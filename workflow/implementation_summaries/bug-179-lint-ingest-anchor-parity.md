---
gmd: "0.1"
id: impl-bug-179-lint-ingest-anchor-parity
title: "bug-179: lint and the store ingester agree on block anchors, and the gate checks it"
tags: [implementation, bugfix, gmd, lint, ingest, anchors, bug-179]
metadata:
  node_type: implementation-summary
  date: 2026-11-09
---

# bug-179: lint and the store ingester agree on block anchors {#root}

rel: implements -> [[task-bug179-lint-ingest-anchor-parity]]
rel: implements -> [[bug_registry#registry]]

This is the GREEN step for the approved spec. The RED tests were committed first: upstream gmd
`e20ece0` (`scripts/test-lint-gates.py`, 15 of 33 failing) and refmatrix `4c32a7c`
(`tests/test_bug179_anchor_parity.py`, 28 failing). The work was done in isolated clones under
`/Volumes/littlebig` (`gmd-bug179`, `refmatrix-bug179`, branch `fix-bug179-anchor-parity`).
The orchestrator lands the commits in order: viascope split, then upstream, then re-vendor.
{#context}

## Commits {#commits}

- **Upstream gmd** `efb514afac0fe16229ba9a90a1354af6e6fb93b6`. It changes `lint.py`, `slice.py`,
  `audit.py`, `SPEC.md` and `gmd-migration-guide.md`. `scripts/test-lint-gates.py` reports
  33 cases pass. {#c-upstream}
- **refmatrix fix** `44c6196`. It re-vendors `tools/gmd/lint.py` and `tools/gmd/slice.py`
  byte-identical from that upstream sha with `git show <sha>:lint.py` and `:slice.py`. Upstream
  `git status --short` was empty at re-vendor time. {#c-refmatrix}
- **viascope split** (R7 b): **viascope `0b443ef69`** (2026-11-09, user consent; committed by
  pathspec on viascope's current branch `task-adr-0111-slice2-config-fold`, its other dirty files
  untouched). The six ids keep their names: the first stays on the bullet, five become sub-items.
  Then upstream `~/claude_tools/gmd` was fast-forwarded to `efb514a` (33 gate cases pass). Order
  held: viascope first, then upstream. {#c-viascope}

## What changed {#changes}

- **R1** lint: more than one `{#id}` on a body or heading line is `[multi-anchor]`, and only the
  first id registers. That matches the ingester. {#ch-r1}
- **R2** lint: a `{#id}` on any `rel:`-prefixed line is `[anchor-on-rel]` and never registers.
  The ingester uses the same trigger. A `rel:` line that `_REL_RE` rejects no longer reaches the
  body-anchor scan. Its wikilinks are still harvested as before. {#ch-r2}
- **R3** ingester and `slice.py`: the heading anchor is read from the inline-code-stripped line,
  starting at the heading-prefix offset. The title cuts out only that span, so a quoted anchor
  stays in the title. {#ch-r3}
- **R3b** lint, `slice.py` and the ingester: inline code is matched as CommonMark backtick runs.
  Masking keeps the line length. {#ch-r3b}
- **fu-audit**: upstream `audit.py` now records only the first anchor per line and none on
  `rel:` lines, so there is no third parser that disagrees. {#ch-audit}
- **R4**: `not-evidence` (plan-14) and `drain-first` (task-14.4) moved off their `rel:` lines to
  the end of the paragraph above. {#ch-r4}
- **R5**: added `scripts/check-gmd-parity.py`, with `find_divergences(paths, memory_dirs=())`,
  `scan` and `main`. Memory dirs are parsed the way the bridge parses them (lenient, memory ids).
  A parse failure is reported and never skipped. `scripts/lint-gmd.sh` no longer `exec`s lint:
  it runs lint and then parity over the same scope, always runs both, and exits non-zero if
  either fails. A missing `.venv-eval/bin/python` exits 2 and names it. {#ch-r5}
- **SPEC**: the two rule lines are in upstream `SPEC.md` and in `docs/gmd/SPEC.md`. The two files
  still differ only in the `id:` line. {#ch-spec}
- **R7 c**: the upstream migration guide section `one-id-per-line` and the upstream commit
  message name the six cliquedb and cliquet lines, with the fix for each shape. {#ch-r7c}

## Verification {#verification}

All logs are under `workflow/review-output/bug179/` in the clone. {#v-logs}

- `green-1.log`: the bug-179 test file plus `test_gmd_body_anchors.py` give 49 passed.
  {#v-green}
- `families-green.log` and `families-post-mutation.log`: `tests/test_gmd*.py`,
  `tests/test_ingest_gmd*.py` and the bug-179 file give 66 passed. `adjacent.log`: memory bridge,
  sync routing, deferrals, brief GMD and coref give 54 passed. The full suite was not run (out of
  scope for this step). {#v-families}
- The real gate scope plus the real memory dir `-Users-tholley-claude-tools-refmatrix/memory`
  (`parity-real.log`) give 0 divergent docs and 0 parse failures. Lint over the same scope has the
  same 43 error texts as the `9901589` base linter, with no new text (AC-6). {#v-corpus}
- AC-7 mutations: each mutation was applied after the fix was committed, each was killed, and
  each was restored with its own `git checkout`. `__pycache__` was cleared afterwards and the
  families re-run green. The (a) to (f) runs log to `mut-<name>.log`. {#v-mutations}
  - (a) lint `len > 1` check disabled: AC-1 (5 tests) and AC-4 fail. {#v-m-a}
  - (b) lint re-registers rel-line ids: AC-2 (both) and AC-5 synthetic fail. {#v-m-b}
  - (c) ingester heading search on the raw line: AC-3 and AC-3b heading parity fail. {#v-m-c}
  - (c2) ingester title via `_ID_RE.sub`: the AC-3 title test fails. {#v-m-c2}
  - (d) plan-14 line restored: both AC-5b tests and AC-6 fail. {#v-m-d}
  - (e) R3b reverted in lint only: the AC-3b lint, heading-parity and wikilink tests and the
    AC-5 synthetic fail. Reverted in the ingester only: the AC-3b ingester and heading-parity
    tests and the AC-5 synthetic fail. {#v-m-e}
  - (f) `exec` lint alone in `lint-gmd.sh`: two AC-10 tests fail. {#v-m-f}
  - (g, extra) ingester `rel:` guard removed: the AC-2 malformed test and the AC-5 synthetic
    fail. {#v-m-g}

## Left for the orchestrator {#left}

- Land the viascope split, then upstream `efb514a`, then this branch. Record the viascope sha
  here; AC-11 needs it. {#l-order}
- The bug-179 registry row says `fixed 44c6196` on this branch. Flip it to the master merge sha
  at merge. {#l-registry}
- No version bump was made here (`pyproject.toml`, `__init__.py`). Bump at release so this
  branch does not conflict with others. {#l-version}
- The clone has no `.venv-eval`, so `scripts/lint-gmd.sh` was not run on the clone itself. AC-10
  runs the real script from a throwaway ROOT, and lint and parity were each run directly over
  the gate scope. {#l-gate}
