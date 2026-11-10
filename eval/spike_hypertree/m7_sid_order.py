"""M7 (hypertree spike 2026-10-20): does ORDER pay at sentence (`sid`) granularity?

ADR-0004's open item; the 2026-10-07 spike found order irrelevant at ENTITY grain (< 0.75%)
because a store's entities fit in one roaring chunk. This builds the sentence layer the stores
do not hold yet and compares per-term roaring bytes under different sid numberings.

Read-only. Paths come from the COPY of the store snapshot; source files are READ from the
project tree; nothing is written except the results JSON.

Sentence layer (Dewey order = document order within path-sorted files):
  file ▸ section (markdown heading / top-level def|class|CREATE) ▸ paragraph (blank-line block)
  ▸ sentence (the 2026-10-06 loc-coloc splitter: `(?<=[.!?])\\s+|\\n+`, so a code line is a
  sentence).
Terms per sentence: production keyword tokenizer (`ingest._WORD_RE`, lowercased, minus
`_DOCSTRING_STOP`) as unigrams, plus underscore-joined bi/trigrams, KEPT only when the term is a
`mentions` concept in the store's code partition (namespace stripped) — i.e. the vocabulary the
store already indexes.

Numberings compared (sids 0..N-1, 32-bit):
  dewey          path-sorted files, document order inside each file
  random         global random permutation (control)          [seed common.SEED]
  file_rand_in   path-sorted files, random order inside each file
  rand_file_doc  random file order, document order inside each file
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import duckdb
from pyroaring import BitMap

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, STORES, copy_db  # noqa: E402
from refmatrix.ingest import _DOCSTRING_STOP, _WORD_RE  # noqa: E402

SENT = re.compile(r"(?<=[.!?])\s+|\n+")
PARA = re.compile(r"\n\s*\n")
MD_HEAD = re.compile(r"^#{1,6}\s", re.M)
CODE_HEAD = re.compile(r"^(?:def |class |async def |CREATE |create )", re.M)
NS = ("keyword/", "phrase/", "query/", "gf/")
MAX_BYTES = 2_000_000
TEXT_EXT = {".py", ".md", ".sql", ".sh", ".json", ".yaml", ".yml", ".toml", ".txt", ".js",
            ".ts", ".tsx", ".jsx", ".html", ".css", ".pseudo", ".rs", ".go", ".plpgsql", ".cfg",
            ".ini", ".rst", ".csv", ""}


def vocab(c, pid: int) -> set[str]:
    names = c.execute(
        """SELECT DISTINCT ce.name FROM entity_links el
           JOIN linkage_types lt ON lt.id = el.linkage_id
           JOIN entities ce ON ce.id = el.concept_id
           JOIN entities e ON e.id = el.entity_id
           WHERE lt.name = 'mentions' AND e.partition_id = ?""", [pid]).fetchall()
    out = set()
    for (n,) in names:
        n = n.lower()
        for p in NS:
            if n.startswith(p):
                n = n[len(p):]
                break
        out.add(n.replace(" ", "_").replace("-", "_"))
    return out


def files_of(c, pid: int, root: str) -> list[str]:
    rows = c.execute(
        "SELECT DISTINCT path FROM entities WHERE partition_id = ? AND kind IN ('doc','code') "
        "AND path IS NOT NULL", [pid]).fetchall()
    out = set()
    for (p,) in rows:
        p = str(p)
        if not p.startswith("/"):
            p = root.rstrip("/") + "/" + p
        out.add(p)
    return sorted(out)


def sections(text: str, ext: str) -> list[str]:
    rx = MD_HEAD if ext == ".md" else (CODE_HEAD if ext in (".py", ".sql") else None)
    if rx is None:
        return [text]
    cuts = [m.start() for m in rx.finditer(text)]
    if not cuts or cuts[0] != 0:
        cuts = [0] + cuts
    cuts.append(len(text))
    return [text[a:b] for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]


def sentence_terms(sent: str, V: set[str]) -> set[str]:
    toks = [w.lower() for w in _WORD_RE.findall(sent)]
    toks = [w for w in toks if w not in _DOCSTRING_STOP and not w.isdigit()]
    out = {w for w in toks if w in V}
    for k in (2, 3):
        for i in range(len(toks) - k + 1):
            g = "_".join(toks[i:i + k])
            if g in V:
                out.add(g)
    return out


def bytes_and_stats(post: dict[str, list[int]], relabel: list[int] | None) -> dict:
    tot = 0
    nc = nrun = 0
    band = defaultdict(int)
    for t, sids in post.items():
        ids = sids if relabel is None else [relabel[x] for x in sids]
        bm = BitMap(ids)
        bm.run_optimize()
        b = len(bm.serialize())
        tot += b
        st = bm.get_statistics()
        nc += st["n_containers"]
        nrun += st["n_run_containers"]
        df = len(bm)
        band["hapax" if df <= 1 else "2-10" if df <= 10 else "11-100" if df <= 100 else ">100"] += b
    return {"bytes": tot, "containers": nc, "run_containers": nrun,
            "run_container_share": nrun / nc if nc else 0.0, "bytes_by_df_band": dict(band)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("store", choices=sorted(STORES))
    a = ap.parse_args()
    t0 = time.time()
    root, pid = STORES[a.store]
    c = duckdb.connect(copy_db(a.store), read_only=True)
    V = vocab(c, pid)
    paths = files_of(c, pid, root)
    c.close()

    post: dict[str, list[int]] = defaultdict(list)
    file_span: list[tuple[int, int]] = []   # (first sid, end sid) per file in path order
    sid = 0
    n_sec = n_para = 0
    skipped = defaultdict(int)
    for p in paths:
        fp = Path(p)
        ext = fp.suffix.lower()
        if ext not in TEXT_EXT:
            skipped["non_text_ext"] += 1
            continue
        if not fp.is_file():
            skipped["missing"] += 1
            continue
        if fp.stat().st_size > MAX_BYTES:
            skipped["too_large"] += 1
            continue
        try:
            text = fp.read_text(errors="ignore")
        except OSError:
            skipped["unreadable"] += 1
            continue
        start = sid
        for sec in sections(text, ext):
            n_sec += 1
            for para in PARA.split(sec):
                if not para.strip():
                    continue
                n_para += 1
                for sent in SENT.split(para):
                    if not sent.strip():
                        continue
                    for t in sentence_terms(sent, V):
                        post[t].append(sid)
                    sid += 1
        if sid > start:
            file_span.append((start, sid))
    N = sid
    rnd = random.Random(SEED)

    # random global permutation
    perm = list(range(N))
    rnd.shuffle(perm)
    # path-sorted files, random within each file
    fri = [0] * N
    for s0, s1 in file_span:
        inner = list(range(s0, s1))
        rnd.shuffle(inner)
        for old, new in zip(range(s0, s1), inner):
            fri[old] = new
    # random file order, document order within
    order = file_span[:]
    rnd.shuffle(order)
    rfd = [0] * N
    nxt = 0
    for s0, s1 in order:
        for old in range(s0, s1):
            rfd[old] = nxt
            nxt += 1

    res = {
        "dewey": bytes_and_stats(post, None),
        "random": bytes_and_stats(post, perm),
        "file_rand_in": bytes_and_stats(post, fri),
        "rand_file_doc": bytes_and_stats(post, rfd),
    }
    rb = res["random"]["bytes"]
    saving = {k: 1 - v["bytes"] / rb for k, v in res.items()}
    band_saving = {b: 1 - res["dewey"]["bytes_by_df_band"].get(b, 0) / v
                   for b, v in res["random"]["bytes_by_df_band"].items() if v}
    dfs = [len(v) for v in post.values()]
    out = {
        "store": a.store, "partition_id": pid, "seed": SEED,
        "files_listed": len(paths), "files_used": len(file_span), "skipped": dict(skipped),
        "sections": n_sec, "paragraphs": n_para, "sentences": N,
        "vocab_size": len(V), "terms_indexed": len(post), "postings": sum(dfs),
        "chunks_65536": (N + 65535) // 65536,
        "numberings": res,
        "saving_vs_random": saving,
        "dewey_saving_by_df_band": band_saving,
        "elapsed_s": round(time.time() - t0, 1),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"m7_{a.store}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
