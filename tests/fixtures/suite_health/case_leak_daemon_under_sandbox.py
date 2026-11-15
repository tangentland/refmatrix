"""R4 item 4: teardown says what it left. A real daemon on a store root UNDER the inner sandbox
root, never stopped. The session-finish hook prints how many sandbox store roots still hold a
live `rmxd.pid` (counted when the hook starts, before anything is stopped or removed)."""
import os

from refmatrix import daemon as dm
from suite_health_support import report, store_root


def test_leaks_a_daemon_under_the_sandbox():
    base, root = store_root("s44-", under=os.environ["RMX_SANDBOX_ROOT"])
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    assert pid > 0 and dm.ping(root)
