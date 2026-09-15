---
gmd: "0.1"
id: QUICK_REFERENCE
title: "Quick Reference"
tags: [reference]
metadata:
  node_type: doc
---

# Quick Reference {#root}

## Commands (host venv — no Docker) {#docker-commands}

```bash
.venv-eval/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee workflow/review-output/pytest.log   # all tests
.venv-eval/bin/python -m pytest tests/test_x.py -q 2>&1 | tee workflow/review-output/pytest-x.log      # one file
./scripts/lint-gmd.sh                                                                                # GMD lint
rmx install-hooks --check                                                                            # hooks == generated
git -C ~/refmatrix pull --ff-only origin master && rmx daemon restart --relaunch                     # deploy
```

## Reading Test Output {#reading-test-output}

```bash
tail -20 workflow/review-output/pytest.log
```

## Git Workflow {#git-workflow}

```bash
git checkout -b task-X.Y-description master    # New branch per task
git checkout master && git merge --no-ff task-X.Y-description  # Merge when complete
```

## Quality Gates (Before Commit) {#quality-gates}

1. Implementation summary written to `workflow/implementation_summaries/<task-name>.md`
2. Tests pass — ALL, output captured to a log
3. GMD lint zero errors
4. `rmx install-hooks --check` clean; verb parity test green
5. Code review (@ch-code-reviewer + @ch-architect) — no Critical/High
6. Test review (@ch-test-engineer) — adequate coverage
7. Gap audit (@ch-gap-master) — todo.md current, mocks graduated, no workarounds
8. Docs review (@ch-doc-writer) — indexes updated, docs/ suite current
9. Real-auth test exists for new auth-protected endpoints
10. Contract test exists for new UI-facing response shapes
11. Cleanup phase completed after implementation chunk (if applicable)

## Key Conventions {#key-conventions}

- ~100 columns; type hints on new signatures; match surrounding style
- No mocks in `src/` — only in `tests/`
- No placeholders, stubs, or `NotImplementedError` in production code
- All API keys via `${ENV_VAR}` — never hardcode secrets
- Write decisions to files immediately — never defer to session end
- New prose docs are GMD — lint with `./scripts/lint-gmd.sh` (zero errors before commit)

## Lookup Priority {#lookup-priority}

| Need | Consult First | Then |
|------|---------------|------|
| Prior work | `handoff.md` + `workflow/past_handoffs/` | Indexes |
| Code structure | `rmx context <symbol>` / `rmx grep` | Source files |
| Architecture | `docs/architecture/ARCHITECTURE_INDEX.md` | `docs/ARCHITECTURE.md`, `docs/SYSTEM.md`; ADRs `docs/adr/` |
| Patterns | `workflow/QUICK_REFERENCE.md` | `workflow/PATTERNS.md` |
| Symbol / call graph | `rmx context <symbol>` → `tldr` | `rmx grep` → raw grep |
| GMD authoring | `docs/gmd/PRIMER.md` | `docs/gmd/SPEC.md` |
| Gaps | `docs/architecture/todo.md` | — |
| Design research | `docs/architecture/explorations/` | Exploration docs |
| Active plans | `workflow/plan-of-plans.md` (index + sequence + Status) | `workflow/plans/` |
| Approved task specs | `workflow/plans/<plan>-tasks/` | Plan file in `workflow/plans/` (`status: approved`) |

## Session Start Checklist {#session-start-checklist}

1. Read `handoff.md`
2. Read `workflow/plan-of-plans.md` for what to implement next
3. Read `docs/architecture/ARCHITECTURE_INDEX.md`
4. Read `docs/architecture/README.md` for architecture overview
5. Verify git state matches handoff
6. Check `docs/architecture/todo.md`
7. If implementing: read the active plan from `workflow/plans/` (stage = its `metadata.status`)

## Planning Pipeline (Status-Tracked Lifecycle) {#planning-pipeline}

```
Exploration (research) → Proposed Plan (decisions) → ADR (if architectural) → Task Specs → Implementation
```

All plans live permanently in `workflow/plans/<plan-name>.md`; the stage is the `metadata.status`
frontmatter field (plans never move directories):

**`drafting`** — no task specs yet
**`approved`** — task specs written under `workflow/plans/<plan>-tasks/`, ready to implement
**`in-progress`** — implementation underway
**`completed`** — shipped and verified (file stays put)

- Write proposed plans to `workflow/plans/` with `status: drafting` BEFORE presenting questions
- After plan approval: create ALL task spec files in `workflow/plans/<plan>-tasks/` and set
  `status: approved` before implementing any task
- `workflow/plan-of-plans.md` is the index + source of truth for execution order
