"""bug-269 (ruling L161): a daemon's stop waits out the startup model warm-up.

green-t03's diagnosis: `Daemon._close_workers` -> `WorkerClient.retire()` takes the worker's
`_lock`, which the warm thread holds for the whole cold load. A stop sent during warm-up took
5.0-5.5 s, and 1.9 s after it (T0.3 base sweep: `graceful_stop(grace=10)` returned False at
10.0 s in L3 trials 5-9, all of L5 and L8 trials 1-3).

The node holds the warm-up open on purpose. A preload (`$RMX_SANDBOX_PRELOAD`, run in every
sandboxed child) wraps `refmatrix.embedder.Embedder.__init__` in the EMBED WORKER process only.
The wrapper writes `held`, then waits for a `release` file the test never writes, for at most
`HOLD_S`, then writes `released` and loads the real model. Nothing in the daemon or in
`WorkerClient` is patched: they are the unit under test.

The check is an ordering outcome (29.4 R3, class C), with no clock assertion: once the stop op
is sent, the daemon process must exit WHILE the warm-up is still held, i.e. before `released`
exists. A stop that waits out the warm-up exits only after the hold ends. A local hang guard
bounds the wait; it raises and never asserts on time.

RED at base: the daemon exits after the hold is released (`HOLD_S` = 20 s), so `released`
exists first.
"""
from __future__ import annotations

import os
import textwrap
import time
from pathlib import Path

from refmatrix import daemon as dm

from tests import task21_1_support as h

# The held warm-up: far longer than a stop that does not wait on it (green-t03: 1.9 s after
# warm-up), so the ordering cannot be won by luck.
HOLD_S = 20.0
# Hang guard for each wait: the hold, the real model load after it, and the exit. A guard, not
# a bound under test.
_GUARD_S = HOLD_S + 120.0

_PRELOAD = r'''
"""bug-269 RED preload: hold the embed worker's cold load open (registered in
workflow/test_mock_registry.md). Acts only in `python -m refmatrix.embed_worker --role embed`."""
import os, sys, time
from pathlib import Path

argv = list(getattr(sys, "orig_argv", sys.argv))
if "refmatrix.embed_worker" in argv and "embed" in argv[argv.index("--role") + 1:][:1]:
    import refmatrix.embedder as _emb
    _d = Path(os.environ["T269_HOLD_DIR"])
    _hold_s = float(os.environ["T269_HOLD_S"])
    _real = _emb.Embedder.__init__
    _parent = os.getppid()

    def _held_init(self, *a, **kw):
        (_d / "held").write_text(str(os.getpid()))
        end = time.monotonic() + _hold_s
        while time.monotonic() < end and not (_d / "release").exists():
            if os.getppid() != _parent:          # the daemon is gone: nothing to load for
                os._exit(0)
            time.sleep(0.05)
        (_d / "released").write_text(str(os.getpid()))
        return _real(self, *a, **kw)

    _emb.Embedder.__init__ = _held_init
'''


def _wait(pred, what: str, d: "h.SandboxDaemon") -> None:
    end = time.monotonic() + _GUARD_S
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError(f"hang guard: {what} did not happen; daemon rc={d.proc.poll()}; "
                         f"log tail: {(d.root / 'rmxd.log').read_text()[-1500:]}")


def test_bug269_a_stop_during_warmup_does_not_wait_out_the_warmup():
    root = Path(os.environ["REFMATRIX_ROOT"])
    hold = root.parent / "t269-hold"
    hold.mkdir()
    pre = root.parent / "t269_preload.py"
    pre.write_text(textwrap.dedent(_PRELOAD))
    d = h.SandboxDaemon(root, RMX_SANDBOX_PRELOAD=str(pre), T269_HOLD_DIR=str(hold),
                        T269_HOLD_S=str(HOLD_S))
    try:
        _wait(lambda: (hold / "held").exists(), "the embed worker entering its held warm-up", d)
        assert d.proc.poll() is None, "the daemon exited before the stop was sent"
        dm.call(root, "stop", {}, timeout=2.0, retries=0)
        _wait(lambda: d.proc.poll() is not None or (hold / "released").exists(),
              "the daemon exiting or the warm-up hold ending", d)
        exited_first = d.proc.poll() is not None and not (hold / "released").exists()
        if not exited_first:
            _wait(lambda: d.proc.poll() is not None, "the daemon exiting after the hold", d)
        assert exited_first, (
            f"bug-269: the stop waited out the warm-up: the embed worker's load was released "
            f"(after the {HOLD_S:.0f} s hold) before the daemon exited (rc={d.proc.returncode}); "
            f"log tail: {(root / 'rmxd.log').read_text()[-1200:]}")
    finally:
        (hold / "release").write_text("1")
        d.stop()
