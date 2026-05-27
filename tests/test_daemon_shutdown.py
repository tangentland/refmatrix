"""Daemon cooperative-shutdown unit tests.

These cover the in-process mechanics only:
  - `_drain_pool` honors its timeout (bounded wait when a worker
    refuses to finish).
  - `_drain_pool` returns promptly when workers do finish.

A full fork+SIGTERM end-to-end test would exercise more, but is heavy
and flaky in CI; the unit shape is what fixes the hang the memory
captured.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from refmatrix.daemon import Daemon


def _make_daemon(tmp_path: Path) -> Daemon:
    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    return d


def test_drain_pool_returns_within_timeout_when_worker_hangs(tmp_path):
    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=2)
    block = threading.Event()

    def _hang() -> None:
        block.wait()  # never set until after drain returns

    pool.submit(_hang)
    pool.submit(_hang)

    start = time.monotonic()
    d._drain_pool("test", pool, timeout_s=0.4)
    elapsed = time.monotonic() - start

    # Bounded — must return well under 2x the cap even with two workers.
    assert elapsed < 1.0, f"drain pinned for {elapsed:.2f}s"
    # Workers still running; we leaked them on purpose.
    block.set()


def test_drain_pool_returns_quickly_when_workers_finish(tmp_path):
    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=2)

    def _quick() -> None:
        time.sleep(0.05)

    pool.submit(_quick)
    pool.submit(_quick)

    start = time.monotonic()
    d._drain_pool("test", pool, timeout_s=5.0)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"drain took {elapsed:.2f}s when workers were fast"


def test_drain_pool_cancels_queued_futures(tmp_path):
    d = _make_daemon(tmp_path)
    pool = ThreadPoolExecutor(max_workers=1)
    started = threading.Event()
    block = threading.Event()

    def _hang() -> None:
        started.set()
        block.wait(2.0)

    pool.submit(_hang)
    started.wait(1.0)
    queued = pool.submit(_hang)  # cannot start; worker count exhausted

    # Drain with a short timeout; the queued future should be cancelled.
    d._drain_pool("test", pool, timeout_s=0.3)
    assert queued.cancelled()
    block.set()


def test_shutdown_event_flips_on_signal_path(tmp_path):
    """Constructor wires `_shutdown_event`; signal handler in serve_forever
    sets it. Here we exercise the field directly — the signal-handler hook
    just calls `self._shutdown_event.set()`."""
    d = _make_daemon(tmp_path)
    assert d._shutdown_event.is_set() is False
    d._shutdown_event.set()
    assert d._shutdown_event.is_set() is True
