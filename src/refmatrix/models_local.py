"""Load sentence-transformers models from the LOCAL cache only — never the network.

WHY (2026-10-07, the user: "find all external calls and remove them").
`SentenceTransformer(name)` and `CrossEncoder(name)` contact huggingface.co on
every load to check for a newer revision, even when the model is already cached
under `~/.cache/huggingface/hub`. Observed live: the hub's shared embed and
rerank workers and a pytest run each held an HTTPS connection to
huggingface.co's CloudFront (108.138.246.71/.67). That was the only implicit
outbound call in `src/`.

Every model load goes through `load_local`, which passes
`local_files_only=True` and defaults `HF_HUB_OFFLINE` for anything the library
reaches transitively. A model that is not cached is a LOUD failure that names
the one-time fetch command — never a silent download from a daemon.
"""
from __future__ import annotations

import os


class ModelNotCached(RuntimeError):
    """The requested model is not in the local Hugging Face cache."""


def fetch_hint(model_name: str) -> str:
    return (f"model {model_name!r} is not in the local Hugging Face cache, and "
            f"refmatrix never downloads at load time. Fetch it once, "
            f"deliberately: `hf download {model_name}` "
            f"(older hubs: `huggingface-cli download {model_name}`)")


def load_local(kind: str, model_name: str, device: str):
    """`kind` is `"embed"` (SentenceTransformer) or `"rerank"` (CrossEncoder)."""
    # Transitive hub calls (tokenizer/config resolution) honour this. Only
    # DEFAULTED: an operator who set it explicitly keeps their value, and
    # `local_files_only` below holds either way.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    if kind == "embed":
        from sentence_transformers import SentenceTransformer as _cls
    elif kind == "rerank":
        from sentence_transformers import CrossEncoder as _cls
    else:
        raise ValueError(f"unknown model kind {kind!r}")
    try:
        return _cls(model_name, device=device, local_files_only=True)
    except OSError as e:
        # transformers/huggingface_hub raise OSError subclasses
        # (LocalEntryNotFoundError, "not a valid model identifier", ...) when
        # the files are not cached and the network is not allowed.
        raise ModelNotCached(fetch_hint(model_name)) from e
