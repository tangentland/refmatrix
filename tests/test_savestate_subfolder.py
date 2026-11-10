"""Task 26.3: save-states live in `savestates/` (ADR-0005 #folders, #legacy, #newest).

At HEAD 8a867bc `handoff` knows one place for a save-state, the memdir's top level:
`compose_save_state` writes `<memdir>/savestate_<slug>.md`, `_latest_savestate` globs
`savestate_*.md` there and takes the newest MTIME (ch-bsd plan-26 r1 #s2: cliquedb's newest
mtime was not its newest save), `_ss_recent_memories` globs top-level `*.md` (so a save-state is
listed as a "recent memory" and a memory in `feedback/` never is), and `_ss_update_index` links
`](<id>.md)`. ADR-0005 makes `savestates/` the home of a save-state in an ORGANISED dir (one
with `.memory-layout`), keeps the top level readable forever, and makes
`memory_layout.iter_savestates` the ONE "newest" ordering (`updated` date, then mtime; never
`created`; a date-only `updated` is never midnight).

Inherited from ch-bsd 26.1 r4 (spec #inherit-261-r4): 26.3 is the first task that MOVES memory
files, so it owns `load_hooks`' id fallback -- an index line whose path is gone (the file moved
into a type folder) must resolve the memory's DERIVED hook by id, or a HEAD cut of derived prose
is frozen into the sidecar as if it were curated (bug-195's shape, by a new door).

Real files under short `mkdtemp()` roots, the real `rmx save-state` / `rmx recall-state` CLI
through CliRunner, the real `rmx_save_state` / `rmx_recall_state` verbs through the verb
registry, a real spawned daemon + the real embed model for AC-6. Nothing in `handoff`,
`memory_layout` or `memory_index` is mocked; the only patch is `cli._root` (and `HOME` for the
lint tool's location), as tests/test_memory_bridge.py does.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import handoff, memory_index as mi, memory_layout, verbs
from refmatrix.stm import Stm
from refmatrix.store import Store

_REPO = Path(__file__).resolve().parent.parent
RECALL_SOURCE = "newest save-state (`savestates/`, legacy top-level)"


# ---- builders -------------------------------------------------------------------------------

@pytest.fixture
def base():
    d = Path(tempfile.mkdtemp(prefix="rmx263-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memdir(base):
    d = base / "memory"
    d.mkdir()
    return d


def organise(memdir: Path) -> None:
    """The ADR-0005 #marker-encoding marker, as 26.5's writer will lay it down."""
    (memdir / ".memory-layout").write_text(json.dumps(
        {"layout": 1, "organised": "2026-11-09T10:00:00-08:00",
         "backup": str(memdir.parent / "backup.tar.gz")}), encoding="utf-8")


def at(y: int, mo: int, d: int, h: int = 12, mi_: int = 0) -> float:
    """A local wall-clock time as an epoch (what an mtime is)."""
    return time.mktime((y, mo, d, h, mi_, 0, 0, 0, -1))


