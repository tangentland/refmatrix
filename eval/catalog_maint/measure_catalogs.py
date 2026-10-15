"""Task 18.1: measure every fleet catalog on a COPY — free blocks, a timed rewrite rehearsal,
and the pre-registered bands that decide whether an offline reclaim (18.3) is worth building.

Why this exists (plan-18 `#open`, d9bb 2026-10-15): on DuckDB 1.5.3 neither CHECKPOINT nor
VACUUM shrinks a file; only a rewrite into a new file (`COPY FROM DATABASE`) gives space back.
Whether a rewrite is worth building depends on two numbers nobody had measured — how much each
catalog would give back, and how long the rewrite takes (the downtime of 18.3). The bands below
were written into the task spec BEFORE the fleet run (`feedback_go_no_go_ranges_not_predrop`);
changing an edge after the run needs a user decision row.

Safety rules, each from an incident:
- bug-110: a `close()` of ANY descriptor on a DuckDB file drops the daemon's fcntl lock. This
  script never opens a file under a live root: it `stat`s, and copies the read snapshot with
  `/bin/cp -p` in a child. The `active` marker is read by a `/bin/cat` child for the same reason.
- bug-112: a second in-process `duckdb.connect` to a path returns the cached database. Every
  DuckDB statement runs in a child process; the parent never imports duckdb.
- It never reads a writer slot and never connects to a socket.
- It deletes only the per-store work dirs it made (ch-bsd r1 #m-3), never the scratch dir's
  other contents.

Evaluation code, not product (task-18.1 R1).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

MiB = 1024 * 1024

# Task-18.1 R3, pre-registered 2026-10-15. AC-7 pins these literals to the spec's tables.
BANDS = {
    "min_reclaim_bytes": 64 * MiB,  # Table A: below this a reclaim is not worth it
    "a1_r": 0.20,                   # Table A: r below this -> A0
    "a2_r": 0.50,                   # Table A: r at/above this -> A2
    "b_agree": 0.10,                # Table B: |f - r| <= this -> the proxy agrees
    "c0_s": 30.0,                   # Table C: median rewrite_s <= this -> C0
    "c1_s": 120.0,                  # Table C: <= this -> C1, above -> C2
    "noisy_ratio": 1.5,             # Table C: max > ratio * median -> noisy
    "in_daemon_max_s": 5.0,         # recorded-not-built: in-daemon reclaim needs every max <= this
}

_CP = "/bin/cp"
_CAT = "/bin/cat"
REHEARSALS = 3


# ---- the catalog fingerprint and its gate (one shape, reused by 18.3) ---------------------


def _rows(con, sql: str, params: list) -> list:
    return [list(r) for r in con.execute(sql, params).fetchall()]


def catalog_fingerprint(con) -> dict:
    """Everything a rewrite must carry over, from an open DuckDB connection's current database.

    One leg per part of the catalog; `gate(a, b)` compares two fingerprints leg by leg. Why every
    leg (ch-bsd task-18.1 r1 #s-3, 2026-10-15): the r1 gate checked only counts, sequence values,
    index NAMES and constraint COUNTS, so a changed DEFAULT (the `nextval` ids depend on), CHECK
    text, index definition, a new view/macro/type, or any value edit that kept the counts passed.
    The content leg is an order-independent `sum(hash(row))` per table — a SUM, not `bit_xor`,
    so a pair of duplicate rows cannot cancel out. `hash()` is DuckDB-version-specific: compare
    fingerprints taken by the same duckdb build (the measurement records `duckdb_version`).
    Plan-18.3's reclaim gates its swap on this function; it must not grow a second gate.
    Values are lists/dicts/scalars only, so a fingerprint compares equal after a JSON round trip.
    """
    db = con.execute("SELECT current_database()").fetchone()[0]
    p = [db]
    rows, content = {}, {}
    for schema, name in con.execute(
            "SELECT schema_name, table_name FROM duckdb_tables() "
            "WHERE database_name = ? ORDER BY 1, 2", p).fetchall():
        n, h = con.execute(
            f'SELECT count(*), sum(hash(_fp_row_)::HUGEINT) FROM "{schema}"."{name}" _fp_row_'
        ).fetchone()
        rows[f"{schema}.{name}"] = n
        content[f"{schema}.{name}"] = None if h is None else int(h)
    columns: dict = {}
    for s, t, *rest in _rows(con,
            "SELECT schema_name, table_name, column_index, column_name, data_type, "
            "column_default, is_nullable FROM duckdb_columns() WHERE database_name = ? "
            "ORDER BY 1, 2, 3", p):
        columns.setdefault(f"{s}.{t}", []).append(rest)
    constraints: dict = {}
    for s, t, *rest in _rows(con,
            "SELECT schema_name, table_name, constraint_type, constraint_text, "
            "list_sort(constraint_column_names) FROM duckdb_constraints() "
            "WHERE database_name = ? ORDER BY ALL", p):
        constraints.setdefault(f"{s}.{t}", []).append(rest)
    return {
        "rows": rows,
        "content": content,
        "columns": columns,
        "constraints": constraints,
        "indexes": {f"{s}.{n}": [t, sql] for s, n, t, sql in _rows(con,
            "SELECT schema_name, index_name, table_name, sql FROM duckdb_indexes() "
            "WHERE database_name = ?", p)},
        "sequences": {f"{s}.{n}": rest for s, n, *rest in _rows(con,
            "SELECT schema_name, sequence_name, start_value, min_value, max_value, "
            "increment_by, cycle, last_value FROM duckdb_sequences() "
            "WHERE database_name = ?", p)},
        "views": {f"{s}.{n}": sql for s, n, sql in _rows(con,
            "SELECT schema_name, view_name, sql FROM duckdb_views() "
            "WHERE database_name = ? AND NOT internal", p)},
        "macros": {f"{s}.{n}": sorted(map(str, defs)) for s, n, defs in _rows(con,
            "SELECT schema_name, function_name, list(function_type || ':' || "
            "coalesce(macro_definition, '')) FROM duckdb_functions() "
            "WHERE database_name = ? AND NOT internal GROUP BY ALL", p)},
        "types": {f"{s}.{n}": [lt, labels] for s, n, lt, labels in _rows(con,
            "SELECT schema_name, type_name, logical_type, labels FROM duckdb_types() "
            "WHERE database_name = ? AND NOT internal", p)},
    }


def gate(before: dict, after: dict) -> list[str]:
    """Every difference between two fingerprints, leg by leg; empty means the gate passes.
    A leg present on one side only is itself a difference (a fingerprint never drops a leg)."""
    diffs = []
    for leg in sorted(set(before) | set(after)):
        a_leg, b_leg = before.get(leg), after.get(leg)
        if a_leg is None or b_leg is None:
            diffs.append(f"{leg}: missing from {'copy' if a_leg is None else 'rewrite'}")
            continue
        for key in sorted(set(a_leg) | set(b_leg)):
            a, b = a_leg.get(key), b_leg.get(key)
            if a != b:
                diffs.append(f"{leg} {key}: copy={a} rewrite={b}")
    return diffs


# ---- child side: every DuckDB statement runs here ----------------------------------------


def _child_measure(path: str) -> dict:
    import duckdb
    con = duckdb.connect(path, read_only=True)
    try:
        db = con.execute("SELECT current_database()").fetchone()[0]
        size = con.execute(
            "SELECT block_size, total_blocks, used_blocks, free_blocks "
            "FROM pragma_database_size() WHERE database_name = ?", [db]).fetchone()
        fp = catalog_fingerprint(con)
    finally:
        con.close()
    return {"pid": os.getpid(), "duckdb_version": duckdb.__version__, "block_size": size[0],
            "total_blocks": size[1], "used_blocks": size[2], "free_blocks": size[3],
            "fingerprint": fp}


def _child_rewrite(path: str, target: str) -> dict:
    # Read-write on purpose: `path` is the scratch COPY, and a read-only connection attaches
    # its targets read-only too (ATTACH of the new file fails).
    import duckdb
    con = duckdb.connect(path)
    try:
        db = con.execute("SELECT current_database()").fetchone()[0]
        t0 = time.monotonic()
        con.execute(f"ATTACH '{target}' AS n")
        con.execute(f'COPY FROM DATABASE "{db}" TO n')
        con.execute("CHECKPOINT n")
        con.execute("DETACH n")
        dt = time.monotonic() - t0
    finally:
        con.close()
    return {"pid": os.getpid(), "duckdb_version": duckdb.__version__, "rewrite_s": dt,
            "rewrite_bytes": os.path.getsize(target)}


def _child_main(argv: list[str]) -> int:
    mode, *rest = argv
    out = _child_measure(*rest) if mode == "measure" else _child_rewrite(*rest)
    sys.stdout.write(json.dumps(out))
    return 0


# ---- parent side ------------------------------------------------------------------------


class StepError(Exception):
    def __init__(self, step: str, msg: str):
        super().__init__(f"{step}: {msg}")
        self.step, self.msg = step, msg


def _child(python: str, *args: str, step: str, timeout_s: float = 3600.0) -> dict:
    proc = subprocess.run([python, str(Path(__file__).resolve()), "--child", *args],
                          capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        tail = (proc.stderr.strip().splitlines() or ["(no stderr)"])[-1]
        raise StepError(step, f"child exited {proc.returncode}: {tail}")
    return json.loads(proc.stdout)


def _size(p: Path) -> int | None:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return None


def stat_root(root: Path) -> dict:
    """The F4 columns, by `stat` only (the marker through a `/bin/cat` child)."""
    proc = subprocess.run([_CAT, str(root / "active")], capture_output=True, text=True)
    active = proc.stdout.strip() if proc.returncode == 0 else None
    other = {"A": "B", "B": "A"}.get(active or "")
    writer = root / f"catalog.{active}.duckdb" if active else None
    return {
        "active": active,
        "writer_bytes": _size(writer) if writer else None,
        "writer_wal_bytes": _size(Path(f"{writer}.wal")) if writer else None,
        "snapshot_bytes": _size(root / "catalog.read.duckdb"),
        "inactive_slot": other,
        "inactive_bytes": _size(root / f"catalog.{other}.duckdb") if other else None,
        "legacy_bytes": _size(root / "catalog.duckdb"),
        "factslog_bytes": _size(root / "facts.log"),
    }


def copy_snapshot(src: Path, dst: Path) -> None:
    proc = subprocess.run([_CP, "-p", str(src), str(dst)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise StepError("copy", f"cp exited {proc.returncode}: {proc.stderr.strip()}")


def derive(*, file_bytes: int, rewrite_bytes: int, free_blocks: int, total_blocks: int,
           min_reclaim_bytes: int = BANDS["min_reclaim_bytes"]) -> dict:
    """Pure: the reclaim estimate `r` comes from the REWRITE; `f` is only the cheap proxy."""
    f = free_blocks / total_blocks if total_blocks else 0.0
    r = 1.0 - rewrite_bytes / file_bytes if file_bytes else 0.0
    reclaimable = file_bytes - rewrite_bytes
    if reclaimable < min_reclaim_bytes or r < BANDS["a1_r"]:
        band_a = "A0"
    elif r < BANDS["a2_r"]:
        band_a = "A1"
    else:
        band_a = "A2"
    band_b = "B-agree" if abs(f - r) <= BANDS["b_agree"] else "B-disagree"
    return {"f": round(f, 4), "r": round(r, 4), "reclaimable": reclaimable,
            "band_a": band_a, "band_b": band_b}


def band_c(median_s: float) -> str:
    if median_s <= BANDS["c0_s"]:
        return "C0"
    return "C1" if median_s <= BANDS["c1_s"] else "C2"


def _is_noisy(times: list[float]) -> bool:
    return max(times) > BANDS["noisy_ratio"] * statistics.median(times)


def store_name(root: Path, *, home: Path | None = None) -> str:
    """The report's name for a store, from its root path (ch-bsd r1 #m-4: the global store
    `~/.refmatrix` was reported as the user's name, `parent.name`)."""
    root = Path(root)
    if root.expanduser().resolve() == ((home or Path.home()) / ".refmatrix").resolve():
        return "global"
    return root.parent.name if root.name == ".refmatrix" else root.name


def measure_root(root: Path, scratch: Path, *, python: str,
                 min_reclaim_bytes: int = BANDS["min_reclaim_bytes"],
                 before_gate: Callable[[Path], None] | None = None,
                 time_hook: Callable[[int, float], float] | None = None,
                 bytes_hook: Callable[[int, int], int] | None = None) -> dict:
    """One row. Failures raise; the caller turns them into a counted error row.

    The copies live in a work dir made fresh for this root under `scratch` and removed in a
    `finally`, whatever happens (ch-bsd r1 #m-3: r1 removed the whole scratch dir the user
    passed, and an uncaught exception left ~800 MB of copies behind)."""
    row: dict = {"root": str(root), "store": store_name(root), **stat_root(root)}
    snap = root / "catalog.read.duckdb"
    if not snap.exists():
        raise StepError("snapshot", "no snapshot")
    work = Path(tempfile.mkdtemp(prefix=f"{row['store']}-", dir=scratch))
    try:
        return _measure_copy(row, snap, work, python=python,
                             min_reclaim_bytes=min_reclaim_bytes, before_gate=before_gate,
                             time_hook=time_hook, bytes_hook=bytes_hook)
    finally:
        shutil.rmtree(work)


def _measure_copy(row: dict, snap: Path, work: Path, *, python: str, min_reclaim_bytes: int,
                  before_gate: Callable[[Path], None] | None,
                  time_hook: Callable[[int, float], float] | None,
                  bytes_hook: Callable[[int, int], int] | None) -> dict:
    copy = work / "snap.duckdb"
    copy_snapshot(snap, copy)
    row["as_of"] = datetime.fromtimestamp(copy.stat().st_mtime).isoformat(timespec="seconds")
    row["file_bytes"] = copy.stat().st_size
    m = _child(python, "measure", str(copy), step="measure")
    row["duckdb_version"] = m["duckdb_version"]
    row["pids"] = {"measure": m["pid"]}
    for k in ("block_size", "total_blocks", "used_blocks", "free_blocks"):
        row[k] = m[k]
    row["rows"] = sum(m["fingerprint"]["rows"].values())

    runs: list[dict] = []

    def batch() -> list[float]:
        times = []
        for _ in range(REHEARSALS):
            ix = len(runs)
            tgt = work / f"rewrite{ix}.duckdb"
            res = _child(python, "rewrite", str(copy), str(tgt), step="rewrite")
            s = time_hook(ix, res["rewrite_s"]) if time_hook else res["rewrite_s"]
            nb = bytes_hook(ix, res["rewrite_bytes"]) if bytes_hook else res["rewrite_bytes"]
            runs.append({**res, "rewrite_s": s, "rewrite_bytes": nb, "target": tgt})
            times.append(s)
            if ix:          # keep only the newest rewrite on disk; the gate reads it
                runs[ix - 1]["target"].unlink()
        return times

    times = batch()
    row["rehearsal_reruns"] = 0
    if _is_noisy(times):
        row["rehearsal_reruns"] = 1
        times = batch()
    versions = {m["duckdb_version"], *(r["duckdb_version"] for r in runs)}
    if len(versions) != 1:
        raise StepError("version", f"children ran different duckdb builds: {sorted(versions)}")
    row["rewrite_s_all"] = [round(r["rewrite_s"], 3) for r in runs]
    # Band C reads the final batch's median (AC-8); the in-daemon ceiling reads the worst run of
    # ANY batch, the noisy first one included (ch-bsd r1 #m-2).
    row["rewrite_s_median"] = round(statistics.median(times), 3)
    row["rewrite_s_max"] = round(max(r["rewrite_s"] for r in runs), 3)
    # The rewrite's size varies run to run (~1.3 % on refmatrix, r1 #s-5): report the median.
    row["rewrite_bytes_all"] = [r["rewrite_bytes"] for r in runs]
    row["rewrite_bytes"] = int(statistics.median(row["rewrite_bytes_all"]))
    last = runs[-1]
    row["pids"]["rewrite"] = last["pid"]

    final = work / "rewrite.duckdb"
    os.replace(last["target"], final)
    if before_gate:
        before_gate(final)
    g = _child(python, "measure", str(final), step="gate")
    row["pids"]["gate"] = g["pid"]
    diffs = gate(m["fingerprint"], g["fingerprint"])
    row["gate"] = "fail" if diffs else "pass"
    if diffs:
        row["gate_diffs"] = diffs
        row["error"] = "gate failed"
        row["step"] = "gate"
        return row
    row.update(derive(file_bytes=row["file_bytes"], rewrite_bytes=row["rewrite_bytes"],
                      free_blocks=row["free_blocks"], total_blocks=row["total_blocks"],
                      min_reclaim_bytes=min_reclaim_bytes))
    row["band_c"] = "noisy" if _is_noisy(times) else band_c(statistics.median(times))
    return row


def verdict(rows: list[dict]) -> dict:
    failed = [r for r in rows if r.get("error")]
    if failed:
        return {"verdict": "INCOMPLETE", "failed": len(failed),
                "note": "no fleet-wide band is applied until every store has a row (R6)"}
    worth = [r for r in rows if r["band_a"] in ("A1", "A2")]
    to_user = [r["root"] for r in worth if r["band_c"] in ("C0", "C1")]
    helix = [r["root"] for r in worth if r["band_c"] == "C2"]
    noisy = [r["root"] for r in worth if r["band_c"] == "noisy"]
    if not worth:
        v183 = "18.3 CLOSED, not needed"
    elif to_user:
        v183 = "18.3 goes to the user (lift C12 for an OFFLINE hand-run reclaim)"
    else:
        v183 = "no store admissible for 18.3"
    agree = all(r["band_b"] == "B-agree" for r in rows)
    return {
        "verdict": v183, "reclaim_candidates": to_user, "helix": helix, "noisy": noisy,
        "band_mode": "free_ratio" if agree else "growth",
        "in_daemon_feasible": all(r["rewrite_s_max"] <= BANDS["in_daemon_max_s"]
                                  for r in rows),
    }


def run(roots: list[Path], scratch: Path, out: Path, *, python: str = sys.executable,
        **kw) -> tuple[list[dict], dict, int]:
    """Measure every root; the report is ALWAYS written, and every root gets a row (R6).

    Any exception from one root becomes that root's error row (ch-bsd r1 #m-3: a `KeyError`
    used to abort the run with no report). Only this run's per-store work dirs are deleted;
    `scratch` itself is removed only if this run created it and it is empty."""
    roots = [Path(r) for r in roots]
    created = not scratch.exists()
    scratch.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    try:
        for root in roots:
            try:
                rows.append(measure_root(root, scratch, python=python, **kw))
            except StepError as e:
                rows.append({"root": str(root), "store": store_name(root), "error": e.msg,
                             "step": e.step})
            except Exception as e:  # noqa: BLE001 - every failure is a counted row, R6
                rows.append({"root": str(root), "store": store_name(root),
                             "error": f"{type(e).__name__}: {e}", "step": "unexpected"})
    finally:
        for root in roots[len(rows):]:   # an interrupt still leaves a row per root
            rows.append({"root": str(root), "store": store_name(root),
                         "error": "not measured: run interrupted", "step": "interrupted"})
        v = verdict(rows)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out.with_suffix(".jsonl"), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        out.with_suffix(".md").write_text(render_md(rows, v))
        if created and not any(scratch.iterdir()):
            scratch.rmdir()
    failed = sum(1 for r in rows if r.get("error"))
    print(f"measured {len(rows) - failed}/{len(rows)} stores; failed={failed}; "
          f"verdict: {v['verdict']}")
    return rows, v, 1 if failed else 0


def _mb(n) -> str:
    return "-" if n is None else f"{n / MiB:,.1f}"


def render_md(rows: list[dict], v: dict) -> str:
    day = datetime.now().strftime("%Y%m%d")
    lines = [
        "---", 'gmd: "0.1"', f"id: plan18-catalog-measure-{day}",
        f'title: "Plan-18 task 18.1 fleet catalog measurement {day}"',
        "tags: [plan-18, duckdb, catalog, measurement]", "---", "",
        f"# Task 18.1 fleet catalog measurement {day} {{#root}}", "",
        "rel: implements -> [[task-18.1-catalog-measurement]]", "",
        "## Per store {#stores}", "",
        "| store | file MiB | rewrite MiB | reclaimable MiB | f | r | A | B | median s | max s "
        "| C | gate | duckdb |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = r["store"]
        if r.get("error"):
            lines.append(f"| {name} | error: {r['error']} (step {r['step']}) "
                         "| | | | | | | | | | | |")
            continue
        lines.append(
            f"| {name} | {_mb(r['file_bytes'])} | {_mb(r['rewrite_bytes'])} "
            f"| {_mb(r['reclaimable'])} | {r['f']:.3f} | {r['r']:.3f} | {r['band_a']} "
            f"| {r['band_b']} | {r['rewrite_s_median']} | {r['rewrite_s_max']} "
            f"| {r['band_c']} | {r['gate']} | {r['duckdb_version']} |")
    lines += ["", "## Fleet verdict {#verdict}", ""]
    lines += [f"- **{k}:** {val}" for k, val in v.items()]
    lines += ["", "## Bands (pre-registered, task-18.1 R3) {#bands}", ""]
    lines += [f"- `{k}` = {val}" for k, val in BANDS.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--child":
        return _child_main(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", action="append", type=Path,
                    help="a .refmatrix root (repeatable); default: the launchd-registered set")
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="report path, no suffix")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter for the DuckDB children (match the stores' duckdb)")
    a = ap.parse_args(argv)
    roots = a.root
    if not roots:
        from refmatrix import discovery
        roots = discovery._roots_from_launchd()
    _, _, code = run(roots, a.scratch, a.out, python=a.python)
    return code


if __name__ == "__main__":
    sys.exit(main())
