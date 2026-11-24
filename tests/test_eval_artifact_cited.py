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


# ── LongMemEval (plan-7, T0.6) ─────────────────────────────────────────────
# The dense and fused rows were blocked on bug-030 until T0.6 re-ran the embed on
# 0.84.0 (2026-11-23). README and PERFORMANCE cite one table of every surface; the
# test compares EVERY cell of that table with the committed artifact, not one row
# (plan-6 r1 #m-3: a one-row check let the rest of a table drift).
LME_ARTIFACT = "eval/production/longmemeval/results/summary-120-0.84.0.json"
LME_HEADING = "LongMemEval-S, production path"
# Column header -> (mode, metric) in the artifact. `ceiling` is the restricted pool's
# recall ceiling, carried in `_meta` and printed beside every restricted figure.
LME_COLUMNS = {
    "restricted R@5": ("restricted", "recall@5"),
    "restricted hit@5": ("restricted", "hit@5"),
    "restricted MRR@20": ("restricted", "mrr"),
    "ceiling": ("restricted", "recall_ceiling"),
    "union R@5": ("union", "recall@5"),
}


def _lme_table(text: str) -> dict[str, dict[str, str]]:
    """The cited LongMemEval table as {surface: {column: cell}}."""
    at = text.find(LME_HEADING)
    assert at >= 0, f"no '{LME_HEADING}' section"
    lines = text[at:].splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("|"))
    rows = []
    for ln in lines[start:]:
        if not ln.lstrip().startswith("|"):
            break
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    header, body = rows[0], rows[2:]
    assert header[0] == "surface", header
    assert set(header[1:]) == set(LME_COLUMNS), header
    table = {}
    for r in body:
        # A surface may carry a footnote mark: * depth-uncontrolled, † / ‡ the bug-300
        # labels on the two `--fuse` rows.
        # An `-rr` row that was not reranked on every question carries its fraction
        # (`reranked n/N`, bug-303); the label is checked by the rerank test below.
        m = re.fullmatch(r"`([\w-]+)`\s*[*†‡]*(?:\s*\(reranked \d+/\d+\))?", r[0])
        assert m, f"unparseable surface cell {r[0]!r}"
        table[m.group(1)] = {h: c.strip("*") for h, c in zip(header[1:], r[1:])}
    return table


def _lme_artifact() -> dict:
    p = REPO / LME_ARTIFACT
    assert p.exists(), f"{LME_ARTIFACT} missing — copy run.py's summary.json with provenance"
    return json.loads(p.read_text())


def _lme_value(d: dict, surface: str, mode: str, metric: str) -> str:
    entry = d[f"{surface}/{mode}"]
    v = entry["_meta"][metric] if metric == "recall_ceiling" else entry["overall"][metric]
    return f"{v:.3f}"


def test_longmemeval_artifact_carries_its_provenance():
    d = _lme_artifact()
    prov = d["_provenance"]
    assert prov["harness"] == "eval/production/longmemeval/run.py"
    assert prov["rmx_version"] == "0.84.0"
    assert prov["n_questions"] == 120 and prov["depth"] == 50
    assert prov["corpus_docs"] == 19829
    assert prov["date"] and prov["command"]
    for key, entry in d.items():
        if key.startswith("_"):
            continue
        # A dead surface and an empty one both score 0.000 (ch-bsd r1 #s-13).
        assert entry["_meta"]["n_failed"] == 0, (key, entry["_meta"])
        assert entry["_meta"]["n_questions"] == 120, key


def test_longmemeval_table_cites_every_surface_and_cell():
    d = _lme_artifact()
    surfaces = {k.split("/", 1)[0] for k in d if not k.startswith("_")}
    assert surfaces == {"context", "scan", "recall", "recall-fuse", "recall-rr",
                        "recall-fuse-rr"}
    for doc in (README, PERF):
        text = doc.read_text()
        assert LME_ARTIFACT in text, f"{doc.name} does not cite {LME_ARTIFACT}"
        table = _lme_table(text)
        assert set(table) == surfaces, (doc.name, sorted(table))
        for surface, cells in table.items():
            for col, (mode, metric) in LME_COLUMNS.items():
                want = _lme_value(d, surface, mode, metric)
                assert cells[col] == want, (doc.name, surface, col, cells[col], want)


