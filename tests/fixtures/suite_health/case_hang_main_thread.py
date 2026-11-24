"""task-29.4a fixture (bsd-294a r1 m-1, ruling L197): a test that hangs in its MAIN thread.

pytest-timeout's `signal` method fails it after a 2 s test-sized budget, and prints no
`+++ Timeout +++` banner: there is one thread, so the runner's banner watcher never takes its
process snapshot. Copied into a throwaway checkout as a `test_*.py` by
tests/test_ptest_runner.py; never collected here (`case_*.py`). The sleep is never reached in
full: the timeout is the bound."""
import time

import pytest


@pytest.mark.timeout(2, method="signal")
def test_hangs_in_its_main_thread():
    time.sleep(30)
