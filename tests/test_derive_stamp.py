"""bug-039: a store's DERIVED graph decays with every health surface green.

On 2026-09-16 this project's own store was structurally under-derived while
`daemon_up`, `dev_tree`, version parity and `rmx install-hooks --check` all
read green. 7 of 12 fixed scan-prompt prompts sat at a 1-bundle / 10-node
floor; a `reingest --force` took the set to 2.46x tokens. The store had not
been force-re-derived since 0.49.1, across ten days and several ingest changes.

`stale_files` cannot see this: it counts mtime drift on tracked FILES and says
nothing about a graph derived by older CODE. These tests cover the missing
fact — which version derived what is in the store — and the surfaces that say
it out loud.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import __version__ as RUNNING
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _track(s: Store, tmp_path: Path) -> Path:
    """Make the store look ingested-into: one tracked file."""
    f = tmp_path / "a.md"
    f.write_text("# a\n")
    s.mark_tracked(str(f.resolve()), f.stat().st_mtime)
    return f


# ---- the stamp -----------------------------------------------------------

def test_stamp_records_the_running_version(store):
    store.stamp_derive("ingest")
    rows = store.derive_status()["passes"]
    assert [(r["pass_name"], r["version"]) for r in rows] == [("ingest", RUNNING)]
    assert rows[0]["at"] > 0


def test_second_stamp_updates_rather_than_accreting(store):
    store.stamp_derive("ingest")
    first = store.derive_status()["passes"][0]["at"]
    store.stamp_derive("ingest", version="9.9.9")
    rows = store.derive_status()["passes"]
    assert len(rows) == 1
    assert rows[0]["version"] == "9.9.9"
    assert rows[0]["at"] >= first


def test_stamps_are_per_partition(store):
    store.stamp_derive("ingest")
    with store.with_partition("other"):
        assert store.derive_status()["passes"] == []


# ---- the verdict ---------------------------------------------------------

def test_a_store_stamped_by_the_running_version_is_not_stale(store, tmp_path):
    _track(store, tmp_path)
    store.stamp_derive("ingest")
    st = store.derive_status()
    assert st["stale"] is False
    assert st["running_version"] == RUNNING
    assert st["reason"] is None


def test_the_incident_replay_a_stamp_ten_days_old(store, tmp_path):
    """The 0.49.1 case: the graph was derived by code that is no longer
    running, and every other signal reads green."""
    _track(store, tmp_path)
    store.stamp_derive("ingest", version="0.49.1")
    st = store.derive_status()
    assert st["stale"] is True
    assert st["oldest_version"] == "0.49.1"
    assert "0.49.1" in st["reason"] and RUNNING in st["reason"]


def test_tracked_files_with_no_stamp_at_all_read_stale(store, tmp_path):
    """The pre-0.71 case — which is exactly the condition that hid for ten
    days. An unstamped store with content must read STALE, not unknown."""
    _track(store, tmp_path)
    assert store.derive_status()["passes"] == []
    st = store.derive_status()
    assert st["stale"] is True
    assert "never" in st["reason"]


def test_an_empty_store_is_not_stale(store):
    """A store nobody ingested into is not decayed. A false positive on every
    fresh store trains the signal away."""
    st = store.derive_status()
    assert st["stale"] is False
    assert st["reason"] is None


def test_a_newer_stamp_than_the_running_binary_is_also_flagged(store, tmp_path):
    """A rolled-back deploy is a mismatch worth saying. The comparison is
    exact inequality, never ordering."""
    _track(store, tmp_path)
    store.stamp_derive("ingest", version="99.0.0")
    st = store.derive_status()
    assert st["stale"] is True
    assert "99.0.0" in st["reason"]


def test_one_stale_pass_among_current_ones_is_enough(store, tmp_path):
    _track(store, tmp_path)
    store.stamp_derive("ingest")
    store.stamp_derive("gmd", version="0.49.1")
    st = store.derive_status()
    assert st["stale"] is True
    assert st["oldest_version"] == "0.49.1"


# ---- the wiring ----------------------------------------------------------

def test_a_real_ingest_stamps_the_store(tmp_path):
    """The pass driver, not the helper: run the real ingest over a small tree
    and read the stamp back. A test that calls `stamp_derive` directly proves
    the method and nothing about whether anything calls it."""
    from refmatrix.ingest import ingest_path

    proj = tmp_path / "proj"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "a.md").write_text("# Alpha\n\nAlpha is a thing.\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        ingest_path(s, proj)
        rows = {r["pass_name"]: r["version"] for r in s.derive_status()["passes"]}
        assert rows.get("ingest") == RUNNING
        assert s.derive_status()["stale"] is False
    finally:
        s.close()


def test_a_real_gmd_ingest_stamps_the_store(tmp_path):
    from refmatrix.ingest_gmd import ingest_gmd_paths

    proj = tmp_path / "gmd"
    proj.mkdir()
    (proj / "d.md").write_text(
        '---\ngmd: "0.1"\nid: d\ntitle: "D"\ntags: [x]\n---\n\n# D {#root}\n\nbody\n')
    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        ingest_gmd_paths(s, [proj / "d.md"])
        rows = {r["pass_name"]: r["version"] for r in s.derive_status()["passes"]}
        assert rows.get("gmd") == RUNNING
    finally:
        s.close()


def test_health_carries_the_derive_verdict(tmp_path, monkeypatch):
    """`_store_health` is what the hub's alert tick reads. The field has to be
    THERE, not merely computable."""
    from refmatrix import daemon as dmod

    s = Store(tmp_path / ".refmatrix")
    s.init()
    f = tmp_path / "a.md"
    f.write_text("# a\n")
    s.mark_tracked(str(f.resolve()), f.stat().st_mtime)
    s.stamp_derive("ingest", version="0.49.1")

    class _D:
        root = tmp_path / ".refmatrix"

        def _st(self):
            return s

        def _read_active_slot(self):
            return None

    try:
        h = dmod._store_health(_D())
        assert h["derive"]["stale"] is True
        assert h["derive"]["oldest_version"] == "0.49.1"
    finally:
        s.close()


def test_daemon_status_prints_the_stale_line_and_only_then(capsys):
    """A green surface stays quiet; a stale one names the versions and the
    command that fixes it."""
    from refmatrix.cli import render_derive_warning

    stale = {"stale": True, "oldest_version": "0.49.1",
             "running_version": "0.71.0",
             "reason": "derived by 0.49.1, running 0.71.0"}
    assert "0.49.1" in render_derive_warning(stale)
    assert "reingest --force" in render_derive_warning(stale)

    current = {"stale": False, "oldest_version": "0.71.0",
               "running_version": "0.71.0", "reason": None}
    assert render_derive_warning(current) == ""
    assert render_derive_warning(None) == ""


# ---- the alert gate measures the CODE's CONTENT (ch-bsd r2 + r3) --------

def test_a_stamp_from_different_code_is_behind_it(store, tmp_path, monkeypatch):
    """The condition bug-039 is actually about: the graph was built by code
    that is not the code running now."""
    import refmatrix.store as store_mod

    _track(store, tmp_path)
    store.stamp_derive("ingest", code_hash="deadbeef")
    monkeypatch.setattr(store_mod, "derive_code_hash", lambda: "cafef00d")
    st = store.derive_status()
    assert st["behind_code"] is True
    assert "before the current ingest code" in st["reason"]


def test_a_stamp_from_the_same_code_is_not_behind_it(store, tmp_path, monkeypatch):
    """A version bump that does not touch ingest must NOT make a store hot:
    34 bumps in ten days across 8 stores is an alert nobody reads twice."""
    import refmatrix.store as store_mod

    _track(store, tmp_path)
    monkeypatch.setattr(store_mod, "derive_code_hash", lambda: "cafef00d")
    store.stamp_derive("ingest", version="0.49.1")     # stamps the hash itself
    st = store.derive_status()
    assert st["behind_code"] is False
    assert st["stale"] is True, "the version line still tells the human"


def test_an_identical_content_rewrite_does_not_fire_the_gate(store, tmp_path):
    """ch-bsd plan-12 r3, demonstrated on this machine: a mutation harness
    restored `ingest.py` byte-for-byte and moved its mtime. Under the mtime
    gate that marked the store behind code that never changed. The hash does
    not move, so neither does the verdict."""
    import refmatrix.store as store_mod

    _track(store, tmp_path)
    store.stamp_derive("ingest")
    assert store.derive_status()["behind_code"] is False

    src = Path(store_mod.__file__).resolve()
    body = src.read_bytes()
    before = store_mod.derive_code_hash()
    src.write_bytes(body)                       # same bytes, new mtime
    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    assert store_mod.derive_code_hash() == before
    assert store.derive_status()["behind_code"] is False


def test_a_stamp_with_no_hash_at_all_counts_as_behind(store, tmp_path):
    """Rows written before this column exist — the blind spot itself."""
    _track(store, tmp_path)
    store.stamp_derive("ingest", code_hash=None)
    store._connect().execute(
        "UPDATE derive_stamps SET code_hash=NULL WHERE partition_id=?",
        (store._partition_id,))
    assert store.derive_status()["behind_code"] is True


def test_the_hash_is_cached_on_path_mtime_size(monkeypatch):
    """The hub's watchdog tick calls this per store; it must not re-read
    ~300 KB every time. A wrong cache key costs a recompute, never a wrong
    answer, which is the right way round."""
    import refmatrix.store as store_mod

    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    first = store_mod.derive_code_hash()
    reads: list = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: reads.append(self) or real(self))
    assert store_mod.derive_code_hash() == first
    assert reads == [], "a cache hit re-read the deriving modules"


def test_derive_code_hash_covers_the_deriving_modules():
    from hashlib import blake2b

    import refmatrix.store as store_mod

    here = Path(store_mod.__file__).resolve().parent
    h = blake2b(digest_size=16)
    for name in ("ingest.py", "ingest_gmd.py", "store.py"):
        h.update((here / name).read_bytes())
    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    assert store_mod.derive_code_hash() == h.hexdigest()


def test_an_mtime_preserving_restore_is_not_a_cache_hit(tmp_path, monkeypatch):
    """ch-bsd plan-12 r4, reproduced: `cp -p` / `rsync -t` / `tar -p` / any
    `os.utime` restores content at the SAME size with the SAME mtime, so a
    key of (path, mtime, size) reads as a hit and returns the OLD hash —
    `behind_code` False, gate silently not firing. That is bug-039's blind
    spot rebuilt inside its own detector, and the same shape as bug-037."""
    import os

    import refmatrix.store as store_mod

    mod = tmp_path / "fake_ingest.py"
    mod.write_text("A = 1\n")
    monkeypatch.setattr(store_mod, "_DERIVE_CODE_MODULES", ("fake_ingest.py",))
    monkeypatch.setattr(store_mod, "__file__", str(tmp_path / "store.py"))
    store_mod._DERIVE_CODE_HASH_CACHE.clear()

    first = store_mod.derive_code_hash()
    st = mod.stat()
    mod.write_text("A = 2\n")                       # same size, new content
    os.utime(mod, ns=(st.st_atime_ns, st.st_mtime_ns))   # ... restored mtime
    assert mod.stat().st_mtime_ns == st.st_mtime_ns
    assert mod.stat().st_size == st.st_size

    assert store_mod.derive_code_hash() != first, (
        "an mtime-preserving same-size rewrite was served from cache")


def test_the_cache_still_hits_when_nothing_moved(tmp_path, monkeypatch):
    import refmatrix.store as store_mod

    mod = tmp_path / "fake_ingest.py"
    mod.write_text("A = 1\n")
    monkeypatch.setattr(store_mod, "_DERIVE_CODE_MODULES", ("fake_ingest.py",))
    monkeypatch.setattr(store_mod, "__file__", str(tmp_path / "store.py"))
    store_mod._DERIVE_CODE_HASH_CACHE.clear()

    first = store_mod.derive_code_hash()
    reads: list = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: reads.append(self) or real(self))
    assert store_mod.derive_code_hash() == first
    assert reads == []
