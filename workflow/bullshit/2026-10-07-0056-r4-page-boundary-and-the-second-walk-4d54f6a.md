---
gmd: "0.1"
id: bsd-r1-remedy-r4-4d54f6a
title: "r3 remedy: case, -w, the bridge and the toggle are closed with power; paging drops rows at page boundaries, the -c directory walk invents zeros and loses matches, and the index answer still depends on cwd"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r3
round: 4
prior: 2026-10-06-2244-r3-verify-after-limit-and-the-bridge-bb5b97f.md
tags: [bsd, audit, remediation, grep, drop-in, index, pagination, learn-switch]
---

# ch-bsd findings — round 4 over the r3 remedy {#root}

**Range:** `bb5b97f..4d54f6a`. The code is in three commits: `9eed544` (#s-1: egg-info untracked,
metrics.json restored), `2c4e6e2` (the four blockers, bug-076..079) and `321ff97` (every
SKETCHY/MEH item, bug-080 and its shell siblings, bug-081 logged). Everything else in the range is
docs only (`207f451`, `b587621`, `83001bc`, `4d54f6a`). HEAD moved to `659c192` during the run, but
those commits touch only plan-16 markdown (`git diff 4d54f6a 659c192 -- src tests bin eval` is
empty).
**Commit audited:** `4d54f6a`, *docs(bsd): plan-16 spec review*. The code tip is `321ff97`.
**Audit written:** 2026-10-07T00:56:18-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Prior round:** [[bsd-r1-remedy-r3-bb5b97f]]: DIRTY, 16 findings (4B/7S/5M)

