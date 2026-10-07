---
gmd: "0.1"
id: bsd-r1-remedy-r6-92c374c
title: "r5 remedy + offline models + live-socket recorder: the printed path and the unreadable note are closed with power; the merge is pinned by a set-cardinality assert, and the CodeRankEmbed retriever still connects to huggingface.co"
severity: BULLSHIT
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r5
round: 6
prior: 2026-10-07-0151-r5-resolved-for-reading-printed-unresolved-c8278b1.md
tags: [bsd, audit, remediation, grep, models, offline, conftest, mutation]
---

# ch-bsd round 6: c8278b1..92c374c {#root}

rel: amends -> [[bsd-r1-remedy-r5-c8278b1]]
rel: evidence-for -> [[impl-remedy-bsd-r5-c8278b1]]

**Range:** c8278b1..92c374c (99387f8 r5 remedy, 43e0fa5 models local-only, 33809ab plan-16 docs
(skipped, the concurrent spec review covers it), 92c374c conftest live-socket recorder)
**Date:** 2026-10-07T09:24-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 28 (src 5, eval 2, tests 7, workflow 14)

## Method {#method}

- Full suite NOT re-run, by instruction (bug-085). I used the recorded run
  `workflow/review-output/r5-remedy-full2.log`: 2527 passed, 1 failed (`test_installed_hooks_match_generated`,
  the expected rewriter drift).
- Targeted run in the tree: 6 changed test files, 67 passed (`workflow/review-output/r6-targeted.log`).
- Mutations ran in an isolated `git archive` copy with its own `Store.init()`ed `.refmatrix/`,
  `PYTHONPATH` pointing at the copy (`refmatrix.__file__` printed and checked), `__pycache__` cleared
  before each run, and each mutation restored with `git checkout` and asserted byte-identical.
  Baseline in the copy: 66 passed, 1 skipped (`dev venv rmx not built`, which does not exist in a copy).
- Index reads ran on a COPY of `.refmatrix/catalog.read.duckdb`, with rows verified against the real
  project root as `base`. The live store was not opened.
- Model probes ran with a socket guard that records and refuses every non-AF_UNIX connect. Partial-cache
  probes used a scratch `HF_HOME` copied from `~/.cache/huggingface/hub`.

18 mutations: 12 killed, 6 survived (A1, A4, B2, D1, D2, D5).

