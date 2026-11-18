---
gmd: "0.1"
id: agent-brief-iso-t1-step1
title: "Isolated agent brief: T1 step 1 — delete detail pins and duplicate tests"
tags: [agent-brief, isolated, t1, test-hygiene]
metadata:
  node_type: brief
  created: 2026-11-18
---

# T1 step 1: delete detail pins and duplicate tests {#root}

You are an isolated small-fix agent (ruling L174/L176) in your own clone of refmatrix. Read
`CLAUDE.md` `#test-discipline` first. Source: `workflow/measurements/test-suite-audit-2026-11-15.md`
`#delete`. Work only in the files named below. Do not run `rmx` write verbs; you cannot reach the
live stores anyway.

rel: implements -> [[plan-of-plans#queue]]
rel: derives-from -> [[test-suite-audit-2026-11-15#delete]]

## The edits {#edits}

Delete (each is a source-text pin of an implementation detail, or cannot fail):
1. `tests/test_embed_phases_r10.py::test_the_cli_embed_loop_uses_the_verdict`
2. `tests/test_embed_phases_r10.py::test_the_watch_flush_uses_the_sum` (a behaviour test sits beside it)
3. `tests/test_plan4_remedy_r2.py::test_foreground_start_refuses_a_busy_daemon_without_reaping_it`
4. `tests/test_plan7_10_remedy_r4.py::test_this_guard_names_the_mechanism_it_replaces`
5. `tests/test_task3_7_curator.py::test_enqueue_curator_writes_through_the_atomic_spool_writer`

Trim:
6. `tests/test_plan5_remedy.py::test_sync_disk_is_a_thin_alias_of_the_bridge`: drop its
   source-text assertions (audit: lines 218-220), keep the behaviour assertions.
7. `tests/test_task3_6_r9_remedy.py::test_the_outer_first_plant_kills_mutant_q5`: drop the
   `src.count(needle) == 1` source assertion, keep the rest.

Duplicates (delete the first, keep the second):
8. `tests/test_plan2_remedy_r7.py::test_verb_memory_partition_reads_the_replica_under_a_held_writer`
   = `tests/test_plan3_remedy_r4.py::test_memory_partition_reads_the_replica_under_a_held_writer`
9. `tests/test_mcp_memory_recall_routing.py::test_resolve_root_unknown_project_raises`
   = `tests/test_task25_1_recall_budget.py::test_ac4e_r10_resolve_root_unknown_project_raises`

NOT in scope: `tests/test_deferrals_clean.py` (T0.4 rewrites it in parallel; the audit's item 6
waits for that).

## Rules {#rules}

- Before each delete, read the test and name the test that keeps the behaviour (for 1-5, the
  behaviour test beside it or "none: it pinned source text only"). For 8 and 9, read both and
  confirm they assert the same thing; if they do NOT, leave both and say why.
- Remove fixtures, helpers and imports that become unused in the touched files; nothing else.
- If a removed test is named in `workflow/test_mock_registry.md`, update that row.
- Run every touched test file with `~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider
  <files> 2>&1 | tee ../step1.log` (your venv; `PYTHONPATH=src`). Before and after: the
  after-run passes, and the collected count drops by exactly the deleted tests.
- One commit, message `T1 step 1: …` listing each item and its kept twin.

## Report {#report}

In the REPORT.md the prompt names: the commit sha, a table (item, action, kept twin or reason),
the before/after collected counts and pass counts, and anything you left alone and why.
