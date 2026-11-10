"""Task 26.1 AC-3..AC-9: `memory_index` walks every folder, keys hooks by id, carries prose.

Measured before this task (ch-bsd plan-26 r1 #b4): `memory_index.write` turned a copy of
viascope's 157-line / 61-link `MEMORY.md` into 1 line, because `collect` globbed only `*.md` +
`impressions/*.md` and `render` emits only entry and pointer lines. Non-entry lines regeneration
drops: viascope 62, cliquedb 29, viascope2 12, cliquet 8. Curated hooks are keyed by relative
path, so a moved file loses its hook.

ADR-0005 #marker: every NEW on-disk behaviour (carried prose, the content-line guard, the
id-keyed sidecar writer) runs only in a dir with `.memory-layout`. A dir without it keeps HEAD's
write byte-for-byte -- proven against golden files captured from HEAD's own code at RED time
(`tests/fixtures/plan26_memory_index_head/`, regenerated only by its `capture_head.py`, and only
on a checkout whose `memory_index.py` is HEAD 61b3bde's). The two un-gated changes are the
readers: `collect` walks with `memory_layout.iter_memory_files` (AC-3), and `load_hooks` reads
both sidecar key shapes (AC-4).

These tests live in their own file so AC-8 ("test_memory_index.py and
test_memory_index_char_budget.py pass UNCHANGED") stays checkable by `git diff --quiet`.

Real files in a `mkdtemp()` dir, the real `python -m refmatrix.memory_index` entry point where
the spec's Test Strategy asks for it. Nothing mocked.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix import memory_index as mi

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "plan26_memory_index_head"
CARRY_HEAD = "<!-- carried from the hand-written index; edit freely -->"
T0 = 1_800_000_000.0


# ---- builders (shared with fixtures/plan26_memory_index_head/capture_head.py) -------------

def mem(memdir: Path, rel: str, *, title: str, mtype: str | None, body: str,
        mid: str | None = None, created: str = "2026-09-01", mtime: float | None = None) -> Path:
    p = memdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    mid = mid or p.stem
    meta = "metadata:\n  node_type: memory\n"
    if mtype:
        meta += f"  type: {mtype}\n"
    meta += f"  created: {created}\n"
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {mid}\n"
                 f'title: "{title}"\n'
                 "tags: [x]\n" + meta + "---\n\n"
                 f"# {title} {{#root}}\n\n{body}\n", encoding="utf-8")
    os.utime(p, (mtime or T0, mtime or T0))
    return p


def build_flat_no_prose(memdir: Path) -> None:
    """AC-8: a flat dir (+ impressions/), curated hooks, a save-state, NO prose."""
    mem(memdir, "feedback_alpha.md", title="Alpha rule", mtype="feedback",
        body="derived alpha prose")
    mem(memdir, "reference_beta.md", title="Beta ref", mtype="reference",
        body="derived beta prose")
    mem(memdir, "project_gamma.md", title="Gamma — a dashed title", mtype="project",
        body="derived gamma prose", mtime=T0 + 1)
    mem(memdir, "project_delta.md", title="Delta", mtype="project",
        body="derived delta prose", mtime=T0 + 2)
    mem(memdir, "impressions/imp_one.md", title="Imp one", mtype="impression", body="imp")
    mem(memdir, "savestate_aaa111.md", title="Save aaa", mtype="session/recall-state",
        body="handoff", created="2026-11-01")
    (memdir / "MEMORY.md").write_text(
        "- [Alpha rule](feedback_alpha.md) — curated alpha hook\n"
        "- [Gamma — a dashed title](project_gamma.md) — curated gamma hook\n",
        encoding="utf-8")


def build_flat_one_prose(memdir: Path) -> None:
    """AC-9 (flat): one prose line, one entry, NO sidecar."""
    mem(memdir, "project_x.md", title="X", mtype="project", body="derived x prose")
    (memdir / "MEMORY.md").write_text(
        "# My hand-written memory index\n"
        "- [X](project_x.md) — curated x hook\n", encoding="utf-8")


VIA_ENTRIES = [
    ("feedback/feedback_f1.md", "F1", "feedback"),
    ("feedback/feedback_f2.md", "F2", "feedback"),
    ("feedback/feedback_f3.md", "F3", "feedback"),
    ("project/project_p1.md", "P1", "project"),
    ("project/project_p2.md", "P2", "project"),
    ("project/project_p3.md", "P3", "project"),
    ("impressions/imp_i1.md", "I1", "impression"),
    ("reference_top.md", "Top", "reference"),
]


def build_viascope_shape(memdir: Path) -> None:
    """viascope's layout in miniature: feedback/ 3, project/ 3, impressions/ 1, 1 top-level."""
    for i, (rel, title, mtype) in enumerate(VIA_ENTRIES):
        mem(memdir, rel, title=title, mtype=mtype, body=f"derived {title} prose",
            mtime=T0 + i)


# ---- helpers ------------------------------------------------------------------------------

@pytest.fixture
def memdir():
    d = Path(tempfile.mkdtemp(prefix="rmx261-")) / "memory"
    d.mkdir()
    yield d
    shutil.rmtree(d.parent, ignore_errors=True)


def organise(memdir: Path) -> None:
    """The ADR-0005 #marker-encoding marker, as 26.5's writer will lay it down."""
    (memdir / ".memory-layout").write_text(json.dumps(
        {"layout": 1, "organised": "2026-11-09T10:00:00-08:00",
         "backup": str(memdir.parent / "backup.tar.gz")}), encoding="utf-8")


def run_entry(memdir: Path, *extra: str, env: dict | None = None):
    """The real entry point: `python -m refmatrix.memory_index <memdir>`."""
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "refmatrix.memory_index", str(memdir), *extra],
                          capture_output=True, text=True, env=e, timeout=60)


def sidecar(memdir: Path) -> dict:
    return json.loads((memdir / mi.HOOKS_SIDECAR).read_text(encoding="utf-8"))


def entry_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln.startswith("- [") and "](" in ln]


def golden(case: str, name: str) -> bytes:
    p = GOLDEN / case / f"{name}.golden"
    assert p.exists(), f"golden {p} missing -- capture it from HEAD with capture_head.py"
    return p.read_bytes()


# ---- AC-3: collect walks every folder, ungated ---------------------------------------------

def test_ac3_collect_sees_type_folders_in_an_unorganised_dir(memdir):
    """r1 #m1: assert on `collect()`, not on rendered lines -- `render` collapses impressions
    into one pointer line. HEAD's glob sees 2 (the top-level file + the impression)."""
    build_viascope_shape(memdir)
    assert not (memdir / ".memory-layout").exists()
    got = sorted(e.rel for e in mi.collect(memdir))
    assert got == sorted(rel for rel, _, _ in VIA_ENTRIES), got


