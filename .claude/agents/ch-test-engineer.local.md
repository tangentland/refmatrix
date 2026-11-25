# ch-test-engineer — refmatrix overlay

## Environment

- Runner: `.venv-eval/bin/python -m pytest`, the host venv (Python 3.14). No container: the
  neutral definition's execution section defers to this line. Output MUST be captured:
  `2>&1 | tee workflow/review-output/<name>.log`.
- Never run the full suite on a branch. Verify with the task's tests plus every importer of a
  changed module, run as `CLAUDE.md` `#test-discipline` rule 9 says (an isolated lane slot on a
  committed sha).
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
- Mutations come after GREEN, on the `src/` change only; RED runs them (L200); none on the small
  path (`workflow/ORCHESTRATION.md` `#task`).

## Known pre-existing failure

`tests/test_graph_landing.py::test_context_op_honors_partition_under_ambient_drift` — stub daemon
lacks `_st` (bug registry). Fix it; do not skip it.

## Self-audit before you report done (mandatory, L166)

Answer the eight questions in `workflow/SELF_AUDIT.md` in your summary, using its `## Self-audit`
form, with evidence (command + output, grep list, test node). "N/A" needs a reason. An
unanswered question blocks the merge. The questions are ch-bsd's recurring findings: running the
real path, the test reaching the wiring, the census of callers and siblings, the whole path
bounded, busy is not absent, the guard can fire, failures loud, nothing handed off on paper.

## RED is the second view, not a second typist (L167)

The spec's ACs are the floor. Write RED from `workflow/SELF_AUDIT.md` as well: for a large change,
at least (1) one test through the entry point users call (CLI / verb / daemon op / hook), not the
helper; (2) one test with the daemon or worker BUSY or slow, run on a real test daemon, never by
patching `ping`/`daemon.call`; (3) one census test that fails when `src/` gains a new caller,
output path or construction outside the fix (an allowlist, not a hand count). Never patch the
value a guard reads. If the spec misses a case these find, say so in the RED report; that
gap is a finding, not scope creep.

## Test discipline (CLAUDE.md #test-discipline, L168)

You own it. Rules 1 (extend, don't add; parametrize variants), 4 (real states, no patched
ping/call/guard input) and 6 (no real waits) are the ones most often broken: check each new test
against all nine before you commit. A new test file needs a reason in your report (a new feature,
not a new round).
