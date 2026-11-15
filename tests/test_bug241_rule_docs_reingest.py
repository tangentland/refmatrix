"""bug-241 RED: `rmx reingest --force --no-sessions` must land the GMD rule docs as GMD.

WHY (bug-241, 2026-11-14). After the 0.83.0 deploy, bug-216 R4 and a forced reingest of the
live refmatrix store, `scripts/check-rel-landing.py` still counted `target_unresolved` claude 234
and project-profile 38. Both files are GMD, neither is ignored, yet the store held only a plain
`doc` row per file (name = relpath, meta NULL): no GMD doc row (name = doc id, `gmd_version` in
meta) and no `<id>#<anchor>` nodes. Every bug-216 test drove `ingest_path` on a tree WITHOUT a
`.tldr/` cache; the live tree has one (`.tldr/cache/semantic/metadata.json`,
`.tldr/cache/call_graph.json`).

Each case builds a throwaway project shaped like this repo -- root `CLAUDE.md` and
`.claude/PROJECT_PROFILE.md` as GMD files with anchors, `.claude/agents/other.md` (must stay
out), `docs/cite.md` citing `[[claude#x]]` and `[[project-profile#y]]`, one Python file -- under
a SHORT `/tmp` mkdtemp root (macOS `sun_path`). The store first holds the OLD config
(`CLAUDE.md` + `.claude` ignored) and, for `prior=plain_row`, the plain relpath rows an older
store holds for both rule docs (mtime stamped, meta NULL). The ignore file then switches to
R4's (`.claude` + `!.claude/PROJECT_PROFILE.md`) and a REAL daemon (spawned by the dev `rmx`,
code from this checkout via PYTHONPATH) runs the production route:

  route=reingest  `rmx reingest --force --no-sessions --no-embed` (embed needs the shared model
                  workers and writes no GMD rows; every other step is the live command's)
  route=sync      `rmx sync <the three .md files>` -- the function the watcher calls per event

and `tldr` names the tree's cache: none, `.tldr/cache/semantic/metadata.json`, or
`.tldr/cache/call_graph.json`.

The verdict per case: a GMD doc row `claude` / `project-profile` with `gmd_version` meta, the
anchor nodes `claude#x` / `project-profile#y`, `.claude/agents/other.md` absent, and
`check-rel-landing.py --json` on the case's own catalog showing no `target_unresolved` for either
rule doc. No mocks: the real CLI, the real daemon, the real script.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from devbin import dev_env, dev_rmx  # bug-253: the dev rmx, defined once (tests/devbin.py)

REPO = Path(__file__).resolve().parents[1]
RMX = dev_rmx()
LANDING = REPO / "scripts" / "check-rel-landing.py"

OLD_RULES = ["CLAUDE.md", ".claude"]
NEW_RULES = [".claude", "!.claude/PROJECT_PROFILE.md"]


def _gmd(doc_id: str, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "{doc_id} title"\ntags: [t]\n---\n\n'
            f"# {doc_id} {{#root}}\n\n{body}")


FILES = {
    "CLAUDE.md": _gmd("claude", "## Section x {#x}\n\nRule text about frobnication.\n"),
    ".claude/PROJECT_PROFILE.md": _gmd(
        "project-profile", "## Section y {#y}\n\nProfile text about quuxing.\n"),
    ".claude/agents/other.md": _gmd("other-agent", "## Z {#z}\n\nMust stay out.\n"),
    "docs/cite.md": _gmd(
        "cite",
        "## Cites {#cites}\n\nCites both rule docs.\n\n"
        "rel: depends-on -> [[claude#x]]\n"
        "rel: depends-on -> [[project-profile#y]]\n"),
    "src/pkg/a.py": "def hello():\n    return bye()\n\n\ndef bye():\n    return 1\n",
}

# The minimal caches `_ingest_path_inner` takes as the primary source: one unit / one edge, so
# the pass returns n > 0 exactly as the live tree's caches do.
TLDR = {
    "metadata": (".tldr/cache/semantic/metadata.json", {"units": [
        {"qualified_name": "src/pkg/a.py::hello", "file": "src/pkg/a.py", "name": "hello",
         "unit_type": "function", "line": 1, "language": "python"}]}),
    "call_graph": (".tldr/cache/call_graph.json", {"edges": [
        {"from_file": "src/pkg/a.py", "from_func": "hello",
         "to_file": "src/pkg/a.py", "to_func": "bye"}]}),
}

PLAIN_ROWS = ["CLAUDE.md", ".claude/PROJECT_PROFILE.md"]


def _env(root: Path) -> dict:
    # This checkout's code in every child (the dev rmx's site-packages point at the dev tree).
    return {**dev_env(), "REFMATRIX_ROOT": str(root), "RMX_INVOCATION_SOURCE": "eval"}


def _rmx(env: dict, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([str(RMX), *args], env=env, capture_output=True, text=True,
                          timeout=timeout)


def _write_ignore(root: Path, base: list[str], rules: list[str]) -> None:
    (root / ".refmatrix_ignore").write_text("\n".join(base + rules) + "\n")


def _seed_plain_rows(root: Path, proj: Path) -> None:
    """The rows an older store holds: kind doc, name = relpath, meta NULL, mtime stamped.
    Written with the daemon DOWN, on this throwaway store only."""
    from refmatrix.store import Store
    s = Store(root)
    try:
        with s.with_partition(proj.name):
            for rel in PLAIN_ROWS:
                p = proj / rel
                s.upsert_entity(kind="doc", name=rel, path=str(p))
                s.mark_tracked(str(p), p.stat().st_mtime)
    finally:
        s.close()


def _wait_sock(root: Path) -> None:
    for _ in range(120):
        if list(root.glob("*.sock")):
            return
        time.sleep(0.5)
    raise AssertionError(f"daemon socket never appeared under {root}")


CASES = [(tldr, prior, route)
         for route in ("reingest", "sync")
         for tldr in ("none", "metadata", "call_graph")
         for prior in ("fresh", "plain_row")]


@pytest.fixture(scope="module", params=CASES, ids=[f"{r}-tldr_{t}-{p}" for t, p, r in CASES])
def case(request):
    tldr, prior, route = request.param
    assert RMX.exists(), f"dev rmx missing at {RMX}"
    base = Path(tempfile.mkdtemp(prefix="b241.", dir="/tmp")).resolve()
    proj = base / "proj"
    proj.mkdir()
    for rel, text in FILES.items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if tldr != "none":
        rel, payload = TLDR[tldr]
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
    (base / "mem").mkdir()
    root = proj / ".refmatrix"
    env = _env(root)
    out: dict = {"proj": proj, "root": root, "env": env, "base": base}
    try:
        r = _rmx(env, "init", "--path", str(proj), "--no-hooks", "--no-agents",
                 "--no-memory-hooks")
        assert r.returncode == 0, r.stdout + r.stderr
        ign = root / ".refmatrix_ignore"
        base_lines = ign.read_text().splitlines() if ign.exists() else []
        _write_ignore(root, base_lines, OLD_RULES)
        if prior == "plain_row":
            _seed_plain_rows(root, proj)
        r = _rmx(env, "daemon", "start", "--no-watch", timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        _wait_sock(root)
        # The store as it stood before R4: one ingest under the OLD config.
        r = _rmx(env, "ingest", str(proj))
        out["old_ingest"] = r
        assert r.returncode == 0, r.stdout + r.stderr
        _write_ignore(root, base_lines, NEW_RULES)         # R4's edit
        if route == "reingest":
            r = _rmx(env, "reingest", "--force", "--no-sessions", "--no-embed",
                     "--memory-dir", str(base / "mem"), timeout=600)
        else:
            files = []
            for rel in ("CLAUDE.md", ".claude/PROJECT_PROFILE.md", "docs/cite.md"):
                files += ["-f", str(proj / rel)]
            r = _rmx(env, "sync", "--project-root", str(proj), *files)
        out["run"] = r
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        _rmx(env, "daemon", "stop", timeout=120)
    yield out
    shutil.rmtree(base, ignore_errors=True)


def _catalog(root: Path) -> Path:
    active = (root / "active").read_text().strip() if (root / "active").exists() else "A"
    cat = root / f"catalog.{active}.duckdb"
    assert cat.is_file(), f"no writer slot at {cat} (files: {sorted(p.name for p in root.iterdir())})"
    return cat


def _rows(root: Path, name: str) -> list[tuple]:
    import duckdb
    con = duckdb.connect(str(_catalog(root)), read_only=True)
    try:
        return con.execute("SELECT kind, name, path, meta FROM entities WHERE name = ?",
                           [name]).fetchall()
    finally:
        con.close()


def _says(c) -> str:
    return (f"\n--- run stdout ---\n{c['run'].stdout[-3000:]}"
            f"\n--- run stderr ---\n{c['run'].stderr[-2000:]}")


# `cite` is not a rule doc: it shows whether the miss is the rule docs' or every GMD doc's.
DOCS = [("claude", "x"), ("project-profile", "y"), ("cite", "cites")]


@pytest.mark.parametrize("doc_id,anchor", DOCS)
def test_the_rule_doc_has_a_gmd_doc_row(case, doc_id, anchor):
    rows = [r for r in _rows(case["root"], doc_id) if r[0] == "doc"]
    assert rows and all(r[3] and "gmd_version" in json.loads(r[3]) for r in rows), (
        f"no GMD doc row named {doc_id!r} (rows: {rows}); plain rows: "
        f"{[_rows(case['root'], p) for p in PLAIN_ROWS]}" + _says(case))


@pytest.mark.parametrize("doc_id,anchor", DOCS)
def test_the_rule_doc_has_its_anchor_node(case, doc_id, anchor):
    rows = _rows(case["root"], f"{doc_id}#{anchor}")
    assert rows, f"no anchor node {doc_id}#{anchor}" + _says(case)


def test_the_rest_of_dot_claude_stays_out(case):
    """Guard: the re-include is the profile only."""
    assert not _rows(case["root"], "other-agent"), "an ignored .claude doc was ingested"
    assert not _rows(case["root"], ".claude/agents/other.md")


def test_check_rel_landing_shows_no_unresolved_rule_doc_citation(case):
    r = subprocess.run([sys.executable, str(LANDING), str(_catalog(case["root"])),
                        str(case["proj"]), "--json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads(r.stdout)
    by_doc = res["unresolved_by_target_doc"]
    bad = {k: v for k, v in by_doc.items() if k in ("claude", "project-profile")}
    assert not bad, (f"target_unresolved for the rule docs: {bad} (full: {res})"
                     + _says(case))
    # The only authored rel: lines are docs/cite.md's two; both must land (a file that never
    # reached the GMD pass would count `file_not_ingested` instead and hide from `by_doc`).
    assert (res["authored"], res["landed"]) == (2, 2), f"recount: {res}" + _says(case)
