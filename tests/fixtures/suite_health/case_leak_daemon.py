"""AC-5 case 1 (bug-229's shape): a test starts a REAL daemon with `spawn_daemon_subprocess` on a
root made by `mkdtemp(dir="/tmp")`, outside the inner sandbox root, and never stops it. The test
itself passes; the inner session must fail, name it `LEAKED PROCESS` and stop it."""
from refmatrix import daemon as dm
from suite_health_support import report, store_root


def test_leaks_a_daemon():
    base, root = store_root("shl-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    assert pid > 0 and dm.ping(root)
