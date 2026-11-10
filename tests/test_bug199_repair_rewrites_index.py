"""bug-199: `--repair-cut-hooks --apply` must not be undone by the next `write`.

The bug-195 repair writes only `.memory_hooks.json`. The memory's MEMORY.md line still carries
the old `prefix…` cut, and on a line WITH room for the repaired value the 26.1 r3 precedence
(`_index_hook_wins`) correctly reads that `prefix…` as the user's own shortening -- so the
stale index line wins over the repaired sidecar value and `write` freezes the cut back in.
Live run 2026-11-10: 29 hooks restored, the next `write` reverted 26 (`mismatched: 26`). The
bug-195 audit's "restore survives a later write" was checked on a FOLDED key, which has no
index line.

Contract (bug-199 Fix column, team-lead RED brief 2026-11-10):
  * after `--apply` (a drop OR a `--restore`), every affected MEMORY.md line carries the
    repaired hook -- the restored text, or the memory's derived hook for a dropped key;
  * so `--apply` then `write` keeps every repaired value, in the index AND the sidecar;
  * `check` is in sync after the apply and after the write;
  * a key with no index line (folded) still works;
  * marker-off (path-keyed) and organised (id-keyed, `.memory-layout`) dirs both;
  * a dry-run still writes nothing, index included; a hand edit on an unaffected line survives.

Every repair runs through the REAL entry point in a child process (`_run`, shared with
`test_memory_hook_repair.py`), on a tmp memdir with `RMX_HOME` pointed at tmp. The pre-repair
state is produced by the REAL `write` over a sidecar holding the bug-193 cuts -- exactly how the
live index came to carry them -- and asserted as a precondition.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from refmatrix import memory_index as mi
from tests.test_memory_hook_repair import (  # noqa: F401 (rmx_home is a fixture)
    CURATED_CUT, DERIVED_CUT, DERIVED_PROSE, _line_naming, _mem, _run, _sidecar_bytes,
    _write_sidecar, rmx_home,
)

# The full curated text an operator recovered from git: it starts with the cut's prefix (so
# the stale index line reads as a `prefix…` of it) and FITS its line (so `_index_hook_wins`
# lets the stale cut win -- the 26-of-29 live shape).
RESTORED = CURATED_CUT[:-1] + " it short, and git still had the whole of it."


def _quiet():
    return open(os.devnull, "w")


def _index(d: Path) -> str:
    return (d / mi.INDEX_NAME).read_text(encoding="utf-8")


def _hook_of(d: Path, link: str) -> str:
    """The hook part of the index line linking `link` (the text after ` — `)."""
    line = _line_naming(_index(d), f"]({link})")
    head, sep, hook = line.partition(f"]({link}) — ")
    assert sep, f"line for {link} carries no hook: {line!r}"
    return hook


def _room(d: Path, link: str) -> int:
    line = _line_naming(_index(d), f"]({link})")
    return mi.MAX_LINE_CHARS - len(line.partition(f"]({link})")[0] + f"]({link})") - len(" — ")


def _flat(tmp_path: Path) -> Path:
    """Marker-off, path-keyed: the live refmatrix shape. One curated cut and one derived cut,
    both on lines with room for the repaired value, plus an intact control."""
    d = tmp_path / "flat" / "memory"
    d.mkdir(parents=True)
    _mem(d, "feedback_derived", title="Derived", body=DERIVED_PROSE, mtype="feedback")
    _mem(d, "project_curated", title="Curated", body="Prose unrelated to the curated hook.")
    _mem(d, "project_fine", title="Fine", body="Prose of the fine one.")
    _write_sidecar(d, {"feedback_derived.md": DERIVED_CUT,
                       "project_curated.md": CURATED_CUT,
                       "project_fine.md": "an intact curated hook with no cut"})
    return d


def _organised(tmp_path: Path) -> Path:
    """Organised (`.memory-layout`), id-keyed sidecar (task 26.1 AC-4)."""
    d = tmp_path / "org" / "memory"
    d.mkdir(parents=True)
    (d / ".memory-layout").write_text(json.dumps({"layout": 1}), encoding="utf-8")
    _mem(d, "feedback/feedback_derived", title="Derived", body=DERIVED_PROSE,
         mtype="feedback")
    _mem(d, "project/project_curated", title="Curated",
         body="Prose unrelated to the curated hook.")
    _write_sidecar(d, {"feedback_derived": DERIVED_CUT, "project_curated": CURATED_CUT})
    return d


LAYOUTS = {
    "flat": (_flat, {"derived": ("feedback_derived.md", "feedback_derived.md"),
                     "curated": ("project_curated.md", "project_curated.md")}),
    "organised": (_organised, {
        "derived": ("feedback/feedback_derived.md", "feedback_derived"),
        "curated": ("project/project_curated.md", "project_curated")}),
}


@pytest.fixture(params=sorted(LAYOUTS))
def stale(request, tmp_path, rmx_home):
    """`(memdir, {role: (index link, sidecar key)})` with the pre-repair index on disk: the
    REAL `write` rendered the cut sidecar values onto lines that have room for the repair."""
    make, keys = LAYOUTS[request.param]
    d = make(tmp_path)
    mi.write(d, out=_quiet())
    for link, _key in keys.values():
        assert _hook_of(d, link).endswith("…"), f"precondition: {link} line carries the cut"
    assert len(RESTORED) <= _room(d, keys["curated"][0]), "precondition: the line has room"
    assert len(DERIVED_PROSE) <= _room(d, keys["derived"][0]), "precondition: room"
    return d, keys


# ---- restore on a line with room ------------------------------------------------------

def test_restore_rewrites_the_stale_index_line_on_apply(stale):
    d, keys = stale
    link, key = keys["curated"]
    rc, out = _run(d, "--apply", restore=[f"{key}={RESTORED}"])
    assert rc == 0, out
    assert _hook_of(d, link) == RESTORED, (
        f"after --apply the index line must carry the restored hook, not the stale cut "
        f"that the next write reads as a hand edit:\n{_index(d)}")
    assert mi.check(d), f"--check must be in sync right after the apply:\n{_index(d)}"


def test_restore_survives_the_next_write(stale):
    d, keys = stale
    link, key = keys["curated"]
    rc, out = _run(d, "--apply", restore=[f"{key}={RESTORED}"])
    assert rc == 0, out
    mi.write(d, out=_quiet())
    assert json.loads(_sidecar_bytes(d))[key] == RESTORED, (
        "the next write reverted the restored value to the stale index cut (bug-199)")
    assert _hook_of(d, link) == RESTORED, _index(d)
    assert mi.check(d), _index(d)


# ---- a dropped derived key on a line with room ----------------------------------------

def test_dropped_derived_key_rewrites_its_line_to_the_full_derived_hook_on_apply(stale):
    d, keys = stale
    link, key = keys["derived"]
    rc, out = _run(d, "--apply")
    assert rc == 0, out
    # Not pinned: whether the sidecar key stays absent or comes back holding the FULL derived
    # text -- a fix that renders the index after the sidecar write re-saves it (bug-199 Fix
    # column, option 2). Either way it must not hold the cut.
    assert json.loads(_sidecar_bytes(d)).get(key) in (None, DERIVED_PROSE), out
    assert _hook_of(d, link) == DERIVED_PROSE, (
        f"after --apply a dropped key's line must carry its derived hook:\n{_index(d)}")
    assert mi.check(d), _index(d)


def test_dropped_derived_key_regains_the_full_hook_after_the_next_write(stale):
    d, keys = stale
    link, key = keys["derived"]
    rc, out = _run(d, "--apply")
    assert rc == 0, out
    mi.write(d, out=_quiet())
    assert _hook_of(d, link) == DERIVED_PROSE, (
        f"the next write put the stale derived cut back (bug-199):\n{_index(d)}")
    assert json.loads(_sidecar_bytes(d)).get(key) == DERIVED_PROSE
    assert mi.check(d), _index(d)


# ---- guards: what must NOT change -----------------------------------------------------

def test_a_restore_on_a_key_with_no_index_line_still_survives_the_write(tmp_path, rmx_home):
    """The folded shape bug-195's audit checked: no index line, so nothing stale can win."""
    d = _flat(tmp_path)
    mi.write(d, out=_quiet())
    idx = d / mi.INDEX_NAME
    idx.write_text("".join(ln + "\n" for ln in _index(d).splitlines()
                           if "](project_curated.md)" not in ln), encoding="utf-8")
    rc, out = _run(d, "--apply", restore=[f"project_curated.md={RESTORED}"])
    assert rc == 0, out
    mi.write(d, out=_quiet())
    assert json.loads(_sidecar_bytes(d))["project_curated.md"] == RESTORED
    assert _hook_of(d, "project_curated.md") == RESTORED, _index(d)


