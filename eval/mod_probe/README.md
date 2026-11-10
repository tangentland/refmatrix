---
gmd: "0.1"
id: eval-mod-probe-readme
title: "Mod probe records for plan-24 — committed copies of the probe sources, summaries and filtered event logs"
tags: [eval, probe, mod, plan-24]
---

# Mod probe records {#root}

Committed copies of the plan-24 mod probes, so the gates that cite them
([[task-24.8-retire-mcp-and-retarget#r1]], 24.4 R5, 24.5 R12, 24.6 R7, 24.7 R4) point at files in
the repo. The working copies live in `workflow/review-output/plan-24-probes/`, which is gitignored.
Copied 2026-10-20 for ch-bsd r3 m3. {#lead}

rel: evidence-for -> [[plan-24-mod-transport#probes]]
rel: evidence-for -> [[plan-24-mod-transport#probes-batch2]]

## What is here {#contents}

- `batch1/`: the first subagent probe: `probe-register.ts` (the mod) and `probe-run2.log` (its
  event log, eight lines: offer, call and service of a mod tool by a subagent under `claude -p`).
- `batch2/batch2-results.md`: the batch-2 write-up (eight probes).
- `batch2/mods/`: every batch-2 probe mod and helper server (`servers.py`, `mcp_pc.py`).
- `batch2/logs/<run>/probe.log`: each run's mod event log, FILTERED: every `session.append` line
  and every line carrying row text was dropped, along with any home path or personal value, and
  the model- or probe-written text fields that remained (`turn.complete … answer=` and
  `agent.spawn … prompt=`) are replaced by `answer_sha256=` / `prompt_sha256=` (the first 16 hex
  digits of the field's sha256), so a line still proves the event fired without carrying its
  text. What is left: event names, `agentId`, session ids, timings, the probe's own state marks
  (`value="MAIN-WAS-HERE"`) and the engine's error messages (`message="… failed: ENOENT …"`),
  which are the facts the write-up cites.
- `batch2/logs/c6|c7/debug-excerpt.log`: the engine debug excerpts for the duplicate-name and
  MCP-collision probes.

## What is not here {#excluded}

The model's run output (`run.out`, `run.err`), debug logs in full, and every transcript-like row:
they hold model text, not probe facts. `batch2/batch2-results.md` is the write-up as written; it
quotes short probe-authored strings (the code words, the injected test lines), never model output
beyond them. Raw prompts and transcripts never go into the public repo.
{#excluded-body}
