# ch-implementer — refmatrix overlay

- Production code lives in `src/refmatrix/`. New agent-facing capability: add a `@verb` in
  `verbs.py`, then expose via `mcp.py` TOOLS and `cli.py` — never implement in the adapter.
- New daemon op: `_op_<name>` in `daemon.py` + register in `OPS` (and `CLI_OPS` only if it is a
  fast read). Writes go through the store under `d._store_lock`.
- Hooks: change `hooks.py` / `search_hooks.py` templates + tests, then `rmx install-hooks --apply`
  in this repo so `.claude/settings.json` matches; never hand-edit the rmx block.
- Version bump in `pyproject.toml` AND `src/refmatrix/__init__.py` for every shipped change.
- Docstrings carry the WHY and the incident date. No `2>/dev/null`/`|| true` in generated
  memory-path hooks; no bare `except: pass` on write paths.
- Verify with `.venv-eval/bin/python -m pytest <file> 2>&1 | tee workflow/review-output/<name>.log`.
  Do not run `.venv-eval/bin/rmx` against the live store.
