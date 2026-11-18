---
gmd: "0.1"
id: agent-brief-iso-bug285
title: "Isolated agent brief: bug-285 — a non-dict snapshot graph is said, not silently skipped"
tags: [agent-brief, isolated, bug-285, stm]
metadata:
  node_type: brief
  created: 2026-11-18
---

# bug-285: a non-dict snapshot graph is said {#root}

You are an isolated small-fix agent (L174/L176) in your own clone of refmatrix: one agent writes
the test and the fix, test seen failing first. Read `CLAUDE.md` `#test-discipline` and
`#no-silent-failures` first, and bug-285's row in `workflow/bug_registry.md`.

rel: implements -> [[bug_registry]]

## The bug {#bug}

`src/refmatrix/stm.py` `pre_prompt_state`: the snapshot (`<session>.pre.json`) graph's shape is
checked only inside `if close and isinstance(pre.get("graph"), dict):`. A snapshot whose `graph` is
not an object (`[]`, `5`, `"x"`) skips `focus_graph_problem` and falls back to the live state
WITHOUT `_say_corrupt` (bug-268's one stderr line per process). A wrong-shaped OBJECT is already
said. {#bug-body}

## Do {#do}

1. RED: extend `tests/test_injection_capture.py::test_a_corrupt_snapshot_graph_falls_back_to_the_live_state`
   (parametrize it; do not add a new file) with non-dict snapshot graphs (`[]`, `5`). Through the
   real entry point (scan-prompt, as the existing case does): exit 0, the live state read, and the
   stderr line containing "focus graph" and "corrupt" naming the pre.json file. Run it and see the
   new cases FAIL for the intended reason (no stderr line). Keep that log.
2. GREEN: a non-dict `graph` in a close-enough snapshot goes through `_say_corrupt(s._pre_path(),
   …)` and the live state, exactly like a wrong-shaped object. Minimal change; docstring names
   bug-285 and the date.
3. Run `tests/test_injection_capture.py tests/test_stm_composite_members.py tests/test_composite.py`
   with `~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider` (`PYTHONPATH=src`), all green.
4. Mutation: revert your src change only, re-run the new cases, they fail; restore.
5. Update bug-285's row in `workflow/bug_registry.md`: fix text and status `fixed` (cite your commit
   after committing, in a second commit).

## Report {#report}

In the REPORT.md the prompt names: commit shas, the RED E line, the GREEN counts, the mutation result.
