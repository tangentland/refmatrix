"""Estimate how often the adjacency disk tier (keyed on facts.log size) would be fresh at a
scan-prompt: was there any store-write signal between consecutive scan-prompts? Read-only text."""
import json, bisect
L = "/Users/tholley/claude_tools/refmatrix/.refmatrix/"
scans = []
for line in open(L + "query.log", errors="replace"):
    try: r = json.loads(line)
    except Exception: continue
    if r.get("kind") == "scan" and r.get("ts", "") >= "2026-11-07": scans.append(r["ts"])
writes = []
W = ("watch flush", "periodic flush", "ingest-progress", "compaction", "compacted")
for line in open(L + "rmxd.log", errors="replace"):
    ts = line[:19]
    if ts >= "2026-11-07" and any(w in line for w in W): writes.append(ts)
# CLI write commands from cli.log (session indexer, save-state, ingest-gmd, sync, memory add...)
WC = {"session", "save-state", "ingest-gmd", "sync", "ingest", "reingest", "memory"}
for line in open(L + "cli.log", errors="replace"):
    try: r = json.loads(line)
    except Exception: continue
    a = r.get("argv") or []
    if r.get("ts", "") >= "2026-11-07" and a and a[0] in WC and not (a[0] == "memory" and a[1:2] and a[1] in ("recall", "get", "list", "search")):
        writes.append(r["ts"])
writes.sort()
fresh = stale = 0; gaps = []
for prev, cur in zip(scans, scans[1:]):
    i = bisect.bisect_right(writes, prev); j = bisect.bisect_right(writes, cur)
    if j > i: stale += 1
    else: fresh += 1
print(f"scan-prompts since 2026-11-07: {len(scans)}; consecutive pairs with NO write signal between "
      f"(disk tier would hit): {fresh}; with a write between (miss -> rebuild): {stale}")
print("write signals counted:", len(writes))

def rate(sig):
    sig = sorted(sig); f = s = 0
    for prev, cur in zip(scans, scans[1:]):
        if bisect.bisect_right(sig, cur) > bisect.bisect_right(sig, prev): s += 1
        else: f += 1
    return f, s
wf = [l[:19] for l in open(L + "rmxd.log", errors="replace") if l[:19] >= "2026-11-07" and "watch flush" in l]
ing = [l[:19] for l in open(L + "rmxd.log", errors="replace") if l[:19] >= "2026-11-07" and "ingest-progress" in l and "-skip" not in l]
sess = []
for line in open(L + "cli.log", errors="replace"):
    try: r = json.loads(line)
    except Exception: continue
    a = r.get("argv") or []
    if r.get("ts", "") >= "2026-11-07" and a and a[0] == "session": sess.append(r["ts"])
print("watch-flush only (code/doc edits):", rate(wf))
print("non-skip ingest only:", rate(ing))
print("session indexer only:", rate(sess))
print("watch-flush + non-skip ingest (excl. session indexer):", rate(wf + ing))
