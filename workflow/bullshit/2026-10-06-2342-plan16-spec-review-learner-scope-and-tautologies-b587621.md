---
gmd: "0.1"
id: bsd-plan16-spec-review-b587621
title: "plan-16 spec review: the learner teaches outside the corpus, three acceptance gates cannot fail, and the off switch can be checked on the wrong root"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim
task: spec-review-16.1-16.4
round: 1
tags: [bsd, audit, spec-review, grep, drop-in, learning, hooks, measurement]
---

# ch-bsd spec review of plan-16 (pre-implementation) {#root}

**Commit:** `b587621b0e1372d00c0934f1dc62ab75535ddb72`, *docs(plan-16): task specs 16.1-16.4;
learner is not a verb; BASH_ENV route; interim plain mode*
**Branch:** `bsd-r1-remedy` (shared tree; I wrote only under `workflow/bullshit/`, ran no
mutations and touched neither `src/` nor `tests/`)
**Audit written:** 2026-10-06T23:42:52-0700
**Scope:** `workflow/plans/plan-16-invisible-grep-shim.md` and
`workflow/plans/plan-16-invisible-grep-shim-tasks/task-16.{1,2,3,4}-*.md`, checked against
`bin/rmxgrep`, `bin/rmxrg`, `search_hooks.py`, `hooks.py`, `learn_queue.py`, `learn_switch.py`,
`daemon._drain_learn_queue` / `_learn_grep_hits`, `store.add_evidence` / `grep_evidence`, `cli.py`
(grep, learn status), the tests the specs name, `/usr/bin/grep` (BSD 2.6.0-FreeBSD), `rg` 15.1.0, and
the Claude Code binary's Grep-tool code.

I did not reopen the user's decisions (d-1, d-2, d-3). Each finding below is about whether the specs
implement those decisions faithfully and completely. Many things hold up, and I checked each one:
`verbs.VERBS == mcp.TOOLS` (`test_verb_parity.py:100`); `_index_may_answer = not paths`
(`cli.py`), which matches the claim that index answers reach only path-less calls; the BASH_ENV
route for child scripts (`bash -c 'declare -f grep'` resolves to `$HOME/refmatrix/bin/rmxgrep`); the
interim plain-mode log (`63 passed`); the flag-stripping ping (a live probe built
`grep --limit 3 foo a.txt` from `-i foo a.txt`); and absolute hits being *accepted* by
`_learn_grep_hits` (it relativises them against `project_root`).

rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: related-to -> [[impression_bsd_guard_cannot_fire]]
rel: related-to -> [[impression_bsd_substring_signature_widens]]

## Findings {#findings}

### BULLSHIT: the learner teaches outside the corpus, as protected entities {#b-1}

