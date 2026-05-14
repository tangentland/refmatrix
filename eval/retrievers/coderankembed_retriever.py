"""CodeRankEmbed retriever adapter.

Mirrors cornstack/src/evaluations/eval_csn.py: SentenceTransformer encodes
queries (with the model's prescribed prefix) and corpus, then cosine ranking.

Heavy imports are deferred to construction so the eval module can be loaded
without torch/sentence-transformers installed.
"""
from __future__ import annotations

import numpy as np


QUERY_PREFIX = "Represent this query for searching relevant code"


class CodeRankEmbedRetriever:
    def __init__(
        self,
        *,
        model_name: str = "cornstack/CodeRankEmbed",
        device: str = "cpu",
        batch_size: int = 32,
        bf16: bool = False,
        max_seq_length: int = 512,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "CodeRankEmbed eval requires sentence-transformers and torch. "
                "Install with: pip install -r eval/requirements.txt"
            ) from exc

        model = SentenceTransformer(model_name, trust_remote_code=True).to(device)
        model.max_seq_length = max_seq_length
        if bf16:
            import torch
            model = model.to(torch.bfloat16)
        self.model = model
        self.batch_size = batch_size

        self._corpus_ids: list[str] = []
        self._corpus_vecs: np.ndarray | None = None

    def ingest_corpus(self, corpus: dict[str, dict]) -> None:
        ids: list[str] = []
        texts: list[str] = []
        for did, doc in corpus.items():
            ids.append(did)
            t = doc.get("title", "")
            x = doc.get("text", "")
            texts.append(f"{t}\n{x}".strip() if t else x)
        self._corpus_ids = ids
        self._corpus_vecs = self.model.encode(
            texts, show_progress_bar=True, batch_size=self.batch_size,
            normalize_embeddings=True,
        )

    def retrieve(self, query: str, top_k: int = 1000) -> dict[str, float]:
        if self._corpus_vecs is None:
            raise RuntimeError("ingest_corpus first")
        q = f"{QUERY_PREFIX}: {query}"
        qv = self.model.encode([q], normalize_embeddings=True)
        scores = (qv @ self._corpus_vecs.T)[0]
        top = np.argsort(-scores)[:top_k]
        return {self._corpus_ids[i]: float(scores[i]) for i in top}

    def run(self, queries: dict[str, str], top_k: int = 1000) -> dict[str, dict[str, float]]:
        if self._corpus_vecs is None:
            raise RuntimeError("ingest_corpus first")
        qids = list(queries.keys())
        qtexts = [f"{QUERY_PREFIX}: {queries[q]}" for q in qids]
        qvecs = self.model.encode(
            qtexts, show_progress_bar=True, batch_size=self.batch_size,
            normalize_embeddings=True,
        )
        scores = qvecs @ self._corpus_vecs.T  # (n_q, n_c)
        out: dict[str, dict[str, float]] = {}
        for i, qid in enumerate(qids):
            row = scores[i]
            top = np.argsort(-row)[:top_k]
            out[qid] = {self._corpus_ids[j]: float(row[j]) for j in top}
        return out