rel: amends -> [[bsd-r1-remedy-r3-bb5b97f]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: contradicts -> [[claude#no-workarounds]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]

## How this was checked {#method}

- **Drop-in behaviour.** I compared `.venv-eval/bin/rmx grep --no-learn` against `/usr/bin/grep`,
  checking stdout and exit codes. Every call was a direct exec on a scratch tree: `RMX_LEARN=0`,
  `RMX_GREP_NOTE=0`, and no daemon.
- **Index reads.** Every index read ran on a COPY of `.refmatrix/catalog.read.duckdb` (592 MB),
  opened the way `_replica_store` opens it. Two harnesses: a Python one that calls
  `Store.grep_evidence`, and the real CLI run inside a scratch project. That project holds the copied
  replica and symlinks to the repo's top-level entries, so relative evidence paths resolve as they
  do in the repo. The live store and the daemon were never touched.
- **Mutations.** Run in an isolated `git archive 4d54f6a` copy with `PYTHONPATH=<copy>/src:$PYTHONPATH`,
  over 30 test files (371 tests), with `__pycache__` cleared before and after each mutation. Every
  restore was checked byte-identical, and the copy's `src/` was diffed clean against pristine at the
  end. The shared `src/` was never written. Log: `workflow/review-output/bsd-r4-mutations.log`.
  - **Harness errors I corrected.** The first pass got two things wrong, and I re-ran with fixes.
    First, the test globs were not expanded, so every mutation was reported as killed with no tests
    run. Second, `PYTHONPATH=<copy>/src` overwrote the ambient path, which made fastapi unimportable
    and silently skipped `test_ui_server.py`. Every survivor and every UI mutation was re-run with the
    fixed environment. Only the second pass's verdicts are used below.
- **Full suite** at HEAD: `workflow/review-output/bsd-r4-full.log`. See [[#state]].

## Findings {#findings}

### BULLSHIT #b-1: the paged verify read duplicates one row and drops another at a page boundary, and it is slower than reading everything {#b-1}

**File:** `src/refmatrix/store.py`, the `grep_evidence` paging loop (`LIMIT ? OFFSET ?` over
`" ORDER BY e.path, ev.line"`)

**What:** bug-076's fix re-runs the SQL page by page until `limit + 1` verified rows exist. Each
page is a separate execution, and `ORDER BY e.path, ev.line` is not a total order: one `file:line`
carries one row per concept. Rows that tie on the sort key can therefore fall on both sides of a
page boundary.

**Evidence, on the replica copy:**

- **Store level, `grep_evidence("error", limit=100)`, 5 trials.** In 3 of them,
  `bsd-plan6-r1-fullsuite-clean.log:2558 query/^FAILED|^ERROR` appears TWICE, and its sibling
  `…:2558 query/^FAILED|^ERROR|passed|failed` is missing. The answer still has 96 rows and
  `capped=False`, so the stats call it complete.
- **Through the CLI, the default `rmx grep error` (no flags), 5 runs.** In 2 runs, a line is printed
  twice. Running `comm` against `--limit 0` names the row that is missing.
- **The fix is one line.** With `ORDER BY e.path, ev.line, lt.name, c.name, e.name`, run on a scratch
  copy of `store.py`, there were 0 duplicates and 0 missing rows in 15 of 15 trials.

**The paging also loses on cost.** In every case, the capped read was slower than the uncapped one
that it exists to avoid:

| pattern | `limit=100` (paged) | `limit=None` (one query, verify all) |
|---|---|---|
| `Q` | 1004 ms | 87 ms |
| `E` | 747 ms | 157 ms |
| `X` | 202 ms | 42 ms |

The pages re-sort the whole result every time. Fetching uncapped, verifying, then capping is
correct by construction and faster.

**No test has power over the loop.** Every fixture fits in the first page, because
`page = max(4 x limit, 256)`. Two mutations that reduce the loop to one page (M1, M1b) both
**SURVIVE** all 371 tests. The `+ 1` that sets `capped` can be removed (M1e) and nothing fails. The
true revert (M1c, LIMIT-then-verify) is killed. So the fix is pinned, but its new mechanism is not.

**Fix:** drop the paging and verify the uncapped result. Or, if paging stays, make the ORDER BY
total and add a fixture that spans three or more pages, with ties on `(path, line)`, compared as a
sequence against `limit=None`.

**Pattern match:** YES. See [[impression_bsd_guard_cannot_fire]] and the new
`impression_bsd_offset_paging_needs_a_total_order`.

rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT #b-2: the `-c` directory expansion is a second walk; it invents a zero for binary files and loses every row when a subdirectory is unreadable {#b-2}

**File:** `src/refmatrix/cli.py`, `_walk_files` and `argv_count_rows` (new in `2c4e6e2`)

**What:** to print grep's zero rows for `-rc DIR`, the remedy lists the directory a second time with
`rg --files --sort path`. Its docstring says this makes "the universe match the walk that produced
the counts (same ignore rules)". It matches on ignore rules. It does not match on binary files or on
errors.

**Evidence (exec, `/usr/bin/grep` as control):**

| invocation | `/usr/bin/grep` | rmx dev |
|---|---|---|
| `-rc alpha d` (`d/a.txt`, plus `d/bin.dat` holding NULs and 2 `alpha` lines) | `d/a.txt:1` `d/bin.dat:2`, exit 0 | `d/a.txt:1` **`d/bin.dat:0`**, exit 0 |
| `-rc alpha d` (`d/a.txt`, plus unreadable `d/locked/`) | `d/a.txt:1`, error, **exit 2** | **stdout empty, exit 1** |
| `-rc zzz d` (same tree) | `d/a.txt:0`, error, exit 2 | stdout empty, `Error: rg --files d failed…`, **exit 1** |

- **The binary row is a fabricated zero.** rg's search skips the binary file and `rg --files` lists
  it, so rmx claims to have counted a file it never searched. That is the class of error r2 #b-2 was
  about, and this docstring cites r2 #b-2.
- **The unreadable-subdirectory case is worse.** `rg --files` exits 2 and `_walk_files` raises a
  `ClickException`. That drops ALL rows, including the real match, and exits 1, which is grep's code
  for "no matches". The implementation summary says the opposite: "A failure of `rg --files` raises;
  it does not drop rows."
- **This is not a contrived input.** On macOS, `grep -rc X ~/...` routinely crosses TCC-protected
  directories. Deployed 0.76.0 omitted the zero rows. That is wrong, but it never fabricated a count
  and never hid a match.

**Fix:** ask the search for its own universe, `rg -c --include-zero` (add `--binary` if grep's
binary counting is wanted), instead of listing the files a second time. If the walk stays, a walk
error must not discard rows that were already counted. The exit status must follow the tool's
(2), not a `ClickException`'s (1).

**Pattern match:** YES. The new `impression_bsd_second_enumeration_of_the_universe`;
[[impression_bsd_resolve_is_not_an_identity]].

rel: contradicts -> [[claude#no-silent-failures]]

### BULLSHIT #b-3: r3 #b-4(b)'s quoted directory row still diverges — two spellings of one directory now interleave {#b-3}

**File:** `src/refmatrix/cli.py`, `argv_rank`

r3's table quoted three rows. Two are now closed: `-c alpha ./f0.txt f0.txt` and
`-n alpha f0.txt ./f0.txt` both match grep. The third is not:

| invocation | `/usr/bin/grep` | rmx dev |
|---|---|---|
| `-rn alpha ./sub sub` | all `./sub/…` rows, then all `sub/…` | `sub/ig.log` `./sub/ig.log` `sub/s1.txt` `./sub/s1.txt` (interleaved) |
| `-rl alpha ./sub sub` | `./sub/…` then `sub/…` | interleaved, same way |

The raw-spelling loop added to `argv_rank` compares `emitted_path == sp`, which only a named FILE
can satisfy. A walked file `./sub/x` falls through to `normpath`. Both arguments normalise to `sub`,
both prefix-match at the same length, the first one wins, and every row ranks 0. The stable sort then
keeps rg's parallel fan-out order. The spellings are no longer collapsed, as they were at r3, but
the grouping is still lost. Both two-spelling tests use files only. M15 (delete the raw loop)
**SURVIVES** too, because rg searches named files in sequence, so the loop's own claimed defect is
not observable through any test.

**Fix:** match the raw directory spelling as a prefix (`emitted.startswith(sp.rstrip('/') + '/')`)
before falling back to `normpath`. Add the `./sub sub` row to `test_grep_count_rows_e2e.py`.

**Pattern match:** YES, [[impression_bsd_quoted_line_sibling]]: one row of the audit's quoted
table was left unfixed.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-4: "exits 2 on a tool error, on every branch": not on `-l`/`-L` when something matched {#b-4}

**File:** `src/refmatrix/cli.py`, `_grep_rg_fallback`'s `-l`/`-L` branch (the `return` after a
match)

| invocation | `/usr/bin/grep` | rmx dev |
|---|---|---|
| `-l alpha f0.txt nosuch.txt` | `f0.txt`, error, **exit 2** | `f0.txt`, error, **exit 0** |
| `-L alpha f0.txt nosuch.txt` | error, **exit 2** | error, **exit 0** |

The branch raises `2 if tool_error else 1` only when nothing matched. On a match it `return`s
before the function's final `if tool_error: raise SystemExit(2)`. The 11 other shapes I ran (`-c`
match and no-match, `-c` on a missing file alone, `-n`, `-o`, `-v`, `-h`, `-q` x2, no-match
`-l`/`-L`) all match grep, exit code included. Mutation M19 (the list branch exits 1
on error) **SURVIVES**, so the `-l` exit path has no test at all. `321ff97`'s message says "on every
branch".

The defect is small. I am escalating it for the pattern: this is the 11th sighting of a remedy
fixing the quoted branch while the sibling branch keeps the bug, and per the escalation rules a
pattern at 3 or more sightings is BULLSHIT. **Fix:** `raise SystemExit(2)` after printing the list
when `tool_error`. Add a `-l` and an `-L` case beside `test_a_missing_file_beside_a_match_still_exits_2`.

**Pattern match:** YES, [[bsd-pattern-sibling-render-path]], 11th sighting.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-5: r3 #s-6's path half is not closed: the default index answer still depends on cwd, and the delegate path still learns relative paths behind a bare `except: pass` {#b-5}

**Files:** `src/refmatrix/store.py` `verify_evidence_rows` (`Path(path).read_text()` on a relative
path), `src/refmatrix/cli.py` `_grep_delegate` (learn block)

**What:** r3 #s-6 asked for verification that does not depend on cwd. The remedy changed only the
producer in `_grep_rg_fallback`. The summary says: "Rows already learned with relative paths stay
until relearned."

**Evidence (replica copy, real CLI):**

| cwd | `rmx grep error` rows | stderr |
|---|---|---|
| project root | 96 | `213 index row(s) dropped` |
| `src/` | **5** | `660 index row(s) dropped — their file could not be read` |

- **Where the relative rows are.** 515 of `error`'s 747 raw rows carry relative paths. All of them
  are learned `query/…` rows, such as `workflow/review-output/*.log` and `.refmatrix/daemon.stderr.log`.
- **"Until relearned" never happens.** Learning runs only when the floor answers, and these patterns
  are now answered by the index, from any cwd that leaves at least one row. The deferral names no
  task, which makes it unanchored under rule 9a.
- **The rows are root-relative.** They were taught mostly through `bin/rmxgrep`'s ping, which
  `cd`s to the project root first. Resolving a relative evidence path against `root.parent` inside
  `verify_evidence_rows` therefore closes the bug for the existing rows with no migration.
- **The sibling path is untouched.** `_grep_delegate`, which serves any flag the index cannot
  express, still teaches the raw `parts[0]` spelling, so it still writes new relative rows. It still
  wraps the broker in `except Exception: pass`, on a memory path (CLAUDE.md#no-silent-failures).
  `321ff97` fixed that exact construct one function over: "A bare except-pass around the learn
  broker now prints to stderr".
- **No test pins the message that did change.** M21 (mute the new message in `_grep_rg_fallback`)
  **SURVIVES**.

**Fix:**

1. Resolve relative evidence paths against the project root in `verify_evidence_rows` (or in
   `grep_evidence`, which knows the store root).
2. Make `_grep_delegate`'s hits absolute, as `_grep_rg_fallback` now does.
3. Replace its `except Exception: pass` with the named stderr line.

**Pattern match:** YES. [[impression_bsd_silent_memory_paths]], and this is the second sibling-path
miss in this round.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-1: the stated second- and third-path fixes are correct by execution and pinned by nothing {#s-1}

Escalated from MEH because r3 #m-2 had this exact shape, and r3 #b-2 was a whole BULLSHIT about a
read path with no test. I executed each item below and each works. Each mutation that removes it
**SURVIVES** all 371 tests:

| mutation | what it removes | executed by me |
|---|---|---|
| M3 / M3b | the daemon-RPC `capped` (CLI side, op side) | RPC shim to the real `OPS` prints the cap note |
| M2b / M3c | the `unreadable` note and its RPC field | same probe: "1 index row(s) dropped" |
| M11 / M11b | `word=` on the replica (DEFAULT) and direct paths | CLI on the copy: `-w err` 1 row, `-w error` 73, `-iw ERROR` 77; 0 lines fail `grep -w` |
| M9 | `\b` around the bridged variants under `-w` | `-w "build context"` → 0 (the only row is `test_build_context_falls_back…`) |
| M7 | grep-branch case letters (no rg) | `PATH=/usr/bin:/bin`: `error e.txt` / `-c` / `-i` == grep |
| M14 | the bare `0` returning for paths that yield no row | `-c alpha nosuch.txt` → no stdout, exit 2 == grep |
| M26 / M27 / M28b / M29 | rewriter throttle and last-resort stderr, rmxgrep throttle, rmxrg's report | chmod 000 store dir, scratch HOME: 1 log line per 2 calls; unwritable log → stderr line |

The commit says "#s-7 … Three tests RED, including the RPC carrying `word`". The default read path,
the replica, is the one with no `-w` test.
**Fix:** one parametrised CLI test over `replica`/`direct`/RPC-shim for `-i`, `-w`, the cap note and
the unreadable note. Add a `-c zzz nosuch.txt` row and the `-l`/`-L` rows from [[#b-4]] to the e2e
file.

rel: related-to -> [[impression_bsd_guard_cannot_fire]]

### SKETCHY #s-2: bug-081 is a live silent false negative in the explicit `rmx grep`, with no task behind "that command's backlog" {#s-2}

`rmx grep -c 'alpha$' f0.txt` → `0`, exit 1 (grep: `3`, exit 0). The same holds for `'^alpha'` and
`'alp.a'`. The interim `RMXGREP_MODE=plain` takes Claude's Bash greps off this path, because a
non-tty there means the real tool. A tty in rich mode still reaches it, and so does any direct
`rmx grep`, which the project's own rmx-first rule recommends. The row's fix text, "logged here for
that command's backlog", names no task. That is rule 9a's "no concrete target". I am scoring it
SKETCHY, not BULLSHIT, for the reason r3 gave #s-5: it is written down in the registry, not buried.
The cheap version already exists for `\|`: a loud exit-2 refusal for BRE metacharacters, which the
wrapper turns into a real-grep fallback. **Fix:** extend that refusal now, or file a task spec. If
it is unchanged at r5, rule 9a applies in full.

### SKETCHY #s-3: unregistered mock: `cli._root` patched in `tests/test_learn_switch.py` {#s-3}

`test_learn_status_says_unreadable_not_absent` adds `monkeypatch.setattr(cli_mod, "_root", lambda:
store)`. That line is new in this range. The `cli._root` row in `workflow/test_mock_registry.md`
lists 12 files, and this one is not among them. **Fix:** add the file to the row.

### MEH #m-1: `_grep_stdin_addendum` is a fourth `grep_indexed` caller that drops `-i`/`-w` {#m-1}

`cli.py` `_grep_stdin_addendum` sends `{pattern, regex: False, …, limit: 5}` with no `ignore_case`
and no `word`. The output goes to stderr only, so it does not change the answer. But under
`… | rmx grep -i error`, the "what the index knows" lines come from a case-sensitive read. The
dispatch asked for any caller that drops a matching flag. This is the only one left.

### MEH #m-2: the multi-word bridge is case-insensitive; the help text now says case-SENSITIVE {#m-2}

`identifier_variant_regex` compiles with `re.IGNORECASE`, and its space-joined form makes the
LITERAL phrase case-insensitive, not only the identifier spellings. As a result,
`rmx grep "SCAN PROMPT"` (no `-i`) returns 4 index rows on the copy, while grep returns none. The
docstring says this is on purpose for identifier joins, which is defensible. The new `--regex` help
says "Default is a case-SENSITIVE substring, as in grep", and bug-073's row has no scope line.
**Fix:** keep the `_`/`-`/camel joins case-insensitive and make the space join follow `-i`. Or scope
the help text and the row to single-word patterns.

### MEH #m-3: `learn-switch.log` is never cleared, so `rmx learn status` reports stale problems forever {#m-3}

After the marker becomes readable again, `learn status` still prints `hook reports 1 line(s) …;
latest: 1791357243 rmxgrep unreadable …`. The stamp is raw epoch seconds, so the reader cannot tell
that the report is old. **Fix:** show only reports newer than the marker's current state (or the
last N minutes), with a human-readable time.

### MEH #m-4: pre-existing and out of range, with no bug row: the floor silently drops `-A`/`-B`/`-C` and skips hidden files in a walk {#m-4}

- `rmx grep -A1 alpha s1.txt` → `alpha` (grep: `alpha`, `beta`), exit 0. `-C1` is the same, and
  deployed 0.76.0 is the same. `_grep_bare_flags`' docstring says `-A/-B/-C` are honored, and
  `_grep_rg_fallback` never passes them to rg.
- `-rc`, `-rn` and `-rl` over a directory omit dotfiles (`sub/.dot.txt`), because that is rg's
  default.

The interim plain mode keeps Claude's Bash off this path. A tty or a direct `rmx grep` does not.
**Fix:** log both rows in `workflow/bug_registry.md`. Plan-16 removes the drop-in exposure, but not
the exposure through the explicit command.

## Closed and verified {#closed}

| r3 finding | status | evidence |
|---|---|---|
| #b-1 cap after verify | **CLOSED** for the cap. New defect in its mechanism: [[#b-1]] | Copy: `error` 96 of 96 (was 13), `partition` 100 + cap note (was 51, silent). M1c (true revert) and M1d (`capped` false) FAIL. M2 / M12 (replica note) FAIL. RPC note correct by execution, untested ([[#s-1]]) |
| #b-2 `-i` on every path | **CLOSED** | RPC carries `ignore_case`/`word` (M4, M5, M5b, M5c FAIL). Floor `-s` (M6 FAILS). `error e.txt`, `-c error e.txt`, `-i error e.txt` == grep with rg, and also with no rg. Copy: `ERROR` → 0 index rows, `-i ERROR` → 179. Remaining dropper: [[#m-1]] |
| #b-3 spelling bridge | **CLOSED** (option a, decided in writing) | 11 of 16 instrument patterns answer after verification (r3: 8). Every bridged row's line holds an identifier spelling (precision 1.000 against an identifier-token control); single-word rows 1.000 literal. The 3 lost (`roaring bitmap`, `grep evidence`, `learn queue`) are all `def`-line rows (read). Guards back on `_op_grep_indexed`: M8 (no variants) and M9b (case-sensitive variants) FAIL. Instrument passes `verify=` explicitly |
| #b-4 bare 0 / argv spelling | **(a) CLOSED; (b) files CLOSED, dirs OPEN** | `-rc zzz sub` → per-file zeros (M13 FAILS), no bare `0` for `-c zzz sub nosuch.txt`. `./f0.txt f0.txt` → two rows (M16 FAILS). Directory spellings: [[#b-3]]. The new walk: [[#b-2]] |
| #s-1 egg-info / metrics | **CLOSED** | `git ls-files src/refmatrix.egg-info` → 0; `metrics.json` identical to `4f70a0b^` |
| #s-2 upsert_vector twin | **CLOSED** | Both stubs gone. Registry row true. The file passes in the full suite |
| #s-3 regex coverage | **CLOSED** | M5d (op ignores `regex`) FAILS `test_grep_indexed_regex_anchors` |
| #s-4 three dropped r2 items | **CLOSED** | One `esc`, five sites escaped (`d.line` is raw process output, so escaping it is correct). M31/M32 FAIL. Task-3.4 spec exists (pending, plan-3 in-progress). `raising=False` gone |
| #s-5 stale measurement docs | **CLOSED** (anchored) | SUPERSEDED banners on all three. Re-run is task-16.4, which names the 18.5%→31.7% figures |
| #s-6 unreadable / cwd | **unreadable half CLOSED by execution** (untested); **path half OPEN** | [[#b-5]], [[#s-1]] |
| #s-7 `-w` | **CLOSED by execution** | 151 distinct `-w`/`-iw` locations on the copy, 0 fail `grep -w`. RPC pinned (M10 FAILS). Replica/direct unpinned ([[#s-1]]) |
| #m-1 80.6% | **CLOSED** | Wording in the replay doc |
| #m-2 learn_switch untested | **CLOSED**, and it found bug-080 | `Path.exists()` → False on a chmod-000 dir (3.14), `marker_state` → `unreadable`, `decision` carries `marker_error`. M22 / M23 / M24 / M25 / M28 / M30 FAIL |
| #m-3 registry/handoff | **CLOSED** | bug-076..080 `fixed (bsd-r1-remedy, unmerged)`; `2c4e6e2` not an ancestor of master, which matches |
| #m-4 floor errors | **CLOSED except `-l`/`-L`** | 11 of 13 shapes == grep including the exit code (M17, M18, M19b FAIL). [[#b-4]] |
| #m-5 `_teach` fallback | **CLOSED** | Raises `AssertionError` |

**bug-080's shell proxy.** `[ -d dir ] && [ ! -x dir ]` is a faithful proxy for EACCES on the
marker. The root-finding loop already proved `$root` searchable, `$HOME` is searchable, so the only
ancestor that can deny the search is the marker's own directory. For uid 0, `-x` on a directory is
always true, so there is no false positive. It disagrees with the Python resolver only on ELOOP
(a symlink loop at `learn.off`), which is contrived. Executed with a scratch `HOME`: `chmod 000
.refmatrix` → both wrappers fall through to rmx and log one line for two calls. The `rmxrg` toggle
honours the store marker, `RMX_LEARN=off` and a malformed value. `rmx learn status` shows UNREADABLE
plus the hook-report line.

**`RMXGREP_MODE=plain` interim.** Both settings files carry it. The wrappers read any value other
than `rich` as auto, and a non-tty under auto takes the real-tool + teach-ping branch. It is a user
decision, it is wired, and nothing reads `plain` specially.

## Deferral sweep (rules 9 / 9a) {#deferrals}

Added lines in `src/`, `bin/`, `eval/`: no hard or soft deferral hits. There are two prose
deferrals: "rows already learned with relative paths stay until relearned" in the implementation
summary ([[#b-5]], unanchored), and bug-081's "that command's backlog" ([[#s-2]]).

## State facts, re-derived {#state}

| claim | verdict |
|---|---|
| "2507 passed, 1 failed (test_installed_hooks_match_generated)" | **true.** 1 failed / 2507 passed in 994.72 s at HEAD (`bsd-r4-full.log`) |
| the one failure is the rewriter template only | **true.** `hooks.check` reports exactly `script rmxgrep-rewrite.py differs`. The installed file is byte-identical to the `bb5b97f` render, and its diff to the `4d54f6a` render is exactly the bug-080 block (`_LEARN_LOG`, `_marker_present`, `_report_unreadable`). Nothing else differs (`bsd-r4-hooks-check.log`) |
| not deployed; `~/refmatrix` at `1452875`, 0.76.0 | true |
| `src/` untouched by this audit | true. All mutations ran in the archive copy. Two stray probe outputs (`o2`, `e2`), written through a symlinked scratch dir into the repo root, were deleted before this report |

## Verdict {#verdict}

**DIRTY: 12 findings (5 BULLSHIT, 3 SKETCHY, 4 MEH).**

This is the strongest remedy in the lineage. All four r3 blockers are closed at the level r3 named
them, and twelve of the sixteen r3 findings are closed outright. Case and `-w` reach every read
path. The bridge decision was made in writing and measures clean. bug-080 is a real find, and its
fix holds on a real `chmod 000`. Every claim the dispatch asked me to attack was checked by
execution.

Three of the new mechanisms are wrong, though:

- **The paging loop** drops and duplicates rows at a page boundary, and no test reaches page 2.
- **The `-c` walk** fabricates zeros for binary files and hides matches behind a walk error.
- **The cwd fix** covers new rows only. From `src/`, the default read loses 91 of 96 rows.

The sibling-branch pattern also appeared twice more: `-l`/`-L` exit status, and the delegate's
`except: pass`.

**Blockers for merging `bsd-r1-remedy`:** [[#b-1]], [[#b-2]], [[#b-3]], [[#b-4]], [[#b-5]]. Each
fix is small. #b-1 is a one-line ORDER BY or removing the paging. #b-3 is one prefix check. #b-4 is
one `raise`. #b-5 is resolving against the root plus mirroring two lines into `_grep_delegate`.
#b-2 is the only one that needs a design choice: `rg -c --include-zero` instead of a second walk.
Round 5 is owed.

rel: contradicts -> [[claude#no-silent-failures]]
rel: amends -> [[bsd-r1-remedy-r3-bb5b97f]]
