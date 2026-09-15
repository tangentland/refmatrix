---
gmd: "0.1"
id: project-profile
title: "Project Profile — refmatrix facts for neutral agents & hooks"
tags: [config, project-profile, refmatrix]
metadata:
  node_type: project-profile
---

# Project Profile {#root}

Single source of **project-specific facts** that the cat-herder baseline's project-neutral agent
definitions, commands, and hooks pull in by reference. Agents read the sections relevant to their
task; they never hardcode these facts. Per-role detail lives in `.claude/agents/<name>.local.md`.

## Identity {#identity}

- **Name:** refmatrix
- **One-liner:** roaring-bitmap reference matrix over documents, code, and concepts — the `rmx`
  CLI, a per-store daemon, a user-level hub, GMD-backed agent memory (STM focus + durable LTM).
- **Package / module:** `refmatrix` (`src/refmatrix/`), console scripts `rmx` and `refmatrix`.
- **Public remote:** github.com/tangentland/refmatrix (default branch `main`; local work on `master`).

## Stack {#stack}

- **Language:** Python 3.14 on the workstation (package declares `>=3.10`). Mixed-ABI gotcha: the
  system site-packages carry cp311 wheels; only C extensions go invisible — use the venvs below.
- **CLI / UI:** click + rich; FastAPI + uvicorn for the hub web UI (`ui` extra).
- **Storage:** DuckDB catalog (A/B writer slots + read snapshot under `.refmatrix/`), Lance vectors,
  pyroaring bitmaps for linkage cells, JSONL facts/telemetry logs.
- **Models:** sentence-transformers (bge-small embed) + cross-encoder reranker, run as out-of-process
  workers shared through the hub's `models.sock`.
- **Watching / supervision:** watchdog file observer; launchd per-daemon labels
  `com.refmatrix.daemon.<slug>` + `com.refmatrix.hub`.
- **Target OS:** macOS (launchd). Linux supervisor support is not implemented (`launchctl.py`).

## Directory layout {#layout}

- **Source root:** `src/refmatrix/` — `cli.py` (click tree), `daemon.py` (ops registry, single
  writer), `store.py`, `hub.py`, `verbs.py` (agent-facing capability layer), `mcp.py` (MCP server),
  `hooks.py` + `search_hooks.py` (hook generators), `handoff.py` (save/recall-state engine),
  `ingest*.py`, `context.py`, `stm.py`, `templates/` (commands + agents shipped to projects).
- **Tests:** `tests/` (pytest, ~1380 tests, ~13 min full run).
- **Evals:** `eval/` (CSN + MemAware harnesses; `eval/datasets/` is not committed).
- **Docs:** `docs/` — `SYSTEM.md`, `ARCHITECTURE.md`, `INTEGRATION.md`, `PERFORMANCE.md`,
  `INDEX.md` (curated catalog); **ADRs at `docs/adr/`** (not `docs/architecture/adr/`);
  `docs/architecture/` holds the cat-herder overview/index/todo that point INTO those.
- **Process:** `workflow/` (plans, governance, `bullshit/` ledger, registries).
- **Runtime state (never committed):** `.refmatrix/` per project; `~/.refmatrix/` global store + hub.
- **Deploy tree:** `~/refmatrix` (git fast-forward of this tree). `~/bin/rmx` runs
  `~/refmatrix/.venv`. That venv MUST be `pip install -e ~/refmatrix` — an editable install of the
  dev tree makes `rmx`, every daemon, and the hub execute uncommitted dev code (found 2026-09-14).

## Commands {#commands}

Host venvs, no Docker. Dev verification uses `.venv-eval/` (isolated Python 3.14). Test output is
captured to a log (the `enforce-test-to-file` hook blocks inline runs).

- **Test (all):** `.venv-eval/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee workflow/review-output/pytest.log`
- **Test (file):** `.venv-eval/bin/python -m pytest tests/test_x.py -q 2>&1 | tee workflow/review-output/pytest-x.log`
- **GMD lint:** `./scripts/lint-gmd.sh` (CLAUDE.md + docs/); memory files:
  `python3 tools/gmd/lint.py <path>`.
