---
gmd: "0.1"
id: agent-brief-fold-c2
title: "Brief: C2 fold of bsd-c2 r1: g-1 killing test, s-1 validate types + per-entry retry, s-2 D5 row"
tags: [agent-brief, fold, c2, hook-writes, bug-248]
metadata:
  node_type: brief
  created: 2026-11-25
---

# C2 fold (bsd-c2 r1) {#root}

rel: implements -> [[bsd-c2-r1-9afff800]]
rel: part-of -> [[task-hook-writes-queue]]

The fold runs in two hands, in this order, in one clone:
`/Volumes/littlebig/refmatrix-c2-fold`, branch `c2-fold` at `9afff800`. A scratch branch
`bsd-c2-mut-tmp` (`c819b066`) holds ch-bsd's g-1 mutant. Read the report first:
`/Users/tholley/claude_tools/refmatrix/workflow/bullshit/2026-11-25-1120-c2-hook-writes-r1-9afff800.md`
(`#g-1`, `#s-1`, `#s-2`). {#lead}

## Stage 1: RED (ch-test-engineer) {#red}

Extend `tests/test_hook_writes.py` (extend, don't add a file; parametrize variants).

1. **g-1 killing test.** A `.tmp` stamped with `time_ns()` now survives `sweep_stale_tmp` and is
   counted `kept`; an old one is swept. Show the test FAILING on the mutant: check out
   `c819b066`'s `src/refmatrix/hook_writes.py` into the tree, run, then restore it with
   `git checkout -- src/` in its own command. Show it passing at `9afff800`. Record both E lines.
2. **s-1 tests**, which fail at `9afff800`:
   - (a) `validate` refuses wrong value types, one parametrized case each: `updated_at` not a
     number, `tags` not a list of str or null, `metadata` not an object or null, `mtype` not a
     str, `protected` not a bool. Each refused entry goes to `bad/` and is counted `bad`.
   - (b) A drain over one good entry plus one entry that passes `validate` but raises inside
     `add_memory`: the good entry is applied, the bad one moves to `bad/` after its retry fails,
     and facts.log holds exactly ONE `memory_content` event for the good entry over 3 drains.
     If (a) makes every raising entry unreachable through the real queue, use a value
     `add_memory` rejects (find one; ch-bsd found none besides `updated_at`). If none exists,
     say so and drop (b) rather than patching `add_memory`.
   - Everything runs through `hook_writes.enqueue` and `drain` on a throwaway Store under a short
     `mkdtemp()` root. Nothing is patched.
3. Commit, run the file on a lane (`scripts/lane-local.sh /Volumes/littlebig/refmatrix-c2-fold
   <sha> c2-fold-red tests/test_hook_writes.py`) and read the log yourself. Report the E lines.

## Stage 2: GREEN (ch-implementer, separate hand) {#green}

- `hook_writes.validate` gains the type checks. On a partition failure, the drain retries each
  winner in its own transaction, and a repeat failure moves to `bad/` with its reason, counted.
  No bare except; every outcome is counted and loud.
- `workflow/deferral_registry.md` D5 row: add L184's queue-aware reads (`memory get` / `recall`
  read the spool) as not built, pointing at 23.1 queue row 13.
- Mutations on the `src/` change, one at a time, restored in their own command, `__pycache__`
  cleared after the batch: drop each type check; drop the per-entry retry; send a repeat failure
  back to pending instead of `bad/`. Each must fail a test.
- Verify on a lane: `test_hook_writes`, `test_memory_content_log`, `test_save_state`,
  `test_compaction_handoff`, `test_plan2_remedy`, every other importer of `hook_writes`, and the
  repo guards (`test_tmp_root_census`, `test_suite_discipline`, `test_docs_generated`,
  `test_mock_registry_coverage`, `test_deferrals_clean`, `test_wallclock_census`,
  `test_budget_outcome_census`, `test_verb_parity`, `test_bug212_r4_red`). Run
  `./scripts/lint-gmd.sh` too.

## Rules for both {#rules}

Read-only against every live store. Look things up with
`/Users/tholley/claude_tools/refmatrix/scripts/rmx-master` or the read-only MCP tools. Never
`find /`, never export `REFMATRIX_ROOT`, never push, and never touch the dev tree. Every
background wait has a deadline. Report as text: shas, lane logs with counts, E lines, and the
mutation table.
