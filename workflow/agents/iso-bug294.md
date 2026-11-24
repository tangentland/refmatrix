---
gmd: "0.1"
id: agent-brief-iso-bug294
title: "Isolated agent brief: bug-294 — relaunch-fleet prints store paths unwrapped"
tags: [agent-brief, isolated, bug-294, cli]
metadata:
  node_type: brief
  created: 2026-11-23
---

# bug-294: `rmx hub relaunch-fleet` never wraps a store path {#root}

You are an isolated small-fix agent (L174/L176) in your own clone: one agent writes the test and
the fix, test seen failing first. Read `CLAUDE.md` `#test-discipline` and bug-294's row in
`workflow/bug_registry.md`.

rel: implements -> [[bug_registry]]

## The bug {#bug}

`rmx hub relaunch-fleet` prints each store path through rich, which wraps at the terminal width:
in a narrow tty a long path splits mid-word (`.ref\nmatrix`). A user copying it gets a broken
path, and `tests/test_plan4_remedy.py::test_relaunch_fleet_relaunches_every_supervised_store`
fails when run in a narrow terminal (an agent's tmux pane). {#bug-body}

## Do {#do}

1. RED: in `test_relaunch_fleet_relaunches_every_supervised_store` (extend it; no new file), run
   the command at a narrow width (`COLUMNS=40` in the CliRunner env, or the `terminal_width`
   the runner supports) and assert each full store path appears unbroken in the output. It must
   FAIL at base; keep the E line.
2. GREEN: `relaunch-fleet` (in `src/refmatrix/cli.py`) prints store paths unwrapped
   (`soft_wrap=True`, `overflow="ignore"`/`no_wrap`, or plain `click.echo` for the path lines).
   Then look for other `cli.py` printers of store paths in the same command family (`hub
   status`, `daemon list`): if one wraps the same way, fix it the same way and extend its test
   too; list what you checked. Docstring names bug-294 and the date.
3. Run `tests/test_plan4_remedy.py tests/test_docs_generated.py tests/test_verb_parity.py
   tests/test_suite_discipline.py` with
   `PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee ../bug294.log`,
   all green. Any background wait has a deadline.
4. Mutation: revert your src change only, re-run the new assertion: it fails; restore.
5. Update bug-294's row: fix text and status `fixed` (cite your commit in a second commit).

## Report {#report}

In the REPORT.md the prompt names: commit shas, the RED E line, the GREEN counts, the mutation
result, the printers checked.
