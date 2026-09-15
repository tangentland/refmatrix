"""plan-6 task 6.3: the headline benchmark number in README / PERFORMANCE
exists in a committed artifact written by the production harness itself.
Until 2026-09-14 the 0.961 lived only in a memory file and a savestate — no
`metrics.json`, no path a reader could open. Now README cites the artifact
path; this test opens it and compares the figure. If the artifact was not a
full-corpus run, README must say which run the number comes from."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
PERF = REPO / "docs" / "PERFORMANCE.md"
ARTIFACT = "eval/production/results/csn_python/metrics.json"


def _cited_mrr(text: str) -> str:
    m = re.search(r"\|\s*\*\*rmx, production path\*\*.*?\|\s*\*\*(\d\.\d{3})\*\*", text)
    if m:
        return m.group(1)
    m = re.search(r"\|\s*MRR@10\s*\|\s*\*\*(\d\.\d{3})\*\*", text)
    assert m, "no bold MRR@10 figure found"
    return m.group(1)


def test_readme_and_performance_cite_the_artifact_path():
    assert ARTIFACT in README.read_text()
    assert ARTIFACT in PERF.read_text()


def test_artifact_exists_and_was_written_by_the_harness():
    p = REPO / ARTIFACT
    assert p.exists(), f"{ARTIFACT} missing — run eval/production/csn_code.py --out {ARTIFACT}"
    d = json.loads(p.read_text())
    assert d["harness"] == "eval/production/csn_code.py"
    assert d["dataset"] == "csn_python"
    for k in ("MRR@10", "Recall@1", "Recall@10", "nDCG@10"):
        assert isinstance(d["metrics"][k], float), k
    assert d["corpus_docs"] > 0 and d["queries"] > 0
    assert isinstance(d["full_run"], bool)
    assert d["git_sha"] and d["refmatrix_version"] and d["generated_at"]


def test_cited_figure_matches_the_artifact():
    d = json.loads((REPO / ARTIFACT).read_text())
    want = f"{d['metrics']['MRR@10']:.3f}"
    assert _cited_mrr(README.read_text()) == want
    assert _cited_mrr(PERF.read_text()) == want


def test_partial_run_is_named_in_the_docs():
    d = json.loads((REPO / ARTIFACT).read_text())
    readme = README.read_text()
    if d["full_run"]:
        assert f"{d['corpus_docs']}" in readme.replace(" ", "").replace(",", "") \
            or "full corpus" in readme.lower()
    else:
        # a sampled run must be described where the number is cited
        assert d["sample_queries"], "partial run without a sample count"
        assert f"{d['sample_queries']} queries" in readme or \
            f"--sample-queries {d['sample_queries']}" in readme
