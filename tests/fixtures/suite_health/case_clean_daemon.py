"""AC-5 case 2: a test that stops its daemon properly. The inner session exits 0 and prints no
`LEAKED` line (the reaper has no false positive on a clean spawn)."""
import shutil

from refmatrix import daemon as dm
from suite_health_support import report, store_root


def test_stops_its_daemon():
    base, root = store_root("shc-")
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    report(pid=pid, root=str(root), base=str(base))
    try:
        assert pid > 0 and dm.ping(root)
    finally:
        assert dm.stop_daemon(root)
        shutil.rmtree(base)
