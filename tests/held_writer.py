"""A REAL daemon whose writer lock the test holds (task-hook-writes-queue RED, 2026-11-24).

Not a test module (no `test_` prefix): the harness `tests/test_plan2_remedy.py`,
`tests/test_save_state.py` and `tests/test_hook_writes.py` share for the hook-writes queue
(23.1 R11 on an interim spool; bug-309, bug-177).

WHY this harness and not `_PingOnlyDaemon`. bug-309's failure is a real daemon whose single
writer (`Daemon._store_lock`, the real `_FairLock`) is held by other work while the Stop hook's
`focus summarize --promote` waits on it: 72 of 136 promotes timed out at 8.04 s (measured
2026-11-24). `_PingOnlyDaemon` is a socket that answers `ping` and never answers anything else,
so it cannot show what the fix is about: the timed-out dial that is still queued inside the
daemon and LANDS when the writer frees, the drain on the daemon's own flush tick, the boot drain
after a crash. CLAUDE.md test discipline rule 4: busy / held behaviour runs on a real daemon,
never a patched `ping` / `daemon.call` / `daemon_status`.

What it is: `Daemon(root).serve_forever()` on the main thread of a CHILD process (the daemon a
user runs is its own process too, so SIGKILL is a real daemon death), plus ONE test-owned thread
in that child that acquires and releases the real `d._store_lock` when a control file appears and
disappears. Nothing below the socket is faked: the dispatcher, the ops, the flush tick, the
snapshot tick and the Store are the shipped ones. The holder is the only seam, registered in
`workflow/test_mock_registry.md`; 23.2's lock-hold fixture (`tests/lockhold.py`, not built yet)
replaces it when it lands.

The child's argv carries `rmx-held-writer` so `discovery.pid_is_rmx` reads it as an rmx process,
as it reads a real daemon's (`.../bin/rmx daemon start`).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from tests.task21_1_support import rmx_env
from tests.timing import HANG_GUARD_S, wait_for

_CHILD = r'''
import sys, threading, time
from pathlib import Path
from refmatrix import daemon as dm

root, ctl = Path(sys.argv[2]), Path(sys.argv[3])
d = dm.Daemon(root)


def _holder():
    held = False
    while True:
        want = (ctl / "hold").exists()
        if want and not held:
            d._store_lock.acquire()
            held = True
            (ctl / "held").write_text("1")
        elif held and not want:
            (ctl / "held").unlink()
            d._store_lock.release()
            held = False
        time.sleep(0.01)


threading.Thread(target=_holder, name="test-writer-holder", daemon=True).start()
d.serve_forever()
'''

# No model loads in a held-writer test: nothing here embeds or reranks, and a cold private
# worker load (~7-8 s, bug-184 r6) is exactly the kind of wait the suite must not sit out.
QUIET_ENV = {"RMX_NO_EMBED_WARMUP": "1", "RMX_RERANK": "0"}


class HeldWriterDaemon:
    """A real daemon child on `root` whose `_store_lock` the test holds with `hold()` and frees
    with `release()`. `flush_s` is the child's `RMX_DAEMON_FLUSH_S`: the flush tick that runs
    the hook-writes drain (D2). A test that must see the BOOT drain alone passes 3600."""

    def __init__(self, root: Path, *, flush_s: float = 1.0, **extra):
        from refmatrix import daemon as dm
        self.root = Path(root)
        self.ctl = self.root.parent / "held-writer.ctl"
        self.ctl.mkdir(exist_ok=True)
        for f in ("hold", "held"):
            (self.ctl / f).unlink(missing_ok=True)
        self.env = rmx_env(self.root, RMX_DAEMON_FLUSH_S=flush_s, **{**QUIET_ENV, **extra})
        self.log = open(self.root.parent / "held-writer.stderr.log", "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD, "rmx-held-writer", str(self.root), str(self.ctl)],
            env=self.env, cwd=str(self.root.parent), stdout=self.log, stderr=subprocess.STDOUT)
        try:
            wait_for(lambda: self.proc.poll() is not None or dm.ping(self.root, timeout=0.5,
                                                                     retries=0),
                     what=f"the held-writer daemon on {self.root} to answer ping")
        except AssertionError:
            self.stop()
            raise
        if self.proc.poll() is not None:
            self.log.close()
            raise RuntimeError(f"held-writer daemon exited rc={self.proc.returncode} before "
                               f"it answered: {self.stderr_tail()}")

    @property
    def pid(self) -> int:
        return self.proc.pid

    def stderr_tail(self, n: int = 3000) -> str:
        p = self.root.parent / "held-writer.stderr.log"
        return p.read_text(errors="replace")[-n:] if p.exists() else ""

    def hold(self) -> None:
        (self.ctl / "hold").write_text("1")
        wait_for(lambda: (self.ctl / "held").exists() or self.proc.poll() is not None,
                 what="the holder thread to take the daemon's _store_lock")
        assert self.proc.poll() is None, f"daemon died taking the hold: {self.stderr_tail()}"

    def is_held(self) -> bool:
        return (self.ctl / "held").exists()

    def release(self) -> None:
        (self.ctl / "hold").unlink(missing_ok=True)
        wait_for(lambda: not (self.ctl / "held").exists() or self.proc.poll() is not None,
                 what="the holder thread to release the daemon's _store_lock")

    def kill(self) -> None:
        """A real daemon death: SIGKILL, no shutdown path runs."""
        if self.proc.poll() is None:
            os.kill(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=HANG_GUARD_S)
        self.log.close()

    def stop(self) -> None:
        (self.ctl / "hold").unlink(missing_ok=True)
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=HANG_GUARD_S)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=HANG_GUARD_S)
        if not self.log.closed:
            self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


# ---- shared readers -----------------------------------------------------------------------------

SPOOL = "hook_writes.spool"


def spool_dir(root: Path) -> Path:
    return Path(root) / SPOOL


def spool_files(root: Path) -> list[Path]:
    """The pending entries: `*.json` directly in the spool dir (not `bad/`, not `*.tmp`)."""
    d = spool_dir(root)
    return sorted(p for p in d.glob("*.json") if p.is_file()) if d.is_dir() else []


def facts_events(root: Path, *, op: str, name: str) -> list[dict]:
    """facts.log events of `op` for `name`, in log order."""
    import json
    from refmatrix.store import LOG_FILENAME
    p = Path(root) / LOG_FILENAME
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("op") == op and ev.get("name") == name:
            out.append(ev)
    return out


def flat(text: str) -> str:
    """Whitespace-normalised text: rich wraps long lines at the console width."""
    return " ".join(text.split())
