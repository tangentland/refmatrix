# ch-test-engineer — refmatrix overlay

## Environment

- Runner: `.venv-eval/bin/python -m pytest` (Python 3.14, no Docker). Output MUST be captured:
  `2>&1 | tee workflow/review-output/<name>.log`.
- Full suite ~13 min / ~1380 tests. Target a file or `-k` while iterating; run the full suite
  before merge.
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
