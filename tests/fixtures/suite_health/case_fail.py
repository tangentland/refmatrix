"""task-29.4a fixture (AC-2, AC-9): one plain failure. Copied into a throwaway checkout as a
`test_*.py` by tests/test_ptest_runner.py; never collected here (`case_*.py`)."""


def test_fails_plainly():
    assert 1 == 2, "fixture: a plain failure"
