"""Per-project scheduled maintenance, run by the hub.

A small config (`~/.refmatrix/schedule.json`) maps a store root to a set of
{op: interval_seconds}. The hub's scheduler thread runs each op via the `rmx`
CLI (which routes through the project daemon) when its interval elapses and the
daemon is up — so graphs never drift stale and the no-op ingest tax is paid on a
cadence, not on every hook. Ops: sync, embed, vacuum, checkpoint, ingest.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from refmatrix.taxonomy import user_home

SCHEDULE_FILE = "schedule.json"
ALLOWED_OPS = ("sync", "embed", "vacuum", "checkpoint", "ingest")
TICK_S = float(os.environ.get("RMX_SCHED_TICK", "30"))


def schedule_path() -> Path:
    return user_home() / SCHEDULE_FILE


def load_schedule() -> dict:
    p = schedule_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_schedule(data: dict) -> None:
    p = schedule_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def add_job(root: Path, op: str, interval_s: int) -> dict:
    if op not in ALLOWED_OPS:
        raise ValueError(f"op must be one of {ALLOWED_OPS}")
    data = load_schedule()
    key = str(Path(root).resolve())
    data.setdefault(key, {})[op] = int(interval_s)
    save_schedule(data)
    return data


def remove_job(root: Path, op: str) -> bool:
    data = load_schedule()
    key = str(Path(root).resolve())
    if key in data and op in data[key]:
        del data[key][op]
        if not data[key]:
            del data[key]
        save_schedule(data)
        return True
    return False


class Scheduler:
    """Runs scheduled ops on a tick. Tracks last-run in memory (resets on hub
    restart — a missed window just runs on the next tick)."""

    def __init__(self, tick: float = TICK_S):
        self.tick = tick
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict[str, float] = {}
        self._now = time.time  # injectable for tests

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="rmx-hub-sched",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:
                pass
            self._stop.wait(self.tick)

    def due(self, now: float | None = None) -> list[tuple[str, str, int]]:
        """Return [(root, op, interval)] whose interval has elapsed."""
        now = now if now is not None else self._now()
        out = []
        for root, ops in load_schedule().items():
            for op, interval in ops.items():
                last = self._last.get(f"{root}|{op}")
                if last is None or now - last >= interval:  # never-run → due now
                    out.append((root, op, interval))
        return out

    def tick_once(self, now: float | None = None) -> list[tuple[str, str]]:
        from refmatrix import daemon as daemon_mod
        now = now if now is not None else self._now()
        ran = []
        for root, op, _interval in self.due(now):
            rp = Path(root)
            if not daemon_mod.ping(rp):
                continue
            self._run(rp, op)
            self._last[f"{root}|{op}"] = now
            ran.append((root, op))
        return ran

    def _run(self, root: Path, op: str) -> None:
        args = [sys.executable, "-m", "refmatrix.cli", op]
        if op == "ingest":
            args.append(".")
        env = {**os.environ, "REFMATRIX_ROOT": str(root),
               "RMX_INVOCATION_SOURCE": "internal"}
        subprocess.Popen(args, cwd=str(root.parent), env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
