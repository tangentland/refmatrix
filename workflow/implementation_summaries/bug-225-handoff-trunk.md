---
gmd: "0.1"
id: impl-bug-225-handoff-trunk
title: "bug-225: save-state / recall-state read the trunk from refs/remotes/origin/HEAD, verified as a commit, the name list only as fallback"
tags: [implementation, bug-225, handoff, save-state, recall-state, git, trunk]
metadata:
  node_type: implementation-summary
  date: 2026-11-14
---

# bug-225: the handoff trunk comes from origin/HEAD {#root}

rel: implements -> [[bug_registry]]
rel: implements -> [[plan-review-2026-11-13#lead]]

Two GREEN rounds, and neither wrote any tests:

- **r1.** RED `be9acae` (`tests/test_bug225_handoff_trunk.py`: 4 RED, 2 guards). Fix `81c3e95`.
  Ruling L82: read `refs/remotes/origin/HEAD` first, verify it, then fall back to the list.
- **r2.** RED `3453b6a` (10 RED, 3 M3 pins). Fix `053499d`. Ruling L96 answered ch-bsd r1 on
  `db411ad` (DIRTY 0B/1S/4M, persisted at `d735ce5`). Before r2, red-225 pinned the r1
  `trunk_error` path in `db411ad`.

## Defect {#defect}

`handoff._ss_git_facts` took the first of `("origin/main", "origin/master", "main", "master")`
that resolved. atlftpd's trunk is `develop`, and the handoff there reported 24 commits ahead of
`origin/master`. The right answer is 12 ahead of `origin/develop`. The fix gets the trunk from
origin/HEAD in every repo. It does not special-case the local `set-head` applied in atlftpd on
2026-11-14.

ch-bsd r1 found that the r1 fix still dropped failures. The candidate verify and the ahead
`git log` both ran through `_ss_sh`, which returns `''` on any error. A dangling origin/HEAD
fell back to the list and said nothing. Plain `rev-parse --verify` accepted a ref whose object
was missing; the `git log` then failed, and the handoff printed "0 commit(s) ahead — in sync".

## Change {#change}

`src/refmatrix/handoff.py`:

- `_ss_git_run(repo: Path, *args: str) -> tuple[int | None, str, str]` returns git's exit code,
  stdout and stderr. The exit code is `None` when git could not run: an OSError or the 20 s
  timeout. `_ss_git_failure(args, rc, out, err) -> str` turns a failed call into one string.
  {#git-run}
- `_ss_origin_head(repo: Path) -> tuple[str, str]` runs
  `git symbolic-ref --quiet --short refs/remotes/origin/HEAD`. Exit 0 returns the name. Exit 1
  means origin/HEAD is unset: it returns `("", "")` and the list decides without a message. Any
  other result comes back as an error string. {#origin-head}
- `_ss_trunk(repo: Path, facts: dict) -> None` checks the candidates in order: the name
  origin/HEAD gives, then `_SS_TRUNK_FALLBACK`. {#trunk}
  - Each candidate is verified with `rev-parse --verify --quiet <name>^{commit}`, so a ref to a
    missing object does not pass.
  - Exit 1 or 128 means the name does not resolve, and the next candidate is tried. Any other
    exit, a git that cannot run, or a timeout stops the loop, and the failure is reported.
  - When origin/HEAD names a ref that does not resolve, the report reads "origin/HEAD names `X`,
    which does not resolve; measured against `Y`". If no list candidate resolves either, it ends
    "no fallback trunk resolves".
  - The ahead `git log --oneline <base>..HEAD` is read the same way. If it fails, the failure is
    reported and `ahead_base` stays empty, so neither the doc nor recall-state can print a
    measured zero.
  - Each problem is stored in `facts["trunk_errors"]` as a (headline, detail) pair.
- `_ss_git_facts` runs `_ss_trunk` only when `branch` is non-empty. A non-git directory therefore
  starts no trunk git call and gets all-empty facts. `trunk_error` joins every problem into one
  string. {#facts}
- `_ss_trunk_lines` renders the problems. The save-state doc gets `- trunk: <headline> — <detail>`
  and recall-state gets the anomaly `trunk: <headline> (<detail>)`. When `symbolic-ref` failed,
  the headline is "origin/HEAD unreadable, measured by the fallback list". {#surface}
- `compose_save_state`'s result now carries `trunk_error`. That result is what the
  `rmx_save_state` verb returns, so MCP callers get it too (M1). {#verb-result}

`src/refmatrix/cli.py`: when `trunk_error` is set, `rmx save-state` prints it after the
`save-state <target>` line, escaped for rich (M1). {#cli}

`src/refmatrix/templates/commands/recall-state.md`: the conventions line and step 2 use
origin/HEAD only when it resolves to a commit (`git rev-parse --verify --quiet <name>^{commit}`).
Otherwise they use the first of `origin/main` / `origin/master` that resolves. Step 2 says to
report a skipped origin/HEAD (M2). {#template}

## Results {#results}

| check | result | log |
|---|---|---|
| r1: bug-225 file + save-state, install-commands, savestate-subfolder, hooks | 119 passed | `workflow/review-output/bug225-green.log` |
| r1: full suite | 7 failed, 4305 passed, 1 skipped; see [[#full-suite-r1]] | `workflow/review-output/bug225-full.log` |
| r1: the 3 non-baseline failures re-run with an absolute `PYTHONPATH` (the lead) | 44 passed | `workflow/review-output/bug225-new-fail-rerun.log` |
| r2: bug-225 file (26) + save-state, install-commands, savestate-subfolder, hooks, verb parity | 305 passed | `workflow/review-output/bug225-r2-green.log` |
| r2: the rest of the save/recall-state family (bridge-move, mcp pointer, memory bridge, plan2/3 remedies, savestate mtype, subject, task21_1 pointer, task3.6 r9, hooks reproducible) | 314 passed | `workflow/review-output/bug225-r2-family.log` |
| r2: full suite, absolute `PYTHONPATH` | 4 failed, 4328 passed, 1 skipped (45:54); none from this change, see [[#full-suite-r2]] | `workflow/review-output/bug225-r2-full.log` |

### Mutations {#mutations}

| round | mutation | killed by | log |
|---|---|---|---|
| r1 | origin/HEAD read dropped | the 4 RED | `bug225-mut1.log` |
| r1 | origin/HEAD name accepted without verify | dangling guard | `bug225-mut2.log` |
| pin (red-225) | `_ss_origin_head` swallows the error | 5: AC-6 ×3, AC-7, AC-8 | `bug225-trunk-error-mut1.log` |
| pin (red-225) | `_ss_render` trunk line dropped | AC-7 | `bug225-trunk-error-mut2.log` |
| pin (red-225) | recall-state trunk anomaly dropped | AC-8 | `bug225-trunk-error-mut3.log` |
| r2 A | verify swallows a non-0/1/128 exit (`rc != 0` → next candidate) | `test_r2_s1c_failing_verify_is_surfaced` | `bug225-r2-mutA.log` |
| r2 B | failed ahead `git log` read as 0 ahead | `test_r2_s1c_failing_ahead_log_is_surfaced_not_read_as_zero` | `bug225-r2-mutB.log` |
| r2 C | verify without the `^{commit}` peel | both S1b tests | `bug225-r2-mutC.log` |
| r2 D+E | dangling note dropped; CLI trunk line dropped | 3 S1a/S1b; the M1 CLI test | `bug225-r2-mutDE.log` |
| r2 F | non-git gate `if facts["branch"]:` → `if True:` | the 3 M3 pins | `bug225-r2-mutF.log` |

All logs are in `workflow/review-output/`. Every mutation ran in a throwaway copy under the
session scratchpad. Each restore ran as its own command and was followed by a `__pycache__`
clear, and `cmp` showed the restored copy matched the clone. The clone's `src/` was never
mutated.

### Real-data runs {#real-data}

These calls ran in-process with the clone's `src` and did not go through `rmx`:

| repo | `ahead_base` | commits ahead | `trunk_error` |
|---|---|---|---|
| atlftpd | `origin/develop` | 12 | empty |
| dev master | `origin/main` | 155 | empty |
| the clone | `origin/master` | 6 | empty |

The atlftpd figure matches the bug row.

### Full-suite failures, compared by E line {#full-suite-r1}

r1 (`bug225-full.log`): four failures match the release-0.82.0 baseline
(`workflow/review-output/release-0.82.0-full.log` on dev master) by E line:

- `brief_real_daemon`;
- `task21_1` AC-6 ×2;
- `gmd_lint_requires_version`, which is bug-155 (`docs/INDEX.md:31`, a dangling-doc link to
  the `adr-0000-adr-overview` id). This branch is cut before bug-155's fix.

Three failures were not in the baseline: `sandbox_redirect` ×2 and `catalog_measure`. They came
from a relative `PYTHONPATH=src`. The clone's `.venv-eval` is a symlink to the dev venv, so a
child process with another cwd imported the dev tree. With the absolute path those three passed.
r2 is in [[#full-suite-r2]].

### r2 full suite {#full-suite-r2}

`bug225-r2-full.log` was run with `PYTHONPATH=/Volumes/littlebig/refmatrix-bug225/src`: 4
failed, 4328 passed, 1 skipped. The r1 `PYTHONPATH` failures (`sandbox_redirect` ×2,
`catalog_measure`) pass. Each of the 4 failures, compared by E line with
`release-0.82.0-full.log` on dev master:

| test | E line here | baseline |
|---|---|---|
| `brief_real_daemon::test_an_unknown_class_fails_loudly_through_the_daemon` | `_duckdb.IOException: … Could not set lock on file "/private/tmp/bd.<x>/.refmatrix/catalog.A.duckdb"` | same; only the tmp dir name differs |
| `task21_1` AC-6 ×2 | `AssertionError: agent usage · window 2026-09-23 .. 2026-10-07T11:06:35`; `assert []` | identical |
| `gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate` | `in-scope GMD errors: docs/INDEX.md:31 … [dangling-doc] … adr-0000-adr-overview` | **different**: the baseline lists dangling `refmatrix-claude-md` links in a `workflow/bullshit/` report |

The gmd_lint failure is the same test as in the baseline but has a different error. That error is
bug-155's own E line: the bug-155 row records it as identical in a pre-fix tree, and this branch
is cut before bug-155's fix. The r1 run on this branch produced the same E line. The error
does not come from `handoff.py`, `cli.py`, the template or this summary. The 0.82.0 baseline's other
10 failures (`search_hooks` ×9, `repo_hooks_in_sync`) do not fail here.

### GMD lint {#lint}

This summary lints with 0 errors, both on its own and with `bug_registry` and the plan review in
scope. The repo-scope `./scripts/lint-gmd.sh` reports `dangling-doc` errors across the docs and
workflow set. This is the bug-155 docs set: the ADR / architecture / measurement ids that
`docs/INDEX.md` and older workflow docs point at, which this pre-fix branch lacks. None of the
errors is in this file (`bug225-lint-gmd.log`, `bug225-r2-lint-gmd.log`).

## Open {#open}

- **Closed: #open-test.** `db411ad` pins the `trunk_error` path, which r2 rewrote. The
  `trunk_error` mutation rows above show the pins kill. {#open-test}
- `~/.claude/commands/recall-state.md` is the user-level installed copy. The 0.83.0 deploy step
  runs `rmx init --force`, which backs the old copy up first, so the installed copy matches the
  package. That step is on the lead's release checklist, not this branch (L96 M2).
  {#open-install}
- The version is not bumped; that belongs to the 0.83.0 release step. {#open-version}
- **Closed by r3 M1 (L100): #open-no-trunk.** A repo where origin/HEAD is unset and no list
  name resolves now gets one info line in the save-state doc, `- trunk: none (origin/HEAD
  unset; no origin/main, origin/master, main or master)`. It is not a recall-state anomaly and
  not `trunk_error`, because nothing failed. See [[#green-r3]]. {#open-no-trunk}

## GREEN r3 (ruling L100) {#green-r3}

RED `5ef3b0c` added 7 RED tests and 4 guards; the git shim gained `B225_GIT_RC`,
`B225_GIT_STDERR` and `B225_GIT_MATCH`. The fix is `4e7a155`, and no tests were edited. Ruling
L100 answered ch-bsd r2 on `9c952eb` (DIRTY 0B/1S/1M, NO-GO; persisted at `e2505f3`). In r2,
`_ss_trunk` read a verify exit of 128 as "not found", so it measured `origin/master` past a
corrupt `origin/main` without saying anything.

### Change {#r3-change}

- **"Not found" is narrower.** In `_ss_trunk`, a candidate counts as not found only when
  `rev-parse --verify --quiet X^{commit}` exits 1 with an empty stderr. Under `--quiet`, git
  2.50.1 exits that way for a missing name or a ref to a missing sha. {#r3-verify}
- **Everything else stops the walk.** That covers exit 128 (corrupt object), exit 1 with
  stderr (unreadable object, broken ref, ref to a tree), any other exit, a git that cannot run,
  and a timeout. Each is reported through `_ss_git_failure` in git's own words, and nothing is
  measured, so there is no ahead line.
- **The headline names the source.** It is "origin/HEAD names `X`, which git could not verify;
  nothing measured" when origin/HEAD named the failing ref, never "does not resolve".
  Otherwise it is "could not verify trunk candidate `X`; nothing measured".
- **Same rule for origin/HEAD itself.** `_ss_origin_head` treats exit 1 with stderr as a
  failure.
- **One doc line per failure.** `_ss_git_failure` joins multi-line stderr with " / ". {#r3-failure-text}
- **No trunk, no failure.** When nothing resolves, nothing failed and origin/HEAD is unset,
  `facts["trunk_info"]` holds `none (origin/HEAD unset; no origin/main, origin/master, main or
  master)`. `_ss_render` prints it as one `- trunk:` line. It is kept out of `trunk_error` and
  out of recall-state's anomalies (M1). {#r3-none}
- **Template.** The conventions line and step 2 of `recall-state.md` name the full fallback
  list (`origin/main`, `origin/master`, `main`, `master`). Step 2 now says to report a check
  that fails with an error as an error, not as "not found". {#r3-template}

### Results {#r3-results}

All runs used `PYTHONPATH=/Volumes/littlebig/refmatrix-bug225/src`.

| check | result | log |
|---|---|---|
| bug-225 file | 37 passed | `bug225-r3-green-file.log` |
| bug-225 file + save-state, install-commands, savestate-subfolder, hooks, verb parity | 316 passed | `bug225-r3-green.log` |
| rest of the save/recall-state family (as r2) | 314 passed | `bug225-r3-family.log` |
| full suite | 4 failed, 4339 passed, 1 skipped (47:10); none from this change, see [[#r3-full-suite]] | `bug225-r3-full.log` |
| mutation r3-1: `rc == 1` without the stderr test | 2 failed: the tree-ref test, the shim exit-1-with-stderr case | `bug225-r3-mut1.log` |
| mutation r3-2: `rc in (1, 128)` (the r2 rule) | 5 failed: corrupt list candidate, corrupt origin/HEAD target, tree ref, shim exit 128 and exit 1 with stderr | `bug225-r3-mut2.log` |
| mutation r3-3: the `trunk: none` line dropped | 1 failed: `test_r3_m1_no_trunk_is_one_info_line_in_the_doc` | `bug225-r3-mut3.log` |

Each mutation ran in a throwaway copy under the session scratchpad. Each restore ran as its own
command, followed by a `__pycache__` clear and a `cmp` match. {#r3-mutations}

Real-data runs, in-process with the clone's `src`:

- In a temp clone whose `origin/master` holds a tree id, `ahead_base` is empty and the error is
  "origin/HEAD names `origin/master`, which git could not verify; nothing measured — `git
  rev-parse --verify --quiet origin/master^{commit}` exited 1: error: … expected commit type,
  but the object dereferences to tree type".
- atlftpd still gives `origin/develop`, 12 ahead, and dev master gives `origin/main`. Both have
  an empty `trunk_error` and an empty `trunk_info`. {#r3-real-data}

### r3 full suite, compared by E line {#r3-full-suite}

`bug225-r3-full.log` fails the same 4 tests as r2 with the same E lines. Compared with
`release-0.82.0-full.log` on dev master:

| test | compared with the baseline |
|---|---|
| `brief_real_daemon` | same `_duckdb.IOException … Could not set lock on file "/private/tmp/bd.<x>/.refmatrix/catalog.A.duckdb"` E line |
| `task21_1` AC-6 ×2 | identical E lines (`agent usage · window 2026-09-23 .. 2026-10-07T11:06:35`; `assert []`) |
| `gmd_lint_requires_version` | same test, different E: `docs/INDEX.md:31` and the rest of the bug-155 docs set |

The baseline's gmd_lint failure lists dangling `refmatrix-claude-md` links in a
`workflow/bullshit/` report. The E line here is bug-155's: this branch is cut before bug-155's
fix, and r1 and r2 produced the same line. None of the four failures comes from `handoff.py`,
`cli.py` or the template.
