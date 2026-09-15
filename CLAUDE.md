---
gmd: "0.1"
id: claude
title: "CLAUDE.md — refmatrix operating instructions"
tags: [instructions, cat-herder, refmatrix]
metadata:
  node_type: instructions
---

# Memory & context layer {#memory-context-layer}

@.claude/PROJECT_PROFILE.md

<!-- refmatrix: top reference-dense symbols, regenerated on SessionStart by the rmx SessionStart hook. Without this include the primer is generated every session and never read. -->
@.refmatrix/PRIMER.md

**`rmx` (refmatrix) is the primary memory, context, and navigation layer — and it is also THIS
project.** Its hooks own session recall, focus, sync, and prompt-scan. Prefer `rmx context`,
`rmx query`, `rmx grep`, and `rmx memory` over raw grep/read for corpus discovery. Remember that
`rmx` on PATH is the DEPLOYED build; the dev tree is verified through `.venv-eval/`.

# CLAUDE.md {#root}

Guidance for Claude Code working in this repository. Bootstrapped from the **cat-herder** template
on 2026-09-14; project facts live in `.claude/PROJECT_PROFILE.md`, role specifics in
`.claude/agents/<name>.local.md`.

## Project Overview {#project-overview}

**refmatrix** — roaring-bitmap reference matrix over documents, code, and concepts; the `rmx` CLI,
a per-store daemon, a user-level hub, and GMD-backed agent memory. See `docs/SYSTEM.md`.

- **Stack**: Python 3.14, click/rich, DuckDB + Lance + pyroaring, sentence-transformers, FastAPI hub
- **Target OS**: macOS (launchd-supervised daemons)

## Development Commands (host venv, no Docker) {#development-commands}

There is no container. Two venvs, one rule each:

- `.venv-eval/` — the DEV interpreter. Tests, evals, and dev-tree verification run here.
- `~/refmatrix/.venv/` — the DEPLOY interpreter behind `~/bin/rmx`, the daemons, and the hub.
  Deploy = fast-forward `~/refmatrix` to a committed `master` sha, then `rmx daemon restart --relaunch`.

**Hard rules:**

- **NEVER run a dev-venv `rmx` with a bumped version against the live store** — the hub version
  handshake restarts the fleet, the daemon falls to in-process writes, and DuckDB lock crashes follow.
  Verify dev code with pytest, or a throwaway store under a short `mkdtemp()` root.
- **NEVER open `Store()` directly on a live `.refmatrix/`** — go through daemon ops (`_store(write)`).
- **All test runs capture output to a file** — `2>&1 | tee workflow/review-output/<name>.log`
  (the `enforce-test-to-file` hook blocks inline runs).

```bash
# Full suite (~13 min)
.venv-eval/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee workflow/review-output/pytest.log
# One file
.venv-eval/bin/python -m pytest tests/test_hooks.py -q 2>&1 | tee workflow/review-output/pytest-hooks.log
# GMD lint (CLAUDE.md + docs/); memory files: python3 tools/gmd/lint.py <path>
./scripts/lint-gmd.sh
```

### Tests (CRITICAL — NEVER SKIP) {#system-dependent-tests}

**ALL tests run.** Never `--ignore` or `-k` away a failing group to get green. Daemon tests need a
SHORT tmp root (macOS `sun_path` is ~104 bytes). A known pre-existing failure is logged in
`workflow/bug_registry.md`, not skipped.

## Development Guidelines {#development-guidelines}

- Match the surrounding style; ~100 columns; type hints on new signatures; no formatter gate.
- Docstrings say WHY and name the incident/date that motivated the code — this repo reads its own
  history through them.
- Reason FROM the primitives in `.claude/PROJECT_PROFILE.md` (entity/partition/store/daemon/hub/
  STM/memory/verbs/hooks) before proposing a new mechanism.

### No Mocks in Production Code (CRITICAL) {#no-mocks}

All `src/` code is fully concrete — no stubs, placeholder branches, "Phase N stub" comments that
outlived their phase, or env-flag-only facades. Mocks live ONLY in `tests/` and are classified in
`workflow/test_mock_registry.md`. A test that monkeypatches the function under test is not a test.

### No Silent Failures on Memory Paths (CRITICAL) {#no-silent-failures}

Anything between a memory file and the store — bridges, hooks, save-state, recall — surfaces its
failure: no `2>/dev/null`, `|| true`, bare `except: pass`, or uncounted `continue`. A skipped file
is counted and printed.

