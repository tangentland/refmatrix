"""bug-199 r2 remedy: ch-bsd r1 #s-1, #s-2, #m-1 on `--repair-cut-hooks --apply`.

Report: workflow/bullshit/2026-11-10-1656-bug199-200-r1-30c35a9.md. The probe that found these
shapes is the auditor's scratchpad `probeB.py` (parts B, C, D); these tests rebuild its setups on
the shared fixtures, they do not import it.

Contracts (team-lead RED brief, 2026-11-10):

  * #s-1 -- an affected MEMORY.md line is rewritten only when its current hook is what the OLD
    sidecar value renders to. A line the user edited by hand is KEPT on a drop, and the
    output names it as kept (hand edit). The hand edit survives in the live
    index, not only in the backup. Base `fb0f35e` kept it; the branch overwrote it and printed
    only `rewrite MEMORY.md line X`. A `--restore` over a hand edit is the exception
    (team-lead decision, 2026-11-10): the explicit restore REPLACES it, the output names the
    replacement, and the backup's MEMORY.md still holds the hand-edited line.
  * #s-2 -- when the MEMORY.md write fails AFTER the sidecar write, the sidecar is put back to
    its original bytes before the command exits non-zero. After it, sidecar and index both
    equal their pre-apply bytes, and the message says nothing was changed and still names the
    backup. The branch left the bug-199 state (repaired sidecar, stale index), so the next
    automated `write` reverted the restore, and it printed `refused` after having written.
  * #m-1 -- a `--restore` keyed by a moved file's OLD path rewrites that memory's index line
    too. The branch printed `restored 1, rewrote 0`, and the next `write` reverted the restore.

#s-2 is tested twice. Once with a REAL fault through the real entry point in a child process:
MEMORY.md is made immutable (`UF_IMMUTABLE`), so the rename onto it fails with EPERM while
reading it still works. That is a non-mock fault injection, registered as such. Once
in-process, with `_atomic_write_text` failing with ENOSPC for the index name only (the seam
the auditor named; registered as a permanent failure injection).
"""
from __future__ import annotations

import errno
import io
import json
import os
import re
import shutil
import stat
from pathlib import Path

import pytest

from refmatrix import memory_index as mi
from tests.test_bug199_repair_rewrites_index import (  # noqa: F401 (stale/rmx_home: fixtures)
    RESTORED, _flat, _hook_of, _index, _quiet, _room, stale,
)
from tests.test_memory_hook_repair import (  # noqa: F401
    CURATED_CUT, DERIVED_CUT, DERIVED_PROSE, _mem, _run, _sidecar_bytes, _write_sidecar,
    rmx_home,
)

HAND = "MY OWN HAND-WRITTEN HOOK, typed into MEMORY.md after the last write"

# The message an index-write failure must print: that NOTHING was changed. Base and branch
# print neither phrase.
NOTHING_CHANGED = re.compile(
    r"nothing (was |has been )?changed|(left|are|is|were) (both )?(untouched|unchanged)", re.I)


def _hand_edit(d: Path, old_hook: str, new_hook: str) -> None:
    idx = d / mi.INDEX_NAME
    text = _index(d)
    assert text.count(old_hook) == 1, f"precondition: {old_hook!r} is on one line:\n{text}"
    idx.write_text(text.replace(old_hook, new_hook), encoding="utf-8")


def _kept_line(out: str, link: str) -> "str | None":
    """The output line that names `link` as kept because it was edited by hand."""
    for ln in out.splitlines():
        low = ln.lower()
        if link in ln and "kept" in low and "hand" in low:
            return ln
    return None


def _replaced_line(out: str, link: str) -> "str | None":
    """The output line that names `link` as a hand edit the restore replaced."""
    for ln in out.splitlines():
        low = ln.lower()
        if link in ln and "replac" in low and "hand" in low:
            return ln
    return None


def _rewrite_line(out: str, link: str) -> "str | None":
    for ln in out.splitlines():
        if re.search(rf"\brewrite\b.*{re.escape(mi.INDEX_NAME)} line {re.escape(link)}\s*$",
                     ln):
            return ln
    return None


def _backup_dirs(home: Path) -> list:
    root = home / "backups" / "memory-hooks"
    return sorted(root.iterdir()) if root.is_dir() else []


# ---- #s-1: a hand edit on an AFFECTED line ---------------------------------------------

