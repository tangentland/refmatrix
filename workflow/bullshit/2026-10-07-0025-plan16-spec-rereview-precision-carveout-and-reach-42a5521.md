---
gmd: "0.1"
id: bsd-plan16-spec-rereview-42a5521
title: "plan-16 spec re-review (r2): 19 of 23 closed, but 16.4's precision gate cannot fail again through its new carve-out, and the Grep-tool route cannot reach the learner as written"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim
task: spec-review-16.1-16.4
round: 2
tags: [bsd, audit, spec-review, grep, drop-in, learning, hooks, measurement]
---

# ch-bsd spec re-review of plan-16, revision 2 (pre-implementation) {#root}

**Commit:** `42a5521fb79ffeb2228cd1ddf72ffa1c662ba4a1`, *docs(plan-16): specs revision 2 — all 23
spec-review findings addressed*
**Branch:** `bsd-r1-remedy` (shared tree; I wrote only this file; no mutations; `src/`, `tests/`,
INDEX.md, IMPRESSIONS.md and last_run.log are untouched; a concurrent r4 code audit is running)
**Audit written:** 2026-10-07T00:25:18-0700
**Scope:** the plan and the task specs 16.1–16.4 at 42a5521, checked against the code they rely on
(`watch.py`, `ingest.py`, `learn_switch.py`, `learn_queue.py`, `daemon._learn_grep_hits` /
`_drain_learn_queue`, `store.upsert_entity` / `add_evidence`, `cli.cli_entry`, `bin/rmxgrep`,
`bin/rmxrg`, `search_hooks.TEACH_TEMPLATE`), the Claude Code binary
(`~/.local/share/claude/versions/2.1.292`), BSD grep 2.6.0-FreeBSD (live runs in my scratchpad), and
this project's 62 real transcripts (15 top-level and 47 subagent).

The user's decisions d-1, d-2 and d-3 are settled. Nothing here reopens them.

rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: related-to -> [[impression_bsd_guard_cannot_fire]]

## Live evidence gathered {#evidence}

- **Corpus predicate (b-1).** `watch.is_relevant` imports nothing from watchdog at module level.
  `watch.py` itself imports `refmatrix.store` and `refmatrix.sync`. `is_relevant` needs
  `CODE_EXTS`, `DOC_EXTS`, `load_ignore_spec` and `IgnoreSpec` from `ingest.py`, and `ingest.py`
  imports `Store`. Separately, `refmatrix/__init__.py` imports `store` and `query`, so ANY
  `import refmatrix.X` loads `pyroaring`, `refmatrix.store` and `refmatrix.query`
  (`-X importtime`, measured). It does NOT load duckdb, lance or watchdog. `is_relevant` rejects
  every dot segment, `venv`/`node_modules`/`__pycache__`/`dist`/`build`, and non-corpus
  extensions. It applies `.refmatrix_ignore` only when `root` is passed. The daemon's own watcher
  calls `is_relevant(p)` without a root, and `sync_files` re-applies `should_ignore`.
- **Roots (b-4).** `learn_switch.store_marker(root) = root/learn.off`, `learn_queue.queue_path(root)`
  is under the same root, and `_drain_learn_queue` uses `self.root` (the store dir) with
  `Path(self.root).parent` as `project_root`. The spec's `store_root`/`project_root` table matches
  all of this.
- **Store writes (b-5).** `add_evidence` is an unconditional INSERT plus an `evidence` event in
  `facts.log`. `upsert_entity` appends an `entity` event AND a `protect` event on every call, even
  when the row is unchanged (`store.py`, after the upsert). `facts.log` is 249 MB today.
  `_learn_grep_hits` assigns `kind` from a hardcoded 13-suffix set (`daemon.py:4281`), whereas
  sync uses `CODE_EXTS` (`sync.py:236`). Entity identity is `(partition_id, kind, name)`.
- **BSD grep 2.6.0 (s-10 table), live runs:**
  - `-S` follows symlinks (it surfaced `./dl/…` duplicates); `-O` follows command-line links;
    `-p` and the default do not.
  - `-y` = `-i`. `-P`/`-T`: `invalid option`, exit 2.
  - `-X`/`-M` on plain text: exit 2. `-J`/`-Z` on plain text: correct lines, exit 0.
  - `-I` skips binary; `-U` gives normal output. `-d read` on a directory: exit 2. `-D skip` skips
    a FIFO. `-m 1` applies per file under `-r`.
  - `--ignore-case` and `-2` (`-NUM` context) are accepted.
  - `Binary file X matches` carries no NUL under `--null`.
  - `grep -rn PAT` with NO operand searches the cwd.
  - A missing operand or an unreadable file under `-r` gives **exit 2 WITH valid hits on stdout**.
  - A FIFO under `-r` blocks indefinitely (my own probe hung on one).
