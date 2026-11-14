---
gmd: "0.1"
id: impl-bug-225-handoff-trunk
title: "bug-225: save-state / recall-state read the trunk from refs/remotes/origin/HEAD, the name list only as fallback"
tags: [implementation, bug-225, handoff, save-state, recall-state, git, trunk]
metadata:
  node_type: implementation-summary
  date: 2026-11-14
---

# bug-225: the handoff trunk comes from origin/HEAD {#root}

rel: implements -> [[bug_registry]]
rel: implements -> [[plan-review-2026-11-13#lead]]

TDD GREEN for the RED group committed at `be9acae` (`tests/test_bug225_handoff_trunk.py`, 4 RED
and 2 guards). The fix is in `81c3e95`. This step wrote no tests. Ruling L82 in the lead
resolutions of the 2026-11-13 plan review sets the shape: read `refs/remotes/origin/HEAD` first,
verify every candidate with `rev-parse --verify`, then fall back to the list. The template's
trunk wording names origin/HEAD.

## Defect {#defect}

`handoff._ss_git_facts` took the first of `("origin/main", "origin/master", "main", "master")`
that resolved. In atlftpd, whose trunk is `develop`, the handoff reported 24 commits ahead of
`origin/master`. The correct answer was 12 ahead of `origin/develop`. The fix does not read the
local `set-head` workaround applied there on 2026-11-14 as a special case: origin/HEAD is now
the general source.

## Change {#change}

`src/refmatrix/handoff.py`:

- `_SS_TRUNK_FALLBACK` holds the old list, which is unchanged and in the same order.
- `_ss_origin_head(repo: Path) -> tuple[str, str]` runs
  `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` and returns `(name, error)`. Exit 0
  returns the name. Exit 1 (unset; `--quiet` prints nothing) returns `("", "")`, so the code
  falls back without a message. Any other exit, or git failing to run (OSError or
  SubprocessError), returns an error string. Nothing is swallowed. {#origin-head}
- `_ss_git_facts(repo: Path, since: str | None) -> dict` reads origin/HEAD only when `branch` is
  non-empty. A non-git directory therefore gives the same all-empty facts it gave before, with
  no error. The function puts origin/HEAD's name in front of the list and verifies EVERY
  candidate with `rev-parse --verify --quiet`. A dangling origin/HEAD fails that check and the
  list decides. The facts dict gets a new key, `trunk_error`. {#facts}
- When `trunk_error` is set, `_ss_render` (the save-state doc) adds the line
  `- trunk: origin/HEAD unreadable, measured by the fallback list — <error>`, and
  `compose_recall_state` adds the matching anomaly. Both read it through `git.get(...)`, so
  callers that build their own facts dict keep working. {#surface}

`src/refmatrix/templates/commands/recall-state.md`: the conventions line and step 2 name the
trunk as `refs/remotes/origin/HEAD` (the repo's default branch), else `origin/main` /
`origin/master`. {#template}

## Results {#results}

| check | result | log |
|---|---|---|
| bug-225 file + save-state, install-commands, savestate-subfolder, hooks tests | 119 passed | `workflow/review-output/bug225-green.log` |
| full suite | 7 failed, 4305 passed, 1 skipped (46 min); none touches handoff, see [[#full-suite]] | `workflow/review-output/bug225-full.log` |
| the 3 non-baseline failures re-run with an absolute `PYTHONPATH` (the lead), plus the bug-225 file | 44 passed | `workflow/review-output/bug225-new-fail-rerun.log` |
| mutation 1: origin/HEAD read dropped | 4 failed (the 4 RED), 2 guards pass | `workflow/review-output/bug225-mut1.log` |
| mutation 2: origin/HEAD name accepted without verify | 1 failed (dangling guard, `ahead_base` = `origin/gone`) | `workflow/review-output/bug225-mut2.log` |

### Full-suite failures, compared by E line {#full-suite}

Four failures match the release-0.82.0 baseline by their E lines:

- `test_brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon`.
- `test_task21_1_agent_usage_report` AC-6, two tests: `assert []` against the frozen-fixture
  counts.
- `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate`:
  `docs/INDEX.md:31` `[dangling-doc] [[adr-0000-adr-overview]]`. This is bug-155, and this branch
  is cut before its fix.

Three were not in the baseline, and all three came from how the suite was run:

- `test_sandbox_redirect`, two tests. The E line reads "tests in
  /Volumes/littlebig/refmatrix-bug225 would exercise refmatrix from
  /Users/tholley/claude_tools/refmatrix/src/refmatrix; set
  PYTHONPATH=/Volumes/littlebig/refmatrix-bug225/src".
- `test_catalog_measure::test_rewrite_bytes_is_the_median_of_the_runs`: `KeyError:
  'rewrite_bytes_all'` after "measured 0/1 stores; failed=1".

The run used `PYTHONPATH=src`, which is relative. The clone's `.venv-eval` is a symlink to the
dev venv, so a child process started with another cwd imported the dev tree. The lead re-ran the
three files plus the bug-225 file with the absolute clone `src` prepended, and all 44 passed.
None of the seven touches `handoff.py` or the template.

The mutations ran in a throwaway copy under the session scratchpad. Each restore was a
separate command and was followed by a `__pycache__` clear. The clone's `src/` matched HEAD
afterwards. {#mutations}

Real-data runs, not through `rmx`: in the clone, `ahead_base` is `origin/master`, which is what
origin/HEAD names there, and `trunk_error` is empty. A non-git temp directory gives all-empty
facts. A temp repo whose `refs/remotes/origin/HEAD` points outside `refs/` makes `symbolic-ref`
exit 128. For it, `trunk_error` holds the error text and the list still picks `master`.
{#real-data}

## Open {#open}

- No test pins the `trunk_error` path: a non-0/1 exit is surfaced in the doc and the anomaly
  list. The exit-128 repo above can be the fixture. This is for ch-test-engineer. {#open-test}
- `~/.claude/commands/recall-state.md` is a user-level installed copy, produced by
  `init_agents.install_commands`. After the deploy it will differ from the package. The
  installer reports `skip … differs` until `rmx init --force` runs, and `--force` backs up the
  old copy first. Nothing in the repo needs regenerating. {#open-install}
- The version was not bumped. That is left to the 0.83.0 release step. {#open-version}
