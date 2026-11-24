---
gmd: "0.1"
id: impl-task-compaction-as-handoff
title: "C1 GREEN: compaction and /clear as a handoff (PreCompact saves then instructs; compact|clear pull a file; read gate; active goal)"
tags: [implementation-summary, c1, hooks, compaction, handoff, save-state, recall-state, telemetry]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-23
---

# C1 GREEN: compaction and /clear as a handoff {#root}

rel: implements -> [[task-compaction-as-handoff#r1]]
rel: implements -> [[task-compaction-as-handoff#r2]]
rel: implements -> [[task-compaction-as-handoff#r3]]
rel: implements -> [[task-compaction-as-handoff#r3b]]
rel: implements -> [[task-compaction-as-handoff#r4]]
rel: implements -> [[task-compaction-as-handoff#r5]]
rel: implements -> [[task-compaction-as-handoff#r6]]

Queue row C1 (L195), large change under L165. Branch `task-compaction-as-handoff` in
`/Volumes/littlebig/refmatrix-cah-green`, cut from the RED tip `f6c1ae68` (red-cah). GREEN wrote
`src/`, the generated docs and the regenerated `.claude/settings.json` only; no test was written
or edited. The lead's rulings L200 (`#red-rulings` on master) are followed as written. The
version is not bumped (lead's instruction).

## What changed {#changes}

- **`handoff.py`** (the new section at the end, plus three small edits):
  - R6: `read_active_goal(transcript)` returns the newest `/goal <text>` not followed by a
    clearing `/goal` (`clear stop off reset none cancel`). It counts only `type: user` records
    whose string content is exactly the probed command form. A bare `/goal` does not clear. A
    file that cannot be read, or holds no JSON, is `unknown` with a one-line note; a tag line
    that is not JSON is counted and said.
  - The save-state renders the result as `## Active goal {#active-goal}`
    (`- goal: /goal <verbatim>`, `- set: <UTC second>`). `parse_active_goal_block` reads it
    back from the whole file, not the 1,800-char excerpt. recall-state renders it as its own
    block, second after the head. `compose_save_state(transcript=)`: without a transcript it uses
    `~/.claude/projects/<slug>/<session>.jsonl` when that exists
    (`session_transcript_path`), so `/save-state` then `/clear` keeps the goal too.
  - R3: `write_pulled_handoff` writes `<store>/handoffs/<session>.txt` atomically (temp file,
    then `os.replace`) and arms `<session>.gate`. `handoff_pointer` is the pointer: at most
    1,024 B, with the path, the byte count, "before any other action", "authoritative" and the
    R6 goal lines, the goal clipped there if it is too long. `handoff_fallback` is the
    "could not be written" line plus 25.1's budgeted report.
  - R3b: `gate_status`, `gate_decision`, `record_pull` (offset ≤ 1, ruling L200) and
    `remind_line`. A missing, unreadable or older-than-24 h file stands the gate down once,
    with one line. Events go to `<store>/handoffs/ledger.jsonl` (renamed in the fold), and `handoff_events` reads
    them for telemetry.
  - R1/R2: `precompact_instruction` is two lines, at most 1,000 B. It names the save-state just
    written, or else the last good one, plus the handoff file.
- **`cli.py`**:
  - `save-state --precompact` (`_precompact_hook`) takes the session and the transcript from the
    envelope, so SessionUnresolved is gone. It saves with promote, sends progress and failures
    to stderr, prints only the instruction, and always exits 0. A manual `/compact <text>`
    saves and prints nothing.
  - `save-state --transcript` is the verb's new `transcript` parameter (parity).
  - `recall-state --handoff` (`_recall_state_handoff`): the file holds exactly what
    `rmx recall-state --session S` prints. A report that cannot be built is one `Error:` line,
    exit 1 (AC-15 e/h).
  - New group `rmx handoff`: `gate` (a JSON deny at exit 0 since the fold; a stand-down is one
    `systemMessage` line), `pulled`, `remind`, and `precompact` (the checkpoint-off entry).
  - The text form of `telemetry --context` gains one `handoff:` line.
- **`verbs.py`**: `save_state(transcript=None)`.
- **`telemetry.py`**: `summarize_context` returns `handoff: {written, pulls, stand_downs,
  unreadable_lines}`.
- **`hooks.py`**:
  - PreCompact is ONE command: `rmx save-state --precompact --no-sync -m "auto: pre-compact
    checkpoint"`, or `rmx handoff precompact` with the checkpoint off. The `focus summarize
    --promote` and `memory recall --recent` entries are gone.
  - The compact|clear entry is `rmx recall-state --handoff --max-bytes 9000`.
  - New entries: PreToolUse with no matcher (every tool, MCP included), PostToolUse(`Read`) and
    UserPromptSubmit.
  - Each new entry runs `_handoff_cmd`, a bash fast path. It reads the envelope's session id and
    exits 0 unless `<store>/handoffs/<session>.gate` exists; the `Read` hook checks for any
    `*.gate`. Measured on a fixture: about 5 ms per call against about 220 ms for a Python
    start.
  - The briefing (`CLAUDE_BRIEFING`) gains the one rule line (ruling L200).
- **Generated:** the README hooks table and the ARCHITECTURE CLI tree
  (`scripts/gen-cli-tree.py`). `.claude/settings.json` was re-rendered for the dev-tree path
  through `hooks.render_managed`, not `install-hooks --apply`. It had also been one generation
  stale (Stop promote `--timeout 5`, the generator says 8). `docs/INTEGRATION.md`
  `#compaction-handoff` is new.

## Contracts bent or read {#contracts}

- **The stand-down line** is printed as Claude Code's `systemMessage` JSON (one line, shown to
  the user), not as a permission decision. An `allow` decision would bypass the user's
  permission prompts.
- **The pointer's goal line comes from the save-state the handoff names** (the newest), on
  `compact` as on `clear`. PreCompact has just written that save-state from the same
  transcript, so the transcript is not parsed a second time, and the file and the pointer
  cannot disagree.
- **checkpoint off** cannot share PreCompact's command, because `test_hooks_reproducible`
  forbids "save-state" in it. Both entries call the same `_precompact_hook`.

## The L202 fold: bsd-cah r1 on `cbbe9e3f` {#fold}

rel: derives-from -> [[bsd-cah-r1-cbbe9e3f]]

The fold RED is `feeb18bf` plus `54b34efe` (red-cah). `9da7e1b0` was amended into `54b34efe`,
and the branch was fast-forwarded to it. Fold GREEN is `8daaa0aa`, then `03ffb385` for L204.
RED's L204 test commit `3b08a897` was cherry-picked as `a5fea141`, and GREEN `4784cdd5` adds
`precompact_deferred`.

- **b-1 / b-2 (bug-307), subagents.** `handoff.is_subagent` is true when `agent_id` is in the
  envelope; a subagent's input carries the lead's `session_id`. Such a call:
  - is allowed by `gate_decision`;
  - has its Read ignored by `record_pull`;
  - gets no reminder;
  - writes no handoff file and arms nothing through `recall-state --handoff`, saying so on
    stderr;
  - saves nothing and prints nothing at PreCompact, so Claude Code's own summary stands.
- **b-3 (bug-308), the gate trap.**
  - `record_pull` lifts the gate before it writes the marker. A gate that cannot be lifted
    stands down.
  - `gate_status` stands down when `handoffs/` is not writable. The stand-down is remembered
    beside the dir (`.handoff-stood-down.<session>`), so its one line is said once.
- **s-1, the deny channel.**
  - A deny is `hookSpecificOutput.permissionDecision: deny` at exit 0.
  - The generated wrapper maps exit 2 to 1, so a broken or older `rmx` allows the call,
    loudly.
- **s-2 / L203 / L204, the PreCompact bound.**
  - `save-state --timeout N` is the verb parameter `timeout`.
  - The order is fixed: the file, then the index, then the store commit (promote), then the
    lint, then the subject filing. The last three share the time left before the deadline,
    one attempt each (filing `retries=0`).
  - An overrun prints the stderr line "the store commit was deferred: … <file> is on disk and
    is the durable record …" and exits 0, still printing the instruction.
  - `hooks.PRECOMPACT_SAVE_TIMEOUT_S = 10` (the user, L204); the entry's Claude Code
    `timeout` is 40.
  - **L204 telemetry:** every PreCompact save writes a `precompact` ledger row.
    `telemetry --context` reports:
    - `handoff.precompact = {saves, save_failures, commits_deferred,
      commits_deferred_by_bound}`, plus the text line;
    - `handoff.precompact_deferred`, one `{ts, session, cause}` row per store commit deferred
      by the bound.
    red-cah's `3b08a897` (cherry-picked as `a5fea141`) pins `precompact_deferred` inside the
    overrun test.
- **m-1:** `REFMATRIX_ROOT='<baked root>'` is set on the `rmx handoff` command in the wrapper,
  so Python decides on the store the shell tested.
- **m-2:** the `install-hooks --precompact-checkpoint` help names the current command.
- **m-3:** each handoff write reaps:
  - unread gates past 24 h (recorded as stand-downs);
  - handoff files older than 7 days, with their markers;
  - ledger rows older than 7 days.

  The reaps are recorded as a `reap` row. The file's mtime is set on the handoff clock;
  `RMX_HANDOFF_NOW` is the test knob.
- **m-4:** the `precompact` budget channel, its `precompact_recall_cmd` and its producer are
  retired. A `--recent --pack` now takes the `session_start` budget. The 21.1 recall-event
  label `precompact` stays. `handoff_remind` (512 B) is the reminder's channel, and the
  reminder clips itself to it.
- **Verify-set defects found at `cbbe9e3f`:**
  - The ledger is `handoffs/ledger.jsonl`; 21.1 AC-9 reserves the `*events.jsonl` names.
  - The four `rmx handoff` paths are classified in `verbs.INTERNAL_CLI` with the reason
    ruled in L204. red-cah adds them to `_INTERNAL_SEED`.
  - `handoff_remind` sits before `recall_state` in both budget tables, because the 25.1 m-a
    fixture anchors on `recall_state` being last.

## L203 / L204: the PreCompact save timing {#l203}

Measured on a throwaway copy of the dev store (`/private/tmp/claude-501/cm.ubFU`): the
read-snapshot catalog, this session's 3,359-event ring, the 341-file memory dir, a 20 MB
transcript and a real test daemon, with `src` snapshotted at `cbbe9e3f`.

Step times, ms, as p50 / p95 / max (n = 20):

| step | idle | busy writer |
|---|---|---|
| savestate file write | 0.2 / 0.3 / 0.3 | 0.2 / 0.3 / 0.3 |
| MEMORY.md index | 106 / 112 / 112 | 106 / 114 / 114 |
| store commit (promote) | 366 / 511 / 511 | 360 / 9,193 / 9,193 |
| subject filing | 14 / 30 / 30 | 14 / 1,290 / 1,290 |
| lint | 47 / 58 / 58 | 40 / 49 / 49 |

Other measurements:
- The 18 historical PreCompact promotes (live `cli.log`) all finished in under 0.6 s.
- The exact hook command under CPU load: p99 1.45 s.
- A promote that timed out at 2 s against a 4-minute sync still landed once the writer
  freed.

The user set X = 10 s (L204). The Stop hook's own 5 s promote contention is bug-309, out of
scope here.

## Runs {#runs}

Every run went through `scripts/lane-local.sh` on a committed sha. Logs are in
`workflow/review-output/`. The lane runs `-q -q`, so a log has no count line; the counts below
are the progress characters.

| run | sha | files | result |
|---|---|---|---|
| `cah-green-r1` | `e671f36c` | test_compaction_handoff | exit 0, 34/34 |
| `cah-green-verifyA` / `B` | `cbbe9e3f` | 185 (verify set) | exit 1: 1542 passed, 1 failed, 1 skipped / 1709 passed, 3 failed. The defects (21.1 AC-9 ledger name, verb parity, ac12) were fixed in the fold |
| `cah-mut-gate-removed` | `2c98c9fb9d` (mutant) | test_compaction_handoff | 5 failed (the mutation is caught) |
| `cah-mut-inline-handoff` | `38cc7c0146` (mutant) | test_compaction_handoff | 27 failed |
| `cah-mut-goal-line-dropped` | `15413d09b7` (mutant) | test_compaction_handoff | 3 failed |
| `cah-fold-r1` | `8daaa0aa` | test_compaction_handoff, 25.1, plan2_remedy, verb_parity | exit 1: 381 passed, 2 failed (the INTERNAL_CLI seed, pending RED; the 25.1 m-a table anchor, fixed in `03ffb385`) |
| `cah-fold-r2` | `4784cdd5` | test_compaction_handoff, test_verb_parity | exit 0, 216 passed |
| `cah-fold-verify2A` / `B` | `4784cdd5` | 186 | A: exit 1, 1802 passed, 2 failed, 1 skipped (21.1 AC-7: a comment named the recall sink, fixed in `a1e4a6a0`; ac4d replica-on: the same E line at master `749608ce`, see `cah-ac4d-master` / `cah-ac4d-branch`). B: exit 0, 1474 passed |
| `cah-l208-red` | `36335b1f` | the 4 new L208 tests | exit 1: all 4 red for the intended reason (shown failing first) |
| **`cah-final-verifyA`** | **`76b6cf5e`** (master `3e4d3b51` merged) | 95 | **exit 0**, 1864 passed |
| **`cah-final-verifyB`** | **`76b6cf5e`** | 95 | **exit 0**, 1458 passed, 1 skipped (the foreign-checkout pin) |

ac4d `[replica-on]` failed at master and at the branch at 00:47 and passed in the final batch at
00:48–01:12. It is intermittent, not caused by this branch; the lead logs it.

The final verify set is 190 files, built on the merged tree:
- the task files and the 9 guards;
- every test importing `hooks`, `handoff`, `search_hooks`, `telemetry`, `verbs`, `hook_budget`
  or `cli`;
- every `tests/test_mcp*.py`.

Batch A:

```
tests/test_agent_env.py
tests/test_bridge_move_safety.py
tests/test_brief_real_daemon.py
tests/test_bsd_r1_telemetry_eval.py
tests/test_bug015_wedge.py
tests/test_bug112_duckdb_reopen.py
tests/test_bug118_optional_hook_exit.py
tests/test_bug178_r2.py
tests/test_bug198_brief_compile_scope.py
tests/test_bug212_r1_remedy.py
tests/test_bug212_r4_red.py
tests/test_bug212_r7_red.py
tests/test_bug216_remedy_l86.py
tests/test_bug216_remedy_r2.py
tests/test_bug216_remedy_r5.py
tests/test_bug216_rule_docs_e2e.py
tests/test_bug225_handoff_trunk.py
tests/test_bug241_r3_l114.py
tests/test_cli_store_rotation.py
tests/test_compaction_handoff.py
tests/test_concept_timeline.py
tests/test_context_rerank_warning.py
tests/test_deferrals_clean.py
tests/test_derive_stamp.py
tests/test_derive_unstamp.py
tests/test_docs_generated.py
tests/test_embed_phases_r10.py
tests/test_fork_safety_reexec.py
tests/test_fragment_repair_audit_r3.py
tests/test_global_memory.py
tests/test_grep_argv_order.py
tests/test_grep_case_every_path.py
tests/test_grep_dropin_contract.py
tests/test_grep_fixed_and_file_lists.py
tests/test_grep_learned_paths_absolute.py
tests/test_grep_no_flag_bundle.py
tests/test_grep_stdin_dialect.py
tests/test_hook_wiring.py
tests/test_hooks.py
tests/test_injection_capture.py
tests/test_lance_drop_failures_loud.py
tests/test_learn_switch.py
tests/test_learn_toggle_sites.py
tests/test_mcp_bus_passthrough.py
tests/test_mcp_memory_recall_routing.py
tests/test_mcp_session_pointer.py
tests/test_mcp_write.py
tests/test_memory_compile_remedy_r1.py
tests/test_memory_index.py
tests/test_memory_recall_exclude_mtype.py
tests/test_memory_recall_widen.py
tests/test_mock_registry_coverage.py
tests/test_plan1_remedy.py
tests/test_plan2_remedy_r6.py
tests/test_plan2_remedy.py
tests/test_plan3_remedy_r3.py
tests/test_plan3_remedy_r5.py
tests/test_plan3_remedy_r7.py
tests/test_plan4_remedy_r2.py
tests/test_plan4_remedy.py
tests/test_plan7_10_remedy_r4.py
tests/test_refine_cli.py
tests/test_repair_entities.py
tests/test_rerank_degrades_are_surfaced.py
tests/test_rewriter_wrapper_resolution.py
tests/test_sandbox_redirect.py
tests/test_save_state.py
tests/test_savestate_subfolder.py
tests/test_scanorder_r2_l120.py
tests/test_session_cli.py
tests/test_session_raw_link.py
tests/test_stm_rationale_capture.py
tests/test_subject.py
tests/test_suite_runs_from_any_checkout.py
tests/test_sync_fails_loudly_r1.py
tests/test_t0_skip_gate.py
tests/test_task21_1_agent_usage_report.py
tests/test_task21_1_mcp_route.py
tests/test_task21_1_pointer_surfacing.py
tests/test_task21_1_recall_skip.py
tests/test_task25_1_recall_budget.py
tests/test_task3_6_r9_remedy.py
tests/test_task3_7_curation.py
tests/test_task3_7_focus.py
tests/test_task3_7_graph.py
tests/test_task3_7_live.py
tests/test_task3_7_refine.py
tests/test_task3_7_remedy_r2_meh.py
tests/test_task3_7_session.py
tests/test_task4_5_r4_remedy.py
tests/test_telemetry_adoption.py
tests/test_telemetry_outcomes.py
tests/test_untrack.py
tests/test_verb_parity.py
tests/test_verbs_migrated.py
```

Batch B:

```
tests/test_bridge_move_safety_r1.py
tests/test_brief_bsd_r1.py
tests/test_brief_surfaces.py
tests/test_budget_outcome_census.py
tests/test_bug111_repair_dead_concept_links.py
tests/test_bug115_liveness_under_load.py
tests/test_bug162_163_worker_qos_hook_path.py
tests/test_bug197_unknown_compile_scope.py
tests/test_bug212_hooks_in_worktrees.py
tests/test_bug212_r2_red.py
tests/test_bug212_r6_red.py
tests/test_bug216_hidden_no_pollution.py
tests/test_bug216_remedy_r1.py
tests/test_bug216_remedy_r4.py
tests/test_bug216_rev4.py
tests/test_bug216_surfaces.py
tests/test_bug240_ingest_file_arg_mcp.py
tests/test_bug267_inprocess_stop.py
tests/test_cli_time_phases.py
tests/test_composite.py
tests/test_context_cost.py
tests/test_daemon_restart_cli.py
tests/test_derive_coverage.py
tests/test_derive_surface.py
tests/test_describe.py
tests/test_embed_partition_routing.py
tests/test_fingerprint.py
tests/test_fragment_partition_scope.py
tests/test_fragment_repair_audit_r4.py
tests/test_grep_answered_by.py
tests/test_grep_backstop.py
tests/test_grep_delegate.py
tests/test_grep_empty_pipe.py
tests/test_grep_flags.py
tests/test_grep_learned_reachable.py
tests/test_grep_output_shape.py
tests/test_grep_verify_before_cap.py
tests/test_hooks_reproducible.py
tests/test_hybrid_recall.py
tests/test_install_commands_user_level.py
tests/test_learn_broker_bounded.py
tests/test_learn_toggle_hook.py
tests/test_locate.py
tests/test_mcp_channels.py
tests/test_mcp_parity.py
tests/test_mcp_tools.py
tests/test_memory_bridge.py
tests/test_memory_compile_scope.py
tests/test_memory_recall_degree.py
tests/test_memory_recall_score.py
tests/test_memory.py
tests/test_partition_audit.py
tests/test_plan12_remedy.py
tests/test_plan2_remedy_r7.py
tests/test_plan3_remedy_r2.py
tests/test_plan3_remedy_r4.py
tests/test_plan3_remedy_r6.py
tests/test_plan3_remedy.py
tests/test_plan4_remedy_r3.py
tests/test_plan5_remedy.py
tests/test_read_surface_grammar.py
tests/test_reingest.py
tests/test_repo_hooks_in_sync.py
tests/test_rerank_warning_routes.py
tests/test_runtime_identity_surface.py
tests/test_save_state_embeds_memories.py
tests/test_savestate_mtype.py
tests/test_scan_prompt_block_order.py
tests/test_search_hooks.py
tests/test_session_launchctl.py
tests/test_shared_worker_readoption.py
tests/test_stm_tool_detail.py
tests/test_suite_discipline.py
tests/test_sync_and_extras.py
tests/test_sync_fails_loudly_r2.py
tests/test_task_cli_session.py
tests/test_task21_1_emitters.py
tests/test_task21_1_pointer_lifecycle.py
tests/test_task21_1_query_rows.py
tests/test_task21_1_used_events.py
tests/test_task3_5_r8_remedy.py
tests/test_task3_7_canon.py
tests/test_task3_7_curator.py
tests/test_task3_7_folded.py
tests/test_task3_7_infra.py
tests/test_task3_7_matrix.py
tests/test_task3_7_remedy_r1.py
tests/test_task3_7_remedy_r3.py
tests/test_task3_7_taxonomy.py
tests/test_task4_6_r5_remedy.py
tests/test_telemetry_invocation.py
tests/test_tmp_root_census.py
tests/test_v2_features.py
tests/test_verbs_memory_recall.py
tests/test_wallclock_census.py
```

Also run, outside the lane:
- `rmx install-hooks --apply` then `--check` on a throwaway sandbox project (own HOME):
  `hooks in sync`, exit 0.
- `scripts/gen-cli-tree.py --check` after the merge: clean.
- `./scripts/lint-gmd.sh`: 0 errors.

The R3 handoff file on the plan25 fixture memdir: 1,928 B. The pointer: 517 B. The PreCompact
instruction: 449 B, 2 lines.

## Self-audit {#self-audit}

```
1 real:     on a throwaway store (sandbox HOME/RMX_HOME): `echo <env> | rmx save-state --precompact
            --no-sync -m …` → 449 B in 2 lines, savestate written; `recall-state --handoff` → a
            517 B pointer, a 1,928 B file; `handoff gate` → a JSON deny at exit 0 for the lead,
            exit 0 for agent_id=a1; `pulled` → `telemetry --context` handoff: 1 written, 1
            pulled. On the live-shaped copy (cm.ubFU): the exact generated PreCompact command,
            20 runs, p50 1,075 ms.
2 wiring:   test_compaction_handoff fires every GENERATED command per event through
            `/bin/bash -c` with the envelope on stdin (h.hook_block, `fire`), plus the
            INSTALLED settings (test_installed_hooks_gate_a_cleared_session_and_check_is_clean).
3 census:   callers of the changed functions: compose_save_state 1 (verbs.save_state, shared by
            CLI and MCP); _latest_savestate 1; recall_state_blocks / fit_recall_state 3 (CLI x2 and
            the verb's `text`); summarize_context 1; hook_producer 1. The PreCompact entries
            (on/off), the compact|clear entry and the 3 handoff hooks are all from
            `_claude_hook_block`. The repo settings.json was re-rendered; README and
            ARCHITECTURE were regenerated.
4 bound:    PreCompact: one deadline (`--timeout 10`) over the promote (one attempt), the lint
            (subprocess timeout = what is left) and the filing (retries=0); git calls 20 s each
            (unchanged). Hook timeout 40. Worst case: ~10.5 s on a held writer, plus git.
            Gate/remind/pulled: file reads only; the bash fast path costs ~5 ms per call.
5 busy:     busy writer → the commit waits ≤ the budget, then is deferred (said; it lands when
            the writer frees, measured); daemon down → in-process local_write (the existing
            path); the gate needs no daemon.
6 guard:    the gate fires on an armed session's non-Read call; reached by the PreToolUse entry
            with no matcher; test_gate_denies_every_tool_but_a_read_of_the_handoff. It stands down
            on missing / unreadable / expired / unwritable state (the test_gate_stands_down_*
            and test_unwritable_handoffs_dir_* tests). Mutation (gate removed) → 5 failures.
7 loud:     forced read-only memdir → exit 0, stderr "rmx save-state --precompact: FAILED:
            save-state could not write … PermissionError …", and the instruction names the last
            good save-state (test_precompact_save_failure_*). Held writer → stderr "the store
            commit was deferred: …" (test_precompact_overrun_*). A handoff write failure → a
            "handoff file could not be written (…)" line plus the inline fallback. An older rmx
            (exit 2) → the wrapper exits 1, loud and allowing.
8 handoff:  AC-3 live probe → the lead at release (#rr-ac3). The fleet install-hooks and the
            CLAUDE.md import → the lead (#rr-claude-md). bug-309 (the Stop promote contention)
            is out of scope.
```

## Not done here {#not-done}

- AC-3, the live auto-compact probe, is the lead's at release (ruling L200 #rr-ac3).
- The RED-side mutations (gate holds, first goal, clear ignored; ruling #rr-mutations) are
  RED's on this tip.
- The fleet `install-hooks --apply`, and the line in this repo's CLAUDE.md if the briefing is not
  imported, are the lead's (ruling #rr-claude-md).
