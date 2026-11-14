import re, sys, collections
from pathlib import Path
R = Path(sys.argv[1]); S = R/"src/refmatrix"; T = R/"tests"
def files(root, pat="*.py"): return sorted(root.rglob(pat))
m_cli = re.compile(r"""-m["']?,?\s*["']?refmatrix\.cli\b""")
for label, fs in (("src", [f for f in files(S)]), ("tests", files(T)), ("eval+scripts+tools", files(R/"eval") + files(R/"scripts") + files(R/"tools"))):
    hits = [(f, len(m_cli.findall(f.read_text()))) for f in fs]
    print(f"{label}: `-m refmatrix.cli` spawn sites: {sum(h for _, h in hits)} in {sum(1 for _, h in hits if h)} files")
imp = re.compile(r"from refmatrix\.cli import|from refmatrix import [^\n]*\bcli\b|import refmatrix\.cli|from \.cli import|from \. import [^\n]*\bcli\b")
src_imp = [(f.name, i + 1, l.strip()) for f in files(S) if f.name != "cli.py" for i, l in enumerate(f.read_text().splitlines()) if imp.search(l)]
print("src modules importing cli:", len(src_imp)); [print("   ", x) for x in src_imp]
t_imp = [f for f in files(T) if imp.search(f.read_text())]
print("test files importing cli:", len(t_imp))
names = collections.Counter()
for f in files(T):
    for m in re.finditer(r"from refmatrix\.cli import ([^\n]+)", f.read_text()):
        for n in m.group(1).replace("(", "").replace(")", "").split(","):
            n = n.split(" as ")[0].strip()
            if n and not n.startswith("#"): names[n] += 1
print("names imported `from refmatrix.cli import X` in tests:", len(names), names.most_common(16))
std = set(sys.stdlib_module_names)
print("src/refmatrix modules whose stem is a stdlib module name:", sorted(p.stem for p in S.glob("*.py") if p.stem in std))
print("proposed cli module stems vs stdlib:", [n for n in ("memory_cmds","session_cmds","daemon_cmds","hub_cmds","ingest_cmds","search_cmds","query_cmds","store_cmds","admin_cmds") if n in std])
argv0 = [(f.name, i + 1, l.strip()[:110]) for f in files(S) for i, l in enumerate(f.read_text().splitlines()) if re.search(r"sys\.argv\[0\]|argv0\b|_sys\.argv\[0\]", l)]
print("sys.argv[0] readers in src:", len(argv0)); [print("   ", x) for x in argv0[:14]]
