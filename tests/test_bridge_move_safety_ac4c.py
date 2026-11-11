"""Task 26.2 AC-4c, the combined 26.2 + 26.3 contract (`workflow/plans/plan-26-memory-organisation-
tasks/task-26.2-bridge-move-safety.md` #ac-4c-combined), owed by whichever task merged second
(26.2, `05164ce`).

WHY. Two rules meet on one memdir and must not hide each other. 26.2 AC-4 refuses an id claimed
by two files (`ingest_gmd.split_claims`: neither is written, both are named). 26.3 lets a
save-state exist mid-move as a PAIR -- top-level `savestate_<id>.md` beside
`savestates/savestate_<id>.md` -- and resolves that pair in the WALK
(`memory_layout.iter_memory_files` via `savestate_pair`, ADR-0005 #newest's `(date, mtime,
name)` key: the newer copy is kept, the other goes on the walk's skip list). So:
- `duplicate_ids` names ONLY the other id (the pair never reaches `split_claims`);
- the save-state is ingested ONCE, from the copy the walk keeps;
- the skip line names the dropped copy.
A pair rule turned off would make every mid-move save-state a refused duplicate; an exemption
for save-states in `split_claims` could hide a real duplicate. The walk's pair rule reads only
`savestates/`, not the marker, so the flat-dir twin is covered too, and both directions of
"newer".

Real CLI (`rmx ingest-gmd --as-memory`) on a throwaway store; the daemon leg through a spawned
daemon, as the 26.2 AC-4 tests do. Nothing is mocked.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from tests.test_bridge_move_safety import (  # noqa: F401 -- fixtures are used by name
    PLAIN, _bridge, _mem, _with_store, daemon, inproc,
)

SS_ID = "savestate_abc"
SS_MD = ('---\ngmd: "0.1"\nid: savestate_abc\ntitle: "save-state abc"\ntags: [savestate]\n'
         'metadata:\n  type: project\n  updated: {updated}\n---\n'
         '# save-state abc {{#root}}\n\n{body}\n')


def _memdir_ac4c(base: Path, *, marker: bool, newer: str) -> dict:
    """y (unique), z claimed by `a/z.md` AND `b/z.md`, and a save-state pair whose `newer`
    copy ("top" or "folder") has the later `updated` date AND the later mtime."""
    d = base / "memory"
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir()
    (d / "savestates").mkdir()
    if marker:
        (d / ".memory-layout").write_text('{"layout": 1}\n', encoding="utf-8")
    (d / "y.md").write_text(PLAIN.format(id="y", body="y alone"), encoding="utf-8")
    (d / "a" / "z.md").write_text(PLAIN.format(id="z", body="z, first claim"), encoding="utf-8")
    (d / "b" / "z.md").write_text(PLAIN.format(id="z", body="z, second claim"),
                                  encoding="utf-8")
    top, sub = d / f"{SS_ID}.md", d / "savestates" / f"{SS_ID}.md"
    kept, dropped = (top, sub) if newer == "top" else (sub, top)
    dropped.write_text(SS_MD.format(updated="2026-11-01", body="the OLDER copy"),
                       encoding="utf-8")
    kept.write_text(SS_MD.format(updated="2026-11-10", body="the NEWER copy"), encoding="utf-8")
    now = time.time()
    os.utime(dropped, (now - 86400, now - 86400))
    os.utime(kept, (now, now))
    return {"memdir": d, "kept": kept, "dropped": dropped,
            "z": [d / "a" / "z.md", d / "b" / "z.md"]}


def _forms(p: Path) -> tuple[str, str]:
    return str(p), str(p.resolve())


def _dup_block(out: str) -> list[str]:
    """The `duplicate_ids: N` header and its `  <id>: <paths>` lines."""
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("duplicate_ids:"):
            block = [ln]
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  "):
                    break
                block.append(nxt)
            return block
    return []


def _assert_ac4c(root: Path, out: str, fx: dict, leg: str) -> None:
    flat = " ".join(out.split())
    block = _dup_block(out)
    assert block, f"{leg}: no duplicate_ids report -- z's two claims were not refused:\n{out}"
    ids = [ln.split(":", 1)[0].strip() for ln in block[1:]]
    assert block[0].startswith("duplicate_ids: 1 ") and ids == ["z"], \
        f"{leg}: duplicate_ids must name ONLY z, got header {block[0]!r}, ids {ids}:\n{out}"
    assert all(any(f in flat for f in _forms(p)) for p in fx["z"]), \
        f"{leg}: the duplicate report does not name both z paths:\n{out}"
    assert not any(SS_ID in ln for ln in block), \
        f"{leg}: the save-state pair reached the duplicate refusal:\n{out}"
    skip = [ln for ln in out.splitlines() if "ingest-gmd --as-memory: skipped" in ln]
    assert skip and any(f in skip[0] for f in _forms(fx["dropped"])), \
        f"{leg}: the skip line does not name the dropped copy {fx['dropped']}:\n{out}"
    assert not any(f in skip[0] for f in _forms(fx["kept"])), \
        f"{leg}: the skip line names the KEPT copy {fx['kept']}:\n{out}"
    m = _mem(root, SS_ID)                     # asserts exactly one row
    assert "the NEWER copy" in m["content"], \
        f"{leg}: the save-state was ingested from the older copy: {m['content']!r}"
    assert m["source_path"] and Path(m["source_path"]).resolve() == fx["kept"].resolve(), \
        f"{leg}: save-state source_path {m['source_path']!r}, expected {fx['kept']}"
    nz = _with_store(root, lambda s: s._connect().execute(
        "SELECT count(*) FROM entities WHERE kind = 'memory' AND name = 'z'").fetchone()[0])
    assert nz == 0, f"{leg}: z was written ({nz} row(s)) although both claims were refused"
    ny = _with_store(root, lambda s: s._connect().execute(
        "SELECT count(*) FROM entities WHERE kind = 'memory' AND name = 'y'").fetchone()[0])
    assert ny == 1, f"{leg}: the unique memory y was not written"


@pytest.mark.parametrize("newer", ["top", "folder"])
@pytest.mark.parametrize("marker", [True, False], ids=["organised", "flat"])
def test_ac4c_pair_is_kept_once_and_only_the_other_id_is_refused(inproc, marker, newer):
    base, root = inproc
    fx = _memdir_ac4c(base, marker=marker, newer=newer)
    out = _bridge(fx["memdir"])
    _assert_ac4c(root, out, fx, f"in-process, {'organised' if marker else 'flat'}, "
                                f"{newer} newer")


def test_ac4c_daemon_leg(daemon):
    base, root = daemon
    fx = _memdir_ac4c(base, marker=True, newer="top")
    out = _bridge(fx["memdir"])
    dm.stop_daemon(root)
    _assert_ac4c(root, out, fx, "daemon, organised, top newer")
