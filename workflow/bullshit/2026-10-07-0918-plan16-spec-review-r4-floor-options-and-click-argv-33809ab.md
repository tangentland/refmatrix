---
gmd: "0.1"
id: bsd-plan16-spec-review-r4-33809ab
title: "plan-16 spec review r4: d-4's table holds on the hand-off route, but the path-less floor re-opens b-r3-1, and routing runs on click's leftover argv, which eats `--` and misroutes d-4's own `--file=` row"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim
task: spec-review-16.1-16.5
round: 4
tags: [bsd, audit, spec-review, grep, drop-in, learning, hooks, measurement]
---

# ch-bsd spec review of plan-16, round 4 (pre-implementation) {#root}

**Commit reviewed:** `33809ab` (revision 4 of the plan and tasks 16.1-16.5). HEAD `92c374c`, branch
`bsd-r1-remedy`. **Written:** 2026-10-07T09:18:52-0700.

**Method:** I read the plan and all five specs, and checked them against the code at HEAD
(`cli.py` `grep()`, `_parse_grep_flags`, `_split_grep_argv`, `_grep_bare_flags`, `cli_entry`;
`watch.py` `is_relevant`; `daemon._learn_grep_hits`). I also ran live probes in my scratchpad:

- click 8.3.3 parsing, using a replica command with `grep()`'s exact options and context settings,
  plus the real `_split_grep_argv` and `_parse_grep_flags`;
- BSD grep 2.6.0, for include/exclude order, a directory operand without `-r`, a writerless FIFO, and
  `--no-ignore-case`;
- `$PWD` against `os.getcwd()`;
- a quote-aware scan of the project's 66 transcripts (15 top-level and 51 subagent; 8,558 Bash
  calls, of which 2,174 heredoc or unparseable calls were skipped).

Nothing in `src/`, `tests/`, the live store, INDEX.md, IMPRESSIONS.md or last_run.log was touched.
No suite was run and no mutation was made. I did not reopen d-1, d-2, d-3, d-4, the kept precision
gate, or 16.5 option 1.