def ss(memdir: Path, rel: str, *, created: str = "2026-11-01", updated: "str | None" = None,
       mtime: "float | None" = None, body: str = "handoff body") -> Path:
    """A save-state file in the shape `_ss_render` writes."""
    p = memdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = ("metadata:\n  node_type: memory\n  type: session/recall-state\n"
            f"  originSessionId: s-{p.stem}\n  created: {created}\n")
    if updated:
        meta += f"  updated: {updated}\n"
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {p.stem}\n"
                 f'title: "Save-state {p.stem}"\n'
                 f'tags: ["session:s-{p.stem}"]\n' + meta + "---\n\n"
                 f"# Save-state {p.stem} {{#root}}\n\n{body} of {p.stem}\n", encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def note(memdir: Path, rel: str, *, mtype: str, mtime: float) -> Path:
    p = memdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {p.stem}\n"
                 f'title: "Title of {p.stem}"\n'
                 f"tags: [{mtype}]\n"
                 f"metadata:\n  node_type: memory\n  type: {mtype}\n  created: 2026-11-01\n"
                 "---\n\n"
                 f"# Title of {p.stem} {{#root}}\n\nprose of {p.stem}\n", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def fm(path: Path, key: str) -> str:
    m = re.search(rf"^\s+{key}:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.M)
    assert m, f"no metadata.{key} in {path}"
    return m.group(1)


def latest(memdir: Path) -> "str | None":
    r = handoff._latest_savestate(memdir)
    return r["id"] if r else None


def stm(base: Path, session: str) -> tuple:
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir(parents=True, exist_ok=True)
    s = Stm(root, session)
    s.record("input", "hand off the 26.3 work")
    return s, root


def compose(base: Path, memdir: Path, session: str = "sess-263", *, today: str = "2026-11-09",
            dry_run: bool = False) -> dict:
    s, root = stm(base, session)
    return handoff.compose_save_state(s, root, repo=root.parent, memdir=memdir, today=today,
                                      message="hand off 26.3", promote=False, dry_run=dry_run)


def store_root() -> Path:
    """The per-test sandbox store the autouse conftest fixture names in `REFMATRIX_ROOT`."""
    return Path(os.environ["REFMATRIX_ROOT"])


def save_verb(memdir: Path, session: str, **extra) -> dict:
    args = {"session": session, "memory_dir": str(memdir), "promote": False,
            "lint": False, "sync": False}
    args.update(extra)
    return verbs.VERBS["rmx_save_state"].run(store_root(), args)


def save_cli(memdir: Path, session: str) -> None:
    r = CliRunner().invoke(cli_mod.main, ["save-state", "-s", session, "--memory-dir",
                                          str(memdir), "--no-lint", "--no-promote", "--no-sync"])
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"


def md_files(memdir: Path) -> list:
    """Every `.md` under the memdir except the index, relative and sorted."""
    return sorted(str(p.relative_to(memdir)) for p in memdir.rglob("*.md")
                  if p.name != "MEMORY.md")


SLUG = "sess263"            # `compose_save_state`'s slug of "sess-263"
MEM_ID = f"savestate_{SLUG}"


# ---- AC-1: the writer, organised dirs only ---------------------------------------------------

def test_ac1_compose_writes_savestates_in_an_organised_dir_creating_the_folder(base, memdir):
    organise(memdir)
    assert not (memdir / "savestates").exists()
    res = compose(base, memdir)
    want = memdir / "savestates" / f"{MEM_ID}.md"
    assert res["target"] == str(want), res["target"]
    assert want.is_file(), md_files(memdir)
    assert not (memdir / f"{MEM_ID}.md").exists(), "an organised save wrote the top level"


def test_ac1_compose_writes_the_top_level_in_an_unorganised_dir_as_at_head(base, memdir):
    res = compose(base, memdir)
    want = memdir / f"{MEM_ID}.md"
    assert res["target"] == str(want)
    assert want.is_file()
    assert not (memdir / "savestates").exists(), "an un-organised dir grew savestates/"


def test_ac1_dry_run_in_an_organised_dir_names_the_new_path_and_writes_nothing(base, memdir):
    organise(memdir)
    ss(memdir, f"{MEM_ID}.md", created="2026-11-02", mtime=at(2026, 11, 2))
    before = md_files(memdir)
    res = compose(base, memdir, dry_run=True)
    assert res["target"] == str(memdir / "savestates" / f"{MEM_ID}.md"), res["target"]
    assert md_files(memdir) == before, "a dry run moved or wrote a file"


@pytest.mark.parametrize("organised", [True, False], ids=["organised", "unorganised"])
def test_ac1_the_mcp_verb_writes_where_the_layout_says(memdir, organised):
    if organised:
        organise(memdir)
    res = save_verb(memdir, "sess-mcp")
    rel = "savestates/savestate_sessmcp.md" if organised else "savestate_sessmcp.md"
    # the verb resolves `memory_dir` (`/var` -> `/private/var` on macOS)
    assert res["target"] == str(memdir.resolve() / rel), res["target"]
    assert md_files(memdir) == [rel], md_files(memdir)


@pytest.mark.parametrize("organised", [True, False], ids=["organised", "unorganised"])
def test_ac1_the_cli_writes_where_the_layout_says(memdir, organised):
    if organised:
        organise(memdir)
    save_cli(memdir, "sess-cli")
    rel = "savestates/savestate_sesscli.md" if organised else "savestate_sesscli.md"
    assert md_files(memdir) == [rel], md_files(memdir)


def test_ac1_updated_is_a_datetime_with_time_of_day_and_created_stays_a_date(memdir):
    """r2 s3: a date-only `updated:` cannot order two saves of one day, so `newest` picked the
    session STARTED last. Going forward `updated:` carries the time of day; `created:` is a
    frozen date. Through the verb, so the date is the real clock's on both."""
    res = save_verb(memdir, "sess-clock")
    p = Path(res["target"])
    upd, cre = fm(p, "updated"), fm(p, "created")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:?\d{2}|Z)?", upd), upd
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cre), cre
    assert upd[:10] == cre, (upd, cre)


