"""bug-216 remedy r5 RED — bsd-216 r5 at aaa1ba5 (DIRTY 0B/1S/1M), ruling L101.

Report: workflow/bullshit/2026-11-14-0456-bug216-r5-aaa1ba5.md (0bd5c9c in the bug-216 clone).
Ruling: workflow/plan-review-2026-11-13.md row L101 (dev master).

  S1  the mirror of the A-loser vector pin (d3b9f6c): B's `shared` LOSES to A's newer `shared`,
      and A's `x-only-a` holds B-shared's old id. Both slots write one `vectors/` dir, so the
      Lance row at that id may be B-shared's vector, now filed under `x-only-a`. Through the
      REAL `_op_replica_merge`, every entity embedded first: the row at the vacated id is
      deleted, `x-only-a` is re-queued, unrelated entities keep their rows and are not
      re-queued, and the reply's `vector_rows` and `re_embed` name the id.
  M1  `_delete_vector_groups` skips a table silently when `lance` cannot be imported. Driven
      for real in a child process whose `sys.modules["lance"]` is None (no function under test
      is patched): a merge with vector rows to delete reports "lance unavailable" in
      `vector_delete_error`, and `rmx replica merge` exits non-zero naming the rows left.

Throwaway stores under short `/tmp` mkdtemp roots only; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pytest

from refmatrix.store import Store
from tests.test_bug216_remedy_r1 import _new_store, _open
from tests.test_bug216_remedy_r3 import _memory_slots
from tests.test_bug216_remedy_r4 import _seed_vectors, _vector_ids


@pytest.fixture
def base():
    b = Path(tempfile.mkdtemp(prefix="b216u", dir="/tmp")).resolve()
    yield b
    shutil.rmtree(b)


def _daemon_root(base: Path, a_root: Path, b_root: Path) -> Path:
    droot = base / "D" / "proj" / ".refmatrix"
    droot.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", droot / "catalog.A.duckdb")
    shutil.copy2(b_root / "catalog.duckdb", droot / "catalog.B.duckdb")
    (droot / "active").write_text("A")
    return droot


def _mark_embedded(*roots: Path) -> None:
    for root in roots:
        con = duckdb.connect(str(root / "catalog.duckdb"))
        try:
            con.execute("UPDATE entities SET vectors_updated_at = updated_at + 1, "
                        "vectors_partition = 'proj'")
        finally:
            con.close()


# ================================================================ S1


def test_s1_an_id_a_b_loser_vacated_loses_its_stale_vector_and_its_holder_is_requeued(base):
    from refmatrix import daemon as dm
    a_root = base / "A" / "proj" / ".refmatrix"
    b_root = base / "B" / "proj" / ".refmatrix"
    _new_store(a_root)
    s = _open(a_root)
    try:
        keep = s.add_memory("keep", "an unrelated, embedded memory")
    finally:
        s.close()
    b_root.mkdir(parents=True)
    shutil.copy2(a_root / "catalog.duckdb", b_root / "catalog.duckdb")
    s = _open(b_root)
    try:
        b_shared = s.add_memory("shared", "SHARED B (older)")      # written first: loses
    finally:
        s.close()
    s = _open(a_root)
    try:
        x_only_a = s.add_memory("x-only-a", "ONLY IN A")
        a_shared = s.add_memory("shared", "SHARED A (newer)")
    finally:
        s.close()
    assert x_only_a == b_shared and a_shared not in (b_shared, keep), (
        f"precondition: A's x-only-a at B-shared's id {b_shared}; a_shared {a_shared}; "
        f"keep {keep}")
    _mark_embedded(a_root, b_root)
    droot = _daemon_root(base, a_root, b_root)
    _seed_vectors(droot, [b_shared, a_shared, keep])
    d = dm.Daemon(droot, partition="proj")
    d._log = lambda msg: None
    d.store = Store(droot, partition="proj")
    d.store.init()
    d.store._connect()
    try:
        r = dm._op_replica_merge(d, {"dry_run": False})
        assert r.get("ok") is True and not r.get("vector_delete_error"), r
        assert r["remap"]["b_loser_count"] == 1 and not r.get("fresh_moved"), (
            f"precondition: B's shared is a name-loser, nothing moves: {r['remap']} "
            f"{r.get('fresh_moved')}")
        with d.store.with_partition("proj"):
            pending = {int(row[0]) for row in d.store.pending_embeddings()}
    finally:
        if d.store is not None:
            d.store.close()
    left = _vector_ids(droot)
    vrows = [list(v) for v in (r.get("vector_rows") or [])]
    problems = []
    if b_shared in left:
        problems.append(f"the Lance row at {b_shared} (B-shared's vector, now under x-only-a) "
                        f"survived")
    if not {a_shared, keep} <= left:
        problems.append(f"a vector whose owner did not change was deleted: kept {sorted(left)}")
    if x_only_a not in pending:
        problems.append(f"x-only-a ({x_only_a}) holds a vacated id but was not re-queued: "
                        f"{sorted(pending)}")
    if keep in pending or a_shared in pending:
        problems.append(f"an entity whose owner did not change was re-queued: {sorted(pending)}")
    if ["proj", "memory", b_shared] not in vrows:
        problems.append(f"vector_rows does not name proj/memory/{b_shared}: {vrows}")
    if not re.search(rf"\b{b_shared}\b", str(r.get("re_embed") or "")):
        problems.append(f"re_embed does not name id {b_shared}: {r.get('re_embed')!r}")
    assert not problems, "\n".join(problems)


# ================================================================ M1

_CHILD = r"""
import json, sys
sys.modules["lance"] = None          # lance cannot be imported in this process
from pathlib import Path
from click.testing import CliRunner
from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix.store import Store