### No Workarounds (CRITICAL) {#no-workarounds}

A missing dependency or a broken environment is defined as a gap, the real fix is proposed, and the
user is asked before proceeding. Consult `workflow/development_resources.md` first.

## Git Workflow {#git-workflow}

Local trunk is `master` (GitHub default branch `main`; the user pushes). One branch per plan task,
merged back with `--no-ff`; never delete branches. Deploy only from a committed `master` sha.

```bash
git checkout -b task-X.Y-description master
# ... work ...
git checkout master && git merge --no-ff task-X.Y-description
```

## Permissions {#permissions}

**YOU ARE ALLOWED TO EXECUTE ALL COMMANDS WITHIN THE PROJECT DIRECTORY STRUCTURE**
   *FOLLOWING THESE RULES*
     - DO NOT share sensitive information or credentials
     - NEVER COMMIT to the 'release' branch
     - DO NOT CONFIDENCE PROMPT FOR PERMISSIONS
     - NEVER EXECUTE THE COMMAND 'rm -rf *'
     - YOU ARE ALLOWED TO MAKE CHANGES WITHOUT ASKING WITHIN THE PROJECT
     - Surgery on a live `.refmatrix/` catalog (index rebuilds, slot swaps) is announced first and
       backed up first.

## MCP Servers {#mcp-servers}

`.mcp.json` carries one server: `refmatrix` (`rmx mcp`). On this workstation it is pointed at
`.venv-eval/bin/rmx` so the MCP surface exercises dev code — that file stays uncommitted. The
MCP server is a per-client stdio process: after a deploy, `/mcp` reconnect to load new tools.

## Discovery & Tooling {#discovery-tooling}

| Tool | Purpose | Notes |
|------|---------|-------|
| **rmx** | `rmx context/query/grep`, GMD memory, STM focus | this repo; `rmx` = deploy build |
| **llm-tldr** (`tldr`) | call graphs, token-efficient code analysis | `tldr context <symbol>` |
| **caveman** | compressed communication mode | `/caveman`, `/commit` |

**Discovery ladder:** `rmx context <symbol>` → `rmx grep` → `tldr` → raw grep. Indexes before
search: `docs/INDEX.md`, `docs/architecture/ARCHITECTURE_INDEX.md`, `workflow/plan-of-plans.md`.

## Graph Markdown (GMD) {#graph-markdown}

Persistent prose is GMD: frontmatter (`gmd: "0.1"` + unique `id` + `title` + `tags`), a `{#anchor}`
on every heading, `rel:` edges for citations. Primer `docs/gmd/PRIMER.md`, spec `docs/gmd/SPEC.md`,
tooling `tools/gmd/`. Validate before commit: `./scripts/lint-gmd.sh` — zero errors.

## Context Management (CRITICAL) {#context-management}

### Write Decisions Immediately {#write-decisions}

Discussion → Decision → Write to file → Continue. Capture the WHY to STM with the `refmatrix` MCP
tool `rmx_focus_note` (thinking is redacted from transcripts). STM graduates to durable memory at
PreCompact/Stop and on `/save-state`.

### Planning, Exploration & Templates {#planning-exploration-templates}

Full workflow in `workflow/PLANNING_WORKFLOW.md`; templates in `workflow/templates/`.
**Write proposed plans to disk BEFORE presenting questions.**

### Navigation & Lookup {#navigation-lookup}

| Need | Consult First | Then |
|------|---------------|------|
| Prior work | `handoff.md` + `rmx recall-state` | `workflow/past_handoffs/` |
| Code structure | `rmx context <symbol>` / `rmx grep` | source |
| Architecture | `docs/architecture/ARCHITECTURE_INDEX.md` | `docs/ARCHITECTURE.md`, `docs/SYSTEM.md` |
| Decisions | `docs/adr/` | `docs/INDEX.md` |
| Gaps | `docs/architecture/todo.md` | `workflow/deferral_registry.md` |
| Active plans | `workflow/plan-of-plans.md` | `workflow/plans/` |
| Audit debt | `workflow/bullshit/last_run.log` | `workflow/bullshit/INDEX.md` |

## Session Start {#session-start}

1. `rmx recall-state` (or `/recall-state`) and read `handoff.md`.
2. Read `workflow/plan-of-plans.md` for what to implement next.
3. Read `workflow/bullshit/last_run.log`; any unaddressed BULLSHIT finding is first priority.
4. Verify git state matches the handoff; check `rmx daemon status` + `rmx hub status`.
5. If implementing: read the active plan (`metadata.status: in-progress`) and its task specs.