| id | mutation | result |
|---|---|---|
| A1 | drop the post-resolution dedup | **SURVIVES** (67 passed) → [[#b-1]] |
| A2 | dedup key `(path, line)` only | killed (`test_a_capped_read_never_duplicates_or_loses_a_tied_row`) |
| A3 | print the unresolved path | killed (`test_a_relative_row_verifies_regardless_of_the_cwd`) |
| A4 | `merged` never incremented | SURVIVES. No caller reads `stats["merged"]` |
| B1 | `_shaped` ignored | killed (`[-c]`) |
| B2 | long-form spellings removed from the guard | **SURVIVES** → [[#s-1]] |
| B3 | short set `"ch"` only | killed (`[-o]`) |
| C1 | malformed lines not counted | killed |
| C2 | 24 h window replaced by `if True:` | killed (r5's C1 is closed) |
| D1 | `load_local` without `local_files_only=True` | **SURVIVES** → [[#m-3]] |
| D2 | `load_local` without the `HF_HUB_OFFLINE` setdefault | **SURVIVES** → [[#m-3]] |
| D3b | both removed | killed (embedder test records a connect) |
| D4 | `except ValueError` in place of `except OSError` | killed |
| D5 | rerank loads through the `SentenceTransformer` class | SURVIVES → [[#m-3]] |
| E1 | no `\b` wrap on bridged variants under `-w` | killed |
| E2 | `unreadable` never incremented | killed |
| E3 | CLI unreadable note off | killed (RPC-path test) |
| E4 | daemon op returns `unreadable: 0` | killed |

## r5 findings: closed vs open {#r5-status}

| r5 | status | evidence |
|---|---|---|
| #b-1 printed path | **CLOSED, path half.** **OPEN, merge half** → [[#b-1]] | A3 killed. On the catalog copy, every printed path exists: `error` 1237/1237, `daemon` 404/404, `bitmap` 6/6. A1 survives |
| #b-2 unreadable note / `-w` variant | **CLOSED with power** | E1-E4 all killed, on the op field, the RPC note, the in-process note and the variant `\b` |
| #s-1 global-store base | **OPEN, no task** → [[#s-3]] | The summary hands it "to the user". No bug row or task spec exists |
| #s-2 delegate teaches non-line output | **PARTIAL** → [[#s-1]] | `-c -h -l -o` are pinned (B1, B3). The guard keys on flag spellings, and the shape it claims is not checked |
| #s-3 `daemon.ping` registry row | **CLOSED** | Row added |
| #m-1 `unreadable` docstring | **OPEN** → [[#m-1]] | `store.py:848` is unchanged. The summary lists #m-1 as handled |
| #m-2 learn status window / malformed | **CLOSED with power** | C1, C2 killed |
| #m-3 16.5 corpus | **CLOSED** | 16.5 now names `-L … nosuch.txt`, `-c zzz nosuch.txt`, `-B 1`, `-C 1` and the dotfile walk |

Closed: 4 (#b-2, #s-3, #m-2, #m-3). Partial: 2 (#b-1, #s-2). Open: 2 (#s-1, #m-1).

## Findings {#findings}

### BULLSHIT #b-1: the merge that r5 #b-1 asked for is asserted through a SET, so dropping it passes every test {#b-1}

**File:** `tests/test_grep_verify_before_cap.py:190-210`, `src/refmatrix/store.py:902-908`
**What:** `verify_evidence_rows` now de-duplicates on `(path, line, linkage, concept)` after resolution,
and counts the collapses in `stats["merged"]`. The summary says the test "was RED" and proves the merge.
**Why it's bullshit:** The test's merge assertion is `len({(r["path"], r["line"]) for r in rows}) == 1`.
That is the size of a set, so it equals 1 whether one row comes back or two. The test was RED only
because of the path half: before the fix, `src/a.py` was printed.
**Evidence:** With mutation A1 (dedup removed), all 67 tests in the six grep files pass. The same fixture
run directly gives `1 {'merged': 1}` at HEAD and `2 {'merged': 0}` under A1. That means two identical
printed rows, and `-c` counts one matching line as 2. A4 also survives: no caller reads `merged`.
**Fix:** Replace the assertion with `assert len(rows) == 1` and `stats["merged"] == 1`. This is a one-line
change.
**Pattern match:** YES. "Correct by execution, pinned by nothing" is the 4th sighting in this lineage
(r4 #s-1, r5 #b-2 three legs, now r6), so it escalates to BULLSHIT. It is also the r5 impression
"assert on what the user receives".

rel: contradicts -> [[claude#system-dependent-tests]]

### BULLSHIT #b-2: the CodeRankEmbed retriever, which 43e0fa5 calls "local-only too", still connects to huggingface.co {#b-2}

**File:** `eval/retrievers/coderankembed_retriever.py:35-41`
**What:** `os.environ.setdefault("HF_HUB_OFFLINE", "1")`, then
`SentenceTransformer(..., trust_remote_code=True, local_files_only=True)`.
**Why it's bullshit:** `sentence_transformers` is imported at the top of `__init__`, a few lines BEFORE the
setdefault, so `huggingface_hub` has already read `HF_HUB_OFFLINE` into its constants and the env var does
nothing. `local_files_only` does not reach the model's remote code either. CodeRankEmbed's
`modeling_hf_nomic_bert.py:63 state_dict_from_pretrained` calls `transformers.utils.hub.cached_file` →
`hf_hub_download` → `get_hf_file_metadata` → httpx.
**Evidence:** I constructed `CodeRankEmbedRetriever(device="cpu")` under the socket guard in `.venv-eval`.
It LOADED, after 4 refused connects to `13.249.74.{25,3,27,12}:443`. The stack trace is above. Without
the guard those connects go out. No test covers this file.
**Fix:** Set both env vars before ANY `sentence_transformers` or `transformers` import in the module.
Then re-run the guarded construction and assert zero attempts, and add that as a test (skipif the model
is not cached). Better still, make the retriever load through `models_local.load_local` with a
`trust_remote_code` passthrough, so the offline rule has one implementation.
**Pattern match:** YES. This is a sibling-path miss (the 13th): the rule was fixed in `load_local` and
copied by hand into the eval retriever in a weaker order.

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-1: the delegate's shape guard checks flag spellings, not the output's shape; a default `--include` grep still teaches wrong lines, and `-m 5` teaches the concept `query/5` {#s-1}

**File:** `src/refmatrix/cli.py:6321-6372`
**What:** `_shaped` skips teaching when a `-c -h -l -L -o -q -Z` letter, or one of 8 long forms, appears in
argv. The comment says "Only `file:line:text` output can teach".
**Why it's sketchy:** Several common invocations still produce output that is not `file:line:text`. I ran
the real `_grep_delegate` with the broker captured, on the real rg 15.1.0 and BSD grep:
- `rmx grep alpha --include=*.yml -r .`: no `-n`, and rg prints no line numbers off a tty.
  `./f.yml:  7: alpha seven` was **taught as `f.yml:7`** (the file has 3 lines; the match is on line 2).
  `--include` is the most common delegate reason.
- `rmx grep -n --include=*.txt alpha log.txt` names one file, so grep implies `-h`. The output
  `2:12:30 alpha in log` was taught as the **file `<cwd>/2`, line 12**.
- `rmx grep -n -m 5 alpha log.txt`: the pattern is "the first token not starting with `-`", which is
  `5`. This taught **`query/5`**, and `_learn_grep_hits` marks both the concept and the entity
  `protected`, so `prune_noise` never removes them.
- `--count-matches` (rg) and `--cou` (accepted by the grep fallback after rg exits 2) taught counts as
  line numbers.
- `_learn_grep_hits` checks neither that the file exists nor that the line is in range.
- B2 survives: none of the long forms is pinned.

**Fix:** Do not enumerate flags. Before teaching, verify each parsed hit the way the read side already
does: the file exists and `lines[n-1]` matches the pattern (`evidence_line_matches`). Take the pattern
from `_split_grep_argv`, not from the first non-dash token. 16.5 deletes this branch, but until it lands
this branch writes protected rows.
**Pattern match:** YES. This is r5 #s-2 a second time, and its own docstring promises the shape.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-2: "an uncached model is a LOUD failure" does not hold for a partial cache, and `rmx context` turns ModelNotCached into a log line {#s-2}

**File:** `src/refmatrix/models_local.py`, `src/refmatrix/daemon.py:4624-4628`
**What:** `load_local` maps `OSError` to `ModelNotCached`. Its docstring says "a model that is not cached
is a LOUD failure".
**Why it's sketchy:** Before this commit, a missing file was fetched. Now it is silently substituted.
Probed with a scratch HF_HOME holding a copy of the real cache, in `.venv-eval` (st 5.5.0):
- bge-small without `tokenizer.json`, `vocab.txt`, `tokenizer_config.json`: it **loads and encodes, with
  cosine 0.553** to the full model, and prints no warning.
- bge-small without `modules.json`: it loads as Transformer+Pooling (mean pooling, no Normalize), **cosine
  0.952**, silently. Vectors from it would land in the same Lance index.
- Without `1_Pooling/`: it raises `TypeError` (Pooling missing `embedding_dimension`), not ModelNotCached.
- Weights or `config.json` missing: ModelNotCached is raised correctly, for both kinds.
- Both venvs load both classes with zero connect attempts, even with `huggingface_hub` imported first.
  st 5.5.0 / transformers 5.8.1 / hub 1.14.0, and st 5.5.1 / 5.9.0 / 1.16.4. That part is correct.

On the context op, `d._reranker()` failures are caught as `except Exception` and written only to
`rmxd.log`, and the answer is served unreranked. ModelNotCached is a new cause on that silent path.
**Fix:** Before loading, check that the files the model needs are present: `modules.json` plus the
tokenizer files for an embed model, and the tokenizer for a rerank model. Raise ModelNotCached when any
is missing. Map `TypeError`/`ValueError` from a load to ModelNotCached as well. Show ModelNotCached on
the context answer (a stderr note or an `ok:false` leg), not only in the log.
**Pattern match:** YES. The same "loud" claim is broken on a sibling path.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-3: r5 #s-1 (`base = root.parent` wrong for the global store) is open, with no bug row and no task {#s-3}

**File:** `src/refmatrix/store.py:3242`
**What:** The summary: "Fixing them needs a data decision … taken to the user."
**Why it's sketchy:** Rule 9a. Nothing records this deferral: no `workflow/bug_registry.md` row and no
task spec. 700 of the global store's 1,087 relative rows are still counted `unreadable` on every global
grep.
**Fix:** File a bug row now, naming the two options (forget them, or re-resolve them), so the user's
decision has a place to land.
**Pattern match:** YES (second round).

### SKETCHY #s-4: "remove ALL external calls" was narrowed to src/ and models, and the remaining eval/ calls are not listed anywhere {#s-4}

**What:** The 43e0fa5 message says "That was the only implicit outbound call in src/". That statement is
true: I swept src/, bin/rmxgrep, bin/rmxrg, `.claude/hooks` and `src/refmatrix/templates`. The only
remaining network path is `rmx upgrade`'s git fetch + pip, which is explicitly allowed. But the user asked
for ALL external calls, and these eval/ calls remain with no list handed back:
- `eval/memaware/run.sh:37-38` runs an implicit `npm install` (npm registry) whenever `node_modules` is
  absent. It is implicit in the same sense the HF revision check was.
- `eval/fetch_datasets.sh:39-60` runs `curl` against huggingface.co.
- `eval/memaware/prepare.py:50` runs `git clone` from github, behind `--clone`.
- `eval/memory_recall/score.py:65` uses the `anthropic.Anthropic()` judge, and the memaware conditions
  call LLM APIs.

Some of these are inherent to a benchmark, which is the user's call. The silent omission is not.
**Fix:** Add one table to a summary or bug row: each remaining call, implicit or deliberate, and a
proposed disposition. Then ask.
**Pattern match:** YES (rule 10, scope shrunk silently).

### SKETCHY #s-5: the live-socket recorder defers "refusing" with nothing behind it, and it cannot see the processes that wedged the daemon {#s-5}

**File:** `tests/conftest.py:83-123`
**What:** In record mode, the recorder logs connects to 4 hard-coded unix paths and `127.0.0.1`/`localhost`
port 7777. Its comment says "refusing comes after the list is known".
**Why it's sketchy:** (a) The list IS known now: 72 touches, 66 to `models.sock` and 6 to the global
`rmxd.sock`. No bug row or task covers the refuse step; bug-085's "Not fixed" names an op-start log
line, not this. That makes it an unanchored deferral under rule 9a. I filed it SKETCHY because it is
test infrastructure, the same call r2 made for #m-2. (b) The commit itself says the 10 wedge clients
"came from spawned subprocesses or another agent". A `pytest_configure` patch does not run in spawned
`rmx` subprocesses, so the recorder is blind to the suspected vector. (c) The hub registry lists a third
live store, `~/github/atollogy/bdep/viascope/.refmatrix/rmxd.sock`, which is not in `_LIVE_UNIX`.
IPv6 loopback `('::1', 7777, 0, 0)` is not in `_LIVE_TCP`. I did not run the federated tests to show a
missed touch, because they read live sockets.
**Fix:** File a row for the refuse stage. For children, export a sitecustomize via `PYTHONPATH` (or an env
var the CLI honours) so spawned interpreters record too. Build the unix set from `registry.json` roots,
and match `::1`.
**Pattern match:** NO.

### MEH #m-1: r5 #m-1 is listed as handled and the docstring is unchanged {#m-1}

`store.py:848` still reads "`stats["unreadable"]` carries the number". The summary's #m-1 row describes
the existing behaviour and changes nothing. **Fix:** add "of the rows read before `stop_after`".

### MEH #m-2: rows are resolved after the ORDER BY, so a file spelled both ways prints as two runs out of line order, and the cap prefers absolute spellings {#m-2}

On the catalog copy, `error`: `tests/test_plan1_remedy.py` appears at output position 286 (line 332),
then at 653-659 (lines 185, 221, …). `daemon` shows the same file split across 362-363 and 391-393.
`/` sorts before `s`, so `stop_after` takes every absolute-spelled row first. `merged` = 0 on all five
patterns I probed, so the split is real while the merge has nothing to merge today.
**Fix:** a stable sort on the resolved `(path, line, linkage, concept)` before capping, or resolve in SQL.

### MEH #m-3: the offline tests leak `HF_HUB_OFFLINE=1` into the rest of the session, and each offline mechanism alone is unpinned {#m-3}

`monkeypatch.delenv(..., raising=False)` on an absent variable records no undo. `load_local`'s
setdefault then outlives the test. I showed this with a follow-on test asserting the variable is absent:
it FAILED with value `1`. D1 (no `local_files_only`) and D2 (no env) each survive, and only D3b (both
removed) is killed. In production, `local_files_only` is the mechanism that still holds when
`huggingface_hub` was imported first. D5 (rerank built through the wrong class) survives, because the
tests assert only `_model is not None`.
**Fix:** use `monkeypatch.setenv` to a sentinel and then `delenv`, or snapshot and restore `os.environ`.
Add a test that imports `huggingface_hub` first and then asserts zero connects. Assert `isinstance(...,
CrossEncoder)`.

### MEH #m-4: the `--fetch` flag of LongMemEval prepare still says "download", and the two error messages send the user in a loop {#m-4}

`prepare.py:253-254` help reads "download the split from HuggingFace if absent". Without the flag, line
267 says "run with --fetch". With it, `fetch()` says "This script does not download". `ingest.py:87` and
`REPORT.md:139` still point at `--fetch`. **Fix:** delete the flag, or rename it to `--check`, and print
the `hf download` line directly.

### MEH #m-5: 43e0fa5 and 92c374c have no implementation summary and no bug row {#m-5}

CLAUDE.md marks the implementation summary MANDATORY. The outbound-HF finding (a live connection
observed to CloudFront) has no `bug_registry.md` row, and the low threshold applies.

## Deferral sweep (rules 9 / 9a) {#deferrals}

Over the added lines in src/, tests/ and eval/, two hits. "plan-16 task 16.5 deletes this branch" is
anchored: the task spec exists and has acceptance criteria. That makes it MEH-active, so it is not
counted. "refusing comes after the list is known" is unanchored → [[#s-5]]. r5 #s-1's "taken to the
user" is unanchored → [[#s-3]].

## Verdict {#verdict}

DIRTY: 12 findings (2 BULLSHIT, 5 SKETCHY, 5 MEH). Blockers: [[#b-1]] (one-line assert) and [[#b-2]]
(env before import, plus a test). Nothing is deployed: `~/refmatrix` is at 1452875. The shared tree was
not modified outside `workflow/bullshit/` and `workflow/review-output/r6-targeted.log`.

rel: contradicts -> [[claude#no-silent-failures]]
