"""Map the test patch targets and private reads on `refmatrix.cli` / `refmatrix.store` onto the
proposed cli modules. Reads private.json (private_census.py) and cli_assign.json (cli_map.py)
from the current directory. Static; runs no test.
"""
import json, collections
d = json.load(open("private.json")); a = json.load(open("cli_assign.json"))
pc = collections.Counter(p[2] for p in d["patches"] if p[1] == "cli")
print("== tests patching refmatrix.cli attributes:", sum(pc.values()), "sites,", len(pc), "names")
for n, c in pc.most_common():
    print(f"   {n:28s} {c:4d}  -> {a.get(n, '(module-level name, not a def)')}")
tc = collections.Counter(u[2] for u in d["tests"] if u[1] == "cli")
moved = {n: c for n, c in tc.items() if a.get(n) not in ("_core", None)}
print("tests reading cli privates:", sum(tc.values()), "sites,", len(tc), "names; names the proposed map moves OUT of the core:",
      len(moved), "names,", sum(moved.values()), "sites")
print("   by target module:", collections.Counter(a[n] for n in moved).most_common())
ps = collections.Counter(p[2] for p in d["patches"] if p[1] == "store")
print("tests patching refmatrix.store module attributes:", sum(ps.values()), "sites;", ps.most_common(12))
ts = collections.Counter(u[2] for u in d["tests"] if u[1] == "store")
print("tests reading store module privates:", sum(ts.values()), "sites;", ts.most_common(12))
