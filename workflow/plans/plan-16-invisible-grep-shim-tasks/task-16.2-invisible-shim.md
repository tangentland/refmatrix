---
gmd: "0.1"
id: task-16.2-invisible-shim
title: "Task 16.2: rmxgrep/rmxrg always exec the real tool; the learner is spawned before the exec; rich mode and RMXGREP_MODE are gone"
tags: [task, grep, hooks, shim, drop-in]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-14
---

# Task 16.2: the invisible shim {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 5, after spec review r4 `bsd-plan16-spec-review-r4-33809ab`)
> Depends on: [[task-16.1-argv-faithful-learner]]

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[task-16.1-argv-faithful-learner]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]

## Revision 5 changelog {#revision-5}

Answers spec review r4 ([[bsd-plan16-spec-review-r4-33809ab]]).

| finding | answered in |
|---|---|
| s-r4-4 one keyed-line format (R2/AC-6 said "one byte") | R2 [[#r2]], R3 [[#r3]] (line format with the cwd; `learn status` prints LINE counts), AC-6 |
| s-r4-7 AC-4 `rmxgrep -i PAT dir` cannot pass | AC-4 (`-ri`), AC-4b (`-i` on a dir = `reason=tool-error`), mutation |
| m-r4-5 `$PWD` vs `getcwd` in the parity test | R2b [[#r2b]] (cwd rule + symlinked-cwd row) |

## Why {#why}

**Three routes run an agent's grep (#s-5).** Two of them reach the shim:

1. **The PreToolUse rewrite.** `grep-rewrite-guard.sh` → `rmxgrep-rewrite.py` turns a LEADING
   `grep`/`rg` in a command segment into the absolute wrapper path.
2. **The agent bashrc.** `~/.claude/agent-bashrc.sh`, sourced through `BASH_ENV` by every
   non-interactive CHILD bash, defines `grep()`/`rg()` functions that call the wrappers. Verified:
   `bash -c 'declare -f grep'` resolves to `$HOME/refmatrix/bin/rmxgrep`.
3. **Claude Code's own `grep()` function.** In the TOP-LEVEL Bash-tool shell, Claude Code's
   snapshot defines `grep()` to run its embedded ugrep. That shadows route 2's function there; `rg`
   is still `rmxrg`. So a grep the rewrite does not touch is NOT observed:
   - one in a non-head position (`if grep -q …`);
   - any command the guard exempts as git;
   - any command containing `<<`.

   This plan does not try to capture route 3, which would reopen d-3. Task 16.4 measures its share.
   {#routes}

Today routes 1 and 2 run with `RMXGREP_MODE=rich` from the generators. The interim since
2026-10-06 is `plain`, set by the user in `~/.claude/settings.json` and `.claude/settings.local.json`.
That value is already auto, so today's wrapper takes its real-tool path plus the flag-stripped ping.
This task deletes the rich branch and replaces the ping with 16.1's learner. {#rich}

## Requirements {#requirements}

**R1. Every path ends in the real tool.** In `bin/rmxgrep` and `bin/rmxrg`:
- Delete the rich branch, `RMXGREP_MODE` handling, and the flag-stripping ping.
- The early exits stay exactly as they are in BOTH wrappers: outside a project, rmx missing, stdin
  is a pipe, and learning is off.
  - The learning-off exit uses the shared `_marker_on` block, which reports unreadable markers per
    bug-080.
  - `rmxrg` gained its learning-off exit in `321ff97` (#s-4); this task keeps it and tests it.
- The final line is `exec "$REAL" "$@"` with argv untouched.
- `$REAL` is resolved ONCE to an absolute path (`command -v`). That same path is what runs and what
  is passed to the learner as `--bin` (#s-6). {#r1}

**R2. Spawn the learner, then exec.**
- **Slot check before spawning (#s-n9).** The shim counts the slot dirs under
  `<store_root>/.grep-learn-slots/` (16.1 R0b) that are fresher than 60 s, using a shell glob and
  `find -mmin`. If the count is at least `RMX_GREP_LEARN_MAX_INFLIGHT` (default 2), the shim does
  not spawn: it appends one keyed LINE (R3's format) to `<store_root>/.rmxgrep-teach/busy` and goes
  straight to the exec. This is what bounds process STARTS: a 1,000-file loop costs globs, not 1,000 Python starts
  at 0.14 s each.
- When the slots and the throttle (R3) both say go:
- Start `"$RMX" grep-learn --tool grep --bin "$REAL_ABS" --cwd "$PWD" [--retired-env
  RMXGREP_TEACH] -- "$@"` with stdin, stdout and stderr on `/dev/null`, backgrounded.
- Detaching, the slot cap and logging all belong to the learner (16.1 R0/R0b/R6); the shell does no
  more than start it. `/bin/sh`'s `&` alone does not give the child its own process group, so the
  learner's `os.setsid()` is what does (#s-1). {#r2}

**R2b. Two implementations of the spawn rules, one parity test (#s-r3-3).** {#r2b} The shims are
shell and `rmx grep` (16.5) is Python, so "one shared function" cannot be literal. The throttle key,
the slot count and the learn-switch read are implemented twice: in `bin/rmxgrep`/`bin/rmxrg` and in
`grep_learn.spawn()`. `tests/test_spawn_parity.py` feeds a table of (cwd, argv, slot state, marker
state) to both and asserts the same decision, the same stamp path and the same keyed line for every
row.
- **The cwd rule (m-r4-5).** The shim keys on the LOGICAL `$PWD`; Python's `os.getcwd()` is
  PHYSICAL (probed: cwd `/tmp` gives `$PWD=/tmp`, `os.getcwd()=/private/tmp`). So
  `grep_learn.spawn()` uses `os.environ["PWD"]` when it is set and
  `os.path.realpath($PWD) == os.path.realpath(os.getcwd())`, else `os.getcwd()`. The learner itself
  still resolves `realpath(cwd)` for paths (16.1 R2); only the throttle key and the `--cwd` text
  follow this rule.
- The parity table has a symlinked-cwd row (process started in a symlinked directory with `PWD`
  set to the symlink spelling) and a stale-`PWD` row (`PWD` names another directory); both sides
  must produce the same key.

**R3. Throttle keyed on what the search IS, and counted (#s-3).**
- The stamp key is `cksum` of `printf '%s\0' "$PWD" "$@"`: the cwd plus NUL-joined argv. `"a b"`
  and `a b` no longer collide, and the same relative argv in two directories counts as two
  searches.
- `RMXGREP_TEACH_TTL_MIN` stays as the throttle window.
- Every throttled call appends one LINE to `<store_root>/.rmxgrep-teach/throttled`, and every busy
  skip (R2) one line to `.../busy`, in ONE format (s-r4-4):
  `<epoch> <cksum> <PWD>\n` — the epoch in whole seconds, the R3 key, then the logical cwd as the
  REST of the line (a cwd may contain spaces; a newline in a cwd is replaced by `?`). Keyed lines,
  not bytes (#s-r3-7): 16.4 joins them by epoch window plus cwd (16.4 R1), never by argv.
- `rmx learn status` prints each file's LINE count since its last rotation (not its size). A
  throttled or busy grep is a counted skip, not an invisible one.
- No other writer uses these two files (16.3's missing-rg case goes through the learner's own log,
  16.3 R1).
- Both counters rotate at 1 MB. Stamps older than 24 h are pruned by the learner (16.1 R9). {#r3}

**R4. `RMXGREP_TEACH` is retired (d-2) (#m-2).**
- The shims stop reading it.
- If it is present in the shim's environment, the learner's record for that call carries
  `reason_extra=retired-env:RMXGREP_TEACH`, because the shim passes `--retired-env` to the learner.
- `rmx learn status` prints one line, "RMXGREP_TEACH is retired; use RMX_LEARN=0", when ANY record
  in the last 24 h carries that marker. It reads the log, not its own environment, because it runs
  in a different process from the grep.
- The shim prints nothing; byte-identity includes stderr. {#r4}

**R5. Generated config drops rich mode.** These changes go through the generators.
- `hooks.py` `AGENT_BASHRC_SECTION` loses `export RMXGREP_MODE`, and its comments (including the
  `rmxg` helper's) say that grep/rg are the real tools and only teach.
- `_install_agent_env`'s `env_block` loses `RMXGREP_MODE`. A project-scope merge REMOVES an
  existing key, whatever its value (`rich` or `plain`). The user-scope snippet says to delete it.
- **NEW CODE, named as such (#s-12):** today `hooks.check()` compares neither the agent-bashrc
  section nor the settings `env` block. This task extends `check()` to report:
  - a bashrc section that differs from `AGENT_BASHRC_SECTION`;
  - any `RMXGREP_MODE` key in the project settings, by name.
- `search_hooks.GUARD_TEMPLATE` header and the module docstring describe observe-only.
- `rmxgrep-rewrite.py`'s rewrite logic is unchanged (d-3). {#r5}

**R6. Tests that pin rich mode or `RMXGREP_TEACH` are rewritten, each listed (#s-11).**

| test | becomes |
|---|---|
| `test_rmxgrep.py::test_rich_mode_forces_rmx_even_when_piped` | differential case, `RMXGREP_MODE=rich` exported, proving it is inert |
| `::test_rich_mode_exit2_falls_back_to_real_grep` | same |
| `::test_plain_is_not_an_escape_anymore` | same |
| `::test_stdin_pipe_is_a_filter_even_in_rich_mode` | pipe exit kept; rich exported |
| `::test_teach_disabled_writes_no_stamp` | INVERTED: `RMXGREP_TEACH=0` still teaches (d-2) and logs `retired-env` |
| `::test_auto_mode_piped_stdout_teach_ping_writes_throttle_stamp` | stamp written by the cwd+argv key; the learner (not the ping) is spawned |
| `test_grep_stdin_dialect.py::test_rmxrg_injects_ere` | the `-E` injection is deleted with the rich branch; becomes a byte-identity case |
| `::test_rmxrg_respects_fixed_strings` | same |
| `::test_bre_fallback_preserves_stdin_for_the_real_tool` | same |
| `test_agent_env.py` (`RMXGREP_MODE` asserts) | inverted: absent |
| `test_learn_toggle_hook.py` (wrapper cases) | both wrappers; `RMXGREP_MODE` dropped from envs |
| docstrings in `test_rewriter_wrapper_resolution.py`, `test_grep_argv_order_e2e.py` | rich-mode wording updated |

**Sandbox rule (#s-11).** Every test that runs a wrapper sets `RMXGREP_RMX` to a sandbox path or
sets `RMX_LEARN=0`. Once d-2 lands, `RMXGREP_TEACH=0` no longer prevents a spawn. An unset
`RMXGREP_RMX` runs the DEPLOY `rmx` on PATH, which the hard rules forbid. A conftest guard fails any
test that spawns `rmx` from PATH. {#r6}

## Acceptance criteria {#acceptance}

1. **The differential (100%, no allowlist).** The corpus is `tests/fixtures/grep_differential.txt`:
   at least 40 invocations replayed from real transcript greps, plus the edge cases below.
   - For each case, `rmxgrep ARGS` vs `/usr/bin/grep ARGS` and `rmxrg ARGS` vs `rg ARGS` must match
     byte-for-byte on stdout, stderr and the exit code.
   - Run inside a project with learning ON and `RMXGREP_MODE=rich` exported.
   - Edge cases:
     - BRE `\b` and `^| 15 |` (bug-081);
     - `-rc` over a directory, a missing file (exit 2), and a binary file;
     - `-l -L -o -h -C 2 -m 1 -q`;
     - a `:` filename; `./f` beside `f`; a no-match (exit 1); `--color=always`.
   - The test fails at the first differing byte and prints both sides.
2. **Power of the differential.** Run against the CURRENT rich-mode shim first. The summary records
   which cases differ there. At minimum `\b`, `^`, the missing file and `-rc` must differ, or the
   corpus cannot see the class this plan removes.
3. **The caller is never delayed.** The `RMXGREP_RMX` stand-in's `grep-learn` sleeps 5 s (an
   external process, registered in the mock registry). `rmxgrep pat file | cat` returns in under
   1 s with the real tool's bytes and `$?`.
4. **The learner runs and gets the binary.** With the real learner, one `rmxgrep -ri PAT dir` call
   gives, within 5 s, a `grep-learn.log` record with `outcome=taught`, `bin` equal to the shim's
   resolved `$REAL`, and a queue record equal to the corpus-filtered `/usr/bin/grep -rniH --null PAT
   dir`.
   - **4b (s-r4-7).** `rmxgrep -i PAT dir` WITHOUT `-r` prints grep's own `Is a directory`, exit 2
     (probed on BSD 2.6.0), and the learner records `outcome=skipped reason=tool-error` with nothing
     queued. The learner never adds `-r`.
5. **Early exits, BOTH wrappers.** Outside a project, rmx missing, piped stdin, `RMX_LEARN=0`, and a
   store marker: each gives byte-exact output, no log record and no stamp. Covers `rmxrg` explicitly.
6. **Throttle and slots.**
   - With 2 fresh slot dirs present (held by two sleeping stand-in learners), a third call does not
     spawn, `busy` gains exactly one line `<epoch> <cksum> <PWD>` whose `cksum` equals
     `printf '%s\0' "$PWD" "$@" | cksum`'s, and the output is byte-identical.
   - The same cwd and argv twice within the TTL gives one spawn and one such line in `throttled`.
   - A cwd containing a space round-trips through the line (16.4's join reads it back).
   - `rmx learn status` prints the two line counts.
   - The same argv from two cwds gives two spawns.
   - `"a b"` vs `a b` gives two spawns.
7. **`RMXGREP_TEACH` retired.** `RMXGREP_TEACH=0` exported: stderr is byte-identical, the learner
   still runs, its record carries `retired-env`, and `rmx learn status` prints the retirement line.
8. **Config.**
   - After `install-hooks --force` at project scope, no `RMXGREP_MODE` is left in settings or in the
     bashrc section.
   - `install-hooks --check` is clean, and reports drift when either is re-added by hand, or when
     the bashrc section is edited.
9. **Overhead, with the REAL learner (#m-4).** Measured over 200 runs of a small fixture, learner
   spawning every run (TTL 0), as shim wall minus bare-tool wall:
   - p50 ≤ 15 ms, p95 ≤ 40 ms;
   - the learner's own CPU is reported beside the wall times.

   A stand-in already passes this bound today (measured +8.4 ms p50 / +10.7 ms p95), so a stand-in
   proves nothing. A miss is reported and decided by the plan, not loosened.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `bin/rmxgrep`, `bin/rmxrg` | rich branch + ping removed; `$REAL_ABS`; cwd+argv stamp; throttle count; learner spawn |
| `src/refmatrix/hooks.py` | bashrc + env block without `RMXGREP_MODE`; removal on merge; `check()` extended (new code) |
| `src/refmatrix/search_hooks.py` | guard/docstring text |
| `src/refmatrix/cli.py` | `learn status`: throttled count, retired-env line; install-hooks `--help` text |
| tests in R6; `tests/test_grep_shim_differential.py`, `tests/fixtures/grep_differential.txt` (new); a conftest guard against PATH `rmx` | |
| `workflow/test_mock_registry.md` | the sleeping stand-in (AC-3) |

## Deploy note {#deploy}

`~/.claude/settings.json` (user scope) is never edited by rmx. After the deploy, the user deletes the
`RMXGREP_MODE` key from its `env` block; its current value is `"plain"`. Until then R1 makes it
inert. The bashrc section is refreshed only by `rmx install-hooks --apply --force`, which also
refreshes the rewriter (bug-080 changed it). The handoff names both steps.

## Test strategy {#test-strategy}

- Real binaries, `shell=False`, list argv. A shell control gets rewritten by the PreToolUse hook.
- Pre-registered mutations:
  - restore the rich branch: AC-1 fails;
  - run the learner in the foreground: AC-3 fails;
  - key the stamp on argv only: AC-6 fails;
  - drop `RMXGREP_MODE` removal from the merge: AC-8 fails;
  - remove the slot check: AC-6 (busy case) fails;
  - write a byte instead of a keyed line: AC-6 fails;
  - the learner adds `-r` for a directory operand: AC-4b fails;
  - key the Python spawn on `os.getcwd()`: the parity test's symlinked-cwd row fails;
  - remove `rmxrg`'s learning-off block: AC-5 fails. {#tests}
