"""Q1b: where build_adjacency's 1.3 s goes, and a vectorised (numpy) CSR build prototype that
produces the same edge set. Asserted identical as (u, v) sets with weights equal to 1e-9 rel."""
import time
from common import *
import numpy as np
from refmatrix import pagerank as pr
from refmatrix.store import DENOTES, DENOTES_TERM_LINKAGES, _CONCEPT_SHIFT, _ENTITY_MASK

print("load at start:", load())
s = open_store(); con = s._connect(); pid = s._partition_id

def phases():
    t = {}; t0 = time.perf_counter()
    op = {int(r[0]) for r in con.execute("SELECT id, name FROM entities WHERE lower(name) LIKE 'session%' OR lower(name) LIKE 'digest%'").fetchall() if pr._OPERATIONAL_RE.match(str(r[1]))}
    t["op_ids_sql"] = time.perf_counter() - t0; t0 = time.perf_counter()
    frag = s._load_fragment("mentions"); n = 0
    for packed in frag: n += 1
    t["iterate_mentions_bits_only"] = time.perf_counter() - t0; t0 = time.perf_counter()
    skip = s.get_linkage_id("mentions")
    rows = con.execute("SELECT el.concept_id, el.entity_id, el.weight, el.linkage_id FROM entity_links el "
                       "JOIN entities ce ON ce.id = el.concept_id AND ce.partition_id = ? "
                       "JOIN entities ee ON ee.id = el.entity_id AND ee.partition_id = ? WHERE el.linkage_id <> ?",
                       (pid, pid, skip)).fetchall()
    t["typed_rows_sql_fetchall"] = time.perf_counter() - t0
    return t, len(rows), n
ph = [phases() for _ in range(5)]
for k in ph[0][0]:
    print(f"  phase {k}: {fmt(stats([p[0][k] for p in ph]))}")
print("  typed rows:", ph[0][1], "mention bits:", ph[0][2])

def vec_build(st, link_weight=2.0):
    con = st._connect(); pid = st._partition_id; duck = con._duck
    op = np.array(sorted(int(r[0]) for r in con.execute(
        "SELECT id, name FROM entities WHERE lower(name) LIKE 'session%' OR lower(name) LIKE 'digest%'").fetchall()
        if pr._OPERATIONAL_RE.match(str(r[1]))), dtype=np.int64)
    arr = np.frombuffer(st._load_fragment("mentions").to_array(), dtype=np.uint64)
    a1 = (arr >> np.uint64(_CONCEPT_SHIFT)).astype(np.int64); b1 = (arr & np.uint64(_ENTITY_MASK)).astype(np.int64)
    w1 = np.ones(len(arr))
    skip = st.get_linkage_id("mentions")
    d = duck.execute("SELECT el.concept_id, el.entity_id, coalesce(el.weight, 1.0) AS w, el.linkage_id FROM entity_links el "
                     "JOIN entities ce ON ce.id = el.concept_id AND ce.partition_id = ? "
                     "JOIN entities ee ON ee.id = el.entity_id AND ee.partition_id = ? WHERE el.linkage_id <> ?",
                     [pid, pid, skip]).fetchnumpy()
    c = d["concept_id"].astype(np.int64); e = d["entity_id"].astype(np.int64)
    w = link_weight * np.abs(d["w"].astype(np.float64)); lk = d["linkage_id"].astype(np.int64)
    try: den = st.get_linkage_id(DENOTES)
    except Exception: den = None
    term = []
    for ln in DENOTES_TERM_LINKAGES:
        try: term.append(st.get_linkage_id(ln))
        except Exception: pass
    a2, b2, w2 = c, e, w
    if den is not None:
        isden = lk == den
        fold = {}
        for cc, ee in zip(c[isden].tolist(), e[isden].tolist()): fold.setdefault(cc, []).append(ee)
        keep = ~isden
        c, e, w, lk = c[keep], e[keep], w[keep], lk[keep]
        hit = np.isin(e, np.fromiter(fold.keys(), dtype=np.int64, count=len(fold))) & ~np.isin(lk, term)
        xa, xb, xw = [], [], []
        for cc, ee, ww in zip(c[hit].tolist(), e[hit].tolist(), w[hit].tolist()):
            tg = fold[ee]
            for t_ in tg: xa.append(cc); xb.append(t_); xw.append(ww / len(tg))
        a2 = np.concatenate([c[~hit], np.array(xa, dtype=np.int64)])
        b2 = np.concatenate([e[~hit], np.array(xb, dtype=np.int64)])
        w2 = np.concatenate([w[~hit], np.array(xw, dtype=np.float64)])
    A = np.concatenate([a1, a2]); B = np.concatenate([b1, b2]); W = np.concatenate([w1, w2])
    m = (A != B) & (W > 0) & ~np.isin(A, op) & ~np.isin(B, op)
    A, B, W = A[m], B[m], W[m]
    U = np.concatenate([A, B]); V = np.concatenate([B, A]); WW = np.concatenate([W, W])
    o = np.lexsort((V, U)); U, V, WW = U[o], V[o], WW[o]
    new = np.ones(len(U), dtype=bool); new[1:] = (U[1:] != U[:-1]) | (V[1:] != V[:-1])
    starts = np.flatnonzero(new)
    U, V, WW = U[starts], V[starts], np.add.reduceat(WW, starts)
    nodes, first = np.unique(U, return_index=True)
    offsets = np.append(first, len(U)).astype(np.int64)
    index = dict(zip(nodes.tolist(), range(len(nodes))))
    return pr.CSRAdjacency(index, offsets, V, WW)

st_vec, vcsr = timeit(lambda: vec_build(s), n=7, warm=1)
print("vectorised CSR build (fragment already loaded):", fmt(st_vec))
st_vec2, _ = timeit(lambda: vec_build(open_store()), n=5)
print("vectorised CSR build (fresh Store):", fmt(st_vec2))
# identity check vs the production build
adj = pr.build_adjacency(s); ref = pr.CSRAdjacency.from_dict(adj)
def canon(c):
    rows = np.repeat(np.fromiter(c._index.keys(), dtype=np.int64, count=len(c._index)), np.diff(c._offsets))
    o = np.lexsort((c._nbrs, rows)); return rows[o], c._nbrs[o], c._wts[o]
X, Y = canon(vcsr), canon(ref)
assert len(vcsr) == len(ref), (len(vcsr), len(ref))
assert np.array_equal(X[0], Y[0]) and np.array_equal(X[1], Y[1])
assert np.allclose(X[2], Y[2], rtol=1e-9, atol=0)
print(f"IDENTICAL edge set: nodes {len(vcsr)} directed edges {len(X[0])}; max |dw| {np.max(np.abs(X[2]-Y[2])):.3g}")
print("load at end:", load())
