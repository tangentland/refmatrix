"""AC-5 case 5: an in-process `Daemon` left serving. Built and served inside the pytest process
(so it never appears in the spawn ledger), it must be found through conftest's weak registry of
`Daemon` instances (task-29.4 `#r4` item 6), reported `LEAKED IN-PROCESS DAEMON`, stopped, and
must fail the session.

Nothing is replaced: since bug-267's fix (L169) `serve_forever` off the main thread leaves the
host's signals alone, so the real daemon serves on a plain thread. The serve thread is a daemon
thread so a session whose reaper does nothing still exits (the outer test reads that as RED, not
as a hang)."""
import threading
import time

from refmatrix import daemon as dm
from suite_health_support import report, store_root

_PING_WAIT_S = 120.0     # hang guard for the boot, not a bound under test


def test_leaves_an_in_process_daemon_serving():
    base, root = store_root("shi-")
    d = dm.Daemon(root)
    t = threading.Thread(target=d.serve_forever, name="case-inproc-serve", daemon=True)
    t.start()
    deadline = time.monotonic() + _PING_WAIT_S
    while not dm.ping(root, retries=0) and time.monotonic() < deadline and t.is_alive():
        time.sleep(0.2)
    report(root=str(d.root), base=str(base))
    assert dm.ping(root, retries=0), "the in-process daemon never answered ping"
