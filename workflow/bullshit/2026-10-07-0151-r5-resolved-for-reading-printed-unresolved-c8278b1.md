---
gmd: "0.1"
id: bsd-r1-remedy-r5-c8278b1
title: "r4 remedy: the paging and the cwd-dependent row set are closed with power; the resolved path is used to read and the unresolved one is printed, the base is wrong for the global store, and the unreadable note is unpinned for a third round"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r4
round: 5
prior: 2026-10-07-0056-r4-page-boundary-and-the-second-walk-4d54f6a.md
tags: [bsd, audit, remediation, grep, index, paths, mutation]
---

# ch-bsd findings — round 5 over the r4 remedy {#root}

**Range:** `4d54f6a..c8278b1`. The code is in one commit, `dffa2df` (bug-082/083/084, the r4
SKETCHY tests, the registry row, the help text and the `learn status` 24 h display). `0a6d00a`,
`659c192` and `c8278b1` change only markdown (`git diff 4d54f6a..c8278b1 --stat -- src tests` covers
`dffa2df` alone).
**Commit audited:** `c8278b1`, *docs(plan-16): task 16.5*. The code tip is `dffa2df`.
**Audit written:** 2026-10-07T01:51:30-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Prior round:** [[bsd-r1-remedy-r4-4d54f6a]]: DIRTY, 12 findings (5B/3S/4M)

