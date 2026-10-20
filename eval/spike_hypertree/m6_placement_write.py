"""M6 (hypertree spike 2026-10-20): write cost of placements vs today's per-file re-sync.

Measurement only, never imported by `src/`. NO DAEMON: the doc's M6 says "through the
daemon"; per the run order it is measured on a throwaway COPY of each store's snapshot,
in-process, with the production per-file re-sync entry point the daemon's watcher and
`_op_sync_files` call (`refmatrix.sync.sync_files(store, [file], project_root, semantic=False)`,
`watch_semantic` defaults to False). The daemon adds socket + lock + snapshot-request cost to
the ingest side only, so omitting it makes the placement RATIO conservative (larger).

Per sampled file:
  prep (untimed): force a real re-ingest -- tracked_files.mtime := -1 (defeats the mtime gate)
                  and drop `gmd_content_hash` from the file's GMD doc meta (defeats the GMD
                  resume skip, as a real edit would);
  t_ingest:       sync_files(...) on the copy;
  t_place:        derive the file's placement rows (fs dir>file, gmd heading tree, code
                  module>class>def) from the just-written entities + write them: DELETE the
                  file's previous-version rows + INSERT the new version, ONE transaction,
                  one batched INSERT.

Load arm: N busy-loop processes (N = os.cpu_count()) run for the whole pass. The worse arm
(by p95 ratio) is the reported one.

    PYTHONPATH=src .venv-eval/bin/python eval/spike_hypertree/m6_placement_write.py <store> \
        [--n 100] [--arms quiet,loaded]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import random
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, SPIKE_ROOT, STORES, copy_db  # noqa: E402

import numpy as np  # noqa: E402

CODE_EXT = {".py", ".sql", ".ts", ".js", ".sh", ".go", ".rs", ".tsx", ".jsx", ".pseudo"}


def _busy(stop):
    x = 0
    while not stop.is_set():
        for i in range(100000):
            x += i * i


def fresh_copy(store: str) -> Path:
    root = SPIKE_ROOT / "m6" / store / ".refmatrix"
    assert str(root).startswith(str(SPIKE_ROOT)), root
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shutil.copyfile(copy_db(store), root / "catalog.duckdb")
    return root


def sample_files(con, pid: int, proot: str, n: int, rnd: random.Random) -> list[str]:
    rows = [r[0] for r in con.execute(
        "SELECT path FROM tracked_files WHERE partition_id = ? ORDER BY path", [pid]).fetchall()]
    absd = []
    seen = set()
    for p in rows:
        ap = p if p.startswith("/") else os.path.join(proot, p)
        ap = os.path.realpath(ap)
        if ap in seen or not ap.startswith(proot + "/") or not os.path.isfile(ap):
            continue
        seen.add(ap)
        absd.append(ap)
    md = [p for p in absd if p.endswith(".md")]
    code = [p for p in absd if os.path.splitext(p)[1] in CODE_EXT]
    other = [p for p in absd if p not in set(md) | set(code)]
    k_md, k_code = n * 2 // 5, n * 2 // 5
    k_other = n - k_md - k_code
    pick = rnd.sample(md, min(k_md, len(md))) + rnd.sample(code, min(k_code, len(code))) \
        + rnd.sample(other, min(k_other, len(other)))
    # top up from whatever class has slack
    rest = [p for p in absd if p not in set(pick)]
    if len(pick) < n and rest:
        pick += rnd.sample(rest, min(n - len(pick), len(rest)))
    rnd.shuffle(pick)
    return pick


def dewey(ords: list[int]) -> str:
    return ".".join(f"{o:04d}" for o in ords)


def derive_placements(con, pid: int, ap: str, rel: str, version: int) -> list[tuple]:
    """(partition_id, representation, version, path, node) rows for one file."""
    rows = con.execute(
        "SELECT id, kind, name, meta FROM entities WHERE partition_id = ? AND path = ?",
        [pid, ap]).fetchall()
    file_node = -1
    gmd, code = [], []
    stem = rel.replace("/", ".")
    for eid, kind, name, meta in rows:
        m = json.loads(meta) if meta else {}
        if kind in ("doc", "code") and (name == rel or m.get("gmd_version")) and file_node < 0:
            file_node = eid
        if m.get("gmd_node") and "level" in m:
            gmd.append((int(m.get("line") or 0), int(m["level"]), eid))
        elif kind == "code" and name != rel:
            q = name[len(stem) + 1:] if name.startswith(stem + ".") else name.split("::")[-1]
            code.append((int(m.get("line") or 0), q.split("."), eid))
    out: list[tuple] = []
    parts = rel.split("/")
    # fs: ancestor dirs at version 0 (shared structure, insert-if-absent) + the file row
    dirs = [("/".join(parts[:i]) + "/") for i in range(1, len(parts))]
    out.append((pid, "fs", version, rel, file_node))
    # gmd heading tree: stack by heading level, ordinal per parent
    if gmd:
        gmd.sort()
        stack: list[tuple[int, int]] = []   # (level, ordinal)
        counters: dict[tuple, int] = {}
        for _line, lvl, eid in gmd:
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            key = tuple(o for _, o in stack)
            counters[key] = counters.get(key, 0) + 1
            stack.append((lvl, counters[key]))
            out.append((pid, "gmd", version, rel + "\x1f" + dewey([o for _, o in stack]), eid))
    # code: module > class > def by qualified-name components, ordinal per parent by line
    if code:
        code.sort(key=lambda t: t[0])
        ords: dict[tuple, int] = {}
        assigned: dict[tuple, list[int]] = {(): []}
        for _line, comps, eid in code:
            path_ord: list[int] = []
            for i in range(len(comps)):
                key = tuple(comps[: i + 1])
                if key not in assigned:
                    parent = tuple(comps[:i])
                    ords[parent] = ords.get(parent, 0) + 1
                    assigned[key] = assigned.get(parent, []) + [ords[parent]]
            path_ord = assigned[tuple(comps)]
            out.append((pid, "code", version, rel + "\x1f" + dewey(path_ord), eid))
    return out, [(pid, "fs", 0, d, -1) for d in dirs]


def write_placements(con, pid: int, rel: str, version: int, rows, dir_rows,
                     own_txn: bool = True) -> None:
    if not own_txn:
        _write(con, pid, rel, version, rows, dir_rows)
        return
    con.execute("BEGIN TRANSACTION")
    try:
        _write(con, pid, rel, version, rows, dir_rows)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _write(con, pid: int, rel: str, version: int, rows, dir_rows) -> None:
    if True:
        # tombstone the previous version of this file's subtree (all representations)
        con.execute(
            "DELETE FROM placement WHERE partition_id = ? AND version > 0 AND version < ? "
            "AND path >= ? AND path < ?", [pid, version, rel, rel + "\x7f"])
        if dir_rows:
            con.execute(
                "INSERT INTO placement VALUES " + ",".join(["(?,?,?,?,?)"] * len(dir_rows))
                + " ON CONFLICT DO NOTHING", [x for r in dir_rows for x in r])
        con.execute(
            "INSERT INTO placement VALUES " + ",".join(["(?,?,?,?,?)"] * len(rows)),
            [x for r in rows for x in r])


def run_arm(store: str, files: list[str], arm: str, mode: str) -> dict:
    from refmatrix.store import Store
    from refmatrix.sync import sync_files
    proot, pid = STORES[store]
    root = fresh_copy(store)
    pname = None
    s = Store(root)
    pname = s._connect().execute("SELECT name FROM partitions WHERE id = ?", [pid]).fetchone()[0]
    s.close() if hasattr(s, "close") else None
    s = Store(root, partition=pname)
    assert Path(s.db_path).resolve() == (root / "catalog.duckdb").resolve(), s.db_path
    con = s._connect()
    con.execute(
        "CREATE TABLE IF NOT EXISTS placement(partition_id INTEGER, representation VARCHAR, "
        "version BIGINT, path VARCHAR, node BIGINT, "
        "PRIMARY KEY(partition_id, representation, version, path))")
    stop = mp.Event()
    procs = []
    if arm == "loaded":
        for _ in range(os.cpu_count() or 4):
            p = mp.Process(target=_busy, args=(stop,), daemon=True)
            p.start()
            procs.append(p)
        time.sleep(1.0)
    per = []
    try:
        # warm-up: one file outside the measurement (imports, first-connection caches)
        version = 1
        for i, ap in enumerate([files[0]] + files):
            rel = os.path.relpath(ap, proot)
            con.execute("UPDATE tracked_files SET mtime = -1 WHERE path IN (?, ?)", [ap, rel])
            for eid, meta in con.execute(
                    "SELECT id, meta FROM entities WHERE path = ? AND meta LIKE "
                    "'%gmd_content_hash%'", [ap]).fetchall():
                m = json.loads(meta)
                m.pop("gmd_content_hash", None)
                con.execute("UPDATE entities SET meta = ? WHERE id = ?", [json.dumps(m), eid])
            version += 1
            if mode == "separate":
                # placement in its OWN transaction after the sync commits (pessimistic)
                t0 = time.perf_counter()
                rep = sync_files(s, [ap], project_root=Path(proot), semantic=False)
                t1 = time.perf_counter()
                rows, dir_rows = derive_placements(con, pid, ap, rel, version)
                td = time.perf_counter()
                write_placements(con, pid, rel, version, rows, dir_rows)
                t2 = time.perf_counter()
                tc = 0.0
            else:
                # fused: same transaction as the file's entities (the doc's B design).
                # sync_files' own `s.transaction()` nests into this one (re-entry safe);
                # the shared COMMIT (+ fragment flush) is charged to the ingest baseline.
                with s.transaction():
                    t0 = time.perf_counter()
                    rep = sync_files(s, [ap], project_root=Path(proot), semantic=False)
                    t1 = time.perf_counter()
                    rows, dir_rows = derive_placements(con, pid, ap, rel, version)
                    td = time.perf_counter()
                    write_placements(con, pid, rel, version, rows, dir_rows, own_txn=False)
                    t2 = time.perf_counter()
                tc = time.perf_counter() - t2
            if i == 0:
                continue
            per.append({"ext": os.path.splitext(ap)[1], "t_ingest": (t1 - t0) + tc,
                        "t_place": t2 - t1, "t_commit": tc, "t_derive": td - t1,
                        "t_write": t2 - td,
                        "rows": len(rows), "dir_rows": len(dir_rows),
                        "touched": rep.get("touched"), "updated": rep.get("updated"),
                        "added": rep.get("added"), "purged": rep.get("purged"),
                        "vector_delete_failed": rep.get("vector_delete_failed")})
    finally:
        stop.set()
        for p in procs:
            p.join(timeout=5)
    ti = np.array([r["t_ingest"] for r in per])
    tp = np.array([r["t_place"] for r in per])
    ratio = tp / np.maximum(ti, 1e-9)
    tw = np.array([r["t_write"] for r in per])
    tdv = np.array([r["t_derive"] for r in per])
    wratio = tw / np.maximum(ti, 1e-9)
    rows = np.array([r["rows"] for r in per])
    by_ext = {}
    for e in sorted({r["ext"] for r in per}):
        sub = [r for r in per if r["ext"] == e]
        by_ext[e] = {"n": len(sub),
                     "t_ingest_p50_ms": 1000 * float(np.median([r["t_ingest"] for r in sub])),
                     "t_place_p50_ms": 1000 * float(np.median([r["t_place"] for r in sub])),
                     "rows_mean": float(np.mean([r["rows"] for r in sub]))}
    return {
        "arm": arm, "mode": mode, "n_files": len(per),
        "t_ingest_ms": {"p50": 1000 * float(np.percentile(ti, 50)),
                        "p95": 1000 * float(np.percentile(ti, 95))},
        "t_place_ms": {"p50": 1000 * float(np.percentile(tp, 50)),
                       "p95": 1000 * float(np.percentile(tp, 95)),
                       "max": 1000 * float(tp.max())},
        "ratio_per_file": {"p50": float(np.percentile(ratio, 50)),
                           "p95": float(np.percentile(ratio, 95))},
        "ratio_p95_over_p95": float(np.percentile(tp, 95) / np.percentile(ti, 95)),
        "t_derive_ms": {"p50": 1000 * float(np.percentile(tdv, 50)),
                        "p95": 1000 * float(np.percentile(tdv, 95))},
        "t_write_ms": {"p50": 1000 * float(np.percentile(tw, 50)),
                       "p95": 1000 * float(np.percentile(tw, 95))},
        "write_only_ratio_per_file": {"p50": float(np.percentile(wratio, 50)),
                                      "p95": float(np.percentile(wratio, 95))},
        "ratio_sum": float(tp.sum() / ti.sum()),
        "rows_per_file": {"mean": float(rows.mean()), "p95": float(np.percentile(rows, 95)),
                          "max": int(rows.max())},
        "files_not_touched": int(sum(1 for r in per if not r["touched"])),
        "vector_delete_failed": int(sum(r["vector_delete_failed"] or 0 for r in per)),
        "by_ext": by_ext,
        "placement_rows_total": con.execute("SELECT count(*) FROM placement").fetchone()[0],
    }


def band(r: float) -> str:
    return "inline (<5%)" if r < 0.05 else ("batch at snapshot tick (5-20%)" if r <= 0.20
                                            else "derive offline only (>20%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("store", choices=sorted(STORES))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--arms", default="quiet,loaded")
    ap.add_argument("--modes", default="fused,separate")
    a = ap.parse_args()
    import duckdb
    proot, pid = STORES[a.store]
    rnd = random.Random(SEED)
    con = duckdb.connect(copy_db(a.store), read_only=True)
    files = sample_files(con, pid, os.path.realpath(proot), a.n, rnd)
    con.close()
    out = {"store": a.store, "seed": SEED, "method": "in-process sync_files on a no-daemon copy",
           "n_sampled": len(files), "arms": {}}
    out["reported"] = {}
    for mode in a.modes.split(","):
        for arm in a.arms.split(","):
            r = run_arm(a.store, files, arm, mode)
            out["arms"][f"{mode}/{arm}"] = r
            print(json.dumps({k: r[k] for k in ("arm", "mode", "t_ingest_ms", "t_place_ms",
                              "ratio_per_file", "ratio_p95_over_p95")}), flush=True)
        arms = [out["arms"][f"{mode}/{arm}"] for arm in a.arms.split(",")]
        w1 = max(arms, key=lambda r: r["ratio_per_file"]["p95"])
        w2 = max(arms, key=lambda r: r["ratio_p95_over_p95"])
        out["reported"][mode] = {
            "p95_of_per_file_ratio": w1["ratio_per_file"]["p95"], "arm": w1["arm"],
            "band_per_file_ratio": band(w1["ratio_per_file"]["p95"]),
            "p95_place_over_p95_ingest": w2["ratio_p95_over_p95"], "arm_p95p95": w2["arm"],
            "band_p95p95": band(w2["ratio_p95_over_p95"]),
            "t_place_p95_ms_worst": max(r["t_place_ms"]["p95"] for r in arms),
            "write_only_p95_ratio_worst": max(r["write_only_ratio_per_file"]["p95"] for r in arms),
            "band_write_only": band(max(r["write_only_ratio_per_file"]["p95"] for r in arms))}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"m6_{a.store}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["reported"], indent=1))


if __name__ == "__main__":
    main()
