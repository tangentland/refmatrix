---
gmd: "0.1"
id: task-16.1-argv-faithful-learner
title: "Task 16.1: a learner that re-runs the caller's own search, keeps only corpus hits, and teaches exactly its lines once"
tags: [task, grep, learning, hooks]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-07
---

# Task 16.1: the argv-faithful learner {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision 3, after spec re-review `bsd-plan16-spec-rereview-42a5521`)
> Depends on: — (plan-16 itself waits on `bsd-r1-remedy` merging)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]

## Why {#why}

Today's teach ping (`bin/rmxgrep`, plain mode) rebuilds argv by DROPPING every flag and runs
`rmx grep --limit 3 PAT PATHS`. A probe showed `-i foo a.txt` becoming `grep --limit 3 foo a.txt`.
That rebuild loses three things:

- **`-i`**, so the search re-runs case-sensitively, because the floor is grep-case since bug-077.
- **`-F`**, so `'a|b'` is re-run as a regex.
- **The caller's dialect.** rmx's `rg` floor re-interprets BSD BRE (`\b`, `^`), which is bug-081.

**Faithful** means: the lines the caller's command MATCHED, under the caller's matching rules and
match cutoffs, restricted to files that belong to the store's corpus, up to a stated cap. No wider
and no narrower. {#why-lead}

## Roots, named once (#b-4) {#roots}

| name | value | used for |
|---|---|---|
| `store_root` | `realpath(<project>/.refmatrix)`, found from `cwd` the way the shim finds it | `learn_switch.decision(store_root)`, `learn_queue.enqueue(store_root, …)`, `<store_root>/grep-learn.log`, `<store_root>/.grep-learn-slots/` |
| `project_root` | `store_root.parent` | the corpus predicate (on the project-RELATIVE path), relativisation |
| `cwd` | the caller's cwd (`--cwd "$PWD"`) | the re-run's working dir; resolving output paths |

## Requirements {#requirements}

**R0. Detach first (#s-1, #m-n2).**
- The first statements are `os.setsid()` and closing inherited fds above 2. `EPERM` (already a
  group leader) is tolerated, since the process is detached already.
- Children are started with `start_new_session=True` and `close_fds=True`.
- After detaching, the learner writes `<store_root>/.grep-learn-slots/<pid>.detached`.
- The ~0.14 s of startup before `setsid` runs is an accepted window, stated here. AC-9 kills only
  after the marker exists.

**R0b. Concurrency bound, visible to the shim before any spawn (#s-2, #s-n9).**
- Slots are DIRECTORIES `<store_root>/.grep-learn-slots/slot-{0..N-1}.d`, taken with `mkdir`
  (atomic) and removed on exit. A slot whose mtime is older than 60 s is stale and is reclaimed.
- `N = RMX_GREP_LEARN_MAX_INFLIGHT`, default 2.
- The SHIM (16.2 R2) counts fresh slot dirs with a shell glob before spawning. When all are taken
  it does not spawn, and it counts `busy`. So a 1,000-file loop costs shell globs, not 1,000
  Python starts.
- The learner re-checks with `mkdir`. On a race it exits with `reason=busy` logged.

**R1. Re-run the caller's binary with the caller's MATCHING rules and CUTOFFS.**
- The shim passes `--bin ABS` (#s-6): its resolved `$REAL`, or for 16.3 the `type -P rg` result.
- The learner execs exactly that binary, with `stdin=/dev/null` and in `cwd`.
- Tokens are classified from ONE table per tool. Short AND long forms, including `--opt=value`,
  are rows of their own (#s-n3).
- The grep rows come from BSD grep 2.6.0's `--help` and `man` (verified live by the re-review:
  `-y`=`-i`; `-P`/`-T` exit 2; `-X`/`-M` exit 2 on plain text; `-S` follows symlinks; `-m` is
  per file). The rg rows come from `rg --help` (15.1.0).
- Every row the build changes is listed in the summary. {#r1}

| class | grep (BSD 2.6.0) | rg (15.1.0) |
|---|---|---|
| keep: match | `-i --ignore-case -y -w --word-regexp -x --line-regexp -F --fixed-strings -E --extended-regexp -G --basic-regexp -e PAT --regexp=PAT -r -R --recursive -S -O -p --include=G --exclude=G --exclude-dir=G -a --text -I -U --binary -d ACT --directories=ACT -D ACT --devices=ACT --binary-files=V` | `-i --ignore-case -s --case-sensitive -S --smart-case -w --word-regexp -x --line-regexp -F --fixed-strings -e PAT --regexp=PAT -g G --glob=G --iglob=G -t T --type=T -T T --type-not=T -u -uu -uuu --hidden --no-ignore* --no-config -L --follow -P --pcre2 -U --multiline --multiline-dotall -a --text --binary -d N --max-depth=N` |
| keep: cutoff (#s-10) | `-m N --max-count=N`; `-l --files-with-matches` → re-run as `-m 1` (the caller matched one line per file) | `-m N --max-count=N`; `-l --files-with-matches` → `-m 1` |
| drop: shape | `-c --count -o --only-matching -s --no-messages -h --no-filename -H --with-filename -n --line-number -b --byte-offset -A N -B N -C[N] --context[=N] -NUM --after-context=N --before-context=N --color[=W] --colour[=W] --label=L --line-buffered --null` | `-c --count --count-matches -o --only-matching -n --line-number -N --no-line-number -H --with-filename -I --no-filename --heading --no-heading -A N -B N -C N --after-context=N --before-context=N --context=N --color=W --column -b --byte-offset --trim -M N --max-columns=N --max-columns-preview -0 --null` |
| kill: teach nothing | `-v --invert-match -L --files-without-match -q --quiet --silent` (a quiet caller saw no lines; and under the corpus pruning of R1b, its "first hit" could be a line it never matched) `-f FILE --file=FILE` (multi-pattern) `-z --null-data` (every hit becomes line 1, measured) `-Z -J -X -M` (decompress: line numbers refer to decompressed text) `-P -T` (rejected, exit 2), more than one `-e` | `-v --invert-match --files-without-match --files --type-list --passthru -q --quiet -f FILE --file=FILE --json --vimgrep -r REPL --replace=REPL`, more than one `-e` |
| append | `-n -H --null` | `-n -H --null --no-heading --color never` |

- **An unknown token kills the teach** (`reason=unknown-flag:<tok>`). {#r1-unknown}
- **AC-1b feeds 16.3's rendered argv through this classifier** and requires that nothing is
  unknown (#s-n3).
- **Exit status (#m-n1).**
  - Exit 0, or exit 2 with hits (BSD grep exits 2 with valid hits when one operand is missing or
    unreadable), teaches the parsed hits and logs `tool_exit`.
  - Exit 2 with no hits teaches nothing (`reason=tool-error`).
  - A child killed at the hit cap teaches what it produced (`tool_exit=killed-at-cap`).
  - A child killed at the timeout teaches nothing (`outcome=timeout`).
- **No-operand, per tool.** grep with no file operand and no `-r`/`-R` teaches nothing
  (`reason=no-operand`), because it would read stdin. A path-less `rg` searches the cwd and is
  re-run as is.

**R1b. Prune to the corpus in the RE-RUN, not only after it (#s-n1).**
- On this repo, a whole-tree `grep -rn X` takes 103 s, because BSD grep walks `.claude`,
  `.refmatrix` and `.venv-eval` first. Path-less recursive greps are about 68 of about 200 in the
  transcripts, so filtering after the walk alone would time out a third of recursive greps.
- The re-run therefore APPENDS pruning flags that are equivalent to R3's predicate.
  - grep: `--exclude-dir='.[A-Za-z0-9_-]*'`, plus one `--exclude-dir=<d>` per `IGNORE_DIRS` entry.
    The `.?*` form was measured to exclude the `.` operand itself.
  - grep: `--include=*<ext>` per corpus extension, ONLY when the caller passed no `--include`.
    BSD grep ORs repeated `--include`s, so adding ours would widen the caller's filter.
  - rg: `-g '!<d>/'` per `IGNORE_DIRS` entry. rg already skips hidden dirs unless the caller passed
    `--hidden` or `-u`. When the caller did, `-g '!.*/'` is added, because R3 drops those hits
    anyway.
- This is faithful by construction: it removes only files R3 would discard.

**R2. Parse canonical output, streaming (#m-3).**
- The output is read line by line. With `--null`, the filename ends at the first NUL, followed by
  `LINE:TEXT`. A `:` in a filename parses.
- A `Binary file X matches` line is counted as `binary`.
- Path: `os.path.normpath(os.path.join(os.path.realpath(cwd), file))`. This resolves cwd directory
  symlinks, agreeing with the daemon's `resolve()`d `project_root` (#s-7). The file's own spelling
  is kept.

**R3. Keep only CORPUS hits, before the cap (#b-1, #m-n6).**
- A hit is taught only if the path is under `project_root` AND `corpus.is_relevant(rel,
  project_root)` holds, where `rel` is the path RELATIVE to `project_root`.
  `is_relevant` tests path parts, so testing the absolute path would reject every hit in a
  project under a dot-dir or `build/` ancestor.
- `src/refmatrix/corpus.py` (new) holds the watcher's predicate and everything it needs:
  `is_relevant`, `IGNORE_DIRS`, `SUPPORTED_EXTS` (from `watch.py`), and `load_ignore_spec`,
  `IgnoreSpec`, `IGNORE_FILE`, `CODE_EXTS`, `DOC_EXTS` (from `ingest.py`).
  - Both modules re-export these, so there is ONE predicate.
  - The predicate is the WATCHER's: it decides what is synced, and so what is ingested. The
    differences from ingest's directory rules (`build/`, `dist/`, `.gmd`) are listed in the summary.
- Drops are counted as `out_of_corpus`.

**R4. Bounded on every leg, the store included (#b-5, #s-n7, #s-n8).**
- At most `RMX_GREP_LEARN_MAX_HITS` corpus hits (default 200). The child is killed at the cap.
- A wall-clock cap, `RMX_GREP_LEARN_TIMEOUT_S` (default 10).
- **Store-side idempotence in `daemon._learn_grep_hits`.**
  1. Compute the set of `(concept, entity, line)` the record would add.
  2. If every one already exists, RETURN BEFORE `add_concept`, `upsert_entity`, `link` or
     `add_evidence`. No `facts.log` event is written.
  3. Otherwise write only the missing evidence rows. `add_evidence` is an unconditional INSERT,
     and `upsert_entity` appends `entity` and `protect` events.
- **`kind` from `corpus.CODE_EXTS`,** not the hardcoded 13-suffix set at `daemon.py:4281`.
  Identity is `(partition, kind, name)`, so a `.sh`/`.tsx`/`.sql` file otherwise becomes a second,
  PROTECTED `doc` entity beside ingest's `code` one.

**R5. The learn switch, on `store_root` (#b-4).** `learn_switch.decision(store_root)` is checked
before any process starts. That covers the env, the store marker and the global marker, and an
unreadable marker is reported per bug-080.

**R6. Never silent.** Exactly one JSONL record per invocation goes to
`<store_root>/grep-learn.log`, rotated at 5 MB with one predecessor kept. Fields:
- `ts`, `tool`, `bin`, `cwd`, `argv_sha`, `argv` (as given);
- `outcome` (`taught | no-hits | skipped | timeout | error`), `reason`, `reason_extra` (#m-n4:
  for example `retired-env:RMXGREP_TEACH`);
- `hits`, `out_of_corpus`, `binary`, `truncated`, `tool_exit`, `ms`.

`argv_sha` and `argv` are what 16.4 joins against transcripts. `rmx learn status` prints last-24 h
counts by outcome and by reason.

**R7. One entry point, not a verb.**
- `rmx grep-learn --tool {grep,rg} --bin ABS --cwd DIR [--retired-env NAME]... -- ARGV...` (#m-n4).
  It is hidden, and goes on `verbs.INTERNAL_CLI` once task 3.4 lands.
- The logic lives in `src/refmatrix/grep_learn.py`.
- `refmatrix/__init__` imports `store` (#m-n6), so "imports no store module" is unattainable. The
  bound is that the learner opens no `Store` and imports no `lance`, `torch`,
  `sentence_transformers` or `watchdog`.
- The real `rmx grep-learn` wall time to first statement is measured and recorded (AC-14).

**R8. Matching rules at read time (#s-8).** Concepts stay `query/<pattern>`. Explicit `rmx grep`
re-verifies under its own caller's rules, so `-i`-taught lines answer `rmx grep -i` and are dropped
for a case-sensitive `rmx grep`.

**R9. Small legs, bounded or named (#m-n3).**
- `.grep-learn-slots/` holds at most N dirs plus stale ones, which are reclaimed.
- Stamp files older than 24 h are pruned by the learner, at most once an hour (a marker file).
- The `throttled` counter rotates at 1 MB.
- Each learner adds one `cli.log` record through `cli_entry`. `cli.log` has no rotation today
  (19 MB), a pre-existing gap that this task logs in the bug registry and does not fix.

## Acceptance criteria {#acceptance}

1. **Flag fidelity with proven power (#s-9).** Coverage: each keep row, per tool, short AND long
   form. At minimum `-i`, `-w`, `-x`, `-F` with `|`, BRE `\b`, BRE `^`, `-E 'a|b'`, `-r` over a
   directory, `--include`, `-m 2`, `-l`, rg `-g`, rg `-t`, rg `--glob`.
   - (a) **Power.** The real tool's output WITH the flag differs from its output WITHOUT the flag
     on the fixture.
   - (b) **Fidelity.** The taught set equals the real tool's output, corpus-filtered.
   - (c) **RED.** Each case fails against a stub that drops the flag, by SET DIFFERENCE, not by
     `ImportError`.
   - **1b.** 16.3's rendered argv for every captured payload classifies with zero unknown tokens.
2. **Shape flags change nothing.** `-c`, `-o`, `-h`, `-C 2` and `--count` each teach the bare
   invocation's set.
3. **Cutoffs.** `-m 1` over a 3-hit file teaches 1. `-l` over two files teaches one line per file.
4. **Kill rows.** `-v`, `-L`, `-q`, `-f`, `-z`, `-P`, two `-e`, an unknown flag, grep with no
   operand, and exit 2 with no hits each produce `skipped` with the right `reason`. Exit 2 WITH hits
   (one missing operand) teaches the hits and logs `tool_exit=2`.
5. **Corpus.**
   - A fixture containing the pattern in `.refmatrix/query.log`, `.venv-eval/x.py`,
     `__pycache__/x.pyc`, a `.refmatrix_ignore`d path and `src/a.py` teaches only `src/a.py`, with
     `out_of_corpus=4`.
   - A 300-hit `.venv-eval/` file walked FIRST does not displace `src/a.py`.
   - A project whose ancestor directory is named `build` still teaches (the relative-path rule).
6. **Pruned re-run (#s-n1).** A 20,000-file out-of-corpus tree placed ahead of `src/` gives a
   path-less `grep -rn PAT` that teaches `src/` hits within the timeout. Without R1b the same
   fixture times out, and that is the RED.
7. **Identity (#s-7, #s-n8).** The taught entity id equals the id `ingest` gave the same file, for
   a `.py`, a `.sh` and a `.tsx` file. Checked with the cwd reached directly and through a
   symlinked directory. A symlinked FILE and its target are two entities.
8. **Parse.** A `:` filename parses. A `Binary file … matches` line is counted as `binary`.
9. **Bounds.**
   - `MAX_HITS=5` on a 50-hit fixture teaches 5, logs `tool_exit=killed-at-cap`, and the child is
     gone within 1 s.
   - A FIFO operand: wall < timeout + 1 s, `outcome=timeout`, nothing taught.
   - Three concurrent learners with `N=2`: one `busy`.
10. **Detached (#m-n2).** After the `.detached` marker exists, `killpg(spawner's group)` leaves the
    learner running to its log record. In a learner spawned as a group leader, `os.setsid()` EPERM
    is tolerated.
11. **The switch on the right root.** `RMX_LEARN=0`, then (7b) a store marker with `RMX_LEARN`
    unset, then (7c) a global marker: each gives `skipped reason=learning-disabled` and an
    unchanged queue file.
12. **Idempotent store (#b-5, #s-n7).** Teach the same argv twice (TTL 0), each time drained by a
    real `Daemon` on `store_root`. After the second drain, the `linkage_evidence` row count AND the
    `facts.log` byte size are unchanged.
13. **End to end.**
    - The real drain runs, then explicit path-less `rmx grep PAT` answers with the taught lines.
    - A `-i` teach answers `rmx grep -i PAT` with the mixed-case lines and not plain `rmx grep PAT`.
14. **Log and startup.**
    - Exactly one record per call across every outcome above.
    - `rmx learn status` shows the counts.
    - `python -X importtime -m refmatrix.cli grep-learn …` (the real entry) imports none of
      `lance`, `torch`, `sentence_transformers`, `watchdog`. Its wall time is recorded.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/grep_learn.py` (new) | detach, slot dirs, tables, classify, pruning flags, re-run, stream-parse, corpus filter, enqueue, log, stamp pruning |
| `src/refmatrix/corpus.py` (new) | predicate + `IGNORE_DIRS`, `SUPPORTED_EXTS`, `load_ignore_spec`, `IgnoreSpec`, `IGNORE_FILE`, `CODE_EXTS`, `DOC_EXTS`, moved from `watch.py` and `ingest.py` (both re-export) |
| `src/refmatrix/daemon.py` | `_learn_grep_hits`: all-present short-circuit before any write; missing-only evidence; `kind` from `CODE_EXTS` |
| `src/refmatrix/cli.py` | hidden `grep-learn`; `learn status` counts |
| `workflow/bug_registry.md` | `cli.log` has no rotation (R9) |

## Test strategy {#test-strategy}

- Real `/usr/bin/grep` and `rg` (skipped with a printed reason when absent), real fixture trees,
  real `store_root`. Nothing in `grep_learn` is patched. AC-12 and AC-13 use a real `Daemon` and
  `Store`.
- Pre-registered mutations, each with the AC it must fail:

| mutation | must fail |
|---|---|
| `-i` keep→DROP | AC-1 (set difference) |
| `-F` keep→drop | AC-1 |
| remove the corpus filter | AC-5 |
| remove R1b's pruning | AC-6 |
| remove the all-present short-circuit | AC-12 (`facts.log` grows) |
| restore the hardcoded kind set | AC-7 (`.sh`) |
| `cwd` instead of `realpath(cwd)` | AC-7 (symlinked cwd) |
| skip `os.setsid()` | AC-10 |
| read the switch on `project_root` | AC-11 7b |
| remove the log write on `timeout` | AC-14 |
| remove a long-form row | AC-1b |

{#tests}
