"""Shared helpers: open the COPY read-only with dev code. Never touches the live store."""
import os, sys, time, statistics, subprocess, resource
from pathlib import Path
S = Path(__file__).resolve().parent
ROOT = Path((S / "ROOT").read_text().strip())
assert str(ROOT).startswith("/private/tmp/claude-501/pb"), ROOT
os.environ.pop("REFMATRIX_ROOT", None)
os.environ.pop("RMX_PARTITION", None)
sys.path.insert(0, "/Users/tholley/claude_tools/refmatrix/src")
from refmatrix.store import Store  # noqa: E402
PART = "refmatrix"

def open_store():
    s = Store(ROOT, partition=PART, read_only=True)
    s._connect()
    assert s._read_only and s.db_path == ROOT / "catalog.read.duckdb", s.db_path
    return s

def load():
    return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip().split("load averages:")[-1].strip()

def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # macOS: bytes

def stats(xs):
    xs = sorted(xs)
    p90 = xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]
    return {"n": len(xs), "med": statistics.median(xs), "p90": p90, "min": xs[0], "max": xs[-1]}

def fmt(st, unit="ms", scale=1e3):
    return f"med {st['med']*scale:.2f}{unit} p90 {st['p90']*scale:.2f}{unit} (min {st['min']*scale:.2f}, max {st['max']*scale:.2f}, n={st['n']})"

def timeit(fn, n=5, warm=0):
    for _ in range(warm):
        fn()
    out = []; res = None
    for _ in range(n):
        t = time.perf_counter(); res = fn(); out.append(time.perf_counter() - t)
    return stats(out), res
