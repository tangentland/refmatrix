"""bug-216 AC-2 (R1+R2), AC-3 (R2) and R2's behavioural walker table — end to end on a throwaway
store.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#ac-2, #ac-3, #r2).

Every route is the production one, on a REAL `Store` under a SHORT `/tmp` mkdtemp root (macOS
`sun_path` is ~104 bytes; the in-process daemon opens no socket here, but the root shape is the
one the daemon tests use):

  sync     `sync.sync_files` -> `_sync_paths` -> `_sync_one` (the route the watcher, the
           post-commit hook and `rmx sync` share)
  watcher  `Daemon._start_watcher`: the REAL handler, debouncer, `_flush` and `sync_files`.
           Only `watchdog.observers.Observer` is replaced (external library; the fake records
           the handler so events are delivered deterministically instead of by FSEvents).
  ingest-gmd (daemon)  `daemon._op_ingest_gmd` on an in-process `Daemon` (no socket)
  ingest-gmd (cli)     `rmx ingest-gmd <proj>` through CliRunner with no daemon up: the CLI's
                       in-process branch (`_ingest_gmd_in_process`)
  ingest   `ingest.ingest_path` (the full `rmx ingest` walk)

Direction (bug-216's corrected diagnosis, 2026-11-13): the ingester stores `rel: X verb -> Y` as
`store.link(verb, X, Y)` = (linkage, concept, entity), i.e. `entity_links(entity_id = Y = the
TARGET, concept_id = X = the SOURCE)`. Every edge assertion below reads it that way and also
pins that the reversed row does NOT exist.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from refmatrix.store import Store

# ---------------------------------------------------------------- the fixture repo

CLAUDE_MD = """---
gmd: "0.1"
id: claude
title: "Project rules"
tags: [rules]
---

# Project rules {#root}

## No silent failures {#no-silent-failures}

Anything between a memory file and the store surfaces its failure.
"""

PROFILE_MD = """---
gmd: "0.1"
id: project-profile
title: "Project profile"
tags: [profile]
---

# Project profile {#root}

## Project constraints {#constraints}

Store access routes through the daemon.
"""

AGENT_MD = """---
gmd: "0.1"
id: agent-x
title: "An agent template"
tags: [agent]
---

# An agent template {#root}

## Duty {#duty}

Program data, not knowledge.
"""

FINDING_MD = """---
gmd: "0.1"
id: finding
title: "A finding"
tags: [audit]
---

# A finding {#root}

Intro paragraph.

## The swallow {#swallow}

A bare except hides the failure.

