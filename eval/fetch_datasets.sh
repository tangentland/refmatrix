#!/usr/bin/env bash
# Fetch BEIR-format CodeSearchNet (Python only) for the rmx vs CodeRankEmbed eval.
#
# Source: same pipeline cornstack uses — GraphCodeBERT's CSN release, then
# convert to BEIR shape (corpus.jsonl / queries.jsonl / qrels/test.tsv).
#
# Output: eval/datasets/csn_python/
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/datasets"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$DEST"

if [[ -d "$DEST/csn_python" ]]; then
  echo "csn_python already present at $DEST/csn_python — skipping fetch."
  exit 0
fi

echo "==> downloading GraphCodeBERT CSN bundle"
cd "$WORK"
curl -L -o dataset.zip \
  https://github.com/microsoft/CodeBERT/raw/master/GraphCodeBERT/codesearch/dataset.zip
unzip -q dataset.zip
mv dataset CSN
echo "==> running CSN run.sh (Python language only)"
cd CSN
# run.sh prepares all languages; we only need python. Run and ignore non-python noise.
bash run.sh || true

echo "==> converting to BEIR format (csn_python)"
python3 - <<'PY'
import json, os
from pathlib import Path

src = Path("python")
out = Path(os.environ["DEST"]) / "csn_python"
(out / "qrels").mkdir(parents=True, exist_ok=True)

# CSN files: codebase.jsonl (docs), test.jsonl (queries). Pair by url.
def load(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]

code = load(src / "codebase.jsonl")
test = load(src / "test.jsonl")

url2id = {}
with open(out / "corpus.jsonl", "w") as f:
    for i, doc in enumerate(code):
        url = doc.get("url") or doc.get("path") or f"doc_{i}"
        url2id[url] = f"{i}_code"
        f.write(json.dumps({
            "_id": url2id[url],
            "text": doc.get("code") or doc.get("function") or "",
            "title": doc.get("docstring") or doc.get("title") or "",
            "metadata": {},
        }) + "\n")

with open(out / "queries.jsonl", "w") as f, \
     open(out / "qrels" / "test.tsv", "w") as q:
    q.write("query-id\tcorpus-id\tscore\n")
    for i, ex in enumerate(test):
        url = ex.get("url") or ex.get("path")
        if url not in url2id:
            continue
        qid = f"{i}_query"
        nl = ex.get("docstring") or ex.get("nl") or ex.get("query") or ""
        f.write(json.dumps({"_id": qid, "text": nl, "metadata": {}}) + "\n")
        q.write(f"{qid}\t{url2id[url]}\t1\n")

print(f"wrote {out}")
PY

echo "==> done. dataset at $DEST/csn_python"
