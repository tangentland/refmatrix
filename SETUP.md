---
gmd: "0.1"
id: SETUP
title: "cat-herder — Project Bootstrap with Claude Code"
tags: [instructions, setup]
metadata:
  node_type: instructions
---

# cat-herder — Project Bootstrap with Claude Code {#root}

**cat-herder** is a structured Claude Code template: a workflow, an agent/command suite, GMD
documentation tooling, and an installer that wires the token-saving dependencies. Follow these
steps to initialize a new project from it.

## Step 1: Scaffold a New Project {#step-1}

`./install.sh PROJECT_PATH` scaffolds the template into the target directory (created if it
doesn't exist; **existing files are preserved, never overwritten**), then installs and wires the
recommended tooling (rmx, llm-tldr, rtk, caveman) and the bundled GMD linter. It is
idempotent and each dependency is optional:

```bash
./install.sh ../my-project          # scaffold into ../my-project, then wire it
./install.sh ~/code/app --minimal   # scaffold, only wire the bundled GMD tooling
./install.sh                        # no path → wire the template repo in place
./install.sh --help                 # full usage + flags
```

Flags: `--minimal`, `--skip-rmx`, `--skip-tldr`, `--skip-rtk`, `--skip-caveman`.

> Scaffolding excludes the template's own `.git/`, memory state, and caches. The new project is
> not a git repo — run `git init` there yourself when ready.

Then `cd PROJECT_PATH` to continue.

> **rmx** ([refmatrix](https://github.com/tangentland/refmatrix)) is the lookup + GMD-memory
> surface referenced in CLAUDE.md. It is a Python package (needs Python ≥ 3.10 and git) exposing
> the `rmx` CLI; the installer pulls it from git via pipx/uv/pip. For semantic recall, add the
> dense extra: `pipx install "refmatrix[dense] @ git+https://github.com/tangentland/refmatrix.git"`.

After install, **restart Claude Code** so the rtk/caveman hooks load.

## Step 2: Find and Replace Placeholders {#step-2}

Search for these placeholders and replace them with your project values:

| Placeholder | Replace With | Example |
|-------------|-------------|---------|
| `{PROJECT_NAME}` | Your project name | `MyApp` |
| `{project_package}` | Python package name | `myapp` |
| `{project_db}` | Database name | `myapp` |
| `{pkg}` | Short package name (for commands) | `myapp` |
| `{DATE}` | Current date | `2026-02-22` |

Files containing placeholders:
- `CLAUDE.md` — main Claude instructions
- `.mcp.json` — MCP server config (database URI)
- `handoff.md` — session handoff
- `workflow/QUICK_REFERENCE.md` — quick lookup
- `workflow/PATTERNS.md` — code patterns
- `.claude/agents/*.md` and `.claude/commands/*.md` — `{project_package}` / `{PROJECT_NAME}` in examples

Quick scan for anything left:

```bash
grep -rn '{PROJECT_NAME}\|{project_package}\|{project_db}\|{pkg}' . --include='*.md' --include='*.json'
```

## Step 3: Set Up Environment Variables {#step-3}

These environment variables are referenced by `.mcp.json`:

**Required:**
```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_..."
```

**Optional (for web search via onmisearch):**
```bash
export TAVILY_API_KEY="tvly-..."
export BRAVE_API_KEY="BSA..."
export KAGI_API_KEY="..."
export EXA_API_KEY="..."
export JINA_AI_API_KEY="..."
export FIRECRAWL_API_KEY="..."
export PERPLEXITY_API_KEY="..."
```

**Tip:** Add these to your shell profile (`~/.zshrc` or `~/.bashrc`) or use a `.env` file
with direnv.

## Step 4: Update .mcp.json Paths {#step-4}

The `onmisearch` server path points to the plugin location on the template author's machine.
Update the path to match your installation:

```json
"command": "node",
"args": ["/path/to/your/.claude/plugins/repos/mcp-omnisearch/dist/index.js"]
```

If you don't have onmisearch installed, remove that server block entirely.

## Step 5: Initialize Claude Code Memory {#step-5}

On your first Claude Code session, Claude will:
1. Read `handoff.md` for initial context
2. Use `rmx context <symbol>` / `rmx grep` for code navigation
3. Begin recording durable learnings as GMD memory files

Memory is authored as GMD files (see `docs/gmd/PRIMER.md`) and indexed for semantic recall via
**rmx** ([refmatrix](https://github.com/tangentland/refmatrix)) — `rmx memory recall` / `rmx memory
search`, backed by `rmx memory sync-disk`. If rmx is not installed, memory files are still written
and linted; only the retrieval layer is unavailable, so the workflow degrades gracefully.

## Step 6: Create Planning & Tracking Directories {#step-6}

The project uses a **status-tracked plan lifecycle**. All plans live permanently in
`workflow/plans/`; a plan never moves between directories — its stage is recorded ONLY by the
`metadata.status` field in its GMD frontmatter: `drafting` → `approved` → `in-progress` →
`completed`.

```bash
# All plans live here permanently; stage = metadata.status frontmatter
mkdir -p workflow/plans

# Architecture documentation
mkdir -p docs/architecture/explorations
mkdir -p docs/architecture/adr

# Implementation tracking
mkdir -p workflow/implementation_summaries
mkdir -p workflow/review-output
mkdir -p workflow/past_handoffs

# Templates (already provided)
# workflow/templates/ — task-spec, proposed-plan, exploration, handoff-session
```

Create the meta index file:

**`workflow/plan-of-plans.md`** — the single plan index + sequenced execution order (with a
Status column). This is the source of truth for what to implement next; each plan's Status
mirrors its `metadata.status` frontmatter:
```markdown
# Plan of Plans

Index and sequenced execution order for all implementation plans. This is the source of truth
for what to implement next. Every plan lives in `workflow/plans/`; the Status column mirrors the
plan's `metadata.status` frontmatter (`drafting` → `approved` → `in-progress` → `completed`).

| # | Plan | Status | Tasks | Notes |
|---|------|--------|-------|-------|
| 1 | {first plan name} | drafting | — | — |
```

## Step 7: Set Up Docker (REQUIRED) {#step-7}

All development and testing runs in Docker. Create a `docker-compose.yml`:

```yaml
services:
  dev:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    volumes:
      - .:/workspace
      - test-output:/test-output
    working_dir: /workspace
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: {project_package}
      POSTGRES_PASSWORD: {project_package}_dev
      POSTGRES_DB: {project_package}
    ports:
      - "5433:5432"

volumes:
  test-output:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ./docker/test-output
```

Create `docker/entrypoint.sh` to manage the container venv:

```bash
#!/bin/bash
VENV_PATH="/opt/{project_package}-venv"
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi
source "$VENV_PATH/bin/activate"
pip install -e ".[dev]"
exec "$@"
```

Create the test output directory:
```bash
mkdir -p docker/test-output
```

**Important:** The container venv lives at `/opt/{project_package}-venv`, NOT at
`/workspace/.venv`. The entrypoint manages all dependency installation. Never run
`uv` or `pip install` manually — add deps to `pyproject.toml` and restart the container.

## Step 8: First Session {#step-8}

Start Claude Code and it will:
1. Read the handoff and indexes
2. Read `workflow/plan-of-plans.md` for what to implement next
3. Check `docs/architecture/todo.md` for known gaps
4. Be ready to implement with full context awareness

Tell Claude what your project does and what to build first. It will follow the
Task Completion Workflow defined in CLAUDE.md automatically.

## Template Files {#template-files}

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Main Claude Code instructions — development workflow, quality gates, agents |
| `install.sh` | Installs + wires the tooling (rmx, llm-tldr, rtk, caveman, GMD) |
| `docs/` | **Knowledge** — `architecture/` (README, INDEX, todo, adr/, concepts/, explorations/, tech-stack/), `guides/`, `reference/`, `specs/`, `design/`, `gmd/` |
| `workflow/` | **Process** — plans, governance, templates, audits, summaries (see `workflow/INDEX.md`) |
| `workflow/PLANNING_WORKFLOW.md` | Full planning, exploration, and plan approval workflow |
| `workflow/PLAN_GOVERNANCE.md` | Plan lifecycle, staleness, question-forcing |
| `workflow/templates/` | Document templates (task-spec, proposed-plan, exploration, handoff) |
| `workflow/test_mock_registry.md` | Mock governance registry |
| `docs/gmd/` | GMD primer + conformance spec (Graph Markdown authoring) |
| `tools/gmd/` | Bundled GMD tooling — `gmd lint\|init\|slice`, `lint.py` |
| `scripts/lint-gmd.sh` | Lint `CLAUDE.md` + `docs/` as a GMD graph |
| `.gmd/config.yml` | Project-local GMD lint config |
| `.claude/agents/` | Agent suite — `ch-architect`, `ch-code-reviewer`, `ch-security-auditor`, `ch-test-engineer`, `ch-doc-writer`, `ch-gap-master`, `ch-bsd`, `ch-performance-tuner`, `ch-work-summary`, `general-purpose` |
| `.claude/commands/` | Commands — `/ch-review`, `/ch-audit`, `/ch-bsd`, `/ch-test-gen`, `/ch-handoff` |
| `.claude/rules/` | Always-on rules (e.g. `bug-registry.md`) |
| `.mcp.json` | MCP server configuration — GitHub, Docker, search, PostgreSQL, diagrams |
| `.gitignore` | Git ignore rules — venv, cache, test output, memory state, IDE files |
| `handoff.md` | Session handoff template — context between conversations |
| `workflow/QUICK_REFERENCE.md` | Fast lookup — commands, conventions, checklist |
| `workflow/PATTERNS.md` | Copy-paste code patterns — testing, async, FastAPI |
| `workflow/development_resources.md` | Infrastructure inventory — Docker, database, environment |
| `SETUP.md` | This file — bootstrap instructions |
