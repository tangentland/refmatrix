---
gmd: "0.1"
id: bsd-r1-remedy-r7-bd59e9a
title: "r6 remedy + bug-085: every r6 code finding is closed with power (22 of 23 mutations killed); a missing model is loud on one leg only, and the Lance batch helper still swallows everything"
severity: SKETCHY
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r6
round: 7
prior: 2026-10-07-0924-r6-merge-unpinned-and-the-eval-model-still-calls-out-92c374c.md
tags: [bsd, audit, remediation, grep, models, offline, lance, wedge, mutation]
---

# ch-bsd round 7: fa3d7ad..bd59e9a {#root}

rel: amends -> [[bsd-r1-remedy-r6-92c374c]]
rel: evidence-for -> [[impl-remedy-bsd-r6-92c374c]]

**Range:** fa3d7ad..bd59e9a. The commits are 12fcc79 (r6 #b-1/#m-2), 3b1b544 (bug-085), f39ec41 (models
#b-2/#s-2/#m-3), 794857b (#s-1), d119c85 (docs and bug rows), 1fc2f12 and bd59e9a (the draft of task
16.6). I read the shas from `git log`. While this audit ran, four more commits landed on the shared
branch (d8c2160..fbb7134: plan-17/18 drafts, bug-089, a launchctl PATH fix). They are outside the
range and were not audited. Only plan-17 is cited below, as context for [[#m-1]].
**Date:** 2026-10-07T10:50-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 18 (src 5, eval 4, tests 5, workflow 4)

## Method {#method}

- **No full suite**, per bug-085/bug-088. I ran the 5 changed test files in the tree: 38 passed
  (`workflow/review-output/r7-targeted.log`). `git status` was clean afterwards, so the conftest
  recorder logged no live-socket touch.
- **Mutations** ran in a `git archive HEAD` copy at `/tmp/r7m`:
  - its own `Store.init()`ed `.refmatrix/`;
  - `PYTHONPATH` prepended with `/tmp/r7m/src`, and `refmatrix.__file__` checked to resolve inside the
    copy before every run (`IMPORT /tmp/r7m/src/...` on all 23 runs);
  - `__pycache__` cleared before each run;
  - each file restored from its saved bytes, asserted byte-identical, and `git diff --quiet` checked
    in the copy;
  - baseline 38 passed. Every mutant collected 38.
- **Model probes** ran under a socket guard that records and refuses every non-AF_UNIX
  `connect`/`create_connection`. `huggingface_hub`, `transformers` and `sentence_transformers` were
  imported BEFORE the code under test.
  - In `.venv-eval` (st 5.5.0 / tf 5.8.1 / hub 1.14.0): all 9 cached models.
  - In the deploy venv `~/refmatrix/.venv` (st 5.5.1 / tf 5.9.0 / hub 1.16.4, dev src prepended):
    the two production models.
  - Partial-cache probes used copied snapshots under the scratchpad.
- **Lance cost** was measured on an APFS clone (`cp -c`) of the live `code.lance`, taken read-only. I
  measured it twice: at 61,395 versions, and again after the live store was compacted by hand during
  this audit (3 versions). Nothing opened the live `.refmatrix/` catalog, and no `rmx` write command
  ran.

### Mutation table {#mutations}

23 mutations, 22 killed, 1 survived (O7).

| id | mutation | result |
|---|---|---|
| A1 | drop the post-resolution dedup (r6's survivor) | killed (`len(rows) == 1`) |
| A4 | `merged` never incremented | killed (`stats["merged"] == 1`) |
| G1 | no sort on the resolved path | killed |
| G2 | no resolution before the sort | killed |
| K1 | `purge_path` purges WITH a per-entity Lance delete | killed (version count) |
| K2 | `purge_path` without the batch delete | killed (vectors left) |
| K3 | `fold_concept_dups` without the batch delete | killed |
| K4 | `prune_noise(drop)` without the batch delete | killed |
| K5 | `prune_noise` per-entity Lance delete | killed |
| K6 | the batch delete raises (swallowed) | killed (3 tests) |
| O1 | `missing_files` bypassed | killed (4) |
| O2 | `enforce_offline` does not flip the imported constant | killed (2) |
| O3 | `trust_remote_code` passthrough dropped | killed (CodeRankEmbed test) |
| O4 | `except OSError` only | killed |
| O5 | the operator's `HF_HUB_OFFLINE=0` is overwritten | killed |
| O6 | no Pooling-config check | killed |
| **O7** | `tokenizer_config.json` no longer required | **SURVIVES** → [[#m-4]] |
| O8 | `snapshot_download` without `local_files_only` | killed |
| O9 | load without `local_files_only` (r6 D1) | killed |
| W1 | `_op_context` appends no warning | killed |
| W2 | the verb drops `warnings` | killed |
| W3 | the CLI does not print `warnings` | killed |
| E1 | the eval retriever loads `SentenceTransformer` directly again | killed |

## r6 findings: closed vs open {#r6-status}

| r6 | status | evidence |
|---|---|---|
| #b-1 merge pinned by a set | **CLOSED with power** | A1 and A4 killed |
| #b-2 CodeRankEmbed calls out | **CLOSED with power** | The guarded construction makes **0 connects** with the hub imported first, and the hub constant ends `True`. E1, O2 and O3 killed. With an explicit `HF_HUB_OFFLINE=0` the remote code makes 1 connect to `huggingface.co:443`. That is the documented operator opt-out, so it is explicit and not a finding (`r7-crev-probe.log`) |
| #s-1 delegate teaches by flag spelling | **CLOSED** | The teach branch is deleted. Eight flag shapes are pinned to an empty queue |
| #s-2 partial cache / context log line | **CLOSED** | All 9 cached models: 8 pass `missing_files` and load with 0 connects. jina-reranker-v1-tiny-en is refused, correctly: its snapshot holds only `config.json` + weights. Partial-cache probes on bge-small: tokenizer.json alone, vocab.txt alone, no `sentence_bert_config.json`, no `config_sentence_transformers.json` → cosine 1.0000. `1_Pooling/` or its config missing → ModelNotCached. W1-W3 killed. The **siblings** stay quiet → [[#s-1]] |
| #s-3 global base | **CLOSED** | bug-086 row, with the user's decision and its order (after deploy) |
| #s-4 external-calls list | **PARTIAL** → [[#m-2]] | A table exists. One implicit call is missing from it, and its line numbers are off by one |
| #s-5 recorder | **CLOSED** | bug-088 row, refuse stage planned, deferral recorded as the user's |
| #m-1 docstring | **CLOSED** | "of the rows READ before `stop_after`" |
| #m-2 resolved-path order | **CLOSED with power** | G1 and G2 killed |
| #m-3 offline test leak | **PARTIAL** → [[#m-3]] | The env vars are restored, and D1/D2/D5 are pinned (O9, O2, `isinstance(..., CrossEncoder)`). The hub CONSTANT still leaks (proven) |
| #m-4 `--fetch` loop | **CLOSED** | The flag is gone. `fetch()` prints the `hf download` line. REPORT and ingest no longer point at the flag |
| #m-5 summaries / bug row | **CLOSED** | `remedy-bsd-r6-92c374c.md`, bug-087 |

Closed: 10. Partial: 2 (#s-4, #m-3). Open: 0.

## bug-085 audit {#bug-085}

- **Every per-ENTITY Lance loop on a lock-holding path is covered.** `purge_path`,
  `fold_concept_dups` and `prune_noise(drop)` are batched, and K1-K5 are each killed.
  `bulk_forget_memories`, `forget_entities` and `vacuum` were already batched (`_bulk_purge_ids`).
- **The remaining per-entity callers are not wedge risks.** `forget_memory` deletes a single entity.
  `_apply_event_body` (`tombstone` → `purge_entity`) is reached only from `apply_log_delta`, and
  `apply_log_delta` has no caller in `src/`: daemon.py names it only in a comment.
- **Dry-run fold** collects no ids, so it issues no Lance write.
- **Measured on the 61,395-version clone:**
  - a per-id delete costs 1.09 s, so 221 entities ≈ 242 s, which reproduces the wedge;
  - a batched delete of 221 ids costs 0.99 s, and of 5,000 ids 1.58 s, one version each;
  - **a delete that matches no row costs 1.94 s and still commits a version.**
- **A 20-file edit flush** (`sync_files` at HEAD, 20 functions per file) took 10.2 s inside one
  `s.transaction()` and added 20 versions. After the live store's compaction, the same flush took
  0.2 s. The per-file residual → [[#m-1]].
- **The swallowed `except` in the batch helper** → [[#s-2]].

## Findings {#findings}

### SKETCHY #s-1: "a missing model is a LOUD failure" holds on one leg; the recall legs and score-time failures stay quiet {#s-1}

**File:** `src/refmatrix/reranker.py:557-558`, `src/refmatrix/daemon.py:5566-5599`,
`src/refmatrix/context.py:788-793`
**What:** f39ec41 puts a rerank failure on the `context` op's answer. The module docstring of
`models_local` now says that a model "not cached, or cached incomplete, is a LOUD failure that names
the one-time fetch command".
**Why it's sketchy:** There is one loud leg, the `context` op's `d._reranker()` construction. It is
reached through MCP `rmx_context`. The CLI's `rmx context` takes the replica branch whenever a replica
file exists, and that branch never reranks, so the new stderr line in cli.py is reachable only on a
store with no replica. The siblings:
- `shared_reranker` ends in `except Exception: return None`. On the default replica-first recall,
  a worker that raises ModelNotCached on its `info` probe prints "rerank skipped: **shared worker
  unavailable**; hits unreranked". The fetch command is lost and the wrong cause is named.
  `scan-prompt` uses the same helper.
- The daemon-RPC `memory_recall` and `ann_search` legs go through `_apply_rerank_safe`, which only
  calls `d._log`.
- Score-time failures inside `build_context` are `print`ed to the DAEMON's stderr
  (`daemon.stderr.log`), not added to the answer's `warnings`. These include a worker respawned after
  the cache was removed, the NaN guard's RuntimeError, and RerankSkipped.

**Evidence:** I read the code. My stub-daemon probe of the score-time leg never reached `score`
(`r7-ctx-score-failure.log`: no content hits), so that leg is not demonstrated by execution.
**Fix:**
- Let `shared_reranker` return the exception class with the None (or re-raise ModelNotCached) and
  print its message.
- Have `_apply_rerank_safe` return a warning that the two ops attach.
- Have `build_context` record a rerank failure on the bundle (`bundle.warnings`), and have
  `_op_context` merge it.

**Pattern match:** YES, the sibling-path miss again (r6 #s-2 named the context op, and the fix stopped
there). It is not escalated: the default recall does say "unreranked". It names the wrong cause; it
is not silent.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-2: the batch Lance helper swallows every failure, and since 3b1b544 it is the only vector delete on re-sync, fold, prune and bulk memory forget {#s-2}

**File:** `src/refmatrix/store.py:3604-3634` (and the second `try/except: pass` around it in
`_bulk_purge_ids`, store.py:6019-6022)
**What:** `except ImportError: return 0`, then `except Exception: pass` per kind. Nothing is counted,
logged or returned that distinguishes a failure from "no dataset".
**Why it's sketchy:** bug-085 moved the hottest write path onto this helper:
- `purge_path`, on every watch flush;
- concept fold and noise prune.

`bulk_forget_memories` is a memory path, and the project rule on memory paths is CRITICAL. A failed
delete leaves vectors for purged ids. The only recovery is a manual `embed --gc`, and nobody is told
to run it. The ImportError arm cannot tell "lance not installed" from a broken install. Under
`python -I` in `.venv-eval`, `import lance` raises `ModuleNotFoundError: typing_inspection` (from
pydantic, via lance_namespace). The helper would read that as "no lance" and skip every delete
silently (`r7-lance-cost` first attempt).

This is consistent with, but not proven to cause, plan-17's count of 559 of 5,495 `code.lance`
vectors with no catalog row.
**Fix:**
- Return `(attempted, failed)`.
- Log each failure with the kind and the exception.
- Count failures in the `sync_files` / prune / fold / forget results.
- Use `importlib.util.find_spec("lance") is None` for "not installed", and let any other import error
  surface.

**Pattern match:** YES, no-silent-failures (bug-082 class). This is pre-existing code, but this diff
widened its blast radius.

rel: contradicts -> [[claude#no-silent-failures]]

### MEH #m-1: the per-file loop still commits one Lance version per file per kind, even when no id matches {#m-1}

`_sync_paths` calls `purge_path` once per changed file, and each call commits a version. On the
61,395-version clone, a 20-file flush held the transaction for 10.2 s. That projects to about a
minute for the 111 files that differ between master and this branch. After compaction it took 0.2 s,
so the cost lives in the version count. Each flush adds versions again, including no-match deletes,
and no compaction exists in `src/`. Plan-17 (landed after this range, `drafting`, no task specs yet)
is where that belongs.
**Fix:** collect `ids_by_kind` across the flush and issue one delete per kind. Filter to ids the
catalog says carry a vector, so a no-match delete does not commit. Give 17.1 a task spec.

### MEH #m-2: the r6 #s-4 table misses one implicit call and cites lines off by one {#m-2}

The table cites `eval/memaware/run.sh:37-38`. The installs are at lines 38-39, and line 39 is a
SECOND implicit call, `npm install @anthropic-ai/sdk`. It runs whenever that package directory is
absent, even when `node_modules` exists, and it installs an unpinned package into the upstream
checkout. The table's one "implicit" row covers only line 38. The judge is at `score.py:66` (65 is
the import). The memaware LLM row does not name the Fireworks provider (`lib/llm.mjs:36`).
**Fix:** add the row, correct the lines, and give "waits on the user" a place to land (a bug row).

### MEH #m-3: the offline fixture still leaks `huggingface_hub.constants.HF_HUB_OFFLINE = True` into the rest of the session {#m-3}

A follow-on test asserted the constant is False after `tests/test_models_offline.py`. It FAILED with
`True` (`r7-env-leak.log`). `monkeypatch.setattr(constants, ...)` restores the value seen at fixture
setup. When `huggingface_hub` is first imported INSIDE a test, while the fixture's env var is set,
the constant is born True and nothing restores it. Later tests then run with the hub offline, so a
would-be connect elsewhere cannot be observed: the guard masks it.
**Fix:** in the fixture's teardown, set the constant to the value `os.environ` implies after the env
restore, or import `huggingface_hub` before `setattr`.

### MEH #m-4: unpinned edges {#m-4}

- O7 survives. No test drops only `tokenizer_config.json`, so the clause that requires it is
  unpinned.
- `rmx grep --learn` on a delegate-routed call now teaches nothing and says nothing. The filter
  branch prints "--learn ignored for this call" (cli.py:6216); the delegate branch does not.

**Fix:** add one parametrized case, and print the same note in the delegate branch when `--learn`
was given explicitly (`get_parameter_source`).

### MEH #m-5: task 16.6 draft, notes for the spec review {#m-5}

- **AC-5's population does not match R5's.** R5 leaves EVERY global relative row's root NULL,
  which is 1,087 entities / 5,159 evidence rows, all classified `orphan-root`. AC-5 compares that
  count to bug-086's ~700 `unreadable` rows. That is a different population, and entities vs rows
  is a different unit.
- **AC-2 conflicts with d-b.** AC-2 says the dry run is byte-identical. d-b has the verifier queue
  read-time marks. If audit and prune reuse that verifier, the next drain changes the catalog after a
  "dry" run.
- **d-c prunes `moved` rows by default.** `moved` rows are the one class that can be re-pointed
  instead of deleted.

## Deferral sweep (rules 9 / 9a) {#deferrals}

On the added lines in src/, tests/ and eval/ there is one hit: "plan-16 task 16.5 deletes this
branch". It is anchored, because the task spec exists, so it is MEH-active and not counted.

On the code touched by the diff:
- `_drop_lance_for_purge`'s "worst case stays orphan, GC reaps later" names a real mechanism
  (`gc_vectors`, store.py:3546) but no trigger → [[#s-2]].
- bug-085's "compaction … user decision" is now the subject of plan-17, which landed after this
  range → [[#m-1]].
- bug-086 and bug-088 carry the user's recorded decisions. They are anchored.

## Verdict {#verdict}

DIRTY: 7 findings (0 BULLSHIT, 2 SKETCHY, 5 MEH). **No blockers.** Every r6 code finding is closed
with power, and 22 of 23 mutations are killed. bug-085's per-entity loops are all batched, and the
residual cost is the version count (plan-17).

**Deploy state moved during the audit.** `~/refmatrix` is now at d0273a5 (0.76.2), with
`fbcc8b3` (0.76.1, "bug-085 hotfix"). That commit's store.py hunks are line-for-line identical to
3b1b544's, so the bug-085 code and test audited here ARE deployed, and [[#s-2]] and [[#m-1]] apply to
the live daemon. The models, grep and context changes (f39ec41, 12fcc79, 794857b) are NOT deployed.
The shared tree was not modified outside `workflow/bullshit/` and `workflow/review-output/r7-*`.

rel: contradicts -> [[claude#no-silent-failures]]
