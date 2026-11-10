"""Hook-precedence probes: clear-a-hook, long hand-edited hook survives N renders?, renamed memory."""
import io, json, sys, tempfile
from pathlib import Path
from refmatrix import memory_index as mi

def mk(d, stem, title, body="Derived first prose line."):
    (d / f"{stem}.md").write_text(f"---\nid: {stem}\ntitle: \"{title}\"\nmetadata:\n  type: feedback\n---\n# {title}\n\n{body}\n")

def hooks_now(d):
    return {e.rel: e.hook for e in mi.collect(d)}

for organised in (False, True):
    print(f"===== organised={organised} ({mi.__file__})")
    d = Path(tempfile.mkdtemp(dir=sys.argv[1]))
    if organised:
        (d / ".memory-layout").write_text('{"layout": 1}')
    mk(d, "feedback_a", "Short A"); mk(d, "feedback_b", "Short B")
    mi.write(d, out=io.StringIO())
    # 1. curate hook of a by hand
    t = (d / "MEMORY.md").read_text().replace("— Derived first prose line.", "— CURATED by hand", 1)
    (d / "MEMORY.md").write_text(t); mi.write(d, out=io.StringIO())
    print("1 curated:", hooks_now(d))
    # 2. user clears the hook in the index (delete ' — CURATED by hand')
    t = (d / "MEMORY.md").read_text().replace(" — CURATED by hand", "", 1)
    (d / "MEMORY.md").write_text(t); mi.write(d, out=io.StringIO())
    print("2 after clearing in index:", hooks_now(d)["feedback_a.md"])
    # 3. long hand-written hook: survives how many renders?
    long = "LONGCURATED " + "x" * 230 + " END"
    t = (d / "MEMORY.md").read_text().splitlines()
    t = [ (f"- [Short B](feedback_b.md) — {long}" if l.startswith("- [Short B]") else l) for l in t]
    (d / "MEMORY.md").write_text("\n".join(t) + "\n")
    for i in range(3):
        mi.write(d, out=io.StringIO())
        side = json.loads((d / ".memory_hooks.json").read_text())
        v = side.get("feedback_b.md") or side.get("feedback_b")
        print(f"3 render {i+1}: sidecar hook len={len(v)} has END={v.endswith('END')}")
