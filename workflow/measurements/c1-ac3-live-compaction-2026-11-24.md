---
gmd: "0.1"
id: c1-ac3-live-compaction-2026-11-24
title: "C1 AC-3: a live auto-compaction on 0.85.0 code — one-step summary, pointer, read gate, pull telemetry"
tags: [measurement, compaction, handoff, c1, ac-3, release-0.85.0]
metadata:
  node_type: measurement
  created: 2026-11-24
---

# C1 AC-3 live compaction record (2026-11-24) {#root}

rel: evidence-for -> [[task-compaction-as-handoff#acceptance]]

The lead's session `8adeba5c` auto-compacted at 2026-11-24 04:12 local (12:12Z), right after the
deploy tree was fast-forwarded to the 0.85.0 release commit `0a9896eb`. The hooks were this repo's
`.claude/settings.json` (already the C1 render since GREEN) running the deployed `rmx` (editable
install, so 0.85.0 code); the dev-tree daemon was still the 0.84.0 process (relaunched minutes
later). This is a real session, not a sandbox: it stands in for AC-3's probe, recorded as shapes and
hashes, never raw text. {#context}

## Compaction records (from the session transcript) {#records}

| # | when (UTC) | trigger | preTokens | postTokens | durationMs | summary chars | summary lines | summary sha256[:16] | hooks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-19 00:19 | auto | 804,345 | — | 61,648 | 13,521 | 169 | `43ae7fc4dac81717` | pre-C1 |
| 2 | 2026-11-24 02:09 | auto | 790,726 | 29,381 | 65,749 | 18,003 | 238 | `ba16b7c6e5b7b99a` | pre-C1 |
| 3 | 2026-11-24 12:12 | auto | 724,554 | 25,692 | 6,535 | 1,888 | 18 | `9382c8f92b641478` | **C1** |

{#records-table}

The C1 summary is 18 lines including Claude Code's fixed wrapper (the "session continued" preamble
and the transcript-path line); the model-written part is one task line plus a four-item step list
and "the handoff file is authoritative". R2 asked for one line; the summariser kept the next steps
as a list. AC-3's bar ("at most a few lines") is met; R2's single line is not met to the letter.
Summary size fell 7-10x and compaction time ~10x against the session's two pre-C1 compactions. {#summary-reading}

## Handoff ledger (`.refmatrix/handoffs/ledger.jsonl`) {#ledger}

| event | ts (local) | detail |
|---|---|---|
| precompact | 04:12:47 | `saved: true`, `commit_deferred: false`, `deferred_by_bound: false` |
| write | 04:12:53 | source `compact`, 58,110 B |
| pull | 04:12:56 | 58,110 B, 2.746 s from the write to the Read |

The pulled marker was written (`<session>.pulled`). The agent's first action after compaction was
the Read of the named file, so the gate's deny path was not exercised live (AC-5's tests cover it).
The file exceeded the Read tool's 25k-token page and took two reads; the gate lifted on the first
(`#rr-read`). Most of the overflow is junk git milestones, bug-233 (now recurring, Seen 2). Reading
the file also loaded `.refmatrix/CLAUDE.md`, whose 0.85.0 briefing carries the R3b rule line. {#ledger-reading}

## Not yet observed {#open}

- R6's goal line: no `/goal` was set in this session (`active goal: none` in the file's header).
  The `/goal` clear and completed-goal record shapes are still to be read live (`#rr-goal`).
- The `clear` trigger and the deny-then-allow sequence, live.