droot = Path(sys.argv[1])
d = dm.Daemon(droot, partition="proj")
d._log = lambda msg: None
d.store = Store(droot, partition="proj")
d.store.init()
d.store._connect()
cli_mod._root = lambda: droot
dm.ping = lambda *a, **k: True
dm.call = lambda root, op, args, **kw: {"ok": True, "result": dm.OPS[op](d, dict(args))}
r = CliRunner().invoke(cli_mod.main, ["replica", "merge", "--yes"] + sys.argv[2:])
print("@@RESULT@@" + json.dumps({"exit": r.exit_code, "stdout": r.stdout,
                                  "stderr": r.stderr or ""}))
"""


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_m1_a_merge_with_lance_unavailable_exits_non_zero_naming_the_rows_left(base, as_json):
    m = _memory_slots(base, n_moves=2)
    droot = _daemon_root(base, m["a"], m["b"])
    _seed_vectors(droot, m["ids"] + [m["keep"]])      # rows the merge must delete
    before = _vector_ids(droot)
    env = dict(os.environ)
    p = subprocess.run([sys.executable, "-c", _CHILD, str(droot)]
                       + (["--json"] if as_json else []),
                       capture_output=True, text=True, env=env, timeout=600)
    out = p.stdout.split("@@RESULT@@")
    assert len(out) == 2, f"child failed (rc {p.returncode}):\n{p.stdout}\n{p.stderr}"
    res = json.loads(out[1])
    assert _vector_ids(droot) == before, "precondition: lance was blocked, nothing deleted"
    assert res["exit"] != 0, (
        f"`rmx replica merge` exited 0 with lance unavailable and vector rows left:\n"
        f"{res['stdout'][-1500:]}\n{res['stderr']}")
    err = res["stderr"]
    assert "lance unavailable" in err and "memory.lance" in err and "not deleted" in err, (
        f"stderr must say lance is unavailable and name the rows left: {err!r}")
    if as_json:
        assert '"vector_delete_error"' in res["stdout"], res["stdout"][-1500:]
