---
gmd: "0.1"
id: task-21.2-precise-identifier-context
title: "Task 21.2: rmx context answers an identifier as precisely as grep, plus callers and tests, in a --brief form"
tags: [task, context, agent, identifier]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  updated: 2026-10-14
---

# Task 21.2: precise identifier answers {#root}

> Plan: [plan-21-agent-context-usage](../plan-21-agent-context-usage.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Wave: 3
> Depends on: 21.1 (the `internal` source and the rows that measure the change), 23.0 (sandbox)

rel: part-of -> [[plan-21-agent-context-usage]]
rel: derives-from -> [[exploration-agent-context-usage]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]

## Why {#why}

Exact-identifier lookups are ~55% of the agent's greps. Replaying 9 of them through `rmx context`
(2026-10-07T11:06:35-11:06:52, all on the `context-replica` route) gave 4 hits, 4 partials and
1 miss:
- **The partials:** DEFINED BY named the file **with no line number**.
- **The miss:** `_drop_lance_for_purge`, where only a test was shown.
- **Output friction:**
  - each test listed twice, under two id forms;
  - edge direction that reads inverted (tests listed under CALLS);
  - `[helix]` "last worked … then:" headers on code anchors;
  - JSON 2.4x the text form.

The 9 names and the per-name baseline were recorded nowhere, and "hit" was undefined (bsd #s-12);
"tests" has no linkage in `src/` (bsd #s-11). This revision freezes both. {#why-body}

## The frozen replay set {#frozen-set}

Committed here BEFORE any change (bsd #s-12). A **hit** is: the FIRST DEFINED BY row of
`rmx context <name>` equals the gold `path:line`. Gold is the line of the `def` / `class` /
module-level assignment of `<name>` in the gold FILE, resolved by Python's `ast` on the file at the
commit under test (so line drift in unrelated edits does not move the target). The gold files are
frozen; the lines below are at HEAD `b1c4324`, for reference.

| # | name | gold file | line at `b1c4324` |
|---|---|---|---|
| 1 | `_op_context` | `src/refmatrix/daemon.py` | 4687 |
| 2 | `_apply_rerank_safe` | `src/refmatrix/daemon.py` | 5855 |
| 3 | `installed_flags` | `src/refmatrix/launchctl.py` | 694 |
| 4 | `shared_reranker` | `src/refmatrix/reranker.py` | 607 |
| 5 | `_drop_lance_for_purge` | `src/refmatrix/store.py` | 3607 (a method of `Store`) |
| 6 | `session_launchctl_install` | `src/refmatrix/cli.py` | 13950 |
| 7 | `_MIN_RERANK_CHARS` | `src/refmatrix/context.py` | 463 |
| 8 | `_should_via_replica` | `src/refmatrix/cli.py` | 557 |
| 9 | `test_run_watcher_picks_up_new_file` | `tests/test_watch.py` | 64 |

{#frozen-set-body}

## Requirements {#requirements}

1. **R1 `path:line` on definitions.** DEFINED BY rows (`LINKAGE_LABELS`, `context.py:40`) render
   `path:line` from the defining evidence. A row with no line evidence says `(line unknown)`; it
   never drops silently.
2. **R2 One id form.** An entity appears once per group. The duplicate `tests/x.py::f` /
   `tests.x.py.f` forms collapse to the canonical one.
3. **R3 Direction labels that read correctly, and TESTED BY defined** (bsd #s-11). For an anchor X:
   `CALLS` lists what X calls, `CALLED BY` lists X's callers. **TESTED BY is a derived view, not a
   new linkage:** the members of X's `called_by` set for which the named predicate
   `context.is_test_entity(e)` holds, where `is_test_entity` is true when the entity's path,
   relative to the store root, starts with `tests/` or its file name matches `test_*.py` or
   `*_test.py`. Those members are listed under TESTED BY and NOT repeated under CALLED BY. The
   label table and the edge direction are checked against the ingest's emission direction
   (`link(linkage, concept, entity)`), with a test per label. 21.3 R2's "m tests" uses this same
   predicate.
4. **R4 No helix block on code anchors** unless `--helix` is given. Helix stays on concepts and
   memories (its measured use).
5. **R5 `--brief`:** the definition `path:line` + signature line, up to 5 CALLED BY `path:line`, up
   to 5 TESTED BY `path:line`, and nothing else, in ≤ 200 tokens. MCP `rmx_context` gets a
   `brief: true` argument; the daemon op passes it through.
6. **R6 Exact-symbol misses fall to the definition.** When the ref is an exact symbol name with a
   `defines` edge, the defining file:line is the first row, even if content ranking would bury it.
7. **R7 The replay harness** lives at `eval/production/context_identifier/` (runner + the frozen
   set + `REPORT.md`). It runs through the CLI with `RMX_INVOCATION_SOURCE=internal` (d4f), so its
   rows never count as agent usage, on a catalog COPY taken from the replica reader file (the
   documented lock-free read path), never by opening `Store()` on a live `.refmatrix/` (bsd #s-7).

## Acceptance criteria {#acceptance}

1. **Baseline first.** The harness's first run, at the commit that adds it and BEFORE any
   `context.py` change, records each of the 9 names as hit / partial / miss in `REPORT.md`
   (expected near 4 / 4 / 1). The commit order is checked: the baseline commit precedes the first
   commit touching `src/refmatrix/context.py` on the task branch.
2. **≥ 8 of 9 hits** on a catalog copy after the change, by the [[#frozen-set]] definition.
3. **`--brief`** output is ≤ 200 tokens (the project's token counter) on all 9, and each contains
   the gold `path:line`.
4. **No duplicates:** no entity appears twice in any group, across the 9.
5. **Labels and TESTED BY:** on a fixture tree with a known call graph (`a` calls `b`;
   `tests/test_b.py::test_b` calls `b`; `c` calls `a`), `rmx context b` lists `a` under CALLED BY
   only, `test_b` under TESTED BY only, and `rmx context a` lists `b` under CALLS and `c` under
   CALLED BY. One test per label.
6. **Latency recorded and bounded:** the harness records p50/p95 wall time for `--brief` and for the
   full bundle on the 9; `--brief` p95 ≤ full-bundle p95 (it does strictly less work). The numbers
   go in `REPORT.md`; 21.3 R0 measures the hook path separately.
7. **No live writes:** the harness run leaves the live `.refmatrix/query.log` line count unchanged
   and writes only `invocation=internal` rows to the copy.
8. **Mutations that must FAIL a test** (pre-registered):
   - DEFINED BY without the line (AC-2, AC-5);
   - dedupe disabled (AC-4);
   - CALLS / CALLED BY label swap (AC-5);
   - `is_test_entity` replaced by "every caller" (AC-5: `a` appears under TESTED BY);
   - helix on code anchors re-enabled (a renderer test on a code anchor);
   - the harness's `internal` source removed (AC-7).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/context.py` | DEFINED BY line, dedupe, labels, `is_test_entity` + TESTED BY view, helix gate, the brief renderer |
| `src/refmatrix/cli.py`, `verbs.py`, `mcp.py`, `daemon.py` (`_op_context`) | `--brief` / `brief` passthrough |
| `eval/production/context_identifier/` (new) | runner, frozen set, `REPORT.md` |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under 23.0's sandbox; the replay subprocesses get `HOME` = tmp,
  `REFMATRIX_ROOT` = the copy's tmp root and `RMX_HUB_MODELS=0`, and assert the live log line
  counts unchanged.
- **RED:** AC-5's fixture analogue (a small ingested Python tree where `rmx context <fn>` returns
  the file without a line, and a test listed under CALLS) fails at HEAD and the failure is
  recorded before GREEN. AC-1's baseline is the RED record for AC-2.
- The replay is evaluated on a copy, never on the live store.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding or decision | answered at |
|---|---|
| bsd #s-11 (TESTED BY undefined) | R3; AC-5 |
| bsd #s-12 (unfrozen set, undefined hit, no baseline) | [[#frozen-set]]; AC-1, AC-2 |
| bsd #s-13 (21.2 has no latency AC) | AC-6 |
| bsd #s-7 / d1a, d1b (catalog copy, live sockets) | R7; [[#test-strategy]]; AC-7 |
| d4f (harnesses set `internal`) | R7; AC-7 |
| #t4-fixes "frozen replay names", "tested by defined or dropped" | [[#frozen-set]]; R3 |
| MEH m-1..m-7 | none touch 21.2 (m-1, m-2, m-4 → 21.1; m-3, m-5, m-6 → 21.3; m-7 → plan `#decisions`) |
