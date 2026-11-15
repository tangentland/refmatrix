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
- **Measuring a live store is read-only on a copy** — copy `.refmatrix/catalog.read.duckdb` to the
  scratchpad and open the copy with duckdb `read_only=True` under `.venv-eval`.

```bash
# Full suite (~13 min)
.venv-eval/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee workflow/review-output/pytest.log
# One file
.venv-eval/bin/python -m pytest tests/test_hooks.py -q 2>&1 | tee workflow/review-output/pytest-hooks.log
# GMD lint (CLAUDE.md + docs/); memory files: python3 tools/gmd/lint.py <path>
./scripts/lint-gmd.sh
```

### Tests (CRITICAL — NEVER SKIP) {#system-dependent-tests}

**ALL tests run.** Never `--ignore` or `-k` away a failing group to get green. How tests are
written, grouped and run: [[#test-discipline]].

### Test Discipline (CRITICAL) {#test-discipline}

The suite is ~4,100 tests and 60 min; the 2026-11-15 audit (`workflow/measurements/test-suite-audit-2026-11-15.md`)
found it bloated by habit, not by junk: per-round files, 2-4 near-identical variants, tests that
wait out real timeouts, and 49 tests "proving" busy/down behaviour against a patched value. These
rules keep it from growing back (L165-L168). Every agent that writes or reviews a test follows them.

1. **Extend, don't add.** Before writing a test, find the feature's existing test file and the
   tests on the same path (`rmx grep`, the test names). Add a case to it; 2+ variants of one
   behaviour are ONE parametrized test. Never a new `test_*_r<n>.py`, `*_remedy*`, `test_bug<N>*`
   or `*_red.py` file per round, bug or fix: name files and tests for the behaviour.
2. **One file per feature, grouped by module**, so `pytest <file or dir>` is a focused run. After
   29.5 the layout mirrors `src/` (`tests/<module>/`).
3. **Through the entry point.** Each feature change has at least one test through what users call
   (CLI, verb, MCP tool, daemon op, hook), not only the helper.
4. **Real states, faked boundaries only.** Never patch the function under test or the value a
   guard reads. Busy, slow, held or down daemon behaviour runs on a real test daemon (the sandbox
   daemon, the lock-hold fixture), never a patched `ping` / `daemon.call` / `daemon_status`. Fake
   only process boundaries (launchd, the hub, a model worker), each registered in
   `workflow/test_mock_registry.md`.
5. **Behaviour, not source text.** A test that reads `src/` is allowed only as a guard on a stated
   rule, and it plants a must-fail case to prove it can fail.
6. **No real waits.** Never sit out a production timeout: use a test-sized budget knob and keep ONE
   test per budget at the real default. Fixtures stop test daemons with a short shutdown timeout.
   Hold a job open with a gate, not with a big dataset.
7. **Seen failing first.** A new test fails before its fix, for the intended reason (its E line).
8. **Never red, never skipped away.** A failing test is fixed or marked
   `xfail(strict=True, reason="bug-NNN")`; nothing stays red across releases. Never `--ignore` or
   `-k` away a failing group. A known failure has a `workflow/bug_registry.md` row.
9. **Running tests: in an isolated slot, on a committed sha.** A verify run goes through
   `scripts/lane-mini.sh <repo> <ref> <log-name> <files…>` (the Mac mini, users `rmxtest1..2`;
   `rmxtest3` there is the latest-versions canary, L172) or
   `scripts/lane-local.sh …` (this machine, local users `rmxtest1..3`). Each slot is its own macOS
   user (own HOME, `~/.refmatrix`, launchd domain, TMPDIR; no write access to the live stores), takes
   the first free slot, and copies the log to `workflow/review-output/<log-name>.log`. Prefer
   the mini; it keeps load off this machine. The old single lane
   (`/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`, output tee'd to a log) is only for
   tests that need the dev tree's live `.refmatrix/` and for the release gate's full suite. Daemon
   tests use a SHORT `mkdtemp()` root (`sun_path` ~104 bytes). A branch runs the verify set (its
   tests plus every importer of a changed module), never the full suite.

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

The default planning path is the one in `workflow/ORCHESTRATION.md` `#planning` (ch-architect on
Fable → ch-bsd spec rounds → lead rulings → user decisions → merge). The SDD chain stays available.

Commands: SDD chain `/ch-constitution → /ch-specify → /ch-clarify → /ch-crucible → /ch-plan →
/ch-tasks → /ch-analyze → /ch-implement`; review `/ch-review` (optional), `/ch-audit`, `/ch-bsd`,
`/ch-test-gen`, `/ch-handoff`; session state `/save-state`, `/recall-state`, `/commit-state`,
`/detour`, `/return`, `/stash*`.

## Task Completion Workflow {#task-completion-workflow}

Continuous Implementation Mode. **The procedure is `workflow/ORCHESTRATION.md`** (lean since
2026-11-15, L165: ceremony scales with risk). In short:

1. **The lead orchestrates** — agents work in their own `/Volumes/littlebig/<project>-<worker>`
   clones, read-only against every live store.
2. **Next task** from `workflow/plan-of-plans.md`; specced just in time, one page.
3. **Small fix** (one module / test-side / < ~100 `src` lines, no shared path): one agent writes
   test + fix, test shown failing first; the lead reads the diff and merges.
4. **Large change** (shared path or several modules): RED → GREEN in separate hands, mutations on
   the `src/` change, one ch-bsd pass (only BULLSHIT earns a second round).
5. **Verify:** the task's tests + every importer of a changed module; E lines vs the last release.
6. **Merge `--no-ff`; release** (major → full suite on merged `master`; minor → verify set),
   deploy, live check with backups first.
7. **Handoff** — `handoff.md`; `rmx save-state` at session end.

### Implementation Plans Must Be Pre-Written (CRITICAL) {#plans-pre-written}

Plans live permanently in `workflow/plans/<name>.md`; stage = `metadata.status`
(`drafting → approved → in-progress → completed`). `approved` requires every task spec under
`workflow/plans/<name>-tasks/`. Do not write production code for a plan before that gate.

### Cleanup Phase (MANDATORY) {#cleanup-phase}

After each plan: triage `docs/architecture/todo.md`, graduate mocks in
`workflow/test_mock_registry.md`, clear deferred Medium review findings. Bounded to the chunk.

## Quality Gates {#quality-gates}

### Before Commit (ALL required) {#before-commit}

- [ ] `src/` fully concrete; no new silent failure on a memory path
- [ ] Verify set passes (log captured); a new test was seen failing before its fix
- [ ] Large changes only: mutations on the `src/` change each fail a test; one ch-bsd pass with
      no unaddressed BULLSHIT
- [ ] GMD lint zero errors (`./scripts/lint-gmd.sh`, memory files via `tools/gmd/lint.py`)
- [ ] `rmx install-hooks --check` clean; verb parity test green
- [ ] POP row current for a merge, release or scope change

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
