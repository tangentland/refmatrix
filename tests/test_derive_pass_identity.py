"""Task 15.1: a pass is stale on ITS OWN code, not on a hash it shares.

`derive_code_hash()` hashed `ingest.py` + `ingest_gmd.py` + `store.py` as one
value, handed to every pass. On 2026-10-06 that flipped this project's own
partition to `behind_code: True` because bug-067's fix added
`Store.grep_evidence` — a READ method, +80 lines, zero effect on what any pass
extracts. The detector was right by its rule and wrong about the graph, and it
could not name a pass because every pass shared the hash.

Per-pass module sets fix both: `gmd` hashes `ingest_gmd.py`, the tree passes
hash `ingest.py`, and `store.py` leaves every set.

HOW THESE TESTS DRIVE IT. The hash reads real files off disk, so the tests edit
real COPIES in a temp tree and point the resolver at them. Monkeypatching the
hash function itself would prove nothing about the mapping — the mapping IS the
thing under test, and a faked hash cannot be wrong in the way a mapping can.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from refmatrix import store as store_mod

SRC = Path(store_mod.__file__).resolve().parent


@pytest.fixture
def modules(tmp_path, monkeypatch):
    """Real copies of the deriving modules, resolved by the hash function.

    The hash resolves `Path(__file__).parent`, so pointing it at a temp dir is
    a one-attribute redirect and the function under test is otherwise intact.
    """
    d = tmp_path / "src"
    d.mkdir()
    for name in ("ingest.py", "ingest_gmd.py", "store.py"):
        shutil.copy2(SRC / name, d / name)
    monkeypatch.setattr(store_mod, "_DERIVE_SRC_DIR", d, raising=False)
    store_mod._DERIVE_CODE_HASH_CACHE.clear()
    yield d
    store_mod._DERIVE_CODE_HASH_CACHE.clear()


def _edit(path: Path, marker: str) -> None:
    """A real content change — the hash is content, not mtime (plan-12 r3)."""
    path.write_text(path.read_text() + f"\n# {marker}\n")
    store_mod._DERIVE_CODE_HASH_CACHE.clear()


# ---- the passes are distinguishable at all -------------------------------

def test_two_passes_hash_differently(modules):
    gmd = store_mod.derive_code_hash("gmd")
    ingest = store_mod.derive_code_hash("ingest")

    assert gmd and ingest
    assert gmd != ingest, (
        "every pass shares one hash, so staleness cannot be attributed")


# ---- the false positive this task exists to remove ----------------------

def test_editing_store_py_does_not_make_any_pass_stale(modules):
    """THE regression under test. `Store.grep_evidence` was a read method and
    it flipped this store to behind_code."""
    before = {p: store_mod.derive_code_hash(p)
              for p in ("ingest", "semantic", "gmd")}

    _edit(modules / "store.py", "a read-only helper, like Store.grep_evidence")

    after = {p: store_mod.derive_code_hash(p) for p in before}
    assert after == before, (
        "an edit to store.py still moves a pass hash — the false positive "
        f"from 2026-10-06 is intact: {before} -> {after}")


def test_editing_a_passs_own_module_does_make_it_stale(modules):
    """The control. A fix that simply stopped hashing anything would pass the
    test above and destroy the detector."""
    before_gmd = store_mod.derive_code_hash("gmd")
    before_ingest = store_mod.derive_code_hash("ingest")

    _edit(modules / "ingest_gmd.py", "a change to what the gmd pass extracts")

    assert store_mod.derive_code_hash("gmd") != before_gmd, (
        "a change to ingest_gmd.py must move the gmd hash")
    assert store_mod.derive_code_hash("ingest") == before_ingest, (
        "a change to ingest_gmd.py must NOT move the tree pass")


def test_editing_ingest_moves_the_tree_passes_only(modules):
    before = {p: store_mod.derive_code_hash(p)
              for p in ("ingest", "semantic", "gmd")}

    _edit(modules / "ingest.py", "a change to the tree extractor")

    after = {p: store_mod.derive_code_hash(p) for p in before}
    assert after["ingest"] != before["ingest"]
    assert after["semantic"] != before["semantic"]
    assert after["gmd"] == before["gmd"]


# ---- the conservative default -------------------------------------------

def test_an_unmapped_pass_hashes_the_union(modules):
    """A pass nobody mapped must read as MAXIMALLY stale, never clean. The
    tempting default — no modules, nothing to compare, so fresh — is a gate
    that cannot fire, which is the failure this project keeps meeting."""
    unmapped = store_mod.derive_code_hash("a-pass-that-does-not-exist")
    union = store_mod.derive_code_hash()

    assert unmapped == union, (
        "an unmapped pass must fall back to the union of every deriving "
        "module, so a new pass is stale until someone maps it")
    assert unmapped != ""


def test_the_no_argument_call_keeps_its_meaning(modules):
    """Existing callers pass nothing and must keep getting the union."""
    union = store_mod.derive_code_hash()

    _edit(modules / "store.py", "store.py is still in the UNION")

    assert store_mod.derive_code_hash() != union, (
        "the no-argument union must still cover store.py — only the PER-PASS "
        "sets drop it")


# ---- what the mapping covers is visible ---------------------------------

def test_the_mapping_is_declared_and_covers_every_stamping_pass():
    """The passes that call `stamp_derive` today are `ingest`, `semantic` and
    `gmd`. Each must be mapped, or it silently gets the union and this task
    bought nothing for it."""
    mapped = store_mod._DERIVE_PASS_MODULES

    for p in ("ingest", "semantic", "gmd"):
        assert p in mapped, f"{p} stamps but has no module set"
        assert mapped[p], f"{p} maps to an empty set, which would read as clean"
        assert "store.py" not in mapped[p], (
            f"{p} still hashes store.py; that is the false positive")
