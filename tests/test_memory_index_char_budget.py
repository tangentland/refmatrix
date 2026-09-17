"""bug-045 (ch-bsd #b-1/#b-2): the index is capped in the unit the loader cuts in,
and it stops writing to the MCP channel.

#b-1. bug-042 capped LINES (`MAX_LINES = 200`). The loader that truncates
`MEMORY.md` does not count lines — it counts CHARACTERS against a ~24.4 KiB
budget. So the cap sat on a dimension nothing enforces, `--check` reported "in
sync", and 38 entries stayed unreachable through the surface whose entire job is
to reach them.

The unit was settled by measurement, not by argument. The live index is 197
lines / 31,607 bytes / 31,043 chars, and the session banner reads "MEMORY.md is
30.3KB (limit: 24.4KB) … 38 of 197 lines were cut off, starting at line 160":

    unit=bytes  budget=24.4 KiB -> first line past budget = 157, 41 cut
    unit=chars  budget=24.4 KiB -> first line past budget = 160, 38 cut   <-- banner
    chars/1024 = 30.3 KiB                                                 <-- banner

Characters reproduce BOTH banner numbers exactly; bytes reproduce neither. (The
audit that found the defect prescribed a BYTE cap — right defect, wrong unit.
Recorded here because the next reader will otherwise re-derive it.)

#b-2. `write()` defaulted its report to stdout. `rmx mcp` speaks JSON-RPC on
stdout, and save-state calls `write()` without an `out=`, so a line reading
`MEMORY.md: 1 -> 2 lines` lands mid-protocol. The failure branch three lines up
already used stderr; only the success path was wrong.
"""
from __future__ import annotations

import io
import sys

import pytest

from refmatrix import memory_index as mi


def _memdir(tmp_path, n: int, *, hook_chars: int = 120, kind: str = "project"):
    d = tmp_path / "memory"
    d.mkdir()
    for i in range(n):
        (d / f"{kind}_entry_{i:04d}.md").write_text(
            "---\n"
            'gmd: "0.1"\n'
            f"id: {kind}_entry_{i:04d}\n"
            f'title: "Entry {i:04d}"\n'
            "metadata:\n"
            f"  type: {kind}\n"
            f"  created: 2026-09-{(i % 28) + 1:02d}\n"
            "---\n\n"
            f"# Entry {i:04d} {{#root}}\n\n"
            + ("x" * hook_chars) + "\n",
            encoding="utf-8",
        )
    return d


def test_render_stays_inside_the_char_budget(tmp_path):
    """The property that actually matters: what render() returns must survive
    the loader whole."""
    d = _memdir(tmp_path, 400)
    text = mi.render(d)
    assert len(text) <= mi.MAX_INDEX_CHARS, (
        f"rendered index is {len(text)} chars, over the "
        f"{mi.MAX_INDEX_CHARS}-char budget — the tail is unreachable"
    )


def test_the_budget_is_counted_in_characters_not_bytes(tmp_path):
    """A multi-byte index must not be folded as if it were ASCII. Every hook
    here is em-dashes (3 bytes, 1 char); counting bytes would fold ~3x too
    hard and silently drop entries that fit."""
    d = _memdir(tmp_path, 120, hook_chars=0)
    for i, p in enumerate(sorted(d.glob("*.md"))):
        p.write_text(
            p.read_text(encoding="utf-8").replace("x" * 0, "") + ("—" * 100) + "\n",
            encoding="utf-8",
        )
    text = mi.render(d)
    assert len(text) <= mi.MAX_INDEX_CHARS
    # The real assertion: we did not fold as if bytes were the unit. A byte cap
    # would leave the char length far under budget on a 3-bytes-per-char index.
    assert len(text.encode("utf-8")) > mi.MAX_INDEX_CHARS, (
        "test is not exercising the multi-byte case"
    )


def test_a_small_index_is_not_folded_at_all(tmp_path):
    """The cap must not fire when there is nothing to cap, or every session
    pays a fold it did not need."""
    d = _memdir(tmp_path, 5)
    text = mi.render(d)
    assert "folded" not in text
    assert len([l for l in text.splitlines() if l.startswith("- [")]) == 5


