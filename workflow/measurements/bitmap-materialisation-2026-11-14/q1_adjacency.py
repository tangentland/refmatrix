"""Q1: build_adjacency cold vs cached_adjacency in-process vs disk tier, on the COPY.
Q2b: the scan-prompt PPR rerank (rank_related_for_prompt, the per-prompt bypass) today vs
a prototype over the cached CSR with a seed-row overlay. Outputs asserted identical."""
import json, time, tracemalloc, gc
from common import *
import numpy as np
from refmatrix import pagerank as pr
from refmatrix import ppr as ppr_mod
from refmatrix.scan import extract_candidates, match_concepts

print("load at start:", load())
# The disk tier is keyed on facts.log size; the copy has none, so give it one (scratch only).
(ROOT / "facts.log").write_text("x" * 12345)
for p in (ROOT / "adjacency.cache.npz", ROOT / "adjacency.cache.json"):
    if p.exists(): p.unlink()

# --- cold: fresh Store (connect + fragment deserialize + SQL) + build_adjacency
def cold_fresh():
    s = open_store(); a = pr.build_adjacency(s); return a
st_cold, adj = timeit(cold_fresh, n=5)
print("build_adjacency cold (fresh Store):", fmt(st_cold))
s = open_store(); pr.build_adjacency(s)  # warm the fragment
st_build, _ = timeit(lambda: pr.build_adjacency(s), n=5)
print("build_adjacency (fragment already loaded):", fmt(st_build))
# breakdown: fragment deserialize alone
def frag_only():
    s2 = open_store(); return s2._load_fragment("mentions")