def test_a_dry_run_leaves_an_existing_index_byte_identical(stale):
    d, keys = stale
    before = (d / mi.INDEX_NAME).read_bytes()
    side = _sidecar_bytes(d)
    rc, out = _run(d, restore=[f"{keys['curated'][1]}={RESTORED}"])
    assert rc == 0, out
    assert (d / mi.INDEX_NAME).read_bytes() == before, "a dry-run must not touch the index"
    assert _sidecar_bytes(d) == side


def test_a_hand_edit_on_an_unaffected_line_survives_the_apply_and_the_write(tmp_path,
                                                                          rmx_home):
    """Rewriting the affected lines must not re-render a hand edit elsewhere away."""
    d = _flat(tmp_path)
    mi.write(d, out=_quiet())
    edit = "a hook the user typed into MEMORY.md by hand"
    idx = d / mi.INDEX_NAME
    idx.write_text(_index(d).replace("an intact curated hook with no cut", edit),
                   encoding="utf-8")
    rc, out = _run(d, "--apply", restore=[f"project_curated.md={RESTORED}"])
    assert rc == 0, out
    assert _hook_of(d, "project_fine.md") == edit, _index(d)
    mi.write(d, out=_quiet())
    assert _hook_of(d, "project_fine.md") == edit, _index(d)
    assert json.loads(_sidecar_bytes(d))["project_fine.md"] == edit
