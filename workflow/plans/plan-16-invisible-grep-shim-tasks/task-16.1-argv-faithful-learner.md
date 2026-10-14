---
gmd: "0.1"
id: task-16.1-argv-faithful-learner
title: "Task 16.1: a learner that re-runs the caller's own search, keeps only corpus hits, and teaches exactly its lines once"
tags: [task, grep, learning, hooks]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
  revised: 2026-10-14
---

# Task 16.1: the argv-faithful learner {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision after the 2026-10-14 decision log; revision 6, answering spec review
> r5 `bsd-plan16-spec-review-r5-cd7c923`)
> **Wave:** 2 (plan-16's chain 16.1 → 16.2 ∥ 16.3 → 16.5; [[plan-16-invisible-grep-shim#waves]]).
> Depends on: [[task-16.6-learned-row-validation]]'s Wave-1 slice (the `learned_evidence` table and
> `Store.add_learned_provenance`, which R10 writes through), and through it plan-23's 23.1 queue.
> Tests run in plan-23 task 23.0's sandbox.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]
rel: amends -> [[bsd-plan16-spec-rereview-42a5521]]
rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: depends-on -> [[task-16.6-learned-row-validation]]
rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t7]]

## Revision 6 changelog {#revision-6}

Answers spec review r5 ([[bsd-plan16-spec-review-r5-cd7c923]]) and the 2026-10-14 decision log
([[plan-review-2026-10-14]]).