# ---- AC-2: the frozen `created:` survives the move -------------------------------------------

def test_ac2_a_legacy_file_is_moved_into_savestates_and_its_created_survives(base, memdir):
    organise(memdir)
    ss(memdir, f"{MEM_ID}.md", created="2026-10-30", updated="2026-10-31",
       mtime=at(2026, 10, 31))
    res = compose(base, memdir)
    new = memdir / "savestates" / f"{MEM_ID}.md"
    assert res["target"] == str(new), res["target"]
    assert not (memdir / f"{MEM_ID}.md").exists(), \
        "the legacy file was left behind -- 26.2's duplicate-id refusal fires on it"
    assert fm(new, "created") == "2026-10-30", "the frozen created: did not survive the move"
    assert "hand off 26.3" in new.read_text(encoding="utf-8"), "the save did not overwrite it"
    same_id = [p for p in memory_layout.iter_memory_files(memdir) if p.stem == MEM_ID]
    assert same_id == [new], same_id


def test_ac2_a_resave_in_savestates_keeps_its_created(base, memdir):
    organise(memdir)
    ss(memdir, f"savestates/{MEM_ID}.md", created="2026-11-01", updated="2026-11-08",
       mtime=at(2026, 11, 8))
    compose(base, memdir)
    p = memdir / "savestates" / f"{MEM_ID}.md"
    assert "hand off 26.3" in p.read_text(encoding="utf-8"), "the re-save did not reach it"
    assert fm(p, "created") == "2026-11-01"
    assert md_files(memdir) == [f"savestates/{MEM_ID}.md"], md_files(memdir)


def test_ac2_an_unorganised_dir_overwrites_the_legacy_file_in_place(base, memdir):
    ss(memdir, f"{MEM_ID}.md", created="2026-10-30", mtime=at(2026, 10, 31))
    compose(base, memdir)
    p = memdir / f"{MEM_ID}.md"
    assert p.is_file() and fm(p, "created") == "2026-10-30"
    assert not (memdir / "savestates").exists()


# ---- AC-3: the reader, with legacy fallback, through the ONE ordering ------------------------

def test_ac3_only_new_files(memdir):
    organise(memdir)
    ss(memdir, "savestates/savestate_a.md", updated="2026-11-08", mtime=at(2026, 11, 8))
    ss(memdir, "savestates/savestate_b.md", updated="2026-11-09", mtime=at(2026, 11, 9))
    r = handoff._latest_savestate(memdir)
    assert r and r["id"] == "savestate_b", r
    assert r["path"] == str(memdir / "savestates" / "savestate_b.md")
    assert "handoff body of savestate_b" in r["body"]


def test_ac3_only_legacy_files_still_resume(memdir):
    """Every other project today: a flat dir, no marker. It must keep resuming."""
    ss(memdir, "savestate_a.md", updated="2026-11-08", mtime=at(2026, 11, 8))
    ss(memdir, "savestate_b.md", updated="2026-11-09", mtime=at(2026, 11, 9))
    assert latest(memdir) == "savestate_b"


