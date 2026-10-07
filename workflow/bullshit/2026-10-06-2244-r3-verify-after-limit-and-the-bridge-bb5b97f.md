---
gmd: "0.1"
id: bsd-r1-remedy-r3-bb5b97f
title: "r2 remedy + bug-073/074: the walk is fixed, and the precision fix truncates silently, drops -i on the daemon read, and quietly ends the spelling bridge"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r2
round: 3
prior: 2026-10-06-1552-r2-the-argv-sort-regresses-the-walk-ae39044.md
tags: [bsd, audit, remediation, grep, drop-in, index, precision, registry]
---

# ch-bsd findings — round 3 over the r2 remedy and bug-073/074 {#root}

**Range:** `ae39044..bb5b97f` (7 commits). Core: `d5e7fec` (bug-073/074 + r2 remedy),
`24523f3` (three fixture rewrites). Also: `7a7efa0`/`4f70a0b` (save-state embed line once),
`607e9db` (peer helix session: ADR-0004, spike, bug-075 — docs/eval only), `8ebb691`/`bb5b97f`
(handoff).
**Commit:** `bb5b97ff1f95c0525023548e672637f0275154a6` — *docs(handoff): correct the State line*
**Audit written:** 2026-10-06T22:44:05-0700
**Author:** Todd Holley / Opus 5 (1M) / orchestrator (d5e7fec..4f70a0b); Todd Holley / Opus 5.5 /
peer helix session (607e9db)
**Prior round:** [[bsd-r1-remedy-r2-ae39044]] — DIRTY, 11 findings (4B/4S/3M)

