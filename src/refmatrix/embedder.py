"""Dense embedding pipeline for refmatrix.

Lazy-loaded sentence-transformers model + per-kind text extractors.
Soft dependency: requires the [dense] extra (sentence-transformers).
Importing this module raises ImportError without the extra; callers
should catch and degrade gracefully.

Default model: `BAAI/bge-small-en-v1.5` — 384-dim, ~134 MB on disk,
CPU-friendly, MTEB-strong for code+docs+general text.

Per-kind text extractors live here, not in vectors.py, so the
embedder is the single place that knows how a row becomes a string.
Phase B memory entities will add an extractor for kind='memory' that
joins MemoryContent.content + tags + type into one string.
"""
from __future__ import annotations

import os
from typing import Iterable, Sequence

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384

# Hard cap on the text length we feed the embedder. Most ST models
# truncate to 512 tokens anyway; bounding upfront keeps the per-row
# memory footprint predictable when an extractor returns a giant blob
# (e.g. a long markdown file).
MAX_INPUT_CHARS = 4096


class Embedder:
    """Lazy-loaded sentence-transformers wrapper.

    Model is loaded on first `embed_texts` call so importing the
    module is cheap. Cached afterwards on the instance.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = (
            model_name or os.environ.get("RMX_EMBED_MODEL") or DEFAULT_MODEL
        )
        self._model = None
        # Cache the model's output dim once we know it. For the default
        # bge-small-en-v1.5 this is 384; users with a different model
        # discover the real value at first encode.
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        """Return the model's output dimension. Loads the model if not
        already loaded — cheap, since we'd need it for any encode."""
        if self._dim is not None:
            return self._dim
        self._load()
        # sentence-transformers 5.x renamed get_sentence_embedding_dimension
        # to get_embedding_dimension. Prefer the new name when present.
        if hasattr(self._model, "get_embedding_dimension"):
            d = int(self._model.get_embedding_dimension())
        else:
            d = int(self._model.get_sentence_embedding_dimension())
        self._dim = d
        return d

    def _load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        # `cache_folder` honors HF_HOME / SENTENCE_TRANSFORMERS_HOME so
        # downloads land in the standard locations. CPU device is the
        # safe default; users with MPS / CUDA can set RMX_EMBED_DEVICE.
        device = os.environ.get("RMX_EMBED_DEVICE", "cpu")
        self._model = SentenceTransformer(self.model_name, device=device)

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """Encode a batch of texts. Returns float32 (N, dim) ndarray.

        Empty input → (0, dim) array. Texts are truncated to
        `MAX_INPUT_CHARS` characters before encoding. Vectors are
        L2-normalized so downstream callers can use cosine similarity
        by taking dot products.
        """
        self._load()
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        truncated = [(t or "")[:MAX_INPUT_CHARS] for t in texts]
        vecs = self._model.encode(
            truncated,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(vecs, dtype="float32")


# ---------- per-kind text extractors -----------------------------------


def extract_text_for_entity(
    store,
    entity_id: int,
    kind: str,
) -> str:
    """Build the text that represents this entity for embedding.

    Dispatches on `kind`. Returns an empty string when nothing useful
    is available; the caller should skip empty-text rows so we don't
    burn a vector slot on a noop embedding (every model maps "" to
    the same point and that point becomes a near-neighbor for any
    query, which is the wrong behavior).
    """
    if kind == "memory":
        return _extract_memory(store, entity_id)
    if kind == "code":
        return _extract_code(store, entity_id)
    if kind == "doc":
        return _extract_doc(store, entity_id)
    if kind == "concept":
        return _extract_concept(store, entity_id)
    return ""


def _row(store, entity_id: int):
    con = store._connect()
    return con.execute(
        "SELECT id, kind, name, path, tldr, canonical_name "
        "FROM entities WHERE id = ?",
        [entity_id],
    ).fetchone()


def _extract_memory(store, entity_id: int) -> str:
    """Phase B memory entities. Joins MemoryContent.content +
    type + tags into one string. Phase A stub: returns the entity
    name when the memory_content sidecar isn't present yet so
    A4 can land before B."""
    con = store._connect()
    try:
        r = con.execute(
            "SELECT content, mtype, tags FROM memory_content WHERE entity_id = ?",
            [entity_id],
        ).fetchone()
        if r is not None:
            content, mtype, tags = r[0], r[1] or "", r[2] or ""
            return f"[{mtype}] {content}\n{tags}".strip()
    except Exception:
        # memory_content table doesn't exist yet (Phase A only).
        pass
    row = _row(store, entity_id)
    return (row["name"] if row is not None else "") or ""


def _extract_code(store, entity_id: int) -> str:
    """code: signature + docstring when we have a tldr; otherwise the
    entity name. The tldr column stores the LLM-condensed summary
    already, so reusing it is a strong default."""
    row = _row(store, entity_id)
    if row is None:
        return ""
    parts: list[str] = []
    if row["name"]:
        parts.append(row["name"])
    if row["tldr"]:
        parts.append(row["tldr"])
    return "\n".join(parts).strip()


def _extract_doc(store, entity_id: int) -> str:
    """doc: tldr (if present) plus the entity name. Avoids reading
    the source file synchronously — embed walk over thousands of
    files would otherwise be IO-heavy."""
    row = _row(store, entity_id)
    if row is None:
        return ""
    parts: list[str] = []
    if row["name"]:
        parts.append(row["name"])
    if row["tldr"]:
        parts.append(row["tldr"])
    return "\n".join(parts).strip()


def _extract_concept(store, entity_id: int) -> str:
    """concept: name + canonical_name (identifier variants). The
    canonical form often disambiguates: 'parseURL' vs 'parse_url'
    both canonicalize to 'parse_url' so the embedding lands at the
    same point."""
    row = _row(store, entity_id)
    if row is None:
        return ""
    name = row["name"] or ""
    canon = row["canonical_name"] or ""
    if canon and canon != name:
        return f"{name} {canon}"
    return name


def extract_batch(
    store, rows: Iterable[tuple[int, str, str]]
) -> list[tuple[int, str, str]]:
    """Given `(entity_id, kind, name)` triples, return
    `(entity_id, kind, text)` triples with empty-text rows filtered
    out. The CLI uses this to skip dead embed slots up front."""
    out: list[tuple[int, str, str]] = []
    for eid, kind, _name in rows:
        text = extract_text_for_entity(store, eid, kind)
        if text:
            out.append((eid, kind, text))
    return out