- **Detach (s-1).** A Python child of a `/bin/sh` script `&` calls `os.setsid()`. It succeeded with
  and without job control (pgid 34086→34087), and the child survived `killpg(SIGKILL)` of the caller's
  group and wrote its record. **But** a `killpg` 5 ms after spawn killed it (no output), because it
  had not reached `setsid` yet. Measured `rmx --help` wall time (cli_entry re-exec plus imports) is
  0.14 s, so that is the vulnerable window. Background pings DO survive normal command completion:
  `cli.log` holds 72 recent `grep --limit 3` records (31 of them exit 2).
- **Stamp key (s-3).** `/bin/sh` (bash 3.2 in sh mode, `/private/var/select/sh -> /bin/bash`)
  `printf '%s\0'` emits NULs, and `"/a" "a b"` and `"/a" "a" "b"` produce different cksums.
  `command -v grep` under a PATH containing `.` returns an absolute `$PWD/./grep`.
- **Claude Code binary (b-3).** `Xno(...)` builds `["--hidden"]`, then `--glob !X` for each entry in
  `Gno=[".git",".svn",".hg",".bzr",".jj",".sl"]`, then `--max-columns 500`. It then adds `-U
  --multiline-dotall`, `-i`, `-l` or `-c -H`, `--json` (content) or `--null`, `-n`, `-o`, the
  context flags, the pattern (`-e` only if it starts with `-`) and `--type T`.
  - **`glob` is split on whitespace, then on commas unless it contains braces,** and each piece
    becomes its own `--glob`.
  - It also adds DYNAMIC `--iglob` deny globs from the permission rules, orphaned-plugin-version
    `!**/…/**` globs (computed with `rg --files`), and task-output globs.
  - The rg is the builtin one (`USE_BUILTIN_RIPGREP`, with `--no-config`).
  - The constants exist as JS literals, so a content-anchored extraction is feasible. The minified
    names change between versions.
- **Hook shell.** `TEACH_TEMPLATE` is `#!/usr/bin/env bash`. `BASH_ENV=~/.claude/agent-bashrc.sh`
  is in both settings `env` blocks. `bash -c 'command -v rg'` prints **`rg`** (the function name),
  not a path.
- **Transcripts (16.4 oracle):** 2,342 Bash commands containing a grep/rg segment (1,103 in
  subagents), and **0 Grep-tool calls**. Of those commands:
  - piped into a post-processor (`head`/`tail`/`wc`/`sort`/`awk`/`sed`/`cut`): 1,785 (76.2%);
  - with more than one grep/rg in the command: 1,084 (46.3%);
  - with any `file:N:` line in the result: 786 (33.6%);
  - **cleanly attributable** (one grep segment, at the head of the pipeline, no pipe or only
    `head`/`tail`, line-addressed output): **55 (2.3%)**, of which 13 had no pipe at all;
  - `2>/dev/null`: 413 (17.6%);
  - heredoc: 390; git in the command: 358.
- **Whole-tree recursion.** `/usr/bin/grep -rn learn_switch .` at the project root takes
  **103 s** (74 s user), because it walks `.refmatrix/` (3.3 GB), `.venv-eval/` (1.0 GB) and
  `eval/datasets/` (124 MB). With dot-dirs excluded it still takes 97 s (`eval/datasets` jsonl).
  The same search over `src tests` takes 0.21 s. In the transcripts, about 68 of about 200
  recursive `grep -r` commands name no path (heuristic count).

## Status of the 23 prior findings {#prior-status}