def test_check_agrees_with_the_char_budget(tmp_path):
    """`--check` reporting "in sync" on an index the loader truncates is the
    exact failure of bug-042: the gate must measure what the loader measures."""
    d = _memdir(tmp_path, 400)
    mi.write(d, out=io.StringIO())
    assert mi.check(d) is True
    assert len((d / mi.INDEX_NAME).read_text(encoding="utf-8")) <= mi.MAX_INDEX_CHARS


def test_write_reports_to_stderr_not_stdout_by_default(tmp_path, capsys):
    """stdout is the MCP JSON-RPC channel. save-state calls write() with no
    `out=`, so the default is what lands mid-protocol."""
    d = _memdir(tmp_path, 3)
    mi.write(d)
    cap = capsys.readouterr()
    assert cap.out == "", f"write() wrote to stdout: {cap.out!r}"
    assert mi.INDEX_NAME in cap.err


def test_write_empty_dir_notice_also_avoids_stdout(tmp_path, capsys):
    """The no-entries branch was already correct; keep it that way."""
    d = tmp_path / "memory"
    d.mkdir()
    mi.write(d)
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "no memory files found" in cap.err


def test_an_explicit_out_still_wins(tmp_path):
    """The CLI passes stdout deliberately; that path must keep working."""
    d = _memdir(tmp_path, 3)
    buf = io.StringIO()
    mi.write(d, out=buf)
    assert mi.INDEX_NAME in buf.getvalue()


def test_the_char_budget_is_overridable(tmp_path, monkeypatch):
    """The number belongs to the harness that loads the file, not to rmx, so it
    must be settable without a release."""
    monkeypatch.setenv("RMX_MEMORY_INDEX_CHARS", "900")
    import importlib
    mod = importlib.reload(mi)
    try:
        d = _memdir(tmp_path, 100)
        text = mod.render(d)
        assert len(text) <= 900
    finally:
        monkeypatch.delenv("RMX_MEMORY_INDEX_CHARS", raising=False)
        importlib.reload(mi)


def test_a_budget_that_cannot_be_met_is_announced_not_faked(tmp_path, capsys):
    """Rule 3 says feedback is NEVER folded. So an index that is all feedback can
    exceed the budget and there is nothing legitimate to do about it — except
    say so. The cap is a fold instruction, not a licence to drop feedback, and
    a silent over-budget index is bug-042 rebuilt (ch-bsd #s-4)."""
    d = _memdir(tmp_path, 200, kind="feedback")
    text = mi.render(d)
    kept = [l for l in text.splitlines() if l.startswith("- [")]

    # Every feedback entry survives: the budget never costs a feedback row.
    assert len(kept) == 200
    assert len(text) > mi.MAX_INDEX_CHARS      # genuinely cannot fit
    assert "folded" not in text                # and nothing was folded to fake it

    mi.write(d)
    err = capsys.readouterr().err
    assert "STILL OVER" in err, (
        "an index that cannot meet the budget must say so; a quiet one is the "
        "silence bug-042 created"
    )


def test_folding_prefers_old_project_notes_over_feedback(tmp_path):
    """When there IS something foldable, feedback must not be what gives."""
    d = _memdir(tmp_path, 150, kind="feedback")
    for i in range(150):
        (d / f"project_old_{i:04d}.md").write_text(
            "---\n"
            'gmd: "0.1"\n'
            f"id: project_old_{i:04d}\n"
            f'title: "Old {i:04d}"\n'
            "metadata:\n"
            "  type: project\n"
            "  created: 2026-01-01\n"
            "---\n\n"
            f"# Old {i:04d} {{#root}}\n\n" + ("y" * 120) + "\n",
            encoding="utf-8",
        )
    text = mi.render(d)
    assert "older project memories folded" in text
    feedback_rows = [l for l in text.splitlines() if "feedback_entry_" in l]
    assert len(feedback_rows) == 150, "folding took feedback rows"
