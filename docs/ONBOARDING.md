---
gmd: "0.1"
id: ONBOARDING
title: "Agent Onboarding — first run in a template-bootstrapped project"
tags: [instructions, onboarding]
metadata:
  node_type: instructions
---

# Agent Onboarding {#root}

What **you (the agent)** do the first time you land in a project scaffolded from the cat-herder
template. This is the human-facing `SETUP.md` steps, driven by the agent. Run it ONCE, then never
again — subsequent sessions follow the normal `CLAUDE.md` Session Start.

## Detect an uninitialized template {#detect}

You are in a fresh, un-onboarded clone if ANY of these hold:

- `CLAUDE.md`, `.mcp.json`, or `.claude/PROJECT_PROFILE.md` still contain literal placeholders:
  `{PROJECT_NAME}`, `{project_package}`, `{project_db}`, `{PATH_TO_OMNISEARCH}`.
- `.claude/PROJECT_PROFILE.md` still has its `{…}` placeholder values.
- No `.claude/agents/*.local.md` overlays exist and `.claude/hooks/hooks.env` is absent.

Quick check: `grep -rl "{PROJECT_NAME}\|{project_package}" CLAUDE.md .mcp.json .claude/PROJECT_PROFILE.md`.
If it matches, run this onboarding. If nothing matches, the project is initialized — skip to
[normal work](#after).

**If you detect an uninitialized template, surface it to the user before mutating anything** — ask
for the project's name, package/module, stack, and DB (or confirm you should infer them from the
existing code). Then proceed.

## Onboarding sequence {#sequence}

1. **Install + wire tooling** — run `./install.sh` (in place) or `./install.sh <path>` to scaffold
   elsewhere. It wires GMD + SDD scripts, installs rmx/tldr/rtk/caveman when available, and seeds
   `.claude/hooks/hooks.env` from its `.example` (only if absent — non-destructive; re-runnable as a
   safe upgrade). See `SETUP.md` for the tooling detail.
2. **Fill the project profile** — `.claude/PROJECT_PROFILE.md`: identity, stack, directory layout,
   Docker test/lint/build commands, discovery-corpus paths, architectural primitives, glossary,
   constraints. This is the shared project-fact source every neutral agent reads.
3. **Expand placeholders** — replace `{PROJECT_NAME}` / `{project_package}` / `{project_db}` /
   `{PATH_TO_OMNISEARCH}` across `CLAUDE.md`, `.mcp.json`, `handoff.md`, and the workflow docs
   (`SETUP.md` Step 2 lists them). Never leave a literal `{…}` placeholder in a live project.
4. **Tune `hooks.env`** — set `SRC_DIR`, `ADR_DIR`, `CORPUS_PATHS`, `CORPUS_EXTS` in
   `.claude/hooks/hooks.env` to this project's real layout (mirrors PROFILE §layout/§corpus).
5. **Create per-agent overlays as needed** — copy `.claude/agents/<name>.local.md.example` →
   `.claude/agents/<name>.local.md` and fill project-specific guidance for the roles that need it
   (at minimum `ch-architect`, `ch-test-engineer`). Overlays are committed (they're this project's
   customization); the neutral committed `<name>.md` stays untouched.
6. **Set the constitution** — run `/ch-constitution` to record this project's governing principles
   under `## Project-specific principles` in `workflow/CONSTITUTION.md` (the non-negotiables ship
   filled; add domain rules, perf budgets, security posture, dependency policy).
7. **Optional — project guardrails** — add `.claude/p20-0/guardrails/<name>.md` (GMD, a fenced
   `guardrail:` block with `tier` + `rule`) for any project-specific action policy, then recompile
   (`python3 .claude/p20-0/compile_guardrails.py`). Requires rmx.
8. **Load hooks + verify** — restart Claude Code so `.claude/settings.json` hooks load; confirm
   `rmx --version` (memory layer) and that `./scripts/lint-gmd.sh` is clean.
9. **Commit the initialized state** — one commit: filled `PROJECT_PROFILE.md`, expanded CLAUDE.md /
   `.mcp.json`, `hooks.env`, `<name>.local.md` overlays, and the `/ch-constitution` output.

## After onboarding {#after}

The project is initialized. Follow `CLAUDE.md` Session Start, then drive real work through the
spec-driven-development chain — `/ch-specify` a first feature →
`/ch-clarify → /ch-crucible → /ch-plan → /ch-tasks → /ch-analyze → /ch-implement`. Capture
decisions to STM via the `refmatrix` MCP tool `rmx_focus_note` as you go.
