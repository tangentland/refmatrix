import json, collections, statistics, sys
L="/Users/tholley/claude_tools/refmatrix/.refmatrix/"
def pct(xs,p):
    xs=sorted(xs); return xs[min(len(xs)-1,int(p*len(xs)))] if xs else None
# query.log
by=collections.defaultdict(list); days=collections.defaultdict(collections.Counter)
for line in open(L+"query.log",errors="replace"):
    try: r=json.loads(line)
    except Exception: continue
    ts=r.get("ts","");
    if ts<"2026-11-07": continue
    k=(r.get("kind"),r.get("source"))
    by[k].append(r.get("latency_ms") or 0); days[k][ts[:10]]+=1
print("query.log since 2026-11-07")
for k,v in sorted(by.items(), key=lambda kv:-len(kv[1])):
    print(k, "n=",len(v),"p50=",pct(v,.5),"p90=",pct(v,.9),"max=",max(v), "per-day=",dict(sorted(days[k].items())))
# cli.log argv[0] counts
c=collections.Counter(); lat=collections.defaultdict(list); first=None
for line in open(L+"cli.log",errors="replace"):
    try: r=json.loads(line)
    except Exception: continue
    ts=r.get("ts","")
    if ts<"2026-11-07": continue
    first=first or ts
    a=r.get("argv") or []
    key=" ".join(a[:2]) if a and a[0] in ("memory","graph","daemon","focus","hub") else (a[0] if a else "")
    c[key]+=1; lat[key].append(r.get("latency_ms") or 0)
print("\ncli.log since",first)
for k,n in c.most_common(40):
    print(f"{k:30s} n={n:6d} p50={pct(lat[k],.5)} p90={pct(lat[k],.9)}")