def test_ac3_collect_skips_dot_dirs_and_the_marker(memdir):
    build_viascope_shape(memdir)
    organise(memdir)
    mem(memdir, ".organise-rollback-1/project_p1.md", title="aside", mtype="project", body="x")
    rels = [e.rel for e in mi.collect(memdir)]
    assert len(rels) == 8 and not any(r.startswith(".") for r in rels), rels


# ---- AC-4: curated hooks keyed by memory id ------------------------------------------------

def test_ac4_a_moved_file_keeps_its_curated_hook_in_an_organised_dir(memdir):
    """The spec's test: index-only dir (no sidecar), curated hook on `project_x.md`, the file
    moves to `project/project_x.md`, regenerate through the real entry point. At HEAD the hook
    is keyed by the old path and falls back to `_first_prose` (and HEAD does not even see
    `project/`)."""
    mem(memdir, "project_x.md", title="X", mtype="project", body="derived x prose")
    mem(memdir, "feedback_keep.md", title="Keep", mtype="feedback", body="derived keep prose")
    (memdir / "MEMORY.md").write_text(
        "- [Keep](feedback_keep.md) — curated keep hook\n"
        "- [X](project_x.md) — the curated x hook, verbatim\n", encoding="utf-8")
    organise(memdir)
    (memdir / "project").mkdir()
    (memdir / "project_x.md").rename(memdir / "project" / "project_x.md")

    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert "- [X](project/project_x.md) — the curated x hook, verbatim" in text, text
    assert "derived x prose" not in text
    assert sidecar(memdir)["project_x"] == "the curated x hook, verbatim"


def test_ac4_an_organised_write_converts_a_legacy_path_keyed_sidecar_to_ids(memdir):
    mem(memdir, "project/project_x.md", title="X", mtype="project", body="derived x prose")
    mem(memdir, "feedback/feedback_y.md", title="Y", mtype="feedback", body="derived y prose")
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps(
        {"project_x.md": "sidecar x hook", "feedback_y.md": "sidecar y hook"}), encoding="utf-8")
    organise(memdir)
    mi.write(memdir, out=io.StringIO())
    assert sidecar(memdir) == {"project_x": "sidecar x hook", "feedback_y": "sidecar y hook"}
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert "- [X](project/project_x.md) — sidecar x hook" in text, text
    assert "- [Y](feedback/feedback_y.md) — sidecar y hook" in text, text


def test_ac4_a_dead_link_hook_is_kept_under_its_path_and_reported(memdir):
    """B4: "Links that are already dead are kept under their path and reported" -- a curated
    hook is never silently discarded because its file is gone right now."""
    for n in ("a", "b", "c"):      # top level, so HEAD's glob sees them and HEAD's write runs
        mem(memdir, f"feedback_{n}.md", title=n.upper(), mtype="feedback", body=f"derived {n}")
    (memdir / "MEMORY.md").write_text(
        "- [A](feedback_a.md) — hook a\n"
        "- [B](feedback_b.md) — hook b\n"
        "- [C](feedback_c.md) — hook c\n"
        "- [Gone](project_gone.md) — the dead link's hook\n", encoding="utf-8")
    organise(memdir)
    buf = io.StringIO()
    mi.write(memdir, out=buf)
    assert sidecar(memdir).get("project_gone.md") == "the dead link's hook", sidecar(memdir)
    assert "project_gone.md" in buf.getvalue(), buf.getvalue()


def test_ac4_the_reader_takes_an_id_keyed_sidecar_in_an_unorganised_dir(memdir):
    """Readers are dual in EVERY dir (ADR-0005 #marker): an id-keyed sidecar left by an
    organised write (or a rollback) is read, not ignored."""
    mem(memdir, "project_x.md", title="X", mtype="project", body="derived x prose")
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({"project_x": "id-keyed hook"}),
                                           encoding="utf-8")
    assert not (memdir / ".memory-layout").exists()
    [e] = mi.collect(memdir)
    assert e.hook == "id-keyed hook"


def test_ac4_the_reader_still_takes_a_path_keyed_sidecar(memdir):
    """Regression guard (GREEN at HEAD): the legacy shape stays readable forever (#legacy)."""
    mem(memdir, "project_x.md", title="X", mtype="project", body="derived x prose")
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({"project_x.md": "path-keyed hook"}),
                                           encoding="utf-8")
    [e] = mi.collect(memdir)
    assert e.hook == "path-keyed hook"


# ---- AC-5: hand-written prose is carried, never dropped ------------------------------------

VIA_INDEX_PROSE_FIRST = [
    "# Viascope — project memory index",
    "Curated by hand. Read the Active Campaign block first.",
    "## Active Campaign",
    "**Goal:** ship the 3.2 ingest rework before the demo.",
    "**Blocked on:** the camera vendor's firmware drop.",
]
VIA_INDEX = (
    VIA_INDEX_PROSE_FIRST
    + ["## Feedback",
       "- [F1](feedback/feedback_f1.md) — curated f1",
       "- [F2](feedback/feedback_f2.md) — curated f2",
       "### Testing",
       "- [F3](feedback/feedback_f3.md) — curated f3",
       "## Project",
       "### Ingest",
       "- [P1](project/project_p1.md) — curated p1",
       "### Cameras",
       "- [P2](project/project_p2.md) — curated p2",
       "### Dashboards",
       "- [P3](project/project_p3.md) — curated p3",
       "## Reference",
       "- [Top](reference_top.md) — curated top",
       "## Impressions",
       "- [I1](impressions/imp_i1.md) — curated i1",
       "## Conventions",
       "### Naming",
       "Folders are singular; ids equal stems.",
       "### Branching",
       "## Open questions",
       "### Q1",
       "Should the dashboards memory move to reference?",
       "## Session log",
       "- 2026-10-01: organised the feedback notes by hand",
       "- 2026-10-03: added the camera project note",
       "- 2026-10-09 — reviewed the ingest notes with the user",
       "## Archive"]
)


def prose_of(lines: list) -> list:
    return [ln for ln in lines if ln.strip() and not (ln.startswith("- [") and "](" in ln)]


def test_ac5_the_viascope_shape_fixture_is_what_the_spec_names():
    headers = [ln for ln in VIA_INDEX if ln.startswith("#")]
    assert len(headers) == 17, len(headers)
    assert any(ln == "## Session log" for ln in VIA_INDEX)