def test_ac3_mixed_the_newest_is_legacy(memdir):
    organise(memdir)
    ss(memdir, "savestates/savestate_n.md", updated="2026-11-07", mtime=at(2026, 11, 7))
    ss(memdir, "savestate_l.md", updated="2026-11-09", mtime=at(2026, 11, 9))
    assert latest(memdir) == "savestate_l"


def test_ac3_mixed_the_newest_is_new(memdir):
    organise(memdir)
    ss(memdir, "savestates/savestate_n.md", updated="2026-11-09", mtime=at(2026, 11, 9))
    ss(memdir, "savestate_l.md", updated="2026-11-07", mtime=at(2026, 11, 7))
    assert latest(memdir) == "savestate_n"


@pytest.mark.parametrize("new_rel", ["savestates/savestate_n.md", "savestate_n.md"],
                         ids=["mixed", "legacy-only"])
def test_ac3_cliquedb_shape_a_newer_mtime_with_an_older_updated_loses(memdir, new_rel):
    """ch-bsd r1 #s2: cliquedb's newest MTIME was a save-state touched by a later copy, not
    its newest save. The newer `updated:` wins."""
    ss(memdir, "savestate_l.md", updated="2026-11-07", mtime=at(2026, 11, 9, 20))
    ss(memdir, new_rel, updated="2026-11-08", mtime=at(2026, 11, 8, 9))
    assert latest(memdir) == "savestate_n"


@pytest.mark.parametrize("fmt", ["date-only", "datetime"])
@pytest.mark.parametrize("folder", ["savestates/", ""], ids=["new", "legacy"])
def test_ac3_same_day_two_sessions_the_session_saved_last_wins(memdir, fmt, folder):
    """r2 s3: A was created 11-07 and re-saved 11-08 at 23:00; B was created and saved 11-08 at
    15:00. A is the newest save. Mutation: `created` before mtime in the key turns this RED."""
    ua, ub = (("2026-11-08", "2026-11-08") if fmt == "date-only"
              else ("2026-11-08T23:00:00", "2026-11-08T15:00:00"))
    ss(memdir, f"{folder}savestate_a.md", created="2026-11-07", updated=ua,
       mtime=at(2026, 11, 8, 23))
    ss(memdir, f"{folder}savestate_b.md", created="2026-11-08", updated=ub,
       mtime=at(2026, 11, 8, 15))
    assert latest(memdir) == "savestate_a"


def test_ac3_mixed_formats_on_one_date_the_later_mtime_wins(memdir):
    """r3 m2: an old MCP server wrote `updated: 2026-11-08` (date-only); the other file has
    `2026-11-08T15:00:00`. Same date, so mtime decides. Mutation: date-only read as midnight
    turns this RED."""
    ss(memdir, "savestates/savestate_x.md", updated="2026-11-08", mtime=at(2026, 11, 8, 18))
    ss(memdir, "savestates/savestate_y.md", updated="2026-11-08T15:00:00",
       mtime=at(2026, 11, 8, 15))
    assert latest(memdir) == "savestate_x"


def test_ac3_recall_state_cli_and_mcp_return_the_same_newest_from_savestates(memdir):
    organise(memdir)
    ss(memdir, "savestate_l.md", updated="2026-11-07", mtime=at(2026, 11, 9, 20))
    ss(memdir, "savestates/savestate_n.md", updated="2026-11-08", mtime=at(2026, 11, 8, 9))
    mcp = verbs.VERBS["rmx_recall_state"].run(
        store_root(), {"session": "sess-rs", "memory_dir": str(memdir)})
    r = CliRunner().invoke(cli_mod.main, ["recall-state", "--json", "-s", "sess-rs",
                                          "--memory-dir", str(memdir)])
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    cli = json.loads(r.stdout)
    assert mcp["savestate"] and mcp["savestate"]["id"] == "savestate_n", mcp["savestate"]
    assert cli["savestate"] == mcp["savestate"], (cli["savestate"], mcp["savestate"])


# ---- AC-4: recents walk THE walk and never list a save-state or an impression ----------------