st_frag, frag = timeit(frag_only, n=5)
print("fresh Store + mentions fragment load:", fmt(st_frag), "bits", len(frag))
st_fd, csr = timeit(lambda: pr.CSRAdjacency.from_dict(adj), n=5)
print("CSRAdjacency.from_dict:", fmt(st_fd))
nodes = len(adj); dedges = sum(len(v) for v in adj.values())
print("nodes", nodes, "directed edges", dedges, "undirected", dedges // 2)
csr_bytes = csr._offsets.nbytes + csr._nbrs.nbytes + csr._wts.nbytes
print("CSR array bytes", csr_bytes)
# dict-of-dicts allocation size (one traced build)
gc.collect(); tracemalloc.start(); a2 = pr.build_adjacency(s); cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
print(f"dict-of-dicts traced: current {cur/1e6:.1f} MB peak {peak/1e6:.1f} MB")
del a2; gc.collect()
gc.collect(); tracemalloc.start(); c2 = pr.CSRAdjacency.from_dict(adj); cur2, _ = tracemalloc.get_traced_memory(); tracemalloc.stop()
print(f"CSR traced (arrays + index dict): {cur2/1e6:.1f} MB"); del c2

# --- cached_adjacency: first call builds + writes npz; then warm in-process; then disk tier
s = open_store()
t = time.perf_counter(); c = pr.cached_adjacency(s); t_first = time.perf_counter() - t
print(f"cached_adjacency first call (build + from_dict + npz write): {t_first*1e3:.1f} ms")
npz = ROOT / "adjacency.cache.npz"; print("npz bytes", npz.stat().st_size)
st_warm, _ = timeit(lambda: pr.cached_adjacency(s), n=50)
print("cached_adjacency warm in-process:", fmt(st_warm, "us", 1e6))
def disk_tier():
    s3 = open_store(); return pr.cached_adjacency(s3)
st_disk, cd = timeit(disk_tier, n=7)
print("cached_adjacency disk tier (fresh Store + npz load):", fmt(st_disk))
def canon(c):
    rows = np.repeat(np.fromiter(c._index.keys(), dtype=np.int64, count=len(c._index)), np.diff(c._offsets))
    o = np.lexsort((c._nbrs, rows)); return rows[o], c._nbrs[o], c._wts[o]
A, B = canon(cd), canon(csr)
same_order = np.array_equal(cd._nbrs, csr._nbrs)
assert len(cd) == len(csr) and all(np.array_equal(x, y) for x, y in zip(A[:2], B[:2])) and np.allclose(A[2], B[2], rtol=1e-12, atol=0)
print("disk-tier CSR == fresh build as an edge SET (weights equal to 1e-12); same row ORDER:", same_order)
st_open, _ = timeit(open_store, n=7)
print("fresh Store open alone:", fmt(st_open))
def npz_only():
    z = np.load(npz); idx = {int(k): int(v) for k, v in zip(z["idx_keys"], z["idx_vals"])}
    return pr.CSRAdjacency(idx, z["offsets"], z["nbrs"], z["wts"])
st_npz, _ = timeit(npz_only, n=7)
print("npz load + index dict alone:", fmt(st_npz))
# Is the live disk cache key what scan-prompt's PPR call would need? link_weight=2.0,
# exclude_operational=True are build_adjacency's defaults == cached_adjacency's defaults.
print("load after Q1:", load())

# --- Q2b: scan-prompt PPR rerank today vs prototype over cached CSR -------------------------
class Overlay:
    """CSR + replacement rows for clique seeds (prototype of overlay_prompt_clique over CSR)."""
    def __init__(self, csr, rows): self.csr, self.rows = csr, rows
    def __contains__(self, u): return u in self.rows or u in self.csr
    def get(self, u, default=None):
        if u in self.rows: return self.rows[u]
        return self.csr.get(u, default)
    def __getitem__(self, u):
        return self.rows[u] if u in self.rows else self.csr[u]

def proto_rank(st, csr, seed_ids, *, k=5, alpha=0.15, eps=1e-4, clique_weight=2.0,
               coverage_alpha=3.0, kinds=("concept",)):
    present = [sid for sid in seed_ids if sid in csr]
    if not present: return []
    cov = {}
    if coverage_alpha > 0:
        if len(present) < 2: cov = {n: 0.0 for n in present}
        else:
            nb = {n: set(csr.get(n)._nbrs.tolist()) for n in present}
            for n in present:
                mine = nb[n]
                if not mine: cov[n] = 0.0; continue
                others = set().union(*(nb[m] for m in present if m != n))
                cov[n] = len(mine & others) / len(mine)
    walk = csr
    if clique_weight > 0 and len(present) >= 2:
        rows = {}
        for a in present:
            v = csr[a]; row = dict(zip(v._nbrs.tolist(), v._wts.tolist()))
            for b in present:
                if a == b: continue
                row[b] = row.get(b, 0.0) + clique_weight
            rows[a] = row
        walk = Overlay(csr, rows)
    p = ppr_mod.local_push_ppr(walk, {sid: 1.0 for sid in present}, alpha=alpha, eps=eps)
    if coverage_alpha > 0:
        for sid, c_ in cov.items():
            if sid in p: p[sid] *= (1.0 + c_) ** coverage_alpha
    seedset = set(present); con = st._connect(); out = []
    for nid, score in sorted(p.items(), key=lambda kv: -kv[1]):
        row = con.execute("SELECT name, kind FROM entities WHERE id = ?", (nid,)).fetchone()
        if row is None: continue
        name, kind = row
        if kinds is not None and kind not in kinds: continue
        if pr._OPERATIONAL_RE.match(name or ""): continue
        rec = {"id": nid, "name": name, "kind": kind, "score": score, "seed": nid in seedset}
        if nid in cov: rec["coverage"] = cov[nid]
        out.append(rec)
        if len(out) >= k: break
    return out

# Realistic seed sets: recent scan-prompt bodies from the live query.log (read as text; the
# prompts themselves are not written to any output).
bodies = []
for line in open("/Users/tholley/claude_tools/refmatrix/.refmatrix/query.log", errors="replace"):
    try: r = json.loads(line)
    except Exception: continue
    if r.get("kind") == "scan" and r.get("source") == "scan-prompt" and r.get("ts", "") >= "2026-11-13":
        bodies.append(r.get("body") or "")
s = open_store(); csr = pr.cached_adjacency(s)
seedsets = []
for b in bodies[-40:]:
    m = match_concepts(s, extract_candidates(b))
    ids = []
    for name in m:
        e = s.resolve_entity(name)
        if e is not None and e.kind == "concept": ids.append(e.id)
    if ids: seedsets.append(ids)
print(f"seed sets from {len(bodies[-40:])} recent prompts: {len(seedsets)}; sizes {[len(x) for x in seedsets]}")
today, proto, ok = [], [], 0
for ids in seedsets:
    t = time.perf_counter()
    a = ppr_mod.rank_related_for_prompt(s, ids, k=5, kinds=("concept",), include_seeds=True,
                                        clique_weight=2.0, coverage_alpha=3.0)
    today.append(time.perf_counter() - t)
    t = time.perf_counter(); b = proto_rank(s, csr, ids); proto.append(time.perf_counter() - t)
    same_ids = [x["id"] for x in a] == [x["id"] for x in b]
    close = same_ids and all(abs(x["score"] - y["score"]) <= 1e-9 * max(abs(x["score"]), 1e-300) for x, y in zip(a, b))
    exact = a == b
    assert close, (a, b); ok += 1; exact_n = globals().get("exact_n", 0) + int(exact); globals()["exact_n"] = exact_n
print(f"rank_related_for_prompt today (build_adjacency each call): {fmt(stats(today))}")
print(f"prototype over warm cached CSR + overlay: {fmt(stats(proto))}  identical ids+order (scores within 1e-9 rel): {ok}/{len(seedsets)}; bit-exact: {globals().get('exact_n',0)}")
print("load at end:", load())
