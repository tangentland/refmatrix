"""AC-5 case 4, first half: a run killed with SIGKILL mid-test. This test starts a real daemon,
reports it, and waits to be killed by the outer test; its session never reaches teardown, so its
sandbox root, its ledger and its daemon are left behind (bug-229's most likely cause)."""
import time

from refmatrix import daemon as dm
from suite_health_support import report, store_root


def test_spawns_and_waits_to_be_killed():
    base, root = store_root("shk-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    time.sleep(600)