def test_ac4_recents_walk_every_folder_and_exclude_savestates_and_impressions(memdir):
    organise(memdir)
    note(memdir, "feedback/feedback_x.md", mtype="feedback", mtime=at(2026, 11, 9, 10))
    note(memdir, "project_top.md", mtype="project", mtime=at(2026, 11, 9, 9))
    note(memdir, "impressions/imp_z.md", mtype="impression", mtime=at(2026, 11, 9, 11))
    ss(memdir, "savestates/savestate_n.md", updated="2026-11-09", mtime=at(2026, 11, 9, 12))
    ss(memdir, "savestate_l.md", updated="2026-11-09", mtime=at(2026, 11, 9, 13))
    got = [mid for mid, _ in handoff._ss_recent_memories(memdir, exclude="")]
    assert got == ["feedback_x", "project_top"], got


def test_ac4_recall_state_recents_carry_no_savestate(base, memdir):
    ss(memdir, "savestate_l.md", updated="2026-11-09", mtime=at(2026, 11, 9, 13))
    note(memdir, "feedback/feedback_x.md", mtype="feedback", mtime=at(2026, 11, 9, 10))
    s, root = stm(base, "sess-rec")
    rep = handoff.compose_recall_state(s, root, repo=root.parent, memdir=memdir,
                                       pointer_anomalies=[])
    assert rep["savestate"]["id"] == "savestate_l"
    assert [mid for mid, _ in rep["recent_memories"]] == ["feedback_x"], rep["recent_memories"]


# ---- AC-5: the index link, and ONE definition of "newest" ------------------------------------

def test_ac5_update_index_links_savestates_and_replaces_the_legacy_line(memdir):
    """The needle, observed on its own: with no memory file on disk the compaction refuses
    (`memory_index.write` never renders an empty dir), so the line `_ss_update_index` wrote is
    what stays."""
    organise(memdir)
    idx = memdir / "MEMORY.md"
    idx.write_text("- [Old](savestate_x.md) — old hook\n- [Keep](other.md) — keep\n",
                   encoding="utf-8")
    handoff._ss_update_index(memdir, "savestate_x", "New Title", "new hook")
    body = idx.read_text(encoding="utf-8")
    assert body.count("](savestates/savestate_x.md)") == 1, body
    assert "](savestate_x.md)" not in body, body
    assert "old hook" not in body and "New Title" in body
    assert "](other.md) — keep" in body


def test_ac5_update_index_in_an_unorganised_dir_is_heads(memdir):
    idx = memdir / "MEMORY.md"
    idx.write_text("- [Old](savestate_x.md) — old hook\n", encoding="utf-8")
    handoff._ss_update_index(memdir, "savestate_x", "New Title", "new hook")
    body = idx.read_text(encoding="utf-8")
    assert body == "- [New Title](savestate_x.md) — new hook\n", body


def test_ac5_the_pointer_line_and_recall_state_name_the_same_newest(memdir):
    organise(memdir)
    ss(memdir, "savestate_l.md", created="2026-11-09", updated="2026-11-07",
       mtime=at(2026, 11, 9, 20))
    ss(memdir, "savestates/savestate_n.md", created="2026-11-01", updated="2026-11-08",
       mtime=at(2026, 11, 8, 9))
    mi.write(memdir, out=io.StringIO())
    ptr = [ln for ln in (memdir / "MEMORY.md").read_text(encoding="utf-8").splitlines()
           if ln.startswith("- [Save-states (")]
    assert ptr == ["- [Save-states (2), newest savestate_n](savestates/savestate_n.md) — "
                   "session handoffs; `rmx recall-state` reads the newest"], ptr
    assert latest(memdir) == "savestate_n"


def test_ac5_a_save_in_an_organised_dir_leaves_no_top_level_link(base, memdir):
    organise(memdir)
    ss(memdir, f"{MEM_ID}.md", created="2026-10-30", mtime=at(2026, 10, 31))
    note(memdir, "feedback/feedback_x.md", mtype="feedback", mtime=at(2026, 11, 1))
    (memdir / "MEMORY.md").write_text(
        f"- [Old]({MEM_ID}.md) — old\n- [Title of feedback_x](feedback/feedback_x.md) — fx\n",
        encoding="utf-8")
    compose(base, memdir)
    body = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert f"]({MEM_ID}.md)" not in body, body
    assert f"](savestates/{MEM_ID}.md)" in body, body


