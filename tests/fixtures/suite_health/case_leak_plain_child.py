"""R4's first sentence: EVERY process the suite starts is known, and one still alive at the end
fails the run -- not only daemons. A plain Python child (not a daemon) started and abandoned.
Its ledger line carries the per-test `REFMATRIX_ROOT` the sandbox gives every child, so a root
in the ledger does not make the pid that root's daemon: `stop_daemon(root)` finds no daemon
there and stops nothing. The reaper must still stop the pid."""
import subprocess
import sys

from suite_health_support import report


def test_abandons_a_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    report(pid=child.pid)
