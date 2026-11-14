"""Tier census for the 29.4 spec: static, ordered rule; no test runs."""
import ast, re, sys, json, collections
from pathlib import Path
REPO = Path(sys.argv[1]); T = REPO / "tests"
collect = Path(sys.argv[2]).read_text().splitlines()
per_file = collections.Counter(l.split("::")[0].split("/")[-1] for l in collect if "::" in l)
WC = {}
for line in Path(sys.argv[3]).read_text().splitlines():
    m = re.match(r"\s*(\d+) (test_\S+\.py):", line)
    if m: WC[m.group(2)] = int(m.group(1))
SIG = {
 "spawn":  r"\bsubprocess\.(Popen|run|check_output|check_call|call)\b|\bos\.(fork|posix_spawn|execv\w*|system)\b|\bmultiprocessing\b|\bpytester\b|\brunpytest",
 "daemon": r"\bspawn_daemon_subprocess\b|\bSandboxDaemon\b|[\"']daemon[\"'],\s*[\"']start[\"']|\bserve_forever\b|\bserve_foreground\b|\b_serve\(",
 "socket": r"\bsocket\.socket\(|\bsocketserver\b|\bAF_UNIX\b|\buvicorn\b|\bOpDispatcher\b",
 "hub":    r"[\"']hub[\"'],\s*[\"']start[\"']|\bhub(_mod)?\.(serve|run|main)\b",
 "models": r"\bSentenceTransformer\b|\bCrossEncoder\b|\bmodels_local\b|\bstart_worker\b|\bSharedWorkerClient\b|\bSubprocWorker\b|\bmodelsrv\.\w*serve",
 "realhome": r"\bRMX_SANDBOX_REAL_HOME\b|\breal_home\(",
 "repo_scope": r"lint-gmd\.sh|\.refmatrix_ignore|install-hooks[\"'],\s*[\"']--check|\.venv-eval",
 "sleep": r"\bsleep\(",
 "mkdtemp_tmp": r"mkdtemp\([^)]*dir\s*=\s*[\"']/(private/)?tmp",
 "fixed_port": r"\bport\s*=\s*\d{4,5}\b|\(\s*[\"']127\.0\.0\.1[\"']\s*,\s*\d{4,5}\s*\)",
}
src = {p.name: p.read_text() for p in sorted(T.glob("*.py"))}
def helpers(name):
    out = set()
    try: tree = ast.parse(src[name])
    except SyntaxError: return out
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            if n.module == "tests":
                out |= {a.name + ".py" for a in n.names}
            elif n.module.startswith("tests."):
                out.add(n.module.split(".")[1] + ".py")
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("tests."): out.add(a.name.split(".")[1] + ".py")
    return {h for h in out if h in src}
def closure(name):
    seen = {name}; todo = [name]
    while todo:
        for h in helpers(todo.pop()):
            if h not in seen: seen.add(h); todo.append(h)
    return seen
clone_only = set(re.findall(r'"tests/(test_\w+\.py)::', src["conftest.py"]))
res = {}
for name in src:
    if not name.startswith("test_"): continue
    cl = closure(name)
    s = {k: sum(len(re.findall(p, src[c])) for c in cl) for k, p in SIG.items()}
    own = {k: len(re.findall(p, src[name])) for k, p in SIG.items()}
    if name in clone_only or own["realhome"] or own["repo_scope"]: tier = "devtree"
    elif name in WC: tier = "timing"
    elif s["spawn"] or s["daemon"] or s["socket"] or s["hub"] or s["models"]: tier = "daemon"
    else: tier = "unit"
    res[name] = dict(tier=tier, tests=per_file[name], sig=s, own=own, helpers=sorted(cl - {name}))
by = collections.defaultdict(list)
for k, r in res.items(): by[r["tier"]].append(k)
tot_f = tot_t = 0
for t in ("unit", "daemon", "devtree", "timing"):
    fs = by[t]; nt = sum(res[f]["tests"] for f in fs); tot_f += len(fs); tot_t += nt
    print(f"{t:8s} files={len(fs):4d} tests={nt:5d}")
print("total", tot_f, tot_t)
print("devtree files:", [(f, res[f]["tests"], "clone_only" if f in clone_only else "", res[f]["own"]["realhome"], res[f]["own"]["repo_scope"]) for f in sorted(by["devtree"])])
print("timing files that would otherwise be unit:", [f for f in by["timing"] if not any(res[f]["sig"][k] for k in ("spawn","daemon","socket","hub","models"))])
d = by["daemon"]
for k in ("spawn","daemon","socket","hub","models"):
    fs = [f for f in d if res[f]["sig"][k]]
    print(f"daemon-tier signal {k:7s}: files={len(fs)} tests={sum(res[f]['tests'] for f in fs)}")
real = [f for f in res if res[f]["sig"]["daemon"]]
print("files with a REAL daemon/serve signal (any tier):", len(real), "tests", sum(res[f]["tests"] for f in real))
only_helper = [f for f in d if not any(res[f]["own"][k] for k in ("spawn","daemon","socket","hub","models"))]
print("daemon tier ONLY via a tests/ helper:", len(only_helper), "tests", sum(res[f]["tests"] for f in only_helper), only_helper[:8])
print("mkdtemp(dir=/tmp) own-file sites:", sum(res[f]["own"]["mkdtemp_tmp"] for f in res), "in", sum(1 for f in res if res[f]["own"]["mkdtemp_tmp"]), "files; helper modules:", {n: len(re.findall(SIG['mkdtemp_tmp'], s)) for n, s in src.items() if not n.startswith('test_') and re.search(SIG['mkdtemp_tmp'], s)})
print("fixed-port literal files:", [(f, res[f]["own"]["fixed_port"]) for f in res if res[f]["own"]["fixed_port"]])
print("sleep sites:", sum(res[f]["own"]["sleep"] for f in res), "in", sum(1 for f in res if res[f]["own"]["sleep"]), "files; unit-tier files with sleep:", sum(1 for f in by["unit"] if res[f]["own"]["sleep"]))
big = sorted(((res[f]["tests"], f) for f in by["unit"]), reverse=True)[:6]
print("largest unit files:", big)
json.dump(res, open(sys.argv[4], "w"), indent=0)
print("helper modules in tests/:", [n for n in src if not n.startswith("test_")])
