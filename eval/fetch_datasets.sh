#!/usr/bin/env bash
# Fetch BEIR-format CodeSearchNet splits for the rmx eval.
#
# Pulls per-language Parquet files directly from the HuggingFace mirror of
# CodeSearchNet (code-search-net/code_search_net) and converts each requested
# language's test split to BEIR shape under
# eval/datasets/csn_<lang>/{corpus.jsonl, queries.jsonl, qrels/test.tsv}.
#
# History note: csn_python in this repo was originally produced via
# GraphCodeBERT's `dataset.zip` + `run.sh` pipeline, which downloads ALL six
# CSN languages plus model checkpoints. The CodeSearchNet S3 bucket
# (s3.amazonaws.com/code-search-net/...) now returns 403, so we use the HF
# mirror instead — per-language Parquet, no shell-script Russian roulette.
# Existing csn_python is preserved by the per-language skip-if-present check.
#
# Languages controlled by LANGS env var (default: "python javascript").
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/datasets"
LANGS="${LANGS:-python javascript}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Pick a python that has pyarrow. The repo's eval venv has it; system python3
# usually doesn't. PYTHON env var overrides.
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "${HERE}/../.venv-eval/bin/python" ]]; then
    PYTHON="${HERE}/../.venv-eval/bin/python"
  else
    PYTHON="python3"
  fi
fi
echo "==> using python: $PYTHON"

mkdir -p "$DEST"

# HuggingFace dataset layout: code-search-net/code_search_net/<lang>/<split>-00000-of-00001.parquet
HF_BASE_URL="https://huggingface.co/datasets/code-search-net/code_search_net/resolve/main"

# TypeScript falls back to Shuu12121's tree-sitter-filtered mirror — CSN itself
# never shipped a TS split. Schema is compatible (code, docstring, func_name,
# url) so the BEIR conversion below works after a column-name remap.
TS_PARQUET_URL="https://huggingface.co/datasets/Shuu12121/typescript-treesitter-filtered-datasetsV2/resolve/main/data/test-00000-of-00001.parquet"

for lang in $LANGS; do
  out_dir="$DEST/csn_${lang}"
  if [[ -d "$out_dir" ]]; then
    echo "==> csn_${lang} already present at $out_dir — skipping"
    continue
  fi

  parquet_path="$WORK/${lang}-test.parquet"
  if [[ "$lang" == "typescript" ]]; then
    parquet_url="$TS_PARQUET_URL"
  else
    parquet_url="$HF_BASE_URL/${lang}/test-00000-of-00001.parquet"
  fi
  echo "==> downloading csn_${lang} test parquet ($parquet_url)"
  curl -L --fail -o "$parquet_path" "$parquet_url"

  echo "==> converting csn_${lang} → BEIR format"
  LANG="$lang" DEST="$DEST" PARQUET="$parquet_path" "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

import pyarrow.parquet as pq

lang = os.environ["LANG"]
parquet_path = Path(os.environ["PARQUET"])
out = Path(os.environ["DEST"]) / f"csn_{lang}"
(out / "qrels").mkdir(parents=True, exist_ok=True)

tbl = pq.read_table(parquet_path)
# CSN columns (Python/JS): repository_name, func_path_in_repository,
# func_name, whole_func_string, func_code_string, func_code_tokens,
# language, func_documentation_string, func_documentation_tokens,
# split_name, func_code_url.
# Shuu12121 TS mirror columns: code, docstring, func_name, language,
# repo, path, url, license. The col-fallback chain below covers both.
def col(name):
    return tbl.column(name).to_pylist() if name in tbl.column_names else [None] * tbl.num_rows

def first_present(*names):
    """Return the column whose name appears in the table, else a column
    of Nones the same length as the table."""
    for n in names:
        if n in tbl.column_names:
            return tbl.column(n).to_pylist()
    return [None] * tbl.num_rows

codes = first_present("whole_func_string", "func_code_string", "code")
docs = first_present("func_documentation_string", "docstring")
urls = first_present("func_code_url", "url")

n_corpus = 0
n_queries = 0
with open(out / "corpus.jsonl", "w") as f_corp, \
     open(out / "queries.jsonl", "w") as f_q, \
     open(out / "qrels" / "test.tsv", "w") as f_qrel:
    f_qrel.write("query-id\tcorpus-id\tscore\n")
    for i, (code, docstring, url) in enumerate(zip(codes, docs, urls)):
        if not code:
            continue
        cid = f"{i}_code"
        f_corp.write(json.dumps({
            "_id": cid,
            "text": code,
            "title": docstring or "",
            "metadata": {"lang": lang, "url": url or ""},
        }) + "\n")
        n_corpus += 1

        if docstring and docstring.strip():
            qid = f"{i}_query"
            f_q.write(json.dumps({
                "_id": qid,
                "text": docstring,
                "metadata": {"lang": lang},
            }) + "\n")
            f_qrel.write(f"{qid}\t{cid}\t1\n")
            n_queries += 1

print(f"  wrote {n_corpus} corpus rows, {n_queries} queries → {out}")
PY
done

echo "==> done. datasets under $DEST"
