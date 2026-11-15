# ch-test-engineer — refmatrix overlay

## Environment

- Runner: `.venv-eval/bin/python -m pytest` (Python 3.14, no Docker). Output MUST be captured:
  `2>&1 | tee workflow/review-output/<name>.log`.
- Full suite ~60 min / ~5,000 tests; never run it on a branch. Verify with the task's tests plus every
  importer of a changed module, through `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`.
- A fold adds to the feature's existing test file; no new per-round `*_r<n>` / `*remedy*` file
  (`workflow/ORCHESTRATION.md#task-tests`).
- Daemon tests: use a SHORT `tempfile.mkdtemp()` root (unix socket `sun_path` limit); never point
  a test at a real `.refmatrix/`.
- Store fixtures: open a `Store` on a tmp root; daemon-up paths are exercised with a spawned
  test daemon (see `tests/test_daemon*.py` patterns), not by monkeypatching `daemon.ping`.

## RED discipline

- A test for a bridge / hook / verb must exercise the REAL path: write a file, run the function,
  read the store row (`get_memory`) or render the hook block and compare to the installed file.
- Monkeypatching the function under test is forbidden (`workflow/bullshit/IMPRESSIONS.md`
  imp-mock-the-sut). Mocks of external services only; register them in
  `workflow/test_mock_registry.md`.
- Mutation check before calling a test done: break the code path it claims to cover and confirm
  the test fails.

## Known pre-existing failure

`tests/test_graph_landing.py::test_context_op_honors_partition_under_ambient_drift` — stub daemon
lacks `_st` (bug registry). Fix it; do not skip it.

## Self-audit before you report done (mandatory, L166)

Answer the eight questions in `workflow/SELF_AUDIT.md` in your summary, using its `## Self-audit`
form, with evidence (command + output, grep list, test node). "N/A" needs a reason. An
unanswered question blocks the merge. The questions are ch-bsd's recurring findings: running the
real path, the test reaching the wiring, the census of callers and siblings, the whole path
bounded, busy is not absent, the guard can fire, failures loud, nothing handed off on paper.