## Agent and Skill Workflow {#agent-skill-workflow}

Agents: `@ch-architect`, `@ch-alignment`, `@ch-implementer` (TDD GREEN, writes no tests),
`@ch-test-engineer` (TDD RED), `@ch-code-reviewer`, `@ch-security-auditor`, `@ch-doc-writer`,
`@ch-gap-master`, `@ch-bsd` (runtime-integration audit, ledger in `workflow/bullshit/`),
`@ch-performance-tuner`, `@ch-work-summary`, `@gmd-curator`. Definitions are project-neutral;
overlays in `.claude/agents/<name>.local.md`.

Commands: SDD chain `/ch-constitution → /ch-specify → /ch-clarify → /ch-crucible → /ch-plan →
/ch-tasks → /ch-analyze → /ch-implement`; review `/ch-review`, `/ch-audit`, `/ch-bsd`,
`/ch-test-gen`, `/ch-handoff`; session state `/save-state`, `/recall-state`, `/commit-state`,
`/detour`, `/return`, `/stash*`.

## Task Completion Workflow {#task-completion-workflow}

Continuous Implementation Mode, TDD per `workflow/TDD_GOVERNANCE.md`:

1. **Identify next task** — `workflow/plan-of-plans.md` → the task spec.
2. **Gap check** — missing infrastructure is named, not worked around.
3. **RED** — failing tests from the acceptance criteria; record the red run.
4. **GREEN** — concrete `src/` code; no tests authored in this step.
5. **Verify** — full relevant tests captured to a log; GMD lint clean.
6. **Review** — `/ch-review`; then `@ch-bsd` over the commit range. Remedy, re-review, until clean.
7. **Docs** — indexes, `docs/INDEX.md`, registries (mock / deferral / bug).
8. **Implementation summary** → `workflow/implementation_summaries/<task>.md` (MANDATORY).
9. **Handoff** — update `handoff.md`; `rmx save-state` at session end.
10. **Commit** on the task branch, merge `--no-ff` to `master`; deploy when a release lands.

### Implementation Plans Must Be Pre-Written (CRITICAL) {#plans-pre-written}

Plans live permanently in `workflow/plans/<name>.md`; stage = `metadata.status`
(`drafting → approved → in-progress → completed`). `approved` requires every task spec under
`workflow/plans/<name>-tasks/`. Do not write production code for a plan before that gate.

### Cleanup Phase (MANDATORY) {#cleanup-phase}

After each plan: triage `docs/architecture/todo.md`, graduate mocks in
`workflow/test_mock_registry.md`, clear deferred Medium review findings. Bounded to the chunk.

## Quality Gates {#quality-gates}

### Before Commit (ALL required) {#before-commit}

- [ ] Implementation summary written
- [ ] `src/` fully concrete; no new silent failure on a memory path
- [ ] Tests pass (all), log captured; new tests proven RED first
- [ ] GMD lint zero errors (`./scripts/lint-gmd.sh`, memory files via `tools/gmd/lint.py`)
- [ ] `/ch-review` Critical/High addressed; `@ch-bsd` no unaddressed BULLSHIT
- [ ] `rmx install-hooks --check` clean (installed hooks == generated hooks)
- [ ] Verb parity test green (every MCP tool is a verb)
- [ ] Registries + indexes current; `handoff.md` updated

## Handoff Rotation {#handoff-rotation}

`handoff.md` keeps the latest session; prior sessions archive to
`workflow/past_handoffs/<seq>-<desc>_<date>.md`. `rmx save-state` writes the durable
`savestate_<session>` memory and runs the memory bridge.

## Planning & Task Documentation {#planning-task-docs}

`workflow/` = process (plans, governance, registries, `bullshit/`); `docs/` = knowledge
(`SYSTEM`, `ARCHITECTURE`, `INTEGRATION`, `PERFORMANCE`, `adr/`, `architecture/` index+todo,
`gmd/`). Source-of-truth order: `plan-of-plans.md` → `plans/<name>.md` → `plans/<name>-tasks/`.

## When to Pause Mid-Task {#when-to-pause}

Only for a blocking dependency, ambiguous requirements, a user request, or a decision that
changes the store on disk. Otherwise follow the Task Completion Workflow.