# bug-303 (bsd-t06 r1 #b-1, 2026-11-24): `memory recall --rerank` falls back to the dense
# order when its rerank cannot run ("rerank skipped: …; hits unreranked" on stderr), and run.py
# kept only the ids, so `recall-rr` was published as a rerank row while 86 of its 120 answers were
# the dense top 50. The artifact now counts the reranked answers. A row reranked on fewer than all
# questions (the fold-t06 re-runs skipped 2, then 1, on the shared worker's probe: bug-306) is cited
# only with its true fraction, `reranked n/N`, in every table cell that names it (L196 ruling (b)).
LME_RERANK_SURFACES = ("recall-rr", "recall-fuse-rr")
LME_RERANK_DOCS = (README, PERF, REPO / "eval/production/longmemeval/REPORT.md")


def _rerank_label_violations(text: str, surface: str, n: int, total: int) -> list[str]:
    """Every cell that LABELS a cited figure for `surface` (a table row's first cell, or a
    column header) must carry `reranked n/total` when n < total, and none may carry a
    fraction other than the artifact's. Returns the offending cells; raises nothing, so a
    planted bad doc can be checked for a non-empty answer."""
    want = f"reranked {n}/{total}"
    bad, seen = [], 0
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not ln.lstrip().startswith("|"):
            continue
        cells = ln.strip().strip("|").split("|")
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        header = bool(re.fullmatch(r"\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?", nxt))
        for cell in (cells if header else cells[:1]):
            if f"`{surface}`" not in cell:
                continue
            seen += 1
            labels = re.findall(r"reranked \d+/\d+", cell)
            if (n < total and labels != [want]) or any(lb != want for lb in labels):
                bad.append(cell.strip())
    if not seen:
        bad.append(f"<no table cell names `{surface}`>")
    return bad


def test_longmemeval_rerank_rows_carry_their_reranked_fraction():
    d = _lme_artifact()
    for surface in LME_RERANK_SURFACES:
        metas = [d[f"{surface}/{mode}"]["_meta"] for mode in ("union", "restricted")]
        for meta in metas:
            assert "n_reranked" in meta, (surface, meta)
            assert (meta["n_reranked"] + meta["n_rerank_skipped"] + meta["n_failed"]
                    == meta["n_questions"]), (surface, meta)
        assert metas[0]["n_reranked"] == metas[1]["n_reranked"], surface
        n, total = metas[0]["n_reranked"], metas[0]["n_questions"]
        for doc in LME_RERANK_DOCS:
            assert _rerank_label_violations(doc.read_text(), surface, n, total) == [], \
                (doc.name, surface, n, total)
    # Planted must-fail cases: the check can fail.
    row = "| `recall-fuse-rr` ‡{} | 0.541 |"
    assert _rerank_label_violations(row.format(""), "recall-fuse-rr", 119, 120)
    assert _rerank_label_violations(row.format(" (reranked 118/120)"), "recall-fuse-rr", 119, 120)
    assert _rerank_label_violations(row.format(" (reranked 119/120)"), "recall-fuse-rr", 120, 120)
    assert _rerank_label_violations("no table here", "recall-fuse-rr", 120, 120)
    header = "| type | `recall-fuse-rr` ‡{} |\n|---|---:|\n| x | 0.4 |"
    assert _rerank_label_violations(header.format(""), "recall-fuse-rr", 119, 120)
    assert not _rerank_label_violations(header.format(" (reranked 119/120)"), "recall-fuse-rr",
                                        119, 120)
    assert not _rerank_label_violations(row.format(" (reranked 119/120)"), "recall-fuse-rr",
                                        119, 120)
