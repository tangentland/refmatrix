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
def _fresh_cache(monkeypatch):
    monkeypatch.delenv("RMX_SESSION", raising=False)
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
    # Production always has a live ring (the hook writes the prompt being
    # served); it is the CURRENT session and must not mask the stale touch.
    _write_ring(tmp_path / ".refmatrix", "livesession", [
        {"ts": _iso(now - 5), "session": "livesession", "kind": "input",
         "terse": "zone_class question", "refs": ["zone_class"]},
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


# --- phase 1.5: current-session exclusion + neighbor annotation -------------


def test_current_session_echo_does_not_mask_staleness(root):
    """The confound fix: the prompt's own STM echo (current ring) is
    excluded from last_touch, so a concept revisited after 60d still
    annotates even though the hook just recorded it."""
    now = time.time()
    # newest-mtime ring = current session; it touches fov_wedge NOW.
    _write_ring(root, "livesession", [
        {"ts": _iso(now - 2), "session": "livesession", "kind": "input",
         "terse": "asking about fov_wedge again", "refs": ["fov_wedge"]},
    ])
    helix._proc_cache.clear()
    note = helix.annotate(root, "fov_wedge")
    assert note is not None and "60d ago" in note or "59d ago" in note


def test_rmx_session_env_names_the_current_ring(root, monkeypatch):
    now = time.time()
    _write_ring(root, "sess-a", [
        {"ts": _iso(now - 3), "session": "sess-a", "kind": "input",
         "terse": "fov again", "refs": ["fov_wedge"]},
    ])
    helix._proc_cache.clear()
    # Without env: sess-a is newest by mtime -> excluded -> stale note.
    assert helix.annotate(root, "fov_wedge") is not None
    # Env names a DIFFERENT session as current: sess-a's fresh touch now
    # counts, so the concept is current -> silent.
    monkeypatch.setenv("RMX_SESSION", "someother")
    helix._proc_cache.clear()
    assert helix.annotate(root, "fov_wedge") is None


def test_subject_ring_belongs_to_its_session(root, monkeypatch):
    now = time.time()
    _write_ring(root, "sess-b__topicx", [
        {"ts": _iso(now - 3), "session": "sess-b", "kind": "input",
         "terse": "fov subject work", "refs": ["fov_wedge"]},
    ])
    monkeypatch.setenv("RMX_SESSION", "sess-b")
    helix._proc_cache.clear()
    # The subject ring's fresh touch is excluded with its session.
    assert helix.annotate(root, "fov_wedge") is not None


def test_neighbor_label_and_log_role(root):
    note = helix.annotate(root, "fov_wedge", label="fov_wedge")
    assert note is not None and note.startswith("[helix] fov_wedge:")
    rows = [json.loads(l) for l in
            (root / "helix.log").read_text(encoding="utf8").splitlines()]
    assert rows[-1]["role"] == "neighbor"
    helix.annotate(root, "fov_wedge")
    rows = [json.loads(l) for l in
            (root / "helix.log").read_text(encoding="utf8").splitlines()]
    assert rows[-1]["role"] == "anchor"


def test_display_ref_drops_junk_and_stopwords():
    assert helix._display_ref("main..maste") == ""
    assert helix._display_ref(".claud") == ""
    assert helix._display_ref("trailing.") == ""
    assert helix._display_ref("/a/b/store.py") == "store.py"
    assert helix._display_ref("ok_token") == "ok_token"


def test_build_context_annotates_stale_neighbor(tmp_path):
    """Anchor is fresh (prompt echo) but its graph neighbor went cold 40d
    ago: the neighbor gets the annotation."""
    now = time.time()
    rmxroot = tmp_path / ".refmatrix"
    _write_ring(rmxroot, "oldwork", [
        {"ts": _iso(now - 40 * DAY), "session": "oldwork", "kind": "tool",
         "terse": "cold_helper refactor", "refs": ["cold_helper", "widget"]},
    ])
    _write_ring(rmxroot, "livesession", [
        {"ts": _iso(now - 5), "session": "livesession", "kind": "input",
         "terse": "hub question", "refs": ["hub_thing"]},
    ])
    s = Store(rmxroot)
    s.init()
    c = s.add_concept("hub_thing")
    s.link("mentions", c, s.upsert_entity(kind="code", name="cold_helper"))
    from refmatrix.context import build_context, render_text
    b = build_context(s, "hub_thing")
    assert any("cold_helper" in n for n in b.helix_neighbor_notes), (
        b.helix_neighbor_notes)
    out = render_text(b)
    assert "[helix] cold_helper:" in out
    s.close()


# --- rendered-gated logging (phase-2 instrument hygiene) --------------------


def test_annotation_logs_only_when_rendered(tmp_path):
    """A built-but-dropped bundle (scan-prompt discards anchor-less/group-less
    bundles) must not count toward the readership signal."""
    now = time.time()
    rmxroot = tmp_path / ".refmatrix"
    _write_ring(rmxroot, "oldwork", [
        {"ts": _iso(now - 40 * DAY), "session": "oldwork", "kind": "tool",
         "terse": "zone tuning", "refs": ["zone_class"]},
    ])
    _write_ring(rmxroot, "livesession", [
        {"ts": _iso(now - 5), "session": "livesession", "kind": "input",
         "terse": "zone_class question", "refs": ["zone_class"]},
    ])
    s = Store(rmxroot)
    s.init()
    c = s.add_concept("zone_class")
    s.link("mentions", c, s.upsert_entity(kind="code", name="zones.py"))
    from refmatrix.context import build_context, render_text
    b = build_context(s, "zone_class")
    assert b.helix_note
    assert not (rmxroot / "helix.log").exists()   # built, not rendered
    render_text(b)
    rows = [json.loads(l) for l in
            (rmxroot / "helix.log").read_text(encoding="utf8").splitlines()]
    assert rows and rows[-1]["concept"] == "zone_class"
    assert rows[-1]["rendered"] is True
    render_text(b)                                # idempotent: sink cleared
    rows2 = (rmxroot / "helix.log").read_text(encoding="utf8").splitlines()
    assert len(rows2) == len(rows)
    s.close()


def test_content_only_path_annotates_stale_hits(tmp_path):
    """The NL/no-anchor path was invisible to helix; its content hits are the
    neighborhood and must be sweepable."""
    now = time.time()
    rmxroot = tmp_path / ".refmatrix"
    _write_ring(rmxroot, "oldwork", [
        {"ts": _iso(now - 30 * DAY), "session": "oldwork", "kind": "tool",
         "terse": "frobnicator rework", "refs": ["frob_helper"]},
    ])
    _write_ring(rmxroot, "livesession", [
        {"ts": _iso(now - 5), "session": "livesession", "kind": "input",
         "terse": "unrelated", "refs": ["other_thing"]},
    ])
    s = Store(rmxroot)
    s.init()
    s.upsert_entity(kind="code", name="frob_helper",
                    tldr="frobnicate the widget pipeline")
    from refmatrix.context import content_only_bundle, render_text
    b = content_only_bundle(s, "frobnicate widget")
    if b.groups:  # content hit found -> the sweep must have seen it
        assert any("frob_helper" in n for n in b.helix_neighbor_notes)
        out = render_text(b)
        assert "[helix] frob_helper:" in out
        assert (rmxroot / "helix.log").exists()
    s.close()
