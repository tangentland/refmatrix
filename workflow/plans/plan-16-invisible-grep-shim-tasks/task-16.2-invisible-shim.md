---
gmd: "0.1"
id: task-16.2-invisible-shim
title: "Task 16.2: rmxgrep/rmxrg always exec the real tool; the learner runs detached; rich mode and RMXGREP_MODE are gone"
tags: [task, grep, hooks, shim, drop-in]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
---

# Task 16.2: the invisible shim {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: [[task-16.1-argv-faithful-learner]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]

## Why {#why}

Agent greps reach the shim by two routes, and both must become invisible:

1. **The PreToolUse rewrite.** `grep-rewrite-guard.sh` → `rmxgrep-rewrite.py` turns a leading
   `grep`/`rg` into the absolute wrapper path.
2. **The agent bashrc.** `~/.claude/agent-bashrc.sh`, sourced through `BASH_ENV` by every
   non-interactive bash, defines `grep()` and `rg()` as functions that call the wrappers. So a grep
   inside a bash SCRIPT the agent runs also reaches the shim.

The second route is why the plan's earlier "scripts are not rewritten" note was wrong; corrected
in the plan by this task. {#routes}

Today both routes run with `RMXGREP_MODE=rich`, which `hooks.py` writes into the bashrc and into
the Claude settings `env` block. In rich mode the wrapper calls `rmx grep`, which answers in
grep's place. That is the mode this task deletes. {#rich}

## Requirements {#requirements}

**R1. Every path ends in the real tool.** In `bin/rmxgrep` and `bin/rmxrg`:
- delete the rich branch, the `RMXGREP_MODE` handling, and the flag-stripping ping;
- keep the four early exits exactly as they are: outside a project, rmx missing, stdin is a pipe,
  learning is off;
- the final line is `exec "$REAL" "$@"` with argv untouched. {#r1}

**R2. The learner is spawned detached, BEFORE the exec, and never delays it.**
- When the throttle stamp (kept: `RMXGREP_TEACH_TTL_MIN`, per-argv `cksum`) says go, launch
  `"$RMX" grep-learn --tool grep --cwd "$PWD" -- "$@"` with all three stdio streams on `/dev/null`,
  in the background, and disowned.
- Because the learner is backgrounded before `exec` and holds none of the caller's descriptors,
  the caller's pipe closes when the real tool exits.
- `--cwd "$PWD"` is the caller's cwd, captured before any `cd`. {#r2}

**R3. `RMXGREP_TEACH` is retired into the learn switch (decision d-2).**
- The shims stop reading it.
- If it is set, the learner records `reason=retired-env:RMXGREP_TEACH` on that call's log record,
  and `rmx learn status` prints one line naming `RMX_LEARN=0` as the switch to use.
- The shim prints NOTHING on stderr. Byte-identity with the real tool includes stderr, and a
  per-call warning would break it on every grep.
- The 2026-09-15 rule holds: the learn switch is the only off switch. {#r3}

**R4. Generated config drops rich mode.** All of this is through the generators, never by hand
(PROJECT_PROFILE#constraints: hook config is generated):
- `hooks.py` `AGENT_BASHRC_SECTION` loses `export RMXGREP_MODE`. Its comment, and the `rmxg`
  helper's comment ("index-backed grep"), say that grep/rg are the real tools and only teach, and
  that the index is asked by name.
- `_install_agent_env`'s `env_block` loses `RMXGREP_MODE`.
- At project scope, the settings merge REMOVES an existing `RMXGREP_MODE` key. At user scope, the
  printed snippet says to delete it, and `rmx install-hooks --check` reports a present
  `RMXGREP_MODE` as drift, by name.
- `search_hooks.GUARD_TEMPLATE` header text and the module docstring describe observe-only.
- `rmxgrep-rewrite.py`'s rewrite logic is unchanged (decision d-3). {#r4}

**R5. Tests that pinned rich mode are rewritten, not deleted silently.**
- In `tests/test_rmxgrep.py`: `test_rich_mode_forces_rmx_even_when_piped`,
  `test_rich_mode_exit2_falls_back_to_real_grep`, `test_plain_is_not_an_escape_anymore` and
  `test_stdin_pipe_is_a_filter_even_in_rich_mode` become the differential cases in AC-1, each
  with `RMXGREP_MODE=rich` STILL EXPORTED, proving the variable no longer changes anything.
- `test_agent_env.py` and `test_learn_toggle_hook.py` assertions on `RMXGREP_MODE` invert: it must
  be absent.
- Every removed test is listed in the implementation summary with what replaces it. {#r5}

## Acceptance criteria {#acceptance}

1. **The differential.** A fixed corpus of at least 40 invocations, held in
   `tests/fixtures/grep_differential.txt` and replayed from the agent transcripts' real grep/rg
   commands plus the edge cases below. For each one, `rmxgrep ARGS` vs `/usr/bin/grep ARGS` and
   `rmxrg ARGS` vs `rg ARGS` must match byte-for-byte on stdout, on stderr, and on the exit code:
   **100%, no allowlist.**
   - Run inside a project with learning ON and with `RMXGREP_MODE=rich` exported.
   - Edge cases that must appear:
     - BRE `\b` and the `^| 15 |` row (the 2026-10-06 false negatives);
     - `-c` over a directory with `-r`, a missing file (exit 2), and a binary file;
     - `-l`, `-L`, `-o`, `-h`, `-C 2`, `-m 1`, `-q`;
     - a filename containing `:`, and `./f` beside `f`;
     - a no-match (exit 1);
     - `--color=always`.
   - The suite fails on the FIRST differing byte and prints both sides.
2. **The learner never delays the caller.** `RMXGREP_RMX` points at a stand-in `rmx` whose
   `grep-learn` sleeps 5 s. This is a test double for an external process, registered in the mock
   registry; the real learner is covered by 16.1.
   - `rmxgrep pat file | cat` returns in under 1 s.
   - `$?` and the bytes equal the real tool's.
3. **The learner does run.** With the real learner, one `rmxgrep -i PAT dir` call leads, within
   5 s, to a `grep-learn.log` record with `outcome=taught` and a queue record whose hits equal
   `/usr/bin/grep -rniH --null PAT dir`'s.
4. **The early exits are byte-exact and teach nothing.** Outside a project, rmx missing, a piped
   stdin, or `RMX_LEARN=0`: no log record and no stamp.
5. **The throttle holds.** The same argv twice within the TTL gives one learner spawn.
6. **`RMXGREP_TEACH` is retired.** With `RMXGREP_TEACH=0` set, stderr is still byte-identical and
   the learner still runs. Its log record carries `retired-env:RMXGREP_TEACH`, and `rmx learn
   status` names `RMX_LEARN=0`.
7. **Config is regenerated.** After `rmx install-hooks --force` at project scope,
   `.claude/settings.local.json` has no `RMXGREP_MODE` and the bashrc section has no
   `RMXGREP_MODE`. `rmx install-hooks --check` is clean, and reports drift when the key is
   re-added by hand.
8. **The shim's overhead is bounded.** Shim wall minus bare-tool wall over 200 runs of a small
   fixture, learner spawning on every run (TTL 0): p50 ≤ 15 ms, p95 ≤ 40 ms. Numbers are recorded
   in the summary. If they miss, the summary says so and the plan decides; the bounds are not
   loosened silently.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `bin/rmxgrep`, `bin/rmxrg` | rich branch + ping removed; detached learner spawn; header rewritten |
| `src/refmatrix/hooks.py` | bashrc section + env block without `RMXGREP_MODE`; removal on merge; `--check` drift |
| `src/refmatrix/search_hooks.py` | guard/docstring text |
| `tests/test_rmxgrep.py`, `tests/test_agent_env.py`, `tests/test_learn_toggle_hook.py` | rich-mode pins rewritten per R5 |
| `tests/test_grep_shim_differential.py` (new), `tests/fixtures/grep_differential.txt` (new) | AC-1, AC-2 |
| `workflow/test_mock_registry.md` | the sleeping stand-in `rmx` (AC-2) |

## Deploy note {#deploy}

`~/.claude/settings.json` (user scope) is never edited by rmx. After the deploy, the user deletes
`"RMXGREP_MODE": "rich"` from its `env` block. Until they do, R1 makes it inert. The handoff names
this step.

## Test strategy {#test-strategy}

- Real binaries throughout. Every exec uses `shell=False` and a list argv, because a shell control
  gets rewritten by the PreToolUse hook (test_grep_argv_order_e2e.py's trap list).
- Each differential case is proven to have power: it is run against the CURRENT rich-mode shim
  first, and the summary records which cases differ there. At least the `\b`, `^`, missing-file
  and `-rc` cases must, otherwise the corpus cannot see the defect class this plan removes.
- Pre-registered mutations:
  - restore the rich branch: AC-1 fails;
  - run the learner in the foreground: AC-2 fails;
  - drop the `RMXGREP_MODE` removal from the merge: AC-7 fails. {#tests}
