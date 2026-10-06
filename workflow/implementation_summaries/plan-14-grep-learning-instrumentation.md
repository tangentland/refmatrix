---
gmd: "0.1"
id: impl-plan-14-grep-learning-instrumentation
title: "Plan 14 summary (14.1-14.3): the grep loop got an instrument, a switch, and a bug"
tags: [implementation-summary, plan-14, telemetry, grep, learning]
metadata:
  node_type: summary
  task: task-14.1-answered-by-telemetry
  created: 2026-10-06
---

# Plan 14 summary — tasks 14.1, 14.2, 14.3, and bug-067 {#root}

rel: realizes -> [[task-14.1-answered-by-telemetry]]
rel: realizes -> [[task-14.2-learning-toggle]]
rel: realizes -> [[task-14.3-hook-follows-toggle]]
rel: part-of -> [[plan-14-grep-learning-measurement]]
rel: evidence-for -> [[bug_registry]]

The ask was "do we have any measure of how effective the learning aspect of funnelling grep through
rmx is?". The answer was no — and building the instrument found a defect that made the question
unanswerable in the first place. {#lead}

## 14.1 — every grep row says WHAT answered it {#answered-by}

`query.log` carried `source: "grep-replica"` for all 1,536 grep rows and nothing separating *the
index answered* from *the tool floor answered*. 35 learn-path tests existed; every one tested the
mechanism (queue bounded, coalescing, non-lossy) and none could see the outcome. {#gap}

`answered_by` is five-valued and that is the design, not a convenience:
`index | floor | dropin | stdin | none`. `_index_may_answer(paths)` is `return not paths`, so a
drop-in read that NAMES files can never be served from the learned index (bug-058: a learned index
answered with 1000 rows covering ~100 of a file's 500 matching lines). A boolean would have scored
every correct drop-in read as a learning miss and made the loop look dead where the floor is the
right answer. `floor` — eligible and empty — is the only bucket learning can move, and it is the
denominator every later claim uses. {#taxonomy}

Decided in ONE place (`_floor_answered_by`, beside `_resolve_output_shape`, which exists because
bug-058/059/060 each resolved an output rule per render path). `learn` rides along so a replayed log
says which arm wrote a row without external bookkeeping. {#one-place}

Two paths were writing **no row at all**, so the 1,536 are a partial census of greps rather than all
of them: the stdin filter returns before the store is resolved (by design — a filter must not pay
for an attach) and a daemon-RPC-served grep has no local store, where `__exit__`'s `store is None`
guard dropped the record silently. `log_query` now takes a `root`, and the filter passes the
resolver as a CALLABLE evaluated at exit, after the bytes are out. {#census}

Historical rows are not re-scored: `body` holds the pattern and nothing holds the paths, so
eligibility is unrecoverable. `summarize` reports them `unknown` and never folds them into `floor`.
A grep row whose producer forgot to label itself is written `unset`, loudly. {#no-backfill}

9 tests, RED first. The mutation check found the `index` and `none` labels covered on ONE of the two
read paths — a fresh store holds only `catalog.duckdb`, which `_replica_reader_path` accepts, so
`_grep_run` never ran in any test. `both_read_paths` now parametrizes over both and each mutation
kills exactly one variant. {#tests-141}

## 14.2 — one toggle, six sites {#toggle}

`--learn/--no-learn` governs one invocation, which cannot turn the loop off: the daemon drains the
queue on a tick in a process started days earlier, and the rewrite hook spawns `rmx grep` itself.
`learn_switch.decision(root)` resolves env `RMX_LEARN` → per-store `learn.off` → `~/.refmatrix/
learn.off` → ON, and names the rule that decided. {#resolver}

A marker FILE, not a catalog key: the rewrite hook answers this on every bare grep in every session
and a CLI with a dead daemon has no reader at all. `learn_switch` imports only os/dataclasses/
pathlib, asserted over its AST. {#marker}

Six sites honour it, and the sixth (`_op_context`'s own `_learn_grep_hits` call) was found by
sweeping callers, not by any finding. Nothing silent, nothing lost: the skipped drain KEEPS the
queue and logs its depth; a malformed `RMX_LEARN=banana` decides nothing and the rejected text
travels on the Decision so `rmx learn status` shows the typo; an EXPLICIT `--learn` the toggle
refuses says so once on stderr while a default-on call silenced by the operator's own marker stays
quiet. {#sites}

14 + 17 tests. The mutation check found three survivors: the broker and backstop guards are
deliberately redundant, so killing either alone left the backstop test green, and `_op_context`'s
guard had no test at all. Each layer now has a test that fails when only that layer breaks — and the
new `_op_context` test ITSELF passed with the guard deleted until both refs were made present in the
corpus. {#tests-142}

## 14.3 — the hook follows the toggle {#hook}

Toggle OFF ⇒ the PreToolUse rewriter emits no rewrite and `bin/rmxgrep` execs the real tool, so the
measurement's OFF arm measures no routing AND no learning (user decision 2026-10-05). Neither
artifact can import the resolver — the rewriter runs under the system `python3`, the wrapper is POSIX
shell — so `render_scripts` interpolates `ENV_VAR`, `MARKER_NAME` and both value sets out of
`learn_switch`, and tests assert the rendered script carries exactly those constants. The check is an
env read and two file tests: no subprocess, no import, asserted by reading the generated script
rather than by timing it. 11 tests, RED with the implementation stashed. {#hook-body}

**Not applied.** `rmx install-hooks --check` reports drift on `rmxgrep-rewrite.py` because the
generated script changed. Applying rewrites `~/.claude/hooks` for every session on this machine, so
it waits for the user. bug-066 (the installed rewriter resolving a STALE wrapper copy) is NOT
absorbed here and the test file says so. {#not-applied}

## bug-067 — the instrument's first finding {#bug-067}

The harness said the loop moved almost nothing, and the cause was a defect rather than a verdict.
`add_concept` writes the canonical underscore row PLUS space/dash ALIAS rows as separate entities;
`_learn_grep_hits` attaches all evidence to the canonical id; the read matched `c.name` and JOINed
evidence. So `query/roaring bitmap` existed with **0** evidence rows while `query/roaring_bitmap`
held all 10, and the next identical grep fell to the floor forever. {#mechanism}

My first causal story — "normalization drops the literal" — was WRONG, and direct SQL corrected it:
the literal row exists, it is just empty. `feedback_causal_story_before_evidence`, caught by
measuring instead of by re-reading my own reasoning. {#correction}

The fix is the read consulting `canonical_name`, the same resolution `resolve_concept_ids` already
used for query/context/neighbors — `identifier.py` says it is "used at the query INPUT boundary" and
grep was the boundary nobody wired. The SQL was in THREE already-divergent copies (daemon
`regexp_matches`, CLI direct and CLI replica `~`); all three now delegate to `Store.grep_evidence`.
{#fix}

| measure | before | after |
|---|---|---|
| taught and reachable on the immediate repeat | 24/76 (31.6%) | **49/60 (81.7%)** |
| multi-word patterns | 0/18 | **14/15** |
| answered from the index on the FIRST call | 29/121 | **43/122** |

The third row is a side effect worth naming: the canonical predicate also reaches ingest-time
concepts, so 14 more patterns are answered from the index before any learning happens. 11 patterns
remain stuck, 10 of them regexes where the learned name is the literal regex text — recorded as a
limitation, not the same defect. {#numbers}

## What is NOT claimed {#not-claimed}

- The eligible SHARE of live traffic. Historical rows hold no paths, so only forward `answered_by`
  data can say what fraction of real greps the index was ever allowed to answer.
- The daemon's flush TICK. The harness calls the real `_drain_learn_queue` directly rather than
  running throwaway daemons, which would register throwaway stores with the machine's hub.
- Any end-to-end retrieval-quality claim. The two-arm sequential replay over the full workload is
  task 14.4 and its report is `docs/measurements/grep-learning-replay.md`.
