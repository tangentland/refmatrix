import sys, shutil, tempfile, random
from pathlib import Path
from refmatrix import memory_index as mi
src = Path(sys.argv[1]); hits = 0; runs = 0
orig = mi._render_organised
for name in ["refmatrix","viascope","cliquedb","cliquet"]:
    for budget in (24000, 40000, 8000, 3000):
        d = Path(tempfile.mkdtemp(dir=sys.argv[2])) / name
        shutil.copytree(src / name, d, symlinks=True)
        (d / ".memory-layout").write_text('{"layout": 1}')
        lines = mi._index_lines(d); prose = mi._prose_lines(lines)
        for i in range(3):
            text = orig(d, mi.collect(d), prose, max_lines=200, max_chars=budget)
            after = set(text.splitlines()); runs += 1
            if [p for p in prose if p not in after]: hits += 1
print(f"guard condition true in {hits} of {runs} renders")
