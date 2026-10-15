---
gmd: "0.1"
id: bsd-plan16-22-spec-diffcheck-r9-29e335a
title: "plan-16 + plan-22 spec diff check r9: round 8 (29e335a) closes all 8 r8 findings, and the re-measure reproduces exactly. Four gaps remain. 22.6's evidence_orphan_drop has no rule for an orphan whose concept is also dead (5,341 rows on cliquedb), because row_event refuses an empty c_kind. The incremental replay path the specs keep extending has no caller. _row_op_c_kinds reads live kinds where the rebuild reads logged kinds. 16.3 R5 collides with the bug-118 branch's test."
severity: SKETCHY
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-diffcheck-r9-16.2-16.3-16.4-16.6-22.1a-22.2-22.6
round: 13 (plan-16) / 9 (plan-22)
tags: [bsd, audit, spec-review, diff-check, removal, replay, bug-117, bug-118, bug-120, bug-121, c-kind, orphan-drop, d9bj, d9bk, d9bl, d9bs]
---

# ch-bsd r9 diff check: plans 16 and 22 after revision round 8 (`29e335a`) {#root}

**Commit reviewed:** `29e335a` on `wave0-spec-reviews` (HEAD). The round-8 revision of plans 16 and 22 is this one commit. It is diffed against `23ad703` for `workflow/plans/plan-16-*`, `workflow/plans/plan-22-*` and `workflow/bug_registry.md`. `src/` has not changed since `23ad703`.

**Written:** 2026-10-15T03:50-0700.
**Author of the revision:** Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision round 8).

**Method (read-only):**
- Every r8 finding was checked at the text of HEAD.
- I read the source at HEAD:
  - `edge_records.py`;
  - from `store.py`: `apply_log_delta`, `_replay_concept`, `_apply_event_body`, `rebuild_index_from_log` (Pass 2, 2b and 3), the edge queries of `dump_catalog_to_log`, and `_log_event`;
  - the learn-switch blocks in `search_hooks.py` and the global `grep-rewrite-guard.sh` / `rmxgrep-rewrite.py`;
  - `.claude/hooks/enforce-rmx-grep.sh`.
- The bug-118 branch: I read `bugs-112-113-118` in `/Volumes/littlebig/refmatrix-bugs112-118`, including its working-tree `hooks.py` and `tests/test_bug118_optional_hook_exit.py`.
- I re-ran the reviser's `scratchpad/r8/ev15d.py` to `ev15g.py` on the r6 cliquedb copy, with `.venv-eval` and DuckDB `read_only`.
- New probes are in `scratchpad/r9/`: `lk.py` (legacy rule over live kinds vs logged kinds), `both.py` (orphans with both ends dead), `ids.py` (orphan identity counts) and `two.py`.
- GMD lint on the 15 plan-16/22 files: 0 errors.

**What I did not touch:** no store or socket was opened, no spec or source was edited, and nothing was committed.

