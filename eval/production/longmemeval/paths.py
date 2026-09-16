"""Where the LongMemEval DATA lives — deliberately not in the repo.

The harness code (paths.py, prepare.py, ingest.py, run.py) is refmatrix source
and stays under version control. Everything it operates on — a 278MB upstream
blob, 19,829 generated session transcripts, the rmx store built over them — is
not, and must not sit inside a tree the refmatrix daemon watches.

That is not a tidiness preference; it happened. The watcher ingested MemAware's
`corpus/` the moment prepare.py wrote it, and benchmark session ids started
surfacing in `scan-prompt` output for this project. `.gitignore` does not stop a
watcher, and `.refmatrix_ignore` only helps if it exists BEFORE the files land.
Putting the data on a separate volume removes the failure mode instead of
guarding against it. Same reasoning, same shape, as `eval/memaware/paths.py`.

Override with LONGMEMEVAL_DATA. Falls back to ./data if the volume is absent,
so a checkout on another machine still works.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
_DEFAULT_VOLUME = Path("/Volumes/littlebig/longmemeval")

DATA = Path(
    os.environ.get("LONGMEMEVAL_DATA")
    or (_DEFAULT_VOLUME if _DEFAULT_VOLUME.parent.is_dir() else HERE / "data")
)

UPSTREAM = DATA / "upstream"
CORPUS = DATA / "corpus"
SUBSETS = DATA / "subsets"
RESULTS = DATA / "results"
QRELS = DATA / "qrels.json"
HAYSTACKS = DATA / "haystacks.json"
QUESTIONS = DATA / "questions.json"

# HuggingFace ships the splits as extensionless JSON blobs on one dataset repo.
HF_REPO = "xiaowu0162/longmemeval"
SPLITS = {"s": "longmemeval_s", "m": "longmemeval_m", "oracle": "longmemeval_oracle"}

# Store root sits DIRECTLY under DATA so the partition name derives from the
# parent dir basename — `longmemeval`. MemAware's first layout nested it as
# `store/.refmatrix`, which named the project "store" and sent
# `embed --kinds memory` to a `memory-store` partition that held nothing.
STORE_ROOT = DATA / ".refmatrix"
PARTITION = "longmemeval"


def rmx_env(base: "dict | None" = None, *, log: bool = True) -> dict:
    """Environment that pins rmx to the benchmark store.

    `log=False` sets RMX_LOG=0, disabling the append-only facts.log. Safe here
    and only here: facts.log exists so a catalog can be rebuilt by replay, and
    this store is rebuildable from corpus/ in one command. Worth turning off for
    the build — the log writes one JSON line per link, and a corpus this size
    emits enough of them to dominate the ingest once the SQL inserts are
    batched (measured on MemAware: 9m22s CPU inside a 23m34s wall clock).
    """
    e = dict(base if base is not None else os.environ)
    e["REFMATRIX_ROOT"] = str(STORE_ROOT)
    e["RMX_PARTITION"] = PARTITION
    e["RMX_INVOCATION_SOURCE"] = "eval"
    if not log:
        e["RMX_LOG"] = "0"
    return e
