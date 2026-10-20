"""Shared fixtures for the task 3.7 RED tests (the verb-it backlog, batch A).

Not a test module. Everything here builds REAL state — a short `/tmp` store
root (macOS `sun_path` is ~104 bytes, so daemon sockets need it), a real
`Store`, a real read snapshot written the way the daemon writes it — except
`FakeDaemon`, the canned-RPC daemon the project's mock registry classifies as
`external` (the daemon process boundary; row "task 3.7 batch A" in
workflow/test_mock_registry.md). The busy / held cases use the existing REAL
socket fixtures `_SilentDaemon` / `_PingOnlyDaemon` (tests/test_plan2_remedy.py).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from refmatrix import daemon as dm
from refmatrix import discovery
from refmatrix.store import Store


def short_root(prefix: str = "r37-") -> "tuple[Path, Path]":
    """(base, root): `root` = `<base>/proj/.refmatrix`, so the store name is `proj`."""
    base = Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))
    root = base / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    return base, root


def rm(base: Path) -> None:
    shutil.rmtree(base, ignore_errors=True)


def init_store(root: Path, entities=(), *, partition: "str | None" = None) -> None:
    """A real catalog with `entities` = [(kind, name), …] in `partition`
    (default: the project partition). Closed before returning."""
    s = Store(root)
    s.init()
    try:
        with s.with_partition(partition or discovery.store_name(root)):
            for kind, name in entities:
                s.upsert_entity(kind, name)
    finally:
        s.close()


def add_entities(root: Path, entities, *, partition: "str | None" = None) -> None:
    init_store(root, entities, partition=partition)


def entity_names(root: Path, kind: str, *, partition: "str | None" = None) -> set:
    """Names of `kind` entities read from the PRIMARY catalog (a read-write
    open, closed after; only call with no daemon holding the store)."""
    s = Store(root)
    try:
        with s.with_partition(partition or discovery.store_name(root)):
            rows = s._connect().execute(
                "SELECT name FROM entities WHERE partition_id=? AND kind=?",
                (s._partition_id, kind)).fetchall()
        return {r[0] for r in rows}
    finally:
        s.close()


def make_snapshot(root: Path) -> Path:
    """Write `catalog.read.duckdb` the way the daemon does (the
    tests/test_plan3_remedy_r4.py `_snapshot` shape) from the current primary."""
    s = Store(root)
    s.init()
    try:
        d = dm.Daemon(root)
        d.store = s
        d._log = lambda msg: None
        d._snapshot_catalog(force=True)
    finally:
        s.close()
    snap = root / "catalog.read.duckdb"
    assert snap.exists(), "the snapshot helper did not write catalog.read.duckdb"
    return snap


class FakeDaemon:
    """A canned daemon RPC: `discovery.daemon_status` says UP and every
    `daemon.call` is recorded as `(op, args, timeout, retries)` and answered
    from `answers[op]` (a dict response, an exception instance to raise, or a
    callable `(args) -> response`). An op with no answer fails the test — a
    verb that dials something unexpected is a finding, not a default."""

    def __init__(self, answers: "dict | None" = None):
        self.answers = dict(answers or {})
        self.calls: list = []

    def install(self, monkeypatch) -> "FakeDaemon":
        monkeypatch.setattr(discovery, "daemon_status",
                            lambda r, **kw: {"up": True, "busy": False, "pid": 4242})
        monkeypatch.setattr(dm, "ping", lambda *a, **k: True)
        monkeypatch.setattr(dm, "call", self)
        return self

    def __call__(self, root, op, args=None, timeout=60.0, retries=2, **kw):
        self.calls.append((op, dict(args or {}), timeout, retries))
        if op not in self.answers:
            raise AssertionError(f"unexpected daemon op {op!r} args={args!r}")
        a = self.answers[op]
        if isinstance(a, BaseException):
            raise a
        if callable(a):
            return a(dict(args or {}))
        return a

    def ops(self) -> list:
        return [c[0] for c in self.calls]

    def last(self, op: str):
        hits = [c for c in self.calls if c[0] == op]
        assert hits, f"op {op!r} never sent; sent: {self.ops()}"
        return hits[-1]
