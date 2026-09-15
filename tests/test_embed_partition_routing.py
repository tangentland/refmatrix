"""`rmx embed` must route the `memory` kind to the memory partition.

Regression for the recall-empty bug: `embed_cmd` used to send *every* kind to
`_resolve_partition()` (the project/code partition). Memory nodes live in the
memory partition (`memory-<project>` pre-merge), so `rmx embed --kinds memory`
scanned the wrong partition, built no memory vectors, and dense recall came up
empty on every prompt — while the recall hook kept advising the very command
that didn't work.

These tests capture the (partition, kinds) tuples embed_cmd sends to the daemon
`embed` op, so they need neither the dense embedder extra nor a real store.
"""
from __future__ import annotations

from click.testing import CliRunner

from refmatrix.cli import main
import refmatrix.cli as cli
import refmatrix.daemon as daemon_mod


def _patch(monkeypatch, calls):
    """Mock the daemon so embed_cmd's routing runs without a model/store."""
    monkeypatch.setattr(cli, "_resolve_partition", lambda: "testproj")
    monkeypatch.setattr(cli, "_memory_partition_default", lambda: "memory-testproj")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)

    def fake_call(root, op, args, timeout=None):
        assert op == "embed"
        calls.append((args["partition"], tuple(args["kinds"])))
        # embedded==0 or remaining==0 ends the per-partition drain loop.
        return {"ok": True, "result": {"embedded": 0, "remaining": 0}}

    monkeypatch.setattr(daemon_mod, "call", fake_call)


def _init(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    r = CliRunner().invoke(main, ["init"], catch_exceptions=False)
    assert r.exit_code == 0, r.output


def test_embed_memory_routes_to_memory_partition(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    calls: list[tuple[str, tuple]] = []
    _patch(monkeypatch, calls)

    r = CliRunner().invoke(main, ["embed", "--kinds", "memory"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    # The memory kind must land in the memory partition, NOT the project one.
    assert calls == [("memory-testproj", ("memory",))], calls


def test_embed_code_routes_to_project_partition(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    calls: list[tuple[str, tuple]] = []
    _patch(monkeypatch, calls)

    r = CliRunner().invoke(main, ["embed", "--kinds", "code"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert calls == [("testproj", ("code",))], calls


def test_embed_mixed_kinds_split_across_partitions(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    calls: list[tuple[str, tuple]] = []
    _patch(monkeypatch, calls)

    r = CliRunner().invoke(main, ["embed", "--kinds", "code", "--kinds", "memory"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    # Non-memory kinds → project partition; memory → memory partition.
    assert ("testproj", ("code",)) in calls
    assert ("memory-testproj", ("memory",)) in calls
    assert len(calls) == 2, calls


def test_embed_memory_folds_when_partitions_coincide(tmp_path, monkeypatch):
    """Post-merge host: memory partition IS the project partition → one call,
    both kinds, no double-embed of the same partition."""
    _init(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_memory_partition_default", lambda: "testproj")
    calls: list[tuple[str, tuple]] = []
    # _patch overrides _memory_partition_default too; set the rest manually.
    monkeypatch.setattr(cli, "_resolve_partition", lambda: "testproj")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)

    def fake_call(root, op, args, timeout=None):
        calls.append((args["partition"], tuple(args["kinds"])))
        return {"ok": True, "result": {"embedded": 0, "remaining": 0}}

    monkeypatch.setattr(daemon_mod, "call", fake_call)

    r = CliRunner().invoke(main, ["embed", "--kinds", "code", "--kinds", "memory"],
                           catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert calls == [("testproj", ("code", "memory"))], calls
