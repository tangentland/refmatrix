"""Shared helpers for the `case_*.py` fixture tests of plan-29 task 29.4 AC-5 (the reaper).

These files are NOT part of the suite (task-29.4 `#r1-fixtures`): `tests/test_daemon_reaper.py`
copies a case into a throwaway checkout as `tests/test_case.py`, copies this file beside it as
`tests/suite_health_support.py`, and runs pytest there in a CHILD process, whose own conftest
(this checkout's, copied) builds the inner session's own sandbox and reaper.

A case tells the outer test what it started through `$RMX_CASE_INFO` (a JSON file), so the outer
test can check what the inner session's reaper did, and stop whatever it did not.

The store roots are `mkdtemp(dir="/tmp")`, OUTSIDE the inner sandbox root, on purpose: that is
bug-229's shape (its daemon served `/private/tmp/r1-hcn81cf7/proj/.refmatrix`), and the reaper is
keyed on the spawn, not on a root under the sandbox (task-29.4 `#r4` item 5). The tmp-root
census exempts `tests/fixtures/suite_health/` by path for exactly this.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def store_root(prefix: str = "sh-", under: "str | None" = None) -> "tuple[Path, Path]":
    """(base, root): an initialised store at `<base>/proj/.refmatrix`, base under /tmp (short:
    macOS `sun_path` is ~104 bytes), or under `under` when given (the inner sandbox root, for
    the R4.4 case)."""
    from refmatrix.store import Store
    base = Path(tempfile.mkdtemp(prefix=prefix, dir=under or "/tmp")).resolve()
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    try:
        s.init()
    finally:
        s.close()
    return base, root


def report(**kw) -> None:
    """Write what this case started to `$RMX_CASE_INFO`, for the outer test."""
    kw.setdefault("test", os.environ.get("PYTEST_CURRENT_TEST", ""))
    kw.setdefault("sandbox", os.environ.get("RMX_SANDBOX_ROOT", ""))
    kw.setdefault("inner_pid", os.getpid())
    path = Path(os.environ["RMX_CASE_INFO"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(kw, default=str))
    os.replace(tmp, path)


def ledger_path() -> Path:
    """The inner session's spawn ledger (task-29.4 `#r4` item 1)."""
    return Path(os.environ["RMX_SANDBOX_ROOT"]) / "children.jsonl"
