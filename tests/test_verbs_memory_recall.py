"""plan-3 task 3.1 — recall semantics live in ONE verb, exercised on a real
store behind a real daemon (no monkeypatching the function under test).

2026-09-14: `--session-start` widening and the session/* exclusion existed
only in cli.py, so the MCP tool answered differently from the hook."""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import verbs
from refmatrix.store import Store

DAY = 86400.0


def _spawn(fresh_age: float):
    """A short-path tmp store with four memories at controlled ages, served by
    a spawned daemon: fresh (fresh_age), old (10d), older (20d, feedback), and
    a session/digest card (2d) that hook modes must hide."""
    base = Path(tempfile.mkdtemp(prefix="rmxv-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root); s.init()
    now = time.time()
    rows = [("fresh", "project", fresh_age), ("old", "project", 10 * DAY),
            ("older", "feedback", 20 * DAY), ("digest", "session/digest", 2 * DAY)]
    for name, mtype, age in rows:
        s.add_memory(name=name, content=f"body of {name}", mtype=mtype)
        s._connect().execute("UPDATE entities SET created_at=? WHERE name=? AND kind='memory'",
                             [now - age, name])
    s.close()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    return base, root


@pytest.fixture
def live():
    base, root = _spawn(1 * DAY)
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def live_old():
    """Everything older than the 7d session-start window."""
    base, root = _spawn(8 * DAY)
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def _names(res):
    return [m["name"] for m in res["memories"]]


def test_session_start_uses_the_7d_window_and_hides_session_cards(live):
    res = verbs.memory_recall(live, session_start=True, k=5)
    assert _names(res) == ["fresh"]
    assert res["mode"] == "session-start" and res["widened"] is False


def test_session_start_widens_when_the_window_is_empty(live_old):
    res = verbs.memory_recall(live_old, session_start=True, k=5)
    assert res["widened"] is True
    assert _names(res) == ["fresh", "old", "older"]     # newest first, digest hidden


def test_explicit_since_is_honored_not_widened(live):
    res = verbs.memory_recall(live, recent=True, since="12h", k=5)
    assert _names(res) == [] and res["widened"] is False


def test_include_session_opts_back_in(live):
    res = verbs.memory_recall(live, session_start=True, k=5, include_session=True)
    assert set(_names(res)) == {"fresh", "digest"}


def test_recent_with_wide_window_returns_newest_first(live):
    res = verbs.memory_recall(live, recent=True, since="30d", k=5, include_session=True)
    assert _names(res) == ["fresh", "digest", "old", "older"]


def test_exclude_mtype_glob_applies(live):
    res = verbs.memory_recall(live, recent=True, since="30d", k=5, exclude_mtype=["feed*", "session/*"])
    assert _names(res) == ["fresh", "old"]
