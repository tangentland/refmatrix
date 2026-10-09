"""A derive stamp that is WRONG has to be removable (bug-098 residue).

bug-098 wrote a forced reingest's `ingest`/`semantic` stamps into
`sessions-refmatrix`, a partition no project ingest derives. The rows were
repaired; the two stamps could not be, because `derive_stamps` only ever
upserts. They keep `rmx daemon status` reporting the sessions partition as
"derived at 0.77.0" by passes that never ran on it.

`rmx derive unstamp PASS` removes ONE pass's stamp from the bound partition,
leaves `derive_history` (the record of what ran) alone, and refuses a
partition that does not exist instead of creating it.
"""
from __future__ import annotations

import threading

import pytest

from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _stamps(s: Store) -> set[tuple[str, str]]:
    names = dict(s._connect().execute("SELECT id, name FROM partitions").fetchall())
    return {(names[p], n) for p, n in s._connect().execute(
        "SELECT partition_id, pass_name FROM derive_stamps").fetchall()}


def test_unstamp_removes_one_pass_in_one_partition(store):
    with store.with_partition("sess"):
        store.stamp_derive("ingest")
        store.stamp_derive("gmd")
    store.stamp_derive("ingest")                          # the default partition keeps its own
    home = store._partition_name
    with store.with_partition("sess"):
        assert store.unstamp_derive("ingest") is True
        assert store.unstamp_derive("ingest") is False     # already gone: said, not raised
        history = store.derive_history("ingest")
    assert _stamps(store) == {("sess", "gmd"), (home, "ingest")}
    assert history, "the history of what ran must survive an unstamp"


def _daemon(store):
    from refmatrix.daemon import Daemon

    d = object.__new__(Daemon)
    d.root = store.root
    d.store = store
    d._store_lock = threading.Lock()
    d._log = lambda *a, **k: None
    d._request_snapshot = lambda: None
    return d


def test_the_op_unstamps_the_named_partition(store):
    from refmatrix.daemon import _op_derive_unstamp

    with store.with_partition("sess"):
        store.stamp_derive("semantic")
    out = _op_derive_unstamp(_daemon(store), {"pass_name": "semantic", "partition": "sess"})
    assert out == {"ok": True, "pass_name": "semantic", "partition": "sess", "removed": True}
    assert ("sess", "semantic") not in _stamps(store)


def test_the_op_refuses_an_unknown_partition_and_creates_nothing(store):
    from refmatrix.daemon import _op_derive_unstamp

    out = _op_derive_unstamp(_daemon(store), {"pass_name": "ingest", "partition": "nosuch"})
    made = store._connect().execute(
        "SELECT count(*) FROM partitions WHERE name='nosuch'").fetchone()[0]
    assert out["ok"] is False and "unknown partition" in out["error"], out
    assert made == 0


def test_the_op_requires_a_pass_and_a_partition(store):
    from refmatrix.daemon import _op_derive_unstamp

    assert _op_derive_unstamp(_daemon(store), {"partition": "x"})["ok"] is False
    assert _op_derive_unstamp(_daemon(store), {"pass_name": "ingest"})["ok"] is False


def test_the_cli_unstamps_the_dash_p_partition(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    root = tmp_path / ".refmatrix"
    s = Store(root)
    s.init()
    with s.with_partition("sess"):
        s.stamp_derive("ingest")
        s.stamp_derive("gmd")
    s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli_mod.main, ["-p", "sess", "derive", "unstamp", "ingest"])
    assert res.exit_code == 0, res.output
    assert "removed" in res.output and "sess" in res.output, res.output
    s = Store(root)
    try:
        assert _stamps(s) == {("sess", "gmd")}
    finally:
        s.close()
    res = CliRunner().invoke(cli_mod.main, ["-p", "sess", "derive", "unstamp", "ingest"])
    assert res.exit_code != 0 and "no `ingest` stamp" in res.output, res.output
