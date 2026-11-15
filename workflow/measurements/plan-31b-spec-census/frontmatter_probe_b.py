"""31.1 probe b: other per-file shapes that might fail the batch, and the env-knob input."""
import os, sys, tempfile, shutil, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from refmatrix.store import Store
from refmatrix.ingest_gmd import ingest_gmd_paths

GOOD = '---\ngmd: "0.1"\nid: good\ntitle: "good"\ntags: [t]\n---\n\n# Good {#root}\n\nBody about frobnication.\n'
H = '---\ngmd: "0.1"\n'
T = '---\n\n# Bad {#root}\n\nx\n'
SHAPES = {
    "id_nul": (H + 'id: a\x00b\ntitle: "t"\n' + T).encode(),
    "title_nul": (H + 'id: tn\ntitle: "t\x00u"\n' + T).encode(),
    "tags_string": (H + 'id: ts\ntitle: "t"\ntags: solo\n' + T).encode(),
    "imports_string": (H + 'id: imps\ntitle: "t"\nimports: solo\n' + T).encode(),
    "gmd_list": b'---\ngmd: [0.1]\nid: gl\ntitle: "t"\n---\n\n# Bad {#root}\n\nx\n',
    "id_hash": (H + 'id: a#b\ntitle: "t"\n' + T).encode(),
    "non_utf8": H.encode() + b'id: nu\ntitle: "\xff\xfe"\n' + T.encode(),
    "unclosed_fm": (H + 'id: uf\ntitle: "t"\n\n# Bad {#root}\n\nx\n').encode(),
    "empty_file": b"",
    "only_delim": b"---\n",
    "body_nul": (H + 'id: bn\ntitle: "t"\n---\n\n# Bad {#root}\n\nx\x00y {#p}\n').encode(),
}
def frame(exc):
    tb = traceback.extract_tb(exc.__traceback__)
    inner = [x for x in tb if "refmatrix" in x.filename]
    g = inner[-1] if inner else tb[-1]
    return f"{Path(g.filename).name}:{g.lineno} in {g.name}"

def run(name, data, mode, env=None):
    base = Path(tempfile.mkdtemp(prefix="p311b.", dir="/tmp")).resolve()
    old = {}
    try:
        for k, v in (env or {}).items():
            old[k] = os.environ.get(k); os.environ[k] = v
        d = base / "docs"; d.mkdir()
        (d / "good.md").write_text(GOOD)
        if data is not None:
            (d / "bad.md").write_bytes(data)
        s = Store(base / ".refmatrix"); s.init()
        try:
            st = ingest_gmd_paths(s, sorted(d.glob("*.md")), lenient=True, project_root=base,
                                  as_memory=(mode == "memory"))
            out = f"OK docs={st.docs} unparseable={[e for _p, e in st.skipped_unparseable]}"
        except Exception as e:
            out = f"RAISED {type(e).__name__}: {str(e)[:90]} @ {frame(e)}"
        print(f"{name:16s} {mode:8s} | {out}")
        s.close()
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        shutil.rmtree(base, ignore_errors=True)

for name, data in SHAPES.items():
    for mode in ("docs", "memory"):
        run(name, data, mode)
run("env_node_yield=x", None, "docs", {"RMX_INGEST_NODE_YIELD_EVERY": "x"})
