"""M5 — subject representation per store (hypertree exploration, spike 2026-10-20).

Read-only, on COPIES. Two inputs, per the doc's M5 row:
1. Louvain modularity of the entity projection, RE-MEASURED on today's snapshot copies with the
   2026-10-07 spike's own `measure.py` (unchanged code, its seed 20261007, so the numbers are
   comparable with spike-2026-10-07-adjacency-shape). Its full output lands in
   results/m5_shape_<store>.json.
2. Subject-label quality, judged by task 19.0's hygiene rules applied mechanically to the
   memory-compile `subject_*` entities of each store (code + session partitions):
   - unlabeled: `subject_unlabeled_N` (compile found no shared concept to name it);
   - junk: every label token is in `scan._PROMPT_STOPWORDS` (the shared stoplist the repo
     mandates, feedback_reuse_shared_stoplist), or <= 2 chars, or a stdlib dotted head;
   - generic: one content token (e.g. `subject_id`) — names a column, not a topic;
   - descriptive: >= 2 content tokens.
   Members = entities linked to the subject (any linkage), counted.
Band (doc): modularity >= 0.40 admit a `subject` representation; 0.30-0.40 label quality first;
< 0.30 no subject tree. Label quality decides only inside the 0.30-0.40 band, but is reported for
every store because an admitted representation still needs usable labels.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import RESULTS, STORES, copy_db  # noqa: E402

PRIOR = HERE.parent / "spikes" / "2026-10-07-adjacency-shape" / "measure.py"
STDLIB_HEADS = {"re", "json", "glob", "collections", "os", "sys", "pathlib", "time", "math"}


def label_class(name: str, stop: set[str]) -> str:
    lab = name[len("subject_"):]
    if lab.startswith("unlabeled"):
        return "unlabeled"
    toks = [t for t in lab.split("_") if t]
    content = [t for t in toks if t not in stop and len(t) > 2 and t not in STDLIB_HEADS
               and not t.isdigit()]
    if not content:
        return "junk"
    return "generic" if len(content) == 1 else "descriptive"


def main() -> None:
    from refmatrix.scan import _PROMPT_STOPWORDS
    stop = {w.lower() for w in _PROMPT_STOPWORDS}
    RESULTS.mkdir(parents=True, exist_ok=True)
    allout = {}
    for store, (_root, pid) in STORES.items():
        shape = RESULTS / f"m5_shape_{store}.json"
        subprocess.run([sys.executable, "-I", str(PRIOR), copy_db(store), "--partition-id",
                        str(pid), "--out", str(shape)], check=True, stdout=subprocess.DEVNULL)
        sh = json.loads(shape.read_text())
        c = duckdb.connect(copy_db(store), read_only=True)
        subs = c.execute(
            r"""SELECT e.id, e.name, p.name,
                       (SELECT count(DISTINCT el.entity_id) FROM entity_links el
                        WHERE el.concept_id = e.id) AS members
                FROM entities e JOIN partitions p ON p.id = e.partition_id
                WHERE e.name LIKE 'subject\_%' ESCAPE '\'""").fetchall()
        classes: dict[str, int] = {}
        members = []
        for _id, nm, _part, m in subs:
            k = label_class(nm, stop)
            classes[k] = classes.get(k, 0) + 1
            members.append(m)
        q = sh["communities"]["louvain_modularity"]
        band = ("admit" if q >= 0.40 else "label-quality-first" if q >= 0.30 else "no-subject-tree")
        allout[store] = {
            "modularity": q, "n_communities": sh["communities"]["n_communities"],
            "largest_communities": sh["communities"]["largest"][:4],
            "entities": sh["entities"], "concepts": sh["concepts"], "edges": sh["edges"],
            "subjects": len(subs), "label_classes": classes,
            "subject_members_total": int(sum(members)),
            "band": band,
        }
        print(store, json.dumps(allout[store]))
    (RESULTS / "m5_all.json").write_text(json.dumps(allout, indent=2))


if __name__ == "__main__":
    main()