rel: contradicts -> [[claude#no-silent-failures]]

## The profile cite {#profile-cite}

Opens the catalog directly.

rel: contradicts -> [[project-profile#constraints]]
"""


def _mini(doc_id: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "{doc_id}"\ntags: [t]\n---\n\n'
            f"# {doc_id} {{#root}}\n\nBody.\n")


def _rel_line(text: str, needle: str) -> int:
    """1-based line number of the `rel:` line citing `needle` (the evidence row's `line`)."""
    hits = [i for i, ln in enumerate(text.splitlines(), 1)
            if ln.startswith("rel:") and needle in ln]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


CLAUDE_LINE = _rel_line(FINDING_MD, "[[claude#no-silent-failures]]")
PROFILE_LINE = _rel_line(FINDING_MD, "[[project-profile#constraints]]")

# R4's config for this store (spec #r4): the CLAUDE.md line removed, `.claude` kept, the profile
# re-included. `src/refmatrix/templates` is the live file's other program-data line.
NEW_SPEC = [".claude", "!.claude/PROJECT_PROFILE.md", "src/refmatrix/templates",
            "!node_modules/n.md"]
# The config at HEAD (2026-09-04).
OLD_SPEC = [".claude", "CLAUDE.md", "src/refmatrix/templates"]

# Files whose GMD doc must reach the store under NEW_SPEC — the same set for EVERY walker (R2).
# Excluded: the agent template (spec `.claude`, hidden dir), the template dir (spec, anchored),
# node_modules (INGEST_IGNORE_DIRS — the `!node_modules/n.md` line must not beat it).
EXPECTED_NEW = {"CLAUDE.md", ".claude/PROJECT_PROFILE.md", "docs/finding.md", "docs/other.md"}
EXPECTED_OLD = {"docs/finding.md", "docs/other.md"}


def _make_proj() -> tuple[Path, Path, Path]:
    """(base, proj, store_root). `store_root` = `<proj>/.refmatrix` with an initialised store."""
    base = Path(tempfile.mkdtemp(prefix="b216", dir="/tmp")).resolve()
    proj = base / "proj"
    files = {
        "CLAUDE.md": CLAUDE_MD,
        ".claude/PROJECT_PROFILE.md": PROFILE_MD,
        ".claude/agents/x.md": AGENT_MD,
        "docs/finding.md": FINDING_MD,
        "docs/other.md": _mini("other"),
        "src/refmatrix/templates/t.md": _mini("template-t"),
        "node_modules/n.md": _mini("vendored-n"),
    }
    for rel, body in files.items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    root = proj / ".refmatrix"
    root.mkdir()
    s = Store(root)
    try:
        s.init()
    finally:
        s.close()
    return base, proj, root


def _write_spec(proj: Path, lines: list[str]) -> None:
    f = proj / ".refmatrix" / ".refmatrix_ignore"
    old = f.stat().st_mtime if f.exists() else None
    f.write_text("\n".join(lines) + "\n")
    if old is not None:  # load_ignore_spec caches by mtime
        os.utime(f, (old + 5, old + 5))


@pytest.fixture
def proj_new():
    base, proj, root = _make_proj()
    _write_spec(proj, NEW_SPEC)
    yield proj, root
    shutil.rmtree(base)


@pytest.fixture
def proj_old():
    base, proj, root = _make_proj()
    _write_spec(proj, OLD_SPEC)
    yield proj, root
    shutil.rmtree(base)


def _all_files(proj: Path) -> list[Path]:
    return sorted(p for p in proj.rglob("*.md")
                  if p.is_file() and ".refmatrix" not in p.relative_to(proj).parts)


# ---------------------------------------------------------------- reading the store back


def _open(root: Path) -> Store:
    s = Store(root)
    s.init()
    return s


def _eid(s: Store, kind: str, name: str) -> int | None:
    e = s.get_entity(kind, name)
    return None if e is None else e.id


def _ingested(s: Store, proj: Path) -> set[str]:
    """Project-relative files that own at least one entity in the store's partition."""
    rows = s._connect().execute(
        "SELECT DISTINCT path FROM entities WHERE partition_id=? AND path IS NOT NULL",
        (s._partition_id,)).fetchall()
    out: set[str] = set()
    for (p,) in rows:
        try:
            out.add(Path(p).resolve().relative_to(proj).as_posix())
        except ValueError:
            continue
    return out


def _lid(s: Store, verb: str) -> int | None:
    row = s._connect().execute("SELECT id FROM linkage_types WHERE name=?", (verb,)).fetchone()
    return None if row is None else row[0]


def _edge_rows(s: Store, verb: str, entity_id: int, concept_id: int) -> int:
    lid = _lid(s, verb)
    if lid is None:
        return 0
    return s._connect().execute(
        "SELECT count(*) FROM entity_links WHERE linkage_id=? AND entity_id=? AND concept_id=?",
        (lid, entity_id, concept_id)).fetchone()[0]


def _evidence(s: Store, verb: str, entity_id: int, concept_id: int) -> list[tuple]:
    lid = _lid(s, verb)
    if lid is None:
        return []
    return s._connect().execute(
        "SELECT file, line FROM linkage_evidence WHERE linkage_id=? AND entity_id=? "
        "AND concept_id=?", (lid, entity_id, concept_id)).fetchall()


TARGET_FILE = {"claude": "CLAUDE.md", "project-profile": ".claude/PROJECT_PROFILE.md"}


def _assert_edge_landed(s: Store, proj: Path, target: str, src: str, line: int) -> None:
    """The node exists, ONE `contradicts` edge lands on it in the store's direction, and its
    evidence row names the citing file and line."""
    tgt = _eid(s, "concept", target)
    assert tgt is not None, f"no `{target}` node in the store"
    # The NODE ENTITY of the rule doc, not merely some row with that name (lead, 2026-11-13:
    # bsd-215m1 found ~38% of resolved rel: lines landing on a path-less same-named concept).
    ent = s.get_entity_by_id(tgt)
    want = TARGET_FILE[target.split("#")[0]]
    assert ent.kind == "concept" and ent.path and \
        Path(ent.path).resolve() == (proj / want).resolve(), (
            f"`{target}` is not {want}'s node entity: kind={ent.kind} path={ent.path}")
    src_id = _eid(s, "concept", src)
    assert src_id is not None, f"no `{src}` node (the citing section) in the store"
    lid = _lid(s, "contradicts")
    assert lid is not None, "no `contradicts` linkage type at all"
    into = s._connect().execute(
        "SELECT concept_id FROM entity_links WHERE linkage_id=? AND entity_id=?",
        (lid, tgt)).fetchall()
    assert [r[0] for r in into] == [src_id], (
        f"`{target}` must carry exactly one contradicts edge, from `{src}`; got {into}")
    assert _edge_rows(s, "contradicts", src_id, tgt) == 0, (
        "edge stored source->target: entity_id must be the TARGET, concept_id the SOURCE")
    ev = _evidence(s, "contradicts", tgt, src_id)
    finding = str(proj / "docs" / "finding.md")
    assert [(Path(f).resolve().as_posix(), ln) for f, ln in ev] == \
        [(Path(finding).resolve().as_posix(), line)], f"evidence rows: {ev}"


def _assert_no_node(s: Store, target: str, src: str) -> None:
    assert _eid(s, "concept", target) is None, f"`{target}` node exists under the old config"
    src_id = _eid(s, "concept", src)
    assert src_id is not None, f"the citing section `{src}` was not ingested at all"
    lid = _lid(s, "contradicts")
    if lid is not None:
        out = s._connect().execute(
            "SELECT count(*) FROM entity_links WHERE linkage_id=? AND concept_id=?",
            (lid, src_id)).fetchone()[0]
        ev = s._connect().execute(
            "SELECT count(*) FROM linkage_evidence WHERE linkage_id=? AND concept_id=?",
            (lid, src_id)).fetchone()[0]
        assert (out, ev) == (0, 0), f"`{src}` has a contradicts edge/evidence with no target"


def _assert_rest_of_dot_claude_stays_out(s: Store, proj: Path) -> None:
    """The re-include lets ONE file in; the rest of `.claude/` (agent templates) stays out
    (spec #why-consistent). At HEAD ingest-gmd's walk takes it, as it takes every `*.md`."""
    assert _eid(s, "concept", "agent-x#duty") is None, "the agent template reached the store"
    assert ".claude/agents/x.md" not in _ingested(s, proj)


# ---------------------------------------------------------------- the routes


def _route_sync(proj: Path, root: Path) -> dict:
    from refmatrix.sync import sync_files
    s = _open(root)
    try:
        rep = sync_files(s, [str(p) for p in _all_files(proj)], project_root=proj)
    finally:
        s.close()
    assert not rep.get("memory_ownership_errors"), rep
    return {"report": rep}


class _FakeObserver:
    """`watchdog.observers.Observer` stand-in (external library). Records each scheduled
    handler so the test delivers events itself; start/stop/join are no-ops."""
    instances: list["_FakeObserver"] = []

    def __init__(self, *a, **k):
        self.handlers: list[tuple[object, str]] = []
        _FakeObserver.instances.append(self)

    def schedule(self, handler, path, recursive=False):
        self.handlers.append((handler, path))

    def start(self):
        pass

    def stop(self):
        pass

    def join(self, timeout=None):
        pass


def _route_watcher(proj: Path, root: Path, monkeypatch) -> dict:
    import watchdog.observers as wo
    from watchdog.events import FileModifiedEvent

    from refmatrix.daemon import Daemon
    _FakeObserver.instances = []
    monkeypatch.setattr(wo, "Observer", _FakeObserver)
    d = Daemon(root, watch_root=proj, watch_debounce_ms=50)
    d.store = _open(root)
    try:
        d._start_watcher()
        assert len(_FakeObserver.instances) == 1, "watcher did not build one observer"
        (handler, path), = _FakeObserver.instances[0].handlers
        assert Path(path).resolve() == proj
        for p in _all_files(proj):
            handler.on_modified(FileModifiedEvent(str(p)))
        # Stopping the runner runs `debouncer.stop()`, which flushes what is pending through
        # the REAL `_flush` -> `sync_files` on this thread before `join` returns.
        d._watch_stop.set()
        d._watch_thread.join(timeout=30)
        assert not d._watch_thread.is_alive(), "watcher thread did not stop"
        assert d.sync_errors() == [], f"the watcher flush failed: {d.sync_errors()}"
    finally:
        d.store.close()
    return {}


def _route_op_ingest_gmd(proj: Path, root: Path) -> dict:
    from refmatrix.daemon import Daemon, _op_ingest_gmd
    d = Daemon(root)
    d.store = _open(root)
    try:
        res = _op_ingest_gmd(d, {"targets": [str(proj)]})
    finally:
        d.store.close()
    return res


def _route_cli_ingest_gmd(proj: Path, root: Path, monkeypatch) -> dict:
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", str(proj)], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    return {"report": r.output}


def _route_ingest_path(proj: Path, root: Path) -> dict:
    from refmatrix.ingest import ingest_path
    s = _open(root)
    try:
        n = ingest_path(s, proj)
    finally:
        s.close()
    return {"n": n}


ROUTES = ["sync", "watcher", "op-ingest-gmd", "cli-ingest-gmd", "ingest-path"]


def _run(route: str, proj: Path, root: Path, monkeypatch) -> dict:
    if route == "sync":
        return _route_sync(proj, root)
    if route == "watcher":
        return _route_watcher(proj, root, monkeypatch)
    if route == "op-ingest-gmd":
        return _route_op_ingest_gmd(proj, root)
    if route == "cli-ingest-gmd":
        return _route_cli_ingest_gmd(proj, root, monkeypatch)
    if route == "ingest-path":
        return _route_ingest_path(proj, root)
    raise AssertionError(route)


# ---------------------------------------------------------------- AC-2


AC2_ROUTES = ["sync", "watcher", "op-ingest-gmd", "cli-ingest-gmd"]


@pytest.mark.parametrize("route", AC2_ROUTES)
def test_ac2_reinclude_config_lands_the_claude_node_and_its_edge(route, proj_new, monkeypatch):
    proj, root = proj_new
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        _assert_edge_landed(s, proj, "claude#no-silent-failures", "finding#swallow", CLAUDE_LINE)
        _assert_rest_of_dot_claude_stays_out(s, proj)
    finally:
        s.close()


@pytest.mark.parametrize("route", AC2_ROUTES)
def test_ac2_reinclude_config_lands_the_profile_node_and_its_edge(route, proj_new, monkeypatch):
    """The profile sits under a hidden dir: only the re-include's hidden-dir override lets it
    in, on every route (R1 + R2)."""
    proj, root = proj_new
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        _assert_edge_landed(s, proj, "project-profile#constraints", "finding#profile-cite",
                            PROFILE_LINE)
        _assert_rest_of_dot_claude_stays_out(s, proj)
    finally:
        s.close()


@pytest.mark.parametrize("route", AC2_ROUTES)
def test_ac2_old_config_has_no_rule_doc_nodes(route, proj_old, monkeypatch):
    """With the 2026-09-04 config neither rule doc reaches the store on ANY route, and the
    citing lines land nothing. (At HEAD ingest-gmd's walk honours no ignore spec at all.)"""
    proj, root = proj_old
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        _assert_no_node(s, "claude#no-silent-failures", "finding#swallow")
        _assert_no_node(s, "project-profile#constraints", "finding#profile-cite")
    finally:
        s.close()


@pytest.mark.parametrize("route", ["op-ingest-gmd", "cli-ingest-gmd"])
def test_ac2_old_config_counts_both_lines_unresolved(route, proj_old, monkeypatch):
    """ingest-gmd's report names unresolved refs (`IngestStats.report`), so the AC's 'the line
    counted unresolved' is observable there. (The sync route discards the GMD stats; see the
    RED summary.)"""
    proj, root = proj_old
    res = _run(route, proj, root, monkeypatch)
    rep = str(res.get("report"))
    assert "claude#no-silent-failures" in rep, rep
    assert "project-profile#constraints" in rep, rep
    if route == "op-ingest-gmd":
        assert res["unresolved"] >= 2, res


# ---------------------------------------------------------------- R2: one predicate, every walker


@pytest.mark.parametrize("route", ROUTES)
def test_r2_every_walker_ingests_the_same_files_under_the_new_config(route, proj_new,
                                                                     monkeypatch):
    """One fixture tree, one spec, the SAME included set on every walk. The tree has a spec
    re-include under a hidden dir (the profile), a hidden-dir file the spec also ignores (the
    agent template), an anchored spec exclusion (templates) and a re-include that must lose to
    INGEST_IGNORE_DIRS (`!node_modules/n.md`)."""
    proj, root = proj_new
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        got = _ingested(s, proj)
    finally:
        s.close()
    assert got == EXPECTED_NEW, (
        f"{route}: missing {sorted(EXPECTED_NEW - got)}, extra {sorted(got - EXPECTED_NEW)}")


@pytest.mark.parametrize("route", ROUTES)
def test_r2_every_walker_ingests_the_same_files_under_the_old_config(route, proj_old,
                                                                     monkeypatch):
    proj, root = proj_old
    _run(route, proj, root, monkeypatch)
    s = _open(root)
    try:
        got = _ingested(s, proj)
    finally:
        s.close()
    assert got == EXPECTED_OLD, (
        f"{route}: missing {sorted(EXPECTED_OLD - got)}, extra {sorted(got - EXPECTED_OLD)}")


def test_r2_watch_is_relevant_agrees_with_should_ignore(proj_new):
    """The `rmx watch` (watch.py) handler's filter, file by file, against the one predicate."""
    from refmatrix.ingest import should_ignore
    from refmatrix.watch import is_relevant
    proj, _root = proj_new
    diff = [p.relative_to(proj).as_posix() for p in _all_files(proj)
            if is_relevant(p, proj) == should_ignore(p, proj)]
    assert diff == [], f"is_relevant disagrees with should_ignore on {diff}"
    assert is_relevant(proj / ".claude" / "PROJECT_PROFILE.md", proj) is True


# ---------------------------------------------------------------- AC-3


def _sync(proj: Path, root: Path, rels: list[str]) -> dict:
    from refmatrix.sync import sync_files
    s = _open(root)
    try:
        return sync_files(s, [str(proj / r) for r in rels], project_root=proj)
    finally:
        s.close()


def _bump(p: Path) -> None:
    t = time.time() + 10
    os.utime(p, (t, t))


def test_ac3_a_path_that_becomes_reincluded_is_picked_up_by_the_next_sync():
    """Ingest with the profile excluded, then add `!.claude/PROJECT_PROFILE.md`: the next sync
    that names the profile ingests it. Its citing doc re-syncs (touched) and the edge lands."""
    base, proj, root = _make_proj()
    try:
        _write_spec(proj, [".claude"])
        _sync(proj, root, [p.relative_to(proj).as_posix() for p in _all_files(proj)])
        s = _open(root)
        try:
            assert _eid(s, "concept", "project-profile#constraints") is None, "precondition"
        finally:
            s.close()
        _write_spec(proj, [".claude", "!.claude/PROJECT_PROFILE.md"])
        rep = _sync(proj, root, [".claude/PROJECT_PROFILE.md"])
        s = _open(root)
        try:
            assert _eid(s, "concept", "project-profile#constraints") is not None, (
                f"re-included profile not picked up by the next sync: {rep}")
        finally:
            s.close()
        _bump(proj / "docs" / "finding.md")
        _sync(proj, root, ["docs/finding.md"])
        s = _open(root)
        try:
            _assert_edge_landed(s, proj, "project-profile#constraints", "finding#profile-cite",
                                PROFILE_LINE)
            assert ".claude/agents/x.md" not in _ingested(s, proj)
        finally:
            s.close()
    finally:
        shutil.rmtree(base)


def test_ac3_a_path_that_becomes_ignored_is_purged_by_the_next_sync():
    """Existing behaviour, re-asserted over a re-included file: drop the re-include and the next
    sync naming the profile purges its doc and nodes, and the edge into it goes with them."""
    base, proj, root = _make_proj()
    try:
        _write_spec(proj, NEW_SPEC)
        _sync(proj, root, [p.relative_to(proj).as_posix() for p in _all_files(proj)])
        s = _open(root)
        try:
            _assert_edge_landed(s, proj, "project-profile#constraints", "finding#profile-cite",
                                PROFILE_LINE)
        finally:
            s.close()
        _write_spec(proj, [".claude"])
        rep = _sync(proj, root, [".claude/PROJECT_PROFILE.md"])
        assert rep["purged"] >= 1, rep
        s = _open(root)
        try:
            assert _eid(s, "concept", "project-profile#constraints") is None
            assert ".claude/PROJECT_PROFILE.md" not in _ingested(s, proj)
            src_id = _eid(s, "concept", "finding#profile-cite")
            lid = _lid(s, "contradicts")
            left = s._connect().execute(
                "SELECT count(*) FROM entity_links WHERE linkage_id=? AND concept_id=?",
                (lid, src_id)).fetchone()[0]
            assert left == 0, "an edge into the purged node survived"
        finally:
            s.close()
    finally:
        shutil.rmtree(base)


def test_ac3_purge_of_a_path_that_becomes_ignored_is_unchanged_for_a_plain_path():
    """The purge half of AC-3 on a path no re-include is involved in (CLAUDE.md is not under a
    hidden dir): ingested under the R4 config, then the old `CLAUDE.md` line comes back and the
    next sync naming it purges it. Existing behaviour — green at HEAD; it pins that R1 did not
    break the purge branch of `_sync_one`."""
    base, proj, root = _make_proj()
    try:
        _write_spec(proj, NEW_SPEC)
        _sync(proj, root, [p.relative_to(proj).as_posix() for p in _all_files(proj)])
        s = _open(root)
        try:
            assert _eid(s, "concept", "claude#no-silent-failures") is not None, "precondition"
        finally:
            s.close()
        _write_spec(proj, OLD_SPEC)
        rep = _sync(proj, root, ["CLAUDE.md"])
        assert rep["purged"] >= 1, rep
        s = _open(root)
        try:
            assert _eid(s, "concept", "claude#no-silent-failures") is None
            assert "CLAUDE.md" not in _ingested(s, proj)
        finally:
            s.close()
    finally:
        shutil.rmtree(base)


# ---------------------------------------------------------------- guard: the memory walk


def test_the_memory_walk_is_not_put_through_should_ignore():
    """`ingest-gmd --as-memory` walks a memdir that lives under `~/.claude/projects/…` — a hidden
    dir on every machine. R2 routes the DOC walk through `should_ignore`; the memory walk
    (`memory_layout.iter_memory_files`, ADR-0005 #one-walk) must not be, or every memory is
    dropped. Green at HEAD; a guard for the implementation."""
    from refmatrix.ingest_gmd import collect_gmd_files
    base = Path(tempfile.mkdtemp(prefix="b216m", dir="/tmp")).resolve()
    try:
        mem = base / ".claude" / "projects" / "p" / "memory"
        mem.mkdir(parents=True)
        (mem / "feedback_x.md").write_text(_mini("feedback_x"))
        files = collect_gmd_files([mem], as_memory=True, skipped=[])
        assert [p.name for p in files] == ["feedback_x.md"], files
    finally:
        shutil.rmtree(base)
