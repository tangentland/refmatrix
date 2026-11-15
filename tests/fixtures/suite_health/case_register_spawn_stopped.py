"""AC-5, last sentence, the control: a fixture registered through `rmx_sandbox.register_spawn`
whose teardown stops its daemon passes, and the session exits 0."""
import shutil

import pytest

import rmx_sandbox
from refmatrix import daemon as dm
from suite_health_support import report, store_root


@pytest.fixture
def owned_daemon():
    base, root = store_root("shr-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    rmx_sandbox.register_spawn(pid, root, "case: a fixture that owns a daemon and stops it")
    yield root
    assert dm.stop_daemon(root)
    shutil.rmtree(base)


def test_uses_the_owned_daemon(owned_daemon):
    assert dm.ping(owned_daemon)
