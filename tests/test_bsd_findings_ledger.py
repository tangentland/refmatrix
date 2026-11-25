"""F4: the findings ledger tallies BULLSHIT by the self-audit question that missed it.

`scripts/bsd-tally.py` reads `workflow/bullshit/OPEN.md` and `CLOSED.md`. Every
test runs it as a subprocess on the real files or on a copy with one planted
row, the way the release step runs it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "bsd-tally.py"
LEDGER_DIR = REPO / "workflow" / "bullshit"


def _run(open_md: Path, closed_md: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--open", str(open_md),
         "--closed", str(closed_md)],
        capture_output=True, text=True, timeout=60)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def _bullshit_rows(*paths: Path) -> int:
    """Independent count: table rows whose level cell (3rd) says BULLSHIT."""
    n = 0
    for p in paths:
        for line in p.read_text().splitlines():
            if line.startswith("| ") and not line.startswith("| id ") \
                    and not line.startswith("|---"):
                if "BULLSHIT" in _cells(line)[2]:
                    n += 1
    return n


def test_tally_on_the_committed_ledger():
    r = _run(LEDGER_DIR / "OPEN.md", LEDGER_DIR / "CLOSED.md")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for n in range(1, 9):
        assert re.search(rf"^SA-{n}\b", out, re.M), out
    assert re.search(r"^unnamed\b", out, re.M), out
    m = re.search(r"^BULLSHIT-level rows: (\d+) \(open (\d+), upheld (\d+), "
                  r"overruled (\d+)\)", out, re.M)
    assert m, out
    total, o, u, ov = map(int, m.groups())
    assert total == o + u + ov
    assert total == _bullshit_rows(LEDGER_DIR / "OPEN.md",
                                   LEDGER_DIR / "CLOSED.md")
    assert total > 0


def _plant(tmp_path: Path, cells_for: "callable") -> tuple[Path, Path]:
    """Copy both ledgers; add one row to CLOSED.md built from its header."""
    o, c = tmp_path / "OPEN.md", tmp_path / "CLOSED.md"
    shutil.copy(LEDGER_DIR / "OPEN.md", o)
    lines = (LEDGER_DIR / "CLOSED.md").read_text().splitlines()
    header = next(l for l in lines if l.startswith("| id "))
    row = "| " + " | ".join(cells_for(len(_cells(header)))) + " |"
    at = max(i for i, l in enumerate(lines) if l.startswith("| "))
    lines.insert(at + 1, row)
    c.write_text("\n".join(lines) + "\n")
    return o, c


def _row(question: str | None):
    def build(width: int) -> list[str]:
        # id | report | level | question | finding | outcome | evidence | closed
        cells = ["plant-x1", "[[r]]", "BULLSHIT", question or "",
                 "a planted finding", "upheld", "fixed abc", "2026-11-25"]
        if question is None:          # a row that lost its question column
            del cells[3]
        return cells
    return build


@pytest.mark.parametrize("case,question", [
    ("empty-cell", ""),
    ("dash", "-"),
    ("unknown-token", "SA-9"),
    ("missing-column", None),
])
def test_tally_refuses_a_bad_row(tmp_path, case, question):
    o, c = _plant(tmp_path, _row(question))
    r = _run(o, c)
    assert r.returncode == 1, (case, r.stdout, r.stderr)
    assert "plant-x1" in r.stderr, (case, r.stderr)


def test_tally_accepts_a_planted_good_row(tmp_path):
    """The planted rows above fail for their cell, not for being planted."""
    o, c = _plant(tmp_path, _row("SA-3, SA-6"))
    r = _run(o, c)
    assert r.returncode == 0, r.stderr
