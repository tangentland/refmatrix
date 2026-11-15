"""Ruling L142 on R4 items 2 and 6: the reaper never signals its own pid or an ancestor. An
in-process `Daemon` writes the PYTEST process's pid into its `rmxd.pid`, so a reaper that
stops it the way it stops a spawned daemon (`stop_daemon(root)`, whose last resort is a
signal to the pid file's pid, or SIGTERM to that pid) would SIGTERM the session itself. It must
be stopped through the weak `Daemon` registry instead.

Same serving setup as case_inprocess_daemon.py (a real daemon on a plain thread, nothing
replaced); this case also reports the pid file's pid, so the outer test can show the hazard is
real: it names this pytest process."""
import os
import threading
import time

from refmatrix import daemon as dm
from suite_health_support import report, store_root

_PING_WAIT_S = 120.0     # hang guard for the boot, not a bound under test


def test_leaves_an_in_process_daemon_whose_pid_file_names_this_session():
    base, root = store_root("sho-")
    d = dm.Daemon(root)
    t = threading.Thread(target=d.serve_forever, name="case-inproc-own-pid", daemon=True)
    t.start()
    deadline = time.monotonic() + _PING_WAIT_S
    while not dm.ping(root, retries=0) and time.monotonic() < deadline and t.is_alive():
        time.sleep(0.2)
    pidfile = dm.pid_path(d.root)
    report(root=str(d.root), base=str(base),
           pidfile=int(pidfile.read_text().strip()) if pidfile.is_file() else None)
    assert dm.ping(root, retries=0), "the in-process daemon never answered ping"
    assert int(pidfile.read_text().strip()) == os.getpid()
