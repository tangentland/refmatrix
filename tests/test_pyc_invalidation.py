"""bug-037: a stale `.pyc` served a mutated constant through a restored source.

A mutation check edited `"45"` -> `"20"` in `modelsrv.py` — the SAME byte
length — and the source was then restored from a backup. `PROBE_TIMEOUT_S`
read 20.0 at runtime while the file on disk read 45, in the same interpreter,
and two tests failed for a reason that had nothing to do with the code under
test. A GREEN run in that state would have been exactly as wrong.

CPython validates a timestamp `.pyc` against the source's `(mtime, size)`. A
same-length edit removes size as a discriminator; a restore that lands the
source on the mtime the `.pyc` recorded removes the other. These tests
reproduce that mechanism on a throwaway package and prove that hash-based
(PEP 552 `checked-hash`) bytecode cannot be fooled by it.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _guard():
    """Load `tools/pyc_guard.py` by path — `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "rmx_pyc_guard", REPO / "tools" / "pyc_guard.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_pkg(root: Path, value: str) -> Path:
    src = root / "m.py"
    src.write_text(f"X = {value}\n")
    return src


def _read_value(root: Path) -> str:
    """Import `m` in a FRESH interpreter and print `m.X`."""
    out = subprocess.run(
        [sys.executable, "-c", "import m; print(m.X)"],
        cwd=str(root), capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _pyc_of(root: Path) -> Path:
    cache = root / "__pycache__"
    pycs = sorted(cache.glob("m.*.pyc"))
    assert pycs, f"no bytecode written under {cache}"
    return pycs[0]


# ---- header reader -------------------------------------------------------

def test_timestamp_bytecode_is_reported_unsafe(tmp_path):
    g = _guard()
    _write_pkg(tmp_path, "45")
    _read_value(tmp_path)                      # writes a timestamp pyc
    assert g.pyc_is_safe(_pyc_of(tmp_path)) is False


def test_checked_hash_bytecode_is_reported_safe(tmp_path):
    g = _guard()
    _write_pkg(tmp_path, "45")
    _read_value(tmp_path)
    g.enforce(tmp_path)
    assert g.pyc_is_safe(_pyc_of(tmp_path)) is True


def test_unchecked_hash_bytecode_is_reported_unsafe(tmp_path):
    """`unchecked-hash` skips validation entirely — worse than a timestamp
    pyc, not better. The reader must not accept it just because bit 0 is set."""
    import py_compile

    g = _guard()
    src = _write_pkg(tmp_path, "45")
    py_compile.compile(
        str(src), doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    assert g.pyc_is_safe(_pyc_of(tmp_path)) is False


# ---- the incident replay -------------------------------------------------

def test_timestamp_bytecode_serves_a_restored_source_stale(tmp_path):
    """The bug-037 mechanism itself. If this stops reproducing, the guard
    below is protecting against nothing and the suite must say so."""
    src = _write_pkg(tmp_path, "45")
    assert _read_value(tmp_path) == "45"

    _write_pkg(tmp_path, "20")                 # SAME byte length
    # Move the mutant off the original's second so the pyc is rebuilt FROM it.
    # (Without this the two writes share an mtime second and a same-length edit
    # is already invisible — bug-037's mechanism, one notch cheaper.)
    mutant_mtime = src.stat().st_mtime + 2
    os.utime(src, (mutant_mtime, mutant_mtime))
    assert _read_value(tmp_path) == "20"       # pyc now records the mutant
    pyc_stat = _pyc_of(tmp_path).stat()

    src.write_text("X = 45\n")                 # restore the ORIGINAL bytes
    os.utime(src, (mutant_mtime, mutant_mtime))  # ... onto the recorded mtime

    served = _read_value(tmp_path)
    assert served == "20", (
        "bug-037's mechanism did not reproduce on this interpreter "
        f"(served {served!r}, source says 45, pyc size {pyc_stat.st_size}) — "
        "the guard proves nothing until it does"
    )


def test_checked_hash_bytecode_cannot_serve_a_restored_source_stale(tmp_path):
    """Same manipulation, hash-based bytecode: the source's hash decides, and
    a same-length edit changes it."""
    g = _guard()
    src = _write_pkg(tmp_path, "45")
    _read_value(tmp_path)
    g.enforce(tmp_path)

    _write_pkg(tmp_path, "20")
    mutant_mtime = src.stat().st_mtime + 2
    os.utime(src, (mutant_mtime, mutant_mtime))
    assert _read_value(tmp_path) == "20"
    g.enforce(tmp_path)

    src.write_text("X = 45\n")
    os.utime(src, (mutant_mtime, mutant_mtime))

    assert _read_value(tmp_path) == "45"


# ---- the guard -----------------------------------------------------------

def test_enforce_reports_what_it_recompiled(tmp_path, capsys):
    g = _guard()
    _write_pkg(tmp_path, "45")
    _read_value(tmp_path)

    n = g.enforce(tmp_path)
    assert n == 1
    assert "pyc-guard" in capsys.readouterr().out

    assert g.enforce(tmp_path) == 0            # already hash-based: no-op


def test_enforce_is_opt_out(tmp_path, monkeypatch):
    g = _guard()
    _write_pkg(tmp_path, "45")
    _read_value(tmp_path)
    monkeypatch.setenv("RMX_PYC_GUARD", "0")
    assert g.enforce(tmp_path) == 0
    assert g.pyc_is_safe(_pyc_of(tmp_path)) is False   # untouched


def test_guard_never_walks_outside_its_root(tmp_path):
    """Recompiling somebody else's install is not this suite's business."""
    g = _guard()
    inside, outside = tmp_path / "in", tmp_path / "out"
    inside.mkdir(), outside.mkdir()
    _write_pkg(inside, "45")
    _write_pkg(outside, "45")
    _read_value(inside), _read_value(outside)

    g.enforce(inside)
    assert g.pyc_is_safe(_pyc_of(inside)) is True
    assert g.pyc_is_safe(_pyc_of(outside)) is False


def test_the_repo_tree_is_enforced_by_conftest():
    """The wiring, not the helper: the session guard must have run over the
    dev tree's own `src/`.

    It does NOT assert "no timestamp pyc under src/" — the import machinery
    writes one for every module this very session compiles, and always as a
    timestamp pyc. It asserts the guard ran, and that nothing on disk
    disagrees with the source beside it.
    """
    if os.environ.get("RMX_PYC_GUARD") == "0":
        pytest.skip("guard opted out for this run")
    g = _guard()
    enforced = os.environ.get(g.ENFORCED_ROOTS_ENV, "").split(os.pathsep)
    assert str((REPO / "src" / "refmatrix").resolve()) in enforced, (
        "conftest's pytest_sessionstart did not enforce src/refmatrix "
        f"(enforced roots: {enforced})")
    stale = g.stale_timestamp_pycs(REPO / "src" / "refmatrix")
    assert stale == [], f"{len(stale)} stale pyc(s) under src/: {stale[:3]}"


def test_stale_timestamp_pyc_is_detected(tmp_path):
    """The detector itself, on the bug-037 shape: content restored onto the
    mtime the pyc recorded, same length."""
    g = _guard()
    src = _write_pkg(tmp_path, "45")
    _read_value(tmp_path)
    assert g.stale_timestamp_pycs(tmp_path) == []

    _write_pkg(tmp_path, "20")
    mutant_mtime = src.stat().st_mtime + 2
    os.utime(src, (mutant_mtime, mutant_mtime))
    _read_value(tmp_path)
    src.write_text("X = 45\n")
    os.utime(src, (mutant_mtime, mutant_mtime))

    # stat says fresh, content says otherwise: the pyc is NOT flagged by stat
    # (that is the whole bug), and `enforce` is what removes the hazard.
    assert g.stale_timestamp_pycs(tmp_path) == []
    assert g.enforce(tmp_path) == 1
    assert _read_value(tmp_path) == "45"