rel: amends -> [[bsd-plan16-spec-review-r3-c8278b1]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]
rel: contradicts -> [[claude#no-silent-failures]]

## Live evidence {#evidence}

### Click and the argv split {#ev-click}

These come from the replica command, with `_split_grep_argv` and `_parse_grep_flags` from HEAD:

| input | result |
|---|---|
| `-f '-c' '^+'` | `flags='-c'` |
| `--flags=-c x` | `'-c'` |
| `-f-c x` | `'-c'` |
| `-fc x` | `'c'`; the bundle parser then raises `UsageError` (loud) |
| `--flags= x f` | an empty bundle (harmless) |
| `-f pats.txt x f` | `UsageError: 'pats.txt' is not a grep-style flag` (loud) |
| `-f -i -f -c x f` | `flags='-c'`. **The first bundle is silently dropped** (click keeps the last value) |
| `-if pats.txt x f` | click takes `f` out of the grep cluster: argv `['-i','x','f']`, `flags='pats.txt'`, then `UsageError` |
| `-- -x f.txt` | **click EATS `--`**: argv `['-x','f.txt']`. The split gives flags `[-x]`, pattern `f.txt`, and **no paths** |
| `-c -- -foo f.txt` | argv `['-c','-foo','f.txt']`. `-foo` is now a flag |
| `--file=pats.txt f.txt` | passes click unchanged. The split gives flags `[--file=pats.txt]`, pattern `f.txt`, **paths `[]`** |
| `--file pats.txt f.txt` | the split gives pattern `pats.txt` and paths `[f.txt]`. It routes as named, but only by accident |
| `-e a -e b` | the split gives pattern `b` and flags `[]`. **Both `-e` tokens leave the flag list** |
| `-d skip foo` | the split gives pattern `skip` and paths `[foo]`. `-d` is not in `_GREP_VALUE_FLAGS` |

`_parse_grep_flags` returns a dict of booleans, not tokens. Its letters are `irIRnLlcvwFEHho`. `r`
and `R` set nothing, and `I` sets `ignore_case=False`.

### BSD grep 2.6.0 {#ev-bsd}

- **Include and exclude order.** With the pruning `--include`s FIRST and a caller
  `--exclude='*.md'`, the call returns `a.py` and `b.txt`. `a.md` stays excluded, so ordering
  closes s-r3-1. With the pruning `--include`s first and a caller `--include='*.py'`, it returns
  `a.py`, `b.txt` and `a.md`: the caller's filter is WIDENED. That is why R1b's omission rule is
  needed.
- **Case.** `C.PY` is not matched by `--include='*.py'`, but `is_relevant` lowercases the suffix,
  so the file is in the corpus.
- **Directory operand.** `grep -i alpha d` without `-r` prints `grep: d: Is a directory`, rc 2,
  and no hits.
- **FIFO.** `grep alpha ff` on a FIFO with no writer is still blocked after 3.0 s (it blocks in
  `open`).
- **No case-sensitive override.** `grep --no-ignore-case` gives `unrecognized option`, rc 2. BSD
  grep has no flag that undoes `-i`.

### Shell and runtime facts {#ev-runtime}

- **cwd.** With cwd `/tmp`, `$PWD` is `/tmp` and `os.getcwd()` is `/private/tmp`.
- **`cli_entry`.** It writes the `cli.log` record in a `finally`, which an `os.execv` never reaches.
- **Plan-14's harness.** `eval/production/grep_learning_replay.py` reads `answered_by`.

### Transcripts {#ev-transcripts}

- **Explicit `rmx grep`.**
  - There are 428 segments. 34 of them are path-less and not piped:
    - 8 carry a BRE meta, mostly `$var` text and escaped `\.`/`\(`;
    - **0 are dot-only identifiers** such as `os.path`;
    - 25 route to the index under R3;
    - 1 carries `-rn`, which is not index-expressible.
  - rmx's own options across 464 occurrences: `--no-learn` 11, **`--` 8**, **`--limit` 7**,
    **`--no-fallback` 4**, `-f`/`--flags` 3.
- **All grep/rg segments with a pattern (4,211).**
  - 56.6% carry a BRE meta, `\|` included.
  - 13.6% contain `.`.
  - 6.6% have the `ident.ident` shape. After 16.2, those all go to the real grep through the shim,
    so R3's `.` rule touches only the explicit command.
- **The forward-join approximation, applied to 2,824 producing segments:**
  - 240 (8.5%) have two or more same-call candidates whose pattern appears literally in the
    segment, so they are `ambiguous`;
  - 151 (5.3%) sit inside a `for`/`while`/`xargs`, so one segment yields N records;
  - 67 (2.4%) have a `$`/backtick pattern;
  - 101 (3.6%) have an argv pattern that is NOT a literal substring of the command text, because of
    escaped quotes inside double quotes. These match no record.
  - Cross-transcript concurrency: 292 of 1,853 grep calls overlap another transcript's grep call in
    the same cwd, but only 3 share a pattern literal. Concurrency is negligible once the
    pattern-literal rule applies.

## Status of prior findings {#prior-status}

### r3 findings {#status-r3}

| id | status | evidence |
|---|---|---|
| b-r3-1 rmx options on the exec route | **partially closed** | d-4 table, `translate_rmx_options`, AC-3 (`--limit` refused, `-f '-c -i'` expands, `--file=` reaches grep), R2/R5 `-f '-c'` pipe case, mutation "treat `-f` as pattern file". Holes: [[#b-r4-2]] (click eats `--`; `--file=` misroutes; `-f` twice drops silently), [[#s-r4-1]] (`-I`/`r` bundle semantics) |
| b-r3-2 path-less flags orphaned | **closed** | R3 routes every non-index flag to `grep -r <pruning FIRST> <caller flags> PAT <root>`; AC-5 `-A2`/`--include`/`alpha$`; mutation "floor drops `-i`". New sibling: rmx's OWN options on that floor, [[#b-r4-1]] |
| s-r3-1 R1b append vs last-match-wins | **closed** | R1b "BEFORE the caller's tokens" + omission of `--include` when the caller passed one; both probed. Residue: line 102 still says "APPENDS" ([[#m-r4-2]]) |
| s-r3-2 two dialects / `\|` refusal first | **partially closed** | BRE patterns route to the floor, the refusal is deleted, and bug-081 is fixed by R3. But AC-5's "route BRE to the index" mutation survives on a store without `query/alpha$` rows (the miss falls to the floor anyway). r3's "same pattern on a store that HAS rows" was not adopted: [[#s-r4-2]] |
| s-r3-3 one shared spawn vs shell | **closed** | 16.2 R2b: two implementations + `tests/test_spawn_parity.py`. Residue: `$PWD` vs `getcwd` ([[#m-r4-5]]) |
| s-r3-4 R6 marks live code deleted | **closed** | 16.5 R8 lists the rows one by one. 076/077/078/083/084 stay. #why carves out 061/065 |
| s-r3-5 documented callers | **closed** | 16.5 R7 (`agent-doc-primer.md:49-52`, docstring, `hooks.py` comment, README) + a scan test, AC-8 |
| s-r3-6 historical oracle = rmx rendering | **closed** | 16.4 R1: excluded and counted; about 9 remain; the gate rests on the forward oracle |
| s-r3-7 forward join text vs argv; unkeyed throttle | **partially closed** | An approximate join with `ambiguous` counted, `ts` = learner start, and keyed lines were added. But the exact-join text was not removed, the route-2 rule is still text equality, zero-candidate segments still count as route 3, and 16.2 R2/AC-6 still say "one byte": [[#s-r4-4]], [[#s-r4-5]] |
| s-r3-8 co-output + Grep paging | **closed** | 16.4 R3 conditions 7 and 8; 16.3 paging paragraph |
| s-r3-9 insufficient-n closure | **closed** | 16.4 closure rule: not `completed` below n = 30; the user decides at 16.2 + 14 days. Anchored |
| s-r3-10 Grep single-file branch | **partially closed** | Modelled as `reason=single-file-filter`, but no AC or mutation exercises it ([[#m-r4-4]]) |
| m-r3-1 `.detached` markers | **closed** | 16.1 R0: removed on exit, reclaimed, the shim counts `slot-*.d` only |
| m-r3-2 grep table gaps | **closed** | `--mmap` and `--include-dir` are keep rows; `--bz2decompress`/`--xz`/`--lzma` are kill rows (man page: `-J, --bz2decompress`) |
| m-r3-3 extraction/hook details | **partially closed** | The anchor is re-stated, the cache is keyed on (path, size, mtime), the brace rule is fixed, and AC-1 stays below the paging limit. The `no-rg` skip goes to the shim's `busy` file in a different line format, from a hook that has no `store_root`: [[#s-r4-4]] |
| m-r3-4 16.5 ACs | **closed** | `rg -w` deletion check, the `-L` and dotfile rows, the 16.2 dependency, the REAL learner. New defect in the rewritten AC: [[#s-r4-3]] |
| m-r3-5 exec drops telemetry | **partially closed** | R6 writes the `query.log` row before the exec. The `cli.log` exit record is still lost: [[#m-r4-3]] |
| m-r3-6 stale plan lines | **open** | Only "Next gate" was fixed. Header line 15 says "revision 3 … Awaiting a third review"; the out-of-scope bullet still contradicts 16.5; #why still says "bug-058 to bug-066": [[#m-r4-1]] |

Tally: **11 closed, 6 partially closed, 1 open.**

### Carried partials from r3 {#status-carried}

| id | status | evidence |
|---|---|---|
| s-n6 pin cannot see upgrade | **closed** | Content anchor on the emitter, not on members; cache; AC-5 re-extracts from the installed binary |
| m-n7 route-2 rule | **open** | 16.4 R1 line 67 still defines route 2 as "argv appears in no top-level segment", which is text equality, so every expanded argv reads as route 2 ([[#s-r4-5]]) |
| b-3 Grep-tool argv | **partially closed** | The single-file and paging branches are modelled in text; the AC gap is [[#m-r4-4]] |
| m-1 stale plan | **partially closed** | Through m-r3-6 ([[#m-r4-1]]) |

## New findings {#findings}

### BULLSHIT: rmx's index-only options on the path-less FLOOR are undefined, which is b-r3-1 again on the sibling route {#b-r4-1}

**Spec:** 16.5 R3, d-4 table, AC-3, AC-5
**What:** R3 lists `--limit`, `-k`, `--linkage` and `--no-fallback` as index-expressible, and runs
the floor "on an index miss" with "the caller's translated flags". d-4 REFUSES exactly those options
on the hand-off route, with exit 2. Three readings are possible, and the spec picks none:

- `rmx grep -k code foo` that misses either exits 2 AFTER the index read, or the floor drops `-k`
  and returns docs too, which is a silently wider answer.
- `rmx grep --no-fallback foo` that misses still runs the floor, which inverts the option.
- `rmx grep --limit 5 'x$'` is either refused or uncapped.

AC-3 covers only the named-path refusal, and AC-5 uses no rmx option. So no AC can fail on this.
The transcripts show 7 `--limit` and 4 `--no-fallback` uses across 464 explicit calls.
**Why it is bullshit:** r3 blocked on "which argv, which option" for the exec route. The revision
answered it for that route and created a second grep route that has the same unanswered question.
This is bsd-pattern-sibling-render-path, so it escalates.
**Fix:**
- Give R3 its own option table for the floor:
  - `-k`/`--linkage`: refuse on the floor route, or skip the floor and say so;
  - `--no-fallback`: no floor, exit 1 on a miss;
  - `--limit`: caps the floor's output, with the truncation said on stderr, as today.
- Add AC-5 rows for each option on an index miss, with a mutation that drops `-k` on the floor.

rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT: routing and translation run on click's leftover argv, which eats `--` and misroutes d-4's own `--file=` row {#b-r4-2}

**Spec:** 16.5 d-4 (`translate_rmx_options(argv)`, the `--file=FILE` and "anything else verbatim"
rows), R1/R3 routing ("named paths" vs "path-less"), AC-3
**Evidence:** probed on click 8.3.3 ([[#evidence]]).

- **`--` is consumed by click.**
  - `rmx grep -- -x f.txt` leaves argv `-x f.txt`. That is handed to grep verbatim, where it means
    pattern `f.txt` read from stdin. It also routes PATH-LESS, because the split finds no paths.
  - The command's own docstring says "A pattern beginning with `-` requires `--`".
  - `--` appears 8 times in transcript `rmx grep` calls.
- **`--file=pats.txt f.txt` splits as pattern `f.txt`, paths `[]`.** It therefore routes
  path-less. The pattern contains a `.`, so it goes to the floor, which runs
  `grep -r <pruning> --file=pats.txt f.txt <root>` and searches the whole tree. The result is a
  wrong answer. AC-3's "`--file=pats.txt` reaches grep" passes, because the floor IS grep.
- **Two `-e` on a path-less call.** The split keeps the last pattern and removes both `-e` from the
  flag list. R3's "every flag is index-expressible" therefore holds, and the index answers `b`
  alone, silently.
- **`-f -i -f -c`.** click keeps the last value, so `-i` is silently dropped.
- **Missing value flags.** `-d ACT`, `-D ACT`, `--label` and the space form of `--binary-files` are
  absent from `_GREP_VALUE_FLAGS`, so their values are taken as the pattern.

**Why it is bullshit:** these are silent wrong answers on rows of the translation table itself, on
a command whose title promises grep's bytes. The R5 differential replays grep argv from 16.2's
fixture, and that fixture has no `--`, `--file=` or repeated `-e`. No AC can see any of these.
**Fix:**
- Name the argv. One parser takes the raw `sys.argv` tail, extracts rmx's options with the SAME
  rules click uses, and keeps `--` and its position. Or use click's
  `context_settings={"allow_interspersed_args": False}` together with a pre-split.
- The routing operand split treats `--file`/`-f`-as-file, `-d`, `-D`, `--label` and
  `--binary-files` as value flags.
- More than one `-e`, or any `--file=`, on a path-less call goes to the floor.
- A repeated `-f`/`--flags` is refused with exit 2, or concatenated, and the spec names which.
- Add R5 rows: `-- -x f.txt`, `-c -- -foo f.txt`, `--file=pats.txt f.txt`, `--file=pats.txt`
  path-less, `-e a -e b` path-less, `-f -i -f -c`.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY: "expanded by the existing `_parse_grep_flags` letters" is undefined for `I`, `r` and `R` {#s-r4-1}

**Spec:** 16.5 d-4, row 1
**What:** `_parse_grep_flags` returns a dict, not tokens, so the spec does not say how the expanded
flags are produced.
- **If it re-emits from the dict,** `r`/`R` are lost, because they set nothing. Then
  `-f '-rl' foo src/` becomes `grep -l foo src/`, which prints `Is a directory` and exits 2.
- **If it passes the letters through literally,** `-f '-I'` changes meaning silently. In rmx, `I`
  is "force case-sensitive"; in grep, `-I` means "skip binary files". BSD grep has no
  `--no-ignore-case` (probed, rc 2).

`_GREP_FLAGS_HELP` still says "-i ignore-case (default ON …)", while the command's own `--regex`
help says "case-SENSITIVE". `-f pats.txt`, a grep user's habit, fails loudly, but the message does
not mention `--file=`.
**Fix:**
- Write a per-letter row: `I` → omit `-i` (or refuse), `r`/`R` → `-r`, and every other letter
  literal.
- Correct the help text.
- Make the `UsageError` for a non-dash bundle name `--file=FILE`.
- Add a unit case for each.

### SKETCHY: two 16.5 ACs cannot fail on the defects they name {#s-r4-2}

**Spec:** 16.5 AC-5, test strategy
- **The floor's oracle is the implementation's own command.** AC-5 compares the floor with
  `grep -r <pruning> … alpha <root>`. If the oracle builds `<pruning>` with the same helper, a
  mutation that always adds the corpus `--include`s survives. That mutation WIDENS
  `--include='*.py'` to return `a.md` and `b.txt` (probed).
- **The routing mutation cannot fail on an empty store.** The mutation "route BRE patterns to the
  index fails `alpha$`" survives when the store has no `query/alpha$` rows: the index misses, the
  floor answers, and the output is identical. r3's s-r3-2 asked for exactly this case, with the same
  pattern on a store that HAS rows.

**Fix:**
- State literal expected file sets for the floor cases (`--include='*.py'` → only `.py` files).
- Seed `query/alpha$` and `query/alpha` rows before the routing cases.
- Pre-register the mutation "always add the pruning `--include`s".

### SKETCHY: 16.5 AC-4's FIFO case hangs or races {#s-r4-3}

**Spec:** 16.5 AC-4
**What:** AC-4 says "a named-path run against a FIFO operand returns at once with grep's own exit".
But the exec'd caller grep opens the same FIFO. With no writer it blocks in `open` (probed: still
blocked at 3.0 s). With a writer, the caller and the learner, which was spawned BEFORE the exec,
race for the single write, so the AC is order-dependent.
**Fix:**
- Prove "returns at once, learner times out" with an operand that the caller finishes and the
  learner does not. For example: a large regular file, a 20,000-file tree, and
  `RMX_GREP_LEARN_TIMEOUT_S=1`.
- Or use a FIFO whose writer serves exactly one open, after the caller has read it.

### SKETCHY: the throttled/busy "keyed line" exists only in 16.2 R3; R2, AC-6 and 16.3 still say bytes or another format {#s-r4-4}

**Spec:** 16.2 R2 (line 66), R3, AC-6; 16.3 R1 (`no-rg`); 16.4 R1
**What:**
- **16.2 contradicts itself.**
  - R2: "appends one byte to … `busy`".
  - AC-6: "`busy` grows by one byte" and "one byte in `throttled`".
  - R3: "one LINE `<epoch> <cksum>` … Keyed lines, not bytes".
  - An implementation that satisfies AC-6 gives 16.4 nothing to join.
  - `rmx learn status` "prints that file's size", which is no longer a count.
- **16.3 writes another format into the same file.** It appends `<epoch> no-rg` to the busy log,
  which is a different format AND a different meaning from "slots full". It does so from a hook
  that, by R2, never resolves `store_root`.
- **16.4 has no join rule for keyed lines.** It says keyed lines make throttled calls
  "distinguishable", but gives no rule. Recomputing `cksum` needs the EXPANDED argv and the logical
  `$PWD`, which is the same text-vs-argv problem as [[#s-r4-5]].

**Fix:**
- Restate R2 and AC-6 in lines: assert one line with the right `cksum`.
- `learn status` prints line counts.
- Give the `no-rg` skip its own file or its own token, with the hook resolving `store_root` the way
  the shim does.
- 16.4 joins keyed lines by epoch window plus cwd, and counts them as `throttled-explained` without
  argv equality.

### SKETCHY: 16.4 R1 keeps both join definitions, and unmatched segments are still route 3 {#s-r4-5}

**Spec:** 16.4 R1 (lines 61-68 against 75-85), R4 `unobserved_share`; 16.1 R6
**What:**
- **The exact join was not removed.** Lines 61-64 still say attribution is argv equality and is
  "exact even for multi-segment commands". The approximate join was ADDED below them.
- **Route 2 is still text equality (m-n7).**
- **Zero-candidate segments are not counted as `unattributable`.** r3 asked for that. Today such a
  segment fails the pattern-literal rule and reads as route 3, unobserved. Measured: 3.6% of
  producing segments (escaped quotes) plus 2.4% (`$` patterns). The rule also marks 8.5% of
  segments ambiguous and 5.3% as loops. That is about 20% excluded or misread before completeness
  is even tested.
- **`ts` is defined only in 16.4.** It is "learner START", but 16.1 R6, the spec that writes the
  field, just lists `ts`.
- **"Learn-off explanation" cannot be evaluated.** A learn-off shim exit writes nothing (16.2
  AC-5).

**Fix:**
- Delete lines 61-64's equality, or scope it to the case with no shell expansion.
- Redefine route 2 as a record with no candidate segment under the approximate join.
- Add an `unattributable` bucket that never counts as route 3, and report it.
- Define `ts` in 16.1 R6.
- Either log learn-off skips as keyed lines, or drop "learn-off explanation" and report it as a
  known confound.

### SKETCHY: 16.5's spawn and floor are not sandboxed from the live store in tests {#s-r4-6}

**Spec:** 16.5 test strategy, R1/R3; 16.2 R6 sandbox rule
**What:** 16.2's sandbox rule (`RMXGREP_RMX`, plus a conftest guard against spawning PATH `rmx`)
covers the wrappers. 16.5's spawn is `grep_learn.spawn()` from inside `rmx grep`, which is not a
PATH `rmx`, so the guard cannot see it. `_root()` from the repo cwd resolves the LIVE `.refmatrix/`.
`92c374c`'s own message says "nothing isolates `_root()` from the live .refmatrix/". A CliRunner
`rmx grep PAT fixture_file` would append fixture hits to the live learn queue and to
`grep-learn.log`, and the live daemon would drain them into the graph.
**Fix:**
- Every 16.5 test runs from a tmp project cwd with its own `.refmatrix/`, or with `RMX_LEARN=0`
  where learning is not the subject.
- The conftest guard fails any learner spawn whose `store_root` is the live one.

### SKETCHY: 16.2 AC-4 cannot pass as written {#s-r4-7}

**Spec:** 16.2 AC-4
**What:** `rmxgrep -i PAT dir` has no `-r`. BSD grep prints `Is a directory`, exits 2 and finds no
hits (probed). Under 16.1 R1 that is `reason=tool-error`, which teaches nothing. Yet AC-4 requires
`outcome=taught` and a queue equal to `grep -rniH --null PAT dir`. An implementer chasing green
would add `-r` in the learner, which is a cheap fix that breaks fidelity.
**Fix:** Make it `rmxgrep -ri PAT dir`, or make the expected outcome `skipped reason=tool-error`.

### MEH: the plan still has stale lines (m-r3-6, m-1) {#m-r4-1}

**Spec:** plan lines 15-18, 37, 172-174
- **Header.** It says "revision 3 … Awaiting a third review".
- **Out-of-scope bullet 2.** It lists `\b` BRE escapes, the missing-path exit code and `-w`
  verification as "the explicit command's backlog". But 16.5 R8 marks bug-081 fixed and the
  named-path rows superseded.
- **#why.** It still says "bug-058 to bug-066".

### MEH: wording contradictions inside a requirement {#m-r4-2}

**Spec:** 16.1 R1b line 102 ("APPENDS pruning flags") against line 110 ("go BEFORE"); 16.3 R1 glob
cell ("UNLESS the piece contains `{`" against "BOTH `{` and `}`").

### MEH: the exec drops the `cli.log` exit record {#m-r4-3}

**Spec:** 16.5 R6
**What:** `cli_entry` writes its record in a `finally` that `os.execv` never reaches. The
`query.log` row written before the exec has no exit code or duration. Name both. Either log a
`handed-off` record before the exec, or run the tool as a child and propagate its status.

### MEH: the single-file Grep branch has no AC {#m-r4-4}

**Spec:** 16.3 AC list
**What:** `reason=single-file-filter` (s-r3-10) has no captured payload and no mutation. Add
`{path: file, glob: non-matching}` and `{path: file, type: X}`.

### MEH: the spawn-parity test cannot see `$PWD` against `getcwd` {#m-r4-5}

**Spec:** 16.2 R2b
**What:** The shim keys on the logical `$PWD`, and Python's `os.getcwd()` is physical (probed:
`/tmp` against `/private/tmp`). The parity table feeds one cwd string to both sides. Specify that
Python uses `$PWD` when it resolves to `getcwd()`, and add a symlinked-cwd row.

### MEH: R3's index list omits habitual no-op flags, and BRE concepts become write-only for `rmx grep` {#m-r4-6}

**Spec:** 16.5 R3; 16.1 R8
**What:**
- `-r`, `-H`, `-h`, `-s` and `--color` are not index-expressible, so the docstring and primer habit
  `rmx grep -rn x` goes to the floor.
- Every taught `query/<BRE>` concept is never read by `rmx grep`, because R3 sends BRE patterns to
  the floor. About 57% of grep patterns carry a BRE meta. Say which surface reads those concepts,
  such as `rmx context`.

### MEH: 16.4 R2 "one snapshot" against per-commit snapshots, and the model and socket source is unstated {#m-r4-7}

**Spec:** 16.4 R2
**What:**
- "Arms on one snapshot" conflicts with "the tree at the transcript's commit". There are 366 commits
  in the transcript span. Each snapshot is a production ingest, so the cost is unbounded.
- The ingest embeds. Since `43e0fa5`, models load from the local cache only, and `ModelNotCached` is
  loud, which is compatible. But the spec should say whether the throwaway store uses the hub's
  live `models.sock`; `92c374c` logged 66 such test touches.
- Bound the snapshot count.

No spec assumes network access to huggingface.co. The learner imports no `sentence_transformers`,
and `_learn_grep_hits` loads no model.

### MEH: the pruning `--include` is case-sensitive, the corpus predicate is not {#m-r4-8}

**Spec:** 16.1 R1b ("faithful by construction")
**What:** `C.PY` is in the corpus, but `--include='*.py'` does not re-run it (probed). There are 0
such files here. Name it, or add uppercase globs.

## Verified, no finding {#verified}

- **R3's BRE test is well defined for `-F`/`--substring`.** They bypass it. This holds provided
  `--substring` counts only when it was given on the command line (its click default is
  substring).
- **`.` in identifiers sends 0 of 34 observed explicit path-less calls to the floor.** Across all
  grep patterns, 6.6% are `ident.ident`, but after 16.2 those all run the real grep through the
  shim.
- **click accepts `-f '-c'`, `--flags=-c` and `-f-c`, and passes `--file=X` through
  `ignore_unknown_options` unchanged.** Routing is the problem ([[#b-r4-2]]), not click acceptance.
- **Pruning FIRST honours a caller `--exclude`,** and R1b's omission rule is necessary for a caller
  `--include` (probed).

## Verdict {#verdict}

**NEEDS-REVISION.**

| prior findings | closed | partially closed | open |
|---|---|---|---|
| r3 (18) | 11 | 6 | 1 |
| carried (4) | 1 (s-n6) | 2 (b-3, m-1) | 1 (m-n7) |

There are **17 new findings: 2 BULLSHIT, 7 SKETCHY, 8 MEH.**

16.1 is ready apart from wording ([[#m-r4-2]], [[#m-r4-8]]). 16.2 and 16.3 need the keyed-line
format made consistent ([[#s-r4-4]]) and 16.2 AC-4 fixed ([[#s-r4-7]]).

Approval is blocked by 16.5:
- [[#b-r4-1]]: the floor route has no option table, which is b-r3-1's question on the sibling
  route;
- [[#b-r4-2]]: the argv the translation and the routing operate on is click's leftover. It has lost
  `--`, and it misroutes the table's own `--file=` row and repeated `-e`.

16.4 needs [[#s-r4-5]] before `unobserved_share` means anything.

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 33809ab (SPEC review r4, plan-16 tasks 16.1-16.5 rev 4, pre-implementation; written 2026-10-07T09:18:52-0700) | 2026-10-07 | Todd Holley / Opus 5.5 / orchestrator | NEEDS-REVISION | 17 new (2B/7S/8M); r3: 11 closed, 6 partial, 1 open; carried: s-n6 closed, b-3/m-1 partial, m-n7 open | [[bsd-plan16-spec-review-r4-33809ab]]: d-4 table holds on the named/pipe route (click: -f '-c', --flags=-c, -f-c all -> '-c'; --file=X passes through). BULLSHIT: path-less FLOOR runs "caller's translated flags" on an index miss while d-4 refuses -k/--linkage/--limit and R3 calls them index-expressible; --no-fallback still floors (b-r3-1 on the sibling route); routing/translation use click's leftover argv, which EATS `--` (`rmx grep -- -x f.txt` -> grep `-x f.txt`, routed path-less), splits d-4's own `--file=pats.txt f.txt` as path-less -> whole-tree floor, drops one of two -e on path-less, keeps only the last -f. SKETCHY: -f bundle I/r semantics (BSD has no --no-ignore-case); AC-5 floor oracle uses the implementation's pruning and the BRE-routing mutation survives an empty store; AC-4 FIFO blocks in open (probed 3.0 s) or races; keyed throttle line only in 16.2 R3 (R2/AC-6 say one byte; 16.3 writes `<epoch> no-rg` into busy); 16.4 keeps both exact and approximate joins, zero-candidate segments still route 3 (measured 3.6% non-literal + 2.4% $ + 8.5% ambiguous + 5.3% loop); 16.5 spawn unsandboxed from live _root() (92c374c); 16.2 AC-4 `rmxgrep -i PAT dir` without -r is exit 2 no hits. No code, no mutations, no live-store access, no suite run. |
```

IMPRESSIONS.md bullets:

```
- plan-16 r4 (33809ab): fixing "which options on route X" by adding route Y re-asks the same question on Y — 16.5's d-4 answered rmx options for the exec route and the new path-less floor inherited them unanswered. When a revision adds a route, demand its option table in the same pass.
- plan-16 r4: a wrapper that says "argv verbatim" must name WHICH argv. click (8.3.3, ignore_unknown_options) eats `--` and keeps only the last value of a repeated option; translation built on the leftover argv cannot be verbatim. Probe the arg parser before approving a pass-through contract.
- plan-16 r4: an AC whose oracle is built by the code under test (floor vs `grep -r <pruning>`) or whose mutation lands on an empty store (BRE routing with no learned rows) is a guard that cannot fire — same family as impression_bsd_guard_cannot_fire.
```
