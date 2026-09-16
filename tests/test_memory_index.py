"""The memory index is generated and capped, not appended forever.

`MEMORY.md` is the flat index loaded into context at session start, and
`MEMORY-RULES.md` caps it at 200 lines "(after-200 lines truncate on context
load)". Nothing enforced that: `handoff._ss_update_index` appends one line per
memory and never collapses anything, so on 2026-09-16 the file stood at 234
lines / 34 KB and the tail — 34 entries — was silently cut from every session's
context. The memories were on disk and unreachable through the index that exists
to reach them.

These tests cover the generator: it keeps the curated hooks, collapses the
classes that are pointers rather than content, and holds the cap.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import memory_index as mi


def _mem(d: Path, name: str, *, title: str, mtype: str, body: str = "body") -> Path:
    p = d / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '---\ngmd: "0.1"\n'
        f"id: {name}\n"
        f'title: "{title}"\n'
        "tags: [x]\n"
        "metadata:\n  node_type: memory\n"
        f"  type: {mtype}\n"
        "  created: 2026-09-01\n"
        "---\n\n"
        f"# {title} {{#root}}\n\n{body}\n"
    )
    return p


@pytest.fixture
def memdir(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    return d


# ---- the curated hooks survive ------------------------------------------

def test_existing_hooks_are_preserved(memdir):
    """The one-line hooks are hand-written and are the whole value of the
    index. A generator that regenerated them from titles would quietly
    destroy the curation it is meant to protect."""
    _mem(memdir, "project_alpha", title="Alpha", mtype="project")
    (memdir / "MEMORY.md").write_text(
        "- [Alpha](project_alpha.md) — the hook a human wrote\n")

    out = mi.render(memdir)
    assert "— the hook a human wrote" in out
    assert out.count("project_alpha.md") == 1


def test_a_new_memory_without_a_hook_gets_one_from_its_title(memdir):
    _mem(memdir, "project_beta", title="Beta ships", mtype="project")
    out = mi.render(memdir)
    assert "](project_beta.md)" in out and "Beta ships" in out


def test_no_memory_file_is_dropped(memdir):
    for i in range(5):
        _mem(memdir, f"project_p{i}", title=f"P{i}", mtype="project")
    _mem(memdir, "feedback_f", title="F", mtype="feedback")
    _mem(memdir, "reference_r", title="R", mtype="reference")
    out = mi.render(memdir)
    for i in range(5):
        assert f"project_p{i}.md" in out
    assert "feedback_f.md" in out and "reference_r.md" in out


# ---- the collapses ------------------------------------------------------

def test_impressions_collapse_to_one_pointer(memdir):
    for i in range(12):
        _mem(memdir / "impressions", f"impression_i{i}", title=f"I{i}",
             mtype="impression")
    out = mi.render(memdir)
    lines = [l for l in out.splitlines() if "impressions/" in l]
    assert len(lines) == 1, lines
    assert "12" in lines[0], "the pointer must say how many it stands for"


def test_savestates_collapse_to_one_pointer_naming_the_newest(memdir):
    for day in ("2026-09-01", "2026-09-14", "2026-09-16"):
        _mem(memdir, f"savestate_{day.replace('-', '')}",
             title=f"Save-state {day}", mtype="session/recall-state")
    out = mi.render(memdir)
    lines = [l for l in out.splitlines() if "savestate_" in l]
    assert len(lines) == 1, lines
    assert "20260916" in lines[0], "the newest is the one worth naming"
    assert "3" in lines[0]


def test_a_long_hook_is_truncated_not_wrapped(memdir):
    _mem(memdir, "project_long", title="Long", mtype="project")
    (memdir / "MEMORY.md").write_text(
        "- [Long](project_long.md) — " + ("x" * 500) + "\n")
    out = mi.render(memdir)
    line = next(l for l in out.splitlines() if "project_long.md" in l)
    assert len(line) <= mi.MAX_LINE_CHARS
    assert line.endswith("…")


# ---- the cap ------------------------------------------------------------

def test_the_cap_holds_by_folding_the_oldest_projects(memdir):
    for i in range(400):
        _mem(memdir, f"project_p{i:03d}", title=f"P{i}", mtype="project")
    out = mi.render(memdir, max_lines=200)
    body = out.splitlines()
    assert len(body) <= 200, len(body)
    fold = [l for l in body if "older project memor" in l]
    assert len(fold) == 1, "one fold line, naming the count"
    folded = int("".join(c for c in fold[0] if c.isdigit())[:3])
    kept = len([l for l in body if l.startswith("- [") and "older project" not in l])
    assert folded + kept >= 400 - 5, (folded, kept)


def test_feedback_is_never_folded_away(memdir):
    """Feedback is how the user corrects behaviour; it outranks project notes
    when something has to go."""
    for i in range(300):
        _mem(memdir, f"project_p{i:03d}", title=f"P{i}", mtype="project")
    for i in range(20):
        _mem(memdir, f"feedback_f{i:02d}", title=f"F{i}", mtype="feedback")
    out = mi.render(memdir, max_lines=100)
    for i in range(20):
        assert f"feedback_f{i:02d}.md" in out, f"feedback_f{i:02d} was folded"


# ---- mechanics ----------------------------------------------------------

def test_render_is_idempotent(memdir):
    for i in range(30):
        _mem(memdir, f"project_p{i:02d}", title=f"P{i}", mtype="project")
    _mem(memdir / "impressions", "impression_a", title="A", mtype="impression")
    first = mi.render(memdir)
    (memdir / "MEMORY.md").write_text(first)
    assert mi.render(memdir) == first


def test_write_reports_what_changed_and_check_detects_drift(memdir, capsys):
    _mem(memdir, "project_a", title="A", mtype="project")
    assert mi.check(memdir) is False          # index missing => drifted
    n = mi.write(memdir)
    assert n > 0
    assert mi.check(memdir) is True
    out = capsys.readouterr().out
    assert "MEMORY.md" in out

    _mem(memdir, "project_b", title="B", mtype="project")
    assert mi.check(memdir) is False


def test_the_index_never_indexes_itself(memdir):
    _mem(memdir, "project_a", title="A", mtype="project")
    out = mi.render(memdir)
    assert "](MEMORY.md)" not in out


# ---- the wiring ---------------------------------------------------------

def test_save_state_compacts_the_index_it_just_appended_to(memdir, capsys):
    """The write that GROWS the index is the write that must cap it. A helper
    nobody calls would leave the index growing exactly as before."""
    from refmatrix import handoff

    for i in range(260):
        _mem(memdir, f"project_p{i:03d}", title=f"P{i}", mtype="project")
    memdir.joinpath("MEMORY.md").write_text(
        "\n".join(f"- [P{i}](project_p{i:03d}.md) — hook {i}" for i in range(260))
        + "\n")
    assert len(memdir.joinpath("MEMORY.md").read_text().splitlines()) == 260

    _mem(memdir, "savestate_20260916", title="Save-state", mtype="session/recall-state")
    handoff._ss_update_index(memdir, "savestate_20260916", "Save-state", "the newest")

    lines = memdir.joinpath("MEMORY.md").read_text().splitlines()
    assert len(lines) <= mi.MAX_LINES, len(lines)
    assert any("savestate_20260916" in l for l in lines), "the new entry survived"
    assert any("older project memories folded" in l for l in lines)
    assert "MEMORY.md" in capsys.readouterr().out, "the compaction must say so"


def test_compaction_failure_is_said_not_swallowed(memdir, monkeypatch, capsys):
    from refmatrix import handoff
    from refmatrix import memory_index as mi_mod

    _mem(memdir, "project_a", title="A", mtype="project")
    monkeypatch.setattr(mi_mod, "check",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk")))
    handoff._ss_update_index(memdir, "project_a", "A", "hook")
    assert "compaction failed" in capsys.readouterr().err


# ---- two defects the real index found that the fixtures did not ---------

def test_a_title_containing_an_em_dash_survives_a_round_trip(memdir):
    """Caught on the real index, not here: `partition(" — ")` split at the
    first em dash, which lives INSIDE the title, so half the title migrated
    into the hook and every re-render shifted it again."""
    _mem(memdir, "feedback_dash",
         title="Capture reasoning deliberately — thinking is redacted",
         mtype="feedback")
    (memdir / "MEMORY.md").write_text(
        "- [Capture reasoning deliberately — thinking is redacted]"
        "(feedback_dash.md) — record WHY at decision points\n")

    first = mi.render(memdir)
    assert "— record WHY at decision points" in first
    assert first.count("thinking is redacted") == 1, first
    (memdir / "MEMORY.md").write_text(first)
    assert mi.render(memdir) == first, "render is not idempotent on its own output"


def test_the_newest_savestate_is_by_date_not_by_name(memdir):
    """Save-state ids are session hashes, so sorting the NAMES picked an
    arbitrary one and labelled it newest — which it was on the real index."""
    import os

    for stem, created, age in (("savestate_fd45323ccbb8", "2026-07-01", 3000),
                               ("savestate_005c1cfc17f6", "2026-09-16", 0),
                               ("savestate_aaa1111bbbb2", "2026-08-01", 1500)):
        p = _mem(memdir, stem, title=f"Save-state {created}",
                 mtype="session/recall-state")
        os.utime(p, (p.stat().st_atime - age, p.stat().st_mtime - age))

    line = next(l for l in mi.render(memdir).splitlines() if "Save-states" in l)
    assert "savestate_005c1cfc17f6" in line, line


def test_an_empty_memdir_never_wipes_the_index(memdir, capsys):
    """The index is derived FROM the files, so a dir that reads empty — the
    wrong path, an unreadable mount, an index written before its files land —
    must leave it alone rather than render nothing over it."""
    idx = memdir / "MEMORY.md"
    idx.write_text("- [Old](savestate_x.md) — old hook\n- [Keep](other.md) — keep\n")
    assert mi.write(memdir) == 0
    assert idx.read_text().count("savestate_x.md") == 1
    assert "left untouched" in capsys.readouterr().out


def test_an_entry_whose_file_is_gone_is_dropped_and_counted(memdir, capsys):
    _mem(memdir, "project_here", title="Here", mtype="project")
    (memdir / "MEMORY.md").write_text(
        "- [Here](project_here.md) — kept\n- [Gone](project_gone.md) — deleted\n")
    mi.write(memdir)
    out = capsys.readouterr().out
    assert "dropped 1 entry" in out and "project_gone.md" in out
    assert "project_here.md" in (memdir / "MEMORY.md").read_text()
