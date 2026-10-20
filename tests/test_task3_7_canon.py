"""Task 3.7 batch B — `rmx_canon(action=find|siblings|link)` (RED).

Spec #fam-canon, #budgets:
  find     — federated read over every live store (`federated_concept`, as `rmx_where`);
             the result carries `skipped`; no timeout is claimed;
  siblings — `snapshot_read` (C4a: absent ⇒ in-process read-only);
  link     — a WRITE via `_call(root, "link_canon", …)` (60 s, single attempt) with
             `write=True` classification; absent ⇒ `local_write`.

Interpretation (named in the report): `link` resolves the local concept id through the
read route (`snapshot_read`), then sends `link_canon` {local_concept_id, canon_partition,
canon_concept_name, partition}; `canon_name` defaults to the concept's own name.
Result shapes: find = federated_concept's dict; siblings {rows:[…siblings_via_canon…]};
link {canon_id, …}.
"""
from __future__ import annotations

import pytest

from refmatrix import discovery, search, verbs
from refmatrix.store import Store
from tests.task3_7_helpers import FakeDaemon, graph_store, make_snapshot, rm, short_root
from tests.test_plan3_remedy_r7 import up_without_replica  # noqa: F401 — fixture


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37k-")
    yield r
    rm(base)


# ---- find -------------------------------------------------------------------------


def test_find_with_no_live_store_carries_an_empty_skipped(root, monkeypatch):
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(search, "_live_roots", lambda: ([], []))
    out = verbs.canon(root, action="find", concept="alpha")
    assert out["projects"] == [] and out["skipped"] == [], out


def test_find_names_a_store_it_could_not_read(root, up_without_replica, monkeypatch):
    """A REAL up daemon whose replica is missing: the store lands in `skipped`,
    never a silent omission (r6 #s-3's shape, as rmx_where)."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [up_without_replica.root])
    out = verbs.canon(root, action="find", concept="held_row")
    assert out["skipped"], out
    assert any(str(up_without_replica.root) in str(s.get("root")) for s in out["skipped"]), out


# ---- siblings ---------------------------------------------------------------------


def _two_partitions_one_canon(root):
    p = discovery.store_name(root)
    s = Store(root)
    s.init()
    try:
        with s.with_partition(p):
            a = s.add_concept("alpha")
            s.link_canon(a, "canon", "Alpha")
        with s.with_partition("other"):
            b = s.add_concept("alpha_other")
            s.link_canon(b, "canon", "Alpha")
    finally:
        s.close()


def test_siblings_with_no_daemon_reads_in_process(root):
    _two_partitions_one_canon(root)
    out = verbs.canon(root, action="siblings", concept="alpha")
    assert [r["name"] for r in out["rows"]] == ["alpha_other"], out
    assert out["rows"][0]["partition_name"] == "other"
    assert out["source"] == "in-process"


def test_siblings_of_an_unknown_concept_is_a_verb_error(root):
    _two_partitions_one_canon(root)
    with pytest.raises(verbs.VerbError):
        verbs.canon(root, action="siblings", concept="nope")


# ---- link -------------------------------------------------------------------------


@pytest.fixture
def snap_store(root):
    ids = graph_store(root)
    make_snapshot(root)
    return root, ids


def test_link_is_one_classified_write_through_link_canon(snap_store, monkeypatch):
    root, ids = snap_store
    fd = FakeDaemon({"link_canon": {"ok": True, "result": {"canon_id": 4242}}}).install(monkeypatch)
    out = verbs.canon(root, action="link", concept="alpha", canon_name="Alpha")
    _op, args, timeout, retries = fd.last("link_canon")
    assert args["local_concept_id"] == ids["alpha"], args
    assert args["canon_partition"] == "canon" and args["canon_concept_name"] == "Alpha"
    assert args["partition"] == discovery.store_name(root)
    assert timeout == 60.0 and retries == 0, (timeout, retries)
    assert out["canon_id"] == 4242


def test_link_canon_name_defaults_to_the_concept(snap_store, monkeypatch):
    root, _ids = snap_store
    fd = FakeDaemon({"link_canon": {"ok": True, "result": {"canon_id": 1}}}).install(monkeypatch)
    verbs.canon(root, action="link", concept="alpha")
    assert fd.last("link_canon")[1]["canon_concept_name"] == "alpha"


def test_link_forwards_the_cli_partition(root, monkeypatch):
    graph_store(root, partition="px")
    make_snapshot(root)
    fd = FakeDaemon({"link_canon": {"ok": True, "result": {"canon_id": 1}}}).install(monkeypatch)
    verbs.canon(root, action="link", concept="alpha", partition="px")
    assert fd.last("link_canon")[1]["partition"] == "px"


def test_link_timeout_is_busy_and_not_confirmed(snap_store, monkeypatch):
    root, _ids = snap_store
    FakeDaemon({"link_canon": TimeoutError("timed out")}).install(monkeypatch)
    with pytest.raises(verbs.VerbBusyError) as ei:
        verbs.canon(root, action="link", concept="alpha")
    assert "not confirmed" in str(ei.value), str(ei.value)


def test_link_refusal_carries_the_daemons_words(snap_store, monkeypatch):
    root, _ids = snap_store
    FakeDaemon({"link_canon": {"ok": False, "error": "CANARY-canon-no"}}).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.canon(root, action="link", concept="alpha")
    assert "CANARY-canon-no" in str(ei.value)


def test_link_of_an_unknown_concept_sends_nothing(snap_store, monkeypatch):
    root, _ids = snap_store
    fd = FakeDaemon({}).install(monkeypatch)
    with pytest.raises(verbs.VerbError):
        verbs.canon(root, action="link", concept="nope")
    assert "link_canon" not in fd.ops()


def test_link_with_no_daemon_writes_in_process(root):
    graph_store(root)
    out = verbs.canon(root, action="link", concept="alpha", canon_name="Alpha")
    assert out["source"] == "in-process" and isinstance(out["canon_id"], int), out
    s = Store(root, partition="canon")
    try:
        assert s.get_entity("concept", "Alpha") is not None
    finally:
        s.close()
