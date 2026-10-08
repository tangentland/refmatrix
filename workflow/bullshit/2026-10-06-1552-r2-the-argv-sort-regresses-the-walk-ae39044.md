---
gmd: "0.1"
id: bsd-r1-remedy-r2-ae39044
title: "r1 remedy: #b-3 and the count are real, and the argv-order fix made `grep -rn <dir>` strictly worse than before it"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r1
tags: [bsd, audit, remediation, grep, drop-in, embed, registry]
---

# ch-bsd findings — round 2 over the r1 remedy {#root}

**Range:** `1452875..ae39044` (7 commits, 27 files, `src/` +183/-38)
**Commit:** `ae39044370601f945d0f1fd7abbcfd215e4d6c47` — *test: harden the order canary to 3 execs; drive #b-1's CAPPED branch for real*
**Audit written:** 2026-10-06T15:52:47-0700
**Author:** Todd Holley / Opus 5 (1M) / orchestrator (6 of 7 commit bodies carry `Co-Authored-By: Claude Opus 5 (1M context)`)
**Prior round:** [[bsd-plan14-15-grep-family-1452875]] — DIRTY, 13 findings (5B/5S/3M)

rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[claude#no-mocks]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]

## The state facts, re-derived rather than taken {#state}

| claim | verdict |
|---|---|
| HEAD `ae39044`, `git status --short` empty | **true**, both at audit start and end |
| suite 2453 passed / 0 failed, log `pytest-bsd-r1-remedy-full.log` | **consistent** — `--collect-only` at HEAD is **2453**, the log's last line is `2453 passed … 1005.27s`, log mtime 15:35 ≈ 15:18:09 + 1005 s, 0 `^FAILED`/`^ERROR` lines |
| no `src/**.py` written during the run (#b-3's gate) | **true, re-measured** — `find src -newermt "2026-10-06 15:18:09" -name '*.py'` empty; `src/refmatrix/store.py` mtime `14:48:12`; newest files in `src/` are `cli.py` 15:13:01 and `learn_switch.py` 15:05:26, both before the run |
| remedy NOT deployed; `~/refmatrix` at `1452875`, fleet 0.76.0 | **true** — deploy sha `1452875`, clean; `rmx hub status` 8 stores all `v0.76.0`, code path `~/refmatrix/src` |
| GMD lint 0 errors / hooks in sync | **true** — zero `: error` lines; `hooks in sync` |
| plan-15 back to `in-progress` | **true** in the plan frontmatter and in `plan-of-plans.md` |

So every regression below is on a branch and not yet live. That is the only
good news in the `-c`/order section.

## Findings {#findings}

### BULLSHIT #b-1: the argv-order fix REGRESSES `grep -rn PAT <dir>` — a walk is now interleaved by line number {#b-1}

**File:** `src/refmatrix/cli.py:6433-6439` (`order_triples_by_argv`), applied at `:6646`

**What:** the hoisted sort is a no-op only when `order` is EMPTY:

```python
if not order:
    return list(triples)
return sorted(triples, key=lambda tr: (argv_rank(tr[0], order), tr[1]))
```

**Why it's bullshit:** `rmx grep -rn PAT .` **names a path**, so `order` is not
empty — it holds exactly one entry, the directory. Every file the walk actually
produces ranks `len(order)`, so every triple ties on the primary key and the
secondary key is `tr[1]`, **the line number**. File grouping is destroyed.

**Evidence — direct exec, three builds, one throwaway store** (`/tmp/gX.y9E7`,
own `.refmatrix`, no daemon; three files of `alpha\nbeta\nalpha\nbeta\nalpha`):

```
/usr/bin/grep -rn alpha .          rmx 0.76.0 DEPLOYED (pre-remedy)   rmx dev (this remedy)
./f0.txt:1  ./f0.txt:3  ./f0.txt:5   ./f2.txt:1 ./f2.txt:3 ./f2.txt:5   ./f2.txt:1 ./f0.txt:1 ./f1.txt:1
./f1.txt:1  ./f1.txt:3  ./f1.txt:5   ./f0.txt:1 ./f0.txt:3 ./f0.txt:5   ./f2.txt:3 ./f0.txt:3 ./f1.txt:3
./f2.txt:1  ./f2.txt:3  ./f2.txt:5   ./f1.txt:1 ./f1.txt:3 ./f1.txt:5   ./f2.txt:5 ./f0.txt:5 ./f1.txt:5
     grouped per file                     grouped per file               INTERLEAVED
```

The pre-remedy build got the file ORDER wrong and the grouping right. The
remedy gets the grouping wrong, which no grep has ever done. Same at
`-rn alpha sub` (`s2:1 s1:1 s2:2 s1:3` vs grep's `s1:1 s1:3 s2:1 s2:2`), and
`-n alpha f0.txt .` interleaves `f0.txt` with `./f0.txt` pairwise. This is the
form every bare `grep -rn` on this machine is rewritten into.

**Why no test caught it — two tests named for exactly this, both blind:**

- `tests/test_grep_fixed_and_file_lists.py::test_a_directory_walk_is_not_reordered`
  writes ONE matching line per file and asserts `len(_lines(res.stdout)) == 2`.
  Interleaving two single-line files is unobservable.
- `tests/test_grep_argv_order_e2e.py::test_a_directory_walk_is_not_reordered`
  asserts `len(_first_appearance(out)) == N_FILES` — a count of DISTINCT files,
  which full interleaving satisfies.
- `tests/test_grep_argv_order.py::test_a_walk_keeps_the_tools_own_order` passes
  `order={}`. A walk never produces that state; only a path-LESS invocation
  does (verified: `rmx grep -rn alpha` with no path is correctly grouped). The
  unit test pins the guard for a configuration the defect cannot be in.

**Proved in the repo's own harness**, by copying that test file and adding a
grouping assertion (3 matching lines per file instead of 1):

```
AssertionError: a walk's files are interleaved:
  ['./a.txt', './b.txt', './a.txt', './b.txt', './a.txt', './b.txt']
assert 6 == 2
```
…in a run where both shipped `test_a_directory_walk_is_not_reordered` cases passed.

**Fix:** the secondary key must preserve the tool's own per-file grouping for
unranked files — e.g. `sorted(enumerate(triples), key=lambda it: (argv_rank(...), it[0]))`,
or `(rank, first_seen_index[f], line)`. Equivalently: only sort when the
triple's file IS a named path, which is what the docstring already claims.

**Pattern match:** YES — [[impression_bsd_guard_cannot_fire]] + the sibling-branch
shape. The guard was written for the state the author imagined a walk has.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-2: `Path.resolve()` as the argv identity merges two files into one `-c` row and SUMS their counts {#b-2}

**File:** `src/refmatrix/cli.py:6396-6416` (`argv_order_index`), consumed at `:6647-6662`

**What:** `argv_order_index` keys both dicts on `str(Path(p).resolve())` with
`setdefault`, and the `-c` render seeds one zero row per key.

**Why it's bullshit:** four differential cases, same throwaway store, `/usr/bin/grep`
by direct exec as the control. Two are NEW in this remedy and strictly worse
than the pre-remedy build:

| invocation | `/usr/bin/grep` | rmx 0.76.0 (pre) | rmx dev (this remedy) |
|---|---|---|---|
| `-c alpha alias.txt f0.txt` (symlink → f0) | `alias.txt:3` `f0.txt:3` | `f0.txt:3` `alias.txt:3` | **`alias.txt:6`** — one row, SUMMED |
| `-c alpha .` | `grep: .: Is a directory` | per-file rows | **`.:0`** + per-file rows |
| `-c alpha f0.txt nosuch.txt f1.txt` | stderr error, `f0.txt:3` `f1.txt:3` | `f1.txt:3` `f0.txt:3` | `f0.txt:3` **`nosuch.txt:0`** `f1.txt:3` |
| `-c alpha f0.txt ./f0.txt` | `f0.txt:3` `./f0.txt:3` | `f0.txt:6` | `f0.txt:6` (unchanged) |

Two distinct argv entries that resolve to the same inode collapse to one row
whose count is the SUM — a wrong number, not merely a wrong order, and the
pre-remedy build had both rows right. And every argv entry is seeded as a file
with count 0 whether or not it IS a file: a directory is reported as a
zero-match file, and a nonexistent path is reported as `nosuch.txt:0` where
grep writes to stderr and exits 2. That is *0 and absent made
indistinguishable* by construction, manufactured by the fix.

**Evidence:** the table above, every cell a direct `subprocess` exec with a list
argv (no shell for the rewrite hook to see; the `# rmx grep fallback via rg`
banner absent from every control).

**Fix:** key the order/display maps on the argv spelling, using `resolve()` only
to MATCH tool output back to a spelling — and seed a zero row only for argv
entries that `is_file()`. `argv_order_index` additionally `continue`s past an
unresolvable path without counting it, which silently drops that file from both
the order and its zero row.

**Pattern match:** YES — new shape for this ledger (an identity function that
over-merges), kin to [[impression_bsd_substring_signature_widens]].

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-3: the `-c` zero-row rule reaches the some-matched branch only; "nothing matched" still drops every row {#b-3}

**File:** `src/refmatrix/cli.py:6586-6595` (the empty-output branch) vs `:6647` (the seeding)

**What:** the seeding lives *after* `if not res.stdout.strip():`, which returns first.

**Why it's bullshit:** the remedy's own test docstring states the rule —
"`grep -c` prints a row for EVERY named file, zeros included" — and the branch
where EVERY file is a zero is the one that does not do it:

```
$ grep -c zzz f0.txt f1.txt        $ rmx grep -c zzz f0.txt f1.txt
f0.txt:0                          (nothing)
f1.txt:0                          rmx grep: no matches
exit 1                            exit 1

$ grep -hc alpha z1.txt z2.txt     $ rmx grep -hc alpha z1.txt z2.txt
0                                 0            <- one row for two files
0
```

So `rmx grep -c PAT *.py` is still wrong on its own inputs whenever the pattern
is absent from all of them, and `-hc` under-reports its row count. The summary
claims "The `-c` half was always closed: a row per named file, zeros included,
in argv order" — that holds only when at least one file matched.

This is the **third** sibling-branch instance inside one remedy, in the same
function whose own comment at `:6530` already warns that this branch "gets BOTH
of their answers wrong" for `-l`/`-L`. The warning was read and not applied to
`-c`.

**Fix:** move the count render before the empty-output branch, as `-l`/`-L`
already were, or seed and emit the zero rows inside it.

**Pattern match:** YES — 8th sighting of [[impression_bsd_quoted_line_sibling]];
see [[bsd-pattern-sibling-render-path]], which this range itself filed.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT #b-4: #b-5 closed 3 of its 5 enumerated files; the double it named as most dangerous is still unregistered, and the remedy added two more {#b-4}

**File:** `workflow/test_mock_registry.md` (+6 rows)

**What:** r1 #b-5 enumerated five files. The remedy added six good rows covering
`test_derive_coverage.py`, `test_save_state_embeds_memories.py`, `_FakeEmb`,
`test_plan12_remedy.py`, `test_grep_learned_reachable.py` and a deleted
`_reversing_tool`. Still absent:

| file | doubles with no row | note |
|---|---|---|
| `tests/test_derive_stamp.py` | `Path.read_bytes` ×2 (**global class patch**), `store.derive_code_hash` ×2, `store._DERIVE_CODE_MODULES`, `store.__file__` ×2 | r1: "`Path.read_bytes` monkeypatched globally is additionally the most dangerous shape on the list" |
| `tests/test_derive_surface.py` | `refmatrix.daemon.ping` ×2, `refmatrix.daemon.call` | **no row for this file at all** |
| `tests/test_save_state_embeds_memories.py` | **NEW:** `Store.upsert_vector` → no-op (class-level patch of a real store WRITE) | and the file's own new row says "`_op_embed`'s own arithmetic runs for real **against a real Store**" |
| `tests/test_learn_toggle_sites.py` | **NEW:** `ls.Path.exists` → raises (global class patch) | same hazard class as `Path.read_bytes` |

`grep -c upsert_vector workflow/test_mock_registry.md` → 0.

**Why it's bullshit:** registry omission is SKETCHY by rule 3, escalated in this
ledger at plan-2 (3-for-3), plan-1 r5, plans 7-10 r4 (6th strike) and r1 (#b-5,
BULLSHIT). A partial close of an ENUMERATED list is rule 10's *scope shrunk
silently*: `workflow/implementation_summaries/remedy-bsd-r1-1452875.md#open`
lists what remains open and does not mention it, and the headline says "Six
registry rows" without saying "of five files, three".

**Fix:** one row per remaining double, plus the two the remedy introduced.

**Pattern match:** YES, 7th.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY #s-1: the capped-branch test stubs `Store.upsert_vector`, and that stub is both unnecessary and the reason the test cannot see the bug's twin {#s-1}

**File:** `tests/test_save_state_embeds_memories.py:435-488`
(`test_the_capped_branch_reports_a_real_count_from_the_real_producer`)

**What:** the test asked for in the dispatch does reach the capped branch for
the claimed reason — `batches=2` is exhausted with `remaining > 0`, verified.
But it also patches `Store.upsert_vector` to a no-op, so the stamp never moves,
the drain re-embeds the SAME row twice, and `remaining` stays pinned at the
initial 9.

**Why it's sketchy:** with the stamp frozen, `out["remaining"] == 9` is also
what a `remaining` sampled BEFORE the loop would produce. The assertion can
tell the old `len(pending_embeddings(limit=1))` from a real count, and cannot
tell a re-measured count from a pre-measured one — which is the next version of
the same defect.

**And the stub buys nothing.** The identical scenario with `upsert_vector` left
real, run under pytest in this repo's dev venv:

```
OUT: {'embedded': 2, 'remaining': 7, 'batches': 2, 'capped': True, 'error': None}
real count now: 7
line: memory embed capped after 2 batches: 2 embedded, 7 still without vectors …
1 passed in 0.57s
```

Still capped (the budget, not the stub, is what caps it), 0.57 s, and
`remaining` now *tracks real progress* 9 → 7 — strictly the stronger assertion,
with one fewer double.

**Fix:** delete the `upsert_vector` patch and assert `remaining == 7` plus
`== pending_embeddings_count(...)`.

rel: contradicts -> [[claude#no-mocks]]

### SKETCHY #s-2: a second `esc` shadows the module-level one `app.js` hoisted for exactly this, and the siblings are unswept {#s-2}

**File:** `src/refmatrix/ui/static/app.js:580` (new) vs `:6-8` (existing)

**What:** `app.js` already carries a module-level escape whose comment says why
it is there:

```js
// Shared HTML escape. Was a local const inside the file viewer; hoisted so any
// renderer interpolating server data into innerHTML can reach it.
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({…}[c]));
```

The remedy defined a second, shadowing `const esc` inside `doWhere` with a
four-`replace` chain and a different null test. Two copies of one rule, in a
remedy whose own #b-1 fix exists to stop a rule being implemented per call path
(`_pending_embeddings_where`). Three other renderers already call the shared one
(`:112`, `:128-134`, `:970`), so reachability was never in question.

**The sibling half, recorded because the remedy's comment establishes the
hazard** ("`reason` now carries exception text and filesystem paths"): the same
server-produced text reaches `innerHTML` unescaped at `:351`
(`<div class="err">${d.error}</div>`), `:425` (`${r.error || "error"}`) and
`:476` (`${d.from}`, `${d.channel}`, `${d.body}` from the bus). Pre-existing and
declared out of scope by the author, not a new defect — but it is the 9th
instance of this range's own pattern file, now in the file that pattern is
named after.

**Fix:** delete the local `esc`; file the three sites as a scoped sweep.

**On the dispatch's question 4 — is a real gate reachable?** Partly. `node
v24.16.0` is on PATH, so a renderer-level test is *possible*, but `app.js` is a
browser module (`fetch`, `WebSocket`, `document`) with no module boundary, so a
real gate means a DOM shim and this repo's first JS test toolchain — a plan, not
a remedy step. The source-level assertion is the right call for now; it does
pin the exact regression (`"skipNote +" in grouped`), and it is named as weak in
both the test docstring and the summary.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-3: #s-3 left the number AND the claim the author called the defect {#s-3}

**File:** `src/refmatrix/store.py:5952-5954`

**What:** I agree with not retuning `DERIVE_HISTORY_MAX = 50` — "the right ORDER
for a cap whose job is bounding the table" is a sound argument, and retuning on
no measurement would be the same unmeasured move inverted. But the remedy's own
reasoning is that *"the defect is the DOCSTRING's claim about what it buys"*,
and the docstring is byte-identical to the one r1 quoted:

```python
# Rows kept per (partition, pass). 50 is enough to see a release arc and
# small enough that the table never becomes the thing you have to prune.
```

r1 measured 4.5 gmd derives/hour → ~11 hours, not a release arc. So the half of
#s-3 that was named as the real defect is untouched, and the summary reports the
item as consciously-left rather than as half-done.

**Fix:** one line — say what 50 rows actually buys (≈11 h at the measured rate,
or "the last N derives", with the rate cited).

rel: contradicts -> [[claude#development-guidelines]]

### SKETCHY #s-4: #m-2's durable half is a deferral with no task spec {#s-4}

**File:** `workflow/deferral_registry.md` (new row)

**What:** the row records the user's decision correctly — "**ACCEPTED, not
deferred**", with the quote, the date, and the scope (`rmx derive log|diff|status`,
`rmx learn on|off|status`). It does not widen it: the eight commands are named,
and the surviving gap (the parity test cannot distinguish "CLI-only by decision"
from "agent-facing and missing its verb") is kept separate and stated in full.
Checked as asked, and it is recorded, not widened.

**Why it is still a finding:** the graduation column reads "next plan touching
`verbs.py` or `test_verb_parity.py`". No task spec under `workflow/plans/*-tasks/`
covers the allowlist, so by the letter of rule 9a this is an unanchored deferral
and rule 9a says BULLSHIT with no grace period. I am filing it SKETCHY and
saying why rather than applying the rule mechanically: the gap, its harm and its
fix are stated in the sanctioned registry instead of buried in a code comment,
r1 scored the parent MEH, and its sibling rows in the same table do point at
plan numbers — which is the one thing this row is missing.

**Fix:** a one-paragraph task spec (acceptance criterion: the parity test reads
an explicit internal-only allowlist and fails on an agent-facing command absent
from `verbs.py`), and point the row at it.

rel: contradicts -> [[claude#before-commit]]

### MEH #m-1: `argv_rank`'s colon-split branch is unreachable, and the test that justifies it states a call shape that does not occur {#m-1}

**File:** `src/refmatrix/cli.py:6419-6431`, `tests/test_grep_argv_order.py` (`test_rank_reads_a_prefixed_line_as_well_as_a_bare_path`)

Both production call sites pass a BARE path: `order_triples_by_argv` ranks
`tr[0]` (`:6439`) and the `-l`/`-L` branch ranks a filename line (`:6558`). No
caller ever hands `argv_rank` a `file:line:text` string, so `head =
line_or_path.split(":", 1)[0]` is dead, and the test's stated reason — "the plain
branch ranks `file:line:text` lines… ONE comparator serves both" — describes
wiring that does not exist. Harmless (a colon-bearing filename resolves on the
first candidate), but it is a docstring claiming a mapping it does not have, in a
file added to fix a finding about exactly that. `_file_rank = argv_rank` at
`:6541` is a one-use alias with no purpose.

### MEH #m-2: #s-4's restated definition is one word off from the one that reproduces {#m-2}

**File:** `docs/measurements/grep-learning-replay.md#fix-numbers` / `#fix-correction`

Recomputed from the committed JSON (`eval/production/results/grep_learning/reachability-{before,after}-fix.json`,
`reachability.rows`, `applied > 0`, `second == "index"`):

| predicate | before | after |
|---|---|---|
| `" " in pattern` — the doc's literal words, "patterns containing a SPACE" | 35 mw → wrong: **41 / 34 / 0** | **42 / 31 / 25** (80.6%) |
| `len(pattern.split()) > 1` — ">1 whitespace token" | **35 / 28 / 0** ✓ | **36 / 27 / 24** ✓ (88.9%) |

So `0/28 → 24/27 (88.9%)` is correct and reproducible, and the stated definition
is not the one that produces it — six patterns whose only space is leading or
trailing. The two alternative pairings the doc offers are also right. One-word
fix: "patterns with more than one whitespace-separated token".

### MEH #m-3: #m-3's own fix drops the note on one of two exits {#m-3}

**File:** `src/refmatrix/learn_switch.py:104-120`

`decision()` collects `problems` from the store-marker read, then checks the
global marker — and if THAT exists it returns `Decision(False, "global-marker",
rejected)`, discarding `problems`. So an unreadable store marker is still
swallowed whenever the global marker answers. The answer is OFF, which is the
safe direction, so this is not the #m-3 harm; it is the same asymmetry one exit
over, and no test covers it (`_raise` in the new test raises for both markers).
Also `Decision(env_enabled, "env", rejected)` returns before any marker is read,
which is correct and worth a word in the comment.

### MEH #m-4: `raising=False` on an attribute that exists removes #b-3's only non-vacuity guard {#m-4}

**File:** `tests/test_derive_stamp.py:276`

`monkeypatch.setattr(store_mod, "_DERIVE_SRC_DIR", d, raising=False)` — the
attribute is defined at `store.py:662`, so `raising=False` only suppresses the
error that would fire if it were renamed. That matters here more than usual:
the copies are byte-identical to the originals, so `derive_code_hash()` returns
the SAME digest whether or not the seam fired, and `before == after` would hold
vacuously. Drop `raising=False`.

## Verified, not findings {#verified}

### #b-3 — CLOSED, and the seam proven live rather than assumed {#v-b3}

Three independent probes, none of them the author's:

1. `stat` around the single test: `store.py` mtime `1791323292` before and
   after, `1 passed in 0.11s`.
2. Across the full suite: nothing in `src/**.py` newer than the run start.
3. The seam is the one being read, and the fixture has power —
   `_DERIVE_SRC_DIR` pointed at an EMPTY dir makes `derive_code_hash()` return
   `""`; writing the copy's bytes back moves its mtime
   (`1789578591682540913 → 1791326327328821165`) while the content hash holds
   `p1:d1d34b0fe531be484`; an mtime-keyed implementation over the same copies
   differs. So the test would fail if the hash went back to mtime.

All three modules in `_DERIVE_CODE_MODULES` (`ingest.py`, `ingest_gmd.py`,
`store.py`) are copied, so `read_any` stays true and the hash is not silently
narrowed. The rewrite moved to `ingest.py`, which is in the union the no-arg
call hashes — the test keeps its whole meaning.

### #b-1's count — CLOSED, on 13 filter arms, not the one the test exercises {#v-b1}

The dispatch's question 1 answered by construction AND by measurement:
`pending_embeddings` and `pending_embeddings_count` share
`_pending_embeddings_where(kinds)` verbatim, and the list adds only `ORDER BY` +
`LIMIT`. Probed on a throwaway sqlite store (12 rows, 9 memory / 3 code):

```
OK all-NULL kinds=None 12/12 | kinds=['memory'] 9/9 | ['code'] 3/3 | both 12/12 | ['nonesuch'] 0/0
OK 4 fresh+matching partition  5/5  | kinds=None 8/8
OK vectors_partition MISMATCH  7/7  | kinds=None 10/10
OK legacy NULL partition trusted 5/5
OK STALE (updated_at > vectors_updated_at) 6/6 | kinds=None 9/9
OK kinds=[] (falsy -> no filter) 9/9
ALL ARMS AGREE: True
```

`daemon.py:5473` is the only consumer, and no `len(pending_embeddings(limit=…))`
read survives anywhere (`rmx grep -rn pending_embeddings src tests`).

### #b-2's named-FILES order — genuinely fixed {#v-b2}

`-c alpha f2.txt f0.txt f1.txt` returns argv order on the dev build and
alphabetical-ish fan-out order on the deployed one; `-n` over named files matches
the real-grep control; `-l alpha alias.txt f1.txt` matches grep. The e2e gate's
power claim is credible on its own terms (six files, reverse-alphabetical
fixture, `shell=False`, banner-absent control, 3-exec canary) — its defect is
scope, not power. The two SKETCHY entries it reports about its own history (the
dead `subprocess` fake deleted the day it was written; the 2-file coin flip) are
accurate and the deletion was the right call.

### #b-4, #s-1, #s-2, #s-5, #m-1, #m-3 — closed as claimed {#v-rest}

- **#b-4**: `box.innerHTML = skipNote + Object.entries(groups)…` — the partial
  branch now carries the note.
- **#s-1**: the chain is complete — `daemon.py:3814` writes `derive_error`,
  `hub.py:682-683` copies it onto the row, `cli.py:2801` turns it into a
  `derive-UNKNOWN` flag. Not hot, which is the right call for a probe timeout.
- **#s-2**: `retries=0` is on the write (`derive_stamp`, `cli.py:10125`). Nit:
  the comment says the other three "are reads and already pass it" — one
  (`cli.py:3480`) passes `retries=1`, which is fine for a read but is not what
  the comment says.
- **#s-5**: plan-15 `in-progress` in the plan and in `plan-of-plans.md`, with
  the reason recorded in the row.
- **#m-1**: `grep_evidence_breadth.py`'s own run block now names itself; the
  file exists.
- **#m-3**: `marker_error` is on the dataclass, both OSError arms append to
  `problems`, `rmx learn` prints it, and the quiet case has its own test. (See
  [[#m-3]] for the one exit it misses.)

### Deferral sweep (rules 9 / 9a) {#deferrals}

ADDED lines only, across `src/`, `tests/`, `eval/`: one hit
(`cli.py` "indistinguishable from a clean one"), which describes the defect
being fixed. No new hard or soft deferral in code. The only new deferral in the
range is the registry row at [[#s-4]].

### No fleet side effect from the new subprocess tests {#fleet}

`test_grep_argv_order_e2e.py` execs `.venv-eval/bin/rmx` four times per run.
Checked: no daemon is spawned for the tmp root, and `rmx hub status` still shows
the same 8 registered stores, none under `/tmp`. The tmp root accumulates
`cli.log` / `query.log` / `learn.queue.jsonl` and is discarded. Safe.

### The three discarded suite runs {#discarded-runs}

Accepted as stated — the third was contaminated by the author's own `#b-2`
mutation loop (byte-identical restore, moved mtime, cleared `__pycache__`), and
only the `ae39044` run is cited. This is
[[feedback_commit_before_mutation_revert]] and
[[feedback_clear_pycache_after_mutation]] working as intended, and the honest
retraction in `handoff.md` for the PRE-remedy log is the right shape.

## Verdict {#verdict}

**DIRTY — 11 findings (4 BULLSHIT, 4 SKETCHY, 3 MEH).**

Of r1's 13: **#b-3 and #b-1 are closed and verified independently**, #b-4 is
closed, #b-2's named-file half is closed, and six of the eight SKETCHY/MEH items
hold. But the `-c`/order work introduced **three new defects in the drop-in path,
two of them strictly worse than the pre-remedy build** — a walk is interleaved by
line number, and a symlink alias collapses two `-c` rows into one summed row —
and #b-5's enumerated list was closed 3-of-5 without saying so.

**Blockers for closing plan-15 / merging `bsd-r1-remedy`:** [[#b-1]], [[#b-2]],
[[#b-3]], [[#b-4]]. None is deployed, so the fleet is unaffected; all three grep
findings are in one function and share one root error — treating `Path.resolve()`
as an argv path's identity, and treating "argv is non-empty" as "every output
file was named".

**I disagree with one of the two deliberate non-fixes.** #m-2 is correctly
recorded (see [[#s-4]] for the one thing it lacks). #s-3's number should indeed
stay, and the claim the author identified as the actual defect is still in the
tree ([[#s-3]]).

Round 3 is owed.

rel: contradicts -> [[claude#no-workarounds]]
rel: contradicts -> [[claude#no-mocks]]
rel: amends -> [[bsd-plan14-15-grep-family-1452875]]
