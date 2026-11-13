---
gmd: "0.1"
id: agent-brief-dd-10r
title: "Brief: dd-10r — how much injected context does the session already hold? (plan-10 reopened as a measurement)"
tags: [agent-brief, dispatch, measurement, plan-10]
---

# Brief: dd-10r — already-held share of injected context {#root}

The user, 2026-11-13: asked whether injected context is deduped against the session's current representation — no.
Task 10.1 (2026-09-15, `workflow/measurements/injection-overlap.md`) stopped plan-10 on
consecutive-call overlap (median 0.000). It never measured injections against what the SESSION
already holds. Measure that, read-only, counts only. Report as text.

rel: related-to -> [[injection-overlap]]
rel: related-to -> [[plan-10-injection-dedup]]
rel: related-to -> [[exploration-handhold-outcome-experiment]]

## Pre-registered (written 2026-11-13 by the lead, before any number) {#prereg}

- **Unit:** one delivered item (`recall-events.jsonl`, `stage = delivered`) on a per-prompt or
  session-boundary channel, in a session with a ring, main loop only for (b).
- **Already held** at delivery time T, any of:
  - (a) **re-delivered**: the same item key (entity id, else name) was delivered earlier in the
    same session (any channel);
  - (b) **already touched**: the item's file (21.5 `item_path` rules, D15 bases) was read, edited or
    named by a main-loop tool call earlier in the session;
  - (c) **in focus**: the item's entity or file is in `focus_view(g, top=30)` of the ring replayed
    to the prompt before T (`stm._apply_turn` replay as `tc-215` did).
- **Primary metric:** share of delivered units already held under (a) ∪ (b) ∪ (c), pooled over both
  corpora, also by BYTES where the event carries a size (report which channels carry one).
- **Bands → action:**
  - ≥ 30%: reopen plan-10 — dedupe injections against the session representation (a "seen at
    turn N" pointer instead of the body).
  - 15-30%: dedupe re-deliveries (a) only, the cheap case.
  - < 15%: stop again; record it.
- **Cost check:** of lbl-215's labelled CAUSED+INFORMED pairs, how many would dedupe have
  suppressed (a used item that was already held). If > 25% of the used pairs, the band's action
  needs the user before it is specified.

## Where and how {#where}

- Corpora: refmatrix (`/Users/tholley/claude_tools/refmatrix`, 2026-10-20..2026-11-13) and cliquedb
  (`/Users/tholley/github/atollogy/bdep/cliquedb`, 2026-11-04..2026-11-11; read-only copy allowed
  by the user 2026-11-13).
- Reuse: `/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/f0521bff-0006-479a-9e0f-6df02d50937e/scratchpad/`
  `a215s/` (proto5 join, D15), `tc/` (`tc.py`, `views.py`: ring replay, main-loop transcript
  paths), `lbl/` (`labels_*.tsv`, `pairs.jsonl`). Python with `-I` (a local `glob.py` shadows
  stdlib in `b215/`); `PYTHONPATH=/Users/tholley/claude_tools/refmatrix/src` with `-P -s` when
  importing `refmatrix.stm`.
- Breakdowns: by channel (scan_prompt, prompt_recall, session_start, context, precompact), by
  criterion (a / b / c and overlaps), by item kind, by corpus; distribution per session; what share
  of (a) is the SAME prompt words repeated (e.g. a repeated term in consecutive prompts).

## Hard rules {#hard-rules}

Read-only. APFS clones (`cp -c`, `cp -cR` for `stm/`) of `<proj>/.refmatrix/{catalog.read.duckdb,
query.log,recall-events.jsonl,stm}` and `~/.refmatrix/recall-events.jsonl` into `mktemp -d
/private/tmp/claude-501/ddXXXX`, `chmod -R a-w`, DuckDB `read_only=True`, deleted after.
Transcripts read in place. Never call `rmx` on a store; never write in `~/refmatrix`,
`~/.refmatrix`, fleet repos, memory dirs or any git repo; no commits. Counts only in the report: no
prompt, command, reply or memory text. Never search from `/`. Working files in the scratchpad under
`dd/`.

## Report {#report}

The primary share pooled and per corpus with its band and action; the breakdowns; the cost check;
limits (ring coverage, event size fields, focus replay fidelity). Provisional: it goes through
ch-bsd before the user decides.
