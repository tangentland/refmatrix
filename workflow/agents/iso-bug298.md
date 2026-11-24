---
gmd: "0.1"
id: agent-brief-iso-bug298
title: "Isolated agent brief: bug-298 — diagnose and fix the HF_HUB_OFFLINE restore test"
tags: [agent-brief, isolated, bug-298, models, offline]
metadata:
  node_type: brief
  created: 2026-11-23
---

# bug-298: the hub-offline constant is not restored {#root}

You are an isolated small-fix agent (L174/L176) in your own clone. Read `CLAUDE.md`
`#test-discipline`, bug-298's row and bug-087's row in `workflow/bug_registry.md`, and the
standing rule that models load cache-only (no implicit external calls; `HF_HUB_OFFLINE`).

rel: implements -> [[bug_registry]]

## The bug {#bug}

`tests/test_models_offline.py::test_the_hub_constant_is_restored_after_the_offline_tests` fails
with the file run alone, on both lanes: `assert constants.HF_HUB_OFFLINE is want` →
`AssertionError: assert False is True`. Undiagnosed. {#bug-body}

## Do {#do}

1. **Diagnose first, and write it down before changing anything.** Run the file alone and read
   the test: what `want` is, where it comes from (env at session start? a fixture?), who sets
   `HF_HUB_OFFLINE` (the env var and the `huggingface_hub.constants` module attribute, which is
   read once at import), and what the offline tests restore. Decide which is wrong: the test's
   expectation, the restore, or production code (`src/refmatrix/` sets the offline flag
   somewhere: find it). If production code fails to make the hub offline, that is a real
   breach of the cache-only rule: STOP and put it in REPORT.md before fixing, with the E line
   and the code path.
2. If it is test-side: fix the test (the restore, or the expectation) so it asserts the true
   contract, and show it would fail if the contract broke (a mutation of the restore or of the
   production offline setting turns it red). If it is production-side and small: RED first (the
   existing test is the RED), then the fix, docstring naming bug-298 and the date.
3. Run `tests/test_models_offline.py` plus every test file that greps for `HF_HUB_OFFLINE`, and
   `tests/test_suite_discipline.py`, with
   `PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee ../bug298.log`.
   Any background wait has a deadline.
4. Update bug-298's row with the root cause, the fix and `fixed` (cite your commit in a second
   commit), or leave it `open` with the diagnosis if you stopped at step 1.

## Report {#report}

In the REPORT.md the prompt names: the diagnosis (cause, where), commit shas, the E lines
before and after, the mutation result.
