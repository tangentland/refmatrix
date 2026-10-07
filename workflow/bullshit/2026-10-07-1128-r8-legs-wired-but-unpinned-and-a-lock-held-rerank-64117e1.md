---
gmd: "0.1"
id: bsd-r1-remedy-r8-64117e1
title: "r7 remedy + bug-090: the vector-delete and rerank surfacing is real code, but 10 of 34 mutations survive on its legs, the failure count reaches no renderer, and the newly live phrase rerank runs inside the store lock"
severity: SKETCHY
plan: plan-15-derive-impact-tracking
task: remedy-bsd-r7
round: 8
prior: 2026-10-07-1050-r7-closed-with-power-recall-legs-still-quiet-bd59e9a.md
tags: [bsd, audit, remediation, rerank, lance, launchd, mutation]
---

# ch-bsd round 8: bd59e9a..64117e1 {#root}

rel: amends -> [[bsd-r1-remedy-r7-bd59e9a]]
rel: evidence-for -> [[impl-remedy-bsd-r7-bd59e9a]]

**Range:** bd59e9a..64117e1. I read the shas from `git log`: d8c2160, d310980 (plan-17/18 drafts),
dc0ec67 (bug-089 row), fbb7134 (launchd PATH), 7afbc2f (bug-090 row), 5e0bcd5 (the r7 report),
8de0c14 (r7 #s-2), 2cd73b9 (r7 #s-1 + bug-089 code), 64117e1 (r7 #m-1..#m-5). While this ran, three
docs-only commits landed on the shared branch (643fb70, e830897, cadc80f: explorations, ADR-0004,
plan-11). They are outside the range and were not audited.
**Date:** 2026-10-07T11:28:55-0700
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed:** 27 (src 10, tests 6, workflow 11)

## Method {#method}

- **No full suite** (bug-085/bug-088). The 6 test files the range touched: 64 passed
  (`workflow/review-output/r8-targeted.log`). `git status` was clean afterwards.
- **Mutations** ran in a `git archive HEAD` copy at `/tmp/r8m` with its own `Store.init()`ed
  `.refmatrix/`. `PYTHONPATH` was PREPENDED with `/tmp/r8m/src`, and `refmatrix.__file__` was
  asserted inside the copy on every run. `__pycache__` was cleared before each run. Each file was
  restored from its saved bytes, checked byte-identical, and `git diff --quiet` was checked in the
  copy. The baseline was 17 files, **162 passed**, and every mutant collected 162.
  - My first pass REPLACED `PYTHONPATH` instead of prepending. That made `import lance` fail
    (`typing_inspection`), the two Lance files skipped, and every Lance mutant "survived". I threw
    that pass away and re-ran everything. The accident is evidence for [[#s-4]].
  - The launchctl dev-tree-guard failures expected in a copy did not appear in this file set, so
    there was nothing to baseline.
- **Model probes** ran under a socket guard that refuses every non-AF_UNIX connect, and also any
  unix socket outside the copy. `huggingface_hub`, `transformers` and `sentence_transformers` were
  imported first. Refused connects: 0.
- **Cost** was measured in a second copy (`/tmp/r8c`) whose own store ingested `docs/` and
  `workflow/plans/`. I used the in-process `cross-encoder/ms-marco-MiniLM-L-12-v2` (warm), and
  `build_context` with and without a reranker, on 10 natural-language phrases.
- **launchd** checks were READ ONLY: `PlistBuddy` on each plist, `launchctl print gui/501/<label>`
  (the `environment` block, not `default environment`), `ps eww` on each running pid, and
  `launchd_path()` rendered by the deploy venv (0.76.2, imports `~/refmatrix/src`).
- Nothing opened a live `.refmatrix/`. No `rmx` write ran. No launchctl verb other than `print` ran.

### Mutation table {#mutations}

34 mutations: 24 killed, **10 survived**.

| id | mutation | result |
|---|---|---|
| V1 | `_lance_for_purge` back to `except ImportError: return None` | killed |
| V2 | the counter does not increment | killed (4) |
| V2b | the failure line is not printed | killed (3) |
| V3 | the batch delete's `except` → `pass` | killed (2) |
| V8 | the single-id delete's `except` → `return False` | killed |
| V4 / V5 / V6 | `sync_files` / `prune_noise` / `fold_concept_dups` report 0 | killed |
| R1 | `_apply_rerank_safe` does not append to `warnings` | killed |
| **R2** | `_op_ann_search` drops `warnings` from its answer | **SURVIVES** |
| **R3** | `_op_memory_recall` drops `warnings` from its answer | **SURVIVES** |
| **R3b** | `_op_memory_recall` does not pass `warnings=` to the helper | **SURVIVES** |
| R4 | the recall verb drops the op's `warnings` | killed |
| **R5** | CLI `memory recall` (daemon branch) does not print them | **SURVIVES** |
| R6 | CLI `search-dense` does not print them | killed |
| R7 | `shared_reranker` does not hand back `why` | killed |
| **R8** | replica recall ignores `why` ("shared worker unavailable") | **SURVIVES** |
| **R9** | scan-prompt does not put `why` on its bundle | **SURVIVES** |
| **R10** | `_op_context` does not merge `bundle.warnings` | **SURVIVES** |
| R11 | `build_context`'s no-anchor hand-off drops the reranker again | killed (2) |
| R12 | a score-time failure is not appended | killed (2) |
| **R13** | `RerankSkipped` is not appended | **SURVIVES** |
| R14 / R15 | `render_text` / `render_json` drop the warnings | killed (2 each) |
| **R16** | the ANCHORED path does not pass `warnings=bundle.warnings` | **SURVIVES** |
| R17 | `content_only_bundle` does not pass it | killed |
| L1 | `launchd_path` returns the caller's PATH | killed (4) |
| L2 | the rmx dir does not lead | killed |
| **L3** | no `is_dir()` filter | **SURVIVES** (all 10 dirs exist on this host) |
| L4 / L5 / L6 | the session / hub / daemon renderer uses the caller's PATH | killed |
| G1 | no `--learn ignored` note on the delegate branch | killed |
| O7 | `tokenizer_config.json` no longer required (r7's survivor) | killed |

Log: `workflow/review-output/r8-mutations.log`.

## r7 findings: closed vs open {#r7-status}

| r7 | status | evidence |
|---|---|---|
| #s-1 rerank legs quiet | **PARTIAL** → [[#s-3]] | Every named leg now carries the cause, and I executed it where I could. On the context op, a construction failure and a score-time failure each land in the op's `warnings`, and the score-time one is also in the body as `# warning:`. scan-prompt shows `# warning: rerank skipped: ModelNotCached …` (`r8-rerank-legs-probe.log`). 9 of the 17 mutations on these legs survive, so the legs work by execution only. |
| #s-2 Lance helper swallows | **PARTIAL** → [[#s-1]], [[#s-4]] | `find_spec` + a hard import holds under the REAL broken import (`env -u PYTHONPATH`, `.venv-eval`): `rmx: vector delete FAILED for 3 code id(s) … (ModuleNotFoundError: No module named 'typing_inspection')`, failures=3 (`r8-lance-broken-import-probe.log`). V1-V8 are killed. But the count reaches no renderer, and the bulk-forget/vacuum paths never report it. |
| #m-1 per-file Lance versions | **OPEN, anchored (MEH-active)** | Recorded in plan-17 (§52, row 17.1). plan-17 is `drafting`, and the 17.1 task spec is not written yet. |
| #m-2 external-calls table | **CLOSED** (note in [[#m-3]]) | `run.sh:38`/`:39` and `score.py:66` verified. |
| #m-3 hub-constant leak | **CLOSED** | A follow-on test in the copy asserts the constant matches the env after `test_models_offline.py`: 17 passed (`r8-m3-constant-probe.log`). |
| #m-4 O7, delegate `--learn` | **CLOSED with power** | O7 and G1 are killed. |
| #m-5 task 16.6 notes | **CLOSED** (text) | Left for 16.6's spec review. |

Closed: 4. Partial: 2. Open-anchored: 1.

## Launchd PATH audit (bug-090) {#launchd}

- **The fleet matches its render.** All 15 `com.refmatrix.*` plists (8 daemons, the hub, 6 session
  indexers) equal `launchd_path('/Users/tholley/bin/rmx')`, rendered by the deploy venv, and so does
  the loaded job's `environment` PATH. The 9 running pids (started 10:50-10:59) carry it in their
  real environment (`ps eww`). Log: `r8-launchd-fleet.log`.
- **Every tool the daemon, hub and indexer exec resolves on it:**
  - `rg` and `git` → `/opt/local/bin`
  - `tldr` → `~/bin` (symlink to `claude_tools/tldr-venv`)
  - `graphify` → `~/.local/bin`
  - `lsof` → `/usr/sbin`
  - `ps` and `launchctl` → `/bin`
  - `grep` → `/usr/bin`
  - Model workers spawn through `sys.executable`, so they need nothing from PATH.
- **The PATH value no longer depends on the caller.** L1, L4, L5 and L6 are killed. Three other
  values still do → [[#m-1]].

## Findings {#findings}

### SKETCHY #s-1: `vector_delete_failed` is counted into dicts that no renderer reads, and the memory-forget paths never count it {#s-1}

**File:** `src/refmatrix/store.py:3591-3600`, `src/refmatrix/sync.py:323-331`,
`src/refmatrix/daemon.py:3018-3041`, `src/refmatrix/cli.py:7744-7759`, `8341-8344`, `12550-12554`
**What:** 8de0c14 says the failure is "PRINTED … and COUNTED …, which sync / prune / fold report".
**Why it's sketchy:** On a daemon-managed store, every one of those calls runs inside the daemon:
- The CLI's `_store(write=True)` proxy routes `prune_noise`, `fold_concept_dups` (`memory dedup`)
  and `sync` through daemon ops. The `print(..., file=sys.stderr)` therefore lands in
  `daemon.stderr.log`, not on the user's terminal.
- The three CLI renderers print fixed keys (`dropped/kept`, `folded/edges_migrated`,
  `+added ~updated -purged`). None of them reads `vector_delete_failed`.
- The watch flush, which is the hot path bug-085 moved onto this helper, sums `added/updated/purged`
  into its `rmxd.log` line and drops the new key.

The only user-reachable trace is the `sync.log` suffix. `bulk_forget_memories`, `forget_entities`
and `vacuum` go through `_bulk_purge_ids`, and they return no count at all. r7 named
`bulk_forget_memories` as the memory path the CRITICAL rule covers.
**Evidence:** I read the code at the lines above. `grep vector_delete_fail src/` finds no consumer
outside store.py and sync.py.
**Fix:**
- Render the key wherever it is non-zero: the three CLI lines and the watch-flush log line.
- Return it from `_bulk_purge_ids` → `bulk_forget_memories` / `forget_entities` / `vacuum`, and from
  their ops.

**Pattern match:** YES. This is the third round in a row where a remedy made a failure loud on one
leg and stopped (r6 #s-2, r7 #s-1, now this). It is not escalated to BULLSHIT, as in r7: the failure
is no longer `pass`. It is in two logs, but not on the surface where the caller is.

rel: contradicts -> [[claude#no-silent-failures]]

### SKETCHY #s-2: the phrase rerank 2cd73b9 brought to life runs the model call inside `_store_lock`, with no deadline, on a route the eval never measures {#s-2}

**File:** `src/refmatrix/daemon.py:4625-4651`, `src/refmatrix/daemon.py:1047-1072`,
`src/refmatrix/context.py:196-204`
**What:** The no-anchor hand-off now passes the reranker, so every natural-language `context` op
reranks. That covers MCP `rmx_context` and the CLI's daemon branch, with the default `RMX_RERANK=1`.
**Why it's sketchy:**
- `_op_context` builds the reranker outside the lock, but `build_context` (and so `score`) runs under
  `with d._store_lock`. `memory_recall` and `ann_search` deliberately score OUTSIDE the lock
  ("Model call OUTSIDE _store_lock -- see collect_rerank_docs").
- The daemon's `RemoteReranker(self._model_client("rerank"))` has no `budget_s`/`deadline`, so a
  busy shared worker can hold the writer lock up to `SHARED_OP_TIMEOUT_S` (45 s).
- That is the lock-holding wedge class of bug-085 and the 2026-10-07 wedges. The anchored path
  already did this. The remedy widened it to every phrase and did not measure the cost.
- The orderings now differ by route. The production eval's `context` method runs the CLI, which
  takes the replica branch, and that branch never reranks. So MCP callers get an ordering whose
  quality has never been measured.

**Evidence (`r8-context-rerank-cost.log`):** 10 of 10 phrases reach `score` (10 docs each). Warm
in-process, `score` takes 0.086-0.115 s. `build_context` goes from 0.017-0.022 s without a reranker
to 0.130-0.159 s with one (median delta 0.121 s, ~7x), and all of that is lock-held in the daemon.
The code's own comment (`context.py:571`) measured 10 docs at 1.33 s on the hook's worker.
**Fix:** Either collect the docs under the lock and score outside it (the `memory_recall` shape), or
give the context op's reranker a deadline. Measure the MCP route's ordering before relying on it, or
default the phrase rerank off until it has been measured.
**Pattern match:** YES, related to bug-085 ("a wedge is a lock-holding op").

rel: contradicts -> [[claude#no-workarounds]]

### SKETCHY #s-3: 9 of the 17 mutations on the r7 #s-1 legs survive; the "7 RED tests" pin the helpers, not the legs {#s-3}

**What:** R2, R3, R3b, R5, R8, R9, R10, R13 and R16 survive. The tests stub the op under the verb
(`fake_call`), the daemon under `_apply_rerank_safe`, and the client under `shared_reranker`. No test
covers any of these:
- an op returning `warnings`;
- the CLI recall printing them;
- the replica leg naming the cause;
- scan-prompt carrying it;
- the context op merging `bundle.warnings`;
- the anchored path's `warnings=`;
- `RerankSkipped` landing on the bundle.

**Why it's sketchy:** My probe shows these legs work today (`r8-rerank-legs-probe.log`, for the
context op and scan-prompt). Any one of them can be deleted with the 162-test family green. That is
exactly how r6 #s-2 → r7 #s-1 happened.
**Fix:** One test per surviving mutation, each driven through the real op or CLI with only the model
boundary stubbed. The context-op and scan-prompt shapes in my probe are ready-made: a stub daemon
over a real ingested store.
**Pattern match:** YES, r4 #s-1 ("works by execution only").

### SKETCHY #s-4: the Lance pins `importorskip("lance")`, so they vanish in exactly the condition r7 #s-2 was about {#s-4}

**File:** `tests/test_lance_drop_failures_loud.py:20`, `tests/test_purge_path_batched_lance.py:18`
**What:** `.venv-eval` has no `typing_inspection`. `import lance` works there only because the
user's shell `PYTHONPATH` adds the system site-packages. With `env -u PYTHONPATH`, both files SKIP:
`could not import 'lance': No module named 'typing_inspection'` (`r8-lance-clean-env.log`). That
silently drops the 4 new pins and bug-085's K1-K5 pins.
**Why it's sketchy:** At module level the test layer does what 8de0c14 removed from `src/`: it reads
a broken install as "not installed" and goes quiet. The project rule is "ALL tests run … never skip".
My own first mutation pass shows the hazard: one environment difference turned 9 killers into 9
skips, with every count still green.
**Fix:**
- Use `find_spec("lance") is None` → skip, and otherwise a hard `import lance` that FAILS.
- Install `typing_inspection` into `.venv-eval`.
- Add a bug row for the dev venv depending on the shell's `PYTHONPATH`.

**Pattern match:** YES, "a guard that cannot fire" (impression_bsd_guard_cannot_fire).

rel: contradicts -> [[claude#system-dependent-tests]]

### MEH #m-1: launchd PATH, the residue {#m-1}

- `launchd_path` says "the installed rmx's own venv bin leads". The deployed `rmx` is the symlink
  `~/bin/rmx`, so `Path(rmx).parent` is `~/bin`, and the deploy venv's `bin` is not on the PATH at
  all. This is harmless today (workers use `sys.executable`), but the docstring is false for the
  only real install.
- L3 survives: all 10 candidate dirs exist on this host, so "only existing dirs are kept" cannot
  fail here. A test with a non-existent `$HOME` would pin it.
- Three more values in the render still depend on the caller, in the same class as bug-090:
  - the hub renderer copies `RMX_WORKER_IDLE_S` and `RMX_HUB_QUEUE_ALERT_INTERVAL` from the
    installing shell, so a reinstall from a shell without them silently drops the knob;
  - `_rmx_path()` is `which rmx`, and this host has two (`~/bin/rmx`, `python_libraries/…/bin/rmx`).
- `~/bin` (167 entries, including `python3.14`, `pip`, `as`) now leads every daemon's PATH, ahead of
  MacPorts and the system. Nothing the daemon execs is shadowed today. Ordering it after the system
  dirs, or listing only the tool dirs, would remove that risk.

### MEH #m-2: duplicate and unreachable messages {#m-2}

- The CLI `rmx context` daemon branch prints a score-time warning twice: once in the body
  (`# warning:`) and again on stderr (`rmx context:`), because `_op_context` both renders it and
  merges it into the op's `warnings`.
- The vector-delete message names `rmx embed --gc` as the remedy. In the broken-import case the
  message exists for, `--gc` needs the same `import lance`, so the remedy cannot run.

### MEH #m-3: doc notes {#m-3}

- The r6 summary records the user's "leave it" as covering BOTH implicit `npm install` rows. The
  second row (`npm install @anthropic-ai/sdk`, unpinned) was added after that decision, and the text
  says "same user decision". It should be put to the user, not inferred.
- Plans 17/18 (drafting): 17.1's AC says "lock released between datasets (measured)", which fits
  [[#s-2]]'s concern. Nothing blocking for the spec review.

## Deferral sweep (rules 9 / 9a) {#deferrals}

On the added and removed lines in `src/` and `tests/` there is one hit: "orphaned until `rmx embed
--gc`". It names a real command, so it is anchored ([[#m-2]] covers its reachability). The removed
docstring "Best-effort … GC reaps later" is gone. That closes r7's unanchored "GC reaps later".
r7 #m-1 is anchored to plan-17 row 17.1. The plan is `drafting`, its task specs are pending, and it
is active, so it is MEH. No stale deferral to a completed plan.

## Verdict {#verdict}

**DIRTY: 7 findings (0 BULLSHIT, 4 SKETCHY, 3 MEH).** No blockers. r7: 4 closed, 2 partial, 1
open-anchored. 34 mutations, 24 killed, 10 survive (9 on the rerank legs, 1 on the launchd dir
filter). The launchd PATH fix is live and consistent across all 15 jobs.

rel: contradicts -> [[claude#no-silent-failures]]
