"""Static census of tests/ for the plan-29 29.4 spec. Reads files only; runs no test."""
import ast, re, sys, json, collections
from pathlib import Path
REPO = Path(sys.argv[1]); T = REPO / "tests"
collect = Path(sys.argv[2]).read_text().splitlines()
per_file = collections.Counter(l.split("::")[0] for l in collect if "::" in l)

TIME_CALLS = {"time", "monotonic", "perf_counter", "monotonic_ns", "perf_counter_ns"}
ELAPSED_NAMES = re.compile(r"^(elapsed|took|wall|dt|duration|dur|secs|seconds|t_?total|spent|waited)\w*$", re.I)

def is_time_call(n):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in TIME_CALLS) or \
           (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in TIME_CALLS)

def timeish(n, elapsed_vars):
    """expression reads a clock difference or a var assigned from one"""
    for sub in ast.walk(n):
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Sub) and (is_time_call(sub.left) or is_time_call(sub.right)):
            return True
        if isinstance(sub, ast.Name) and sub.id in elapsed_vars:
            return True
    return False

def num(n):
    return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)

def census_file(p):
    src = p.read_text()
    tree = ast.parse(src)
    out = {"lines": src.count("\n") + 1}
    # vars assigned from a clock difference, per file (coarse)
    ev = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = n.value
            if any(isinstance(s, ast.BinOp) and isinstance(s.op, ast.Sub) and (is_time_call(s.left) or is_time_call(s.right) or (isinstance(s.right, ast.Name) and s.right.id in ("t0","start","t","began","t_start","started")) and is_time_call(s.left)) for s in ast.walk(v)):
                ev.add(n.targets[0].id)
    wc = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assert):
            for c in ast.walk(n.test):
                if isinstance(c, ast.Compare):
                    ops = c.ops; parts = [c.left] + c.comparators
                    for i, op in enumerate(ops):
                        l, r = parts[i], parts[i+1]
                        if isinstance(op, (ast.Lt, ast.LtE)) and num(r) and timeish(l, ev):
                            wc.append((n.lineno, "upper", r.value))
                        elif isinstance(op, (ast.Gt, ast.GtE)) and num(l) and timeish(r, ev):
                            wc.append((n.lineno, "upper", l.value))
    out["wallclock"] = sorted(set(wc))
    # signals
    sig = collections.Counter()
    pats = {
      "popen": r"\bsubprocess\.(Popen|run|check_output|check_call|call)\b|\bPopen\(",
      "daemon_start_cli": r"[\"']daemon[\"'],\s*[\"']start[\"']|daemon start",
      "start_daemon_fn": r"\b(start_daemon|spawn_daemon|ensure_daemon|launch_daemon)\(",
      "serve_forever": r"\bserve_forever\b|\bserve_foreground\b",
      "make_daemon": r"\bmake_daemon\b",
      "Daemon_ctor": r"\b(dm|daemon|daemon_mod)\.Daemon\(|\bDaemon\(",
      "stop_daemon": r"\bstop_daemon\(",
      "hub_start": r"hub[\"'],\s*[\"']start|\bHub\(|run_hub|hub\.serve",
      "mkdtemp": r"\bmkdtemp\(",
      "mkdtemp_tmp": r"mkdtemp\([^)]*dir\s*=\s*[\"']/(private/)?tmp",
      "socket_srv": r"socket\.socket\(|AF_UNIX",
      "threading": r"threading\.Thread\(",
      "sleep": r"\btime\.sleep\(|\b_time\.sleep\(|\bsleep\(",
      "CliRunner": r"\bCliRunner\(",
      "real_models": r"SentenceTransformer|CrossEncoder|modelsrv|model_worker|subproc\b",
      "sys_executable": r"sys\.executable",
      "launchctl": r"\blaunchctl\b",
      "git_cmd": r"[\"']git[\"']",
      "repo_root_reads": r"_REPO\b|REPO\b|parents\[1\]",
    }
    for k, pat in pats.items():
        sig[k] = len(re.findall(pat, src))
    out["sig"] = dict(sig)
    # imports of refmatrix modules
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            if n.module == "refmatrix":
                for a in n.names: mods.add(a.name)
            elif n.module.startswith("refmatrix."):
                mods.add(n.module.split(".")[1])
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("refmatrix."):
                    mods.add(a.name.split(".")[1])
                elif a.name == "refmatrix":
                    mods.add("__init__")
    out["imports"] = sorted(mods)
    return out

res = {}
for p in sorted(T.glob("test_*.py")):
    r = census_file(p); r["tests"] = per_file.get(f"tests/{p.name}", 0); res[p.name] = r
json.dump(res, open(sys.argv[3], "w"), indent=0)
n = len(res)
print("test files", n, "collected", sum(r["tests"] for r in res.values()), "lines", sum(r["lines"] for r in res.values()))
print("files with 0 collected:", [k for k, r in res.items() if r["tests"] == 0])
wcf = {k: r for k, r in res.items() if r["wallclock"]}
print("wall-clock upper-bound asserts (AST):", sum(len(r["wallclock"]) for r in wcf.values()), "in", len(wcf), "files; tests in those files:", sum(r["tests"] for r in wcf.values()))
for k, r in sorted(wcf.items()):
    print("  ", k, r["tests"], "tests:", ", ".join(f"L{l}<{v}" for l, _, v in r["wallclock"]))
for key in ["popen","daemon_start_cli","start_daemon_fn","serve_forever","make_daemon","Daemon_ctor","stop_daemon","hub_start","mkdtemp","mkdtemp_tmp","socket_srv","threading","sleep","CliRunner","sys_executable","launchctl","git_cmd"]:
    fs = [k for k, r in res.items() if r["sig"][key]]
    print(f"{key:18s} files={len(fs):4d} hits={sum(res[k]['sig'][key] for k in fs):5d} tests_in_files={sum(res[k]['tests'] for k in fs)}")
imp = collections.Counter()
for r in res.values():
    for m in r["imports"]: imp[m] += 1
print("import fan-in (test files importing refmatrix.<m>):", imp.most_common(40))
print("files importing no refmatrix module:", sum(1 for r in res.values() if not r["imports"]))