| id | status | evidence |
|---|---|---|
| b-1 corpus | **closed** | 16.1 R3: one predicate, filtered before the cap, `out_of_corpus` counted, AC-5 with a walk-order-first 300-hit file. `is_relevant` does reject `.refmatrix/`, `.venv-eval/`, `__pycache__/` and `.pyc`. Residuals are filed as new findings [[#m-n6]] and [[#s-n1]]. |
| b-2 tautological oracle | **OPEN** | The re-run oracle was replaced, but R4's `unseen-but-verified` carve-out makes precision_B unfalsifiable again, and AC-4 contradicts R3 ([[#b-n1]]). The O2 oracle has zero coverage ([[#s-n10]]). |
| b-3 Grep-tool argv | **partially closed** | `--hidden`, the VCS globs, `--max-columns` and the paging fields are mapped (verified against the binary), and the control is the tool's response. Still open: the glob split rule ([[#s-n4]]), 16.1's rg table cannot parse the long flags 16.3 emits ([[#s-n3]]), `command -v rg` yields a function name ([[#s-n5]]), and the pin cannot see an upgrade ([[#s-n6]]). |
| b-4 roots | **closed** | The `#roots` table matches the code exactly. AC-10 7b/7c cover the marker with the env var unset. AC-11/12 drain through a `Daemon` on `store_root`. 16.3 R2 defers to the learner. |
| b-5 store growth | **partially closed** | `linkage_evidence` dedupe plus AC-11. `facts.log` still grows by 2+ events per file per re-teach ([[#s-n7]]). |
| s-1 pgid | **closed** | `os.setsid()` measured to escape the caller's pgid and to survive `killpg`, with and without job control. Residual window and EPERM: [[#m-n2]]. |
| s-2 fan-out | **partially closed** | Searches are capped at 2. Process STARTS are not ([[#s-n9]]). |
| s-3 throttle key | **closed** | `printf '%s\0' "$PWD" "$@"` verified in `/bin/sh`. Throttled calls are counted. Rotation: [[#m-n3]]. |
| s-4 rmxrg toggle | **closed** | `bin/rmxrg:52-70` carries `_marker_on` and the `RMX_LEARN` case. `test_rmxrg_follows_the_toggle_too` exists. 16.2 AC-5 names `rmxrg`. |
| s-5 route 3 | **closed** | `declare -f grep` in this shell is Claude Code's ugrep function, as documented. 16.4 measures `unobserved_share`. |
| s-6 binary | **partially closed** | Closed for the shims (sh `command -v` returns an absolute path). Open for 16.3, where the bash hook's `command -v rg` returns `rg` ([[#s-n5]]). |
| s-7 symlinked cwd | **closed** | R2 resolves the cwd with `realpath`, and AC-6 covers it. A separate identity split by `kind` is new: [[#s-n8]]. |
| s-8 matching rules | **closed** | R8 states read-time verification. AC-12 tests both `-i` directions. |
| s-9 RED power | **closed** | AC-1 (a)/(b)/(c). `-i` and `-F` keep→drop mutations are pre-registered. |
| s-10 flag table | **closed** | Every row I could run is true on this machine. Residual gaps (long aliases, `-NUM`, the exit-2 rule) are in [[#m-n1]] and [[#m-n7]]. |
| s-11 pinned tests | **closed** | The R6 table lists all of them. The sandbox rule plus a conftest guard handle the deploy `rmx`. |
| s-12 surfaces / `--check` | **closed** | Surfaces are listed with line refs. `check()` is named as new code. The deploy note says `plain` and `--apply --force`. |
| s-13 16.4 pitfalls | **closed** (residual) | cwd, subagents, the exec'd rewriter and no train-on-test are all specified. The old-sha runtime is underspecified: [[#m-n5]]. |
| m-1 stale plan | **partially closed** | The header and the tasks table are fixed. The `#learner` prose now contradicts 16.1 ([[#s-n2]]). |
| m-2 retired-env trigger | **closed** | `learn status` reads the log. `--retired-env` is passed by the shim. |
| m-3 binary / streaming | **closed** | R2 is streaming, `binary` is counted, and the child is killed at the cap. |
| m-4 overhead stand-in | **closed** | AC-9 requires the REAL learner with TTL 0 and reports its CPU. |
| m-5 delegate swallow | **OPEN** | `cli.py:6334-6336` is still `_broker_learn_from_grep(...)` / `except Exception: pass`. No bug-registry row and no spec mention. The commit message says "all 23 addressed". |

Tally: **closed 15**, **partially closed 6**, **open 2** (b-2, m-5).

## New findings {#findings}

### BULLSHIT: 16.4's precision_B cannot fail through its own carve-out, and AC-4 contradicts R3 {#b-n1}

**Spec:** 16.4 R3/R4 (precision_B row), AC-4
**What:** precision_B is "taught pairs the agent saw / taught pairs ≥ 0.98". Taught pairs the agent
did not see are "counted separately as `unseen-but-verified` by re-reading the line".
**Why it is bullshit:** Arm B runs `grep_learn` ON THE SNAPSHOT. Every pair it teaches is a line of
that snapshot which matched under the caller's argv, so re-reading the line verifies it by
construction. Two readings are possible, and neither works:
- **Carve-out applied.** Every taught pair is either seen or unseen-but-verified, so precision_B
  is 1.0 on any input. This is the b-2 tautology again, one step removed.
- **Carve-out not applied.** precision measures truncation, not fidelity. 76% of real grep
  commands pipe into `head`/`tail`/`wc`/…, so the agent saw a prefix while the learner teaches up
  to 200. The 0.98 gate then fails for a reason unrelated to the learner.

AC-4 claims that a recorded line edited after the fact pushes precision_B below 1. Under R3,
though, the edited pair FAILS the hash check and leaves O1, and the re-run's pair becomes
`unseen-but-verified`. So precision is unchanged, and AC-4's independence proof contradicts R3.
**Fix:**
- Compute precision ONLY over invocations whose recorded output is COMPLETE: no pipe stage after
  the grep, under the tool-output size limit, no `Output too large`, and fewer hits than the cap.
  There, taught∖seen is a genuine over-teach (for example a dropped `-w` or `-x`).
- Report recall on the visible prefix for truncated outputs.
- Drop the carve-out.
- Rewrite AC-4 as a synthetic COMPLETE-output invocation where the learner over-teaches (a
  `-w`-dropping stub), and require that precision_B falls.
- Pre-register a minimum n ([[#s-n10]]).

**Pattern match:** YES. `impression_bsd_guard_cannot_fire`, and the same shape as r1 #b-2.

### SKETCHY: a whole-tree recursive grep cannot finish inside the learner's 10 s cap on this repo {#s-n1}

**Spec:** 16.1 R1/R3/R4, plan d-1 ("every grep still teaches")
On the project root, `grep -rn X .` and the path-less `grep -rn X` (which walks the cwd) take
103 s. About 68 of about 200 recursive greps in the transcripts are path-less. BSD's walk visits
`.claude`, `.refmatrix` and `.venv-eval` first, so the learner times out, discards everything,
teaches nothing, and burns 10 s of CPU in each of its 2 slots. The timeout is counted, so this is
not silent, but "every grep still teaches" is false for this whole class, and AC-8 (a FIFO) cannot
see it.
**Fix:** Add pruning flags equal to the corpus predicate to the re-run:
- `--exclude-dir` for dot directories and `IGNORE_DIRS`;
- `--include` for the corpus extensions, but ONLY when the caller passed no `--include`, because
  BSD ORs multiple `--include`s and adding them would widen a caller's filter.

This is faithful by construction, since R3 drops those hits anyway. Note that the pattern
`--exclude-dir='.?*'` excluded the `.` operand itself in my run; use `.[A-Za-z0-9_-]*`. Add an AC
with a large out-of-corpus tree placed ahead of `src/`.

### SKETCHY: the plan's `#learner` contradicts 16.1 on cutoffs and on `-e`, and the plan outranks the task {#s-n2}

**Spec:** plan `#learner` bullets 1–2 vs 16.1 R1
The plan still says "Ignored: shaping flags (`-c`, `-l`, `-o`, `-h`, `-A/-B/-C`, `-m`)" and "Kept:
… every `-e` value". 16.1 makes `-m`, `-l` and `-q` CUTOFFS, and kills on more than one `-e`.
CLAUDE.md's source-of-truth order is plan → task, so an implementer who resolves the conflict by
the rules picks the wrong one. That is s-10's definitional defect, restored at the higher level.
**Fix:** Make the plan's bullets match 16.1 R1.

### SKETCHY: 16.1's rg table cannot parse the flags 16.3 feeds it, so every Grep-tool teach dies as `unknown-flag` {#s-n3}

**Spec:** 16.3 R1 table vs 16.1 R1 rg rows and `#r1-unknown`
16.3 always emits `--glob !<d>` and `--max-columns 500`. 16.1's rg rows list only `-g GLOB` and
`-M N`, and an unknown token kills the teach. The same gap covers rg `--type`, `--ignore-case`,
`--max-count` and `-d`/`--max-depth`. The 16.1 table also has no long aliases for grep:
`--ignore-case`, `--recursive`, `--word-regexp`, `--fixed-strings`, `--max-count`,
`--files-with-matches`, `--regexp=`, `--context=` and `-NUM`, all of which BSD grep accepts.
**Fix:** Give each row its long alias (and `=` form). Add an AC that feeds 16.3's rendered argv to
16.1's classifier.

### SKETCHY: the 16.3 `glob` mapping is not the tool's {#s-n4}

**Spec:** 16.3 R1 table (`glob` → `-g GLOB`)
The binary splits `glob` on whitespace, then on commas unless the piece contains braces, and emits
one `--glob` per piece. For `*.ts,*.tsx` or `*.py *.md`, a single `-g` matches nothing, so the
learner teaches nothing while the tool returned hits.
**Fix:**
- Port the split rule, and include it in the binary-extraction fixture.
- Add comma and whitespace glob payloads to AC-1.
- Add a mutation that drops the split.

### SKETCHY: `--bin "$(command -v rg)"` in the bash hook yields `rg`, the agent-bashrc function name {#s-n5}

**Spec:** 16.3 R1
`TEACH_TEMPLATE` is a bash script, and `BASH_ENV` is in the settings env that hooks inherit.
Measured: `bash -c 'command -v rg'` prints `rg`. 16.1 requires `--bin ABS`, so either the learner
rejects every call or it PATH-resolves a name, which is exactly what s-6 forbade. The template's
own header already says "internal tools by absolute path so shell aliases/functions can't alias
them". A test run without `BASH_ENV` passes while production fails.

Separately, the Grep tool runs Claude Code's BUILTIN ripgrep with `--no-config`, not
`/opt/local/bin/rg`, so the "same tool" claim does not hold on this route.
**Fix:**
- Resolve with `type -P rg` or `env -u BASH_ENV`.
- Pass `--no-config`.
- Record the system rg's version against the builtin's in the summary.
- Have the test set `BASH_ENV` to a file that defines `rg()`.

### SKETCHY: the "pinned constants" AC cannot see a Claude Code upgrade {#s-n6}

**Spec:** 16.3 R1 bullet 1, AC-5
AC-5 compares the rendered hook to a checked-in fixture. Nothing re-reads the installed binary, so
"a Claude Code upgrade is a visible diff" is false. The binary auto-updates (`versions/2.1.292`,
installed 2026-10-06). The tool's dynamic exclusions (permission `--iglob` denies,
orphaned-plugin globs and task-output globs) are not constants, and the spec does not mention them.
**Fix:**
- Add a test that re-extracts `Gno` and the `--max-columns` value from `CLAUDE_CODE_EXECPATH` or
  `~/.local/bin/claude`, anchored on content (not minified names), and compares them to the
  fixture. If the binary is absent, skip with a printed reason.
- Name the dynamic exclusions as unmodelled divergence. The deny list is empty here today.

### SKETCHY: store-side idempotence covers `linkage_evidence` only; `facts.log` still grows on every re-teach {#s-n7}

**Spec:** 16.1 R4 "Store-side idempotence", AC-11, plan "bounded on every leg"
`_learn_grep_hits` calls `add_concept`, `upsert_entity` and `link` on every re-teach.
`upsert_entity` appends an `entity` and a `protect` event unconditionally, so a re-taught 200-hit
argv adds roughly 400 or more `facts.log` lines each TTL with zero new information. `facts.log` is
249 MB. AC-11 counts evidence rows only.
**Fix:**
- Short-circuit `_learn_grep_hits` when every `(concept, entity, line)` already exists, before any
  upsert or link.
- Add `facts.log` byte growth = 0 on the second drain to AC-11.

### SKETCHY: the learner and ingest disagree on `kind`, so AC-6's "same entity id" fails for 13 code extensions {#s-n8}

**Spec:** 16.1 AC-6, R4 (`daemon.py` row in Files to modify)
`_learn_grep_hits` uses a hardcoded suffix set (`.py .js .ts .go .rs .java .rb .php .cpp .c .h .hpp
.pseudo`). Sync uses `CODE_EXTS`, which also contains `.sh .bash .zsh .tsx .jsx .sql .kt .swift
.cc .cs .scala .lua .pyi`. Identity is `(partition, kind, name)`, so for example
`scripts/lint-gmd.sh` is taught as a second, PROTECTED `doc` entity beside ingest's `code` one.
AC-6 sees this only if its fixture happens to use one of those extensions.
**Fix:**
- Use `CODE_EXTS`, imported from the new corpus module.
- Run AC-6 over a `.sh` and a `.tsx` file.
- Add a mutation that restores the hardcoded set.

### SKETCHY: slots bound searches, not process starts {#s-n9}

**Spec:** 16.1 R0b, 16.2 R2
Every throttle miss starts a full `rmx` process (`cli_entry` re-exec plus click/rich import,
measured at 0.14 s wall) before the learner can discover `busy`. Each one also writes a `cli.log`
record. Over 1,000 files, `for f in *; do grep x "$f"; done` costs about 140 CPU-seconds of
Python starts.
**Fix:** Gate on the slot in the shim (a cheap `mkdir`-lock or `ls | wc` probe, counted as
`busy` in the `throttled` counter) before spawning. Alternatively, accept the cost and state it,
with a number, in R0b.

### SKETCHY: 16.4's gates have no minimum coverage, and O2 has none at all {#s-n10}

**Spec:** 16.4 R3/R4
- O2: 0 Grep-tool calls in 62 transcripts. 16.3's route is unmeasured here.
- O1: 55 of 2,342 commands (2.3%) are cleanly attributable. 46% contain several grep segments,
  and R3 gives no attribution rule for them.
- recall_B is a MEDIAN per invocation. Up to half the invocations can score 0 (every timeout from
  [[#s-n1]], for example) and the gate still passes.

**Fix:**
- Pre-register a minimum n per oracle, and report n.
- Use micro-averaged recall plus the share of invocations with recall < 1, and count timeouts in
  the denominator.
- Define attribution for multi-segment commands, or exclude them and count them.
- State that 16.3 is measured by its own AC-1 only, or harvest Grep-tool calls from other
  projects' transcripts.

### MEH: "exit 2 teaches nothing" is narrower than `#why-lead`, and is undefined at the cap {#m-n1}

**Spec:** 16.1 R1 "The tool's own exit decides", R4
Measured: BSD grep exits 2 WITH valid stdout hits when one operand is missing or one file is
unreadable. 18% of agent greps discard stderr, so the agent would not even see that there was an
error. At the cap, the child is killed, so its exit is a signal and not 2 or 0, and the rule for
that case is unstated.
**Fix:**
- Teach the parsed hits from exit 2 and log `tool_exit=2`. Alternatively, justify the drop as a
  stated narrowing.
- State that a child killed at the cap teaches.

### MEH: `setsid` needs an EPERM path, and AC-9 has a measured race {#m-n2}

**Spec:** 16.1 R0, AC-9
- `os.setsid()` raises EPERM in a process-group leader. That happens, for example, to a harness
  that spawns with `start_new_session=True`.
- The 0.14 s before `grep_learn` runs is unprotected. A `killpg` 5 ms after spawn killed my probe
  child.

**Fix:** Tolerate EPERM (the process is already a leader). In AC-9, kill only after the learner has
written a "detached" marker.

### MEH: small unbounded legs {#m-n3}

**Spec:** 16.2 R3, 16.1 R7
- The `.rmxgrep-teach/throttled` byte counter has no rotation.
- Stamp files are never pruned (466 today; the cwd in the key multiplies them).
- Every learner adds a `cli.log` record through `cli_entry` (19 MB, no rotation).

Name each one with a bound, or as accepted.

### MEH: 16.1 R7's signature lacks `--retired-env`, which 16.2 R4 passes {#m-n4}

**Spec:** 16.1 R6/R7 vs 16.2 R4
Add the flag to R7, and `reason_extra` to R6's record fields.

### MEH: arm A and `forgone_index_share` need the old `rmx`, not just the old `bin/rmxgrep` {#m-n5}

**Spec:** 16.4 R2/R4
The ping execs `$RMX grep --limit 3`, and does so after `cd "$root"`. Replaying it with today's
`rmx` is not what ran. Specify a `git worktree` plus a venv at the pre-16.2 sha, pinned through
`RMXGREP_RMX`.

`cli.log` shows 31 of 72 recent pings exiting 2, so "taught_invocations B ≥ A" is nearly free.
Report it, and do not call it a gate.

### MEH: the corpus-module claims are wrong in detail {#m-n6}

**Spec:** 16.1 R3, Files to modify (`corpus.py` "moved from `watch.py`"), R7/AC-14
- `load_ignore_spec`, `IgnoreSpec`, `IGNORE_FILE`, `CODE_EXTS` and `DOC_EXTS` live in `ingest.py`,
  not in `watch.py`. They must move too, with `ingest.py` re-exporting them.
- "imports … not the store" is unattainable: `refmatrix/__init__` imports `store`.
- AC-14 imports `grep_learn` in isolation, not the real `rmx grep-learn` entry.
- `is_relevant` tests ABSOLUTE path parts, so a project under a dot-dir or a `build/` ancestor
  rejects every hit. Apply it to the project-relative path.
- The watcher's predicate is not ingest's (`build/`, `dist/`, `.gmd`).

### MEH: route-2 detection in 16.4 is unspecified {#m-n7}

**Spec:** 16.4 R1
"Detected when the grep runs inside a script file the command executes" requires reading the
script at the snapshot. No rule is given for which files count or how their greps are enumerated.

## Verdict {#verdict}

**NEEDS-REVISION.** Of the 23 prior findings, 15 are closed, 6 are partially closed and 2 are open
(b-2, m-5). There are 18 new findings: 1 BULLSHIT, 10 SKETCHY, 7 MEH.

16.1 and 16.2 are close. Approval is blocked by:
- **[[#b-n1]].** 16.4's precision gate is unfalsifiable again, and its independence AC
  contradicts its own oracle rule.
- **The Grep-tool route cannot reach the learner as written.** These are [[#s-n3]] (an unknown
  long flag kills every teach), [[#s-n4]] (the glob split) and [[#s-n5]] (`--bin rg`).
- **m-5.** The commit claims it was addressed, and it was not.

[[#s-n1]] and [[#s-n7]] should be fixed in the same revision. Both are cheap, and both were what
"bounded" and "every grep teaches" claimed to cover.

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 42a5521 (SPEC re-review r2, plan-16 tasks 16.1-16.4, pre-implementation; written 2026-10-07T00:25:18-0700) | 2026-10-07 | Todd Holley / Opus 5.5 / orchestrator | NEEDS-REVISION | 18 new (1B/10S/7M); prior 23: 15 closed, 6 partial, 2 open | [[bsd-plan16-spec-rereview-42a5521]]: b-1/b-4 closed and verified against code (is_relevant rejects dot segments; store_root table matches learn_switch/learn_queue/drain); setsid measured to escape the caller pgid and survive killpg; `printf '%s\0'` keys verified in /bin/sh; the BSD 2.6.0 flag table true on every row I could run. BULLSHIT: 16.4 precision_B's `unseen-but-verified` carve-out re-creates b-2's tautology (arm B runs ON the snapshot, so every unseen pair verifies), and AC-4's edited-line proof contradicts R3's hash rule. SKETCHY: whole-tree `grep -r` takes 103 s here, so the 10 s learner times out on ~1/3 of recursive greps; plan #learner still calls -m/-l "ignored", contradicting 16.1; 16.3 emits --glob/--max-columns, which 16.1's rg table does not know (unknown-flag kills every Grep teach); the tool splits glob on whitespace/commas; `command -v rg` in the bash hook prints `rg` under BASH_ENV; the constant pin never re-reads the binary; facts.log still +2 events/file per re-teach; learner `kind` set != CODE_EXTS splits .sh/.tsx entities; slots cap searches, not 0.14 s Python starts; O2 = 0 Grep-tool calls in 62 transcripts, O1 cleanly attributable 55/2342 (2.3%), recall is a median with no min n. m-5 (cli.py:6335 swallow) still open despite "all 23 addressed". No code, no mutations, no live-store access. |
```

IMPRESSIONS.md bullets:

```
- plan-16 r2 (42a5521): an oracle fix can re-import the tautology through a CARVE-OUT ("unseen-but-verified" re-reads what the learner itself produced on the same snapshot). When an oracle gains an exception class, ask whether membership in that class is computed from the thing under test.
- plan-16 r2: cross-spec seams are where revisions break — 16.3 emits long rg flags that 16.1's table does not parse, and a bash hook's `command -v` returns a FUNCTION name under BASH_ENV. Check every producer/consumer pair across task specs, not each spec alone.
- plan-16 r2: "all N findings addressed" in a commit subject is a claim; m-5 was not touched. Always tabulate prior ids against the diff.
```
