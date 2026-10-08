---
gmd: "0.1"
id: bsd-plan16-spec-review-r3-c8278b1
title: "plan-16 spec review r3: 16.1-16.4 close almost every r2 finding, but 16.5 deletes the delegate without routing rmx's own options or the path-less flags it served, and 16.4's historical oracle is rmx's own rendering"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim
task: spec-review-16.1-16.5
round: 3
tags: [bsd, audit, spec-review, grep, drop-in, learning, hooks, measurement]
---

# ch-bsd spec review of plan-16, round 3 (pre-implementation) {#root}

**Commits reviewed:** `659c192` (revision 3 of 16.1-16.4 and the plan) and `c8278b1` (task 16.5).
HEAD `c8278b172f5603a5d967bc4aca8c5b1972175173`, branch `bsd-r1-remedy`.
**Audit written:** 2026-10-07T01:40:51-0700
**Method:** I read the five specs and the plan, and checked them against the code at HEAD
(`cli.py` `grep()`, `_split_grep_argv`, `_grep_delegate`, `_grep_rg_fallback`, `telemetry.py`
`ANSWERED_BY`, `watch.py`, `ingest.py`, `bin/rmxgrep`, `hooks.py:926`, `docs/agent-doc-primer.md`).
I also ran live probes in my scratchpad:
- BSD grep 2.6.0-FreeBSD: R1b's pruning flags, run on scratch trees and timed on this repo;
- ripgrep 15.1.0: globs on explicit file operands;
- `type -P rg` under `BASH_ENV`;
- a Python content scan of the Claude Code binary (`versions/2.1.292`, 235 MB);
- a heuristic scan of this project's 64 transcripts (15 top-level, 49 subagent).

Nothing in `src/`, `tests/`, the live store, INDEX.md, IMPRESSIONS.md or last_run.log was touched.
The user's decisions are not reopened: d-1, d-2 and d-3, the kept precision gate, and 16.5 option 1.

rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[bsd-r1-remedy-r4-4d54f6a]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]
rel: contradicts -> [[claude#no-silent-failures]]

## Live evidence {#evidence}

- **R1b pruning, BSD grep 2.6.0.** `--exclude-dir='.[A-Za-z0-9_-]*'` does NOT exclude the `.`,
  `..`, `../`, `./src` operands, or a path-less `-r`. It does exclude an explicitly named `.hid`
  operand, which R3 would drop anyway. The old `.?*` form searched only `./top.py`, because
  `--exclude-dir` also matches `fts_path` and `*` crosses `/`. `--exclude-dir=build` leaves the
  following alone: an absolute or relative operand THROUGH a `build/` ancestor, and a cwd inside
  `build/` with `.` or no operand. So 16.1 AC-5's ancestor case holds.
  - `--include` also filters named FILE operands, with or without `-r`. That is harmless, because
    R3 drops those files too.
  - **Last match wins between `--include` and `--exclude`:** `--exclude='*.md' … --include='*.md'`
    prints `d/a.md`, and the reverse order does not. See [[#s-r3-1]].
- **Timing.** The pruned whole-tree `grep -rnH --null` on this repo, at the project root (dot-dirs,
  `IGNORE_DIRS`, and `--include` for all 31 `SUPPORTED_EXTS`), takes **0.08 s** (`learn_switch`,
  50 hits) and **0.13 s** (`-i error`, 2,495 hits). r2 measured the unpruned walk at 103 s.
- **rg 15.1.0:** `rg --glob='*.py' needle d/a.md` and `--glob='!*.md' … d/a.md` both print the `.md`
  hit, so globs do not apply to explicit file operands.
- **Hook rg.** With `BASH_ENV=~/.claude/agent-bashrc.sh`, `type -P rg` prints `/opt/local/bin/rg`,
  while `command -v rg` prints `rg` (the type is `function`). With `PATH=/usr/bin:/bin`,
  `type -P rg` prints nothing, rc 1.
- **Claude Code binary (2.1.292).**
  - `"--max-columns","500"` occurs exactly once: `for(let Rn of Gno)Ne(`!${Rn}`);if(xe.push("--max-columns","500")…`.
  - A member-anchored search for `".git",".svn"` finds THREE arrays: `Gno=[…6…]` (the Grep tool),
    `fEr=[…6…]` (the ugrep shell function), and a different 8-member
    `[".git",".hg",".svn",".jj",".sl",".bzr","_darcs","CVS"]`.
  - The glob split keeps a piece whole only when it contains BOTH `{` and `}`.
  - When `path` is a single FILE, the tool deletes its `--glob` args and matches the globs itself
    (minimatch, `dot:true`). It returns `[]` on a mismatch, and returns `[]` whenever `type` is set.
  - `head_limit` defaults to `zno=250`, and the result carries `with pagination = …`.
  - A Python scan of the 235 MB binary takes **33 s**.
- **Transcripts (heuristic regex over Bash `tool_use`).**
  - 2,003 commands with a grep/rg segment (3,163 segments).
  - Segments containing a quote: 1,883 commands. With `$`/backtick: 117. With an unquoted glob: 109.
    Inside a `for`/`while`/`xargs` loop: 134.
  - **274 of 3,163 segments repeat the same cwd and text within 5 minutes**, which is the throttle
    TTL. 64 commands contain an identical segment twice.
  - "Complete-ish" invocations (one segment, no pipe after it, no heredoc, no `Output too large`,
    a `file:N:` line in the result): **37**. **28 of the 37 carry rmx rendering markers**
    (`# rmx grep fallback via rg`, `query/`, `[mentions]`). Samples also show OTHER commands'
    output (`ls -la`) in the same `tool_result`.
  - Grep-tool calls: 0. Span: 2026-09-06 to 2026-10-07.
- **Code facts.**
  - `rmx grep` owns these click options: `-f/--flags`, `--limit`, `-k/--kind`, `--linkage`,
    `--regex/--substring`, `--learn/--no-learn`, `--via-replica`, `--fallback`.
  - `-f` is grep's `-f FILE`.
  - `_grep_delegate` runs **rg first** and, for a path-less call, appends `_root().parent`.
  - The `\|`-family BRE refusal (`cli.py:6132-6144`) runs before the path-less/pipe/named split.
  - `telemetry.ANSWERED_BY = ("index","floor","dropin","stdin","none")`.
  - `bug-076` and `bug-078` are index-read rows, and `bug-077` is half index and half floor.

## Status of prior findings {#prior-status}

### r2 findings {#status-r2}

| id | status | evidence |
|---|---|---|
| b-n1 carve-out tautology | **closed** | 16.4 R3 scores precision only on complete invocations and has no carve-out. AC-4 is a `-w`-dropping stub on a synthetic complete invocation, so it can fail. A mutation restores the carve-out. The oracle's own validity is new: [[#s-r3-6]] |
| s-n1 whole-tree timeout | **closed** | R1b is in place. Probes: `.`/`..`/`./src` are not excluded, the `build` ancestor is safe, 0.08–0.13 s against 103 s. AC-6 has RED. New residual: [[#s-r3-1]] |
| s-n2 plan contradicts 16.1 | **closed** | Plan `#learner` defers to 16.1 R1 and lists the cutoffs and kill rows |
| s-n3 long flags | **closed** | Every row carries its long and `=` forms. AC-1b feeds 16.3's argv through the classifier, with a mutation. Residual table gaps: [[#m-r3-2]] |
| s-n4 glob split | **closed** (detail) | Ported, with AC-3 RED and a mutation. The binary needs `{` AND `}`, the spec says `{`: [[#m-r3-3]] |
| s-n5 `command -v rg` | **closed** | `type -P` verified under `BASH_ENV` (`/opt/local/bin/rg`). `env -u BASH_ENV`, `--no-config`, AC-5b with an `rg()` file. The empty-result case is unspecified: [[#m-r3-3]] |
| s-n6 pin cannot see upgrade | **partially closed** | Live re-extraction is specified. The `--max-columns` anchor is unique. The member anchor is ambiguous across 3 arrays, and costs 33 s per run: [[#m-r3-3]] |
| s-n7 facts.log growth | **closed** | R4 all-present short-circuit before any write. AC-12 checks `facts.log` bytes, with a mutation |
| s-n8 kind split | **closed** | `kind` from `corpus.CODE_EXTS`. AC-7 checks `.py`/`.sh`/`.tsx`, with a mutation |
| s-n9 process starts | **closed** | Slot dirs counted in the shim before the spawn, with `busy` counted (16.2 R2, AC-6). Residual: [[#m-r3-1]] |
| s-n10 min n / O2 | **closed** in text | n ≥ 30 or `insufficient-n`, micro averages, timeouts in the denominator, multi-segment commands excluded and counted, O2 through 16.3 AC-1. New: [[#s-r3-7]], [[#s-r3-8]], [[#s-r3-9]] |
| m-n1 exit-2 rule | **closed** | Exit 2 with hits teaches. Killed-at-cap teaches. A timeout does not. AC-4 |
| m-n2 EPERM / race | **closed** | EPERM tolerated. AC-10 kills only after the `.detached` marker |
| m-n3 small legs | **closed** | R9 bounds each leg, and the `cli.log` gap goes to the registry. New unbounded leg: [[#m-r3-1]] |
| m-n4 `--retired-env` | **closed** | In R7, and `reason_extra` in R6 |
| m-n5 old rmx | **closed** | Worktree plus venv pinned through `RMXGREP_RMX`. `taught_invocations` is reported, not gated |
| m-n6 corpus module | **closed** | Moves from `watch.py` AND `ingest.py`. The predicate takes the project-relative path. AC-14 uses the real entry. The unattainable import claim is restated |
| m-n7 route-2 rule | **partially closed** | Defined as a record whose argv appears in no top-level segment. Text equality makes every expanded argv look like route 2: [[#s-r3-7]] |

Tally: **15 closed, 3 partially closed, 0 open.**

### r1 findings left partial or open by r2 {#status-r1}

| id | status | evidence |
|---|---|---|
| b-2 tautological oracle | **closed** | Through b-n1 |
| b-3 Grep-tool argv | **partially closed** | s-n3/s-n4/s-n5 are closed. The single-file `path` branch and the default `head_limit` 250 are not modelled: [[#s-r3-10]], [[#m-r3-3]] |
| b-5 store growth | **closed** | Through s-n7 |
| s-2 fan-out | **closed** | Through s-n9 |
| s-6 binary | **closed** | Shims use `command -v` under sh (absolute). The hook uses `type -P` |
| m-1 stale plan | **partially closed** | `#learner` is fixed. Still stale: "Next gate … (16.1–16.4)", and an out-of-scope bullet that contradicts 16.5: [[#m-r3-6]] |
| m-5 delegate swallow | **closed** | `dffa2df` replaced the `except: pass` with a named stderr line, and bug-082 is logged. 16.5 R4 deletes `_grep_delegate` entirely |

### r4 code-audit items that 16.5 claims to supersede (`dffa2df` message) {#status-r4}

| r4 item | covered by 16.5? | note |
|---|---|---|
| #b-2 `-c` second walk | **yes** | Named paths go to the real grep. `argv_count_rows`/`_walk_files` are deleted. R5 has cases for the binary file and the unreadable subdir |
| #b-3 `./sub sub` | **yes** | R5 has the case |
| #b-4 `-l`/`-L` exit 2 | **partial** | R5 lists only `-l alpha f0.txt nosuch.txt`. r4 quoted the `-L` row too (sibling pattern): [[#m-r3-4]] |
| #m-4 `-A/-B/-C`, dotfiles | **partial** | Named `-A 2` is in R5, but the dotfile walk row is not. The path-less `-A` is orphaned: [[#b-r3-2]] |
| `_grep_stdin_addendum` MEH | **yes** | Deleted |
| bug-081 | **partial** | Named paths are fixed by R1. On the path-less read it is fixed only on an index MISS, and the `\|` refusal still runs first: [[#s-r3-2]] |
| r4 survivors (`bsd-r4-mutations.log` pass 2 lists 19, not 13) | **partial** | M14, M15, M19 and M21 die with deleted code. M7's class (the case letters of the grep-only floor) MOVES to 16.5's new grep floor, and no mutation is pre-registered for it ([[#b-r3-2]]). The index-path survivors (M1/M1b/M1e/M2b/M3/M3b/M3c/M9/M11/M11b) are on code 16.5 keeps, and belong to the r5 code audit of `dffa2df`. M26–M29 belong to 16.2, whose AC-5 has no UNREADABLE-marker case for `rmxrg` (M29) |

bug-081 is now anchored to a concrete task spec (16.5 R5/AC-1 cases), so under rule 9 it is an
**active deferral (MEH)**, not an unanchored one. It stays live in explicit `rmx grep` until 16.5
ships.

## New findings {#findings}

### BULLSHIT: 16.5's "argv untouched" is undefined against rmx's own options, and `-f` is two different flags {#b-r3-1}

**Spec:** 16.5 R1 and R2, R5, AC-1/AC-2
**What:** For named paths or a pipe, R1/R2 run `/usr/bin/grep` "with the caller's argv untouched".
But `rmx grep` parses eight click options of its own before any argv reaches `grep()`:
`-f/--flags`, `--limit`, `-k/--kind`, `--linkage`, `--regex/--substring`, `--learn/--no-learn`,
`--via-replica` and `--fallback`. The spec does not say which argv is untouched.
**Why it is bullshit:**
- **Using click's leftover `argv`** silently drops those options. The documented
  `git diff | rmx grep -f '-c' "^+"` (`docs/agent-doc-primer.md:52`) becomes `grep '^+'`: it prints
  every added line, with exit 0, instead of a count. That is a silent wrong answer.
- **Using the raw argv** makes the same call `grep -f -c '^+'`, which reads patterns from a file
  named `-c`, so it errors.
- `--no-learn` on a named-path call has no stated effect on the learner spawn.
- An explicit `--limit 5 PAT file` is either dropped or passed to grep as an invalid option.

R5's differential feeds IDENTICAL `ARGS` to `rmx grep` and `/usr/bin/grep`, built from a grep
corpus, so no rmx-only option ever appears in it. No AC can fail on this.
**Fix:**
- State the contract per option:
  - `-f/--flags` and `--regex` on a named-path or pipe call are a usage error, exit 2, OR are
    translated, with a table;
  - `--no-learn` suppresses the spawn;
  - `--limit`/`--kind`/`--linkage`/`--via-replica` are rejected or ignored, and the choice is named.
- Update `docs/agent-doc-primer.md:45-52`.
- Add AC rows that pair `rmx grep -f '-c' PAT file` and `… | rmx grep -f '-c' PAT` with their
  stated outcome.
**Pattern match:** YES. [[impression_bsd_guard_cannot_fire]]: the differential cannot see the
input class that breaks.

rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT: deleting `_grep_delegate` orphans the path-less flags it served, and R3's floor names only `-l/-c/-n` {#b-r3-2}

**Spec:** 16.5 R3, R4 ("its flag-routing job is subsumed by R1"), test strategy
**What:** R1 covers named paths only. Today the delegate also serves PATH-LESS calls that carry a
flag the index cannot express: `--include`, `-A/-B/-C`, `-NUM`, `-m`, `-g`, `-t`, and unknown
letters. For these it runs **rg first** over `_root().parent`. After R4 deletes it, nothing in 16.5
says what `rmx grep -A 2 PAT`, `rmx grep --include='*.py' PAT` or `rmx grep -t py PAT` do: an index
read that ignores the flag, the floor, or an error.

R3's floor is `grep -rnH <pruning> PAT <project_root>`, with "the only shaping … the `-l`/`-c`/`-n`
flags". The MATCHING flags that today's floor honours are not mentioned: `-i` (bug-077's floor
rule), `-w`, `-x`, `-v`, `-L`, `-F`, `-E`, `-o`, and `--limit`.
**Why it is bullshit:** this is the remaining place where rmx renders grep's output, and the spec
enumerates the shaping flags while leaving out the matching ones. That is the exact shape of
bsd-pattern-sibling-render-path, which has 11 sightings. M7 (the grep-only floor's case letters)
survived r4, and its class now lives on 16.5's grep floor. Test strategy pre-registers only three
mutations: the banner, Python rendering, and an `rg -F` floor. None of them drops `-i` from the
floor.
**Fix:**
- Give R3 a flag table for the path-less read: index-honoured, floor-passed, error.
- Say what replaces the path-less delegate. For example: any flag that is not index-expressible
  sends the call straight to the pruned grep floor with the caller's flags, or the call exits 2
  with a message.
- Add a path-less differential, `rmx grep FLAGS PAT` vs
  `/usr/bin/grep -rnH <pruning> FLAGS PAT <root>`, over `-i -w -x -v -F -E -A 2 --include -m 1`.
- Add the mutation "floor drops `-i`".

**Pattern match:** YES. [[bsd-pattern-sibling-render-path]], escalated by rule.

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY: R1b APPENDS `--include`, and BSD lets the last match win, so a caller's `--exclude` is undone {#s-r3-1}

**Spec:** 16.1 R1b ("APPENDS pruning flags", "faithful by construction")
**Evidence:** `grep -rn --exclude='*.md' needle d --include='*.py' --include='*.md' --include='*.txt'`
prints `d/a.md`. Putting the includes BEFORE `--exclude` keeps it out. The learner would teach
lines from files the caller excluded, which is an over-teach. R1b guards only against a caller
`--include`, and no AC uses `--exclude`.
**Fix:** PREPEND the pruning flags ahead of the caller's tokens, or omit `--include` when the
caller passed `--exclude`. Add an AC-1 row `--exclude='*.md'` with RED by set difference, and a
mutation that appends.

### SKETCHY: the path-less read answers in two dialects, so bug-081 is "fixed" only on an index miss {#s-r3-2}

**Spec:** 16.5 R3, R6 ("bug-081 is marked fixed by R3"), AC-4
**What:**
- The index read stays substring by default, or Python `re` under `--regex`, and verifies learned
  rows in that dialect. The floor becomes BSD BRE.
- `rmx grep 'foo.bar'` therefore returns literal-only rows whenever the index has any. When it has
  none, the floor returns BRE matches (`fooXbar`). The same pattern gets a different answer
  depending on index state.
- A BRE pattern taught by the floor (`alpha$`) is stored as `query/alpha$` and then fails substring
  verification on every later read. It is learned and never served.
- The `\|` refusal at `cli.py:6132-6144` runs before the named/pipe/path-less split, so it still
  rejects `rmx grep 'a\|b' file`, which R1 says must exec grep, and the path-less floor that R3
  says reads BRE natively. The spec does not move or delete it.

AC-4 tests only the miss.
**Fix:**
- Order R1/R2 routing before the BRE refusal.
- Either make the path-less index read verify in BRE, or document `rmx grep PAT` as a
  substring-index read whose floor is `grep -F` unless `-G`/`-E` is given.
- Add an AC with the same pattern on a store that HAS rows.

### SKETCHY: "ONE shared function" for the spawn contradicts 16.2's shell slot and throttle {#s-r3-3}

**Spec:** 16.5 R1, Files ("the shared spawn function R1 and the shims both use") vs 16.2 R2/R3
The shims are `/bin/sh`. 16.2 puts the slot glob and the `cksum` stamp key in shell precisely so
that a skipped call costs no Python start (#s-n9). A Python function in `grep_learn.py` cannot be
"used by the shims". So there are two implementations of the throttle key
(`printf '%s\0' "$PWD" "$@" | cksum`) and of the slot count. If the keys differ, the same search
through `rmx grep` and through the shim is taught twice, or the throttle counter undercounts.
**Fix:** Say that the shell copy is canonical and the Python copy mirrors it. Add a parity AC: the
same cwd and argv through both routes gives the same stamp path and ONE spawn within the TTL.

### SKETCHY: R6 would mark live index fixes as "superseded (code deleted)" {#s-r3-4}

**Spec:** 16.5 R6 vs R3
R6 marks bug-076 to bug-079 `superseded by task-16.5 (code deleted)`. But bug-076
(verify-before-cap), bug-078 (spelling bridge) and the index half of bug-077 are in
`Store.grep_evidence` and the index read, which R3 explicitly KEEPS ("bug-073/074/076/077/078/083/084's
rules"). Only bug-079 and the named-path half of bug-077 lose their code. The registry would claim
that live code no longer exists, and that hides any regression of it. #why also cites "bug-058 to
bug-066", a range that includes bug-061 (bus retention) and bug-065 (save-state recall), which are
not drop-in rows.
**Fix:** List the rows one by one: superseded (bug-079, #b-2/#b-3/#b-4, #m-4) vs still live and
fixed (bug-076/078, the index half of bug-077).

### SKETCHY: the behaviour changes break documented calls that no spec owns {#s-r3-5}

**Spec:** 16.5 R1 "Behaviour change, stated", 16.3 R3's doc list
These calls stop working, and no task lists them:
- `docs/agent-doc-primer.md:49` `rmx grep "FIXME" src/ tests/` (no `-r`) becomes
  `Is a directory`, exit 2.
- `:51` `rmx grep -f '-il' "daemon"` and `:52` `git diff | rmx grep -f '-c' "^+"` (see [[#b-r3-1]]).
- `cli.py:6080-6082` docstring examples `rmx grep -i -l "daemon" src/` and
  `rmx grep -e "-x" -- src/` (no `-r`) fail the same way.
- `hooks.py:926` `rmxg() … # index-backed grep (bare grep/rg flags OK)`: rg flags (`-t py`, `-g`,
  `--hidden`) with a path used to reach rg through the delegate, and now reach `/usr/bin/grep`,
  which exits 2.

16.3 R3's list does not include `docs/agent-doc-primer.md`, and 16.5's Files table lists no docs.
**Fix:** Add these surfaces to 16.5's Files table, and extend 16.3 AC-7's stale-claim scan to
"`rmx grep` with a directory operand and no `-r`" and to "rg flags OK".

### SKETCHY: 16.4's historical O1 oracle is mostly rmx's own rendering, not grep's {#s-r3-6}

**Spec:** 16.4 R1 (historical), R3 ("what the agent SAW")
Before the 2026-10-06 interim, every rewritten grep ran in rich mode, so the `tool_result` holds
`rmx grep`'s answer, including its floor rendering and its known false negatives (bug-081, bug-076,
bug-079). Of 37 heuristic complete-ish historical invocations, **28 carry rmx markers**
(`# rmx grep fallback via rg`, `query/`, `[mentions]`). Scoring a grep-faithful learner against
rmx's buggy output counts rmx's misses as the learner's over-teaches. The gate can now fail for a
reason unrelated to the learner, which is the opposite failure from b-n1 and equally uninformative.
**Fix:** Count an invocation as complete only when the real tool produced the output: no rmx marker,
and either the era is known to be plain (interim or post-16.2) or the forward oracle applies. Report
how many were excluded as `rmx-rendered`. State the expected historical n after the exclusion.

### SKETCHY: the forward join is not exact: shell text is not argv, and throttled calls leave no keyed trace {#s-r3-7}

**Spec:** 16.4 R1 (forward), R4 `unobserved_share`
- **Text vs argv.** "The record's argv, joined, equals one of the command's grep segments"
  compares SHELL SOURCE with POST-EXPANSION argv. 1,883 of 2,003 grep commands contain quotes (a
  shlex parse can fix those). 117 use `$`/backticks, 109 an unquoted glob, and 134 a loop or
  `xargs`. No text join can fix those. Each one is an unmatched segment PLUS an unmatched record,
  which reads as route 3 plus route 2.
- **Throttle and busy.** A throttled or busy call writes one unkeyed BYTE (16.2 R3). No argv, cwd
  or ts is recorded, so "no record and no … throttle or busy explanation" cannot be evaluated per
  segment. 274 of 3,163 historical segments repeat the same cwd and text inside the 5-minute TTL,
  and 64 commands repeat a segment verbatim. All of them would read as unobserved.
- **Timestamp.** R6 does not say whether `ts` is the learner's start or end. A 10 s learner can
  log after the `tool_result`, so the window test is undefined.
**Fix:**
- Have the shim write a one-line keyed record (ts, cwd, argv_sha) for throttled and busy calls, or
  have the learner log `throttled` itself.
- Specify an expansion-tolerant match: shlex-split, then a glob or `$`-aware match. Count what does
  not match as `unattributable`, never as route 3.
- Define `ts` as the spawn time passed by the shim.

### SKETCHY: "complete" ignores other output in the same tool_result and the Grep tool's own paging {#s-r3-8}

**Spec:** 16.4 R3 conditions 1-6
- A Bash `tool_result` concatenates every command's stdout. The samples show `ls -la …` output
  beside the grep output, and `cat`/`echo`/`sed -n` can emit `file:N:`-shaped lines. Condition 5
  (one attributed segment) does not exclude other output-producing commands.
- For O2, the Grep tool truncates content mode at `head_limit`, which defaults to 250
  (`zno=250` in 2.1.292), and marks it `with pagination = …`. Neither the marker nor
  `appliedLimit` is a condition, so a paged response scores as complete, and lines past the page
  count as over-teaches.

**Fix:** Require the command to be a single pipeline-free grep, or attribute only lines whose
path parses under the segment's operands. Add `appliedLimit`/`pagination` as an O2 incompleteness
marker.

### SKETCHY: `insufficient-n` has no plan-closure rule {#s-r3-9}

**Spec:** 16.4 R4/R5, plan Tasks row
R5 says the first run after 16.2 is "the plan's acceptance run". The heuristic historical count is
37 before the hash/drift/cap exclusions, and about 9 once rmx-rendered outputs are removed
([[#s-r3-6]]). The acceptance run is therefore almost certainly `insufficient-n`. Nothing says
whether plan-16 can be marked `completed` with the gate unevaluated, or by when forward n must reach
30. A gate that may stay unevaluated forever is an unanchored deferral (rule 9a).
**Fix:** State it. For example, plan-16 stays `in-progress` until a run with n ≥ 30, with a dated
re-run task spec. Or name the acceptance as `insufficient-n → plan re-decided by the user`.

### SKETCHY: a single-file `path` takes a different branch in the Grep tool, and rg ignores globs on explicit files {#s-r3-10}

**Spec:** 16.3 R1 table, AC-1
For a FILE `path`, Claude Code removes its `--glob` args, matches `glob` itself (minimatch,
`dot:true`, nocase under `-i`), and returns `[]` on a mismatch. It also returns `[]` whenever
`type` is set. rg 15.1.0 searches an explicit file regardless of `-g` (probe). So
`{path: "d/a.md", glob: "*.py"}` returns nothing, while the learner's re-run teaches `a.md`. AC-1's
captured payloads are not required to include this branch.
**Fix:** Model the branch: for a file path with a non-matching glob, or any `type`, teach nothing
and log a reason. Add a captured payload for it.

### MEH: `<pid>.detached` markers accumulate in the directory the shim globs {#m-r3-1}

**Spec:** 16.1 R0, R9; 16.2 R2
Each learner writes `.grep-learn-slots/<pid>.detached`, and no step removes it. R9 bounds the slot
DIRS only. The shim's count must also match `slot-*.d` exactly, or the markers count as busy slots.
**Fix:** Remove the marker at exit, prune it with the stamps, and require the glob `slot-*.d`.

### MEH: grep table gaps {#m-r3-2}

**Spec:** 16.1 R1 table
BSD 2.6.0's man page also lists `--mmap` (a no-op, but unknown tokens kill the teach), `--include-dir`,
and the long forms `--bz`/`--decompress`/`--lzma`/`--xz`. Each should be a row, so a kill is a
decision and not an accident.

### MEH: 16.3 extraction and hook details {#m-r3-3}

**Spec:** 16.3 R1, AC-1, AC-3b, AC-5
- **The member anchor is ambiguous.** It finds 3 VCS-like arrays, one of which has 8 members.
  Anchor on the `"--max-columns","500"` site and follow its `for(let X of Y)` back to `Y=[…]`.
- **The scan costs 33 s** of the 235 MB binary on every suite run. Cache it, keyed on the binary's
  size and mtime.
- **The brace rule needs both `{` and `}`.**
- **The `type -P rg` empty result** (no rg on PATH) has no stated outcome. Make it
  `skipped reason=no-binary`, logged.
- **AC-1 vs AC-3b.** AC-1's equality with the tool's response holds only below `min(200,
  head_limit or 250)`, which conflicts with AC-3b's paging payloads. Say what is compared when the
  tool pages.

### MEH: 16.5 ACs that cannot fail as written, and a missing dependency {#m-r3-4}

**Spec:** 16.5 AC-3, AC-6, R5, header
- **AC-3** proves the spawn with "`grep-learn.log` records with 16.1's fields" while using 16.2's
  SLEEPING stand-in, which writes no such record. Use the stand-in for the timing and the real
  learner for the record.
- **AC-6** (`pytest --collect-only`) cannot see in-function imports or `cli_mod.argv_rank`
  attribute access. The gate is the full suite.
- **R5** lacks r4's `-L alpha f0.txt nosuch.txt` row and the dotfile walk row.
- **Missing dependency.** 16.5 uses 16.2's `grep_differential.txt` and AC-3 stand-in, but depends
  on 16.1 only.

### MEH: an exec drops telemetry, and `ANSWERED_BY` keeps dead values {#m-r3-5}

**Spec:** 16.5 R1/R2
If the named-path or pipe route `exec`s, which the title says, no `log_query` row is written and no
`cli.log` exit record is written for those calls. `telemetry.ANSWERED_BY`'s `dropin` and `stdin`
become values nothing produces. `eval/production/grep_learning_replay.py` reads them. Name the
change, and either retire the values or log before the exec.

### MEH: the plan still has stale lines {#m-r3-6}

**Spec:** plan `#decisions` last paragraph, `#out-of-scope` bullet 2, `#why`
- "Next gate: task specs written (`…-tasks/`, 16.1–16.4)" does not mention 16.5.
- The out-of-scope bullet says the explicit command's drop-in gaps "belong to the explicit
  command's backlog", which 16.5 now owns.
- "bug-058 to bug-066" includes bug-061 and bug-065, which are not drop-in bugs.

## Verdict {#verdict}

**NEEDS-REVISION.** Of the prior findings:
- **r2:** 15 closed, 3 partially closed, 0 open;
- **r1 residue:** 5 of 7 closed, 2 partially closed (b-3, m-1);
- **m-5:** closed in code by `dffa2df`.

There are **18 new findings: 2 BULLSHIT, 10 SKETCHY, 6 MEH.**

16.1 and 16.2 are ready apart from [[#s-r3-1]] (prepend, do not append) and [[#m-r3-1]]. The R1b
pruning claim was the riskiest in r2, and it holds under every probe: `.`/`..`/`./src` are kept,
the `build` ancestor is safe, and it runs in 0.08–0.13 s against 103 s.

Approval is blocked by 16.5:
- [[#b-r3-1]]: rmx's own options on the exec route, where the documented `-f '-c'` pipe becomes a
  silent wrong answer;
- [[#b-r3-2]]: the path-less flags orphaned by deleting the delegate, while the floor's flag set
  lists shaping and not matching.

16.4's oracle needs [[#s-r3-6]] and [[#s-r3-7]] before its numbers mean anything.

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| c8278b1 (SPEC review r3, plan-16 tasks 16.1-16.5, pre-implementation; written 2026-10-07T01:40:51-0700) | 2026-10-07 | Todd Holley / Opus 5.5 / orchestrator | NEEDS-REVISION | 18 new (2B/10S/6M); r2: 15 closed, 3 partial, 0 open; r1 residue 5/7 closed; m-5 closed (dffa2df) | [[bsd-plan16-spec-review-r3-c8278b1]]: R1b pruning verified live on BSD 2.6.0 (`.`/`..`/`./src` kept, build ancestor safe, 0.08-0.13 s vs 103 s); type -P rg correct under BASH_ENV; --max-columns anchor unique in the 2.1.292 binary. BULLSHIT: 16.5's "argv untouched" ignores rmx's own click options (-f/--flags collides with grep -f FILE; documented `git diff | rmx grep -f '-c' "^+"` becomes a silent line listing) and the identical-ARGS differential cannot see it; deleting _grep_delegate orphans path-less --include/-A/-t/-m and R3's floor names only -l/-c/-n, not -i/-w/-v/-F (bug-077 sibling, M7 class). SKETCHY: R1b appends --include after a caller --exclude and BSD last-match-wins re-includes (probe); path-less index substring vs floor BRE (bug-081 fixed only on a miss; \| refusal still first); "one shared spawn function" vs shell shims; R6 marks live bug-076/078 "code deleted"; agent-doc-primer/docstring/rmxg calls break; 16.4 historical O1 is rmx's rendering (28/37 complete-ish); forward join compares shell text to expanded argv and throttle/busy are unkeyed bytes (274/3163 segments repeat in TTL); completeness ignores co-output and Grep head_limit 250; insufficient-n has no closure rule; Grep tool single-file path branch vs rg ignoring globs on explicit files. No code, no mutations, no live-store access. |
```

IMPRESSIONS.md bullets:

```
- plan-16 r3 (c8278b1): a "delete instead of patch" spec must route EVERY input class the deleted code served, not just the class that motivated the deletion — 16.5 deleted the delegate for named paths and orphaned its path-less callers. Enumerate the deleted function's callers by input shape before approving.
- plan-16 r3: a differential that feeds IDENTICAL argv to both sides cannot see the wrapper's OWN options (rmx's -f/--flags vs grep's -f FILE). When a wrapper both owns flags and passes argv "untouched", demand a per-option table.
- plan-16 r3: an oracle built from historical transcripts records what the OLD tool printed; when the old tool is the thing being replaced (rich-mode rmx grep), the oracle scores the new code against the old bugs — 28 of 37 "complete" outputs were rmx-rendered.
```
