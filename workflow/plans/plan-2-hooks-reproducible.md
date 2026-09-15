---
gmd: "0.1"
id: plan-2-hooks-reproducible
title: "Hooks are generated: `rmx install-hooks` produces the whole production config and `--check` proves it"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: completed
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

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 PreCompact save-state: print the bridge line or `--no-sync`? | `--no-sync`, loud. A 30 s synchronous ingest at compaction is the wrong moment; the SessionStart catch-up bridge and manual save-state cover the store. Output is never swallowed. | 2026-09-14 |
| Q2 | Q2 Where do the install flags persist so `--check` re-renders identically? | `.claude/rmx-hooks.json` `{version, flags}` written by `--apply`; committed. | 2026-09-14 |
| Q3 | Q3 Template hooks vs rmx hooks — two sources? | No: install-hooks emits the enforcement entries too (`--enforce`, default on when the scripts exist) so settings.json has ONE author. | 2026-09-14 |

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
