"""bug-216 R2 under the user's condition — hidden-dir files never pollute the graph, and the
memory bridge still lands memories that live under `~/.claude/`.

The lead ruled (2026-11-13) that R2 supersedes 26.1 AC-2's "the doc walk reads dot-dirs"
(tests/test_memory_bridge.py::test_ac2_doc_ingest_keeps_its_own_walk). The user made that
conditional: "as long as the files [in] hidden directories don't pollute the graph because of
incorrect classification." This file pins the condition on the STORE, not on a walk's file list:

  (a) a memdir's `.organise-rollback-1/x.md` and `.hidden/y.md` reach the store through NO
      route — the doc walk, the `--as-memory` bridge (daemon op and in-process CLI), prestage,
      sync and the watcher: no entity of any kind with a path under either dot-dir, no entity
      named after their GMD ids or their body sentinel, no `linkage_evidence` row from them,
      no `entity_links` row naming such an entity;
  (b) the ONE hidden-dir file bug-216 re-includes, `.claude/PROJECT_PROFILE.md` (by the `!`
      line), lands exactly once, as kind=doc named `project-profile`, in the project partition
      — never as kind=memory, never twice — and `.claude/agents/x.md` lands nowhere;
  (c) the positive pin (addendum 2, the important one): a real memdir lives under
      `~/.claude/projects/<slug>/memory`, a path with a hidden segment. Here the memdir sits
      under `<proj>/.claude/projects/x/memory` AND the project's ignore file lists `.claude`,
      so a `should_ignore` leaking into the memory walk (hidden-dir rule or the `.claude` line)
      would drop EVERY memory. The bridge must land `keep_top` / `keep_nested` as kind=memory,
      report no exclusion for them, and still exclude the two dot-dir files.

NOT pinned here: the doc walk run on a memdir lands the memdir's VISIBLE memory files
(`keep_top`, `keep_nested`) as kind=doc. That is pre-existing, not hidden-dir specific, and is
bug-220 (dev master); the route below that does it is not an endorsement of doc-kind memory rows.

Every store is a throwaway under a short `/tmp` mkdtemp root; no live `.refmatrix/` is touched.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix.store import Store

SENTINEL = "quodlibetzanzibar"     # a body term only the dot-dir files carry
DOT_IDS = ("rollback_aside_q7", "hidden_aside_q7")
MEM_PARTITION = "memory-proj"


def _gmd(doc_id: str, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n'
            f"metadata:\n  type: feedback\n---\n\n# Fixture document {{#root}}\n\n{body}\n\n"
            f"## Part {{#part}}\n\nMore text.\n")


# Two layouts, because each has a different rule doing the excluding:
#   dot-claude  the memdir sits under `<proj>/.claude/projects/x/memory` (the real shape) and the
#               ignore file lists `.claude` — the spec line ALSO covers the dot-dir files, so this
#               layout alone cannot tell whether the hidden-dir rule is doing anything;
#   visible     the memdir sits under `<proj>/notes/memory`, no spec line covers it, and ONLY the
#               built-in hidden-dir rule keeps `.organise-rollback-1/` and `.hidden/` out.
LAYOUTS = ("dot-claude", "visible")


def _make(layout: str = "dot-claude") -> dict:
    base = Path(rmx_sandbox.short_root("b216h")).resolve()
    proj = base / "proj"
    mem = (proj / ".claude" / "projects" / "x" / "memory" if layout == "dot-claude"
           else proj / "notes" / "memory")
    files = {
        proj / ".claude" / "PROJECT_PROFILE.md": _gmd("project-profile", "Project facts."),
        proj / ".claude" / "agents" / "x.md": _gmd("agent-x", "An agent template."),
        proj / "docs" / "d.md": _gmd("d", "A real doc."),
        mem / "keep_top.md": _gmd("keep_top", "A top-level memory."),
        mem / "feedback" / "keep_nested.md": _gmd("keep_nested", "A memory in a type folder."),
        mem / ".organise-rollback-1" / "x.md": _gmd(DOT_IDS[0], f"An aside {SENTINEL}."),
        mem / ".hidden" / "y.md": _gmd(DOT_IDS[1], f"A dot-dir file {SENTINEL}."),
    }
    for p, body in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    root = proj / ".refmatrix"
    root.mkdir()
    (root / ".refmatrix_ignore").write_text(".claude\n!.claude/PROJECT_PROFILE.md\n")
    s = Store(root)
    s.init()
    s.close()
    return {"base": base, "proj": proj, "root": root, "mem": mem,
            "dot_dirs": [mem / ".organise-rollback-1", mem / ".hidden"],
            "profile": proj / ".claude" / "PROJECT_PROFILE.md",
            "agent": proj / ".claude" / "agents" / "x.md"}


@pytest.fixture(params=LAYOUTS)
def env(request):
    e = _make(request.param)
    yield e
    shutil.rmtree(e["base"])


@pytest.fixture
def dot_claude_env():
    e = _make("dot-claude")
    yield e
    shutil.rmtree(e["base"])


def _open(root: Path) -> Store:
    s = Store(root)
    s.init()
    return s


# ---------------------------------------------------------------- routes


def _daemon(root: Path):
    from refmatrix.daemon import Daemon
    d = Daemon(root)
    d.store = _open(root)
    return d


def r_doc_walk_op(e, mp):
    """The DOC walk on the memdir (no as_memory) — the route bug-220 is about."""
    from refmatrix.daemon import _op_ingest_gmd
    d = _daemon(e["root"])
    try:
        return _op_ingest_gmd(d, {"targets": [str(e["mem"])]})
    finally:
        d.store.close()


def r_doc_walk_cli(e, mp):
    return _cli(e, mp, ["ingest-gmd", str(e["mem"])])


def r_bridge_op(e, mp):
    from refmatrix.daemon import _op_ingest_gmd
    d = _daemon(e["root"])
    try:
        return _op_ingest_gmd(d, {"targets": [str(e["mem"])], "as_memory": True,
                                  "partition": MEM_PARTITION})
    finally:
        d.store.close()


def r_bridge_cli(e, mp):
    return _cli(e, mp, ["ingest-gmd", "--as-memory", str(e["mem"])])


def r_prestage_op(e, mp):
    from refmatrix.daemon import _op_prestage_hashes
    r_bridge_op(e, mp)
    d = _daemon(e["root"])
    try:
        return _op_prestage_hashes(d, {"targets": [str(e["mem"])], "as_memory": True,
                                       "partition": MEM_PARTITION})
    finally:
        d.store.close()


def r_project_sync(e, mp):
    from tests.test_bug216_rule_docs_e2e import _run
    return _run("sync", e["proj"], e["root"], mp)


def r_project_watcher(e, mp):
    from tests.test_bug216_rule_docs_e2e import _run
    return _run("watcher", e["proj"], e["root"], mp)


def r_project_ingest_gmd(e, mp):
    from tests.test_bug216_rule_docs_e2e import _run
    return _run("op-ingest-gmd", e["proj"], e["root"], mp)


def r_project_ingest_path(e, mp):
    from tests.test_bug216_rule_docs_e2e import _run
    return _run("ingest-path", e["proj"], e["root"], mp)


def _cli(e, mp, argv):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    mp.setenv("REFMATRIX_ROOT", str(e["root"]))
    mp.delenv("RMX_PARTITION", raising=False)
    r = CliRunner().invoke(cli_mod.main, argv, catch_exceptions=False)
    assert r.exit_code == 0, r.output
    return {"report": r.output}


ROUTES = {
    "doc-walk-op": r_doc_walk_op, "doc-walk-cli": r_doc_walk_cli,
    "bridge-op": r_bridge_op, "bridge-cli": r_bridge_cli, "prestage-op": r_prestage_op,
    "project-sync": r_project_sync, "project-watcher": r_project_watcher,
    "project-ingest-gmd": r_project_ingest_gmd, "project-ingest-path": r_project_ingest_path,
}


# ---------------------------------------------------------------- (a) no pollution


def _pollution(e) -> dict:
    s = _open(e["root"])
    try:
        con = s._connect()
        prefixes = [str(d) + "/" for d in e["dot_dirs"]]
        ents = [r for r in con.execute("SELECT id, kind, name, path FROM entities").fetchall()
                if (r[3] and any(str(r[3]).startswith(p) for p in prefixes))
                or str(r[2]).split("#")[0] in DOT_IDS or SENTINEL in str(r[2]).lower()]
        ids = [int(r[0]) for r in ents]
        ev = [r for r in con.execute("SELECT file, line FROM linkage_evidence").fetchall()
              if r[0] and any(str(r[0]).startswith(p) for p in prefixes)]
        links = 0
        if ids:
            ph = ",".join("?" * len(ids))
            links = con.execute(
                f"SELECT count(*) FROM entity_links WHERE entity_id IN ({ph}) "
                f"OR concept_id IN ({ph})", (*ids, *ids)).fetchone()[0]
        return {"entities": [(k, n, p) for _i, k, n, p in ents], "evidence": ev,
                "links": links}
    finally:
        s.close()


@pytest.mark.parametrize("route", list(ROUTES))
def test_a_dot_dir_files_reach_the_store_through_no_route(route, env, monkeypatch):
    ROUTES[route](env, monkeypatch)
    got = _pollution(env)
    assert got == {"entities": [], "evidence": [], "links": 0}, f"{route}: {got}"


def test_a_dot_dir_files_reach_the_store_through_no_route_all_routes_in_turn(env,
                                                                             monkeypatch):
    for name, fn in ROUTES.items():
        fn(env, monkeypatch)
        got = _pollution(env)
        assert got == {"entities": [], "evidence": [], "links": 0}, f"after {name}: {got}"


# ---------------------------------------------------------------- (b) the re-included profile


def _profile_rows(e) -> dict:
    s = _open(e["root"])
    try:
        con = s._connect()
        rows = con.execute(
            "SELECT e.kind, p.name FROM entities e JOIN partitions p ON p.id = e.partition_id "
            "WHERE e.name = 'project-profile'").fetchall()
        agent = con.execute(
            "SELECT kind, name FROM entities WHERE path = ? OR name = 'agent-x' "
            "OR name LIKE 'agent-x#%'", (str(e["agent"]),)).fetchall()
        return {"profile": sorted((str(k), str(n)) for k, n in rows),
                "agent": [tuple(r) for r in agent]}
    finally:
        s.close()


PROFILE_ONCE = {"profile": [("doc", "proj")], "agent": []}
PROJECT_ROUTES = ["project-sync", "project-watcher", "project-ingest-gmd", "project-ingest-path"]


@pytest.mark.parametrize("route", PROJECT_ROUTES)
def test_b_the_reincluded_profile_lands_once_as_a_project_doc(route, env, monkeypatch):
    ROUTES[route](env, monkeypatch)
    assert _profile_rows(env) == PROFILE_ONCE, route


def test_b_every_route_in_turn_still_leaves_one_profile_doc_and_no_agent(env, monkeypatch):
    """Every route, one after another, on one store: the bridge routes must not pick the
    profile up as a memory, and the project routes must not land it twice."""
    for name, fn in ROUTES.items():
        fn(env, monkeypatch)
    assert _profile_rows(env) == PROFILE_ONCE


# ---------------------------------------------------------------- (c) the bridge lands memories


def _memory_names(e) -> set[str]:
    s = _open(e["root"])
    try:
        return {str(r[0]) for r in s._connect().execute(
            "SELECT name FROM entities WHERE kind = 'memory'").fetchall()}
    finally:
        s.close()


def test_c_the_bridge_op_lands_memories_under_a_dot_claude_path(dot_claude_env, monkeypatch):
    """The memdir's absolute path contains `.claude` and the project ignore file lists `.claude`;
    the --as-memory daemon op must still land both memories and exclude only the dot-dirs."""
    env = dot_claude_env
    assert ".claude" in env["mem"].parts
    res = r_bridge_op(env, monkeypatch)
    assert {"keep_top", "keep_nested"} <= _memory_names(env), (
        f"the bridge dropped memories under a .claude path: {res.get('report')}")
    skipped = {Path(p) for p in res.get("skipped_paths") or []}
    assert not any(p.name.startswith("keep_") for p in skipped), skipped
    assert {p.parent for p in skipped} >= set(env["dot_dirs"]), skipped
    assert "keep_" not in "\n".join(
        ln for ln in str(res.get("report")).splitlines() if "ignored" in ln or "skipped" in ln)


def test_c_the_in_process_bridge_lands_memories_under_a_dot_claude_path(dot_claude_env,
                                                                       monkeypatch):
    env = dot_claude_env
    assert ".claude" in env["mem"].parts
    out = r_bridge_cli(env, monkeypatch)["report"]
    assert {"keep_top", "keep_nested"} <= _memory_names(env), out
    exclusion_lines = [ln for ln in out.splitlines() if "ignored" in ln or "skipped" in ln]
    assert not any("keep_" in ln for ln in exclusion_lines), exclusion_lines
    assert any(".organise-rollback-1" in ln for ln in exclusion_lines), out
    assert any(".hidden" in ln for ln in exclusion_lines), out
