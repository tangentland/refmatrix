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


# ---- batch B: a graph fixture with real Lance vectors ------------------------


class HashEmbedder:
    """ONE deterministic test embedder (task 3.7 #fam-graph-read-recall, r2 M3):
    injected into BOTH the base CLI's `Embedder()` and the daemon's `d._embedder()`
    so a rank order can be pinned across the two paths. sha256 → 8 floats, L2-normed."""
    dim = 8
    model_name = "test-hash-8"

    def embed_texts(self, texts):
        import hashlib

        import numpy as np
        out = []
        for t in texts:
            h = hashlib.sha256(str(t).encode()).digest()
            v = np.frombuffer(h[:self.dim * 4], dtype=np.uint32).astype("float32")
            out.append(v / np.linalg.norm(v))
        return np.vstack(out).astype("float32")


def graph_store(root: Path, *, partition: "str | None" = None) -> dict:
    """concepts alpha / beta; docs d0..d5 (`path` under the project dir); alpha
    `mentions` d0..d3 with weights 1..4, beta `mentions` d2..d5; one 8-dim
    HashEmbedder vector per doc ("document number i"). Ids are deterministic on a
    fresh store: alpha=1, beta=2, d0..d5=3..8. Returns the ids."""
    p = partition or discovery.store_name(root)
    s = Store(root)
    s.init()
    try:
        with s.with_partition(p):
            a = s.add_concept("alpha")
            b = s.add_concept("beta")
            docs = [s.upsert_entity("doc", f"d{i}.md", path=str(root.parent / f"d{i}.md"))
                    for i in range(6)]
            for j, d in enumerate(docs[:4]):
                s.link("mentions", a, d, weight=float(j + 1))
            for d in docs[2:]:
                s.link("mentions", b, d)
            emb = HashEmbedder()
            s.upsert_vector(docs, emb.embed_texts([f"document number {i}" for i in range(6)]),
                            kind="doc", dim=emb.dim)
    finally:
        s.close()
    return {"alpha": a, "beta": b, "docs": docs}
