---
gmd: "0.1"
id: impl-remedy-bsd-r6-92c374c
title: "Remediation of ch-bsd r6 (c8278b1..92c374c), bug-085 named by py-spy, and the summaries 43e0fa5 / 92c374c / d559567 never got"
tags: [implementation-summary, bsd, remediation, grep, models, offline, daemon, lance]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r6-92c374c
  created: 2026-10-07
---

# Remediation of ch-bsd r6 {#root}

rel: implements -> [[bsd-r1-remedy-r6-92c374c]]
rel: amends -> [[impl-remedy-bsd-r5-c8278b1]]

Round 6 was DIRTY with 12 findings (2 BULLSHIT, 5 SKETCHY, 5 MEH). Every code finding was fixed
TDD: the new test was run RED against the unfixed code first, and the log is named below. Where the
audit named a surviving mutation, the same mutation was re-run and now FAILS. The full suite was NOT
run, per bug-088: the touched families were run instead. {#lead}

## Findings {#findings}

| finding | commit | change | proof |
|---|---|---|---|
| #b-1 | `12fcc79` | The merge test asserts `len(rows) == 1` and `stats["merged"] == 1`, not a set size. | Mutation A1 (dedup removed) FAILS it (`r6-b1-mutation-A1.log`). |
| #m-2 | `12fcc79` | `grep_evidence` resolves relative paths and re-sorts on the resolved `(path, line, linkage, concept, entity)` BEFORE the lazy verify + cap. | `test_the_cap_and_the_order_follow_the_resolved_path` RED at HEAD (`r6-m2-red.log`). |
| #b-2 | `f39ec41` | The CodeRankEmbed retriever loads through `models_local.load_local(trust_remote_code=True)`. `enforce_offline()` flips the already-imported `huggingface_hub.constants.HF_HUB_OFFLINE` (an explicit operator `0` is kept). | Guarded construction: 4 connects to 108.138.246.x RED (`r6-models-red.log`), 0 after. |
| #s-2 | `f39ec41` | `missing_files()` refuses a partial cache before loading: config, weights, tokenizer, `modules.json`, Pooling configs. A load `TypeError`/`ValueError` maps to `ModelNotCached`. `_op_context` returns a rerank failure as `warnings`; the CLI prints it to stderr and the verb keeps it on the parsed bundle. | 4 partial-cache cases + 3 context-warning tests RED first. Mutations S2 (no check) and S2b (TypeError unmapped) FAIL. |
| #m-3 | `f39ec41` | The offline fixture uses setenv-then-delenv so it restores a variable it never saw set, and restores the hub constant. It asserts `isinstance(r._model, CrossEncoder)`. Each mechanism is pinned alone: operator opt-out (`HF_HUB_OFFLINE=0`) holds on `local_files_only`, and the hub imported first holds on `enforce_offline`. | Mutations D1 (no `local_files_only`) and D2 (no `enforce_offline`) each FAIL (`r6-models-mut-*.log`). |
| #s-1 | `794857b` | `_grep_delegate` TEACHES NOTHING (user-approved). The branch and its `learn=` parameter are gone; output is unchanged. | Eight invocations (default, `-m 5`, `-c -h -l -o`, `--count`) leave the queue empty. The default and `-m 5` cases were RED on the old code. Grep family 281 passed. |
| #m-1 | this commit | The `unreadable` docstring says "of the rows READ before `stop_after`". | — |
| #m-4 | this commit | LongMemEval `prepare.py` has no `--fetch`. A missing blob prints the `hf download` line. `ingest.py` and REPORT.md no longer point at the flag. | — |
| #s-3 | this commit | bug-086 records the global store's wrong `base` and the user's scheduled repair. | — |
| #s-5 | this commit | bug-088 records the recorder's blind spots and the deferred refuse stage. | — |
| #m-5 | this commit | bug-087 (outbound HF) and this summary (below). | — |
| #s-4 | — | The table below; the dispositions are the user's call. | — |

## bug-085: the wedge, named {#bug-085}

py-spy (`uv tool install py-spy==0.4.2`, run with sudo) and a CPU watcher caught the fourth wedge at
10:14. The busy thread's stack was
`watch flush -> sync_files -> purge_path -> purge_entity -> _drop_lance_for_purge -> lance delete("id = N")`.
That is ONE Lance commit per entity of the re-synced file, under `_store_lock`. 910 of ~990 samples
sat in `lance/dataset.py delete`. {#bug-085-cause}

- `code.lance` carries 60,944 versions and 10,189 deletion files, and has never been compacted.
- store.py has 221 entities, so one edit held the lock for 7+ minutes.
- The hub watchdog SIGTERMed the daemon at 10:17:54 for not answering ping.

`3b1b544` makes `purge_path`, `fold_concept_dups` and `prune_noise(drop=True)` issue one batched
delete per kind. The tests count Lance versions on a real dataset: RED at HEAD with 12, 6 and 4
commits. {#bug-085-fix}

**Still open:** Lance compaction and old-version cleanup on the live store (surgery, user decision),
and an op-start log line. Until deploy, every edit to a large `src/` file can re-wedge the deployed
daemon. {#bug-085-open}

Evidence: `workflow/review-output/pyspy-wedge-1569-20261007-101452.*`, the idle baseline
`pyspy-daemon-1569-idle-baseline.txt`, and `bug085-red*.log` / `bug085-green*.log`.

## The summaries 43e0fa5, 92c374c and d559567 never got (r6 #m-5) {#missing-summaries}

- **43e0fa5 — models load from the local cache only.** `models_local.load_local` passes
  `local_files_only=True` and defaults `HF_HUB_OFFLINE`, and the embedder and reranker load through
  it. `ModelNotCached` names `hf download`. LongMemEval `prepare.py` stopped calling
  `hf_hub_download`. r6 found that the eval retriever's copy was ordered wrong (#b-2) and that a
  partial cache loaded silently (#s-2); both are closed above. bug-087. {#s-43e0fa5}
- **92c374c — the live-socket recorder.** A `pytest_configure` patch on `socket.connect` records
  every connect to a live rmx unix socket or `127.0.0.1:7777`, with the test that made it, into
  `workflow/review-output/live-socket-touches.log`. One full run logged 72: 66 to `models.sock` and
  6 to the global `rmxd.sock`. It is record-only. Its blind spots and the deferred refuse stage are
  bug-088. {#s-92c374c}
- **d559567 — the `-f/--flags` bundle removed.** `rmx grep -f FILE` is grep's pattern file again.
  rmx's own options are long-form only. `tests/test_grep_no_flag_bundle.py` pins the change, and
  plan-16 d-4 shrank to the index-only options. {#s-d559567}

## Remaining external calls in eval/ (r6 #s-4) {#external-calls}

43e0fa5's claim holds for `src/`: no implicit outbound call remains (r6 swept `src/`, `bin/rmxgrep`,
`bin/rmxrg`, `.claude/hooks` and the templates; `rmx upgrade`'s git fetch + pip are explicitly
allowed). eval/ still calls out:

| call | where | implicit? | proposed disposition |
|---|---|---|---|
| `npm install` when `node_modules` is absent | `eval/memaware/run.sh:37-38` | **yes**, runs on its own | Make it explicit: fail with the install command, like `--fetch` above. |
| `curl` to huggingface.co | `eval/fetch_datasets.sh:39-60` | no; it is a named setup script | Keep. It is "explicit eval setup", which the user allowed. |
| `git clone` from github | `eval/memaware/prepare.py:50`, behind `--clone` | no; behind a flag | Keep. |
| `anthropic.Anthropic()` judge; memaware conditions call LLM APIs | `eval/memory_recall/score.py:65`, memaware conditions | no; the benchmark's own scorer | Keep. It is inherent to the benchmark. |

Only the first row is implicit. Its disposition waits on the user.

rel: evidence-for -> [[bug_registry#registry]]
