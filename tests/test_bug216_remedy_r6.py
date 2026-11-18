"""bug-216 remedy r6 RED — bsd-216 r6 at f8db8f6 (MEH-only), ruling L103, #m1.

Report: workflow/bullshit/2026-11-14-0714-bug216-r6-f8db8f6.md #m1 (9bf04fc in the bug-216 clone).
Ruling: workflow/plan-review-2026-11-13.md row L103 (dev master).

  M1  a purge whose vector table EXISTS while the `lance` package cannot be imported deletes
      nothing and says nothing: `_lance_for_purge` returns None on `find_spec("lance") is None`,
      and both purge paths read that as "nothing to delete". bsd's probe: three memories with
      vectors, purged through the REAL purge paths — the batch (`bulk_forget_memories`, which
      goes through `_drop_lance_for_purge_batch`) and the single (`purge_entity`, through
      `_drop_lance_for_purge`). Required: the failure is counted (`vector_delete_failures`),
      printed naming lance as missing and the (partition, kind) table, and the rows reported as
      left behind — never a silent 0 / False.

How "lance unavailable" is made real: a CHILD process sets `sys.modules["lance"] = None` before
anything imports it. `importlib.util.find_spec("lance")` then returns None (an entry of None in
sys.modules is "not importable"), so the code under test takes its own not-installed branch; no
function under test and no `find_spec` is patched. The Lance table is written by THIS process,
which has the [dense] extra, so the table exists — bsd's "written by an interpreter that has
lance, purged by one that does not".

Throwaway stores under short `/tmp` mkdtemp roots only; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from tests.test_bug216_remedy_r1 import _new_store, _open

_CHILD = r"""
import json, sys
sys.modules["lance"] = None              # the [dense] extra is not importable here
import importlib.util
assert importlib.util.find_spec("lance") is None
from pathlib import Path
from refmatrix.store import Store
root, mode, ids = Path(sys.argv[1]), sys.argv[2], [int(x) for x in sys.argv[3].split(",")]
s = Store(root)
s.init()
try:
    with s.with_partition("proj"):
        if mode == "batch":
            res = s.bulk_forget_memories(ids=ids)
            res = {k: v for k, v in res.items() if isinstance(v, (int, str, bool, type(None)))}
        else:
            res = [s.purge_entity(i) for i in ids]
    print("@@RESULT@@" + json.dumps({"failures": getattr(s, "vector_delete_failures", 0),
                                      "result": res}))
finally:
    s.close()
"""


@pytest.fixture
def store_with_vectors():
    base = Path(rmx_sandbox.short_root("b216v")).resolve()
    root = base / "proj" / ".refmatrix"
    _new_store(root)
    s = _open(root)
    try:
        ids = [s.add_memory(f"mem-{k}", f"body {k}") for k in range(3)]
    finally:
        s.close()
    from refmatrix.vectors import LanceVectorStore
    LanceVectorStore(root / "vectors", partition="proj", dim=4).upsert_vectors(
        ids, np.ones((3, 4), dtype="float32"), kind="memory")
    yield {"root": root, "ids": ids}
    shutil.rmtree(base)


def _lance_ids(root: Path) -> "list[int]":
    from refmatrix.vectors import LanceVectorStore
    got, _ = LanceVectorStore(root / "vectors", partition="proj", dim=0).read_vectors(
        kind="memory")
    return sorted(got)


@pytest.mark.parametrize("mode", ["batch", "single"])
def test_m1_a_purge_with_lance_missing_but_the_table_present_is_counted_and_said(
        store_with_vectors, mode):
    st = store_with_vectors
    p = subprocess.run([sys.executable, "-c", _CHILD, str(st["root"]), mode,
                        ",".join(str(i) for i in st["ids"])],
                       capture_output=True, text=True, env=dict(os.environ), timeout=600)
    parts = p.stdout.split("@@RESULT@@")
    assert len(parts) == 2, f"child failed (rc {p.returncode}):\n{p.stdout}\n{p.stderr}"
    res = json.loads(parts[1])
    assert _lance_ids(st["root"]) == sorted(st["ids"]), (
        "precondition: with lance unavailable the purge cannot have deleted any vector row")
    err = p.stderr
    problems = []
    if not res["failures"] >= len(st["ids"]):
        problems.append(f"vector_delete_failures = {res['failures']} for {len(st['ids'])} rows "
                        f"left behind (the purge returned {res['result']})")
    if not (re.search(r"\blance\b", err)
            and re.search(r"not installed|missing|unavailable", err, re.I)):
        problems.append("stderr does not say lance is missing")
    if not ("memory" in err and "proj" in err):
        problems.append("stderr does not name the (partition, kind) table proj/memory")
    if not re.search(r"orphan|left behind|not deleted", err, re.I):
        problems.append("stderr does not say the rows were left behind")
    assert not problems, f"{mode} purge with lance missing:\n- " + "\n- ".join(problems) + (
        f"\nstderr: {err!r}")
