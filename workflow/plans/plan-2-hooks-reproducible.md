---
gmd: "0.1"
id: plan-2-hooks-reproducible
title: "Hooks are generated: `rmx install-hooks` produces the whole production config and `--check` proves it"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: in-progress
  created: 2026-09-14
  bsd_findings: "#bs-4, #sk-5"
---

# Proposed Plan: Hooks are generated: `rmx install-hooks` produces the whole production config and `--check` proves it {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-2-hooks-reproducible.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-2.1-plan-2-hooks-reproducible]]
rel: specifies -> [[task-2.2-plan-2-hooks-reproducible]]
rel: specifies -> [[task-2.3-plan-2-hooks-reproducible]]

## Context {#context}

BSD #bs-4 / #sk-5: `.claude/settings.local.json` carried four hand-authored hooks nothing generates (`scan-prompt
--composite-every 3`, PreCompact `focus summarize --promote`, PreCompact `rmx save-state … >/dev/null 2>&1 || true`, resume
`focus context --top 15`) and lacked two the template emits. `install-hooks --force` would delete them. The only unattended
save-state caller swallowed the bridge failure and ran a 30 s synchronous bridge at compaction. `install()` has
`memory_hooks/primer/scan_prompt` knobs no CLI flag reaches. The cat-herder template adds enforcement hooks
(`enforce-rmx-grep`, `enforce-test-to-file`, `adr-gate`, p20-0 guardrail compile) that install-hooks knows nothing about.

## Proposed Approach {#proposed-approach}

One generator, one target, one check:
1. `_claude_hook_block()` grows first-class options: `composite_every: int|None`, `precompact_checkpoint: bool` (save-state
   `--no-promote --no-sync`, output NOT swallowed), `stop_promote: bool` (Stop runs `focus summarize --promote`), `resume_focus:
   int|None` (`focus context --top N` on resume), `enforce: bool` (the cat-herder hooks when `.claude/hooks/*.sh` exist).
   Defaults = what this repo runs today. Every memory-path command stays loud.
2. `install-hooks` writes the rmx block to **`.claude/settings.json`** (committed, project scope) and leaves
   `settings.local.json` for per-machine keys; `--scope user` unchanged. Flags `--[no-]memory-hooks --[no-]primer
   --[no-]scan-prompt --[no-]enforce --composite-every N --[no-]precompact-checkpoint`.
3. `install-hooks --check`: render with the flags recorded in `.claude/rmx-hooks.json` (written on apply) and diff against the
   installed file; exit 1 + unified diff on drift. A repo test runs the same comparison in CI.
4. Migrate this repo: `--apply --force` into settings.json, strip the rmx block from settings.local.json, `--check` clean.

## Open Questions {#open-questions}

### Q1: Q1 PreCompact save-state: print the bridge line or `--no-sync`? {#q1}
**Status:** RESOLVED

**Decision:** `--no-sync`, loud. A 30 s synchronous ingest at compaction is the wrong moment; the SessionStart catch-up bridge and manual save-state cover the store. Output is never swallowed.
**Rationale:** see Decisions Log.

### Q2: Q2 Where do the install flags persist so `--check` re-renders identically? {#q2}
**Status:** RESOLVED

**Decision:** `.claude/rmx-hooks.json` `{version, flags}` written by `--apply`; committed.
**Rationale:** see Decisions Log.

### Q3: Q3 Template hooks vs rmx hooks — two sources? {#q3}
**Status:** RESOLVED

**Decision:** No: install-hooks emits the enforcement entries too (`--enforce`, default on when the scripts exist) so settings.json has ONE author.
**Rationale:** see Decisions Log.

### Q4: Stop-time `focus summarize --promote` — keep it? {#q4}
**Status:** RESOLVED (after ch-bsd bsd-plan2 #s-6, 2026-09-14)

**Decision (revised after bsd-plan2-r2 #s-1):** Keep (default on), BOUNDED. The 0.13 s figure was an
idle-daemon number; live firings on 2026-09-14 took 55 s / 15 s / 6.5 s / 0.1 s while the daemon
was busy with the detached bridge and a 34 s post-commit sync. The Stop entry now runs
`rmx focus summarize --promote --timeout 5` with no daemon-call retries: past 5 s it fails loud
("promote skipped this turn") and PreCompact / save-state catch up. A hook may shout; it may not
hold the turn for the store. It implements `feedback_save_state_includes_promote`. Its no-daemon branch no longer opens the active
slot from a CLI process: `focus summarize --promote` refuses loudly when the daemon is down
(store-through-daemon, constitution VII), the same contract `ingest-gmd --detach` has.
**Rationale:** the plan's "equals what runs today" requirement was about not LOSING hooks; adding
the promote is a documented rule, now written down here instead of in a code comment.

### Q5: What does `--check` prove? {#q5}
**Status:** RESOLVED (after ch-bsd bsd-plan2 #s-4)

**Decision:** managed entries are compared as a MULTISET of full entry JSON (every key, so a
`timeout` edit or a duplicated block is drift); unmanaged (foreign) hooks are LISTED as `? event/
matcher: cmd` lines without failing (they are a documented survivor of `--force`); the three
`~/.claude/hooks` search scripts are compared against `render_scripts()`; flags are recorded on
every project-scope `--apply`, not only the claude path.

### Q6: A busy daemon is not an absent daemon {#q6}
**Status:** RESOLVED (after ch-bsd bsd-plan2 #s-11)

**Decision:** `ingest-gmd --detach` distinguishes absent (no pid, no socket) from busy (alive,
not answering): busy retries the ping for `RMX_DETACH_WAIT_S` (10 s) and then fails with
"daemon busy pid=N — catch-up skipped, retry" instead of "no daemon running … start one".

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 PreCompact save-state: print the bridge line or `--no-sync`? | `--no-sync`, loud. A 30 s synchronous ingest at compaction is the wrong moment; the SessionStart catch-up bridge and manual save-state cover the store. Output is never swallowed. | 2026-09-14 |
| Q2 | Q2 Where do the install flags persist so `--check` re-renders identically? | `.claude/rmx-hooks.json` `{version, flags}` written by `--apply`; committed. | 2026-09-14 |
| Q3 | Q3 Template hooks vs rmx hooks — two sources? | No: install-hooks emits the enforcement entries too (`--enforce`, default on when the scripts exist) so settings.json has ONE author. | 2026-09-14 |
| Q7 | (r6 #b-1) Which legs does the recall budget cover? | ALL of them, from one clock started before the partition probe: the probe (`_memory_intent(partition_timeout=min(5, budget))`), the daemon RPCs (one attempt), the global store on BOTH paths (`_left()`, `retries=0`), and the replica path's shared-worker sockets (the embed client and the rerank client are constructed with the remaining budget; a rerank that cannot fit in `RERANK_MIN_S` (2 s) is skipped and said; a rerank timeout is said, never swallowed). Acceptance: wall ≤ budget + 0.6 s on the exact hook argv. Amends Q4. | 2026-09-15 |
| Q8 | (r6 #m-3/#m-4) The third recall hook and the default budget | PreCompact's `memory recall --recent` carries `--timeout 30`; `RMX_INVOCATION_SOURCE=hook` (exported by every generated hook) is hook mode for `memory recall` (degrade to `[]` + exit 0, session/* excluded unless `--include-session`); the CLI `--timeout` default is 30 s, the same as `verbs.memory_recall` and therefore the MCP tool — the generated hooks pass their own budgets explicitly. | 2026-09-15 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 2.1 | Hook block options for the production hooks | — |
| 2.2 | install-hooks writes settings.json, records flags, gains --check | 2.1 |
| 2.3 | Migrate this repo and guard it in CI | 2.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
