"""Task 26.1 AC-1: `refmatrix.memory_layout` is the ONE place the memory dir's layout lives.

ADR-0005 (`docs/adr/0005-memory-dir-layout.md`) fixes the folder table, the one walk, the one
"newest save-state" ordering and the `.memory-layout` marker. Before this module, three readers
each kept their own glob (`memory_index.collect` = `*.md` + `impressions/*.md`;
`ingest_gmd.collect_gmd_files` = `rglob`, dot-dirs included; `handoff` = top level only) and
two definitions of "newest" (recall-state by mtime, the index by `created` then mtime) --
ch-bsd plan-26 r1 #s2/#s3, r2 #s3, r3 #m2.

Real files in a `mkdtemp()` dir; nothing mocked. RED at HEAD: the module does not exist, so
each test fails on its own import (imported inside the test, never inside a `pytest.raises`).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


def _layout():
    from refmatrix import memory_layout
    return memory_layout


@pytest.fixture
def memdir():
    d = Path(tempfile.mkdtemp(prefix="rmx261-")) / "memory"
    d.mkdir()
    yield d
    import shutil
    shutil.rmtree(d.parent, ignore_errors=True)


def _md(p: Path, *, mid: str | None = None, mtype: str = "project",
        updated: str | None = None, created: str | None = None,
        mtime: float | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    mid = mid or p.stem
    meta = ["metadata:", "  node_type: memory", f"  type: {mtype}"]
    if created:
        meta.append(f"  created: {created}")
    if updated:
        meta.append(f"  updated: {updated}")
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {mid}\ntitle: \"{mid}\"\ntags: [x]\n" + "\n".join(meta)
                 + f"\n---\n\n# {mid} {{#root}}\n\nbody of {mid}\n", encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


# ---- the folder table ---------------------------------------------------------------------

def test_folders_maps_every_adr_0005_folder_to_its_type():
    ml = _layout()
    assert ml.FOLDERS == {
        "feedback": "feedback",
        "project": "project",
        "reference": "reference",
        "user": "user",
        "guardrail": "guardrail",
        "impressions": "impression",
        "savestates": "session/recall-state",
    }


@pytest.mark.parametrize("mtype,folder", [
    ("feedback", "feedback"), ("project", "project"), ("reference", "reference"),
    ("user", "user"), ("guardrail", "guardrail"), ("impression", "impressions"),
    ("session/recall-state", "savestates"),
])
def test_folder_for_type_inverts_the_table(mtype, folder):
    assert _layout().folder_for_type(mtype) == folder


def test_savestate_dir_is_the_savestates_collection(memdir):
    assert Path(_layout().savestate_dir(memdir)) == memdir / "savestates"


# ---- THE walk -----------------------------------------------------------------------------

def test_iter_memory_files_walks_type_folders_and_skips_dot_paths_and_non_memories(memdir):
    """ch-bsd r1 #s3: a `.organise-rollback-1/x.md` inside a memdir was ingested as a memory.
    A dot-dir is never a memory store; MEMORY.md / README.md / dotfiles are never memories."""
    ml = _layout()
    keep = [
        _md(memdir / "project_top.md"),
        _md(memdir / "feedback" / "feedback_a.md", mtype="feedback"),
        _md(memdir / "project" / "project_b.md"),
        _md(memdir / "reference" / "reference_c.md", mtype="reference"),
        _md(memdir / "impressions" / "imp_d.md", mtype="impression"),
        _md(memdir / "savestates" / "savestate_e.md", mtype="session/recall-state"),
    ]
    (memdir / "MEMORY.md").write_text("- [x](project_top.md) — idx\n", encoding="utf-8")
    (memdir / "README.md").write_text("# readme\n", encoding="utf-8")
    _md(memdir / ".draft.md")                                   # a dotfile
    _md(memdir / ".organise-rollback-1" / "x.md")               # a dot-dir (r1 #s3)
    _md(memdir / ".hidden" / "y.md")
    _md(memdir / "feedback" / ".cache" / "z.md")                # a nested dot-dir
    (memdir / ".memory_hooks.json").write_text("{}", encoding="utf-8")
    (memdir / ".memory-layout").write_text("{}", encoding="utf-8")
    (memdir / "notes.txt").write_text("not markdown", encoding="utf-8")
    (memdir / "feedback" / "side.json").write_text("{}", encoding="utf-8")

    got = sorted(str(Path(p).relative_to(memdir)) for p in ml.iter_memory_files(memdir))
    assert got == sorted(str(p.relative_to(memdir)) for p in keep)


def _skip_shapes(memdir: Path) -> dict:
    """ch-bsd 26.1 #s-3: three file shapes the walk dropped WITHOUT putting them on `skipped`.
    The symlink targets live OUTSIDE the memdir (the walk never follows a link out of it)."""
    outside = memdir.parent / "elsewhere"
    outside.mkdir()
    _md(outside / "project_far.md")
    keep = _md(memdir / "project_keep.md")
    linked = memdir / "linked"
    linked.symlink_to(outside, target_is_directory=True)        # a symlinked sub-folder
    dangling = memdir / "project_dangling.md"
    dangling.symlink_to(memdir.parent / "no-such-file.md")      # a dangling .md symlink
    gmd = memdir / "notes.gmd"                                  # HEAD's bridge ingested .gmd
    gmd.write_text('---\ngmd: "0.1"\nid: notes\ntitle: "notes"\ntags: [x]\n---\n\n'
                   "# notes {#root}\n\nbody\n", encoding="utf-8")
    hidden = _md(memdir / ".hidden" / "y.md")                   # already counted at HEAD
    return {"keep": keep, "linked": linked, "dangling": dangling, "gmd": gmd, "hidden": hidden}


def test_iter_memory_files_puts_every_dropped_shape_on_skipped(memdir):
    """CLAUDE.md #no-silent-failures: `skipped` receives every path the walk excluded. At HEAD
    a symlinked sub-folder, a dangling `.md` symlink and a `.gmd` file were dropped uncounted."""
    ml = _layout()
    f = _skip_shapes(memdir)
    skipped: list = []
    got = [Path(p) for p in ml.iter_memory_files(memdir, skipped=skipped)]
    assert got == [f["keep"]], got
    sk = [Path(p) for p in skipped]

    def named(target: Path) -> bool:
        # the path itself, or (for the symlinked folder) a path under it
        return any(p == target or target in p.parents for p in sk)

    missing = [k for k in ("linked", "dangling", "gmd", "hidden") if not named(f[k])]
    assert not missing, f"dropped without being put on `skipped`: {missing}; skipped={sk}"
    assert not any(p == f["keep"] for p in sk), sk


# ---- ONE "newest" save-state (r2 s3, r3 m2) -------------------------------------------------

T0 = 1_800_000_000.0     # a fixed epoch so mtimes are deterministic


def _order(memdir):
    return [Path(p).stem for p in _layout().iter_savestates(memdir)]


def test_iter_savestates_reads_the_folder_and_the_legacy_top_level_only(memdir):
    _md(memdir / "savestates" / "savestate_new.md", mtype="session/recall-state",
        updated="2026-11-09", mtime=T0 + 10)
    _md(memdir / "savestate_legacy.md", mtype="session/recall-state",
        updated="2026-11-08", mtime=T0)
    _md(memdir / "project_x.md", updated="2026-11-10", mtime=T0 + 99)        # not a save-state
    _md(memdir / "impressions" / "savestate_lookalike.md", mtype="impression",
        updated="2026-11-10", mtime=T0 + 99)                                 # wrong folder
    _md(memdir / ".organise-rollback-1" / "savestate_aside.md",
        mtype="session/recall-state", updated="2026-11-10", mtime=T0 + 99)  # a dot-dir
    assert _order(memdir) == ["savestate_new", "savestate_legacy"]


def test_a_later_updated_date_beats_a_newer_mtime(memdir):
    _md(memdir / "savestates" / "savestate_a.md", updated="2026-11-08", mtime=T0 + 100)
    _md(memdir / "savestates" / "savestate_b.md", updated="2026-11-09", mtime=T0)
    assert _order(memdir) == ["savestate_b", "savestate_a"]


def test_created_is_never_part_of_the_key(memdir):
    """r2 s3: a session created earlier but saved later must win."""
    _md(memdir / "savestates" / "savestate_early.md", created="2026-11-01",
        updated="2026-11-09", mtime=T0)
    _md(memdir / "savestates" / "savestate_late.md", created="2026-11-07",
        updated="2026-11-08", mtime=T0 + 100)
    assert _order(memdir) == ["savestate_early", "savestate_late"]


def test_same_date_both_with_time_of_day_mtime_still_decides(memdir):
    """ADR-0005 #newest, amended 2026-11-09 (ch-bsd 26.1 #s-2): on the same date mtime decides
    ALWAYS -- a time of day in `updated` is informational only. The earlier rule (both timed ->
    the datetimes decide) is what let three same-day save-states form a cycle."""
    _md(memdir / "savestates" / "savestate_ten.md",
        updated="2026-11-09T10:00:00-08:00", mtime=T0)
    _md(memdir / "savestates" / "savestate_nine.md",
        updated="2026-11-09T09:00:00-08:00", mtime=T0 + 100)
    assert _order(memdir) == ["savestate_nine", "savestate_ten"]


def _cycle_set(memdir: Path) -> dict:
    """The ch-bsd 26.1 #s-2 probe, verbatim, plus a name-tied fourth file.

    Under the old rule: A (12:00) beats C (10:00) by datetime, C beats B (date-only) by mtime,
    B beats A by mtime -- a cycle, so `sort_savestates(...)[0]` followed the input order.
    Under the one key `(date, mtime, name)`: D (mtime 3000, name 'd') > C (3000, 'c') > B (2000)
    > A (1000)."""
    s = memdir / "savestates"
    return {
        "a": _md(s / "savestate_a.md", updated="2026-11-09T12:00:00-08:00", mtime=1000.0),
        "b": _md(s / "savestate_b.md", updated="2026-11-09", mtime=2000.0),
        "c": _md(s / "savestate_c.md", updated="2026-11-09T10:00:00-08:00", mtime=3000.0),
        "d": _md(s / "savestate_d.md", updated="2026-11-09", mtime=3000.0),
    }


def test_three_same_day_save_states_order_the_same_for_every_input_permutation(memdir):
    """ch-bsd 26.1 #s-2: `newest` must not depend on scandir order. 26.3 routes
    `rmx recall-state` through this ordering; a cycle resumes the wrong session."""
    import itertools
    ml = _layout()
    files = _cycle_set(memdir)
    want = [files[k] for k in ("d", "c", "b", "a")]
    got = {}
    for perm in itertools.permutations(files.values()):
        got[tuple(p.stem for p in perm)] = [Path(p) for p in ml.sort_savestates(list(perm))]
    wrong = {k: [p.stem for p in v] for k, v in got.items() if v != want}
    assert not wrong, f"order depends on input order (want d,c,b,a): {wrong}"
    assert [Path(p) for p in ml.iter_savestates(memdir)] == want
    # the newest is the max mtime (name breaks the 3000/3000 tie)
    assert Path(ml.iter_savestates(memdir)[0]).stem == "savestate_d"


def test_same_date_same_mtime_the_file_name_breaks_the_tie(memdir):
    """ADR-0005 #newest step 3 (guard): a remaining tie is broken by file name, the same way
    for either input order -- even when one side carries a time of day."""
    ml = _layout()
    s = memdir / "savestates"
    x = _md(s / "savestate_x.md", updated="2026-11-09T08:00:00-08:00", mtime=T0)
    y = _md(s / "savestate_y.md", updated="2026-11-09", mtime=T0)
    assert [Path(p) for p in ml.sort_savestates([x, y])] == [y, x]
    assert [Path(p) for p in ml.sort_savestates([y, x])] == [y, x]


def test_no_updated_is_dated_by_the_mtimes_local_date(memdir):
    """ADR-0005 #newest step 1 (amended): with no `updated`, the key's date is the mtime's LOCAL
    date -- the same `(date, mtime, name)` key as every other file, so the order stays total.
    The old rule compared a no-`updated` file by raw mtime against a dated one and skipped the
    date step: N (no `updated`, mtime 2026-11-08 13:00 local) beat D (`updated` 2026-11-09,
    mtime 2026-11-08 12:00 local) on mtime alone."""
    from datetime import datetime
    m_d = datetime(2026, 11, 8, 12, 0).timestamp()
    m_n = datetime(2026, 11, 8, 13, 0).timestamp()
    _md(memdir / "savestates" / "savestate_dated.md", updated="2026-11-09", mtime=m_d)
    _md(memdir / "savestates" / "savestate_undated.md", mtime=m_n)
    assert _order(memdir) == ["savestate_dated", "savestate_undated"]


def test_same_date_one_side_date_only_mtime_decides_never_midnight(memdir):
    """r3 m2: old MCP stdio servers keep writing date-only `updated:` until respawned. Read as
    midnight, the 23:00 datetime would win; the rule is that mtime decides."""
    _md(memdir / "savestates" / "savestate_dateonly.md", updated="2026-11-09", mtime=T0 + 100)
    _md(memdir / "savestates" / "savestate_late_evening.md",
        updated="2026-11-09T23:00:00-08:00", mtime=T0)
    assert _order(memdir) == ["savestate_dateonly", "savestate_late_evening"]


def test_no_updated_falls_back_to_mtime(memdir):
    _md(memdir / "savestates" / "savestate_old.md", mtime=T0)
    _md(memdir / "savestate_newer.md", mtime=T0 + 50)
    assert _order(memdir) == ["savestate_newer", "savestate_old"]


# ---- the marker (ADR-0005 #marker-encoding, pinned 2026-11-09) ------------------------------

def _marker(memdir: Path, payload) -> Path:
    p = memdir / ".memory-layout"
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


def test_no_marker_is_not_organised(memdir):
    assert _layout().is_organised(memdir) is False


def test_a_layout_1_marker_is_organised_and_extra_keys_are_ignored(memdir):
    ml = _layout()
    _marker(memdir, {"layout": 1, "organised": "2026-11-09T10:00:00-08:00",
                     "backup": "/tmp/b.tar.gz"})
    assert ml.is_organised(memdir) is True
    _marker(memdir, {"layout": 1, "organised": "2026-11-09T10:00:00-08:00",
                     "backup": "/tmp/b.tar.gz", "later_field": [1, 2]})
    assert ml.is_organised(memdir) is True


@pytest.mark.parametrize("payload", [
    "{not json",
    "",
    {"layout": 2, "organised": "2026-11-09T10:00:00-08:00", "backup": "/tmp/b.tar.gz"},
    {"organised": "2026-11-09T10:00:00-08:00", "backup": "/tmp/b.tar.gz"},
    ["layout", 1],
])
def test_an_unreadable_or_foreign_marker_is_a_hard_error_naming_the_file(memdir, payload):
    """A silent "not organised" would re-enable the old renderer over an organised dir."""
    ml = _layout()
    _marker(memdir, payload)
    with pytest.raises(Exception) as ei:
        ml.is_organised(memdir)
    assert ".memory-layout" in str(ei.value), ei.value
