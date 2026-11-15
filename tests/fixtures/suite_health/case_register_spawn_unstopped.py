"""AC-5, last sentence: a fixture registered through `rmx_sandbox.register_spawn` whose teardown
does NOT stop its daemon fails its own test, by name, before the session ends (task-29.4 `#r4`
item 7: a registered entry's teardown asserts the stop answered and the pid exited)."""
import pytest

import rmx_sandbox
from refmatrix import daemon as dm
from suite_health_support import report, store_root


@pytest.fixture
def owned_daemon():
    base, root = store_root("shr-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    rmx_sandbox.register_spawn(pid, root, "case: a fixture that owns a daemon and forgets it")
    yield root
    # teardown deliberately does NOT stop it


def test_uses_the_owned_daemon(owned_daemon):
    assert dm.ping(owned_daemon)


def test_runs_after():
    assert True