| finding / decision | answered in |
|---|---|
| d6d + #t8-amendments (the learn-time provenance write moves INTO 16.1, Wave 2) | R10 [[#r10]]; header (depends on 16.6's Wave-1 slice, not the reverse); AC-15 |
| #t6-fixes (provenance carries tool + regex dialect + line hash) / r5 b-r5-1 | R10 (`tool`, `bin`, `dialect`, `match_argv`, `line_hash`); AC-15 |
| #t7-fixes / r5 s-r5-2 (16.1's case-insensitive `--include` pruning only on recursive calls, so `grep -i PAT dir` keeps exit 2) | R1b [[#r1b]] "only on a recursive re-run"; AC-4 rows; mutation |
| r4 s-r4-7 (partial; 16.2 AC-4b) | R1b (the cause); 16.2 AC-4b kept as written |
| r5 s-r5-2 (AC-4's missing operand depends on file names) | AC-4: the missing operand has a corpus extension (`nosuch.py`) |
| #t7-fixes / r5 s-r5-6 (a `spawned_by` field on learner records) | R6 [[#r6]], R7 `--spawned-by`; AC-16 |
| #t7-fixes MEH / r5 m-r5-5 (space-form rows for long value flags) | R1 table + rule [[#r1-space-forms]]; AC-1 space forms; mutation |
| r5 s-r5-1 support (16.5's cluster walk needs the short value letters) | R1 [[#r1]] `value` column: short letters `e f m A B C d D` |
| bug-102 (`--context` as a space-value flag, `cli.py:5540`) | R1 `value` column (`--context` takes a value only as `=`) is the fix; 16.5 R4 deletes `_GREP_VALUE_FLAGS`; 16.5 R8 closes the row |
| d1a/d1b (tests sandboxed by task 23.0) | [[#test-strategy]] |

## Revision 5 changelog {#revision-5}

Answers spec review r4 ([[bsd-plan16-spec-review-r4-33809ab]]), which found 16.1 ready apart from
wording.

| finding | answered in |
|---|---|
| m-r4-2 R1b "APPENDS" vs "BEFORE" | R1b [[#r1b]]: "ADDS … BEFORE the caller's tokens", stated once |
| m-r4-8 case-sensitive `--include` vs the lowercasing predicate | R1b: lower AND upper globs per extension; mixed case named as a recall-only gap |
| s-r4-5 `ts` defined only in 16.4 | R6 [[#r6]]: `ts` = learner START, before the re-run |
| s-r4-4 (16.3's missing rg) | R1 [[#r1]]: `--bin` empty or not executable → `skipped reason=no-binary` |
| b-r4-2 (16.5 needs grep's value flags) | R1: the grep table's `value` column (space-form value flags, probed) is the ONE source 16.5 R0/R0b read |

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
- After detaching, the learner writes `<store_root>/.grep-learn-slots/<pid>.detached` and REMOVES
  it on exit (#m-r3-1). Stale markers (older than 60 s, pid not alive) are reclaimed with the slots.
  The shim counts only `slot-*.d` dirs, never markers.
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
- Every row the build changes is listed in the summary.
- **`--bin` empty, missing or not executable** → nothing runs, `outcome=skipped
  reason=no-binary` (16.3's missing-rg case, s-r4-4).
- **The `value` column (b-r4-2).** The grep table also records which tokens consume the NEXT
  argv token. Probed on BSD 2.6.0 (revision 5), space-form value flags are exactly: `-e --regexp
  -f --file -m --max-count -A --after-context -B --before-context -C -d --directories -D --devices
  --label --binary-files --include --exclude --exclude-dir --include-dir`. `--context` and
  `--color`/`--colour` take a value only as `=` (`--context 1 alpha a.py` reads `1` as the
  pattern). The space forms `--binary-files V` and `--label L` are rows of their own in the table
  below, beside the `=` forms. 16.5 R0/R0b read this column; there is no second value-flag set. {#r1}
  - The SHORT letters that take a value are `e f m A B C d D`. 16.5 R0's cluster walk reads them:
    in a cluster, a value letter ends the cluster and the rest of the token is its value (BSD:
    `-ekey` is `-e key`, probed in r5).
  - This column is also the fix for bug-102: `--context` is NOT a space-value flag (`cli.py:5540`'s
    `_GREP_VALUE_FLAGS` wrongly lists it; 16.5 R4 deletes that set).
- **Every long flag in the `value` column has its SPACE form as a row of its own (m-r5-5),** beside
  its `=` form, in the class its `=` form has: `--include G`, `--exclude G`, `--exclude-dir G`,
  `--include-dir G`, `--regexp PAT`, `--directories ACT`, `--devices ACT` (keep: match);
  `--max-count N` (keep: cutoff); `--after-context N`, `--before-context N` (drop: shape);
  `--file FILE` (kill). Without them, `grep -r --include '*.py' x .` would kill the teach as
  `unknown-flag:--include`. {#r1-space-forms}

| class | grep (BSD 2.6.0) | rg (15.1.0) |
|---|---|---|
| keep: match | `-i --ignore-case -y -w --word-regexp -x --line-regexp -F --fixed-strings -E --extended-regexp -G --basic-regexp -e PAT --regexp=PAT --regexp PAT -r -R --recursive -S -O -p --include=G --include G --exclude=G --exclude G --exclude-dir=G --exclude-dir G --include-dir=G --include-dir G -a --text -I -U --binary -d ACT --directories=ACT --directories ACT -D ACT --devices=ACT --devices ACT --binary-files=V --binary-files V --mmap` | `-i --ignore-case -s --case-sensitive -S --smart-case -w --word-regexp -x --line-regexp -F --fixed-strings -e PAT --regexp=PAT -g G --glob=G --iglob=G -t T --type=T -T T --type-not=T -u -uu -uuu --hidden --no-ignore* --no-config -L --follow -P --pcre2 -U --multiline --multiline-dotall -a --text --binary -d N --max-depth=N` |
| keep: cutoff (#s-10) | `-m N --max-count=N --max-count N`; `-l --files-with-matches` → re-run as `-m 1` (the caller matched one line per file) | `-m N --max-count=N`; `-l --files-with-matches` → `-m 1` |
| drop: shape | `-c --count -o --only-matching -s --no-messages -h --no-filename -H --with-filename -n --line-number -b --byte-offset -A N -B N -C[N] --context[=N] -NUM --after-context=N --after-context N --before-context=N --before-context N --color[=W] --colour[=W] --label=L --label L --line-buffered --null` | `-c --count --count-matches -o --only-matching -n --line-number -N --no-line-number -H --with-filename -I --no-filename --heading --no-heading -A N -B N -C N --after-context=N --before-context=N --context=N --color=W --column -b --byte-offset --trim -M N --max-columns=N --max-columns-preview -0 --null` |
| kill: teach nothing | `-v --invert-match -L --files-without-match -q --quiet --silent` (a quiet caller saw no lines; and under the corpus pruning of R1b, its "first hit" could be a line it never matched) `-f FILE --file=FILE --file FILE` (multi-pattern) `-z --null-data` (every hit becomes line 1, measured) `-Z -J -X -M --decompress --bz2decompress --xz --lzma` (decompress: line numbers refer to decompressed text) `-P -T` (rejected, exit 2), more than one `-e` | `-v --invert-match --files-without-match --files --type-list --passthru -q --quiet -f FILE --file=FILE --json --vimgrep -r REPL --replace=REPL`, more than one `-e` |
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
- The re-run therefore ADDS pruning flags that are equivalent to R3's predicate, placed BEFORE the
  caller's tokens (see "The pruning flags go BEFORE" below; m-r4-2). {#r1b}
- **Only on a RECURSIVE re-run (s-r5-2, #t7-fixes).** The pruning flags (the `--include`s AND the
  `--exclude-dir`s) are added only when the caller's tokens make grep recurse: `-r`, `-R`,
  `--recursive`, `-d recurse`, `--directories=recurse` or `--directories recurse`. A
  non-recursive re-run names its operands explicitly, so it walks nothing and gains nothing from
  pruning, and R3 still filters its hits. Probed in r5: with the `--include`s added, `grep -i PAT
  dir` skips the directory silently and exits 1 (instead of `Is a directory`, exit 2), and `grep
  PAT a.py nosuch` exits 0 instead of 2. So a non-recursive re-run keeps grep's own exit status,
  and R1's exit-status rules and 16.2 AC-4b hold as written. rg always walks, so its `-g`
  exclusions are added on every rg re-run (rg ignores `-g` on a named file).
  - grep: `--exclude-dir='.[A-Za-z0-9_-]*'`, plus one `--exclude-dir=<d>` per `IGNORE_DIRS` entry.
    The `.?*` form was measured to exclude the `.` operand itself.
  - grep: `--include=*<ext>` AND `--include=*<EXT>` (upper case) per corpus extension, ONLY when
    the caller passed no `--include`. BSD grep ORs repeated `--include`s, so adding ours would
    widen the caller's filter.
  - **Case (m-r4-8).** BSD `--include` globs are case-sensitive (probed: `--include='*.py'` skips
    `C.PY`), while `is_relevant` lowercases the suffix, so `C.PY` IS in the corpus. The upper-case
    globs cover all-caps suffixes. A mixed-case suffix (`.Py`) is still pruned from the re-run: a
    recall-only loss (never an over-teach, because R3 still filters), with 0 such files in this repo
    today; named in the summary.
  - rg: `-g '!<d>/'` per `IGNORE_DIRS` entry. rg already skips hidden dirs unless the caller passed
    `--hidden` or `-u`. When the caller did, `-g '!.*/'` is added, because R3 drops those hits
    anyway.
- **The pruning flags go BEFORE the caller's tokens (#s-r3-1).** BSD grep lets the LAST matching
  `--include`/`--exclude` win (probed), so appended `--include`s re-included files the caller had
  `--exclude`d. Placed first, every caller filter overrides ours.
- This is faithful by construction: it removes only files R3 would discard.
- Probed on BSD 2.6.0 (spec review r3): `--exclude-dir='.[A-Za-z0-9_-]*'` excludes neither `.`,
  `..`, `./src` nor a path-less `-r`. The pruned whole-tree grep takes 0.08–0.13 s on this repo,
  against 103 s unpruned.

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

**R6. Never silent.** {#r6} Exactly one JSONL record per invocation goes to
`<store_root>/grep-learn.log`, rotated at 5 MB with one predecessor kept. Fields:
- `ts` — the learner's START time (epoch seconds, float), taken after `setsid` and BEFORE the
  re-run, so it falls inside the calling tool call's window even when the re-run times out
  (s-r4-5; 16.4 R1 joins on it);
- `tool`, `bin`, `cwd`, `argv_sha`, `argv` (as given);
- `spawned_by` — who started the learner, from `--spawned-by` (s-r5-6, #t7-fixes): `shim` (16.2's
  wrappers), `grep-tool-hook` (16.3), `rmx-grep` (16.5's named route and floor). A missing or
  unknown value is refused at argv parsing (`outcome=skipped reason=bad-spawned-by`), never
  defaulted; 16.4 separates its routes on it;
- `outcome` (`taught | no-hits | skipped | timeout | error`), `reason`, `reason_extra` (#m-n4:
  for example `retired-env:RMXGREP_TEACH`);
- `hits`, `out_of_corpus`, `binary`, `truncated`, `tool_exit`, `ms`.

`argv_sha` and `argv` are what 16.4 joins against transcripts. `rmx learn status` prints last-24 h
counts by outcome and by reason.

**R7. One entry point, not a verb.**
- `rmx grep-learn --tool {grep,rg} --bin ABS --cwd DIR --spawned-by {shim,grep-tool-hook,rmx-grep}
  [--retired-env NAME]... -- ARGV...` (#m-n4, s-r5-6).
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

**R10. Learn-time provenance (d6d: moved here from 16.6 R1; #t6-fixes; b-r5-1).** {#r10}
- The learner's queue record carries, per record: `tool`, `bin`, `dialect`, `match_argv`,
  `spawned_by`, `root` (= `project_root`), `pattern`; and per hit: `file`, `line`, `line_hash`.
  - `match_argv` = the MATCH-class and CUTOFF-class tokens R1 kept, verbatim and in order (the
    cutoff as re-run, so `-l` is recorded as `-m 1`). Pruning flags (R1b) and the appended
    canonical tokens are NOT in it.
  - `dialect`: grep `-F`/`--fixed-strings` → `fixed`, `-E`/`--extended-regexp` → `ere`, else `bre`;
    rg `-F` → `fixed`, `-P`/`--pcre2` → `pcre2`, else `rust`; tokens naming more than one dialect →
    `mixed`. Informational: 16.6 R2 always re-runs `tool`.
  - `line_hash` = sha256 hex of the TEXT bytes after `LINE:` in the canonical output, without the
    line terminator (16.6 R3).
- `_learn_grep_hits` writes one `learned_evidence` row per evidence row it adds, `origin=learner`,
  through `Store.add_learned_provenance` (16.6 R1), in the SAME transaction as `add_evidence`. It
  replaces 16.6 R1b's `legacy-writer` call on this path.
- **The context backstop** (`daemon.py:4795-4806`) passes its provenance to `_learn_grep_hits`:
  `origin=context-backstop`, `spawned_by=context-backstop`, `tool` = `rg` or `grep` as
  `context.py:912-926` chose, `bin` = that path, `match_argv` = its kept tokens (`-i -F`, `-w` when
  set, and every `-e TERM`), `dialect=fixed`, `line_hash` from the line read at learn time.
- **Idempotence (R4) covers the sidecar.** The all-present short-circuit tests the evidence rows
  AND their sidecar rows under this record's `rules_sha`. A re-teach under the same rules writes
  nothing. A re-teach under different rules (`-i` after none) writes only the missing sidecar rows,
  no evidence row and no `facts.log` event.

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
   - **1c (m-r5-5).** Every long `value` flag in its SPACE form classifies as its `=` form does:
     `grep -r --include '*.py' alpha .`, `--exclude-dir build`, `--regexp alpha`, `--max-count 1`,
     `--after-context 1`, `--file pats.txt` (kill) each produce the same outcome and taught set as
     the `=` spelling.
2. **Shape flags change nothing.** `-c`, `-o`, `-h`, `-C 2` and `--count` each teach the bare
   invocation's set.
3. **Cutoffs.** `-m 1` over a 3-hit file teaches 1. `-l` over two files teaches one line per file.
4. **Kill rows.** `-v`, `-L`, `-q`, `-f`, `-z`, `-P`, two `-e`, an unknown flag, grep with no
   operand, `--bin ""`, and exit 2 with no hits each produce `skipped` with the right `reason`. Exit 2 WITH hits
   (one missing operand, `alpha a.py nosuch.py`: the missing operand carries a CORPUS extension, so
   a pruning `--include` could not mask it) teaches the hits and logs `tool_exit=2`.
   - **4b (s-r5-2).** `grep -i alpha sub` (a directory, no `-r`) logs `outcome=skipped
     reason=tool-error`, `tool_exit=2`, and the recorded re-run argv carries no `--include` and no
     `--exclude-dir`. `grep -ri alpha sub` re-runs WITH the pruning flags.
5. **Corpus.**
   - A fixture containing the pattern in `.refmatrix/query.log`, `.venv-eval/x.py`,
     `__pycache__/x.pyc`, a `.refmatrix_ignore`d path and `src/a.py` teaches only `src/a.py`, with
     `out_of_corpus=4`.
   - A 300-hit `.venv-eval/` file walked FIRST does not displace `src/a.py`.
   - A project whose ancestor directory is named `build` still teaches (the relative-path rule).
   - **5b.** A path-less `grep -rn PAT` re-run with R1b's pruning teaches `src/C.PY` (m-r4-8).
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
15. **Provenance at learn time (R10, b-r5-1).** On a real `Daemon` drain in the sandbox:
    `grep 'zzz\|alp' a.py` and `grep '\(foo\)x' b.py` each write `learned_evidence` rows with
    `origin=learner`, `tool=grep`, `bin=/usr/bin/grep`, `dialect=bre`, `match_argv=[]`,
    `spawned_by` as passed, and `line_hash` = sha256 of the file's line; 16.6 R2 verifies both
    `ok`. `grep -F 'a|b'` records `dialect=fixed`, `match_argv=['-F']`; `-l` records `['-m', '1']`.
    A learned evidence row with no sidecar row after the drain: 0. Re-teaching the same argv writes
    nothing (AC-12 holds with the sidecar); re-teaching with `-i` adds sidecar rows only.
16. **`spawned_by` (s-r5-6).** Each of `--spawned-by shim`, `grep-tool-hook`, `rmx-grep` lands in the
    log record and the sidecar; a missing `--spawned-by` gives `skipped reason=bad-spawned-by`.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/grep_learn.py` (new) | detach, slot dirs, tables, classify, pruning flags, re-run, stream-parse, corpus filter, enqueue, log, stamp pruning |
| `src/refmatrix/corpus.py` (new) | predicate + `IGNORE_DIRS`, `SUPPORTED_EXTS`, `load_ignore_spec`, `IgnoreSpec`, `IGNORE_FILE`, `CODE_EXTS`, `DOC_EXTS`, moved from `watch.py` and `ingest.py` (both re-export) |
| `src/refmatrix/daemon.py` | `_learn_grep_hits`: all-present short-circuit (evidence + sidecar) before any write; missing-only evidence; `kind` from `CODE_EXTS`; R10 sidecar write replacing 16.6 R1b's legacy call; the context backstop's provenance |
| `src/refmatrix/cli.py` | hidden `grep-learn`; `learn status` counts |
| `workflow/bug_registry.md` | `cli.log` has no rotation (R9). bug-102 is closed by 16.5 R8 when 16.5 R4 deletes `_GREP_VALUE_FLAGS`; this table is its fix |

## Test strategy {#test-strategy}

- **Sandbox (d1a/d1b).** Every test runs inside plan-23 task 23.0's shared sandbox (`$HOME`, the
  global root, the registry and the LaunchAgents dir in a tmp dir before `refmatrix` is imported;
  injected store roots; spawned `rmx` children refuse sockets outside the tmp dir; the conftest
  guard fails any touch of `~/.refmatrix` or a registered live store). `store_root` is a tmp
  project's `.refmatrix/` under a SHORT `mkdtemp()` root.
- Real `/usr/bin/grep` and `rg` (skipped with a printed reason when absent), real fixture trees,
  real `store_root`. Nothing in `grep_learn` is patched. AC-12, AC-13 and AC-15 use a real `Daemon`
  and `Store`.
- Pre-registered mutations, each with the AC it must fail:

| mutation | must fail |
|---|---|
| `-i` keep→DROP | AC-1 (set difference) |
| `-F` keep→drop | AC-1 |
| remove the corpus filter | AC-5 |
| remove R1b's pruning | AC-6 |
| drop the upper-case `--include`s | AC-5b (`src/C.PY` is in the corpus and must be taught) |
| remove the all-present short-circuit | AC-12 (`facts.log` grows) |
| restore the hardcoded kind set | AC-7 (`.sh`) |
| `cwd` instead of `realpath(cwd)` | AC-7 (symlinked cwd) |
| skip `os.setsid()` | AC-10 |
| read the switch on `project_root` | AC-11 7b |
| remove the log write on `timeout` | AC-14 |
| remove a long-form row | AC-1b |
| remove a space-form long value row (`--include G`) | AC-1c (`unknown-flag:--include`) |
| add the pruning flags on a non-recursive re-run | AC-4b (`no-hits`, exit 1, instead of `tool-error`) |
| give AC-4's missing operand no corpus extension and always add `--include`s | AC-4 (exit 0, not 2) |
| omit the sidecar write in `_learn_grep_hits` | AC-15 (rows without provenance) |
| hash the `file:line:` prefix instead of the TEXT | AC-15 (`line_hash` mismatch) |
| record the pruning flags in `match_argv` | AC-15 (`match_argv=[]`) |
| default a missing `--spawned-by` to `shim` | AC-16 |

{#tests}
