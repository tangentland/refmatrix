---
gmd: "0.1"
id: task-16.1-argv-faithful-learner
title: "Task 16.1: a learner that re-runs the caller's own search in canonical form and teaches exactly its lines"
tags: [task, grep, learning, hooks]
metadata:
  node_type: task
  status: pending
  created: 2026-10-06
---

# Task 16.1: the argv-faithful learner {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending
> Depends on: — (plan-16 itself waits on `bsd-r1-remedy` merging)

rel: part-of -> [[plan-16-invisible-grep-shim]]

## Why {#why}

Today's teach ping (`bin/rmxgrep`, plain mode) rebuilds argv by DROPPING every flag and runs
`rmx grep --limit 3 PAT PATHS`. That has four consequences:

- **The case is wrong.** `-i` is gone, and since bug-077 the floor is case-sensitive, so a `-i`
  search re-runs case-sensitively and misses the hits the caller saw.
- **Literal patterns become regexes.** `-F` is gone, so `-F 'a|b'` is re-run as a regex.
- **The regex dialect changes.** The re-run goes through rmx's own `rg` floor. BSD grep's BRE
  (`\b`, `^` and `\|`, a GNU extension) is re-interpreted, so taught lines can differ from what
  the caller's grep matched. Both false negatives found on 2026-10-06 have this shape.
