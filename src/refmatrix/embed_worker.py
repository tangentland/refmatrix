"""Model worker process. Not imported by the daemon — spawned by it.

Run as `python -m refmatrix.embed_worker --role embed|rerank`. Reads
request frames from stdin, writes response frames to stdout, exits on EOF
(which is how the parent says "die" — see `subproc.WorkerClient.close`).

Roles:
    embed   — sentence-transformers bi-encoder. Ops: info, embed.
    rerank  — sentence-transformers CrossEncoder. Ops: info, rerank.

Everything the daemon needs from a model is text-in / numbers-out, so
nothing else crosses the process boundary. In particular the per-kind
text extractors in `embedder.py` read DuckDB and stay in the daemon —
this process never opens a store, never sees a catalog, and holds no
locks. If it dies, it dies alone.
"""
from __future__ import annotations

import argparse
import os
import sys

# Protect the protocol channel BEFORE importing anything that might print.
# torch / transformers / sentence-transformers all write to stdout under
# some configurations, and a single stray byte desynchronizes every frame
# that follows. Dup fd 1 to a private handle, then point fd 1 at stderr so
# library output lands in the daemon log instead of the pipe.
_OUT_FD = os.dup(1)
os.dup2(2, 1)
sys.stdout = sys.stderr

# Same treatment for stdin: a library that reads fd 0 would eat frames.
_IN_FD = os.dup(0)
_devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(_devnull, 0)
os.close(_devnull)

CHAN_OUT = os.fdopen(_OUT_FD, "wb")
CHAN_IN = os.fdopen(_IN_FD, "rb")

from refmatrix.subproc import recv_frame, send_frame  # noqa: E402


class _EmbedRole:
    """Bi-encoder. Delegates to the same `embedder.Embedder` the
    in-process path uses, so the two paths cannot drift on model
    selection, truncation, or normalization."""

    name = "embed"

    def __init__(self, model: str | None):
        from refmatrix.embedder import Embedder
        self._emb = Embedder(model_name=model)

    def info(self) -> dict:
        return {"model": self._emb.model_name, "dim": self._emb.dim}

    def handle(self, op: str, req: dict, blob: bytes):
        if op != "embed":
            raise ValueError(f"unknown op for role=embed: {op}")
        texts = req.get("texts") or []
        vecs = self._emb.embed_texts(texts)
        # float32 C-contiguous — the client reinterprets with np.frombuffer
        # and reshapes, so shape travels in the header, not the payload.
        import numpy as np
        vecs = np.ascontiguousarray(vecs, dtype="float32")
        return ({"n": int(vecs.shape[0]), "dim": int(self._emb.dim)},
                vecs.tobytes())


class _RerankRole:
    """Cross-encoder. Unlike the bi-encoder it scores (query, doc) pairs
    jointly, which is why it can fix an ordering the bi-encoder got wrong
    — and why it can only ever run over a shortlist."""

    name = "rerank"

    def __init__(self, model: str | None):
        from refmatrix.reranker import Reranker
        self._rr = Reranker(model_name=model)

    def info(self) -> dict:
        # Force the load here, the way the embed role's `dim` does. The
        # daemon's warmup calls info() and nothing else; without this the
        # worker spawns "warm" in 0.1s and the FIRST real recall still pays
        # the model load -- which is the exact failure `_start_embedder_warmup`
        # was written to prevent.
        self._rr._load()
        return {"model": self._rr.model_name}

    def handle(self, op: str, req: dict, blob: bytes):
        if op != "rerank":
            raise ValueError(f"unknown op for role=rerank: {op}")
        query = req.get("query") or ""
        docs = req.get("docs") or []
        scores = self._rr.score(query, docs)
        return ({"scores": [float(s) for s in scores]}, None)


ROLES = {"embed": _EmbedRole, "rerank": _RerankRole}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="refmatrix.embed_worker")
    ap.add_argument("--role", choices=sorted(ROLES), required=True)
    ap.add_argument("--model", default=None)
    ns = ap.parse_args(argv)

    model = ns.model or os.environ.get("RMX_WORKER_MODEL") or None
    # Built lazily so a model-load failure comes back as a frame the parent
    # can surface, rather than a silent nonzero exit during startup.
    role = None

    while True:
        try:
            req, blob = recv_frame(CHAN_IN)
        except EOFError:
            return 0                      # parent closed stdin: clean exit
        except Exception as exc:
            print(f"worker: bad frame: {exc!r}", file=sys.stderr)
            return 1

        op = req.pop("op", "")
        try:
            if op == "ping" and role is None:
                # Liveness without paying the model load.
                send_frame(CHAN_OUT, {"ok": True})
                continue
            if role is None:
                role = ROLES[ns.role](model)
            if op == "ping":
                send_frame(CHAN_OUT, {"ok": True})
                continue
            if op == "info":
                # Report the interpreter too: a worker on the wrong python
                # fails as a missing dependency, which reads like a broken
                # install rather than a wrong venv. The parent compares.
                send_frame(CHAN_OUT, {
                    "ok": True,
                    "python": sys.executable,
                    "prefix": sys.prefix,
                    **role.info(),
                })
                continue
            hdr, out_blob = role.handle(op, req, blob)
            send_frame(CHAN_OUT, {"ok": True, **hdr}, out_blob)
        except Exception as exc:
            # Report and keep serving. A bad request (unknown op, model
            # mismatch) should not cost the parent a respawn; a real crash
            # exits on its own and the parent respawns from that.
            print(f"worker: op={op} failed: {exc!r}", file=sys.stderr)
            try:
                send_frame(
                    CHAN_OUT,
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                )
            except Exception:
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
