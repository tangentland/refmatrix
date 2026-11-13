"""MCP `rmx_memory_recall` must do DENSE recall on the MEMORY partition.

Regression for the read-side twin of the embed wrong-partition bug: the handler
used to call the lexical `memory_search` op against `store_name(root)` (the code
partition), so natural-language recall returned `[]` while the CLI (dense, memory
partition) returned ranked hits.

Graduated onto REAL stores by task 25.1 (rev 7 F7, 2026-11-13; registry row "task 25.1 RED --
`daemon.ping` / `daemon.call` … in tests/test_mcp_memory_recall_routing.py"). These tests used to
answer a fake `daemon.call` (`partition_list` / `memory_recall` / `memory_get` /
`memory_recent`) and stub `discovery.discover_roots` / `store_name`, so they proved which op
and payload the handler SENT, never what a store gave back -- and since 25.1 R5 the verb tries
the replica leg first, so a fake RPC "no longer proves the route" (spec #files-to-modify).
Now: real sandbox stores served by real foreground daemons (one with a pre-merge
`memory-<p>` partition, one post-merge), embedded by the real model, and a REAL store
registry under a tmp `RMX_HOME`. The dense-not-lexical proof is behavioural: a query that is
a substring of NO memory still returns ranked rows (the lexical op returned `[]`).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import refmatrix.mcp as mcp
from tests import task21_1_support as h

# No row's content contains this phrase, so a lexical substring op (the old bug) answers [].
NL_QUERY = "which shard owns the reconciliation of overnight ledger batches"
BODIES = {
    "m_route_a": "The quasar ledger is reconciled per shard after the nightly batch closes.",
    "m_route_b": "Zorbulate shards merge their flux batches before the ledger reconcile pass.",
    "m_route_c": "An unrelated note about the colour of the office kettle.",
}


def _short_base(tag: str) -> Path:
    import tempfile
    return Path(tempfile.mkdtemp(prefix=f"{tag}-", dir=os.environ["RMX_SANDBOX_ROOT"]))


def _store_with(base: Path, name: str, partition: "str | None") -> Path:
    """A store at `<base>/<name>/.refmatrix` whose memories sit in `partition` (None = the
    project partition, post-merge)."""
    from refmatrix.store import Store
    root = base / name / ".refmatrix"
    root.parent.mkdir(parents=True)
    st = Store(root)
    try:
        st.init()
        ctx = st.with_partition(partition) if partition else None
        if ctx is not None:
            ctx.__enter__()
        try:
            for n, body in BODIES.items():
                st.add_memory(name=n, content=body, mtype="note")
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
    finally:
        st.close()
    return root


@pytest.fixture(scope="module")
def routed():
    """Two real stores, each served by a real sandbox daemon and embedded: `legacy` holds its
    memories in the pre-merge `memory-legacy` partition, `merged` in its project partition.
    RMX_RERANK=0 (the rows' ORDER is not what these tests check)."""
    from refmatrix import daemon as dm, verbs
    import rmx_sandbox
    base = _short_base("rtg")
    home = base / "g" / ".refmatrix"
    roots = {"legacy": _store_with(base, "legacy", "memory-legacy"),
             "merged": _store_with(base, "merged", None)}
    old = os.environ.get("RMX_HOME")
    os.environ["RMX_HOME"] = str(home)
    ds = []
    try:
        for key, root in roots.items():
            d = h.SandboxDaemon(root, RMX_HOME=str(home), RMX_RERANK="0")
            ds.append(d)
            d.wait_models_warm()
            part = verbs.memory_partition(root, timeout=30)
            assert part == ("memory-legacy" if key == "legacy" else "merged"), (key, part)
            assert dm.call(root, "embed", {"kinds": ["memory"], "partition": part},
                           timeout=900).get("ok")
            assert dm.call(root, "snapshot", {"force": True}, timeout=300).get("ok")
        yield {**roots, "home": home}
    finally:
        for d in ds:
            d.stop()
        if old is None:
            os.environ.pop("RMX_HOME", None)
        else:
            os.environ["RMX_HOME"] = old
        rmx_sandbox.remove_tree(base)


@pytest.fixture
def at_home(routed, monkeypatch):
    monkeypatch.setenv("RMX_HOME", str(routed["home"]))
    monkeypatch.delenv("RMX_RECALL_REPLICA_FIRST", raising=False)
    return routed


def test_recall_uses_dense_op_on_memory_partition(at_home):
    """Legacy `memory-<p>` partition present: a natural-language query (a substring of no
    memory) returns ranked rows from THAT partition -- dense, not the lexical op -- with the
    ranking fields the CLI shows (plan-3 r1 #sk-4)."""
    out = mcp._t_memory_recall({"query": NL_QUERY, "k": 3, "scope": "project",
                                "root": str(at_home["legacy"])})
    rows = out["memories"]
    assert rows, f"dense recall on the legacy memory partition returned nothing: {out}"
    assert {r["name"] for r in rows} <= set(BODIES), rows
    for r in rows:
        assert r["scope"] == "project", r
        assert r.get("distance") is not None and r["fused"] is False and "score" in r, r
    assert any(w.startswith("recall leg:") for w in out.get("warnings") or []), out


def test_recall_falls_back_to_project_partition_post_merge(at_home):
    """No legacy `memory-<p>` partition: the same call reads the PROJECT partition."""
    out = mcp._t_memory_recall({"query": NL_QUERY, "k": 2, "scope": "project",
                                "root": str(at_home["merged"])})
    rows = out["memories"]
    assert rows and {r["name"] for r in rows} <= set(BODIES), out


def test_empty_query_uses_recent_on_memory_partition(at_home):
    """An empty query means "what is recent" (MCP contract since 0.21), on the memory
    partition: every legacy-partition row comes back, newest first."""
    out = mcp._t_memory_recall({"scope": "project", "root": str(at_home["legacy"])})
    assert out["mode"] == "recent", out
    assert {r["name"] for r in out["memories"]} == set(BODIES), out
    assert all(r["scope"] == "project" for r in out["memories"]), out


def test_resolve_root_targets_project_by_name(tmp_path, monkeypatch):
    """Two REGISTERED stores; the cwd is NEITHER. `project` resolves the right root
    independent of the MCP server's cwd (the recall-drift fix) -- over the real registry
    (`discovery.register_root` under a tmp RMX_HOME), not a stubbed `discover_roots`."""
    from refmatrix import discovery
    from refmatrix.store import Store
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home" / ".refmatrix"))
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    roots = {}
    for name in ("cliquedb", "viascope"):
        root = tmp_path / name / ".refmatrix"
        st = Store(root)
        st.init()
        st.close()
        discovery.register_root(root)
        roots[name] = root
    monkeypatch.chdir(tmp_path)
    assert mcp._resolve_root({"project": "cliquedb"}).resolve() == roots["cliquedb"].resolve()
    assert mcp._resolve_root({"project": "viascope"}).resolve() == roots["viascope"].resolve()


def test_resolve_root_explicit_root_beats_project(tmp_path, monkeypatch):
    # `root` wins over `project` (no lookup at all); path normalized to the .refmatrix dir.
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home" / ".refmatrix"))
    got = mcp._resolve_root({"root": str(tmp_path), "project": "ignored"})
    assert got == tmp_path / ".refmatrix"


def test_resolve_root_unknown_project_raises(tmp_path, monkeypatch):
    """Inverted by task 25.1 R10 (bug-181): this test used to PIN the silent fallback --
    an unknown project name fell through to `REFMATRIX_ROOT` (then the cwd store), so a
    caller naming a store that does not exist quietly read another one. A name that resolves
    nothing is now `VerbUnknownProjectError` (a `VerbArgsError`), even with REFMATRIX_ROOT
    set; the real-registry legs are tests/test_task25_1_recall_budget.py::test_ac4e_r10_*.
    Graduated (F7): an EMPTY real registry under a tmp RMX_HOME, no `discover_roots` stub."""
    from refmatrix import verbs
    monkeypatch.setenv("RMX_HOME", str(tmp_path / "home" / ".refmatrix"))
    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    with pytest.raises(verbs.VerbArgsError) as ei:
        mcp._resolve_root({"project": "nope"})
    assert type(ei.value).__name__ == "VerbUnknownProjectError"
    assert "'nope'" in str(ei.value)


# --- _root slug-decode: cwd under ~/.claude/projects/<slug>/ ----------------

def test_root_decodes_projects_slug_to_project_store(tmp_path, monkeypatch):
    import refmatrix.cli as cli
    from pathlib import Path
    # A discovered project store whose parent encodes to <slug>.
    proj = tmp_path / "github" / "acme" / "widget"
    root = proj / ".refmatrix"
    root.mkdir(parents=True)
    slug = str(proj.resolve()).replace("/", "-").replace("_", "-")
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [root])
    # cwd standing inside ~/.claude/projects/<slug>/memory
    cwd = Path.home() / ".claude" / "projects" / slug / "memory"
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: cwd))
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    assert cli._root() == root  # NOT the global home store


def test_root_from_projects_slug_no_match_returns_none(tmp_path, monkeypatch):
    import refmatrix.cli as cli
    from pathlib import Path
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [])
    cwd = Path.home() / ".claude" / "projects" / "-nonexistent-proj" / "memory"
    assert cli._root_from_projects_slug(cwd) is None
    # a cwd outside ~/.claude/projects → None (not a projects-slug dir)
    assert cli._root_from_projects_slug(tmp_path) is None
