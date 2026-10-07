---
gmd: "0.1"
id: task-19.1-pack-recall-under-budget
title: "Task 19.1: memory recall packs its hits under a character budget, and the hooks use it"
tags: [task, memory, recall, hooks, budget]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 19.1: pack recall under the budget {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending
> Depends on: — (19.5's threshold probe sets the default; until then 9,500)

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[reference_hook_output_10k_cap]]

## Why {#why}

The three recall hooks emit JSON with full bodies and no size bound:
- SessionStart: `--session-start --k 10 --scope both --json`, `hooks.py:277`; 26,567 B measured.
- Per-prompt: `--stdin-json --k 5 --scope both --json`, `hooks.py:313`; 16,347 B.
- PreCompact: `--recent --since 1h --k 20 --scope both --json`, `hooks.py:340`; up to ~50 KB.

Above ~10k chars Claude Code delivers a ~2 KB preview, so the agent sees about one hit of ten. {#why-body}

## Requirements {#requirements}

1. **R1 `--max-chars N`** on `rmx memory recall` (and the verb): the rendered payload is ≤ N
   **characters**, the unit the harness counts (the bug-045 lesson: chars, not bytes or lines).
   The env `RMX_HOOK_BUDGET_CHARS` supplies the default when the flag is absent and `--pack` is
   given.
2. **R2 `--pack`**, a text format built greedily in rank order:
   - (a) one header line naming the channel, the hit count and the budget;
   - (b) per hit, a line `- <name> — <title> — <hook>  (rmx memory get <name>)`, using the
     curated hook from `.memory_hooks.json` / MEMORY.md when present, else the first sentence;
   - (c) full bodies for the top hits, appended while the remaining budget allows a whole body
     (never a cut body; the hit stays as its hook line);
   - (d) a trailer when anything was left out: `+N more: rmx memory recall "<query>" --k M`.

   Hook lines are emitted for ALL hits before any body, so the budget is spent on reach first.
3. **R3 Hooks.** The generator (`hooks.py`) emits `--pack --max-chars ${RMX_HOOK_BUDGET_CHARS}`
   in place of `--json` on all three recall hooks, and `--k` rises to what packing can carry
   (SessionStart 30, per-prompt 12, PreCompact 30). `rmx install-hooks --check` must equal the
   new generation, and the plan's deploy step re-installs.
4. **R4 Loud overflow.** If even the header plus the first hook line exceeds N, the payload is
   the header plus a one-line error naming N. It is never empty and never over N.
5. **R5 No silent drop.** Every hit is either a hook line, a body, or counted in the trailer's
   `+N more`. The counts add up to the number retrieved.

## Acceptance criteria {#acceptance}

1. For each hook argv on the live corpus (run on a catalog COPY through the CLI, the production
   path), `len(payload) ≤ N` for N ∈ {2000, 5000, 9500}.
2. On 20 recorded prompts (from this session's transcript), the number of DISTINCT memories named
   inside the payload is ≥ 5x the number inside today's first 2 KB preview. That is measured
   against the same retrieval, so only packing differs.
3. R5 holds on every payload: hook lines + bodies + `+N more` = hits retrieved.
4. `rmx install-hooks --check` is clean after `--apply`, and the generated commands contain
   `--pack --max-chars`.
5. Mutations that must FAIL a test:
   - bodies before hook lines;
   - a cut body;
   - a missing trailer count;
   - counting bytes instead of chars (use a fixture with `—`/`→`);
   - the hook generator keeping `--json`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`memory recall`) | `--max-chars`, `--pack`, the packer |
| `src/refmatrix/verbs.py` (`memory_recall`) | `max_chars` / `pack` passthrough so MCP gets the same packing |
| `src/refmatrix/hooks.py` (`:277`, `:313`, `:340`) | `--pack --max-chars`, the raised `--k` |
| `src/refmatrix/memory_index.py` | export the curated-hook lookup (`.memory_hooks.json`) for reuse |

## Test strategy {#test-strategy}

- **RED first:** a test that runs the generated SessionStart argv on a fixture store with 30
  memories (bodies ~2 KB each) and asserts `len(out) ≤ 9500` and that ≥ 20 distinct memory names
  appear. It fails today: JSON, unbounded.
- **Unit tests for the packer:** ordering, whole bodies only, trailer arithmetic, a multibyte
  fixture.
- **Generator test:** the three hook commands contain `--pack --max-chars`.
- **Measurement:** AC-2 is a script under `eval/production/` run on a catalog copy. Its table goes
  into the implementation summary.

## Out of scope {#out-of-scope}

Ranking changes (19.2's usage scores feed the order later). The scan-prompt hook's 2,000-token
budget; 19.5 records it, and changing it is a follow-up.
