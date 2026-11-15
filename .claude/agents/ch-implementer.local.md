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

## Self-audit before you report done (mandatory, L166)

Answer the eight questions in `workflow/SELF_AUDIT.md` in your summary, using its `## Self-audit`
form, with evidence (command + output, grep list, test node). "N/A" needs a reason. An
unanswered question blocks the merge. The questions are ch-bsd's recurring findings: running the
real path, the test reaching the wiring, the census of callers and siblings, the whole path
bounded, busy is not absent, the guard can fire, failures loud, nothing handed off on paper.

## Tests you write (small fixes) and the discipline (CLAUDE.md #test-discipline)

On the **small-fix path** ([ORCHESTRATION #task-small]) you write the test AND the fix: this
overrides "authors no tests" in the neutral definition. Follow CLAUDE.md #test-discipline: extend
the feature's existing test file (no per-fix file), go through the entry point, no patched daemon
state, no real waits, and show the test failing before the fix by its E line. On the large path
you still write no tests.