def test_s1_a_drop_keeps_a_hand_edit_on_the_affected_line_and_says_so(stale):
    """Probe B1: the derived key is dropped, but its line no longer carries the cut the
    sidecar rendered -- the user retyped it. The line is kept, the output says so, and the
    hand edit still wins the next `write` (as at base)."""
    d, keys = stale
    link, key = keys["derived"]
    _hand_edit(d, DERIVED_CUT, HAND)
    rc, out = _run(d, "--apply")
    assert rc == 0, out
    assert _hook_of(d, link) == HAND, (
        f"the apply overwrote a hand-edited hook on an affected line; it survives only in "
        f"the backup now (#s-1):\n{_index(d)}\n--- output ---\n{out}")
    assert _kept_line(out, link), (
        f"the output must name {link} as kept (hand edit), not as rewritten:\n{out}")
    assert _rewrite_line(out, link) is None, f"{link} is reported as rewritten:\n{out}"
    mi.write(d, out=_quiet())
    assert _hook_of(d, link) == HAND, f"the next write lost the hand edit:\n{_index(d)}"


def test_s1_a_restore_replaces_a_hand_edit_and_says_so(stale, rmx_home):
    """Probe B2: the operator restores a key whose line the user retyped by hand after the
    last write. `--restore k=text` is the newer, explicit instruction for that key, so it
    REPLACES the hand edit -- keeping it would let the next `write` read it as a hand edit
    that wins, reverting the restore (bug-199 again). The replacement is named in the output
    (not printed as a plain rewrite), and the hand edit stays recoverable from the backup
    (team-lead decision, 2026-11-10)."""
    d, keys = stale
    link, key = keys["curated"]
    _hand_edit(d, CURATED_CUT, HAND)
    hand_line = next(ln for ln in _index(d).splitlines() if f"]({link})" in ln)
    rc, out = _run(d, "--apply", restore=[f"{key}={RESTORED}"])
    assert rc == 0, out
    assert _hook_of(d, link) == RESTORED, (
        f"the restore must replace the hand edit on its line:\n{_index(d)}\n{out}")
    assert _replaced_line(out, link), (
        f"the output must name {link} as a REPLACED hand edit, not as a plain rewrite "
        f"(#s-1, B2):\n{out}")
    dirs = _backup_dirs(rmx_home)
    assert len(dirs) == 1, f"one backup dir expected, got {dirs}\n{out}"
    bak = dirs[0] / mi.INDEX_NAME
    assert bak.is_file() and hand_line in bak.read_text(encoding="utf-8").splitlines(), (
        f"the replaced hand edit must be recoverable from the index backup {bak}:\n"
        f"{bak.read_text(encoding='utf-8') if bak.is_file() else '(missing)'}")
    mi.write(d, out=_quiet())
    assert _hook_of(d, link) == RESTORED, (
        f"the next write reverted the restore:\n{_index(d)}")
    assert json.loads(_sidecar_bytes(d))[key] == RESTORED


def test_s1_a_rendered_line_is_still_rewritten_beside_a_kept_hand_edit(stale):
    """One apply, two affected lines: the hand-edited derived line is kept, the curated line
    that still carries its rendered cut is rewritten to the restore (bug-199 itself). A fix
    that stops rewriting altogether fails here."""
    d, keys = stale
    dlink, _dkey = keys["derived"]
    clink, ckey = keys["curated"]
    _hand_edit(d, DERIVED_CUT, HAND)
    rc, out = _run(d, "--apply", restore=[f"{ckey}={RESTORED}"])
    assert rc == 0, out
    assert _hook_of(d, dlink) == HAND, f"hand edit overwritten (#s-1):\n{_index(d)}\n{out}"
    assert _kept_line(out, dlink), f"{dlink} not named as kept (hand edit):\n{out}"
    assert _hook_of(d, clink) == RESTORED, f"the rendered line was not rewritten:\n{_index(d)}"
    assert _rewrite_line(out, clink), f"{clink} must be reported as rewritten:\n{out}"
    mi.write(d, out=_quiet())
    assert _hook_of(d, dlink) == HAND, _index(d)
    assert _hook_of(d, clink) == RESTORED, _index(d)
    assert json.loads(_sidecar_bytes(d))[ckey] == RESTORED


# ---- #s-2: the MEMORY.md write fails after the sidecar write ---------------------------

def _assert_rolled_back(d: Path, home: Path, before: dict, rc: int, out: str) -> None:
    assert rc != 0, f"an index-write failure must exit non-zero:\n{out}"
    assert _sidecar_bytes(d) == before["side"], (
        f"the sidecar was left repaired while the index stayed stale -- the bug-199 state, "
        f"which the next automated write turns back into the cuts (#s-2):\n"
        f"now:    {_sidecar_bytes(d)[:300]!r}\nbefore: {before['side'][:300]!r}\n"
        f"--- output ---\n{out}")
    assert (d / mi.INDEX_NAME).read_bytes() == before["index"], "the index changed"
    assert stat.S_IMODE((d / mi.HOOKS_SIDECAR).stat().st_mode) == before["mode"], (
        "the sidecar rollback must keep the sidecar's mode (the atomic write's contract)")
    assert sorted(p.name for p in d.iterdir()) == before["names"], (
        f"the failed apply left files behind in the memdir: "
        f"{sorted(p.name for p in d.iterdir())}")
    assert NOTHING_CHANGED.search(out), (
        f"the failure message must say nothing was changed (it must not read as a partial "
        f"write followed by `refused`):\n{out}")
    dirs = _backup_dirs(home)
    assert len(dirs) == 1, f"one backup dir expected, got {dirs}\n{out}"
    assert str(dirs[0]) in out, f"the message must still name the backup {dirs[0]}:\n{out}"


