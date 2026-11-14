import re, sys, collections
from pathlib import Path
REPO = Path(sys.argv[1]); T = REPO/"tests"
tests = {p.name: p.read_text() for p in sorted(T.glob("*.py"))}
def count(pat):
    hits = {n: len(re.findall(pat, s)) for n, s in tests.items()}
    return sum(hits.values()), sum(1 for v in hits.values() if v)
for m in ("cli", "store"):
    al = r"(?:_?%s(?:_mod|m)?)" % m
    print(f"== tests reading {m} SOURCE or FILE:")
    print("   path literal '%s.py' joined to a src path:" % m, count(r"""[/"']%s\.py["']""" % m))
    print("   source_of(<%s alias>, ...):" % m, count(r"source_of\(%s\s*," % al))
    print("   inspect.getsource[lines](<%s alias>...):" % m, count(r"getsource(?:lines)?\(%s[.)]" % al))
    print("   <%s alias>.__file__:" % m, count(r"\b%s\.__file__" % al))
print("   non-recursive src glob (blind to a subpackage):", [(n, len(re.findall(r"""["']refmatrix["']\)?\.glob\(["']\*\.py""", s))) for n, s in tests.items() if re.search(r"""["']refmatrix["']\)?\.glob\(["']\*\.py""", s)])
def cites(root, exts=(".md",)):
    out = collections.Counter(); files = collections.defaultdict(set)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and ".refmatrix" not in p.parts and "review-output" not in p.parts:
            try: s = p.read_text()
            except Exception: continue
            for m in re.findall(r"\b(cli|store|daemon)\.py:\d+", s):
                out[m] += 1; files[m].add(p)
    return out, files
for label, root, exts in (("workflow/plans", REPO/"workflow/plans", (".md",)), ("workflow (all, minus review-output)", REPO/"workflow", (".md",)), ("docs", REPO/"docs", (".md",)), ("src", REPO/"src", (".py", ".md")), ("tests", REPO/"tests", (".py",))):
    c, f = cites(root, exts)
    print(f"{label}: " + "; ".join(f"{m}.py:NNNN {c[m]} sites in {len(f[m])} files" for m in ("cli", "store", "daemon")))
c, f = cites(REPO/"workflow/plans")
st = collections.Counter(); open_files = []
for p in sorted(f["cli"] | f["store"]):
    m = re.search(r"^\s*status:\s*(\S+)", p.read_text(), re.M); s = m.group(1) if m else "?"
    st[s] += 1
    if s not in ("completed", "complete", "done", "closed", "superseded"): open_files.append((p.relative_to(REPO/"workflow/plans").as_posix(), s, len(re.findall(r"\b(?:cli|store)\.py:\d+", p.read_text()))))
print("plan/spec files citing cli.py:N or store.py:N, by metadata.status:", dict(st))
print("not-completed files:", len(open_files), "sites:", sum(x[2] for x in open_files))
for x in sorted(open_files, key=lambda x: -x[2])[:25]: print("   ", x)
