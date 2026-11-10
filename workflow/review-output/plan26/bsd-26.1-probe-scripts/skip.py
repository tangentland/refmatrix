import sys, tempfile, os
from pathlib import Path
from refmatrix.ingest_gmd import collect_gmd_files
from refmatrix import memory_index as mi
base = Path(tempfile.mkdtemp(dir=sys.argv[1])); d = base/"mem"; d.mkdir()
fm = lambda i: f'---\ngmd: "0.1"\nid: {i}\ntitle: {i}\nmetadata:\n  type: feedback\n---\n# {i} {{#root}}\nbody\n'
(d/"feedback_a.md").write_text(fm("feedback_a"))
ext = base/"elsewhere"; ext.mkdir(); (ext/"feedback_b.md").write_text(fm("feedback_b"))
os.symlink(ext, d/"feedback")                       # symlinked type folder
(d/"feedback_c.gmd").write_text(fm("feedback_c"))   # .gmd memory
(d/"broken.md").symlink_to(base/"nope.md")          # dangling file link
(d/".hidden").mkdir(); (d/".hidden"/"y.md").write_text(fm("y"))
files = collect_gmd_files([d], as_memory=True)
print("bridge took:", sorted(p.name for p in files))
print("index collect:", sorted(e.rel for e in mi.collect(d)))