- **Learned paths depend on the cwd.** `_learn_grep_hits` stores whatever spelling the floor
  emitted, so a relative argv teaches relative paths (ch-bsd r3 #s-6).

A learner is faithful when the lines it teaches are the lines the caller's own command matched,
no more and no fewer, up to a stated cap. {#why-lead}

## Requirements {#requirements}

**R1. Re-run the SAME tool with the caller's MATCHING rules.** The learner execs the binary the
shim was about to exec (`$REAL` in `rmxgrep`, real `rg` in `rmxrg`). It does not use rmx's floor.
This makes the dialect the caller's by construction.
- Argv is classified token by token from a table, one table per tool, written in ONE module.
- Match-affecting flags are kept verbatim.
- Output-shaping flags are dropped.
- Canonical output flags are appended.
- If the argv holds any learn-killing flag, nothing is taught and the reason is recorded.
{#r1}

| class | grep (BSD/GNU) | rg |
|---|---|---|
| keep (match) | `-i -y -w -x -F -E -G -P -e PAT -f FILE -r -R --include --exclude --exclude-dir -a -U -z`, `--` | `-i -s -S -w -x -F -e PAT -f FILE -g GLOB -t TYPE -T TYPE -u -uu -uuu --hidden --no-ignore* -L -P -U --multiline-dotall -a -z`, `--` |
| drop (shape) | `-c -l -o -q -s -h -H -n -b -m N -A N -B N -C N --color* --label --line-buffered -Z --null -T` | `-c --count-matches -l -o -q -n -N -H -I --heading --no-heading -m N -A N -B N -C N --color* --json --vimgrep -0 --null -r REPL --column -b --trim -M N --max-columns-preview` |
| kill (teach nothing) | `-v -L --files-without-match` | `-v --files-without-match --files --type-list --passthru` |
| append (canonical) | `-n -H --null` | `-n -H --null --no-heading --color never` |

- **An unknown flag kills the teach.** It is never kept on faith, because an unknown shaping flag
  breaks the parse. The reason is recorded as `unknown-flag:<tok>`. {#r1-unknown}
- **The table is evidence, not memory.** Before it is written, each row is checked against
  `/usr/bin/grep --help`, `man grep` and `rg --help` on this machine. The spec's table is a
  starting point, and the implementation summary records every row it changed. {#r1-table}
- **No input means no teach.** Stdin is always `/dev/null`. A grep with no file operand and no
  `-r` would read stdin, so it teaches nothing (`reason=no-operand`). {#r1-stdin}

**R2. Parse the canonical output exactly.**
- With `--null` the filename ends at the first NUL. Then comes `LINE:TEXT`. A filename that
  contains `:` must parse correctly; that is a test.
- Each hit is `{file: abspath, line: int}`, where `abspath = os.path.normpath(os.path.join(cwd,
  file))`.
- Never `Path.resolve()`. The spelling is the identity
  (`impression_bsd_substring_signature_widens`), and a symlink is not merged into its target.
{#r2}

**R3. Teach through the existing queue.** Hits go through `learn_queue.enqueue(root, pattern,
hits)`, the same file-append the grep fallback uses. That means no socket and no daemon, and the
daemon's drain applies it. `pattern` is the single pattern operand. With more than one pattern
(`-e a -e b`, `-f FILE`), hits cannot be attributed to a pattern, so nothing is taught
(`reason=multi-pattern`). {#r3}

**R4. Bounded on every leg.**
- At most `RMX_GREP_LEARN_MAX_HITS` hits (default 500) are taught; the rest are counted as
  `truncated`.
- The child tool runs under a wall-clock cap, `RMX_GREP_LEARN_TIMEOUT_S` (default 10). On expiry
  the child's process group is killed and partial hits are discarded. A partial grep is not a set
  of lines the caller matched in any defined order.
- The learner never waits on the daemon. {#r4}

**R5. Learn switch and throttle.**
- `learn_switch.learning_enabled(root)` is checked first.
- The per-invocation throttle stamp stays where it is: the shim (16.2) owns it, because it must be
  checked before a process is spawned. {#r5}

**R6. Never silent (CLAUDE.md#no-silent-failures).** Every invocation appends exactly one JSONL
record to `<root>/.refmatrix/grep-learn.log`. The record carries:
- `ts`, `tool`, `cwd`, `argv_sha`
- `outcome`, one of `taught`, `no-hits`, `skipped`, `timeout`, `error`
- `reason`, `hits`, `truncated`, `ms`

`rmx learn status` gains a line counting the last 24 h by outcome and by reason. Failures that
cannot be logged go to stderr, which the detached spawn discards, so the log is the record. A
test asserts one record per call on every outcome. {#r6}

**R7. One entry point, not a verb.**
- The entry point is `rmx grep-learn --tool {grep,rg} --cwd DIR -- ARGV...`, a HIDDEN click
  command.
- It is not a verb: `verbs.VERBS` is exactly the MCP tool set (`tests/test_verb_parity.py`
  rule 1), and a learner that only a hook calls is not an agent capability.
- The logic lives in `src/refmatrix/grep_learn.py`. The click command is a thin adapter, so 16.3's
  Grep-tool hook reaches the same function.
- Startup must not import the store, models or DuckDB. The import set is asserted. {#r7}

## Acceptance criteria {#acceptance}

1. **Flag fidelity, per row of R1, against the real tool as the control.** For each keep flag and
   for each tool, the taught `(file, line)` set equals the set `/usr/bin/grep -nH --null <same
   matching argv>` (or `rg …`) prints on a fixture tree. At minimum, cover `-i`, `-w`, `-x`, `-F`
   with `|` in the pattern, BRE `\b`, BRE `^` anchor, ERE `-E 'a|b'`, `-r` over a directory,
   `--include`, rg `-g` and rg `-t`. Every case is RED before the implementation.
2. **Shaping flags do not change what is taught.** `-c`, `-l`, `-o`, `-h` and `-C 2` each teach
   the same set as the bare invocation.
3. **Kill flags teach nothing and log their reason.** `-v`, `-L`, an unknown flag, multiple
   patterns, and no operand each produce `outcome=skipped` with the right `reason`.
4. **Paths are absolute and spelling-true.** A relative-argv invocation from a subdirectory teaches
   absolute paths. Over a symlink and its target named separately, two different `file`s are
   taught.
5. **A filename containing `:` parses correctly.**
6. **The bounds hold.**
   - With `MAX_HITS=5` over a 50-hit fixture, 5 hits are taught and `truncated=45`.
   - A child that cannot finish (a FIFO operand) is killed at the timeout: wall < timeout + 1 s,
     `outcome=timeout`, nothing taught.
7. **The learn switch holds.** `RMX_LEARN=0` gives `outcome=skipped`, `reason=learning-disabled`,
   and no queue write.
8. **The log is complete.** Exactly one record per call across all outcomes above, and `rmx learn
   status` shows the counts.
9. **The import is light.** `python -X importtime -m refmatrix.grep_learn` imports no `duckdb`,
   `lance`, `torch` or `sentence_transformers`.
10. **The real drain works.** Taught records are drained by the real `Daemon._drain_learn_queue`
    into a real `Store`, and `rmx grep PATTERN` (explicit, path-less) then answers from the index
    with the taught lines.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/grep_learn.py` (new) | flag tables, classify, re-run, parse, enqueue, log |
| `src/refmatrix/cli.py` | hidden `grep-learn` command; `learn status` 24 h outcome counts |
| `src/refmatrix/learn_queue.py` | none expected; if the hit shape needs a field, it is added here once |

## Test strategy {#test-strategy}

- `tests/test_grep_learn.py`: real binaries (`/usr/bin/grep`, `rg`, skipped if absent with the
  reason printed), a real fixture tree under `tmp_path`, a real store root for the queue and log.
  Nothing in the learner is patched.
- The control for every fidelity case is the real tool's own `-nH --null` output, run in the test.
  The fixture is never asserted by hand-written expected lines alone.
- AC-10 uses the real drain function on a real `Store`, as `tests/test_grep_learned_reachable.py`
  does.
- Mutations to pre-register in the summary:
  - drop one keep-flag row (`-i`): AC-1 must fail;
  - replace `normpath` with `resolve`: AC-4 must fail;
  - remove the log write on the `timeout` path: AC-8 must fail. {#tests}
