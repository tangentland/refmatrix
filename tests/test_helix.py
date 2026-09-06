"""Helix phase 1: point-in-time STM snapshot annotation.

A retrieval whose anchor was last STM-touched OUTSIDE the working window
gets that moment's neighborhood attached; current work gets nothing (the
live composite covers it). Every emission logs to helix.log — the
readership signal that decides the phase-2 storage fork.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from refmatrix import helix
from refmatrix.store import Store

DAY = 86400.0


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def _write_ring(root: Path, stem: str, events: list[dict]) -> Path:
    d = root / "stm"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.jsonl"
    with open(p, "w", encoding="utf8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return p


@pytest.fixture(autouse=True)
def _fresh_cache():
    helix._proc_cache.clear()
    yield
    helix._proc_cache.clear()


@pytest.fixture
def root(tmp_path):
    now = time.time()
    old = now - 60 * DAY
    _write_ring(tmp_path, "oldsession", [
        {"ts": _iso(old), "session": "oldsession", "kind": "tool",
         "terse": "rework fov_wedge polygon clipping",
         "refs": ["fov_wedge", "polygon", "clip"]},
        {"ts": _iso(old + 60), "session": "oldsession", "kind": "say",
         "terse": "clip edge cases", "refs": ["fov_wedge", "raycast"]},
    ])
    _write_ring(tmp_path, "newsession", [
        {"ts": _iso(now - 600), "session": "newsession", "kind": "tool",
         "terse": "touch fresh concept", "refs": ["fresh_thing"]},
    ])
    return tmp_path


def test_stale_touch_gets_annotated_with_that_moments_neighborhood(root):
    note = helix.annotate(root, "fov_wedge")
    assert note is not None
    assert "[helix] last worked" in note
    assert "oldsessi" in note                       # session id prefix
    assert "polygon" in note and "raycast" in note  # co-refs of the moment
    assert "fresh_thing" not in note


def test_recent_touch_is_silent(root):
    assert helix.annotate(root, "fresh_thing") is None


def test_unknown_concept_is_silent(root):
    assert helix.annotate(root, "never_seen") is None


def test_kill_switch(root, monkeypatch):
    monkeypatch.setenv("RMX_HELIX", "0")
    assert helix.annotate(root, "fov_wedge") is None


def test_window_is_wall_clock_and_tunable(root, monkeypatch):
    # 90-day window swallows the 60-day-old touch -> current, silent.
    monkeypatch.setenv("RMX_HELIX_WINDOW_DAYS", "90")
    assert helix.annotate(root, "fov_wedge") is None


def test_emission_logs_readership_signal(root):
    helix.annotate(root, "fov_wedge")
    rows = [json.loads(l) for l in
            (root / "helix.log").read_text(encoding="utf8").splitlines()]
    assert rows and rows[-1]["concept"] == "fov_wedge"
    assert rows[-1]["age_days"] >= 59


def test_index_is_incremental_over_new_rings(root):
    idx1 = helix.build_index(root)
    assert "fov_wedge" in idx1["touch"]
    now = time.time()
    _write_ring(root, "thirdsession", [
        {"ts": _iso(now - 30 * DAY), "session": "thirdsession",
         "kind": "tool", "terse": "later fov work",
         "refs": ["fov_wedge", "lens"]},
    ])
    helix._proc_cache.clear()
    idx2 = helix.build_index(root)
    stems = {row[1] for row in idx2["touch"]["fov_wedge"]}
    assert "thirdsession" in stems and "oldsession" in stems


def test_leaf_and_canonical_candidates_match(root):
    # Anchor named like a symbol still finds the ring token.
    note = helix.annotate(root, "src/geo.py::fov_wedge")
    assert note is not None


def test_build_context_attaches_and_renders_the_note(tmp_path):
    now = time.time()
    _write_ring(tmp_path / ".refmatrix", "ancient", [
        {"ts": _iso(now - 45 * DAY), "session": "ancient", "kind": "tool",
         "terse": "tuning zone_class thresholds",
         "refs": ["zone_class", "threshold"]},
    ])
    s = Store(tmp_path / ".refmatrix")
    s.init()
    c = s.add_concept("zone_class")
    s.link("mentions", c, s.upsert_entity(kind="code", name="zones.py"))
    from refmatrix.context import build_context, render_text
    b = build_context(s, "zone_class")
    assert b.helix_note and "[helix]" in b.helix_note
    out = render_text(b)
    assert "[helix] last worked" in out
    s.close()
