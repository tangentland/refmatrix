"""The draft tier rule of task-29.4 R1, applied to tier_signals.py's output. Static; runs no test.

usage: tier_rule.py <repo> <tiers.json from tier_signals.py> <wallclock_census.py output>
"""
import json, re, sys, collections
from pathlib import Path
REPO = Path(sys.argv[1]); res = json.load(open(sys.argv[2]))
conf = (REPO / "tests" / "conftest.py").read_text()
clone_only = set(re.findall(r'"tests/(test_\w+\.py)::', conf))
WC = {}
for line in open(sys.argv[3]):
    m = re.match(r"\s*(\d+) (test_\S+\.py):", line)
    if m: WC[m.group(2)] = int(m.group(1))
# Non-literal upper bounds (wallclock_nonliteral.py at f3709d2): three more timing files.
# test_bug212_r4_red.py holds only the hang guard (`< HANG_BOUND_S`) and stays out.
for f, n in (("test_plan3_remedy_r7.py", 2), ("test_task3_5_r8_remedy.py", 1), ("test_task3_6_r9_remedy.py", 4)):
    WC[f] = WC.get(f, 0) + n
LISTED = {"test_search_hooks.py", "test_bug230_repo_scope_gate.py"}
PROC = ("spawn", "daemon", "socket", "hub", "models")
def tier(f, r):
    if f in clone_only or r["own"]["realhome"] or f in LISTED: return "devtree"
    if f in WC: return "timing"
    if any(r["sig"][k] for k in PROC): return "daemon"
    return "unit"
by = collections.defaultdict(list)
for f, r in res.items(): by[tier(f, r)].append(f)
total = sum(r["tests"] for r in res.values())
for t in ("unit", "daemon", "devtree", "timing"):
    n = sum(res[f]["tests"] for f in by[t])
    print(f"{t:8s} files={len(by[t]):4d} tests={n:5d}  ({100 * n / total:.1f}%)")
print("total", sum(len(v) for v in by.values()), total, "| timing asserts in the allow list:", sum(WC.values()))
d = by["daemon"]
print("daemon tier: real daemon/serve signal:", sum(1 for f in d if res[f]["sig"]["daemon"]), "files; model signal:",
      sum(1 for f in d if res[f]["sig"]["models"]), "; only via a tests/ helper:",
      sum(1 for f in d if not any(res[f]["own"][k] for k in PROC)))
print("all tiers: real daemon/serve signal:", sum(1 for f in res if res[f]["sig"]["daemon"]),
      "| model signal:", sum(1 for f in res if res[f]["sig"]["models"]))
print("devtree files:", sorted(by["devtree"]))
print("timing files:", sorted(by["timing"]))