def _snapshot(d: Path) -> dict:
    os.chmod(d / mi.HOOKS_SIDECAR, 0o640)       # a non-default mode the rollback must keep
    return {"side": _sidecar_bytes(d), "index": (d / mi.INDEX_NAME).read_bytes(),
            "mode": 0o640, "names": sorted(p.name for p in d.iterdir())}


def test_s2_a_real_index_write_failure_puts_the_sidecar_back(stale, rmx_home):
    """REAL fault, real entry point (child process): MEMORY.md is immutable, so the index
    rename fails with EPERM while reading the index for the rewrite and its backup works."""
    d, keys = stale
    before = _snapshot(d)
    idx = d / mi.INDEX_NAME
    os.chflags(idx, stat.UF_IMMUTABLE)
    try:
        rc, out = _run(d, "--apply", restore=[f"{keys['curated'][1]}={RESTORED}"])
    finally:
        os.chflags(idx, 0)
    _assert_rolled_back(d, rmx_home, before, rc, out)


def test_s2_an_injected_index_write_failure_puts_the_sidecar_back(stale, rmx_home,
                                                                  monkeypatch, capsys):
    """Probe C, in-process: `_atomic_write_text` fails with ENOSPC for the index ONLY; the
    sidecar write -- and a sidecar rollback through the same helper -- run for real."""
    d, keys = stale
    before = _snapshot(d)
    real = mi._atomic_write_text
    calls: list = []

    def index_write_fails(memdir, name, text):
        calls.append(name)
        if name == mi.INDEX_NAME:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(memdir, name, text)

    monkeypatch.setattr(mi, "_atomic_write_text", index_write_fails)
    buf = io.StringIO()
    rc = mi.repair_cut_hooks(d, apply=True, restores=[f"{keys['curated'][1]}={RESTORED}"],
                             out=buf)
    cap = capsys.readouterr()
    out = buf.getvalue() + cap.out + cap.err
    assert mi.INDEX_NAME in calls, (
        f"precondition: the apply reached the index write through the seam: {calls}\n{out}")
    _assert_rolled_back(d, rmx_home, before, rc, out)


# ---- #m-1: a restore keyed by a moved file's OLD path ---------------------------------

def test_m1_a_restore_keyed_by_a_moved_files_old_path_rewrites_its_line(tmp_path, rmx_home):
    """Probe D: the sidecar keys the memory by `project_curated.md`; the file has since moved
    to `sub/project_curated.md` and its index line links the new path (the 26.4/26.5
    migration window). The old-path key aliases to the memory's id, so the restore must reach
    that line too -- otherwise the next `write` puts the cut back (bug-199 via the move)."""
    d = tmp_path / "moved" / "memory"
    d.mkdir(parents=True)
    _mem(d, "project_curated", title="Curated", body="Prose unrelated to the curated hook.")
    _mem(d, "project_fine", title="Fine", body="Prose of the fine one.")
    _write_sidecar(d, {"project_curated.md": CURATED_CUT,
                       "project_fine.md": "an intact curated hook with no cut"})
    mi.write(d, out=_quiet())
    (d / "sub").mkdir()
    shutil.move(d / "project_curated.md", d / "sub" / "project_curated.md")
    idx = d / mi.INDEX_NAME
    idx.write_text(_index(d).replace("](project_curated.md)", "](sub/project_curated.md)"),
                   encoding="utf-8")
    link = "sub/project_curated.md"
    assert _hook_of(d, link) == CURATED_CUT, "precondition: the moved line carries the cut"
    assert len(RESTORED) <= _room(d, link), "precondition: the moved line has room"

    rc, out = _run(d, "--apply", restore=[f"project_curated.md={RESTORED}"])
    assert rc == 0, out
    assert _hook_of(d, link) == RESTORED, (
        f"a restore keyed by the moved file's OLD path left its line stale (#m-1):\n"
        f"{_index(d)}\n--- output ---\n{out}")
    mi.write(d, out=_quiet())
    assert _hook_of(d, link) == RESTORED, (
        f"the next write reverted the old-path restore to the cut (#m-1):\n{_index(d)}")
    values = json.loads(_sidecar_bytes(d)).values()
    assert CURATED_CUT not in values and RESTORED in values, _sidecar_bytes(d)