# ---- AC-6: lint at the new path; the bridge ingests it; a recall finds it --------------------

@pytest.fixture
def live(monkeypatch, base):
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield root
    dm.stop_daemon(root)


@pytest.mark.timeout(900)
def test_ac6_save_state_lints_the_savestates_path_and_recall_finds_the_handoff(
        live, base, monkeypatch):
    from tests.test_save_state_embeds_memories import _read_snapshot
    root = live
    memdir = base / "memory"
    memdir.mkdir()
    organise(memdir)
    note(memdir, "feedback/feedback_x.md", mtype="feedback", mtime=at(2026, 11, 1))
    # `finalize_save_state` runs `~/claude_tools/gmd/lint.py`; the sandbox HOME has none, so a
    # throwaway HOME gets this checkout's copy (set AFTER the daemon spawned).
    home = base / "h"
    (home / "claude_tools" / "gmd").mkdir(parents=True)
    shutil.copy(_REPO / "tools" / "gmd" / "lint.py", home / "claude_tools" / "gmd" / "lint.py")
    monkeypatch.setenv("HOME", str(home))
    phrase = "quarried tamarind lighthouse cadastre"
    res = verbs.VERBS["rmx_save_state"].run(root, {
        "session": "sess-ac6", "memory_dir": str(memdir), "promote": False,
        "lint": True, "sync": True, "message": f"resume at the {phrase}"})
    want = memdir.resolve() / "savestates" / "savestate_sessac6.md"
    assert res["target"] == str(want), res["target"]
    assert res["lint"] and str(want) in res["lint"], f"lint did not run on {want}: {res['lint']}"
    # `_ss_sh` captures lint's stdout: its findings, one per line (the summary is stderr)
    assert not [ln for ln in res["lint"].splitlines() if ": error:" in ln], res["lint"]
    assert res["sync"]["error"] is None, res["sync"]
    assert res["embed"] and res["embed"]["error"] is None, res["embed"]
    part = verbs.memory_partition(root)
    r = dm.call(root, "memory_recall", {"query": phrase, "k": 5, "partition": part},
                timeout=300)
    assert r.get("ok"), r
    hits = (r.get("result") or {}).get("hits") or []
    assert hits, f"recall found nothing for a phrase unique to the handoff: {r}"
    name = _read_snapshot(root, part, "name", str(int(hits[0]["id"])))
    assert name == "savestate_sessac6", (name, hits)


# ---- AC-7: the command docs ------------------------------------------------------------------

@pytest.mark.parametrize("rel", ["src/refmatrix/templates/commands/recall-state.md",
                                 ".claude/commands/recall-state.md"])
def test_ac7_recall_state_docs_name_the_savestates_source(rel):
    text = (_REPO / rel).read_text(encoding="utf-8")
    assert RECALL_SOURCE in text, f"{rel} does not say {RECALL_SOURCE!r}"


def test_ac7_the_installed_command_is_the_template():
    a = (_REPO / "src/refmatrix/templates/commands/recall-state.md").read_bytes()
    b = (_REPO / ".claude/commands/recall-state.md").read_bytes()
    assert a == b


# ---- inherited from ch-bsd 26.1 r4: the id fallback for a MOVED file's derived hook ----------

DERIVED = ("derived prose " * 30).strip()


def _moved_dir(memdir: Path) -> tuple:
    """The r4 probe shape (scratchpad/edge_moved.py): organised, NO sidecar, the index line
    still at the flat path `feedback_a.md`, the file moved to `feedback/feedback_a.md`, and the
    line's hook a HEAD cut of the memory's derived prose."""
    (memdir / "feedback").mkdir()
    (memdir / "feedback" / "feedback_a.md").write_text(
        '---\ngmd: "0.1"\nid: feedback_a\ntitle: A\ntags: [feedback]\nmetadata:\n'
        "  type: feedback\n---\n\n# A {#root}\n\n" + DERIVED + "\n", encoding="utf-8")
    full = f"- [A](feedback_a.md) — {DERIVED}"
    cut = full[:mi.MAX_LINE_CHARS - 1].rstrip() + "…"
    (memdir / "MEMORY.md").write_text(cut + "\n", encoding="utf-8")
    organise(memdir)
    return cut


