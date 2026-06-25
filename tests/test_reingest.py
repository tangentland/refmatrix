"""`rmx reingest` — the orchestrator that runs every ingest pass in canonical
order (code+docs -> memory -> sessions -> embed).

These tests drive the real CLI via CliRunner over an isolated scratch project
(cwd-resolved root), exercising steps 1-2 with sessions + embed disabled so the
test needs neither ~/.claude nor the dense embedder extra.
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix.store import Store

MEM_ONE = """\
---
gmd: "0.1"
id: mem_one
title: "One"
tags: [project]
metadata:
  type: project
---

# One {#root}

Body about the frobnicator.

rel: related-to -> [[mem_two]]
"""

MEM_TWO = """\
---
gmd: "0.1"
id: mem_two
title: "Two"
tags: [project]
metadata:
  type: project
---

# Two {#root}

Second body.
"""


def test_reingest_runs_code_then_memory_in_order(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "code.py").write_text("def frobnicate(x):\n    return x + 1\n")
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "mem_one.md").write_text(MEM_ONE)
    (mem / "mem_two.md").write_text(MEM_TWO)

    # init + reingest resolve the store root from cwd.
    monkeypatch.chdir(proj)
    runner = CliRunner()
    assert runner.invoke(main, ["init"], catch_exceptions=False).exit_code == 0

    r = runner.invoke(
        main,
        ["reingest", "--no-sessions", "--no-embed", "--no-semantic",
         "--memory-dir", str(mem)],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert "1/5 code+docs" in r.output
    assert "2/5 memory" in r.output
    assert "5/5 pagerank" in r.output
    assert "reingest done" in r.output

    s = Store(proj / ".refmatrix")
    con = s._connect()
    # Code pass ran.
    assert con.execute(
        "SELECT count(*) FROM entities WHERE kind='code'"
    ).fetchone()[0] >= 1
    # Memory pass ran with bodies AND deduped (one memory node per slug).
    for slug in ("mem_one", "mem_two"):
        rows = con.execute(
            "SELECT kind, count(*) FROM entities WHERE name=? GROUP BY kind",
            (slug,),
        ).fetchall()
        assert {r[0]: r[1] for r in rows} == {"memory": 1}
    assert con.execute(
        "SELECT count(*) FROM memory_content WHERE length(content) > 0"
    ).fetchone()[0] == 2
    s.close()


def test_reingest_skip_flags_short_circuit(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "code.py").write_text("x = 1\n")
    monkeypatch.chdir(proj)
    runner = CliRunner()
    assert runner.invoke(main, ["init"], catch_exceptions=False).exit_code == 0
    r = runner.invoke(
        main,
        ["reingest", "--no-sessions", "--no-embed", "--no-semantic",
         "--memory-dir", str(tmp_path / "does-not-exist")],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert "sessions: skipped" in r.output
    assert "embed: skipped" in r.output
    assert "memory: no dir" in r.output
