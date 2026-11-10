"""bug-195: a one-shot, backed-up repair of the hook values bug-193 cut.

bug-193 (precedence fixed in 25af9ca) saved the renderer's `prefix…` cut back into
`.memory_hooks.json` as if it were the curated hook. The fixed precedence stops new damage
but never heals old values: the live refmatrix sidecar held 66 values ending in `…` on
2026-11-10. Spec: `workflow/plans/task-bug195-cut-hook-repair.md` (R1-R5, AC-1..AC-6).

Every test drives the REAL entry point, `python -m refmatrix.memory_index
--repair-cut-hooks <memdir> [--apply] [--restore k=text]`, in a child process, on a tmp
memdir. Never a real memory dir.

Backup root contract (R3): `~/.refmatrix/backups/memory-hooks/<memdir-slug>-<ts>/`, where
`~/.refmatrix` is resolved the way every other user-level path in refmatrix resolves it --
`taxonomy.user_home()`, i.e. `$RMX_HOME` when set, else `~/.refmatrix`. Each test points
`RMX_HOME` at its own tmp dir so the backup is inspectable and never reaches the sandbox's
shared home (let alone the live one).

Pinned output contract (chosen by RED, report says so): one line per `…` value naming its
key and its class -- `derived`, `bare`, `curated-lost`, `gone` -- and a count per class
written `<class>: <n>`; a second apply prints `nothing to repair`.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix import memory_index as mi

SIDECAR = ".memory_hooks.json"

DERIVED_PROSE = "Fix one condition in a gate and then check every sibling condition too."
DERIVED_CUT = "Fix one condition in a gate and then check…"
CURATED_CUT = "A hand-written hook whose full text is lost because the renderer cut…"
GONE_CUT = "a hook for a memory whose file was deleted…"
FINE_HOOK = "an intact curated hook with no cut"


def _mem(d: Path, name: str, *, title: str, body: str, mtype: str = "project") -> Path:
    p = d / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '---\ngmd: "0.1"\n'
        f"id: {Path(name).name}\n"
        f'title: "{title}"\n'
        "tags: [x]\n"
        "metadata:\n  node_type: memory\n"
        f"  type: {mtype}\n"
        "  created: 2026-09-01\n"
        "---\n\n"
        f"# {title} {{#root}}\n\n{body}\n",
        encoding="utf-8")
    return p


def _sidecar_bytes(memdir: Path) -> bytes:
    return (memdir / SIDECAR).read_bytes()


def _write_sidecar(memdir: Path, data: dict) -> None:
    # The exact shape `save_hooks` writes, so a byte comparison is meaningful.
    (memdir / SIDECAR).write_text(json.dumps(data, indent=0, sort_keys=True,
                                             ensure_ascii=False), encoding="utf-8")


def _run(memdir: Path, *flags: str, restore: "list[str] | None" = None):
    argv = [sys.executable, "-B", "-m", "refmatrix.memory_index",
            "--repair-cut-hooks", str(memdir), *flags]
    for r in restore or []:
        argv += ["--restore", r]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ))
    return p.returncode, p.stdout + p.stderr


def _line_naming(out: str, key: str) -> str:
    lines = [ln for ln in out.splitlines() if key in ln]
    assert lines, f"no output line names {key!r}; output was:\n{out}"
    return lines[0]


def _count(out: str, cls: str) -> "int | None":
    m = re.search(rf"(?<![\w-]){re.escape(cls)}\s*:\s*(\d+)\b", out)
    return int(m.group(1)) if m else None


def _backups(home: Path) -> list:
    root = home / "backups" / "memory-hooks"
    return sorted(root.iterdir()) if root.is_dir() else []


@pytest.fixture
def rmx_home(tmp_path, monkeypatch):
    h = tmp_path / "rmxhome"
    h.mkdir()
    monkeypatch.setenv("RMX_HOME", str(h))
    return h


@pytest.fixture
def memdir(tmp_path):
    """One `…` value of each class, a gone-file key, and an intact hook (un-organised,
    path-keyed: the shape of the live refmatrix sidecar on 2026-11-10)."""
    d = tmp_path / "proj-slug" / "memory"
    d.mkdir(parents=True)
    _mem(d, "feedback_derived", title="Derived", body=DERIVED_PROSE, mtype="feedback")
    _mem(d, "project_bare", title="Bare", body="The bare one has prose of its own.")
    _mem(d, "project_curated", title="Curated", body="Prose unrelated to the curated hook.")
    _mem(d, "project_fine", title="Fine", body="Prose of the fine one.")
    _write_sidecar(d, {
        "feedback_derived.md": DERIVED_CUT,
        "project_bare.md": "…",
        "project_curated.md": CURATED_CUT,
        "project_gone.md": GONE_CUT,
        "project_fine.md": FINE_HOOK,
    })
    return d


# ---- AC-1: dry-run classifies, prints, changes nothing --------------------------------

def test_dry_run_classifies_every_cut_value_by_key_and_changes_nothing(memdir, rmx_home):
    before = _sidecar_bytes(memdir)
    rc, out = _run(memdir)
    assert rc == 0, out
    assert "derived" in _line_naming(out, "feedback_derived.md"), out
    assert "bare" in _line_naming(out, "project_bare.md"), out
    assert "curated-lost" in _line_naming(out, "project_curated.md"), out
    assert "gone" in _line_naming(out, "project_gone.md"), out
    assert "project_fine.md" not in out, "an intact hook is not a cut; it is not listed"
    assert (_count(out, "derived"), _count(out, "bare"), _count(out, "curated-lost"),
            _count(out, "gone")) == (1, 1, 1, 1), out
    assert _sidecar_bytes(memdir) == before, "dry-run must not write the sidecar"
    assert not (memdir / mi.INDEX_NAME).exists(), "dry-run must not render the index"
    assert _backups(rmx_home) == [], "dry-run takes no backup"


# ---- AC-2: apply drops derived + bare, keeps curated + gone, backs up first ----------

def test_apply_drops_derived_and_bare_keeps_the_rest_and_backs_up(memdir, rmx_home):
    before = _sidecar_bytes(memdir)
    old = json.loads(before)
    rc, out = _run(memdir, "--apply")
    assert rc == 0, out
    new = json.loads(_sidecar_bytes(memdir))
    assert "feedback_derived.md" not in new, "derived cut must be dropped (mutation: never dropped)"
    assert "project_bare.md" not in new, "bare `…` must be dropped (mutation: bare kept)"
    assert new.get("project_curated.md") == old["project_curated.md"], \
        "curated-lost must be kept unchanged (mutation: curated dropped)"
    assert new.get("project_gone.md") == old["project_gone.md"], "a gone-file key is never touched"
    assert new.get("project_fine.md") == FINE_HOOK, "an intact hook is never touched"
    assert set(new) == {"project_curated.md", "project_gone.md", "project_fine.md"}

    dirs = _backups(rmx_home)
    assert len(dirs) == 1, f"one backup dir expected under {rmx_home}, got {dirs}\n{out}"
    bak = dirs[0] / SIDECAR
    assert bak.read_bytes() == before, "the backup must equal the pre-apply sidecar"
    assert str(bak) in out, f"the backup path must be printed; output was:\n{out}"
    assert bak.exists()
    leftovers = sorted(p.name for p in memdir.iterdir()
                       if p.name not in {SIDECAR} and not p.name.endswith(".md"))
    assert leftovers == [], f"an atomic write leaves no temp file behind: {leftovers}"


# ---- AC-3: idempotent and loud -------------------------------------------------------

def test_second_apply_writes_nothing_and_says_so(memdir, rmx_home):
    rc, out = _run(memdir, "--apply")
    assert rc == 0, out
    assert "feedback_derived.md" not in json.loads(_sidecar_bytes(memdir)), out
    side = memdir / SIDECAR
    os.utime(side, (1_000_000_000, 1_000_000_000))      # an mtime a rewrite cannot keep
    before = side.read_bytes()
    rc2, out2 = _run(memdir, "--apply")
    assert rc2 == 0, out2
    assert "nothing to repair" in out2.lower(), out2
    assert side.stat().st_mtime == 1_000_000_000, "a second apply must not rewrite the sidecar"
    assert side.read_bytes() == before


# ---- AC-4: the full derived hook returns ---------------------------------------------

def test_after_apply_write_renders_the_full_first_prose_hook(memdir, rmx_home):
    rc, out = _run(memdir, "--apply")
    assert rc == 0, out
    assert "feedback_derived.md" not in json.loads(_sidecar_bytes(memdir)), out
    mi.write(memdir, out=open(os.devnull, "w"))
    idx = (memdir / mi.INDEX_NAME).read_text(encoding="utf-8")
    line = _line_naming(idx, "feedback_derived.md")
    assert line.endswith(f"— {DERIVED_PROSE}"), line
    assert DERIVED_CUT not in idx
    assert json.loads(_sidecar_bytes(memdir))["feedback_derived.md"] == DERIVED_PROSE


def test_a_derived_cut_longer_than_its_line_regains_the_full_hook_in_the_sidecar(
        tmp_path, rmx_home):
    """The live shape: 39 of the 66 cuts were on index lines too short for the prose. The
    line stays cut (that is the renderer's job); the sidecar must hold the FULL text again."""
    d = tmp_path / "long" / "memory"
    d.mkdir(parents=True)
    prose = "A derived hook " + "that keeps going " * 14 + "until the end."
    assert len(prose) > mi.MAX_LINE_CHARS
    _mem(d, "feedback_long", title="Long", body=prose, mtype="feedback")
    cut = prose[:120].rstrip() + "…"
    _write_sidecar(d, {"feedback_long.md": cut})
    rc, out = _run(d, "--apply")
    assert rc == 0, out
    assert "derived" in _line_naming(out, "feedback_long.md"), out
    mi.write(d, out=open(os.devnull, "w"))
    assert json.loads(_sidecar_bytes(d))["feedback_long.md"] == prose


def test_nested_path_keys_are_resolved_against_the_memdir(tmp_path, rmx_home):
    """`impressions/<x>.md` keys exist in live sidecars; a cut there is classified from its
    own file, not reported gone."""
    d = tmp_path / "nest" / "memory"
    d.mkdir(parents=True)
    _mem(d, "impressions/impression_one", title="One", body=DERIVED_PROSE, mtype="impression")
    _write_sidecar(d, {"impressions/impression_one.md": DERIVED_CUT})
    rc, out = _run(d)
    assert rc == 0, out
    assert "derived" in _line_naming(out, "impressions/impression_one.md"), out
    assert _count(out, "gone") in (0, None), out


def test_an_organised_id_keyed_sidecar_is_classified_by_memory_id(tmp_path, rmx_home):
    """An organised dir (`.memory-layout`) keys its sidecar by memory id (task 26.1 AC-4). A
    derived cut under an id key is dropped; an id with no memory is gone, untouched."""
    d = tmp_path / "org" / "memory"
    d.mkdir(parents=True)
    (d / ".memory-layout").write_text(json.dumps({"layout": 1}), encoding="utf-8")
    _mem(d, "feedback/feedback_derived", title="Derived", body=DERIVED_PROSE,
         mtype="feedback")
    _write_sidecar(d, {"feedback_derived": DERIVED_CUT, "project_vanished": GONE_CUT})
    rc, out = _run(d, "--apply")
    assert rc == 0, out
    assert "derived" in _line_naming(out, "feedback_derived"), out
    assert "gone" in _line_naming(out, "project_vanished"), out
    new = json.loads(_sidecar_bytes(d))
    assert "feedback_derived" not in new
    assert new.get("project_vanished") == GONE_CUT


# ---- AC-5: a backup that cannot be written refuses the apply -------------------------

def test_unwritable_backup_root_refuses_and_leaves_the_sidecar(memdir, rmx_home):
    root = rmx_home / "backups" / "memory-hooks"
    root.mkdir(parents=True)
    root.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        before = _sidecar_bytes(memdir)
        rc, out = _run(memdir, "--apply")
        assert rc != 0, f"apply must refuse when the backup fails; output was:\n{out}"
        assert "backup" in out.lower(), out
        assert _sidecar_bytes(memdir) == before, "nothing is written when the backup fails"
    finally:
        root.chmod(stat.S_IRWXU)


# ---- AC-6: --restore sets exactly the given value, backed up -------------------------

def test_restore_sets_exactly_the_value_and_is_backed_up(memdir, rmx_home):
    before = _sidecar_bytes(memdir)
    text = "the full curated text, recovered from ~/.claude git; a=b stays whole"
    rc, out = _run(memdir, "--apply", restore=[f"project_curated.md={text}"])
    assert rc == 0, out
    new = json.loads(_sidecar_bytes(memdir))
    assert new["project_curated.md"] == text, "split on the FIRST `=` only"
    assert new["project_fine.md"] == FINE_HOOK
    assert new["project_gone.md"] == GONE_CUT
    dirs = _backups(rmx_home)
    assert len(dirs) == 1, f"a restore is backed up like any apply: {dirs}\n{out}"
    assert (dirs[0] / SIDECAR).read_bytes() == before


# ---- R4: every failure is printed and exits non-zero ---------------------------------

def test_unparseable_sidecar_fails_loud_and_writes_nothing(memdir, rmx_home):
    (memdir / SIDECAR).write_text("{not json", encoding="utf-8")
    for flags in ((), ("--apply",)):
        rc, out = _run(memdir, *flags)
        assert "Traceback" not in out, f"{flags}: a named failure, not a crash:\n{out}"
        assert rc != 0, f"{flags}: an unparseable sidecar must exit non-zero:\n{out}"
        assert SIDECAR in out, out
        assert (memdir / SIDECAR).read_text(encoding="utf-8") == "{not json"
    assert _backups(rmx_home) == []


def test_unreadable_memory_file_fails_loud_and_writes_nothing(memdir, rmx_home):
    f = memdir / "feedback_derived.md"
    f.chmod(0)
    try:
        if os.access(f, os.R_OK):
            pytest.fail("running as a user that ignores file modes; this check is unprovable")
        before = _sidecar_bytes(memdir)
        for flags in ((), ("--apply",)):
            rc, out = _run(memdir, *flags)
            # A crash is not a printed failure: HEAD's `write()` dies on this file with a
            # PermissionError traceback, which would satisfy a bare `rc != 0`.
            assert "Traceback" not in out, f"{flags}: a named failure, not a crash:\n{out}"
            assert rc != 0, f"{flags}: an unreadable memory file must exit non-zero:\n{out}"
            assert "feedback_derived.md" in _line_naming(out, "unreadable"), out
            assert _sidecar_bytes(memdir) == before, "fail closed: no partial repair"
        assert _backups(rmx_home) == []
    finally:
        f.chmod(stat.S_IRUSR | stat.S_IWUSR)