def test_r4_a_moved_files_derived_cut_is_never_frozen_into_the_sidecar(memdir):
    _moved_dir(memdir)
    fresh = memdir.parent / "fresh"
    shutil.copytree(memdir, fresh)
    (fresh / "MEMORY.md").unlink()
    mi.write(fresh, out=io.StringIO())
    derived_line = [ln for ln in (fresh / "MEMORY.md").read_text(encoding="utf-8").splitlines()
                    if "](feedback/feedback_a.md)" in ln]
    mi.write(memdir, out=io.StringIO())
    side = json.loads((memdir / mi.HOOKS_SIDECAR).read_text(encoding="utf-8"))
    frozen = {k: v for k, v in side.items() if v.endswith("…")}
    assert not frozen, f"a cut of derived prose was frozen as a curated hook: {frozen}"
    assert side.get("feedback_a") == DERIVED, side
    got = [ln for ln in (memdir / "MEMORY.md").read_text(encoding="utf-8").splitlines()
           if "](feedback/feedback_a.md)" in ln]
    assert got == derived_line and len(got) == 1, (got, derived_line)


def test_r4_load_hooks_resolves_a_moved_files_derived_hook_by_id(memdir):
    cut = _moved_dir(memdir)
    hooks = mi.load_hooks(memdir)
    assert cut.split(" — ", 1)[1] not in hooks.values(), hooks
    assert hooks.get("feedback_a") == DERIVED, hooks
    assert hooks.get("feedback_a.md") == DERIVED, hooks


# ---- RED-round decisions (spec #red-decisions, 995daa9) --------------------------------------
#
# #rd-one-newest: the MEMORY.md save-state pointer and the reader use ONE ordering
# (`memory_layout.sort_savestates`) in EVERY dir. At HEAD a flat dir's pointer ordered by
# (created, mtime) while the reader took the newest mtime: two answers to "newest". The flat
# pointer changing is a named exception to 26.1 AC-9's byte-identity.

def _pointer_newest(memdir: Path) -> str:
    ptr = [ln for ln in (memdir / "MEMORY.md").read_text(encoding="utf-8").splitlines()
           if ln.startswith("- [Save-states (")]
    assert len(ptr) == 1, ptr
    m = re.match(r"- \[Save-states \(\d+\), newest (\S+)\]\(([^)]+)\)", ptr[0])
    assert m, ptr
    return m.group(1), m.group(2)


@pytest.mark.parametrize("shape", ["created-vs-mtime", "mixed-format"])
def test_rd_one_newest_a_flat_dirs_pointer_names_the_readers_newest(memdir, shape):
    """A flat (no marker) cliquedb-shaped dir. `savestate_n` is the newest save by the ONE key;
    `savestate_l` has the later `created` (HEAD's pointer key) and, in the mixed-format shape,
    also the later mtime under an older date."""
    if shape == "created-vs-mtime":
        # HEAD's pointer -> l (later created); HEAD's reader -> n (later mtime): they disagree.
        ss(memdir, "savestate_l.md", created="2026-11-09", updated="2026-11-07",
           mtime=at(2026, 11, 7, 9))
        ss(memdir, "savestate_n.md", created="2026-11-01", updated="2026-11-08",
           mtime=at(2026, 11, 8, 9))
    else:
        # date-only vs datetime on one date: mtime decides -> n. HEAD's pointer -> l (created).
        ss(memdir, "savestate_l.md", created="2026-11-08", updated="2026-11-08T15:00:00",
           mtime=at(2026, 11, 8, 15))
        ss(memdir, "savestate_n.md", created="2026-11-07", updated="2026-11-08",
           mtime=at(2026, 11, 8, 23))
    note(memdir, "feedback_x.md", mtype="feedback", mtime=at(2026, 11, 1))
    assert not (memdir / ".memory-layout").exists()
    mi.write(memdir, out=io.StringIO())
    name, rel = _pointer_newest(memdir)
    assert name == latest(memdir), f"pointer names {name}, recall-state reads {latest(memdir)}"
    assert (name, rel) == ("savestate_n", "savestate_n.md"), (name, rel)


