"""BEIR-format dataset loader.

The CodeRankEmbed reference eval uses BEIR layout:
    corpus.jsonl       one doc per line: {_id, text, title?, metadata?}
    queries.jsonl      one query per line: {_id, text, metadata?}
    qrels/test.tsv     header row then `query-id\tcorpus-id\tscore` rows

Same loader works for CSN per-language splits (csn_python, csn_java, ...)
and any CoIR task laid out in BEIR form.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BeirDataset:
    name: str
    corpus: dict[str, dict]
    queries: dict[str, str]
    qrels: dict[str, dict[str, int]]

    def __repr__(self) -> str:
        return (
            f"BeirDataset(name={self.name!r}, "
            f"corpus={len(self.corpus)}, queries={len(self.queries)}, "
            f"qrels={sum(len(v) for v in self.qrels.values())})"
        )


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_beir(root: Path | str, name: str | None = None) -> BeirDataset:
    root = Path(root)
    corpus = {
        d["_id"]: {"text": d.get("text", ""), "title": d.get("title", "")}
        for d in _read_jsonl(root / "corpus.jsonl")
    }
    queries = {q["_id"]: q.get("text", "") for q in _read_jsonl(root / "queries.jsonl")}

    qrels: dict[str, dict[str, int]] = {}
    qrels_path = root / "qrels" / "test.tsv"
    with qrels_path.open() as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        # Some BEIR dumps omit the header; sniff first row.
        if header and header[0].lower() not in {"query-id", "qid"}:
            rows = [header] + list(reader)
        else:
            rows = list(reader)
        for row in rows:
            if len(row) < 3:
                continue
            qid, did, score = row[0], row[1], row[2]
            try:
                s = int(score)
            except ValueError:
                continue
            qrels.setdefault(qid, {})[did] = s

    return BeirDataset(
        name=name or root.name,
        corpus=corpus,
        queries=queries,
        qrels=qrels,
    )
