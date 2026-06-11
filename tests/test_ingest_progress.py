"""Ingest emits per-pass progress so the blocking daemon ingest isn't opaque."""
from __future__ import annotations

from refmatrix.ingest import ingest_path
from refmatrix.store import Store


def test_ingest_path_fires_progress_cb_per_pass(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "r.md").write_text("# Title\n\nbody about foo\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    phases: list[tuple[str, int, int]] = []
    n = ingest_path(s, tmp_path, source="auto", semantic=True,
                    progress_cb=lambda ph, d, t: phases.append((ph, d, t)))
    assert n >= 1
    names = [p[0] for p in phases]
    assert any("tldr/tree" in x for x in names)        # primary pass
    assert any("python-semantic" in x for x in names)  # semantic pass (a.py)
    assert any("markdown/adr" in x for x in names)      # md pass
    # the semantic pass reports its file count
    sem = [p for p in phases if p[0] == "code+docs: python-semantic"]
    assert sem and sem[0][2] == 1
    s.close()


def test_ingest_path_reports_per_file_counts(tmp_path):
    """The parse-heavy loops report incremental done/total, not just a single
    pass marker — so a big tree shows movement, not a frozen line."""
    for i in range(30):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    sem: list[tuple[int, int]] = []
    ingest_path(s, tmp_path, source="auto", semantic=True,
                progress_cb=lambda ph, d, t: (
                    sem.append((d, t)) if ph == "code+docs: python-semantic" else None))
    # incremental: a mid-run count (25/30) and a final (30/30)
    assert (30, 30) in sem
    assert any(0 < d < 30 for d, _ in sem)
    s.close()


def test_ingest_path_progress_cb_is_optional_and_isolated(tmp_path):
    """No cb → silent (back-compat); a throwing cb never breaks the ingest."""
    (tmp_path / "a.py").write_text("x = 1\n")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    assert ingest_path(s, tmp_path) >= 0           # no cb, unchanged behavior
    def _boom(*a):
        raise RuntimeError("progress sink died")
    # a broken sink is swallowed — ingest still completes
    assert ingest_path(s, tmp_path, source="tree", progress_cb=_boom) >= 0
    s.close()