def test_ac5_every_prose_line_is_carried_verbatim_in_order_before_the_entries(memdir):
    build_viascope_shape(memdir)
    (memdir / "MEMORY.md").write_text("\n".join(VIA_INDEX) + "\n", encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    lines = (memdir / "MEMORY.md").read_text(encoding="utf-8").splitlines()

    assert lines.count(CARRY_HEAD) == 1, lines
    start = lines.index(CARRY_HEAD)
    first_entry = next(i for i, ln in enumerate(lines) if ln.startswith("- ["))
    assert start < first_entry, "the carried block is not placed before the generated entries"
    want = prose_of(VIA_INDEX)
    got = [ln for ln in lines[start + 1:first_entry] if ln.strip()]
    # every prose line, verbatim, in its original order, inside the block
    it = iter(got)
    missing = [p for p in want if not any(p == g for g in it)]
    assert not missing, f"prose dropped or reordered: {missing}"
    for p in want:
        assert lines.count(p) == 1, f"prose line duplicated or lost: {p!r}"
    # entries still rendered with their curated hooks
    assert "- [F3](feedback/feedback_f3.md) — curated f3" in lines


def test_ac5_re_rendering_a_carried_block_carries_it_once(memdir):
    build_viascope_shape(memdir)
    (memdir / "MEMORY.md").write_text("\n".join(VIA_INDEX) + "\n", encoding="utf-8")
    organise(memdir)
    assert run_entry(memdir).returncode == 0
    first = (memdir / "MEMORY.md").read_bytes()
    assert CARRY_HEAD.encode() in first
    assert run_entry(memdir).returncode == 0
    assert (memdir / "MEMORY.md").read_bytes() == first, "a second write changed the index"
    chk = run_entry(memdir, "--check")
    assert chk.returncode == 0, chk.stdout + chk.stderr


def test_ac5_prose_that_leaves_under_a_quarter_of_the_budget_refuses_the_write(memdir):
    """Prose counts against MAX_INDEX_CHARS. When it alone leaves < 25% of the budget for
    entries, the write refuses (index untouched, return 0) and names the prose line count."""
    build_viascope_shape(memdir)
    prose = [f"Hand-written paragraph {i}: " + "x" * 140 for i in range(10)]   # ~1,700 chars
    before = "\n".join(prose + ["- [F1](feedback/feedback_f1.md) — curated f1"]) + "\n"
    (memdir / "MEMORY.md").write_text(before, encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir, env={"RMX_MEMORY_INDEX_CHARS": "2000"})
    assert r.returncode == 0, r.stderr
    assert (memdir / "MEMORY.md").read_text(encoding="utf-8") == before, "the index was rewritten"
    said = r.stdout + r.stderr
    assert "prose" in said and re.search(r"\b10\b", said), said
    assert "untouched" in said, said


# ---- AC-6: the shrink guard counts CONTENT lines; organised dirs only ----------------------

def test_ac6_the_guard_refuses_when_under_half_the_content_would_remain(memdir):
    """A partial view of the dir (files the index lists are not visible) must never render:
    10 entries + 1 prose line before, 3 entries + the carried prose after = 4/11 < 50%."""
    # Top-level files: at HEAD `collect` must SEE the 3 survivors, or HEAD's empty-dir refusal
    # ("no memory files found") would leave the index untouched for the wrong reason.
    lines = ["# hand index"]
    for i in range(10):
        lines.append(f"- [N{i}](feedback_n{i}.md) — curated n{i}")
        if i < 3:
            mem(memdir, f"feedback_n{i}.md", title=f"N{i}", mtype="feedback", body=f"n{i}")
    before = "\n".join(lines) + "\n"
    (memdir / "MEMORY.md").write_text(before, encoding="utf-8")
    organise(memdir)
    buf = io.StringIO()
    n = mi.write(memdir, out=buf)
    assert n == 0, buf.getvalue()
    assert (memdir / "MEMORY.md").read_text(encoding="utf-8") == before
    assert "untouched" in buf.getvalue(), buf.getvalue()


def test_ac6_a_fold_is_not_a_loss_content_counting_lets_it_through(memdir):
    """Folded entries are NAMED by the render (the fold line counts them): content counting
    sees 30 + 3 prose of 33 remain. Links-only counting would see ~11 of 30 link lines and
    refuse -- the "count links only" mutation turns this test RED."""
    hook = "a curated hook long enough that thirty of them overflow a small budget " * 2
    lines = ["# Hand index", "Kept by hand.", "## Projects"]
    for i in range(30):
        # top level, so HEAD's glob sees them: HEAD writes (and folds) and fails on the prose
        mem(memdir, f"project_q{i:02d}.md", title=f"Q{i:02d}", mtype="project",
            body=f"q{i}", mtime=T0 + i)
        lines.append(f"- [Q{i:02d}](project_q{i:02d}.md) — {hook[:150]}")
    (memdir / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    organise(memdir)
    buf = io.StringIO()
    n = mi.write(memdir, max_chars=2000, out=buf)
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert n > 0, buf.getvalue()
    assert "older project memories folded" in text, text
    assert len(entry_lines(text)) < 15, "the fixture no longer forces a >50% link fold"
    assert len(text) <= 2000, len(text)
    for p in ("# Hand index", "Kept by hand.", "## Projects"):
        assert p in text.splitlines(), f"prose lost: {p!r}"


def test_ac6_no_guard_in_an_unorganised_dir(memdir):
    """r3 m4: without the marker, HEAD's write runs unguarded (the same partial-view input
    that the organised guard refuses is written, as at HEAD)."""
    lines = []
    for i in range(10):
        lines.append(f"- [N{i}](feedback_n{i}.md) — curated n{i}")
        if i < 3:
            mem(memdir, f"feedback_n{i}.md", title=f"N{i}", mtype="feedback", body=f"n{i}")
    (memdir / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    n = mi.write(memdir, out=io.StringIO())
    assert n == 3
    assert len(entry_lines((memdir / "MEMORY.md").read_text(encoding="utf-8"))) == 3


# ---- AC-7: Entry.kind reads the folder first ----------------------------------------------

@pytest.mark.parametrize("rel,fm_type,kind", [
    ("feedback/note_a.md", "project", "feedback"),
    ("reference/note_b.md", "project", "reference"),
    ("project/note_c.md", "feedback", "project"),
    ("savestates/session_d.md", "project", "savestate"),
    ("impressions/note_e.md", "feedback", "impression"),
])
def test_ac7_kind_reads_the_folder_first(memdir, rel, fm_type, kind):
    p = mem(memdir, rel, title="t", mtype=fm_type, body="b")
    assert mi.Entry(p, memdir, {}).kind == kind


@pytest.mark.parametrize("stem,kind", [
    ("feedback_x", "feedback"), ("reference_y", "reference"), ("project_z", "project"),
    ("savestate_abc", "savestate"),
])
def test_ac7_the_stem_is_the_fallback_in_a_flat_dir(memdir, stem, kind):
    """Regression guard (GREEN at HEAD): no frontmatter type, top level -> the stem decides."""
    p = mem(memdir, f"{stem}.md", title="t", mtype=None, body="b")
    assert mi.Entry(p, memdir, {}).kind == kind


# ---- AC-8 / AC-9: un-organised dirs keep HEAD's bytes --------------------------------------

def test_ac8_a_flat_dir_with_no_prose_renders_byte_identically_to_head(memdir):
    build_flat_no_prose(memdir)
    mi.write(memdir, out=io.StringIO())
    assert (memdir / "MEMORY.md").read_bytes() == golden("flat_no_prose", "MEMORY.md")
    assert (memdir / mi.HOOKS_SIDECAR).read_bytes() == golden("flat_no_prose", "memory_hooks.json")


def test_ac9_flat_marker_off_is_heads_write_byte_for_byte(memdir):
    """HEAD drops the prose line and writes a path-keyed sidecar; un-organised, so must we.
    "Sidecar absent" is the wrong assertion: HEAD creates it (r3 s1)."""
    build_flat_one_prose(memdir)
    assert not (memdir / mi.HOOKS_SIDECAR).exists()
    mi.write(memdir, out=io.StringIO())
    assert (memdir / "MEMORY.md").read_bytes() == golden("flat_one_prose", "MEMORY.md")
    assert (memdir / mi.HOOKS_SIDECAR).read_bytes() == golden("flat_one_prose", "memory_hooks.json")


def test_ac9_flat_marker_on_twin_carries_prose_and_keys_the_sidecar_by_id(memdir):
    build_flat_one_prose(memdir)
    organise(memdir)
    mi.write(memdir, out=io.StringIO())
    lines = (memdir / "MEMORY.md").read_text(encoding="utf-8").splitlines()
    assert CARRY_HEAD in lines
    assert lines.index(CARRY_HEAD) < lines.index("# My hand-written memory index") \
        < lines.index("- [X](project_x.md) — curated x hook"), lines
    assert sidecar(memdir) == {"project_x": "curated x hook"}


def test_ac9_nested_marker_off_lists_every_entry_drops_prose_keeps_path_keys(memdir):
    """r4 s1 + r5 m1: viascope's shape with no marker gets AC-3's wider `collect` under HEAD's
    render, compaction and sidecar. "All 8 listed" = 7 entry links + the impressions pointer
    (`ch-bsd impressions (1)`); 8 on `collect()`. HEAD renders 1 entry link + the pointer."""
    build_viascope_shape(memdir)
    hand = ["# one hand-written prose line"] + [
        f"- [{t}]({rel}) — curated {t.lower()}" for rel, t, _ in VIA_ENTRIES]
    (memdir / "MEMORY.md").write_text("\n".join(hand) + "\n", encoding="utf-8")
    assert len(mi.collect(memdir)) == 8
    mi.write(memdir, out=io.StringIO())
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    links = entry_lines(text)
    for rel, t, mtype in VIA_ENTRIES:
        if mtype == "impression":
            continue
        assert f"- [{t}]({rel}) — curated {t.lower()}" in links, (rel, text)
    assert "- [ch-bsd impressions (1)](impressions/)" in text
    assert len(links) == 8, links                  # 7 entry links + the impressions pointer
    assert "# one hand-written prose line" not in text, "HEAD's trade: prose is dropped here"
    assert CARRY_HEAD not in text
    assert set(sidecar(memdir)) == {rel for rel, _, _ in VIA_ENTRIES}, sidecar(memdir)


# ---- task 26.1 remedy, ch-bsd 26.1 #b-1: an entry line never loses its link ---------------
#
# `Entry.line` cut every line at MAX_LINE_CHARS (200). With a long title the cut landed before
# `](rel)`: the line kept `- [` but lost its link, so the next ORGANISED render read it as prose,
# carried it, and rendered the same entry again -- the carried block grew every pass (real
# cliquedb: 8 -> 16 -> ... -> 64 lines, frozen at 40,458 chars). Marker-off, HEAD's cut made the
# memory unreachable from the index (8 link-less lines in cliquedb's live index today). AC-5
# (amended): an entry line is never cut inside its link, and a generated entry line is never
# prose. The HEAD goldens above have short titles and stay byte-identical.

LONG_TITLE = ("A very long memory title — the kind cliquedb really carries, naming the "
              "mechanism, the incident, the date and the fix in one breath because the "
              "author wanted the index line to say everything: 2026-11-09 edition, part two")
LONG_HOOK = ("a curated hook that runs on and on, well past the line cap, because the human "
             "who wrote it wanted the whole story in the index rather than in the memory "
             "itself, which is exactly what real indexes look like")
B1_PROSE = ["# Hand index", "Read the campaign block first.", "## Campaign",
            "**Goal:** keep every link."]


def build_long_title_dir(memdir: Path) -> dict:
    assert len(LONG_TITLE) > 200 and len(LONG_HOOK) > 200
    mem(memdir, "feedback/feedback_long_title.md", title=LONG_TITLE, mtype="feedback",
        body="derived long-title prose")
    mem(memdir, "feedback/feedback_long_hook.md", title="Short title", mtype="feedback",
        body="derived long-hook prose")
    mem(memdir, "project/project_plain.md", title="Plain", mtype="project",
        body="derived plain prose")
    (memdir / "MEMORY.md").write_text("\n".join(B1_PROSE + [
        f"- [Short title](feedback/feedback_long_hook.md) — {LONG_HOOK}",
        "- [Plain](project/project_plain.md) — curated plain",
    ]) + "\n", encoding="utf-8")
    return {"feedback/feedback_long_title.md": LONG_TITLE,
            "feedback/feedback_long_hook.md": "Short title",
            "project/project_plain.md": "Plain"}


def carried_block(lines: list) -> list:
    """The carried block's lines: from CARRY_HEAD up to the blank line that closes it."""
    if CARRY_HEAD not in lines:
        return []
    i = lines.index(CARRY_HEAD)
    out = []
    for ln in lines[i + 1:]:
        if not ln.strip():
            break
        out.append(ln)
    return out


def assert_every_entry_keeps_its_link(text: str, rels: dict) -> None:
    lines = text.splitlines()
    cut = [ln for ln in lines if ln.startswith("- [") and "](" not in ln]
    assert not cut, f"entry line(s) cut before their link: {cut}"
    for rel, title in rels.items():
        hits = [ln for ln in lines if f"]({rel})" in ln]
        assert len(hits) == 1, f"{rel}: {len(hits)} entry lines carry its link: {hits}"
        assert hits[0].startswith("- [" + title[:40]), f"{rel}: title not kept: {hits[0]!r}"
        assert len(hits[0]) <= mi.MAX_LINE_CHARS, (len(hits[0]), hits[0])


def test_b1_long_title_organised_render_is_stable_over_three_renders(memdir):
    rels = build_long_title_dir(memdir)
    organise(memdir)
    sizes, texts = [], []
    for n in (1, 2, 3):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
        assert_every_entry_keeps_its_link(text, rels)
        block = carried_block(text.splitlines())
        gen = [ln for ln in block if ln.startswith("- [")]
        assert not gen, f"render {n}: a generated entry line was carried as prose: {gen}"
        assert block == B1_PROSE, f"render {n}: carried block is not the hand prose: {block}"
        sizes.append(len(block))
        texts.append(text)
    assert sizes[0] == sizes[1] == sizes[2], f"carried block grew per render: {sizes}"
    assert texts[0] == texts[1] == texts[2], "re-rendering changed the index"
    chk = run_entry(memdir, "--check")
    assert chk.returncode == 0, chk.stdout + chk.stderr


def test_b1_marker_off_then_organised_never_carries_entry_lines(memdir):
    """The real migration order: the un-organised (HEAD) write runs first, then 26.5 lays the
    marker and save-state renders again and again. No entry line produced by the marker-off
    write may come back as carried prose."""
    rels = build_long_title_dir(memdir)
    (memdir / "MEMORY.md").write_text("\n".join(B1_PROSE) + "\n", encoding="utf-8")
    mi.write(memdir, out=io.StringIO())                       # marker-off: HEAD's write
    assert_every_entry_keeps_its_link((memdir / "MEMORY.md").read_text(encoding="utf-8"), rels)
    organise(memdir)
    sizes = []
    for n in (1, 2, 3):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
        assert_every_entry_keeps_its_link(text, rels)
        block = carried_block(text.splitlines())
        assert not [ln for ln in block if ln.startswith("- [")], (n, block)
        sizes.append(len(block))
    assert sizes[0] == sizes[1] == sizes[2], sizes


def test_b1_marker_off_a_long_title_keeps_its_link(memdir):
    """Stated byte change vs HEAD for long-title dirs only: HEAD cut the link off (the memory
    became unreachable from the index). Short-title dirs stay byte-identical (the goldens)."""
    mem(memdir, "feedback_long_title.md", title=LONG_TITLE, mtype="feedback",
        body="derived long-title prose")
    mem(memdir, "feedback_short.md", title="Short", mtype="feedback", body="derived short")
    (memdir / "MEMORY.md").write_text(
        f"- [Short](feedback_short.md) — {LONG_HOOK}\n", encoding="utf-8")
    assert not (memdir / ".memory-layout").exists()
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert_every_entry_keeps_its_link(
        text, {"feedback_long_title.md": LONG_TITLE, "feedback_short.md": "Short"})


# ---- task 26.1 remedy, ch-bsd 26.1 #m-1: an organised write never exceeds max_chars --------
#
# On cliquedb, marker-on render 1 was 24,378 chars: the carried prose pushed the tail past the
# budget, the report said "STILL OVER ... the tail WILL be cut on load", and the write went ahead.
# AC-6 (amended): an organised write folds further, and refuses when even a full fold cannot
# fit -- index AND sidecar untouched, the reason (with the prose count) on `out`, return 0.

def test_m1_organised_write_folds_further_to_fit_the_budget(memdir):
    """Guard: when folding project notes CAN make room, the written index fits."""
    prose = [f"Hand paragraph {i}: " + "p" * 100 for i in range(8)]          # ~950 chars
    for i in range(3):
        mem(memdir, f"feedback/feedback_k{i}.md", title=f"K{i}", mtype="feedback", body=f"k{i}")
    lines = list(prose)
    for i in range(20):
        mem(memdir, f"project/project_q{i:02d}.md", title=f"Q{i:02d}", mtype="project",
            body=f"q{i}", mtime=T0 + i)
        lines.append(f"- [Q{i:02d}](project/project_q{i:02d}.md) — " + "h" * 120)
    (memdir / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    organise(memdir)
    buf = io.StringIO()
    n = mi.write(memdir, max_chars=2400, out=buf)
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert n > 0, buf.getvalue()
    assert len(text) <= 2400, (len(text), buf.getvalue())
    assert "older project memories folded" in text
    assert carried_block(text.splitlines()) == prose


def test_m1_organised_write_refuses_when_a_full_fold_cannot_fit(memdir):
    """Feedback is never folded. 8 prose lines (~950 chars, under the 75% the 25% rule allows)
    plus 10 long feedback entries (~1,600 chars) cannot fit 2,000 chars at any fold: refuse.
    At HEAD the over-budget render is written and only reported as STILL OVER."""
    prose = [f"Hand paragraph {i}: " + "p" * 100 for i in range(8)]
    lines = list(prose)
    for i in range(10):
        mem(memdir, f"feedback/feedback_f{i}.md", title=f"F{i}", mtype="feedback", body=f"f{i}")
        lines.append(f"- [F{i}](feedback/feedback_f{i}.md) — " + "c" * 130)
    before = "\n".join(lines) + "\n"
    # AC-6 (amended 03516f2): refuse only when the CARRIED PROSE blocks the fit -- the same
    # entries with no carried block fit 2,000 chars.
    assert len("\n".join(lines[len(prose):]) + "\n") < 2000
    (memdir / "MEMORY.md").write_text(before, encoding="utf-8")
    side_before = json.dumps({f"feedback_f{i}": "c" * 130 for i in range(10)})
    (memdir / mi.HOOKS_SIDECAR).write_text(side_before, encoding="utf-8")
    organise(memdir)
    buf = io.StringIO()
    n = mi.write(memdir, max_chars=2000, out=buf)
    said = buf.getvalue()
    assert (memdir / "MEMORY.md").read_text(encoding="utf-8") == before, \
        f"an over-budget render was written: {said}"
    assert (memdir / mi.HOOKS_SIDECAR).read_text(encoding="utf-8") == side_before
    assert n == 0, said
    assert "untouched" in said and "prose" in said and re.search(r"\b8\b", said), said


def test_m1_entry_point_never_writes_over_budget(memdir):
    """The same refusal through the real entry point and the env budget."""
    prose = [f"Hand paragraph {i}: " + "p" * 100 for i in range(8)]
    lines = list(prose)
    for i in range(10):
        mem(memdir, f"feedback/feedback_f{i}.md", title=f"F{i}", mtype="feedback", body=f"f{i}")
        lines.append(f"- [F{i}](feedback/feedback_f{i}.md) — " + "c" * 130)
    before = "\n".join(lines) + "\n"
    assert len("\n".join(lines[len(prose):]) + "\n") < 2000     # no-prose render fits
    (memdir / "MEMORY.md").write_text(before, encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir, env={"RMX_MEMORY_INDEX_CHARS": "2000"})
    assert r.returncode == 0, r.stderr
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert text == before, \
        f"a full fold cannot fit, so the write must refuse; wrote {len(text)} chars"
    assert "untouched" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_b1_a_legacy_link_less_cut_line_is_dropped_and_re_rendered_with_its_link(memdir):
    """AC-5 (amended 4fff5cc): any line shaped like an entry (starts `- [`) is never prose,
    link or no link. HEAD's link-less cut lines already sit in live indexes (cliquedb: 8); an
    organised render drops them and renders the memory again WITH its link -- never carries
    them. The legacy line is built with HEAD's own cut formula."""
    rel = "feedback/feedback_long_title.md"
    mem(memdir, rel, title=LONG_TITLE, mtype="feedback", body="derived long-title prose")
    mem(memdir, "project/project_plain.md", title="Plain", mtype="project", body="plain")
    full = f"- [{LONG_TITLE}]({rel}) — derived long-title prose"
    legacy = full[:mi.MAX_LINE_CHARS - 1].rstrip() + "…"          # HEAD's Entry.line cut
    assert legacy.startswith("- [") and "](" not in legacy
    (memdir / "MEMORY.md").write_text("\n".join(B1_PROSE + [
        legacy, "- [Plain](project/project_plain.md) — curated plain"]) + "\n",
        encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    first = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    lines = first.splitlines()
    block = carried_block(lines)
    assert legacy not in block, f"the legacy cut line was carried as prose: {block}"
    assert block == B1_PROSE, block
    assert legacy not in lines, "the legacy link-less line survived the render"
    hits = [ln for ln in lines if f"]({rel})" in ln]
    assert len(hits) == 1 and hits[0].startswith("- [" + LONG_TITLE[:40]), hits
    assert not [ln for ln in lines if ln.startswith("- [") and "](" not in ln], lines
    assert run_entry(memdir).returncode == 0
    assert (memdir / "MEMORY.md").read_text(encoding="utf-8") == first, \
        "a second render changed the index"


def test_m1_no_prose_over_budget_even_fully_folded_writes_and_says_still_over(memdir):
    """AC-6 (amended 03516f2): with NO carried prose there is nothing the user can move, so an
    index that cannot fit even fully folded is WRITTEN and `STILL OVER` is printed, exactly as a
    marker-off dir does -- an index that stops updating is worse than an over-budget one."""
    for i in range(10):
        mem(memdir, f"feedback/feedback_f{i}.md", title=f"F{i}", mtype="feedback",
            body="c" * 130)
    before = "- [F0](feedback/feedback_f0.md) — the only entry the old index listed\n"
    (memdir / "MEMORY.md").write_text(before, encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir, env={"RMX_MEMORY_INDEX_CHARS": "1000"})
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert text != before, f"the over-budget, prose-free write was refused: {said}"
    assert CARRY_HEAD not in text
    assert len(entry_lines(text)) == 10, text
    assert len(text) > 1000, len(text)
    assert "STILL OVER" in said, said
    assert "untouched" not in said, said
    n = mi.write(memdir, max_chars=1000, out=io.StringIO())   # the in-process return value
    assert n == len(text.splitlines()), n


# ---- AC-5 hook precedence (amended 03516f2): an empty index hook never erases a curated one -
#
# An entry whose link alone is over MAX_LINE_CHARS renders with NO hook. The next render read
# that line back as an empty curated hook, which overrode the sidecar's curated text; the entry
# fell back to derived prose and `save_hooks` wrote the derived text over the curated hook.

CURATED = "the curated hook a human wrote for this memory"


def _long_link_memory(memdir: Path, rel: str) -> str:
    mem(memdir, rel, title="Long link", mtype="feedback", body="derived prose, not curated")
    mem(memdir, "feedback/feedback_short.md" if "/" in rel else "feedback_short.md",
        title="Short", mtype="feedback", body="derived short")
    assert len(f"- [Long link]({rel})") > mi.MAX_LINE_CHARS
    return Path(rel).stem


def test_hook_precedence_empty_index_hook_keeps_the_curated_sidecar_hook_organised(memdir):
    rel = "feedback/feedback_" + "l" * 190 + ".md"
    mid = _long_link_memory(memdir, rel)
    organise(memdir)
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({mid: CURATED}), encoding="utf-8")
    for n in (1, 2):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        side = sidecar(memdir)
        assert side.get(mid) == CURATED, f"render {n}: curated hook lost: {side.get(mid)!r}"
    assert [e.hook for e in mi.collect(memdir) if e.id == mid] == [CURATED]


def test_hook_precedence_empty_index_hook_keeps_the_curated_sidecar_hook_marker_off(memdir):
    """Readers are dual in every dir (ADR-0005 #marker): the same precedence holds in
    `load_hooks` without the marker, where `save_hooks` writes the path-keyed sidecar."""
    rel = "feedback_" + "l" * 195 + ".md"
    _long_link_memory(memdir, rel)
    assert not (memdir / ".memory-layout").exists()
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({rel: CURATED}), encoding="utf-8")
    for n in (1, 2):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        side = sidecar(memdir)
        assert side.get(rel) == CURATED, f"render {n}: curated hook lost: {side.get(rel)!r}"
    assert [e.hook for e in mi.collect(memdir) if e.rel == rel] == [CURATED]


# ---- task 26.1 follow-up (ch-bsd 26.1 r2, spec #followup-r2) ------------------------------
#
# #fu-hooks (bug-193, r2 #s-1 + #m-1): an index hook replaces the sidecar value EXCEPT when the
# index could not carry it -- (a) the link alone is over the cap (no hook on the line; the two
# tests above), (b) the hook is the rendered cut of the sidecar value (`prefix…`), (c) a bare
# `…`. A hook the user deletes from a line that HAD room is cleared, as at HEAD 61b3bde, in
# every dir. Supersedes the remedy GREEN's "an empty index hook never erases a curated hook".

HEAD_SHA = "61b3bde"
REPO = Path(__file__).resolve().parents[1]


def _layouts():
    return pytest.mark.parametrize("organised", [True, False], ids=["organised", "marker-off"])


def _key(organised: bool, rel: str) -> str:
    """The sidecar key a write uses: memory id (organised) or relative path (marker-off)."""
    return Path(rel).stem if organised else rel


def _rel(organised: bool, folder: str, stem: str) -> str:
    return f"{folder}/{stem}.md" if organised else f"{stem}.md"


def _line_for(text: str, rel: str) -> str:
    hits = [ln for ln in text.splitlines() if f"]({rel})" in ln]
    assert len(hits) == 1, (rel, hits)
    return hits[0]


@_layouts()
def test_fu_hooks_a_long_curated_hook_keeps_its_full_text_over_three_renders(memdir, organised):
    """bug-193: a hand-written hook longer than the line allows renders as `prefix…`. At
    7b5ea2f the next render read `prefix…` back from the index, it won over the sidecar, and
    `save_hooks` wrote the cut over the full text: 246 chars survived one render, then 171."""
    rel = _rel(organised, "feedback", "feedback_long_hook")
    mem(memdir, rel, title="Short title", mtype="feedback", body="derived prose, not curated")
    mem(memdir, _rel(organised, "project", "project_plain"), title="Plain", mtype="project",
        body="derived plain")
    assert len(f"- [Short title]({rel}) — {LONG_HOOK}") > mi.MAX_LINE_CHARS
    (memdir / "MEMORY.md").write_text(
        f"- [Short title]({rel}) — {LONG_HOOK}\n", encoding="utf-8")
    if organised:
        organise(memdir)
    key = _key(organised, rel)
    lines = []
    for n in (1, 2, 3):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        side = sidecar(memdir)
        assert side.get(key) == LONG_HOOK, \
            f"render {n}: the sidecar lost the full curated hook: {side.get(key)!r}"
        text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
        ln = _line_for(text, rel)
        assert ln.endswith("…") and len(ln) <= mi.MAX_LINE_CHARS, (n, ln)
        lines.append(ln)
    assert lines[0] == lines[1] == lines[2], f"the cut line moved between renders: {lines}"
    assert [e.hook for e in mi.collect(memdir) if e.rel == rel] == [LONG_HOOK]
    chk = run_entry(memdir, "--check")
    assert chk.returncode == 0, chk.stdout + chk.stderr


@_layouts()
def test_fu_hooks_the_live_cut_state_restores_nothing_lost_from_the_sidecar(memdir, organised):
    """The state live refmatrix's index is in today: sidecar holds the full hook, the index
    holds its rendered cut. A render must keep the sidecar's full text, not take the cut."""
    rel = _rel(organised, "feedback", "feedback_long_hook")
    mem(memdir, rel, title="Short title", mtype="feedback", body="derived prose, not curated")
    key = _key(organised, rel)
    if organised:
        organise(memdir)
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({key: LONG_HOOK}), encoding="utf-8")
    full = f"- [Short title]({rel}) — {LONG_HOOK}"
    cut = full[:mi.MAX_LINE_CHARS - 1].rstrip() + "…"            # the rendered cut
    (memdir / "MEMORY.md").write_text(cut + "\n", encoding="utf-8")
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    assert sidecar(memdir).get(key) == LONG_HOOK, sidecar(memdir)
    assert _line_for((memdir / "MEMORY.md").read_text(encoding="utf-8"), rel) == cut


@_layouts()
def test_fu_hooks_a_bare_ellipsis_index_hook_never_replaces_the_sidecar(memdir, organised):
    """3 sidecar values across the fleet copies are a bare `…`, left by HEAD cuts that ended
    `.md)…`. A bare `…` read from the index is no hook: the curated sidecar text stands."""
    rel = _rel(organised, "feedback", "feedback_a")
    mem(memdir, rel, title="A", mtype="feedback", body="derived a prose")
    key = _key(organised, rel)
    if organised:
        organise(memdir)
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({key: CURATED}), encoding="utf-8")
    (memdir / "MEMORY.md").write_text(f"- [A]({rel}) — …\n", encoding="utf-8")
    for n in (1, 2):
        r = run_entry(memdir)
        assert r.returncode == 0, r.stderr
        assert sidecar(memdir).get(key) == CURATED, (n, sidecar(memdir))
        assert _line_for((memdir / "MEMORY.md").read_text(encoding="utf-8"), rel) == \
            f"- [A]({rel}) — {CURATED}", n


@_layouts()
def test_fu_hooks_guard_an_edited_hook_that_is_not_the_cut_still_replaces(memdir, organised):
    """Guard (GREEN at 7b5ea2f): the exception is NARROW. A hand edit -- even one ending `…` --
    that is not a prefix of the sidecar value replaces it; the index is what a human last
    edited."""
    rel = _rel(organised, "feedback", "feedback_a")
    mem(memdir, rel, title="A", mtype="feedback", body="derived a prose")
    key = _key(organised, rel)
    if organised:
        organise(memdir)
    (memdir / mi.HOOKS_SIDECAR).write_text(json.dumps({key: CURATED}), encoding="utf-8")
    edited = "a fresh hand edit that trails off…"
    (memdir / "MEMORY.md").write_text(f"- [A]({rel}) — {edited}\n", encoding="utf-8")
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    assert sidecar(memdir).get(key) == edited, sidecar(memdir)


def _hook_clear_dir(memdir: Path, organised: bool) -> str:
    rel = _rel(organised, "feedback", "feedback_a")
    mem(memdir, rel, title="A", mtype="feedback", body="derived a prose")
    mem(memdir, _rel(organised, "feedback", "feedback_b"), title="B", mtype="feedback",
        body="derived b prose")
    (memdir / "MEMORY.md").write_text(
        f"- [A]({rel}) — {CURATED}\n"
        f"- [B]({_rel(organised, 'feedback', 'feedback_b')}) — curated b\n", encoding="utf-8")
    return rel


def _clear_hook(memdir: Path, rel: str) -> None:
    idx = memdir / "MEMORY.md"
    text = idx.read_text(encoding="utf-8")
    line = _line_for(text, rel)
    assert line.endswith(f" — {CURATED}"), line
    idx.write_text(text.replace(line, f"- [A]({rel})"), encoding="utf-8")


def test_fu_hooks_a_hook_deleted_from_a_line_with_room_is_cleared_organised(memdir):
    """r2 #m-1: at 7b5ea2f the sidecar brought a deleted hook back. The line had room for it,
    so the deletion is the user's: the entry falls back to the file's first prose line."""
    rel = _hook_clear_dir(memdir, organised=True)
    organise(memdir)
    assert run_entry(memdir).returncode == 0
    assert sidecar(memdir).get("feedback_a") == CURATED          # curated, before the clear
    _clear_hook(memdir, rel)
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert _line_for(text, rel) == f"- [A]({rel}) — derived a prose", text
    side = sidecar(memdir)
    assert CURATED not in side.values(), f"the deleted hook survives in the sidecar: {side}"
    assert side.get("feedback_a") == "derived a prose", side
    assert [e.hook for e in mi.collect(memdir) if e.rel == rel] == ["derived a prose"]


def _head_memory_index():
    """HEAD 61b3bde's own `memory_index` (stdlib-only), loaded from git -- the reference the
    marker-off clear must match byte for byte (ADR-0005 #marker)."""
    import importlib.util
    src = subprocess.run(["git", "-C", str(REPO), "show",
                          f"{HEAD_SHA}:src/refmatrix/memory_index.py"],
                         capture_output=True, text=True, timeout=30)
    assert src.returncode == 0, f"cannot read {HEAD_SHA}'s memory_index: {src.stderr}"
    assert "memory_layout" not in src.stdout, "not HEAD's pre-26.1 memory_index"
    d = Path(tempfile.mkdtemp(prefix="rmxhd-"))
    f = d / "head_memory_index.py"
    f.write_text(src.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("head_memory_index_61b3bde", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    shutil.rmtree(d, ignore_errors=True)
    return mod


def test_fu_hooks_a_hook_deleted_from_a_line_with_room_is_cleared_marker_off_as_at_head(memdir):
    """Marker-off keeps HEAD 61b3bde's hook-clear exactly: the same two renders (write, user
    deletes the hook, write) through HEAD's code and through ours give the same index AND the
    same sidecar bytes."""
    head = _head_memory_index()
    twin = memdir.parent / "twin"
    twin.mkdir()
    rel = _hook_clear_dir(memdir, organised=False)
    _hook_clear_dir(twin, organised=False)
    assert not (memdir / ".memory-layout").exists()
    assert run_entry(memdir).returncode == 0
    head.write(twin, out=io.StringIO())
    _clear_hook(memdir, rel)
    _clear_hook(twin, rel)
    r = run_entry(memdir)
    assert r.returncode == 0, r.stderr
    head.write(twin, out=io.StringIO())
    want = (twin / "MEMORY.md").read_text(encoding="utf-8")
    assert _line_for(want, rel) == f"- [A]({rel}) — derived a prose", want   # HEAD's behaviour
    assert (memdir / "MEMORY.md").read_text(encoding="utf-8") == want
    assert (memdir / mi.HOOKS_SIDECAR).read_bytes() == (twin / mi.HOOKS_SIDECAR).read_bytes(), \
        (sidecar(memdir), json.loads((twin / mi.HOOKS_SIDECAR).read_text(encoding="utf-8")))


# #fu-dropped (r2 #m-3): HEAD's whole-line cut left lines cut INSIDE their link (cliquedb: 11)
# and before it (8). The memories exist; the first render after the fix links them again. The
# report must not call that "dropped ... whose file is gone" -- only a link to a truly absent
# file is counted there.

CUT_TITLE = "T" * 180


@_layouts()
def test_fu_dropped_a_link_cut_by_head_is_not_reported_as_a_gone_file(memdir, organised):
    cut_rel = _rel(organised, "feedback", "feedback_cut_inside_the_link_aaaa")
    before_rel = _rel(organised, "feedback", "feedback_cut_before_the_link")
    plain_rel = _rel(organised, "project", "project_plain")
    gone_rel = _rel(organised, "project", "project_gone")
    mem(memdir, cut_rel, title=CUT_TITLE, mtype="feedback", body="derived cut prose")
    mem(memdir, before_rel, title=LONG_TITLE, mtype="feedback", body="derived before prose")
    mem(memdir, plain_rel, title="Plain", mtype="project", body="derived plain")

    def head_cut(title, rel, hook):
        full = f"- [{title}]({rel}) — {hook}"
        return full[:mi.MAX_LINE_CHARS - 1].rstrip() + "…"          # HEAD's Entry.line cut

    inside = head_cut(CUT_TITLE, cut_rel, "derived cut prose")
    before = head_cut(LONG_TITLE, before_rel, "derived before prose")
    assert "](" in inside and ")" not in inside.split("](", 1)[1], inside   # cut inside link
    assert "](" not in before, before                                      # cut before link
    (memdir / "MEMORY.md").write_text("\n".join([
        inside, before,
        f"- [Plain]({plain_rel}) — curated plain",
        f"- [Gone]({gone_rel}) — a memory whose file was deleted",
    ]) + "\n", encoding="utf-8")
    if organised:
        organise(memdir)
    r = run_entry(memdir)
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    for rel in (cut_rel, before_rel, plain_rel):
        _line_for(text, rel)                                     # every memory is linked again
    dropped = [ln for ln in said.splitlines() if "whose file is gone" in ln]
    assert len(dropped) == 1, f"a truly gone file must still be reported once: {said}"
    m = re.search(r"dropped (\d+) entr", dropped[0])
    assert m and m.group(1) == "1", \
        f"a memory re-linked after HEAD's cut was counted as gone: {dropped[0]}"
    assert gone_rel in dropped[0], dropped[0]
    assert "…" not in dropped[0] and Path(cut_rel).stem[:20] not in dropped[0], dropped[0]


@_layouts()
def test_fu_dropped_only_cut_links_no_gone_line_at_all(memdir, organised):
    """With no truly missing file the report prints no "dropped" line (or says 0)."""
    cut_rel = _rel(organised, "feedback", "feedback_cut_inside_the_link_aaaa")
    plain_rel = _rel(organised, "project", "project_plain")
    mem(memdir, cut_rel, title=CUT_TITLE, mtype="feedback", body="derived cut prose")
    mem(memdir, plain_rel, title="Plain", mtype="project", body="derived plain")
    full = f"- [{CUT_TITLE}]({cut_rel}) — derived cut prose"
    inside = full[:mi.MAX_LINE_CHARS - 1].rstrip() + "…"
    assert "](" in inside and ")" not in inside.split("](", 1)[1], inside
    (memdir / "MEMORY.md").write_text(
        f"{inside}\n- [Plain]({plain_rel}) — curated plain\n", encoding="utf-8")
    if organised:
        organise(memdir)
    r = run_entry(memdir)
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    for ln in said.splitlines():
        if "whose file is gone" in ln:
            m = re.search(r"dropped (\d+) entr", ln)
            assert m and m.group(1) == "0", f"false 'dropped' report: {ln}"


# #fu-skips (r2 #m-2, organised half): `_prose_lines` drops every line that starts `- [`. A
# hand-written `- [ ] todo` names no memory; dropping it uncounted is a silent loss
# (CLAUDE.md #no-silent-failures). It is counted and named in the write report.

def test_fu_skips_an_organised_write_counts_and_names_a_dropped_bracket_prose_line(memdir):
    mem(memdir, "feedback/feedback_a.md", title="A", mtype="feedback", body="derived a")
    mem(memdir, "project/project_p.md", title="P", mtype="project", body="derived p")
    todo = "- [ ] todo: rotate the signing keys before the release"
    (memdir / "MEMORY.md").write_text("\n".join([
        "# Hand index", todo,
        "- [A](feedback/feedback_a.md) — curated a",
        "- [P](project/project_p.md) — curated p",
    ]) + "\n", encoding="utf-8")
    organise(memdir)
    r = run_entry(memdir)
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    text = (memdir / "MEMORY.md").read_text(encoding="utf-8")
    assert todo not in text                       # dropped, as decided (entry-shaped)
    assert "rotate the signing keys" in said, \
        f"the dropped `- [` prose line is not named in the report: {said}"
    assert "whose file is gone" not in said, said
    assert re.search(r"\b(dropped|skipped) 1\b", said), \
        f"the dropped `- [` prose line is not counted ('dropped 1' / 'skipped 1'): {said}"
