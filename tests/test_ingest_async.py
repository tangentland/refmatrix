"""Fire-and-poll queued ingest: `ingest_path_start` returns a job_id
immediately and the work runs detached on bg_pool, polled via
`ingest_gmd_status` (generic over all ingest jobs). The single-active guard
rejects a second start while one is running.
"""
from __future__ import annotations

import importlib.util
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

duckdb_only = pytest.mark.skipif(
    importlib.util.find_spec("duckdb") is None, reason="duckdb not installed",
)


def _make_daemon(tmp_path: Path):
    from refmatrix.daemon import Daemon
    from refmatrix.store import Store
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root)
    s.init()
    d = Daemon(root)
    d.store = s
    # serve_forever() normally wires the pools; a unit test drives ops directly.
    d._bg_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="t-bg")
    return d, s


def _poll_done(d, job_id, timeout=20.0):
    from refmatrix.daemon import _op_ingest_gmd_status
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _op_ingest_gmd_status(d, {"job_id": job_id})["job"]
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish within timeout")


@duckdb_only
def test_ingest_path_start_returns_job_then_completes(tmp_path):
    from refmatrix.daemon import _op_ingest_path_start
    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True, exist_ok=True)
    (proj / "pkg" / "a.py").write_text("def hello():\n    return 1\n")
    (proj / "README.md").write_text("# Title\n\nsome docs\n")

    d, s = _make_daemon(tmp_path)
    t0 = time.monotonic()
    r = _op_ingest_path_start(d, {"path": str(proj), "source": "tree"})
    elapsed = time.monotonic() - t0

    # The start call is time-bound — it returns a job handle, not the result.
    assert "job_id" in r and r["status"] == "running"
    assert elapsed < 1.0, "start op blocked instead of returning immediately"
    assert "entities" not in r

    job = _poll_done(d, r["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["entities"] >= 1
    d._bg_pool.shutdown(wait=True)
    s.close()


@duckdb_only
def test_single_active_guard_rejects_second_start(tmp_path):
    from refmatrix.daemon import _op_ingest_path_start, _register_ingest_job
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "a.py").write_text("x = 1\n")
    d, s = _make_daemon(tmp_path)
    # Simulate an in-flight job by reserving the slot.
    _register_ingest_job(d, files_total=5, args={})
    with pytest.raises(RuntimeError, match="ingest already active"):
        _op_ingest_path_start(d, {"path": str(proj)})
    d._bg_pool.shutdown(wait=True)
    s.close()
