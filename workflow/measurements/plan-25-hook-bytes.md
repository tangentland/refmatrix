---
gmd: "0.1"
id: plan-25-hook-bytes
title: "Plan 25 hook bytes: every generated hook command on the frozen 25.1 fixture, HEAD vs task 25.1 GREEN, against its byte budget"
tags: [measurement, hooks, budget, plan-25, task-25.1, bug-164]
metadata:
  node_type: measurement
  measured: 2026-11-13
  head: "45d8abf (src = f7c0d39)"
  green: "16ace00"
  fixture: "tests/fixtures/plan25 (build_full: 30 memories + dup + mis-typed save-state, 5 subjects, 10 global rows, 30 long curator paths, a 48-input STM ring)"
---

# Plan 25 hook bytes: HEAD vs task 25.1 GREEN {#root}

rel: evidence-for -> [[task-25.1-recall-hook-byte-budget#fixture]]
rel: depends-on -> [[hook-output-cap-probe]]
rel: part-of -> [[plan-25-cliquedb-field-report]]

The before / after table the task 25.1 spec asks for ([[task-25.1-recall-hook-byte-budget#fixture]]).
It is shared with tasks 25.2 and 25.3, which add their own rows. {#lead}

## How it was measured {#method}

- **GREEN.** Commit `16ace00` in the `refmatrix-plan25-1` clone, 2026-11-13. A scratch probe
  built the RED tests' own fixture with `tests/task25_1_support.build_full`, inside 23.0's
  sandbox. It ran each GENERATED hook command three times through `bash -c`, the way Claude Code
  runs it: the envelope on stdin, a sandbox `HOME`, and real sandbox daemons for the project
  and global stores. The question prompt is used unless a row says otherwise. Each byte count
  is the command's stdout.
  The run log is `workflow/review-output/plan25/25.1-green-b-probe.log`.
- **HEAD.** The single RED run at `45d8abf` (src `f7c0d39`), on the same fixture and the same
  argv. Its numbers are copied from
  [[task-25.1-recall-hook-byte-budget-summary#red-head-bytes]], whose log is
  `workflow/review-output/plan25/25.1-red.log`. HEAD was not re-run three times.
- **Budget.** Each budget comes from `refmatrix.hook_budget`. R0 found outcome (A) on both
  events ([[hook-output-cap-probe#headline]]): Claude Code caps each hook COMMAND at 10,000
  UTF-16 units, so the budget of each command is at most `0.9 × cap` = 9,000 B. A command that
  carries two producers gets the SUM of their channel budgets (`HOOK_COMMAND_CHANNELS`).
  {#method-list}

## The table {#table}

| generated hook command (event) | budget | HEAD | GREEN run 1 / 2 / 3 | within |
|---|---|---|---|---|
| `memory recall --stdin-json` (UserPromptSubmit), question | `prompt_recall` 4,000 | 18,865 | 2,434 / 2,434 / 2,434 | yes |
| `memory recall --stdin-json` (UserPromptSubmit), ack | `prompt_recall` 4,000 | 34,368 | 2,270 / 2,270 / 2,270 | yes |
| `scan_cmd` = scan-prompt `;` curator status (UserPromptSubmit) | 5,000 (4,500 + 500) | 8,545 | 4,640 / 4,640 / 4,640 | yes |
| scan-prompt alone | `scan_prompt` 4,500 | 6,660 | 4,234 / 4,234 / 4,234 | yes |
| `rmx curator status` alone (30 paths over 120 chars) | `curator_status` 500 | 1,885 | 406 / 406 / 406 | yes |
| `focus hook --event input` (UserPromptSubmit) | `focus_input` 256 | not recorded | 0 / 0 / 0 | yes |
| **UserPromptSubmit event sum** (question) | not binding under (A) | 27,410 (8,545 + 18,865; focus input not recorded) | 7,074 / 7,074 / 7,074 | — |
| `sess_cmd` = primer `;` curator status (SessionStart) | 500 | 1,885 | 406 / 406 / 406 | yes |
| `memory recall --session-start` (SessionStart, resume) | `session_start` 9,000 | 10,075 | 8,609 / 8,609 / 8,609 | yes |
| `focus context --top 15` (SessionStart, resume) | `focus_context` 1,500 | 3,300 | 1,477 / 1,467 / 1,457 | yes |
| `recall-state --max-bytes 9000` (SessionStart, compact) | `recall_state` 9,000 | no such entry | 4,699 / 4,700 / 4,700 | yes |
| `memory recall --recent --since 1h` (PreCompact) | `precompact` 9,000 | 67,098 | 8,606 / 8,606 / 8,606 | yes |

{#table-rows}

- **Reach (AC-3).** "Reach" is the set of distinct non-subject, non-session memories in the
  part of the per-prompt payload that the model actually receives. At GREEN that is 11
  memories. At HEAD it was 0, because the model received only a 2 KB preview of a JSON list.
  The 11 are: `fx_dup_x`, `fx_mem_00`, `fx_mem_03`, `fx_mem_10`, `fx_mem_20`, `fx_mem_23`, and
  `gx_mem_5` through `gx_mem_9`. {#reach}
- **The per-prompt payload.** It holds 12 named hits and no trailer, in 2,434 of 4,000 B. That
  is d3's pointer list: 12 hook lines, and no room left for a body. The first named hit is the
  mis-typed `savestate_fx01`. Task 26.4 owns the fix for that, so AC-5 stays RED until 26.4
  merges. {#per-prompt}
- **The SessionStart payload.** It holds 30 named hits, which take up 5,961 B of hook lines.
  That leaves 2,981 B after the header. Three bodies fit in that space, all of them GLOBAL rows:
  `fx_dup_x` at 126 B, and `gx_mem_9` and `gx_mem_8` at 1,214 B each. No project body fits. The
  smallest project body among the 30 hits is `fx_mem_12` at 4,934 B. The fixture's project
  bodies range from 2.0 to 8.7 KB.
  [[task-25.1-recall-hook-byte-budget-summary#lead-judge]] has the AC-9 consequence.
  {#session-start}
- **The rerank setting.** None of the sandbox daemons set `RMX_RERANK`, so every recall leg
  measured above ran with the daemon's default rerank. The recall verb's `warnings` named that
  leg: "recall leg: daemon RPC (the daemon's embedder and rerank default)". {#rerank}

## Not measured here {#not-measured}

- `ingest-gmd --detach` (SessionStart) was not run. It is a one-line job handoff, and running it
  would enqueue a re-ingest on the shared fixture daemon (RED a11).
- The live check after deploy is not a gate. The spec asks for the 21.1 byte distribution to be
  re-read from `recall-events.jsonl` on refmatrix and cliquedb after a week of use. That belongs
  to the lead, after release.