rel: amends -> [[bsd-plan16-22-spec-rereview-r8-23ad703]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5]]
rel: contradicts -> [[task-22.2-repair-then-remove#r3]]

## Round-8 findings: status {#prior-status}

| r8 id | status | evidence at HEAD |
|---|---|---|
| b-1 (row ops predate bug-117) | **closed** | <ul><li>22.2 R3 "How the ends resolve" is rewritten: ends resolve by `(c_kind, c)`; legacy events go through `resolve_c_kind`; matching is by `row_key`; `row_event` raises when `c_kind` is empty.</li><li>The "pre-existing and unchanged" note is deleted.</li><li>Every op now carries `c_kind`: `evidence_remove`, `evidence_repoint`, R9 `unlink` (through `edge_event`), `evidence_orphan_drop`, `learned_provenance` and `_move`.</li><li>The LWW key is `(partition, linkage, c_kind, c, e_kind, e)`.</li><li>Fixtures:<ul><li>AC-3b: `Y` is a doc and `concept Y` is logged, with the mutation "`unlink` without `c_kind`".</li><li>AC-3c and AC-3d are on a DOC.</li><li>AC-3e stays on `concept`.</li><li>New AC-3f covers a legacy append against a kinded remove.</li></ul></li><li>The 16.6 helpers match the code at HEAD ([[#helpers-vs-code]]). Residue: [[#s-2]], [[#m-1]], [[#m-5]].</li></ul> |
| s-1 (orphan drop "at that point") | **closed** | <ul><li>22.6 [[task-22.6-removal-entry-points#r5-timeline]] defines dead-at-`T` on per-key `entity`/`tombstone` `ts` lists, and AC-6b has the mutation.</li><li>I traced the rule against Pass 3 ([[#timeline-trace]]). It can be evaluated, and the mutation fails as stated.</li><li>d-28 is recorded.</li><li>Residue: [[#s-1]] (both ends dead) and [[#m-4]] (partition field).</li></ul> |
| s-2 (learn.off operator state) | **closed** | <ul><li>Plan-16 has `#today-learn-off` and `#learn-flip`, and the waves row says "deploy together, then the user flips".</li><li>16.2 `#rich` is rewritten.</li><li>16.3 R5 retires the redirect and keeps the signature for the reap; AC-10 is added.</li><li>16.4 R0 adds the window start and the decision in the header; runs read `learning-off` / `no-window`; AC-8.</li><li>The marker state is as stated: the global marker exists (00:29) and the project marker does not.</li><li>The route-1 claim holds: `rmxgrep-rewrite.py` reads `learn.off`.</li><li>Residue with bug-118: [[#m-3]].</li></ul> |
| m-1 (row pass keeps Pass 2b) | **closed** | <ul><li>16.6 R1d says Pass 2b stays, and the row pass takes `resolved_evidence`.</li><li>The AC-9c AST clause is scoped to pass 3.</li><li>`tests/test_bug117_rebuild_non_concept.py` exists and asserts the counters.</li></ul> |
| m-2 (one legacy rule for naming and reborn) | **closed** | <ul><li>22.1a [[task-22.1a-provenance-free-classes#r1-covering]] covers by logged kinds through `resolve_c_kind`, counts `legacy_unresolved`, and treats every live covering key as reborn.</li><li>The re-measure reproduces exactly ([[#remeasure]]).</li></ul> |
| m-3 (legacy resolution differs between paths) | **closed in the specs, but the registry anchor is false** | <ul><li>The "agree on kinded events only" paragraph is present in 16.6 and in 22.2.</li><li>bug-120 is filed, but its Planned cell points to a task that disclaims the fix ([[#s-2]]).</li></ul> |
| m-4 (rebuild counters) | **closed** | <ul><li>AC-3b asserts `links_skipped_dead == 0`, and "tombstone only" fails directly.</li><li>AC-3c, 3d, 3e, 3f, 6b and 9c assert `evidence_unresolved` / `evidence_skipped_dead`.</li><li>R9 step 5 counts.</li></ul> |
| m-5 (pins) | **closed** | <ul><li>`:7941` is the sort.</li><li>`:7946` / `:7968` are `dpart` / `part`.</li><li>`:7640` / `:7662` are the dump `GREATEST`.</li><li>The 22.6 `#facts` re-read matches HEAD.</li></ul> |
| r8 observation (`\|\| true`) | **filed as bug-118** | <ul><li>The row matches the branch.</li><li>`_optional_project_hook` renders `if [ -x P ]; then P; fi`, and all three sites route through it.</li><li>The test runs a stub that exits 2 and requires exit 2 back, plus an AST check that no second rendering exists.</li></ul> |

**Totals:** all 8 r8 ids are closed in the spec text. m-3's registry anchor is false, which [[#s-2]] covers.

## Verified facts {#facts}

### 16.6 `#r1d-one-format` against `edge_records.py` and `store.py` at HEAD {#helpers-vs-code}

**What exists today:**
- `edge_records.py` holds `EDGE_OPS`, `edge_fields`, `edge_event` (raises outside `EDGE_OPS`) and `resolve_legacy_kind`.
- `ROW_OPS`, `row_event`, `row_key` and `resolve_c_kind` do not exist yet. They are new in this slice, as the file list says.

**What matches the code:**
- **`resolve_c_kind`.** Its contract ("`c_kind` when present, else `resolve_legacy_kind(kinds_by_name.get((partition, c), ()))`") is exactly the per-event rule of Pass 2b at `store.py:8045` and `:8061`. `kinds_by_name` is built from `entity_state`, which includes tombstoned keys.
- **Callers of `resolve_legacy_kind`.** Exactly three call sites exist (`:7789`, `:8045`, `:8061`), so the "only from `resolve_c_kind`" pin in AC-9d check 2 is achievable by extraction.
- **`row_event`.** It returns `{"op": op, **edge_fields(...)}`. That dict display has a non-constant `"op"`, so AST check 1 does not trip on the builder itself. The dump's existing `{"ts", "partition", **edge_event(...)}` shape is also safe.

**Where AC-9d can mis-fire:** check 3 and check 4 ([[#m-5]]).

**Can the mutations fail?**
- "Row pass before Pass 2b" can fail, as I traced below.
- **The trace.** The legacy append's `c_kind` stays None, so `name_to_id[(None, "query/P")]` misses. The row is skipped, and the provenance is counted `no_row`, which gives `unresolved_provenance == 1`.
- **The remaining four.** "Dict literal", "row op resolves as `concept`", "second `resolve_legacy_kind`" and "per-branch counter" are each caught by their AST clause.

### 22.6 `#r5-timeline` during a rebuild (AC-6b) {#timeline-trace}

**What the rule needs:**
- Pass 2 keeps only `latest_ts` per entity key and `tombstone_ts` (latest). The rule asks for per-key sorted `ts` lists, which come from the same loop with no new input.
- The row pass runs after materialization. An append whose entity is dead at the end of the log is skipped there and counted `evidence_skipped_dead`, so a drop has nothing to delete for it.

**The AC-6b sequence, step by step:**

| step | log time | event |
|---|---|---|
| 1 | T0 | ingest `D`: `entity D`, `evidence(B=D → target)` |
| 2 | T1 | `tombstone D` |
| 3 | T2 | `evidence_orphan_drop` |
| 4 | T3 | `entity D` plus the identical `evidence` |

**The trace under the timeline rule:**
- `D` survives to the end, so the T0 copy is materialized onto the new `D` in pass order.
- At T2, `D`'s latest tombstone at or before T2 is T1. That is at or after its latest `entity` at or before T2, which is T0. So `D` was dead at T2, and the drop deletes the copy.
- T3 appends one copy, so the rebuild holds 1, which equals live. `orphan_drop_skipped_live == 0`.

**The trace under the mutation** "orphan-drop checks the materialized catalog": `D` exists at T2, so the drop skips. The copy holds 2 and the AC fails, as stated.

**Verdict:** the rule can be evaluated during a rebuild.

### The cliquedb re-measure (bug-121, d9bs) {#remeasure}

I re-ran the reviser's `ev15d.py` to `ev15g.py` on the r6 copy. The output is identical to the reviser's logs:

| quantity | value |
|---|---|
| dead rows | 14,733 (14,745 rows; the probes dedup identity without `detail`) |
| rows covered | 1,995 |
| `(row, live covering key)` pairs held | 2,744 |
| pairs not held | 121 |
| dead ids | `unnamed:none` 3,882; `unnamed:reborn` 896 |
| reborn on more than one live key | 381 |
| reborn ids with a row to remove | 47 |
| `legacy_unresolved` | 0 |
| two-kind covering names | 10, all resolved to `concept` |
| of the 121 rows | 121 held by the doc, 0 by the concept |
| revive pairs held live by another kind | 121 of 121 |

**Tie-order noise confirmed.** In `ev15c`, the 515 untied best keys are all live as `concept` only, and the two-kind list is empty. r7's "15 as both" therefore lived only on the 381 tied ids.

**One wording slip.** bug-121 says "10 names exist as both doc and concept". Store-wide there are 21 such names (`two.py`). The 10 are the covering names ([[#m-6]]).

## New findings {#findings}

### SKETCHY s-1: `evidence_orphan_drop` cannot name the concept of an orphan whose concept is also dead, and 5,341 of cliquedb's 7,599 vacuum orphans are that shape {#s-1}

**The spec.** 22.6 [[task-22.6-removal-entry-points#r5]]:
> `linkage` and the concept end are by NAME, the concept's kind(s) through 22.2's one helper `Store._row_op_c_kinds`

The helper is `_row_op_c_kinds(c_name, catalog_kind)`. 16.6 `row_event` "RAISES … on an empty `c_kind`".

**The data** (`scratchpad/r9/both.py`, read-only copies):

| store | orphan rows (`vacuum` step 3: entity dead) | of which the concept is dead too |
|---|---|---|
| cliquedb | 7,599 | **5,341** |
| refmatrix (r6 copy) | 833,401 (441,721 identities, 28,682 dead entity ids) | **2,679** |

**Why this is a problem.** A both-dead orphan has no catalog name and no catalog kind for its concept. Followed literally:
- `_row_op_c_kinds` has no `catalog_kind` to take.
- `row_event` raises, and `vacuum` aborts mid-step.

An implementer who works around that will either skip these rows without an event, which is a silent skip on a memory path (CLAUDE.md `#no-silent-failures`), or invent a kind. The spec offers no rule, and no AC has a both-dead fixture. This is the same gap 22.2 R9 solved for dead concept ids (22.1a naming), but it was never carried to the vacuum path.

**Fix (text):** add to 22.6 R5:
> **Both ends dead.** An orphan row whose CONCEPT id is also dead is named by 22.1a's dead-id naming ([[task-22.1a-provenance-free-classes#r1-dangling]], covering per [[task-22.1a-provenance-free-classes#r1-covering]]). A NAMED or reborn concept logs the drop on each key that covers it, using that logged key's `c_kind` and `c`, exactly as 22.2 R9 step 4 keys its events. A nameless concept (`unnamed:none` / `unnamed:ambiguous`) logs NO event and is counted `orphan_drop_nameless` and printed, because no logged name lets a rebuild re-attach the row (22.2 R9 step 5's reason). `_row_op_c_kinds` is called only for a live concept.

**New AC-6c:**
- **Setup.** One orphan whose concept was tombstoned with an `entity` event in the log (named), and one whose concept id no event names (nameless).
- **After `vacuum`.** There is 1 drop event, keyed on the named concept's logged kind. `orphan_drop_nameless == 1`.
- **Rebuild check.** A rebuild on a copy, after re-creating both names, holds neither row.
- **Mutation.** "Skip both-dead rows without a count" FAILS on the counter.

rel: contradicts -> [[task-22.6-removal-entry-points#r5]]

### SKETCHY s-2: the incremental replay path the specs extend has no production caller, and bug-120's "Planned" cites a task that disclaims the fix {#s-2}

**The code.** `apply_log_delta` is the only caller of `_apply_one_event`, which is the only caller of `_apply_event_body`. `apply_log_delta` itself has no caller in `src/`. The only remaining mention is the `REPLICA_REBUILD_DELTA_BYTES` comment in `daemon.py:516`, which describes the dropped rotation (d9ao). So the whole incremental path is dead at HEAD.

**What the specs mandate on it anyway:**
- an `_apply_event_body` branch for every new op (16.6 R1d, 22.2 R3, 22.6 R5);
- AC-9d check 3 (every `EDGE_OPS ∪ ROW_OPS` branch calls `_replay_concept`);
- `row_skips` "on both paths";
- 22.6's "incremental path keeps the catalog check";
- AC-3f's "the incremental replay of the same delta counts the `concept` op `no_row`".

Each of these is new code on an unreachable path, kept alive only by tests (rule 1).

**The registry anchor is false.** bug-120's Planned cell says "Planned (16.6 `#r1d-one-format`): ONE resolver … fed the logged kinds on both paths, or retire `apply_log_delta`". But 16.6 `#r1d-one-format` says `_replay_concept` calls `resolve_c_kind` "with the LIVE catalog's kinds". 16.6 R1d also says the difference "is a bug-registry item for the orchestrator, not a requirement of this task". So the registry row points at a task that explicitly declines the work. That makes it an unanchored deferral (rule 9a).

**Fix (needs a user ruling; I recommend (a)):**
- **(a) Retire the incremental path.**
  - Delete `apply_log_delta`, `_apply_one_event`, `_apply_event_body` and `_replay_concept`, together with their tests. This could go in 16.6's slice, which already touches the path.
  - Strip the incremental clauses from 16.6 R1d / AC-9d check 3, from 22.2 R3 / AC-3f, and from 22.6 R5.
  - `row_skips` becomes rebuild-only.
  - bug-120 closes as "retired".
  - d9ao's rationale (rotation dropped) already covers this.
- **(b) Keep the path.** In that case bug-120's Planned cell must name a task whose acceptance criteria actually close it, and none does today. Feeding logged kinds incrementally needs a log scan, which defeats the path's purpose.

Either way, rewrite bug-120's Planned cell now so it does not cite 16.6.

rel: contradicts -> [[task-16.6-learned-row-validation#r1d-one-format]]

### MEH m-1: `_row_op_c_kinds` reads the LIVE kinds, but the rebuild's legacy rule reads LOGGED kinds; a tombstoned same-name `concept` slips through {#m-1}

**The spec.** 22.2 R3: the extra kind is `resolve_c_kind(None, c_name, partition, <kinds of c_name in the live partition>)`. The same paragraph says "A row op must name the key a rebuild holds the copies under". d9bl requires "the SAME … `resolve_legacy_kind` path as the replay of that row", which on a rebuild is the logged kinds.

**The failure case:**
1. A `concept X` is tombstoned. R9 step 4's own named-concept tombstones create exactly this.
2. A live `doc X` holds `B`'s row through a legacy append.
3. R2 purges `doc X`.
4. The helper sees live kinds `{doc}` and logs only the `doc` op.
5. On a rebuild, the legacy append resolves to `concept` (it is logged). It is skipped dead until `concept X` is re-created, and then it revives on the new concept. Live does not hold that row.

**Scale today.** On the cliquedb copy, the two rules differ for only 2 names, and neither has an evidence event (`scratchpad/r9/lk.py`). The risk grows with every plan-22 tombstone.

**Fix.** The legacy rule can only mis-resolve to `concept`: `resolve_legacy_kind` returns `concept` whenever one is logged. So no log read is needed. Define:
> `_row_op_c_kinds(c_name, catalog_kind)` returns `(catalog_kind,)`, plus `edge_records.LEGACY_PREFERRED_KIND` (today's `_LEGACY_PREFERRED_KIND`, made public) when `catalog_kind` differs from it and no LIVE entity of that kind and name holds an identical row.

- The extra op is harmless when no `concept` was ever logged: it matches nothing, and is counted `no_row`.
- AC-9d check 2 then drops `_row_op_c_kinds` from its `resolve_c_kind` caller list, or keeps it with the constant.
- Add a third AC-3f run:
  1. `concept A` is tombstoned in the log; `doc A` holds `B`'s legacy row.
  2. Purge `doc A`, then re-create `concept A`.
  3. A rebuild on a copy holds no `B` row on `concept A`.
- Mutation "the helper reads live kinds through the legacy rule" FAILS it.

### MEH m-2: AC-3f's second-run divergence is avoidable with the existing `keep=1` {#m-2}

**The current rule.** When `concept A` holds an identical row live, the helper logs no concept op and counts `legacy_misresolved`. The rebuilt copy holds `concept A`'s row twice while live holds it once, which is accepted as residue.

**The alternative.** R2's `remove_evidence` already has `keep=1` ("collapses to one"). Logging the concept-keyed op with `keep: 1` when the live concept holds exactly one copy makes the copy equal live:
- Under the timestamp order, the copies on the concept key at `T` are the concept's own copy plus the misresolved one, and `keep=1` collapses them to one.
- Incrementally it is a no-op.

**Fix (22.2 R3):**
- The concept op carries `keep = n`, where `n` is the number of identical copies the live concept holds, when `n` is 0 or 1.
- `legacy_misresolved` is counted only when `n >= 2`.
- AC-3f's second run then asserts that the copy equals live (once).
- Mutation "`keep: 0` on the concept op" FAILS it, because the copy holds 0.

### MEH m-3: 16.3 R5 collides with the bug-118 branch, and AC-10's `|| true` note goes stale when bug-118 merges {#m-3}

**The collision.** On `bugs-112-113-118` (working tree), `tests/test_bug118_optional_hook_exit.py` has `SCRIPTS = ("enforce-test-to-file.sh", "enforce-rmx-grep.sh", "adr-gate.sh")`. With `enforce=True`, it asserts `name in cmds` for each script. The new `_add_enforce_entries` renders all scripts from one tuple. When 16.3 R5 stops emitting the `enforce-rmx-grep.sh` entry, that test fails, and 16.3's file list does not name it.

**The stale note.** AC-10's parenthetical ("the generator's `|| true` wrapper turns the script's exit 2 into 0, so the exit code alone cannot see it") is false once bug-118 merges.

**Prose the files list misses:**
- `.claude/hooks/hooks.env:10` and `hooks.env.example` ("redirected to rmx by enforce-rmx-grep");
- `telemetry.py:192`'s docstring.

**Fix:**
- Add `tests/test_bug118_optional_hook_exit.py` to 16.3's files list: drop `enforce-rmx-grep.sh` from `SCRIPTS`, and assert that it is NOT rendered even with `enforce=True`.
- Make the AC-10 exit-code assertion primary ("no hook exits 2"). Replace the parenthetical with "before bug-118 the exit code could not see it; after bug-118 it can".
- Add `hooks.env`, `hooks.env.example` and `telemetry.py` to R5's prose sweep.
- **Ordering note for the deploy handoff.** If bug-118 deploys before 16.3, the redirect really blocks wherever the marker is absent. Today the global marker covers every project, and d9bj keeps the flip after 16.3, so the handoff only needs to say "do not run `rmx learn on` in any scope before 16.3 is deployed".

### MEH m-4: 22.6 R5 does not say which `partition` field `evidence_orphan_drop` carries {#m-4}

**Why it matters:**
- `_log_event` adds no partition (`store.py:1119`).
- A compacted log's appends carry `partition: p`, while live-shape appends carry none.
- The row pass runs per partition. A drop logged without the field lands in the default partition's pass and cannot match a compacted append in `p`.
- 22.2 R9 step 4 has the rule for this ("the `partition` field of the `facts.log` event it answers, exactly as that event carries it"). 22.6 R5 does not.

**Fix:**
- In R5, one drop per distinct partition field among the appends of that identity, each carrying the field as those appends carry it (R9 step 4's rule, cited).
- AC-6b variant: run the vacuum after a compaction in a non-default partition, so the appends carry `partition: p`. The rebuild still holds 1 copy.
- Mutation "drop without the appends' partition field" FAILS it.

### MEH m-5: two AC-9d AST clauses can mis-fire on legitimate code {#m-5}

**Check 3.** It reads "neither `_apply_event_body` nor `rebuild_index_from_log` calls `get_entity` or indexes `name_to_id` with a constant kind". `rebuild_index_from_log`'s memory-body block legitimately tests `("memory", key[1]) not in name_to_id` (Pass 3, memory bodies). `_apply_event_body` calls `get_entity(ev["kind"], …)` for `entity`/`protect`/`noise`/`tombstone`.

A broad implementation of the check fails at HEAD, which invites weakening the check.

**Fix for check 3:** scope it to "the `EDGE_OPS ∪ ROW_OPS` branches of `_apply_event_body` and the link and row passes of `rebuild_index_from_log`". Then name the memory-body membership test as allowed.

**Check 4.** Its heuristic ("no tuple display holding both a `"file"` and a `"line"` subscript of an event") also catches the SQL parameter tuple that `evidence_remove`'s DELETE needs.

**Fix for check 4:** say that parameters are taken from `row_key(ev)`, e.g. `k = row_key(ev)` then `(…, k[5], k[6], …)`.

### MEH m-6: registry wording {#m-6}

- **bug-121.** "10 names exist as both doc and concept" should read "10 COVERING names (21 store-wide) exist as both".
- **bug-120.** See [[#s-2]].

## Per-task verdict {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1 | **ready** | none |
| 16.2 | **ready** | none |
| 16.3 | **ready after a small edit** | [[#m-3]] (bug-118 test, AC-10 note, prose sweep) |
| 16.4 | **ready** | none (R0 and AC-8 are sound) |
| 16.5 | **ready** | none |
| 16.6 | **ready after a small edit** | [[#s-2]] (ruling on the incremental path), [[#m-5]] (AC-9d scoping) |
| 22.1 | **ready** | none |
| 22.1a | **ready** | none (the re-measure is verified) |
| 22.2 | **ready after a small edit** | [[#m-1]], [[#m-2]], plus [[#s-2]] (AC-3f incremental clause) |
| 22.3 | **ready** | none |
| 22.4 | **ready** | none |
| 22.5 | **ready** | none |
| 22.6 | **needs an edit pass** | [[#s-1]] (both-dead orphans plus AC-6c), [[#m-4]], plus [[#s-2]] |

**One user ruling is needed:** [[#s-2]], whether to retire the incremental replay path (my recommendation) or keep it and give bug-120 a real owner. Everything else is a text edit.

## Verdict {#verdict}

DIRTY: 8 findings (0 BULLSHIT, 2 SKETCHY, 6 MEH). r8: 8 of 8 closed.

- **Plan-16:** approvable after the 16.3 / 16.6 MEH edits and the [[#s-2]] ruling.
- **Plan-22:** approvable after one edit pass on 22.6 ([[#s-1]], [[#m-4]]) and 22.2 ([[#m-1]], [[#m-2]]). No design is open.