rel: amends -> [[bsd-r1-remedy-r2-ae39044]]
rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[claude#no-mocks]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]

## How this was checked {#method}

- **Drop-in behaviour** by direct `subprocess` exec, list argv, no shell, `/usr/bin/grep` as the
  control and `.venv-eval/bin/rmx` vs the deployed `~/bin/rmx` (0.76.0) on a throwaway store in
  the session scratchpad (`Store.init()`, no daemon, `RMX_GREP_NOTE=0`).
- **Index read** on a COPY of this repo's `catalog.read.duckdb` (569 MB) in the scratchpad — never
  the live store, never through a daemon.
- **Mutations** in an isolated `git archive HEAD` copy run with `PYTHONPATH=<copy>/src` (the shared
  tree's `src/` was never written); the e2e tests ran in the copy through a symlinked `.venv-eval`
  and were proven to import the copy (a mutation failed them). `__pycache__` cleared before and
  after each; restore verified byte-identical. Log: `workflow/review-output/bsd-r3-mutations.log`.
- **Full suite** at HEAD: `workflow/review-output/bsd-r3-full.log` (see [[#state]]).

## Findings {#findings}

### BULLSHIT #b-1: verification runs AFTER the SQL `LIMIT`, so the default `rmx grep PAT` is a silent short read {#b-1}

**File:** `src/refmatrix/store.py:3117-3133` (`grep_evidence`: `LIMIT ?` in the SQL, then
`verify_evidence_rows(out, …)`)

**What:** bug-074 verifies each row against its real line — after the SQL has already cut the
result to `limit` raw rows. Most raw rows are `def`-line rows that verification drops, so the cap
is spent on rows that never reach the user.

**Why it's bullshit — measured on a copy of the live replica, dev CLI, no paths (the exploration
read, default `--limit 100`):**

| pattern | verified rows that exist (`--limit 0`) | default `rmx grep PAT` | stderr | exit |
|---|---|---|---|---|
| `error` | **96** | **13** | *(empty)* | 0 |
| `partition` | **128** | **51** | *(empty)* | 0 |

13 of 96, exit 0, nothing on stderr. Deployed 0.76.0 on the same copy returns 100 rows — wrong
ones, but the cap was at least visible as a full page. This is bug-058's shape exactly — "a short
read that looks successful is the worst failure shape this project has" — and `verify_evidence_rows`'
own docstring cites bug-058 to argue it is "a filter and not a truncation". That holds only for the
FULLY-filtered case. The partially-filtered case is a truncation with no notice.

`handoff.md#next` item 7 frames the remaining breadth as "a cost question (74 rows fetched to keep
4) rather than a correctness one". It is a correctness one: the 70 rows are not just fetched, they
consume the cap.

**Fix:** verify before capping — page the SQL until `limit` VERIFIED rows are collected (or fetch
uncapped, verify, then cap), and keep the existing truncation note when the cap bites.

**Pattern match:** YES — bug-058 (silent short read), and [[impression_bsd_guard_cannot_fire]]:
every verification test runs with `limit=None` or a fixture smaller than the cap.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-2: bug-073 is closed on two of four read paths; its "Live … grep's behaviour exactly" ran through the floor {#b-2}

**Files:** `src/refmatrix/cli.py:6800-6803` (`_grep_run`'s RPC call), `cli.py:6508-6511`
(the floor's case flag), `workflow/bug_registry.md` bug-073

**(a) The daemon-RPC read never sends `-i`.** `_grep_run` calls
`daemon_mod.call(root, "grep_indexed", {"pattern", "regex", "linkage", "kind", "limit"})` — no
`ignore_case`. `_op_grep_indexed` reads `args.get("ignore_case", False)` and its new comment says
"Same rule as the CLI's two read paths — one implementation, three callers". Probe (real `Daemon`,
real `Store`, a forwarding shim that hands the CLI's args to the real `OPS["grep_indexed"]`; file
line `ERROR raised here`, evidence on it under `keyword/error`, `rmx grep -i error`):

```
RPC args sent: [{'pattern': 'error', 'regex': False, 'linkage': None, 'kind': None, 'limit': 100}]
answered_by: floor
DIRECT branch answered_by: index | …/a.py:1  [mentions]  keyword/error
```

Same invocation, same store: the direct branch answers from the index, the daemon branch falls to
the floor. **No test can see it** — mutations M5 (replica path drops `ignore_case`) and M6 (the op
ignores it) both SURVIVE all seven grep test files. The only `-i` test is a store-level call.

**(b) The drop-in floor is smart-case, not grep-case.** `ignore_case is None` (no flag) maps to
`rg -S`, which is case-INSENSITIVE for a lowercase pattern:

| invocation | `/usr/bin/grep` | rmx dev | rmx 0.76.0 |
|---|---|---|---|
| `error e.txt` (file: `ERROR here`) | *(nothing)*, exit 1 | `ERROR here`, exit 0 | same as dev |
| `-c error e.txt` | `0`, exit 1 | `1`, exit 0 | same as dev |

This is the path every rewritten bare `grep` takes. The bug-073 row's evidence — "Live: `rmx grep
error f.txt` hits, `rmx grep ERROR f.txt` reports no matches, `rmx grep -i ERROR f.txt` hits —
grep's behaviour exactly" — used NAMED FILES, and `_index_may_answer(paths)` is `not paths`, so
none of those three calls touched the code bug-073 changed. They exercised the floor, on a file
that held lowercase `error`, which is the one input where smart-case and grep-case agree.

Pre-existing in the floor; the defect in this range is the FIXED claim and the evidence behind it.

**Fix:** send `ignore_case` on the RPC (and add a CLI-level `-i` test through BOTH read branches);
make the floor `-s` when `ignore_case is None` on a drop-in read; correct the bug-073 row.

**Pattern match:** YES — the sibling-branch shape, now in the read that the commit message and the
op's comment both say was threaded; [[bsd-pattern-sibling-render-path]].

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-3: bug-074 quietly ends the bug-067/070 spelling bridge, and the guards that pinned it were re-pointed so they stay green {#b-3}

**Files:** `src/refmatrix/store.py` `verify_evidence_rows` (literal `pattern in line`),
`tests/test_grep_learned_reachable.py` `_concept_names` (now `verify=False`),
`eval/production/grep_evidence_breadth.py:108`

**What:** bug-067's fix let a space-spelled query reach underscore-spelled concepts through
`canonical_name`; bug-070 then chose its predicate by measuring that REACH — "the number not to
lose" — and the instrument's own docstring says literal precision against `rg` was discarded
because it "would have indicted the mechanism it was built to protect". bug-074's verification is
exactly that literal check, applied in production.

**Evidence — bug-070's own 16 instrument patterns, on a copy of the live replica, raw → verified:**

```
'build context'    rows 12 -> 0   answered True -> False
'scan prompt'      rows 20 -> 0   answered True -> False
'replica bundle'   rows  7 -> 0   answered True -> False
'grep evidence'    rows  1 -> 0   answered True -> False
'learn queue'      rows  1 -> 0   answered True -> False
'ERROR'            rows 737 -> 0  answered True -> False
answered: 13 -> 8 of 16
```

Five of the bridge's multi-word answers are gone. Whether a grep-shaped read SHOULD answer
`replica bundle` from `_replica_bundle` is a fair product question. The trade was not taken, though;
it was hidden:

- **The guards were re-pointed.** `test_the_spelling_bridge_survives_the_narrowing` and
  `test_a_leading_underscore_identifier_is_still_reachable` called `_op_grep_indexed` at
  `ae39044`; `d5e7fec` routed `_concept_names` to `store.grep_evidence(…, verify=False)` with the
  docstring "which concepts does the SQL select is a different subject". Pointing the helper back
  at the production op fails four tests, and the assertion messages describe this regression:
  `the dash spelling is gone`, `the leading-underscore identifier lost its index answer`
  (`workflow/review-output/bsd-r3-bridge-probe.log`). Those tests are named for REACH, and REACH
  is what a production read gives the user. They were right, and they were moved off the
  production path so they would not say so.
- **The instrument changed meaning silently.** `grep_evidence_breadth.py` calls
  `grep_evidence(pat, limit=None)` and now gets verified rows by default. Its committed numbers
  and `docs/measurements/grep-canonical-breadth.md` can no longer be reproduced by re-running it.
- **The rows still say FIXED with reach intact.** bug-070: "all 16 patterns still answered".
  bug-067: "first-call index answers rose 29 -> 43 because the canonical predicate also reaches
  ingest-time concepts". Neither row is amended; bug-074's row mentions only the replay share.

**Fix:** decide it in writing. Either (a) verify a row the canonical predicate selected against the
pattern's identifier VARIANTS (`roaring_bitmap`, `RoaringBitmap`, `roaring-bitmap`), which keeps
the bridge and still drops the `def`-line rows, or (b) accept the loss — amend bug-067/070, rename
and re-scope the two guards to assert the production read's actual behaviour, pass `verify=`
explicitly in the instrument, and re-run grep-canonical-breadth.

**Pattern match:** YES — rule 10, *test bent to match code*; [[impression_bsd_guard_cannot_fire]].

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-4: r2 #b-2/#b-3 are half closed — the fabricated zero moved to the nothing-matched branch, and the "spelling" is not the argv spelling {#b-4}

**Files:** `src/refmatrix/cli.py:6645-6655` (empty-output `-c` branch), `cli.py` `grep()`
(`paths = [Path(p) for p in path_strs]`), `argv_order_index`

**(a) A new bare `0`, worse than deployed.** The old empty-output branch printed `0` only when
`not shape["with_filename"]`. The remedy's `else: click.echo("0")` dropped that guard:

| invocation | `/usr/bin/grep` | rmx 0.76.0 | rmx dev |
|---|---|---|---|
| `-rc zzz sub` | `sub/s1.txt:0` `sub/s2.txt:0`, exit 1 | *(nothing)* | **`0`** |
| `-c zzz sub nosuch.txt` | 2 errors, exit 2 | *(nothing)* | **`0`** |
| `-c zzz nosuch.txt` | error, exit 2 | `0` | `0` |

A bare number in a filename-shaped answer, for a directory and a file that does not exist: the
`.:0`/`nosuch.txt:0` class r2 #b-2 named, relocated into the branch r2 #b-3 named. The comment
justifying it — "No named files (a walk, or stdin): one number, as before" — is wrong twice:
`grep -rc` prints a row per walked file, and "as before" had the `with_filename` guard.

**(b) The identity is not the argv spelling.** `grep()` turns argv into `Path` objects before any
of this code runs, and `str(Path("./f0.txt")) == "f0.txt"`:

| invocation | `/usr/bin/grep` | rmx dev |
|---|---|---|
| `-c alpha ./f0.txt f0.txt` | `./f0.txt:3` `f0.txt:3` | **`f0.txt:6`** — one row, SUMMED |
| `-n alpha f0.txt ./f0.txt` | `f0.txt:…` ×3, `./f0.txt:…` ×3 | `f0.txt:…` ×6 |
| `-rn alpha ./sub sub` | `./sub/…` then `sub/…` | `sub/…` ×2 |

r2 #b-2's title is "merges two files into one `-c` row and SUMS their counts"; r2 listed this row
in its table. The symlink half is fixed (`-c alpha alias.txt f0.txt` now matches grep); the
`./` half is not, while the new docstring states "grep echoes a path exactly as given, so the
SPELLING is the identity". Raw `rg` keeps both spellings; the normalisation is ours.

**What IS closed:** the walk grouping and every named-file case I ran — see [[#closed]].

**Fix:** keep `path_strs` as the argv identity through to `argv_order_index`; in the empty-output
branch print the bare `0` only when `not with_filename` (stdin / single file), and emit per-walked-
file zeros for `-rc` (`rg --include-zero`) in both branches.

**Pattern match:** YES — 10th sighting of [[impression_bsd_quoted_line_sibling]]: the remedy fixed
the rows the audit quoted and the branch beside them took the bug.

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-1: `4f70a0b` ("test(save-state)…") carried five unrelated files: it re-tracks the gitignored egg-info and overwrites a benchmark result {#s-1}

**Files:** `src/refmatrix.egg-info/{PKG-INFO,SOURCES.txt,entry_points.txt,requires.txt}`,
`eval/results/csn_python/rmx_bm25_docstring30_cov30_cm20/metrics.json`

- `*.egg-info/` is ignored (`.gitignore:6`); `438f3a2` ran `git rm --cached` on exactly these files
  because "they re-dirtied the tree on every pip install -e". They are tracked again, with
  `Version: 0.3.10` (the package is 0.76.0). Checked with a two-clone test: a `pull --ff-only`
  OVERWRITES ignored untracked files silently, so the next deploy replaces `~/refmatrix`'s egg-info
  (0.66.3) with these stale files, and every later `pip install -e` dirties the deploy tree again.
  Runtime is unaffected (`__version__` is a literal, not metadata) — I checked.
- `metrics.json`: `elapsed_sec` 104.7 → **1016.1** (10x, a loaded-machine run) plus float noise in
  `MRR@10`/`nDCG@10`, written over the committed reference result.

Neither is mentioned in the commit message.
**Fix:** `git rm -r --cached src/refmatrix.egg-info`; restore `metrics.json` or recommit it with a
reason.

### SKETCHY #s-2: r2 #s-1 was fixed in one test; its twin keeps the stub, and the registry says the stub is gone {#s-2}

**File:** `tests/test_save_state_embeds_memories.py:291-301`, `workflow/test_mock_registry.md`

`monkeypatch.setattr(Store, "upsert_vector", lambda self, *a, **k: None)` is still there, class-
level, in `test_…_remaining…` 180 lines above the test the remedy fixed. Its own comment states r2's
critique: "upsert_vector is stubbed, so the stamp never moves and all 7 remain", asserting
`remaining > 1`, which a count sampled before the loop also satisfies. The new registry row reads
`Store.upsert_vector … — (REMOVED 2026-10-06) | (none)`. Not removed; one of two removed.
**Fix:** drop the stub, assert `remaining == 5 == pending_embeddings_count(...)`; correct the row.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY #s-3: the 24523f3 fixture rewrite cost the daemon op its only regex coverage {#s-3}

**File:** `tests/test_grep.py::test_grep_indexed_regex_anchors`

**On the dispatch's question — cheap fix or faithfulness?** Mostly genuine. `_seed` writing real
files with the pattern on the seeded lines, and the learn test's hit lines existing, make fixtures
match states production can reach; that is the opposite of bending a test. Moving the
`query/foobar` probe to `verify=False` is defensible because `test_grep_learned_reachable` still
drives learned-pattern reach through `_op_grep_indexed` with verification on.

The exception: the regex-anchor test moved from `_op_grep_indexed(daemon, {"pattern": "^token",
"regex": True})` to `daemon.store.grep_evidence(…, verify=False)`. Mutation **M7** (the op passes
`regex=False` regardless) now SURVIVES every grep test file. It did not have to: line 7 of the new
fixture is `tokenizer = 1`, which `^token` already verifies against; one line ending in `parser`
covers `parser$`.
**Fix:** keep the op in that test and make the fixture lines satisfy the anchors.

### SKETCHY #s-4: three r2 findings dropped without a word, and no implementation summary for the remedy {#s-4}

r2 #s-2 (the shadowing `esc` at `app.js:580` — still there), r2 #s-4 (no task spec for the
verb-parity allowlist; `deferral_registry.md` untouched) and r2 #m-4 (`raising=False` at
`tests/test_derive_stamp.py:276` — still there) are not fixed, not in the `d5e7fec` message, not
in `handoff.md`, and there is no `workflow/implementation_summaries/` file for `d5e7fec` or
`24523f3` (CLAUDE.md: MANDATORY). The commit message does report the one disagreement (#m-2,
[[#m-1]]). Second consecutive round where an enumerated list was closed partly and silently (r2
#b-4).

rel: contradicts -> [[claude#task-completion-workflow]]

### SKETCHY #s-5: the measurement docs still state superseded numbers as current {#s-5}

`docs/measurements/grep-learning-replay.md` (last touched `753acd4`, before this range) still
reports index share 18.5% → 31.7% with no scope line; `docs/INDEX.md:85` and
`workflow/plans/plan-14-grep-learning-measurement.md:16` repeat it as the result. bug-074 changes
what "answered from the index" means — on the live copy `ERROR` alone goes 737 → 0 rows — and
[[#b-3]] removes five bridge answers that bug-067's "29 → 43" relied on. The staleness is recorded
only in `handoff.md#next` item 5 and in bug-074's row ("needs a re-run and a scope line"). No task
spec covers the re-run (rule 9a). I am scoring this SKETCHY rather than BULLSHIT because the gap is
written down in the registry, not buried. If it is unchanged at r4, rule 9a applies in full.
**Fix:** a one-line "superseded by bug-074 — re-run pending" banner on the doc and both citing
rows now, plus a task spec for the re-run.

rel: contradicts -> [[claude#before-commit]]

### SKETCHY #s-6: verification drops rows silently and depends on the process cwd {#s-6}

**File:** `store.py` `verify_evidence_rows` / `grep_evidence(verify_stats=…)`

The docstring: "A row whose file cannot be read is DROPPED and COUNTED … `stats["unreadable"]`
carries the number so a caller can say it." `git grep verify_stats -- src tests eval` → only the
definition and its pass-through. No caller collects it, so nothing can say it. On the live copy,
`error`: **213 of 737** raw rows are unreadable. 144 point at deleted session scratchpads. The
other 69 are learned rows with RELATIVE paths (`pytest-plan4-r4-red.log`):
`_learn_grep_hits` stores `path=str(ap)` from a relative argv spelling, so verification resolves
them against whatever cwd the CLI or the daemon has. That makes them unreadable, or the wrong
file.
**Fix:** surface `unreadable` on stderr from the CLI read paths (and in the op result); store
learned paths absolute (resolve against `project_root`) so verification is cwd-independent.

### SKETCHY #s-7: "precision 1.000 on every pattern that still answers" excludes `-w` {#s-7}

`-w` without `-E` leaves `effective_pattern` bare, and verification checks a substring.
`rmx grep -w err` on the live copy: **34 index rows, 0 of 34 lines match `grep -w err`**
(precision 0.000). The verifier is the natural place to honour `-w` (and the exploration help
still says "Default is case-insensitive substring" while the index read is now case-sensitive
and the floor smart-case). Pre-existing breadth; the over-broad claim is new.
**Fix:** pass `word` to the verifier (`\b…\b`), or force the floor for `-w`; fix the help text.

### MEH #m-1: r2 #m-2's disagreement — r2's 80.6% reproduces exactly; the commit's "does not reproduce under either" is wrong {#m-1}

Recomputed from the committed `reachability-{before,after}-fix.json` (`applied > 0`,
`second == "index"`):

| predicate | before | after |
|---|---|---|
| `" " in pattern` (the doc's words: "containing a SPACE") | 41 mw / 34 taught / 0 | 42 / **31** / **25** → **80.6%** |
| `len(pattern.split()) > 1` | 35 / 28 / 0 | 36 / **27** / **24** → **88.9%** |

The 88.9% is right for the split definition, and the doc's literal definition gives 80.6%. The
six-pattern difference is leading/trailing-space patterns. Change the word in the doc.

### MEH #m-2: r2 #m-3's fix is correct by execution and has no test {#m-2}

Direct call with an unreadable store marker and a present global marker:
`Decision(enabled=False, rule='global-marker', …, marker_error='/x/store.marker: PermissionError: …')`.
Correct. No test sets that state, and the "7 new tests, all RED on ae39044" in `d5e7fec` does not
include one.

### MEH #m-3: registry and handoff state facts the tree contradicts {#m-3}

bug-073 and bug-074 are `fixed` while `git merge-base --is-ancestor d5e7fec master` is false
(`feedback_verify_fix_reachable_from_master`). `handoff.md#state-deploy` still says the remedy
"exists only on `master`", which is the reverse of the State line that `bb5b97f` corrected.

### MEH #m-4: `-c`/missing-path behaviour on the floor (pre-existing, adjacent to #b-4) {#m-4}

`-rc alpha .` omits zero-count files (`z1.txt:0`, `z2.txt:0`); `rg -c` needs `--include-zero`.
`_grep_rg_fallback` never reads `res.stderr` or `res.returncode`. A missing path gives
`rmx grep -n alpha nosuch.txt` → "no matches", exit 1, where grep prints the error and exits 2,
so "absent" and "zero" cannot be told apart from the exit code. Both match deployed 0.76.0.

### MEH #m-5: `_teach`'s fallback re-creates the unfaithful fixture it was written to remove {#m-5}

`tests/test_grep_learned_reachable.py::_teach` falls back to `[{"line": 1}]` when the pattern is not
in the corpus — silently. Unused today (every taught pattern is present — checked), but a future
pattern missing from `_corpus` would teach line 1 again with no error. Raise instead.

## Closed and verified {#closed}

Each one checked by direct exec against `/usr/bin/grep` and/or by a mutation I ran:

- **r2 #b-1 (walk interleaving) — CLOSED.** `-rn alpha .`, `-rn alpha sub`, `-rn alpha sub
  f0.txt`, `-rn alpha f0.txt sub`, `-rl alpha sub f1.txt` are grouped per file, argument order
  across arguments. (Order *within* a walk is still rg's own, which differs from BSD grep's,
  unchanged from deployed and accepted at r2.) M1 (restore the `(rank, line)` key) FAILS 2 unit
  tests and the e2e `test_a_directory_walk_keeps_its_files_GROUPED`. The walk tests now have power.
- **r2 #b-2 symlink half — CLOSED.** `-c alpha alias.txt f0.txt` → `alias.txt:3` `f0.txt:3`,
  identical to grep. Some-matched `.:0` / `nosuch.txt:0` gone (M2 FAILS 5 tests). Open half: [[#b-4]].
- **r2 #b-3 named-file half — CLOSED.** `-c zzz f0.txt f1.txt`, `-hc alpha z1.txt z2.txt`,
  `-hc zzz z1.txt z2.txt` identical to grep (M3 FAILS 2 tests). Open half: [[#b-4]].
- **Named-file order — still CLOSED.** `-c`/`-n`/`-l`/`-L` over reversed argv identical to grep.
- **r2 #b-4 — mostly CLOSED.** Rows now exist for `test_derive_stamp.py`, `test_derive_surface.py`,
  `ls.Path.exists`, `_DERIVE_*`. The `upsert_vector` row is false ([[#s-2]]).
- **r2 #s-1 — CLOSED for the capped test** (`remaining == 7 == pending_embeddings_count`,
  unstubbed); twin open ([[#s-2]]).
- **r2 #s-3 — CLOSED.** The docstring now states the bound and the measured horizon;
  50 / (12 / 2.66 h) = 11.1 h checks.
- **r2 #m-1 — CLOSED.** The colon-split branch and the `_file_rank` alias are gone.
- **r2 #m-3 — CLOSED by execution**, untested ([[#m-2]]).
- **bug-074's core claim** holds where it applies: on the live copy every verified row I sampled is
  a real match, and the fully-filtered case does fall to the floor (`ERROR` → floor banner). M4
  (skip verification) FAILS 4 tests; M8 (ignore the case flag) FAILS 1.
- **7a7efa0/4f70a0b (embed line once) — CLOSED.** Every path that produces `fin["embed"]` also
  echoes a report that already carries the line (daemon op and in-process twin both append it);
  M9 (restore a second print) FAILS `test_save_state_command_renders_the_embed_line`.
- **607e9db** touches no `src/` or `tests/`. The spike scripts take the store root from argv and open
  it `read_only=True` (README: replica copies). Nit: they pickle to another session's absolute
  scratchpad path, so they cannot be re-run as committed.

**Still open from r2:** #b-2 (half), #b-3 (half), #s-2, #s-4, #m-2 (author's pushback incorrect),
#m-4.

## Deferral sweep (rules 9 / 9a) {#deferrals}

Added lines in `src/`, `tests/`, `eval/` (egg-info excluded): no hard or soft deferral hits. The one
unanchored deferral in the range is the replay re-run, which lives in prose ([[#s-5]]). bug-075 is
an `open` registry row, which is the sanctioned place for it.

## State facts, re-derived {#state}

| claim | verdict |
|---|---|
| HEAD `bb5b97f`, tree clean | true at start and end |
| not deployed; deploy at `1452875`, fleet 0.76.0 | true (`~/refmatrix` at `1452875`) |
| GMD lint 0 errors | true (`./scripts/lint-gmd.sh`, 0 `: error`) |
| full suite green ("2475 passed") | **true** — 2475 passed / 0 failed in 969.89 s at HEAD (`workflow/review-output/bsd-r3-full.log`); every finding above sits in a path no test reaches |

## Verdict {#verdict}

**DIRTY — 16 findings (4 BULLSHIT, 7 SKETCHY, 5 MEH).**

The r2 regression is fixed properly: a walk is grouped again, and the tests that missed it now have
power. Named-file `-c`/order matches grep on every case I ran. bug-074 is a real improvement in
what an index row MEANS. But it shipped three defects of its own. It truncates silently because it
filters after the `LIMIT`. Its `-i` half never reached the daemon read, and the "live" proof for
that half ran through a path that never touched it. And it removed the bug-067/070 spelling
bridge, with the guards that pinned the bridge re-pointed so they would stay green. The `-c` remedy
moved r2's fabricated zero into the branch next to the one r2 quoted.

**Blockers for closing plan-15 / merging `bsd-r1-remedy`:** [[#b-1]], [[#b-2]], [[#b-3]], [[#b-4]],
plus [[#s-1]] (untrack the egg-info before any deploy pull). Round 4 is owed.

rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[claude#no-mocks]]
rel: amends -> [[bsd-r1-remedy-r2-ae39044]]
