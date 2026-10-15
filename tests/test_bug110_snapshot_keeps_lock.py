"""bug-110: a snapshot must not release the daemon's DuckDB lock on its own writer slot.

DuckDB guards a database file with a POSIX `fcntl` lock. POSIX record locks belong to the
(process, file) pair and are dropped on ANY `close()` of ANY descriptor for that file in the
process — so the in-process `shutil.copy2(slot, tmp)` in `_snapshot_catalog` released the
daemon's lock the first time it ran, and a second process could then open the live slot and
commit (ch-bsd bug-105 r5 #s5-3, probe q2b). The probe here is that second process.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from refmatrix.daemon import Daemon
from refmatrix.store import Store


_PROBE = (
    "import sys, duckdb\n"
    "con = duckdb.connect(sys.argv[1])\n"
    "con.execute('CREATE TABLE IF NOT EXISTS bug110_probe (x INTEGER)')\n"
    "con.execute('INSERT INTO bug110_probe VALUES (1)')\n"
    "con.close()\n"
)


def _second_writer(db_path: Path) -> subprocess.CompletedProcess:
    """Open `db_path` read-write from ANOTHER process and commit a row."""
    return subprocess.run([sys.executable, "-c", _PROBE, str(db_path)],
                          capture_output=True, text=True, timeout=60)


def _bare_daemon(root: Path, store: Store) -> Daemon:
    d = object.__new__(Daemon)
    d.root = root
    d._log = lambda *a, **k: None
    d.store = store
    d._store_lock = threading.Lock()
    d._snapshot_lock = threading.Lock()
    d._last_snapshot_ts = 0.0
    d._snapshot_dirty = False
    d._snapshot_event = threading.Event()
    d._snapshot_stop = threading.Event()
    return d


def test_second_writer_is_refused_before_and_after_a_snapshot(tmp_path):
    s = Store(tmp_path, backend="duckdb")
    s._connect()
    try:
        before = _second_writer(s.db_path)
        assert before.returncode != 0, "control: the open store must hold the lock"
        assert "lock" in before.stderr.lower(), before.stderr

        d = _bare_daemon(tmp_path, s)
        out = d._snapshot_catalog(force=True)
        assert "snapshot_path" in out, out

        after = _second_writer(s.db_path)
        assert after.returncode != 0, (
            "a second process committed to the live writer slot after a snapshot: "
            "the snapshot copy dropped the daemon's DuckDB lock")
        assert "lock" in after.stderr.lower(), after.stderr
    finally:
        s.close()


def test_snapshot_is_a_readable_copy_of_the_writer(tmp_path):
    """The fix changes HOW the bytes are copied; the snapshot must still open and match."""
    import duckdb

    s = Store(tmp_path, backend="duckdb")
    con = s._connect()
    con.execute("CREATE TABLE bug110_rows (x INTEGER)")
    con.execute("INSERT INTO bug110_rows VALUES (1), (2), (3)")
    try:
        d = _bare_daemon(tmp_path, s)
        out = d._snapshot_catalog(force=True)
        snap = Path(out["snapshot_path"])
        ro = duckdb.connect(str(snap), read_only=True)
        try:
            assert ro.execute("SELECT count(*) FROM bug110_rows").fetchone()[0] == 3
        finally:
            ro.close()
    finally:
        s.close()


# ---- ch-bsd r1 (bsd-bug110-lock-held-tests-now-fail-60893d3) #s-2: the copy's failure paths -----

def _fake_cp(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fakecp.sh"
    script.write_text("#!/bin/sh\n" + body + "\n")
    script.chmod(0o755)
    return str(script)


def test_a_failed_copy_installs_no_snapshot_and_keeps_the_previous_one(tmp_path, monkeypatch):
    """A full volume makes cp exit 1 after writing part of the file. The partial tmp must never
    replace the snapshot readers use."""
    import refmatrix.daemon as dm

    s = Store(tmp_path, backend="duckdb")
    s._connect()
    try:
        d = _bare_daemon(tmp_path, s)
        good = d._snapshot_catalog(force=True)
        snap = Path(good["snapshot_path"])
        before = snap.read_bytes()
        # Writes a truncated tmp (the destination is the last argument), then fails.
        monkeypatch.setattr(dm, "_CP", _fake_cp(
            tmp_path, 'for a; do dst="$a"; done; printf partial > "$dst"; '
                      'echo "No space left on device" >&2; exit 1'))
        out = d._snapshot_catalog(force=True)
        assert out.get("error") == "copy", out
        assert "No space left on device" in out["detail"], out
        assert snap.read_bytes() == before, "a partial copy replaced the snapshot"
    finally:
        s.close()


def test_a_copy_that_hangs_times_out_as_an_oserror(tmp_path, monkeypatch):
    import refmatrix.daemon as dm

    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 1024)
    monkeypatch.setattr(dm, "_CP", _fake_cp(tmp_path, "sleep 30"))
    import pytest
    with pytest.raises(OSError, match="timed out"):
        dm._copy_out_of_process(src, tmp_path / "dst.bin", timeout_s=0.5)


def test_the_copy_preserves_mtime_like_copy2(tmp_path):
    import os
    import refmatrix.daemon as dm

    src = tmp_path / "src.bin"
    src.write_bytes(b"y" * 4096)
    os.utime(src, (1_700_000_000, 1_700_000_000))
    dst = tmp_path / "dst.bin"
    dm._copy_out_of_process(src, dst)
    assert dst.read_bytes() == src.read_bytes()
    assert int(dst.stat().st_mtime) == 1_700_000_000
