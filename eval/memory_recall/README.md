# Memory-recall fusion eval

Decides whether `rmx memory recall --fuse` (dense ⊕ content_rank RRF, shipped
in d8efc53) should flip **default-on**. The round-4 in-process check on the
63-memory refmatrix store was muted/mixed (dense already nailed rare-keyword
targets; RRF even nudged one down 1→2). This harness re-runs the question on
**real viascope recall traffic** with **LLM-judged** relevance — a trust set
grounded in usage, not synthetic.

## Why this shape

- **Queries are real.** The recall hook fires `memory recall --stdin-json`, so
  the query lives in stdin and never reaches `cli.log`. But the same
  UserPromptSubmit prompt is logged by `scan-prompt` as a `kind="scan"`
  `query.log` row. Those bodies are the real queries the memory system serves.
- **No logged labels exist.** Nothing records which memory "won" — there is no
  click/use signal. So relevance is *judged*, TREC-pooling style: pool dense ∪
  symbolic top-k per query, then an LLM grades each candidate.
- **Synthetic is curve-shape only.** Title-derived synthetic queries flatter
  the lexical side; this harness uses the viascope judged set for the go/no-go.

## Pipeline

```
mine_queries.py   query.log scan bodies ─filter─▶ queries.jsonl   (stdlib only)
pool_candidates.py dense ∪ symbolic top-k ──────▶ candidates.jsonl (deploy venv: lance+ST)
score.py          LLM-judge ▶ qrels.tsv ; fuse ▶ REPORT.md         (anthropic + refmatrix)
```

## Run

```bash
ROOT=/Users/tholley/github/atollogy/bdep/viascope
DEV=/Users/tholley/claude_tools/refmatrix/src
PY=/Users/tholley/refmatrix/.venv/bin/python      # deploy venv has the dense extra + 0.10.0 code

# 1. mine real queries (no deps, read-only on query.log)
python mine_queries.py --root "$ROOT" --limit 80 --out queries.jsonl

# 2. pool candidates (read-only on the memory partition; needs lance + embedder)
PYTHONPATH=$DEV "$PY" pool_candidates.py --root "$ROOT" \
    --partition memory-viascope --k 10 --queries queries.jsonl --out candidates.jsonl

# 3. judge + score (needs `pip install anthropic` + ANTHROPIC_API_KEY)
PYTHONPATH=$DEV "$PY" score.py --candidates candidates.jsonl --qrels qrels.tsv --out REPORT.md
#    re-score without re-paying the judge:
PYTHONPATH=$DEV "$PY" score.py --no-judge
```

`qrels.tsv` is the cache — judging is incremental and append-only, so an
interrupt keeps prior labels and a re-run only judges new pairs.

## Reading the result

`REPORT.md` tables MRR@10 / Recall@1,5,10 / nDCG@10 for `dense`, `symbolic`,
and `fused@{10,30,60,100}`. **Verdict = FLIP** when the best `fused@k` beats
`max(dense, symbolic)` on MRR@10 — that k is the value to ship. Otherwise KEEP
default-off (round-4's decision stands).

## Scope / caveats

- `eval/` only — reads the deployed store **read-only**, touches no
  deploy-path code. The viascope daemon is not required (in-process reads).
- Targets `memory-viascope` (the partition production recall defaults to, ~130
  memories). viascope also has memories in the `viascope` (272) and
  `sessions-viascope` (149) partitions; recall doesn't query those by default.
- Judge model `claude-haiku-4-5`; ~N_queries × ~20 candidate calls (cheap, but
  it IS a paid API + needs the key).
