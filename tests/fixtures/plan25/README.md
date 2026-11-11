---
gmd: "0.1"
id: plan25-fixture-readme
title: "Plan-25 task 25.1 frozen fixture: synthetic memories, global rows and prompts"
tags: [fixture, plan-25, task-25.1, bug-164, tests]
---

# Plan-25 task 25.1 frozen fixture {#root}

rel: part-of -> [[task-25.1-recall-hook-byte-budget]]
rel: derives-from -> [[task-25.1-recall-hook-byte-budget#why]]

Synthetic text only: no real prompt, query log, STM ring or memory body is copied here
(`feedback_no_raw_prompts_in_public_repo`). Regenerate with
`python3 tests/fixtures/plan25/make_fixture.py`; the tests read the committed files, and
`tests/task25_1_support.py` copies `memory/` into a sandbox memdir and brings it in through the
real bridge (`rmx ingest-gmd --as-memory`). {#lead}

## What it reproduces {#reproduces}

The 21.1 byte counts quoted in the task spec ([[task-25.1-recall-hook-byte-budget#why]]):
cliquedb's per-prompt recall bodies measured 2.0-8.7 KB, so the 30 memory bodies step linearly
from 2,000 to 8,700 B (on disk 2,259-8,942 B with frontmatter). Every curated hook and every body
carries at least 4 of `—` / `→` (3 UTF-8 bytes, 1 character each), the multibyte density AC-2
and AC-10 require. {#sizes}

## Contents {#contents}

- `memory/fx_mem_00..29.md`: 30 GMD memories (`project` / `feedback` / `reference`), each with a
  curated hook in `memory/MEMORY.md` that differs from its first sentence (`HOOK-<name> …` vs
  `First sentence of <name> …`) and a `BODYMARK <name>` paragraph that marks a printed body.
- `memory/fx_dup_x.md`: the project row of a name the global store also holds (AC-11).
- `memory/savestates/savestate_fx01.md`: a hand-authored save-state mis-typed
  `metadata.type: project`, placed where 26.3 puts save-states, whose body repeats the question
  prompt (AC-5).
- `global/memories.json`: 10 global memories plus the global `fx_dup_x`; each body holds the
  question verbatim because the global leg is a substring search.
- `prompts.json`: the question, a bare ack and a symbol-only prompt.

Seeded by the support module rather than committed: 5 subject rows (one with
`metadata.stale = true` + `stale_since`) through the daemon `memory_add` op, an STM ring sized
so `rmx focus context --top 15` prints > 3,000 B, a curator spool of 30 paths > 120 chars, and a
docs + code corpus for scan-prompt. {#seeded}
