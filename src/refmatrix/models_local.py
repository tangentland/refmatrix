"""Load sentence-transformers models from the LOCAL cache only — never the network.

WHY (2026-10-07, the user: "find all external calls and remove them").
`SentenceTransformer(name)` and `CrossEncoder(name)` contact huggingface.co on
every load to check for a newer revision, even when the model is already cached
under `~/.cache/huggingface/hub`. Observed live: the hub's shared embed and
rerank workers and a pytest run each held an HTTPS connection to
huggingface.co's CloudFront (108.138.246.71/.67). That was the only implicit
outbound call in `src/`.

Every model load goes through `load_local`, which passes
`local_files_only=True`, puts the hub in offline mode even when it was imported
first (`enforce_offline`), and refuses a PARTIAL cache (`missing_files`). A
model that is not cached, or cached incomplete, is a LOUD failure that names
the one-time fetch command — never a silent download from a daemon, and never
a silently substituted tokenizer or pooling.
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


_TRUE = {"1", "ON", "YES", "TRUE"}


def enforce_offline() -> None:
    """Put the Hugging Face stack in offline mode, even if it is already imported.

    `huggingface_hub` reads `HF_HUB_OFFLINE` into `constants` ONCE, at import,
    and checks that constant before every request. Setting the env var after
    the import does nothing (ch-bsd r6 #b-2: the CodeRankEmbed retriever set it
    a few lines after `import sentence_transformers` and still made 4 connects
    to huggingface.co). Model REMOTE code (`trust_remote_code`) calls
    `cached_file` without `local_files_only`, so the constant is the only thing
    that holds there. Defaulted, never forced: an operator who set
    `HF_HUB_OFFLINE=0` explicitly keeps their value.
    """
    import sys
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None:
        constants.HF_HUB_OFFLINE = os.environ["HF_HUB_OFFLINE"].upper() in _TRUE


_TOKENIZER_ANY = ("tokenizer.json", "vocab.txt", "sentencepiece.bpe.model",
                  "spiece.model", "tokenizer.model", "vocab.json")
_WEIGHTS_ANY = ("model.safetensors", "model.safetensors.index.json",
                "pytorch_model.bin", "pytorch_model.bin.index.json")


def _snapshot_dir(model_name: str):
    """The local directory a load would read: the path itself, or the cached
    snapshot. Never a network call (`local_files_only=True`)."""
    from pathlib import Path
    p = Path(model_name).expanduser()
    if p.is_dir():
        return p
    from huggingface_hub import snapshot_download
    try:
        return Path(snapshot_download(model_name, local_files_only=True))
    except Exception as e:
        raise ModelNotCached(fetch_hint(model_name)) from e


def missing_files(kind: str, snap) -> "list[str]":
    """Files a `kind` model needs that `snap` lacks. A partial cache LOADED
    before this check (ch-bsd r6 #s-2): without its tokenizer files bge-small
    encoded at cosine 0.553 to itself, without `modules.json` it came up with
    mean pooling and no Normalize (cosine 0.952) — both silently, into the same
    Lance index."""
    import json
    missing: list[str] = []
    if not (snap / "config.json").is_file():
        missing.append("config.json")
    if not any((snap / f).is_file() for f in _WEIGHTS_ANY):
        missing.append("weights (" + " | ".join(_WEIGHTS_ANY) + ")")
    if not ((snap / "tokenizer_config.json").is_file()
            and any((snap / f).is_file() for f in _TOKENIZER_ANY)):
        missing.append("tokenizer (tokenizer_config.json + one of "
                       + " | ".join(_TOKENIZER_ANY) + ")")
    if kind == "embed":
        modules = snap / "modules.json"
        if not modules.is_file():
            missing.append("modules.json")
        else:
            for m in json.loads(modules.read_text()):
                # Normalize has no files; every module with a config does.
                if "Pooling" in m.get("type", "") and not (
                        snap / m.get("path", "") / "config.json").is_file():
                    missing.append(f"{m.get('path')}/config.json")
    return missing


def load_local(kind: str, model_name: str, device: str, *,
               trust_remote_code: bool = False):
    """`kind` is `"embed"` (SentenceTransformer) or `"rerank"` (CrossEncoder)."""
    enforce_offline()
    if kind == "embed":
        from sentence_transformers import SentenceTransformer as _cls
    elif kind == "rerank":
        from sentence_transformers import CrossEncoder as _cls
    else:
        raise ValueError(f"unknown model kind {kind!r}")
    snap = _snapshot_dir(model_name)
    missing = missing_files(kind, snap)
    if missing:
        raise ModelNotCached(
            f"model {model_name!r} is cached INCOMPLETE at {snap}: missing "
            + ", ".join(missing) + ". " + fetch_hint(model_name))
    try:
        return _cls(model_name, device=device, local_files_only=True,
                    trust_remote_code=trust_remote_code)
    except (OSError, TypeError, ValueError) as e:
        # OSError: transformers/huggingface_hub (LocalEntryNotFoundError, "not a
        # valid model identifier", ...) when the files are not cached and the
        # network is not allowed. TypeError/ValueError: a module config the
        # check above passed but the library cannot build (r6 #s-2 saw
        # `Pooling.__init__() missing 'embedding_dimension'`).
        raise ModelNotCached(f"{model_name!r} failed to load from the local "
                             f"cache ({type(e).__name__}: {e}). "
                             + fetch_hint(model_name)) from e
