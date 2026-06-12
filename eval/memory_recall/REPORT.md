# Memory-recall fusion eval (viascope, real queries)

- Queries judged (≥1 relevant): **79** / 80 pooled
- Judge: **4 parallel Claude subagents** (not the score.py Haiku path), graded
  0/1/2 over the 1103-pair pool; relevance = r>0. Calibrated to reserve 2 for
  direct on-topic hits (most pooled items are dense-near session cards).
- Go/no-go: fused must beat max(dense, symbolic) MRR@10 = **0.8477**

| method | MRR@10 | Recall@1 | Recall@5 | Recall@10 | nDCG@10 |
|---|---|---|---|---|---|
| dense | 0.8477 | 0.1264 | 0.4315 | 0.6459 | 0.6013 |
| symbolic | 0.7089 | 0.1157 | 0.2987 | 0.3627 | 0.4133 |
| fused@10 | 0.7937 | 0.1024 | 0.4885 | 0.7885 | 0.6967 |
| fused@30 | 0.7682 | 0.0961 | 0.4774 | 0.7794 | 0.6769 |
| fused@60 | 0.7658 | 0.0961 | 0.4774 | 0.7794 | 0.6765 |
| fused@100 | 0.7668 | 0.0961 | 0.4774 | 0.7794 | 0.6767 |

**Best fused:** rrf_k=10 at MRR@10=0.7937 (vs 0.8477 best single). **Verdict on the
MRR@10 go/no-go: KEEP `--fuse` default-off.**

But the metric tells a split story worth keeping `--fuse` as a documented opt-in:
fusion *loses* on MRR@10 (top-1 precision, −0.054) yet *wins* on Recall@10
(0.7885 vs 0.6459, **+0.143**), Recall@5 (+0.057), and nDCG@10 (0.6967 vs 0.6013,
**+0.095**). Dense puts the single best memory at rank 1 more often; fusion pulls
**more** relevant memories into the top-k and orders them better. So fusion is the
right call when a caller wants the best *set* of memories (multi-result context
injection), and dense is right when it wants the single most-relevant hit — which
is why default-off + `--fuse` opt-in is the correct shipped shape. A future flip
would be justified only for a recall-oriented surface, not for top-1 lookup.
