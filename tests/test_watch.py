"""Tests for the filesystem watcher."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from refmatrix.store import Store
from refmatrix.watch import Debouncer, is_relevant, run_watcher

# bug-091 (T0.3 R3.3, 2026-11-15): the watcher test waited ONE 3 s `wait` for a real FSEvents
# callback and failed under suite load (`watcher did not fire` / `wait(timeout=3.0)`, twice). It
# measures that the event is delivered, not how fast, so it polls until this deadline. Read at
# call time (never bound as a default) so a forced-failure run can shorten it.
WATCHER_DELIVERY_DEADLINE_S = 30.0


def test_is_relevant_filters_unsupported_and_ignored(tmp_path):
    assert is_relevant(Path("a.py")) is True
    assert is_relevant(Path("README.md")) is True
    assert is_relevant(Path("notes.bin")) is False
    assert is_relevant(Path(".git/HEAD")) is False
    assert is_relevant(Path("node_modules/foo/bar.py")) is False
    assert is_relevant(Path(".refmatrix/catalog.db")) is False
    assert is_relevant(Path("__pycache__/x.py")) is False


def test_debouncer_coalesces_and_fires(monkeypatch):
    fired: list[list[str]] = []
    d = Debouncer(delay_ms=80, callback=lambda paths: fired.append(paths))
    d.start()
    try:
        d.add("a")
        d.add("b")
        d.add("a")  # dedup
        time.sleep(0.05)  # before deadline -> not fired yet
        assert fired == []
        d.add("c")          # resets deadline
        time.sleep(0.20)    # past deadline
        assert len(fired) == 1
        assert sorted(fired[0]) == ["a", "b", "c"]
    finally:
        d.stop()


def test_debouncer_final_flush_on_stop():
    fired: list[list[str]] = []
    d = Debouncer(delay_ms=10_000, callback=lambda paths: fired.append(paths))
    d.start()
    d.add("x")
    d.stop()
    # we never reached the 10s deadline, but stop() flushes the pending batch
    assert fired == [["x"]]


def test_debouncer_swallows_callback_exceptions(capsys):
    def boom(_):
        raise ValueError("nope")
    d = Debouncer(delay_ms=30, callback=boom)
    d.start()
    d.add("a")
    time.sleep(0.12)
    d.stop()
    out = capsys.readouterr().out
    assert "sync error" in out


def test_run_watcher_picks_up_new_file(tmp_path):
    pytest.importorskip("watchdog")
    proj = tmp_path / "proj"
    proj.mkdir()
    s = Store(tmp_path / ".refmatrix")
    s.init()

    seen: list[tuple[list[str], dict]] = []
    seen_event = threading.Event()

    def on_batch(paths, report):
        seen.append((paths, report))
        seen_event.set()

    stop = threading.Event()
    t = threading.Thread(
        target=run_watcher,
        kwargs=dict(
            store=s, project_root=proj, debounce_ms=80,
            on_batch=on_batch, stop_event=stop,
            install_signal_handlers=False,
        ),
        daemon=True,
    )
    t.start()
    # A write made before the observer subscribes is never delivered, and no deadline fixes
    # that (ruling L141). There is no subscription signal to wait on, so the file is re-written
    # while polling: whichever write lands after the subscription is the one delivered.
    deadline_s = WATCHER_DELIVERY_DEADLINE_S
    t0 = time.monotonic()
    writes = 0
    try:
        while not seen_event.is_set():
            elapsed = time.monotonic() - t0
            if elapsed >= deadline_s:
                break
            (proj / "a.py").write_text(f"x = {writes + 1}\n")
            writes += 1
            seen_event.wait(timeout=min(1.0, deadline_s - elapsed))
        elapsed = time.monotonic() - t0
        assert seen_event.is_set(), (
            f"watcher did not fire: elapsed {elapsed:.1f} s against the delivery deadline "
            f"{deadline_s:g} s after {writes} write(s); watcher thread alive={t.is_alive()} "
            f"(alive and silent: the observer never delivered; not alive: run_watcher exited), "
            f"batches seen={len(seen)}")
    finally:
        stop.set()
        t.join(timeout=3.0)
    assert not t.is_alive()

    s.close()
    paths, report = seen[0]
    assert any(p.endswith("a.py") for p in paths)
    assert report["added"] >= 1
