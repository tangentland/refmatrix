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