**Targets:** 16.1 R1/R4 (and the plan's `#learner`)
**What:** The learner re-runs the caller's real `grep -r`. BSD grep ignores `.gitignore`. Today's
floor runs `rg -nH …` (`cli.py`, `cmd = ["rg", "-nH", case_flag, "--no-heading"]`), and `rg` does
respect `.gitignore`. That file lists `.refmatrix/`, `.venv-eval/`, `eval/datasets/` and
`__pycache__/`.
**Why it is bullshit:** `_learn_grep_hits` calls `upsert_entity(..., protected=True)` for every
hit's file and applies no relevance filter (`daemon.py:4253-4296`). A faithful
`grep -rn foo .` from the project root therefore teaches:
- site-packages lines under `.venv-eval/`;
- `.refmatrix/query.log` and `cli.log`, which contain the pattern itself;
- binary catalog matches.

Each of these becomes a *protected* entity, and `prune_noise` never removes it. A probe in my
scratchpad matched `./st/.refmatrix/catalog.duckdb` on the first line. The 500-hit cap is applied in
walk order, so out-of-corpus hits can crowd every in-corpus hit out of the cap. This breaks
`feedback_operational_content_not_in_graph` on the default path, and it is a regression against
the floor it replaces.
**Fix:** Filter hits through the same relevance predicate ingest and the watcher use
(`watch.is_relevant` plus the store's watch roots). Filter BEFORE the cap. Count the dropped hits as
`out-of-corpus` in the log record. Add an AC where a fixture containing `.refmatrix/` and
`.venv-eval/` text hits teaches none of them.
**Pattern match:** YES. This is the sibling-render-path shape: the same rule ("which files are the
corpus") was enforced on one engine and not on the other.

### BULLSHIT: 16.4's precision_B = 1.000 and recall_B ≥ 0.99 cannot fail {#b-2}

**Targets:** 16.4 R3
**What:** The spec defines the oracle as *"the caller's own command matches (real tool, same argv,
run against the snapshot)"*.
**Why it is bullshit:** That is exactly the computation the learner performs: the same binary, the
same matching argv and the same files. To compare a `-c`/`-l`/`-o`/`-q` invocation at line level,
the harness has to canonicalise it, and the only canonicaliser is the learner's own classifier.
Both thresholds hold by construction, and the "must be 1.000" gate is decorative. The same applies
to recall, except under the cap.
**Fix:** Use an oracle that is independent of `grep_learn`:
- (a) the agent's recorded `tool_result` in the transcript, for invocations whose output is
  line-addressed (`-n` with filenames), with a file-hash check that the line still matches; and/or
- (b) the caller's argv run VERBATIM and parsed only where its output format already carries
  `file:line`.

Report each oracle's coverage. Keep the thresholds, and pre-register them against that oracle.
**Pattern match:** YES (`impression_bsd_guard_cannot_fire`).

### BULLSHIT: 16.3 AC-1's control is the learner's own argv, and the field table is not the Grep tool's {#b-3}

**Targets:** 16.3 R1 table, AC-1, AC-2
**What:** AC-1's control is `rg -nH --null <mapped argv>`. That is the same argv the mapping
produces, so a mapping that omits something the Grep tool passes passes the test.
**Evidence (the Claude Code binary on this machine):** The Grep tool builds
`xe=["--hidden"]`, pushes `--glob !<vcs dir>` for each entry in its VCS list, then
`--max-columns 500`, `-U --multiline-dotall`, `-i`, and so on. Its input destructures
`head_limit`, `offset`, `context`, `-o`, `-n`, `-i`, `multiline`, `output_mode`, `glob`, `type` and
`path`. Against the spec:
- **`--hidden` is missing from the table.** Every dotfile or dot-dir hit the tool returned
  (`.claude/`, `.github/`) is never taught.
- **`offset`, `context` and `-o` are absent.** Under R1's own rule ("an unrecognised input field …
  teaches nothing"), every Grep call that carries them is killed.
**Fix:**
- Map `--hidden` and the VCS `--glob !…` set.
- Add `offset`, `context` and `-o` as shaping inputs.
- Make AC-1's control the tool's own captured `tool_response` (the files and lines it returned),
  not `rg` on the mapped argv.
- Add an AC with a hit under a dot-directory.

### BULLSHIT: the learn switch can be read on the wrong root, and AC-7 cannot see it {#b-4}

**Targets:** 16.1 R3, R5, R6, AC-7, AC-10
**What:** `learn_switch.store_marker(root)` is `root/learn.off`, and `learn_queue.queue_path(root)`
is `root/learn.queue.jsonl`. In both, `root` is the STORE root (`<project>/.refmatrix`). The daemon
drains `self.root`, which is `Path(root).resolve()` of the store dir. The spec says
`learning_enabled(root)` and `enqueue(root, …)` in the same breath as
`<root>/.refmatrix/grep-learn.log`, where `root` is the project root.
**Why it is bullshit:** If the learner passes the project root:
- the queue goes to `<project>/learn.queue.jsonl`, which no daemon drains;
- `<project>/learn.off` never exists, so a store marker is ignored.

AC-7 tests only `RMX_LEARN=0`, and the env value decides before `root` is read, so AC-7 passes on
the wrong root. On the 16.3 route, `TEACH_TEMPLATE` has no switch check of its own, so the learner's
check is the only one. The rule being broken is the user's own: "the learn switch is the only off
switch".
**Fix:**
- Name the root precisely: the store root for `learn_switch` and `learn_queue`, and the store root
  for the log too.
- Add AC-7b: a per-store `learn.off` marker with `RMX_LEARN` unset gives `skipped` and no queue
  line.
- Make AC-10 drain through a `Daemon` built on the store root, not one built from the learner's
  return value.

### BULLSHIT: "bounded on every leg" leaves out the store, where re-teaching grows evidence without limit {#b-5}

**Targets:** 16.1 R4 (and the plan's `#learner` "It is bounded")
**What:** `Store.add_evidence` is an unconditional `INSERT` (`store.py:5216`) and appends a
`facts.log` event every time. `learn_queue.read_rotated` dedupes `(file, line)` only *within one
drained batch*.
**Why it is bullshit:** The plan raises the per-call teach from today's ping (`--limit 3`) to 500,
and makes it fire on every observed grep. A repeated argv is re-taught after every TTL (5 min), and
each repeat adds up to 500 duplicate `linkage_evidence` rows. Duplicate learned rows are the
documented root cause of bug-058 (`_index_may_answer`'s docstring: "1000 rows, each line up to
3x"). None of 16.1's bounds or ACs sees this.
**Fix:** Dedupe at `_learn_grep_hits`: skip an existing `(concept, entity, line)`, or upsert it. Add
an AC: teaching the same argv twice, with the TTL at 0 and a drain between, leaves the evidence row
count unchanged.

### SKETCHY: "own process group" is promised, and the spec's mechanism does not deliver it {#s-1}

**Targets:** the plan's `#shim`, and 16.2 R2/AC-2
**What:** The plan says the child is "detached … with its own process group". 16.2 R2 says
"background, disowned". I measured today's identical construct, `( … ) >/dev/null 2>&1 &` in
`#!/bin/sh`: the ping's pgid was 8112, equal to the pipeline's pgid, and the caller shell's was 8105.
macOS has no `setsid(1)`.
**Risk:** If a harness timeout or interrupt runs `killpg` on the command's group, it kills the
learner before it writes its log record. R6's "exactly one record per call" then fails silently.
**Fix:** `grep_learn` calls `os.setsid()` as its first statement, and every child it starts uses
`start_new_session=True` and `close_fds`. Add an AC: the learner's pgid differs from the caller's,
and it survives a `killpg` of the caller's group and still logs.

### SKETCHY: learner fan-out has no concurrency bound {#s-2}

**Targets:** 16.1 R4, 16.2 R2
Via the BASH_ENV route, `for f in *; do grep x "$f"; done` produces N distinct argv, so N throttle
misses. Each miss starts a Python learner plus a grep, each allowed up to 10 s, with no in-flight
cap. **Fix:** a lockfile or semaphore (for example at most 2 in flight per store), with every skip
counted as `reason=busy` in the log.

### SKETCHY: the throttle key leaves out the cwd, and throttled calls are never counted {#s-3}

**Targets:** 16.2 R2/AC-5
**What:** The stamp is `printf '%s' "$*" | cksum` (`bin/rmxgrep:119`, `bin/rmxrg:82`).
- The same relative argv (`grep -rn foo .`) run from two directories is a different search, but
  teaches only once per TTL.
- `"a b"` and `a b` collide.
- A throttled call leaves no record, so neither `learn status` nor 16.4 can see how many greps the
  throttle dropped (an uncounted skip on a memory path).

**Fix:** Key the stamp on `$PWD` plus a NUL-joined argv. Count throttle hits, for example with a
counter file in the stamp dir that `learn status` reads.

### SKETCHY: rmxrg has no learn-off exit, so "keep the four early exits exactly as they are" is false {#s-4}

**Targets:** 16.2 R1/AC-4, and the plan's `#shim` ("Unchanged: … the learn toggle")
`bin/rmxrg` has three exits: outside a project, rmx missing, and a piped stdin. There is no
`RMX_LEARN`/marker branch, and no test covers one. `test_learn_toggle_hook.py` tests only rmxgrep and
the rewriter. With learning off, the BASH_ENV `rg()` still writes a stamp and spawns a process. AC-4
must name both shims, and R1 must say "add" for rmxrg.

### SKETCHY: the route map leaves out Claude Code's own `grep()` function {#s-5}

**Targets:** 16.2 `#routes`, the plan's d-1 claim "every grep still teaches", 16.4 R1
**What:** In the top-level Bash-tool shell, `type grep` shows Claude Code's snapshot function. It
runs the embedded **ugrep**: `exec -a ugrep "$CLAUDE_CODE_EXECPATH" -G --ignore-files --hidden -I
--exclude-dir=.git …`. That function shadows agent-bashrc's `grep()`. `rg` is still `rmxrg`, and a
child `bash -c` sees rmxgrep.

Some greps are never rewritten:
- non-head positions (`if grep -q …`);
- any command matching the guard's `\bgit\b` exemption, which passes the whole command;
- any command containing `<<`.

These run ugrep, which is neither the shim nor `/usr/bin/grep`, and they are not observed.
**Fix:** This does not reopen d-3. Document the third route. Have 16.4 classify each transcript
command by which route actually ran it, and report the unobserved share.

### SKETCHY: the learner entry point does not carry the binary {#s-6}

**Targets:** 16.1 R1 vs R7, 16.2 R2
R1 says the learner execs `$REAL` (`RMXGREP_GREP` / `RMXRG_RG`), but R7's
`rmx grep-learn --tool {grep,rg} --cwd DIR` carries no binary. This machine's PATH contains `./` and
an empty entry, so a learner that re-resolves `grep` from the caller's cwd can run a different
program. **Fix:** add `--bin ABS` and have the shim pass the resolved `$REAL`.

### SKETCHY: "spelling is the identity" splits entities whenever the cwd is reached through a symlink {#s-7}

**Targets:** 16.1 R2/AC-4/AC-10
**What:** R2 builds `normpath(join($PWD, file))` from the logical `$PWD`. The daemon passes
`Path(self.root).parent`, where `self.root` has been `resolve()`d.
**Why it matters:** When `relative_to` raises `ValueError`, `_learn_grep_hits` falls back to
`rel = str(ap)`. The result is a NEW protected entity named by its absolute path, separate from the
ingested `src/x.py`. On macOS `/tmp` is a symlink to `/private/tmp`, so test fixtures are prone to
this. AC-4 checks only that paths are "absolute".
**Fix:** Add an AC asserting that the taught entity id equals the ingested file's entity id, with
the cwd reached both directly and through a symlinked directory.

### SKETCHY: matching rules are dropped at the queue boundary {#s-8}

**Targets:** 16.1 R3/AC-10, the plan's `#learner` Goal 2
**What:** The queue record is `{pattern, hits}` and the concept is `query/<pattern>`, so
`-i foo`, `foo`, `-F 'a|b'` and `-E 'a|b'` all coalesce into one concept. Explicit `rmx grep`
finds concepts by `ILIKE` on the name (`store.grep_evidence`) and then verifies under its own
rules, which are case-sensitive since bug-077.
**Consequence:** The case-variant lines a `-i` search taught are filtered out at read time.
AC-10 as written ("rmx grep PATTERN answers with the taught lines") can pass on a plain pattern
alone.
**Fix:** Add `-i` and `-F` cases to AC-10, or record the matching flags with the queued record.

### SKETCHY: AC-1's RED proof has no power, and the mutation list misses the original defect {#s-9}

**Targets:** 16.1 AC-1 and the `#tests` mutations
**What:**
- "Every case is RED before the implementation" is satisfied by an `ImportError` alone.
- Each case needs proof of power: the control *with* the flag must differ from the control
  *without* it on that fixture.
- The mutation "drop the `-i` row" makes `-i` an unknown flag, which kills the teach, so AC-1 fails
  for the wrong reason.
- The defect this plan exists to remove is "`-i` moved from keep to drop", and that mutation is not
  listed. Add it, plus "`-F` keep→drop".

### SKETCHY: the flag table has rows that are false on this machine, and a definitional contradiction {#s-10}

**Targets:** 16.1 R1 table, `#why-lead`, R1-stdin
Rows that are false, checked against `/usr/bin/grep --help`, `man grep` and live runs:
- `-P` (keep) and `-T` (drop) are `invalid option`, exit 2, in BSD grep. Because `-T` is a drop
  row, the learner teaches lines where the caller only got an error.
- `-z` (keep) is `--null-data`: the whole file becomes one NUL-terminated record and every hit is
  line 1 (measured). That breaks R2.
- `-Z` is `--decompress` in BSD grep, not `--null`.
- `-J`, `-X`, `-M`, `-O`, `-S`, `-p`, `-D`, `-d` and `-I` are not in the table.
- `-f` is a keep row in R1 but a kill reason (multi-pattern) in R3.

The definitional contradiction: `-m N` ("Stop reading the file after num matches"), `-q` and `-l`
are match CUTOFFS, not shaping flags. Dropping them teaches lines the caller never matched, which
contradicts `#why-lead`'s "no more and no fewer". Either redefine "faithful" or keep the cutoff.

R1-stdin is grep-only. A path-less `rg` with stdin on `/dev/null` (the agent shell's stdin, char
device `0x3000002`) searches the cwd, so applying `no-operand` to rg would kill the most common
agent form. State the rule per tool. R1-table already says the table is "a starting point", so this
is not filed as BULLSHIT.

### SKETCHY: 16.2 R5 misses tests that pin rich mode and RMXGREP_TEACH, and d-2 points sandboxes at the deploy rmx {#s-11}

**Targets:** 16.2 R5
Tests not listed:
- `test_rmxgrep.py::test_teach_disabled_writes_no_stamp`, which directly contradicts d-2;
- `::test_auto_mode_piped_stdout_teach_ping_writes_throttle_stamp`;
- `test_grep_stdin_dialect.py::test_rmxrg_injects_ere`, `::test_rmxrg_respects_fixed_strings`
  and `::test_bre_fallback_preserves_stdin_for_the_real_tool` (rich-mode branch, `RMXGREP_MODE=rich`);
- the docstrings in `test_rewriter_wrapper_resolution.py` and `test_grep_argv_order_e2e.py`.

Tests that set `RMXGREP_TEACH=0` "because no daemon in this sandbox" (`test_rmxgrep.py:62-65, 134,
157, 190`) will spawn the learner once d-2 lands. If `RMXGREP_RMX` is unset, that learner is the
DEPLOY `rmx` on PATH (CLAUDE.md hard rule). Require such tests to pin `RMXGREP_RMX` or `RMX_LEARN=0`.

### SKETCHY: sibling doc and help surfaces, and a `--check` the code cannot do yet {#s-12}

**Targets:** 16.2 R4, 16.3 R2/AC-4, 16.2 `#deploy`
**Surfaces missed:**
- `README.md:209-213` (rich/plain mode prose), `README.md:257` (`RMXGREP_MODE` env block) and
  `README.md:412`;
- the install-hooks `--help` in `cli.py` ("(+ RMXGREP_MODE)");
- `rmx grep`'s docstring in `cli.py` ("Drop-in for grep/rg … so a rewrite hook");
- the `learn status` area docstring in `cli.py` (PreToolUse rewrite);
- `docs/ARCHITECTURE.md:398`;
- `workflow/development_resources.md:36` (`RMXGREP_MODE=rich` "the only value").

`cli.py` line numbers moved under me (9179 → 9208), because a parallel agent is editing the file.

**The `--check` gap:** `hooks.check()` (`hooks.py:587`) compares neither the agent-bashrc section
nor the `settings.local.json` env block. R4's "`--check` reports `RMXGREP_MODE` as drift" is new
code, and the spec has to say so.

**Deploy note:** It says to delete `"RMXGREP_MODE": "rich"`, but the live value in both files is now
`"plain"`. It also omits that the bashrc is refreshed only by `install-hooks --force`.

### SKETCHY: 16.4 corpus and cost-side pitfalls {#s-13}

**Targets:** 16.4 R1/R2/R3
- **The cwd can be wrong.** The message `cwd` is not the grep's cwd after `cd sub && grep …`.
  Parse or count those cases.
- **"Imported, not re-implemented" is impossible as written.** `REWRITER_TEMPLATE` carries
  `@LEARN_*@` placeholders and is not importable, and the git exemption and the `<<` skip live in
  the bash guard. Specify `render_scripts()[REWRITER_NAME]` exec'd, plus the guard regex.
- **Subagent transcripts** live under per-session `subagents/` directories.
- **`forgone_index_share` is train-on-test.** It is computed after arm B taught the same corpus.
  The cost is what the pre-16.2 rich path answered from the index, so replay arm A's sha in rich
  mode on the snapshot store.

### MEH: the plan text is stale and contradicts the specs {#m-1}

**Targets:** the plan's status header and `#tasks` table
- The header still says "No task specs yet".
- The `#tasks` row for 16.1 says "the `grep_learn` verb + `rmx grep --learn-only`" and "bounded
  under a stalled daemon". `#learner` and 16.1 R7 say the opposite: a hidden `rmx grep-learn`, not a
  verb, that never touches the daemon.

### MEH: the trigger for d-2's `learn status` line is undefined {#m-2}

**Targets:** 16.2 R3/AC-6
`learn status` runs in a different process from the grep. Should it read its own env, or recent log
records? Is `RMXGREP_TEACH=1` "set"? Define both.

### MEH: binary files and the output memory bound {#m-3}

**Targets:** 16.1 R2/R4
- `Binary file X matches` lines under `-nH --null` need a counted parse outcome. 16.1 has no AC
  for them.
- AC-6's exact `truncated=45` forces a full read. Require a streaming parse, so that output volume
  inside the 10 s cap is not buffered without limit.

### MEH: the overhead gate passes trivially with a stand-in {#m-4}

**Targets:** 16.2 AC-8
Today's shim with an `exit 0` stand-in measured a delta of p50 8.4 ms and p95 10.7 ms over bare
grep (100 runs). That already passes the ≤15/≤40 ms bounds. Require the REAL learner spawning on
every run, which is where the CPU contention lives.

### MEH: an existing silent swallow on the teach path is not owned by any task {#m-5}

**Targets:** the plan's `#explicit` (out of scope)
The delegate branch of `rmx grep` (`cli.py`, near `_broker_learn_from_grep(_r, pat, hits[:200])`)
ends in `except Exception: pass`. That is a memory path (CLAUDE.md#no-silent-failures). Log it in
the bug registry even though the plan leaves it out of scope.

## Verdict {#verdict}

**NEEDS-REVISION.** 23 findings: 5 BULLSHIT, 13 SKETCHY, 5 MEH.

The direction is sound, and the plan's factual claims about today's behaviour mostly check out.
Four problems block approval:
- the learner's corpus is wider than the store's ([[#b-1]]);
- two measurement and acceptance gates are tautologies ([[#b-2]], [[#b-3]]);
- the off-switch AC cannot detect a wrong root ([[#b-4]]);
- the store-side growth leg is unbounded ([[#b-5]]).

Revise 16.1, 16.3 and 16.4 for these, then re-review before `approved`.
