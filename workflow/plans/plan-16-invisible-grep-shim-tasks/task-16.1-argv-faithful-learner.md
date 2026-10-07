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
> Status: Pending (revision 2, after ch-bsd spec review `bsd-plan16-spec-review-b587621`)
> Depends on: — (plan-16 itself waits on `bsd-r1-remedy` merging)

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: amends -> [[bsd-plan16-spec-review-b587621]]

## Why {#why}

Today's teach ping (`bin/rmxgrep`, plain mode) rebuilds argv by DROPPING every flag and runs
`rmx grep --limit 3 PAT PATHS`. That does four kinds of damage:

- **`-i` is lost.** A `-i` search re-runs case-sensitively, because the floor has been grep-case
  since bug-077, and so misses the hits the caller saw. Probed live: `-i foo a.txt` was rebuilt as
  `grep --limit 3 foo a.txt`.
- **`-F` is lost.** `-F 'a|b'` is re-run as a regex.
- **The dialect changes.** The re-run goes through rmx's own `rg` floor, which re-interprets BSD
  grep's BRE (`\b`, `^`). Both 2026-10-06 false negatives (bug-081) had this shape.
- **Learned paths depend on the cwd.** That one was fixed at the floor in 321ff97 (r3 #s-6), and the
  learner must not reintroduce it.

**Faithful** means the learner teaches the lines the caller's command MATCHED, under the caller's
own matching rules and match cutoffs, restricted to files that belong to the store's corpus, up to a
stated cap. It is no wider than that and no narrower. {#why-lead}

## Roots, named once (spec review #b-4) {#roots}

| name | value | used for |
|---|---|---|
| `store_root` | `<project>/.refmatrix`, found from the caller's cwd the way the shim finds it, then `realpath` | `learn_switch.decision(store_root)`, `learn_queue.enqueue(store_root, …)`, `<store_root>/grep-learn.log` |
| `project_root` | `realpath(store_root.parent)` | the corpus predicate, relativisation |
| `cwd` | the caller's cwd, passed by the shim (`--cwd "$PWD"`) | resolving the tool's relative output paths |

No requirement below says "root" without one of these names.

## Requirements {#requirements}

**R0. Detach first (#s-1).** The first statements of `grep_learn` are `os.setsid()` and closing
inherited fds above 2. Every child is started with `start_new_session=True` and `close_fds=True`. The
learner's process group never equals the caller's. `/bin/sh` `&` + `disown` does not do this
(measured: the ping's pgid was the pipeline's).

**R0b. Concurrency bound (#s-2).** At most `RMX_GREP_LEARN_MAX_INFLIGHT` learners run per store
(default 2). Each slot is an `fcntl.flock` on a file under `<store_root>/.grep-learn-slots/`. A
learner that gets no slot exits at once with `outcome=skipped reason=busy` logged. A shell loop over
N files therefore starts N short-lived processes but runs at most 2 searches.

**R1. Re-run the caller's binary with the caller's MATCHING rules and CUTOFFS.**
- The shim passes its resolved real binary as `--bin ABS` (#s-6), because PATH holds `./` and an
  empty entry. The learner execs exactly that path with `stdin=/dev/null`.
- Argv is classified token by token from ONE table per tool, in `grep_learn.py`.
- Rows are taken from `/usr/bin/grep --help`, which on this machine is BSD grep 2.6.0-FreeBSD:
  usage `[-abcdDEFGHhIiJLlMmnOopqRSsUVvwXxZz] … [--binary-files] [--context] [--directories]
  [--label] [--line-buffered] [--null]`.
- The rg rows are taken from `rg --help` (15.1.0).
- The table below is the spec's starting point, re-checked at build time. Every row the build
  changes is listed in the summary. {#r1}

| class | grep (BSD 2.6.0) | rg (15.1.0) |
|---|---|---|
| keep: match | `-i -y -w -x -F -E -G -e PAT -r -R -S -O -p --include --exclude --exclude-dir -a -I -U -d ACT -D ACT --binary-files=V` | `-i -s -S -w -x -F -e PAT -g GLOB -t T -T T -u -uu -uuu --hidden --no-ignore* -L -P -U --multiline-dotall -a --binary` |
| keep: cutoff (#s-10) | `-m N`; `-l`/`--files-with-matches` → re-run as `-m 1` (the caller matched one line per file); `-q` → `-m 1` plus a stop after the first file with a hit | `-m N`; `-l` → `-m 1`; `-q` → first hit only |
| drop: shape | `-c -o -s -h -H -n -b -A N -B N -C[N] --context[=N] --color* --label --line-buffered --null` | `-c --count-matches -o -n -N -H -I --heading --no-heading -A N -B N -C N --color* --column -b --trim -M N --max-columns-preview -0 --null` |
| kill: teach nothing | `-v -L -f FILE` (#s-10: `-f` is multi-pattern, so not a keep row), `-z` (`--null-data`: every hit becomes line 1, measured), `-Z`/`-J`/`-X`/`-M` (gzip/bz2/xz/lzma decompress: line numbers refer to the decompressed text), `-P`/`-T` (BSD grep rejects them, exit 2; the caller got an error, not lines), more than one `-e` | `-v --files-without-match --files --type-list --passthru -f FILE`, `--json`/`--vimgrep` (whole-output reformat), `-r REPL` (rg's replace), more than one `-e` |
| append | `-n -H --null` | `-n -H --null --no-heading --color never` |

- **An unknown flag kills the teach** (`reason=unknown-flag:<tok>`). {#r1-unknown}
- **The tool's own exit decides (#s-10).** The learner records the re-run's exit code. Exit 2 (an
  error) teaches nothing (`reason=tool-error`), so a flag the caller's grep rejected can never teach.
- **No-operand, per tool (#s-10).** grep with no file operand and no `-r`/`-R` would read stdin, so
  it teaches nothing (`reason=no-operand`). A path-less `rg` searches the cwd, so it is a valid
  search and is re-run as is.

**R2. Parse canonical output, streaming (#m-3).**
- Read line by line from the child's stdout, never buffered whole.
- With `--null`, the filename ends at the first NUL, then `LINE:TEXT`. A filename containing `:`
  parses correctly; that is a test.
- A `Binary file X matches` line is counted as `binary` and teaches nothing.
- Path: `os.path.normpath(os.path.join(os.path.realpath(cwd), file))`. Directory symlinks in the
  CWD are resolved, so the base agrees with the daemon's `resolve()`d `project_root` (#s-7). The
  file component's own spelling is kept, so a symlinked FILE is not merged into its target.

**R3. Keep only CORPUS hits, before the cap (#b-1).**
- A hit is taught only if `corpus.is_relevant(path, project_root)` is true AND the path lies under
  `project_root`.
- `corpus.is_relevant` is the predicate the watcher already uses (`watch.is_relevant`: supported
  extension, no `IGNORE_DIRS` segment, no dot segment, `.refmatrix_ignore`).
- That predicate is MOVED into a module that imports neither watchdog nor the store, and
  `watch.py` re-exports it. There is ONE predicate, not a copy.
- The filter runs as hits stream in, BEFORE the cap. Drops are counted as `out_of_corpus` on the
  log record.
- Without this, BSD `grep -r` (which ignores `.gitignore`) teaches `.refmatrix/` logs, which contain
  the pattern itself, `.venv-eval/` site-packages and catalog binaries, all as PROTECTED entities
  that `prune_noise` never removes.

**R4. Bounded on every leg, the store included (#b-5).**
- At most `RMX_GREP_LEARN_MAX_HITS` corpus hits per call (default 200). The remainder is counted as
  `truncated`, and the child is killed once the cap is reached rather than read to the end.
- A wall-clock cap, `RMX_GREP_LEARN_TIMEOUT_S` (default 10). On expiry, the child's session is
  killed, partial hits are discarded, and `outcome=timeout` is logged.
- **Store-side idempotence.** `daemon._learn_grep_hits` skips any `(concept, entity, line)` evidence
  row that already exists. Today `Store.add_evidence` is an unconditional INSERT, and the queue
  dedupes only within one drained batch. That way a re-taught argv every TTL cannot grow
  `linkage_evidence`, which was bug-058's duplicate-row cause.

**R5. The learn switch, on `store_root` (#b-4).** `learn_switch.decision(store_root)` is checked
before any process is started. That decision includes the store marker, the global marker and the
env, and it reports an unreadable marker per bug-080. The shim's throttle (16.2) stays in the shim.

**R6. Never silent.** Each invocation appends exactly one JSONL record to
`<store_root>/grep-learn.log`. The record holds:
- `ts`, `tool`, `bin`, `cwd`, `argv_sha`;
- `outcome`, one of `taught`, `no-hits`, `skipped`, `timeout`, `error`;
- `reason`, `hits`, `out_of_corpus`, `binary`, `truncated`, `tool_exit`, `ms`.

`rmx learn status` prints last-24 h counts by outcome and by reason. A test asserts exactly one
record per call on every outcome. The log rotates at 5 MB, keeping one predecessor.

**R7. One entry point, not a verb.**
- The entry point is `rmx grep-learn --tool {grep,rg} --bin ABS --cwd DIR -- ARGV...`, a hidden
  click command that goes on `verbs.INTERNAL_CLI` once task 3.4 lands. It is not a verb, because
  `verbs.VERBS` is exactly the MCP tool set.
- The logic lives in `src/refmatrix/grep_learn.py`. Startup imports no `duckdb`, `lance`, `torch`,
  `sentence_transformers` or `watchdog`.

**R8. Matching rules at read time (#s-8).** The queue record stays `{pattern, hits}`, and the
concept stays `query/<pattern>`. Explicit `rmx grep` re-verifies lines under ITS caller's rules
(bug-074/077), so lines taught by a `-i` search answer `rmx grep -i PAT` and are correctly dropped
for a case-sensitive `rmx grep PAT`. This is stated, and AC-10 tests it, rather than encoding flags
into the concept.

## Acceptance criteria {#acceptance}

1. **Flag fidelity, with proven power (#s-9).** Covers each keep row the build supports, per tool,
   and at minimum: `-i`, `-w`, `-x`, `-F` with `|`, BRE `\b`, BRE `^`, ERE `-E 'a|b'`, `-r` over a
   directory, `--include`, `-m 2`, `-l`, rg `-g`, rg `-t`.
   - (a) **Power:** on the fixture, the real tool's `-nH --null` output WITH the flag differs from
     the output WITHOUT it. A case whose flag changes nothing is not a test.
   - (b) **Fidelity:** the taught `(file, line)` set equals the real tool's output with the flag,
     corpus-filtered.
   - (c) **Red:** each case fails against a stub `grep_learn` that drops the flag. That failure must
     be the set difference, not an `ImportError`.
2. **Shape flags change nothing.** `-c`, `-o`, `-h`, `-C 2` teach the same set as the bare
   invocation.
3. **Cutoffs are honoured.** `-m 1` over a 3-hit file teaches 1. `-l` over two files teaches one
   line per file.
4. **Kill rows teach nothing and log their reason.** Covers `-v`, `-L`, `-f`, `-z`, `-P`, two
   `-e`, an unknown flag, grep with no operand, and a tool exit of 2.
5. **Corpus (#b-1).** A fixture whose tree holds the pattern in `.refmatrix/query.log`,
   `.venv-eval/x.py`, `__pycache__/x.pyc`, a path in `.refmatrix_ignore` and `src/a.py` teaches
   exactly `src/a.py`'s line, with `out_of_corpus=4`. A 300-hit `.venv-eval/` file placed FIRST in
   walk order does not displace `src/a.py` from the cap.
6. **Paths and identity (#s-7).** A relative-argv call from a subdirectory teaches absolute paths.
   The taught entity id EQUALS the id `ingest` gave the same file, whether the cwd is reached
   directly or through a symlinked directory. A symlinked FILE and its target named separately are
   two entities.
7. **Parse.** A filename containing `:` parses. A `Binary file … matches` line counts as `binary`.
8. **Bounds.**
   - `MAX_HITS=5` over a 50-hit fixture teaches 5 with `truncated>0`, and the child is gone within
     1 s of the fifth hit.
   - A FIFO operand times out: wall < timeout + 1 s, `outcome=timeout`, nothing taught.
   - Three concurrent learners with `MAX_INFLIGHT=2`: exactly one `reason=busy`.
9. **Detached (#s-1).** The learner's pgid differs from its spawner's. After `killpg(spawner's
   group)`, the learner still finishes and logs.
10. **The switch on the right root (#b-4).**
    - `RMX_LEARN=0` gives `skipped`.
    - **7b:** with `RMX_LEARN` UNSET and a per-store `learn.off` at `store_root`, the result is
      `skipped reason=learning-disabled` and the queue file is unchanged.
    - **7c:** a global marker gives the same result.
11. **Idempotent store (#b-5).** Teach the same argv twice (TTL 0), drain through a real `Daemon`
    built on `store_root` after each, and the `linkage_evidence` row count is unchanged after the
    second drain.
12. **End to end through the real drain.**
    - The queued records are drained by `Daemon._drain_learn_queue` on a real `Store` at
      `store_root`. Then explicit path-less `rmx grep PAT` answers from the index with the taught
      lines.
    - For a `-i` teach over a mixed-case fixture, `rmx grep -i PAT` returns the mixed-case lines and
      `rmx grep PAT` does not (R8).
13. **Log completeness.** Exactly one record per call across every outcome above. `rmx learn status`
    shows the counts.
14. **Light import.** `python -X importtime -c 'import refmatrix.grep_learn'` lists none of
    `duckdb`, `lance`, `torch`, `sentence_transformers`, `watchdog`.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/grep_learn.py` (new) | detach, slots, tables, classify, re-run, stream-parse, corpus filter, enqueue, log |
| `src/refmatrix/corpus.py` (new) | `is_relevant` + `IGNORE_DIRS` + `SUPPORTED_EXTS` + `load_ignore_spec`, moved from `watch.py` (re-exported there) |
| `src/refmatrix/daemon.py` | `_learn_grep_hits` skips existing `(concept, entity, line)` evidence |
| `src/refmatrix/cli.py` | hidden `grep-learn`; `learn status` 24 h outcome counts |
| `src/refmatrix/verbs.py` | `grep-learn` on `INTERNAL_CLI` (if task 3.4 has landed; otherwise noted in the 3.4 row) |

## Test strategy {#test-strategy}

- `tests/test_grep_learn.py` uses real `/usr/bin/grep` and `rg` (skipped with a printed reason if
  either is absent), a real fixture tree, and real `store_root` queue and log files. Nothing in
  `grep_learn` is patched.
- AC-11 and AC-12 use a real `Daemon` and `Store`, as `tests/test_grep_learned_reachable.py` does.
- Pre-registered mutations:
  - move `-i` from keep to DROP: AC-1 fails on its set difference, which is the defect this task
    exists to remove;
  - move `-F` from keep to drop: AC-1 fails;
  - remove the corpus filter: AC-5 fails;
  - remove the `_learn_grep_hits` dedupe: AC-11 fails;
  - use `cwd` instead of `realpath(cwd)`: AC-6 fails under the symlinked cwd;
  - skip `os.setsid()`: AC-9 fails;
  - read the switch on `project_root`: AC-10 7b fails;
  - remove the log write on `timeout`: AC-13 fails. {#tests}
