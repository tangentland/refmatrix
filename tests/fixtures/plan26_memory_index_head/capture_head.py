"""Capture task 26.1's HEAD golden files (AC-8, AC-9 flat) from HEAD's own `memory_index`.

Run ONLY on a checkout whose `src/refmatrix/memory_index.py` is HEAD 61b3bde's (the code
before task 26.1), with that checkout's src first on the path:

    PYTHONPATH=$PWD/src:$PWD python -B tests/fixtures/plan26_memory_index_head/capture_head.py

It refuses when `memory_layout` is importable (26.1 has landed: the goldens would record the
new code, and a byte-identity test against its own output proves nothing).
"""
from __future__ import annotations

import importlib.util
import io
import shutil
import tempfile
from pathlib import Path

if importlib.util.find_spec("refmatrix.memory_layout") is not None:
    raise SystemExit("refmatrix.memory_layout exists: this is not HEAD's memory_index; refusing")

from refmatrix import memory_index as mi  # noqa: E402
from tests.test_memory_index_layout import build_flat_no_prose, build_flat_one_prose  # noqa: E402

HERE = Path(__file__).resolve().parent

for case, build in (("flat_no_prose", build_flat_no_prose),
                    ("flat_one_prose", build_flat_one_prose)):
    base = Path(tempfile.mkdtemp(prefix="rmx261g-"))
    try:
        d = base / "memory"
        d.mkdir()
        build(d)
        mi.write(d, out=io.StringIO())
        out = HERE / case
        out.mkdir(exist_ok=True)
        (out / "MEMORY.md.golden").write_bytes((d / "MEMORY.md").read_bytes())
        (out / "memory_hooks.json.golden").write_bytes((d / mi.HOOKS_SIDECAR).read_bytes())
        print(f"{case}: captured from {mi.__file__}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