rel: amends -> [[bsd-r1-remedy-r4-4d54f6a]]
rel: contradicts -> [[claude#no-silent-failures]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]
rel: related-to -> [[task-16.5-explicit-grep-hands-off]]

## Scope set by the user's decision {#scope}

The user chose option 1 on 2026-10-07. r4 #b-2, #b-3, #b-4, #m-4, the `_grep_stdin_addendum` MEH,
bug-081 and the rendering/shim mutation survivors are superseded by task 16.5, which deletes the
Python re-implementation of grep output. They are not re-filed here as blockers. Their coverage in
16.5's spec is checked in [[#coverage]].

## How this was checked {#method}

- **Index reads** ran on a copy of `.refmatrix/catalog.read.duckdb` in a scratch project. The
  project's top-level entries are symlinks to the repo, and `realsub/` is a REAL directory inside it
  (see the harness correction below). Every CLI call was `.venv-eval/bin/rmx grep --no-learn` with
  `RMX_LEARN=0`. A copy of `~/.refmatrix/catalog.read.duckdb` was opened read-only for the
  global-store counts.
- **Delegate probes** ran in a fresh scratch store with `HOME` redirected. Teach records were read
  from that store's `learn.queue.jsonl`.
- **Mutations** ran in an isolated `git archive c8278b1` copy with
  `PYTHONPATH=<copy>/src:$PYTHONPATH` (prepended) and `.venv-eval` symlinked in, so the e2e files
  find the dev rmx. Baseline: **319 passed, 0 skipped** over 26 grep/learn files. Without the
  symlink it was 306 passed / 13 skipped, so the symlink is what made the count complete. Each
  mutation asserted exactly one anchor match and cleared `__pycache__` before and after. Each
  restore was asserted byte-identical. The shared `src/` was never written.
- **Full suite** at HEAD in the main tree: [[#state]].
- **Harness correction, stated.** My first "from `src/`" run used the scratch project's `src`
  symlink. `_root()` calls `Path.cwd().resolve()`, so that cwd resolved to the REAL repo and read
  the LIVE `catalog.read.duckdb`. It was a read-only open with learning off, and nothing was
  written. That run (96 rows) is discarded. Every cwd number below comes from `realsub/`. The same
  confound may sit under r4's "5 rows from `src/`" figure, if r4's `src/` was also a symlink.

## Findings {#findings}

### BULLSHIT #b-1: rows are verified against the RESOLVED path and printed with the UNRESOLVED one; from a subdirectory, 83 of 88 printed paths do not exist {#b-1}

**Files:** `src/refmatrix/store.py` `verify_evidence_rows` (resolves `fp = base / path` and keeps
`r` unchanged); `src/refmatrix/cli.py` `_render_grep_rows` (prints `r["path"]`)

**What:** bug-084 made the row SET independent of the cwd, and the SET is now correct:
`rmx grep error` returns the same 88 rows from the project root and from `realsub/` (byte-identical
stdout). But `verify_evidence_rows` resolves the path only to read the file. It appends the
original row, so the renderer still prints the root-relative spelling. Before the fix those rows
were dropped from a subdirectory. Now they are printed, under paths that are wrong for the caller.

**Evidence (replica copy, real CLI, cwd `realsub/`):**

- **`rmx grep error`:** 88 rows. 83 are printed relative (`workflow/review-output/lint-gmd-partition-probe.log:…`
  ×61, `tests/test_telemetry_outcomes.py:…` ×5, …). Of the 10 distinct printed paths, **7 do not
  exist from the cwd**. The 3 that open are the absolute ones.
- **One file can appear under two spellings.** On the copy, 82 relative evidence paths have an
  absolute twin. `rmx grep --limit 0 -c def` prints `src/refmatrix/helix.py: 18` AND
  `/Users/tholley/claude_tools/refmatrix/src/refmatrix/helix.py: 1`: one file split into two count
  rows, one of them unopenable from the cwd. The same `file:line` printed under two spellings: 3
  for `def`, 1 for `grep`, 4 for `test`.
- **This is not superseded.** 16.5 R3 KEEPS the path-less index read and "its rendering". This is
  the path that stays.

**Why BULLSHIT:** this is the quoted-line sibling again. The fix was applied where the path is read
and not where it is used. That is the 12th sighting of [[bsd-pattern-sibling-render-path]], which
is BULLSHIT by escalation.

**Fix:** have `verify_evidence_rows` (or `grep_evidence`) return the resolved path in the row it
keeps. Print it absolute or `os.path.relpath`-to-cwd, then dedupe on the resolved
`(path, line, linkage, concept)` before the cap. Test: run a relative row from a subdirectory and
assert that the PRINTED path opens from that cwd.

**Pattern match:** YES. [[impression_bsd_quoted_line_sibling]].

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-2: third round in a row: the `unreadable` note and the `-w` bound on bridged spellings are correct by execution and pinned by nothing, on the read path 16.5 keeps {#b-2}

**Files:** `src/refmatrix/cli.py` `_grep_index_notes`, `_grep_run` (RPC `unreadable`);
`src/refmatrix/daemon.py` `_op_grep_indexed`; `src/refmatrix/store.py` (`\b` around `variants`
under `word`)

Every mutation below **SURVIVES** 319 tests (`mutations.log` in the scratch copy):

| mutation | removes |
|---|---|
| D1 | `_grep_index_notes`' unreadable line (`if n:` → `if False:`) |
| D2 | the RPC result's `unreadable` on the CLI side (→ 0) |
| D3b | `_op_grep_indexed`'s `unreadable` (→ 0) |
| D5 | the `\b(?:…)\b` wrap of bridged variants under `-w` |

These are r4 #s-1's M2b / M3c / M9. r4 #s-1 was itself escalated from r3 #m-2. The remedy pinned
the other half of #s-1: the RPC cap note (my A3 / D3 / D4 each FAIL), `-w` on the replica and
direct paths (D6 / D6b FAIL), and the rewriter throttle (E1 FAILS). It did not pin these four. The
summary's superseded list folds "the 13 surviving mutations" into 16.5, but 16.5 R3 keeps
`_grep_index_notes`, the RPC and `grep_evidence`. Nothing deletes this code. At three sightings,
SKETCHY escalates to BULLSHIT. The note works by execution: "221 index row(s) dropped" on the copy.

**Fix:** two tests. (1) Through the RPC shim and the replica, seed an evidence row whose file does
not exist and assert the stderr note's count. (2) Assert that `-w` on a bridged multi-word pattern
drops a row whose line holds the spelling only inside a longer identifier.

**Pattern match:** YES. [[impression_bsd_guard_cannot_fire]]; r3 #m-2 → r4 #s-1 → here.

### SKETCHY #s-1: `base = store.root.parent` is wrong for the global store, and for rows learned from a subdirectory {#s-1}

**File:** `src/refmatrix/store.py` `grep_evidence` (`base=self.root.parent`)

**What:** the docstring says a relative row resolves against "the project root it was relative to
when learned". That holds for rows that `bin/rmxgrep` taught after `cd`-ing to the root. It does
not hold for:

- **The global store.** Outside every project, `_root()` falls back to `~/.refmatrix`, so the base
  is `$HOME`. A copy of the global replica holds **1,087 relative evidence paths (5,159 rows, all
  `query/` learned rows)**, and only **387 exist under `$HOME`**. The rest (`atlapi/…`,
  `customer_cfgs/…`, `build/lib/…`, `node_modules/…`) were taught from other cwds. Under the old
  cwd rule, re-running `rmx grep` from the cwd that taught them found them. Under the new rule they
  are unreadable from EVERY cwd, including that one. For those rows this is a regression, though
  the "N index row(s) dropped" note counts them.
- **Project-store rows taught from a subdirectory.** 9 of 186 relative paths on the project copy do
  not resolve under the base. Examples: `pytest-plan4-r4-green.log` (taught from
  `workflow/review-output/`), and garbage paths that bug-082's parse produced (see [[#s-2]]).

The new test seeds only the `<proj>/.refmatrix` layout. The learn cwd was never recorded, so no
base is right for every row.

**Fix:** a one-time migration. Rewrite a relative row to absolute where it exists under its store's
base, and count and delete the rest, instead of guessing at read time. Or scope the docstring and
bug-084's row to project stores and say the global store's relative rows are lost. Either way, add
a global-layout case.

### SKETCHY #s-2: bug-082's delegate still teaches `-c` counts as line numbers and `-h` content as file paths, now as absolute paths; the "unparsed" counter misses them {#s-2}

**File:** `src/refmatrix/cli.py` `_grep_delegate`

Scratch store, real CLI, teach records read from `learn.queue.jsonl`:

| invocation | output | taught |
|---|---|---|
| `-c --include=c.txt -r alpha sub` (`alpha` on lines 4 and 5) | `sub/c.txt:2` | `…/sub/c.txt` **line 2**, which is `y` |
| `-h --include=d.txt -r alpha sub` (content `alpha:3`) | `alpha:3` | **`<cwd>/alpha` line 3**: a file that does not exist |
| `-h …` over three lines | 3 lines | the stderr note says **1** "not file:line"; the 2 lines with no colon are not counted |

- **The parse is the same as before.** `raw.split(":", 2)` plus `int(parts[1])` was already there.
  The remedy rewrote this block and registered it as fixed, and the fix only made the wrong paths
  absolute.
- **bug-082's headline is unpinned.** Muting the named learn failure (B2) and the unparsed note
  (B3) both **SURVIVE**.
- **The new stderr line fires on every delegated grep without `-n`.** That is the common case, so
  under rich mode the transcript gets a second rmx line.

Not a merge blocker under the user's decision: 16.5 R4 deletes `_grep_delegate`, and 16.1's
learner drops `-c`/`-h` and re-runs with `-n -H`. Until 16.5 lands, though, this branch writes
fabricated evidence into the graph. **Fix if the branch merges first:** teach only when the parsed
shape is grep's `-n` shape (filename present, `-n` in argv, no `-c`/`-l`/`-h`/`-o`), and count
every skipped line.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-3: unregistered mock: `refmatrix.daemon.ping` patched in `tests/test_grep_learned_paths_absolute.py` {#s-3}

`test_the_delegate_branch_teaches_absolute_paths_too` adds
`monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)`. The registry row for that
patch (line 119) lists `test_grep_case_every_path.py` and `test_grep_verify_before_cap.py` only.
This is r4 #s-3's shape one round later, in the commit that closed r4 #s-3. **Fix:** add the file
to the row.

rel: related-to -> [[impression_bsd_registry_row_deferral]]

### MEH #m-1: with `stop_after`, `dropped`/`unreadable` count only the rows read before the stop {#m-1}

Measured on the copy: `Q` gives `unreadable` 10,305 under `--limit 100` and 10,394 uncapped. `e`
gives `dropped` 832 vs 6,336. No caller reads `dropped`. The CLI note prints the prefix count beside
the cap note, which is defensible. The docstring still says `stats["unreadable"]` "carries the
number". **Fix:** add "of the rows read before the cap".

### MEH #m-2: the `learn status` 24 h window is unpinned, and a malformed log line vanishes uncounted {#m-2}

C1 (`if True:` in place of the window) **SURVIVES**. The test was changed to write a current
timestamp, so it passes with or without the filter. A line whose head is not a float hits
`continue` with no count, on a diagnostic surface that exists to report the learn switch.
**Fix:** one stale line plus one fresh line in the test; count the unparsed lines.

### MEH #m-3: 16.5's differential corpus does not name four of the cases it supersedes {#m-3}

See [[#coverage]]. Executing the real grep makes them correct by construction. But AC-1's "these
cases must DIFFER on the current code first" and R6's "marked superseded" both depend on the corpus
naming them. **Fix:** add the four rows to R5.

## r4 findings: closed, superseded, open {#closed}

| r4 | status | evidence |
|---|---|---|
| #b-1 paging | **CLOSED** | One read. `ORDER BY e.path, ev.line, lt.name, c.name, e.name` contains all five DISTINCT columns, so the order is total. A1 (revert the order) FAILS the tie test; A3 (no `+ 1`) FAILS. Copy cost, capped vs uncapped: `Q` 53/63 ms, `E` 97/136 ms, `e` 96/138 ms over 59,580 raw rows (r4: 1004 ms paged). A2 (verify everything) survives, which is correct: only the cost changes. No `limit=None` caller changed behaviour: `_op_grep_indexed` maps 0 → uncapped as before, and the eval passes `None` explicitly |
| #b-2 `-c` walk | **SUPERSEDED, covered** | R5 names `-rc zzz sub`, a binary file, and an unreadable subdir |
| #b-3 dir spellings | **SUPERSEDED, covered** | `-rn alpha ./sub sub`, `-rl` with two spellings |
| #b-4 `-l`/`-L` exit 2 | **SUPERSEDED, half covered** | `-l alpha f0.txt nosuch.txt` is named. `-L` is not ([[#m-3]]) |
| #b-5 cwd / delegate | **Row set CLOSED** (88 = 88 across cwds; A4/A5 FAIL). **Display OPEN** → [[#b-1]]. **Base** → [[#s-1]]. **Delegate paths CLOSED** (B1 FAILS); named failure unpinned → [[#s-2]] |
| #s-1 untested paths | **HALF CLOSED** | Cap note, `-w` replica/direct and throttle are pinned. Unreadable note and variant `\b` are not → [[#b-2]] |
| #s-2 bug-081 | **SUPERSEDED, covered** | R3 (BRE floor), R5 (bug-081's `\b` and table-row patterns), AC-4 (`alpha$`) |
| #s-3 `cli._root` | **CLOSED** | Row added. A new unregistered patch appeared → [[#s-3]] |
| #m-1 stdin addendum | **SUPERSEDED, covered** | R2 deletes it; AC-5 verifies deletion |
| #m-2 bridge help | **CLOSED** | Help text scoped. `"SCAN PROMPT"` → 4 rows, each an identifier spelling |
| #m-3 learn-switch.log | **CLOSED by execution, unpinned** → [[#m-2]] |
| #m-4 `-A/-B/-C`, dotfiles | **SUPERSEDED, partly covered** | `-A 2` is named. `-B`/`-C` and the dotfile walk are not ([[#m-3]]) |

## 16.5 coverage check {#coverage}

| superseded item | named in 16.5 R5/AC? |
|---|---|
| r4 #b-2 (three rows) | yes, all three |
| r4 #b-3 (`-rn`, `-rl` two spellings) | yes |
| r4 #b-4 `-l … nosuch.txt` | yes |
| r4 #b-4 `-L … nosuch.txt` | **no** |
| r4 #m-4 `-A` | yes (`-A 2`) |
| r4 #m-4 `-B`/`-C` | **no** |
| r4 #m-4 dotfile skipped in `-r` walk | **no** |
| r4 #s-1 M14 `-c zzz nosuch.txt` | **no** |
| `_grep_stdin_addendum` | yes (R2 + AC-5) |
| bug-081 | yes (R3, R5, AC-4) |
| the "13 survivors" | **not all**: 4 sit on the path-less read 16.5 keeps → [[#b-2]] |
| r5 [[#b-1]] display | **no**: R3 keeps the renderer |

## Deferral sweep (rules 9 / 9a) {#deferrals}

No hard or soft deferral was added in `src/`, `tests/` or `bin/`. "The branch itself is replaced by
plan-16 task 16.5" (bug-082's row) and the summary's superseded list both point at a task spec that
exists with acceptance criteria. Plan-16 is `drafting` and sequenced right after this branch merges.
That makes them MEH-grade active deferrals, and they are not counted.

## State facts, re-derived {#state}

| claim | verdict |
|---|---|
| "2514 passed, 1 failed (test_installed_hooks_match_generated)" | **true.** 1 failed / 2514 passed in 997.57 s at `c8278b1` (`workflow/review-output/bsd-r5-full.log`). The one failure is `script rmxgrep-rewrite.py differs`, the expected template drift |
| tree during the run | `git status` before and after showed one untracked file, the concurrent spec reviewer's report (`…-0140-plan16-spec-review-r3…`). No `src/` change |
| three new SKETCHY tests have power | **true**: A3/D3/D4 (cap), D6/D6b (`-w`), E1 (throttle) each FAIL |
| bug-083/084 RED tests | have power under mutation (A1, A4, A5) |
| live store untouched | one read-only open of the live replica through a symlinked cwd, with no write ([[#method]]) |

## Verdict {#verdict}

**DIRTY: 8 findings (2 BULLSHIT, 3 SKETCHY, 3 MEH).**

Both code blockers that r4 left in surviving code are closed in their mechanism. The single
total-order read is correct, faster, and pinned. The row set no longer depends on the cwd. All
three new tests have power. The new defects sit beside the fix:

- **The display.** The resolved path is used to read and the unresolved path is printed
  ([[#b-1]]).
- **The base.** The chosen base is wrong for the global store ([[#s-1]]).
- **The tests.** The half of r4 #s-1 that sits on the read path 16.5 keeps is still unpinned
  ([[#b-2]]).

**Blockers for merging `bsd-r1-remedy`:** [[#b-1]] (print the resolved path, dedupe after
resolution) and [[#b-2]] (two tests). Both are small.

rel: contradicts -> [[claude#no-silent-failures]]
rel: amends -> [[bsd-r1-remedy-r4-4d54f6a]]
