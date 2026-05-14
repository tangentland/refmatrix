"""Convert GraphCodeBERT CSN python output to BEIR layout.

Reads <src>/codebase.jsonl + <src>/test.jsonl and writes:
    <dest>/corpus.jsonl
    <dest>/queries.jsonl
    <dest>/qrels/test.tsv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, required=True, help="dir with codebase.jsonl + test.jsonl")
    p.add_argument("--dest", type=Path, required=True, help="output BEIR dir")
    args = p.parse_args()

    (args.dest / "qrels").mkdir(parents=True, exist_ok=True)

    url2id: dict[str, str] = {}
    with (args.src / "codebase.jsonl").open() as fin, \
         (args.dest / "corpus.jsonl").open("w") as fout:
        for i, line in enumerate(fin):
            line = line.strip()
            if not line:
                continue
            js = json.loads(line)
            url = js.get("url")
            if not url:
                continue
            did = f"{i}_code"
            url2id[url] = did
            fout.write(json.dumps({
                "_id": did,
                "text": js.get("original_string") or js.get("code") or "",
                "title": " ".join(js.get("docstring_tokens") or []),
                "metadata": {"path": js.get("path"), "func_name": js.get("func_name")},
            }) + "\n")

    n_queries = 0
    n_qrels = 0
    with (args.src / "test.jsonl").open() as fin, \
         (args.dest / "queries.jsonl").open("w") as fq, \
         (args.dest / "qrels" / "test.tsv").open("w") as fqr:
        fqr.write("query-id\tcorpus-id\tscore\n")
        for i, line in enumerate(fin):
            line = line.strip()
            if not line:
                continue
            js = json.loads(line)
            url = js.get("url")
            if url not in url2id:
                continue
            qid = f"{i}_query"
            doc = " ".join(js.get("docstring_tokens") or []) or js.get("docstring") or ""
            fq.write(json.dumps({"_id": qid, "text": doc, "metadata": {}}) + "\n")
            fqr.write(f"{qid}\t{url2id[url]}\t1\n")
            n_queries += 1
            n_qrels += 1

    print(f"wrote {len(url2id)} docs, {n_queries} queries, {n_qrels} qrels -> {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
