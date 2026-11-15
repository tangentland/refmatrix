"""bug-267 (ruling L151): an in-process daemon stopped through its `stop` op or its `_stop` flag
must END ITS SERVE THREAD, not the process. At c4b44d0 `Daemon.serve_forever` always finished
with `os._exit(0)` (daemon.py ~2220), so stopping an in-process daemon killed the host pytest
with exit 0 before its summary: green-t02's registry reaper measured exactly that
(`green-wip-reaper-1.log`).

Three tests, in order: a stop through the `stop` op, a stop through the `_stop` flag, and a
DELIBERATE failure, so the session's own status (1) is distinguishable from `os._exit(0)`.

ch-bsd T0.2 r1 B1 (ruling L169): NO `signal.signal` double. The serve thread runs the REAL
`serve_forever`, so what production does off the main thread is what is tested. At 1121b4e
`serve_forever` installed its SIGTERM/SIGINT handlers unconditionally, which Python refuses off
the main thread (`ValueError: signal only works in main thread of the main interpreter`): the
in-host return path ran only because these cases swapped `signal.signal`. The serve thread's own
exception is captured and asserted first, so that is the E line, not a ping timeout.
Since the fix (L169) `serve_forever` off the main thread installs no signal handlers (the
host owns its signals), so the real daemon serves on a plain thread."""
import json
import os
import shutil
import threading
import time
from pathlib import Path

from refmatrix import daemon as dm
from suite_health_support import store_root

_PING_WAIT_S = 120.0     # hang guards for the boot and the stop, not bounds under test
_STOP_WAIT_S = 120.0


def _note_base(base: Path) -> None:
    """Append `base` to `$RMX_CASE_INFO` so the outer test removes it whatever happens here."""
    p = Path(os.environ["RMX_CASE_INFO"])
    d = json.loads(p.read_text()) if p.is_file() else {}
    d.setdefault("bases", []).append(str(base))
    p.write_text(json.dumps(d))


def _serve(prefix: str):
    """A REAL `Daemon` served by its REAL `serve_forever` on a non-main thread, no double; the
    serve thread's exception (if any) is kept and asserted before the ping."""
    base, root = store_root(prefix)
    _note_base(base)
    d = dm.Daemon(root)
    errors: list = []

    def _run():
        try:
            d.serve_forever()
        except BaseException as exc:    # the thread's own failure is the finding, not a hang
            errors.append(exc)
            raise

    t = threading.Thread(target=_run, name=f"case-{prefix}serve", daemon=True)
    t.start()
    deadline = time.monotonic() + _PING_WAIT_S
    while not dm.ping(root, retries=0) and time.monotonic() < deadline and t.is_alive():
        time.sleep(0.2)
    assert not errors, (f"serve_forever off the main thread raised "
                        f"{type(errors[0]).__name__}: {errors[0]}")
    assert dm.ping(root, retries=0), "the in-process daemon never answered ping"
    return base, root, d, t


def test_the_stop_op_ends_the_serve_thread_not_the_process():
    base, root, d, t = _serve("s67o-")
    r = dm.call(root, "stop", {}, retries=0)
    assert r.get("ok", True), r
    t.join(_STOP_WAIT_S)
    assert not t.is_alive(), "the serve thread did not end after the stop op"
    assert not dm.ping(root, timeout=0.5, retries=0), "the socket still answers after stop"
    shutil.rmtree(base)


def test_the_stop_flag_ends_the_serve_thread_not_the_process():
    base, root, d, t = _serve("s67f-")
    d._stop = True
    t.join(_STOP_WAIT_S)
    assert not t.is_alive(), "the serve thread did not end after `_stop = True`"
    assert not dm.ping(root, timeout=0.5, retries=0), "the socket still answers after stop"
    shutil.rmtree(base)


def test_zz_the_session_keeps_its_own_status():
    assert False, "deliberate: the session must end with pytest's own status (1), not exit 0"