# #rd-duplicate: a crash mid-move leaves both `<id>.md` and `savestates/<id>.md`. The reader
# takes the `savestates/` copy; the next save of that id writes `savestates/`, removes the
# top-level copy and prints `removed duplicate top-level <name>`; until then the bridge counts
# and names the duplicate in its skip line.

DUP = "savestate_sessdup"


def _duplicate(memdir: Path) -> tuple:
    """Both copies; the TOP-LEVEL one is the later mtime (the copy a crash after the write and
    before the unlink would leave newer), so a reader that only sorts picks the wrong one."""
    new = ss(memdir, f"savestates/{DUP}.md", created="2026-11-01", updated="2026-11-08",
             mtime=at(2026, 11, 8, 9), body="the savestates copy")
    old = ss(memdir, f"{DUP}.md", created="2026-11-01", updated="2026-11-08",
             mtime=at(2026, 11, 8, 10), body="the stale top-level copy")
    return new, old


@pytest.mark.parametrize("organised", [True, False], ids=["organised", "unorganised"])
def test_rd_duplicate_the_reader_takes_the_savestates_copy(memdir, organised):
    if organised:
        organise(memdir)
    new, _old = _duplicate(memdir)
    r = handoff._latest_savestate(memdir)
    assert r and r["path"] == str(new), r
    assert "the savestates copy" in r["body"] and "stale top-level" not in r["body"], r["body"]


def test_rd_duplicate_the_next_save_writes_savestates_and_removes_the_top_level_copy(memdir):
    organise(memdir)
    new, old = _duplicate(memdir)
    r = CliRunner().invoke(cli_mod.main, ["save-state", "-s", "sess-dup", "--memory-dir",
                                          str(memdir), "--no-lint", "--no-promote", "--no-sync",
                                          "-m", "after the crash"])
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    assert not old.exists(), "the top-level duplicate survived the next save"
    assert "after the crash" in new.read_text(encoding="utf-8"), "the save did not reach savestates/"
    assert fm(new, "created") == "2026-11-01"
    assert md_files(memdir) == [f"savestates/{DUP}.md"], md_files(memdir)
    said = " ".join(r.output.split())
    assert f"removed duplicate top-level {DUP}" in said, r.output


@pytest.fixture
def inproc_store(monkeypatch, base):
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    return root


def test_rd_duplicate_the_bridge_counts_and_names_the_duplicate_before_the_save(
        inproc_store, base):
    root = inproc_store
    memdir = base / "memory"
    memdir.mkdir()
    organise(memdir)
    _duplicate(memdir)
    note(memdir, "feedback/feedback_x.md", mtype="feedback", mtime=at(2026, 11, 1))
    assert not dm.ping(root, retries=0), "the in-process leg must run with NO daemon"
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert out.get("skipped") == 1, f"the duplicate is not counted as a skip: {out}"
    named = " ".join(str(p) for p in (out.get("skipped_paths") or []))
    # named by absolute path (either spelling of a macOS tmp dir) or by memdir-relative path
    spellings = (str(memdir / f"{DUP}.md"), str(memdir.resolve() / f"{DUP}.md"))
    assert any(x in named for x in spellings) or f" {DUP}.md" in f" {named}", out
    assert "savestates/" not in named, f"the savestates/ copy was skipped instead: {named}"
    report = " ".join(str(out.get("report") or "").split())
    assert re.search(r"skipped 1\b", report) and f"{DUP}.md" in report, report
    s = Store(root)
    try:
        row = s.find_memory_any_partition(DUP)
    finally:
        s.close()
    assert row and "the savestates copy" in (row.get("content") or ""), row
