#!/usr/bin/env python3
"""Materialize a CSN subsample as real .py files, for the PRODUCTION pipeline.

Every other harness here bypasses the thing it claims to measure.
`eval/retrievers/rmx_retriever.py` imports `fuse_rrf` and `Store` and builds its
own index straight from the BEIR jsonl with its own tokenizer and its own
docstring splitter — it never calls `refmatrix.ingest`. So the 0.982 MRR@10 in
`eval/results/REPORT.md` measures the scoring stack and says nothing about what
ingest actually writes. That blind spot is why four separate "declared but never
populated" defects survived in the ingest path: `_extract_concept` ignoring a
populated `tldr`, `_UNIT_META_FIELDS` listing fields nothing filled,
`RecordingStore` dropping its `tldr` argument, and `_ingest_tldr_metadata`
reading a cache nothing generated.

This harness writes the corpus to DISK and then uses `rmx` exactly as a user
does: `rmx ingest`, `rmx embed`, `rmx context`. No adapter, no shortcut. If the
production path is broken, this is the harness that says so.

Two things it deliberately does NOT do:

  * It does not reuse the 43,827-doc corpus. Ingesting and embedding that many
    files is hours; a subsample is honest as long as the number is reported and
    never compared to the full-corpus table.
  * It does not write inside the refmatrix tree. The watcher would ingest the
    corpus into the project's own store — which has happened here before
    (`feedback_generated_data_off_watched_tree`).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE.parent / "datasets" / "csn_python"


def _read_jsonl(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            out[d["_id"]] = d.get("text") or ""
    return out


def _read_qrels(path: Path) -> dict[str, str]:
    """query-id -> the single gold corpus-id (CSN qrels are 1:1)."""
    out: dict[str, str] = {}
    with path.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if int(row.get("score") or 0) > 0:
                out[row["query-id"]] = row["corpus-id"]
    return out


def _module_name(doc_id: str) -> str:
    return f"unit_{doc_id.replace('_code', '')}.py"


def build(dataset: Path, out: Path, *, n_queries: int, seed: int,
          distractors: int) -> dict:
    """Write `n_queries` gold docs plus `distractors` extra docs as .py files.

    The gold set comes first so every sampled query is answerable; distractors
    enlarge the haystack. A subsample makes retrieval EASIER than the full
    corpus, which is why these numbers are only ever compared against each
    other, never against `eval/results/REPORT.md`.
    """
    corpus = _read_jsonl(dataset / "corpus.jsonl")
    queries = _read_jsonl(dataset / "queries.jsonl")
    qrels = _read_qrels(dataset / "qrels" / "test.tsv")

    rng = random.Random(seed)
    usable = [q for q, gold in qrels.items() if q in queries and gold in corpus]
    usable.sort()
    rng.shuffle(usable)
    picked = usable[:n_queries]

    keep = {qrels[q] for q in picked}
    pool = [c for c in sorted(corpus) if c not in keep]
    rng.shuffle(pool)
    keep.update(pool[:distractors])

    src = out / "corpus"
    src.mkdir(parents=True, exist_ok=True)
    for old in src.glob("*.py"):
        old.unlink()

    doc_to_file: dict[str, str] = {}
    for doc_id in sorted(keep):
        text = corpus[doc_id]
        # CSN units are function bodies indented for their original class, so a
        # bare write is a syntax error and `ast.parse` bails — which would make
        # the semantic pass silently extract nothing. Dedent to column 0.
        lines = text.splitlines()
        if lines and lines[0].startswith((" ", "\t")):
            text = "\n".join(ln[4:] if ln.startswith("    ") else ln
                             for ln in lines)
        name = _module_name(doc_id)
        (src / name).write_text(text + "\n", encoding="utf-8")
        doc_to_file[doc_id] = name

    manifest = {
        "dataset": dataset.name,
        "seed": seed,
        "n_queries": len(picked),
        "n_docs": len(keep),
        "distractors": distractors,
        "queries": {q: queries[q] for q in picked},
        "gold": {q: qrels[q] for q in picked},
        "doc_to_file": doc_to_file,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--out", type=Path, required=True,
                    help="Destination OUTSIDE the refmatrix tree (the watcher "
                         "would otherwise ingest the corpus into the project's "
                         "own store).")
    ap.add_argument("--queries", type=int, default=300)
    ap.add_argument("--distractors", type=int, default=1700)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    if not a.dataset.exists():
        print(f"dataset not found: {a.dataset}", file=sys.stderr)
        return 2
    resolved = a.out.resolve()
    if "claude_tools/refmatrix" in str(resolved):
        print("refusing to write inside the refmatrix tree; the watcher would "
              "ingest the corpus into the project store", file=sys.stderr)
        return 2

    m = build(a.dataset, resolved, n_queries=a.queries, seed=a.seed,
              distractors=a.distractors)
    print(f"wrote {m['n_docs']} .py files for {m['n_queries']} queries "
          f"-> {resolved/'corpus'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