- **Lint / type gates:** none wired (no ruff/mypy config in the repo). Match surrounding style;
  100-col soft limit.
- **Deploy:** commit on `master` → `git -C ~/refmatrix pull --ff-only origin master` →
  `rmx daemon restart --relaunch` (verifies the new pid + version) → hub self-restarts on version
  mismatch. Never run a dev-venv `rmx` with a bumped version against the live store: it trips the
  hub version handshake and restarts the fleet.
- **Live store health:** `rmx daemon status`, `rmx hub status`, `tail .refmatrix/daemon.stderr.log`
  (DuckDB `FatalException` lines are the crash-loop signature; status alone cannot see it).

## Discovery corpus {#corpus}

Mirrored into `.claude/hooks/hooks.env` (`CORPUS_PATHS`, `SRC_DIR`, `ADR_DIR`).

- **Corpus roots:** `src docs workflow tests eval`
- **Source extensions:** `.py .md .sh .json .yaml .yml .toml .txt .html .css .js .pseudo`
- **Lookup ladder:** `rmx context <symbol>` → `rmx grep` → `tldr` → raw grep (the global
  `grep-rewrite-guard` hook rewrites bare grep to `rmx grep`; `RMXGREP_MODE=plain` is the escape).

## Architectural primitives {#primitives}

- **Entity / concept / linkage** — every doc, code symbol, concept, or memory is an entity with a
  stable integer id; linkage types are an open set of `(linkage, concept) → bitmap of entity ids`.
- **Partition** — one store, N logical partitions (project code, memory, sessions, canon).
- **Store** — the DuckDB + Lance + bitmap catalog; opened by ONE writer (the daemon). CLI reads go
  to the lock-free snapshot; CLI writes go through daemon ops (`_store(write)` control point).
- **Daemon** — per-store unix-socket server; `OPS` registry; fast-exits on DuckDB invalidation for
  launchd to respawn. `_op_*` is the only write surface.
- **Hub** — one per machine: watchdog over every daemon, shared model workers, global memory
  store, bus, web UI on :7777.
- **STM / focus** — per-session working-memory ring + composite; promoted to durable memory
  (`session/digest`) at save-state / PreCompact.
- **Memory** — `kind=memory` rows; curated GMD files under `~/.claude/projects/<slug>/memory/`
  reach the store through the bridge (`ingest-gmd --as-memory`, run by save-state + SessionStart).
- **Verbs** — `verbs.py` is the agent-facing capability registry; MCP tools and CLI commands are
  thin adapters over verbs (the anti-drift rule; MCP/CLI parity is a test, not a hope).
- **Hooks** — `hooks.py` / `search_hooks.py` GENERATE the Claude Code hook config; the installed
  config must equal the generated one (`rmx install-hooks --check`).

## Domain glossary {#glossary}

- **bridge** — the path that ingests the curated memory dir into the store as memory rows.
- **helix** — snapshot-time annotation on stale retrievals (`[helix] last worked …`).
- **primer** — `.refmatrix/PRIMER.md`, top reference-dense symbols, regenerated at SessionStart.
- **scan-prompt** — UserPromptSubmit hook that injects context for symbols in the prompt.
- **save-state / recall-state** — session handoff writer / reader (CLI + MCP, shared `handoff.py`).
- **slot** — `catalog.A/B.duckdb` writer files; `active` marker names the live one.
- **fast-exit** — daemon self-termination on a DuckDB fatal so the supervisor respawns it.

## Project constraints {#constraints}

- No silent failures on memory-critical paths: no `2>/dev/null`, `|| true`, bare `except: pass`,
  or uncounted skips between a memory file and the store.
- Store access routes through the daemon; never open `Store()` on the active slot from a CLI path
  while a daemon may hold it.
- The benchmark path IS the production path (`eval/production/`): never measure a bespoke path
  and report it as the product.
- Every capability an agent can call is a verb first; CLI and MCP expose it, never implement it.
- Hook config is generated, never hand-edited; hand-authored hooks are template bugs.
- GMD everywhere: memory files, docs, workflow. Zero lint errors before commit.
