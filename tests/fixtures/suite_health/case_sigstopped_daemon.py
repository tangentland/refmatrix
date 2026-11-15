"""AC-5 case 6: a daemon left SIGSTOPped (the `stopped` fixture of test_plan4_remedy.py; 25.1b
AC-28 leaves one). The reaper must SIGCONT it, stop it, report it and fail the session."""
import os
import signal

from refmatrix import daemon as dm
from suite_health_support import report, store_root


def test_leaves_a_stopped_daemon():
    base, root = store_root("shs-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    assert pid > 0 and dm.ping(root)
    os.kill(pid, signal.SIGSTOP)
