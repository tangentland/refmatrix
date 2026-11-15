"""31.1 probe: where does a list-valued id / title raise? Throwaway store, dev code, no daemon."""
import sys, tempfile, shutil, traceback, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from refmatrix.store import Store
from refmatrix.ingest_gmd import ingest_gmd_paths, parse_gmd, plan_memory_refresh

GOOD = '---\ngmd: "0.1"\nid: good\ntitle: "good"\ntags: [t]\n---\n\n# Good {#root}\n\nBody about frobnication.\n'
SHAPES = {
    "id_inline_list": '---\ngmd: "0.1"\nid: [a, b]\ntitle: "bad"\ntags: [t]\n---\n\n# Bad {#root}\n\nx\n',
    "id_block_list": '---\ngmd: "0.1"\nid:\n  - a\n  - b\ntitle: "bad"\n---\n\n# Bad {#root}\n\nx\n',
    "id_empty": '---\ngmd: "0.1"\nid:\ntitle: "bad"\n---\n\n# Bad {#root}\n\nx\n',
    "id_empty_brackets": '---\ngmd: "0.1"\nid: []\ntitle: "bad"\n---\n\n# Bad {#root}\n\nx\n',
    "title_inline_list": '---\ngmd: "0.1"\nid: tbad\ntitle: [a, b]\n---\n\n# Bad {#root}\n\nx\n',
    "title_block_list": '---\ngmd: "0.1"\nid: tbad\ntitle:\n  - a\n  - b\n---\n\n# Bad {#root}\n\nx\n',
    "title_empty": '---\ngmd: "0.1"\nid: tbad\ntitle:\n---\n\n# Bad {#root}\n\nx\n',
    "plain_no_gmd_id_list": '---\nid: [a, b]\n---\n\n# Plain\n\nx\n',
}
def last_frame(exc):
    tb = traceback.extract_tb(exc.__traceback__)
    f = tb[-1]
    inner = [x for x in tb if "refmatrix" in x.filename]
    g = inner[-1] if inner else f
    return f"{Path(g.filename).name}:{g.lineno} in {g.name}"

for backend in ("duckdb",):
    for name, text in SHAPES.items():
        for mode in ("docs_strict", "docs_lenient", "memory"):
            base = Path(tempfile.mkdtemp(prefix="p311.", dir="/tmp")).resolve()
            try:
                d = base / "docs"; d.mkdir()
                (d / "good.md").write_text(GOOD)
                (d / "bad.md").write_text(text)
                s = Store(base / ".refmatrix"); s.init()
                paths = sorted(d.glob("*.md"))
                try:
                    doc = parse_gmd(d / "bad.md", lenient=(mode != "docs_strict"), memory_ids=(mode == "memory"))
                    pd = f"parse ok doc_id={doc.doc_id!r} title={doc.title!r}" if doc else "parse None"
                except Exception as e:
                    pd = f"parse RAISED {type(e).__name__}: {e}"
                try:
                    st = ingest_gmd_paths(s, paths, lenient=(mode != "docs_strict"), project_root=base,
                                          as_memory=(mode == "memory"))
                    out = f"OK docs={st.docs} unparseable={len(st.skipped_unparseable)} non_gmd={st.skipped_non_gmd}"
                    good = s.get_entity("memory" if mode == "memory" else "doc", "good")
                    out += f" good_row={'yes' if good else 'NO'}"
                    names = [r[0] for r in s._connect().execute("SELECT name FROM entities WHERE kind IN ('doc','memory') ORDER BY name").fetchall()]
                    out += f" doc_rows={names}"
                except Exception as e:
                    out = f"RAISED {type(e).__name__}: {e} @ {last_frame(e)}"
                print(f"{name:22s} {mode:13s} | {pd} | ingest: {out}")
                if mode == "memory":
                    try:
                        plan_memory_refresh(s, paths, project_root=base)
                        print(f"{name:22s} {'dry-run':13s} | plan_memory_refresh OK")
                    except Exception as e:
                        print(f"{name:22s} {'dry-run':13s} | plan_memory_refresh RAISED {type(e).__name__}: {e} @ {last_frame(e)}")
                try: s.close()
                except Exception: pass
            finally:
                shutil.rmtree(base, ignore_errors=True)

# lint on the same shapes
print("---- lint")
for name, text in SHAPES.items():
    base = Path(tempfile.mkdtemp(prefix="p311l.", dir="/tmp")).resolve()
    try:
        (base / "good.md").write_text(GOOD)
        (base / "bad.md").write_text(text)
        r = subprocess.run(["python3", str(Path(__file__).resolve().parents[3] / "tools" / "gmd" / "lint.py"), str(base)],
                           capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()
        print(f"{name:22s} exit={r.returncode} | {' / '.join(x[-150:] for x in tail[-2:])}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
