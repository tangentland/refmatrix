"""bug-240 RED: `rmx ingest <FILE>` is refused, naming `rmx sync -f` -- never a quiet 0.

WHY (bug-240, 2026-11-14). At the 0.83.0 deploy, re-including `CLAUDE.md` in four fleet stores
(cliquedb, viascope, cliquet, atldb), `rmx ingest CLAUDE.md` exited 0 printing `ingested 0
entities from CLAUDE.md` and wrote nothing, also with an absolute path: the command walks a
DIRECTORY, `click.Path(exists=True)` accepts a file, and a file walks no tree. A write the user
asked for became a quiet success (CLAUDE.md #no-silent-failures). `rmx sync -f CLAUDE.md` then
synced it.

Lead ruling (2026-11-14): REFUSE, in the shared ingest path so CLI and MCP agree (the MCP half
is `test_bug240_ingest_file_arg_mcp.py`). `ingest` is a tree verb whose options (`--source`,
the tldr / graphify caches) mean nothing for one file; `sync -f` is the single-file path. The
verdict: a non-zero exit, exactly one `Error:` line, that line names `rmx sync -f`, and the
file is NOT ingested by the refused call.

Real CLI, real daemon (spawned by the dev `rmx`, this checkout's code via PYTHONPATH), throwaway
store under a SHORT `/tmp` mkdtemp root (macOS `sun_path`). The daemon-down route (the CLI's
in-process `_ingest`) is driven too: the same command, a different write path. Guard: `rmx
ingest <dir>` still ingests the directory.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from devbin import dev_env, dev_rmx  # bug-253: the dev rmx, defined once (tests/devbin.py)

REPO = Path(__file__).resolve().parents[1]
RMX = dev_rmx()

GMD = ('---\ngmd: "0.1"\nid: claude\ntitle: "rules"\ntags: [t]\n---\n\n'
       "# Rules {#root}\n\n## Section x {#x}\n\nRule text about frobnication.\n")
PLAIN = "# Notes\n\nPlain markdown about quuxing.\n"

FILES = {"CLAUDE.md": GMD, "docs/notes.md": PLAIN,
         "src/pkg/a.py": "def hello():\n    return 1\n"}


def _env(root: Path) -> dict:
    return {**dev_env(), "REFMATRIX_ROOT": str(root), "RMX_INVOCATION_SOURCE": "eval"}


def _rmx(env: dict, *args: str, cwd: "Path | None" = None,
         timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([str(RMX), *args], env=env, capture_output=True, text=True,
                          timeout=timeout, cwd=cwd)


def _wait_sock(root: Path) -> None:
    for _ in range(120):
        if list(root.glob("*.sock")):
            return
        time.sleep(0.5)
    raise AssertionError(f"daemon socket never appeared under {root}")


@pytest.fixture(params=["daemon", "in_process"])
def proj(request):
    assert RMX.exists(), f"dev rmx missing at {RMX}"
    base = Path(tempfile.mkdtemp(prefix="b240.", dir="/tmp")).resolve()
    p = base / "proj"
    for rel, text in FILES.items():
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    root = p / ".refmatrix"
    env = _env(root)
    r = _rmx(env, "init", "--path", str(p), "--no-hooks", "--no-agents", "--no-memory-hooks")
    assert r.returncode == 0, r.stdout + r.stderr
    up = request.param == "daemon"
    if up:
        r = _rmx(env, "daemon", "start", "--no-watch", timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        _wait_sock(root)
    try:
        yield {"proj": p, "root": root, "env": env, "up": up}
    finally:
        if up:
            _rmx(env, "daemon", "stop", timeout=120)
        shutil.rmtree(base, ignore_errors=True)


def _stop(c) -> None:
    """Read the writer slot only once nothing holds it."""
    if c["up"]:
        r = _rmx(c["env"], "daemon", "stop", timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        c["up"] = False


def _rows_for(c, path: Path) -> list[tuple]:
    import duckdb
    root = c["root"]
    # The writer's file, as `Store._active_slot_path` picks it: the slot the `active` marker
    # names (a store a daemon has served), else the pre-rotation `catalog.duckdb` (a store only
    # the CLI's in-process route has written).
    active = root / "active"
    slot = (root / f"catalog.{active.read_text().strip()}.duckdb") if active.exists() else None
    cat = slot if slot is not None and slot.exists() else root / "catalog.duckdb"
    con = duckdb.connect(str(cat), read_only=True)
    try:
        return [tuple(r) for r in con.execute(
            "SELECT kind, name FROM entities WHERE path = ?", [str(path)]).fetchall()]
    finally:
        con.close()


def _verdict(c, r: subprocess.CompletedProcess, target: Path) -> None:
    out = r.stdout + r.stderr
    assert r.returncode != 0, (f"`rmx ingest {target.name}` exited 0 (a file must be refused); "
                               f"output:\n{out}")
    errs = [ln for ln in out.splitlines() if ln.startswith("Error:")]
    assert len(errs) == 1, f"a refusal prints exactly one Error: line; got {errs}\n{out}"
    assert "rmx sync -f" in errs[0], f"the refusal must name `rmx sync -f`: {errs[0]!r}"
    _stop(c)
    assert not _rows_for(c, target), f"a refused ingest wrote rows for {target}"


@pytest.mark.parametrize("rel", ["CLAUDE.md", "docs/notes.md"])
def test_ingest_of_a_file_by_absolute_path_is_refused_naming_sync(proj, rel):
    target = proj["proj"] / rel
    _verdict(proj, _rmx(proj["env"], "ingest", str(target)), target)


def test_ingest_of_a_file_by_relative_path_is_refused_naming_sync(proj):
    """The live form: `rmx ingest CLAUDE.md` from the project root."""
    target = proj["proj"] / "CLAUDE.md"
    _verdict(proj, _rmx(proj["env"], "ingest", "CLAUDE.md", cwd=proj["proj"]), target)


def test_guard_ingest_of_a_directory_still_ingests_it(proj):
    r = _rmx(proj["env"], "ingest", str(proj["proj"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Error:" not in r.stdout + r.stderr
    _stop(proj)
    for rel in FILES:
        assert _rows_for(proj, proj["proj"] / rel), f"directory ingest lost {rel}\n{r.stdout}"
