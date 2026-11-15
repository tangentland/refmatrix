"""bug-216 remedy pins, ruling L86 (dev master, 2026-11-14) — beside tests/test_bug216_remedy_r1.py.

1. B1 with the rule doc present: `rmx ingest <proj>/.claude` judged against the PROJECT root
   lands exactly the GMD `.claude/PROJECT_PROFILE.md` (R11 built-in include) and no other doc
   row — no agent template, no memory file from a memdir under `.claude/`.
2. S1, R4's live procedure as now ruled: the ignore edit THEN `rmx reingest --force
   --no-sessions`. On the old store built by 758bca1's `ingest_gmd_paths` (the build whose
   citer has no legacy relpath row, so `rmx ingest .` hash-skips it — red-216's aac951c
   finding), the procedure binds both citing lines on the rule docs' nodes. `--force` clears
   the GMD content hashes, so the unchanged citer is re-processed. Run in-process (no sandbox
   daemon in this harness): `_root()` -> a throwaway store with no daemon -> the CLI's
   in-process branch, the same passes the daemon route runs.

Throwaway stores under short `/tmp` mkdtemp roots only.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from tests.test_bug216_remedy_r1 import (
    _OLD_BUILD,
    CLAUDE_MD,
    FINDING_MD,
    MEM,
    OLD_SPEC,
    PROFILE_MD,
    R4_SPEC,
    _bound,
    _gmd,
    _new_store,
    _old_src,
    _open,
    _write,
    base,  # noqa: F401 — the shared mkdtemp fixture
)


def _point_cli_at(monkeypatch, root) -> None:
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)


# ---------------------------------------------------------------- 1. B1 with the profile


def test_l86_ingest_of_dot_claude_lands_exactly_the_builtin_included_profile(base, monkeypatch):
    proj = base / "proj"
    _write(proj, "docs/d.md", _gmd("d"))
    _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    _write(proj, ".claude/agents/x.md", _gmd("agent-x"))
    _write(proj, f"{MEM}/feedback_a.md", _gmd("feedback_a", extra_fm="metadata:\n  type: feedback\n"))
    root = proj / ".refmatrix"
    _new_store(root)
    _point_cli_at(monkeypatch, root)
    r = CliRunner().invoke(cli_mod.main, ["ingest", str(proj / ".claude")], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    # "Exactly the profile" is judged by FILE: `ingest_path` also writes a relpath twin doc row
    # for every markdown file it walks (`rmx ingest <proj>` gives both `docs/d.md` and `d`,
    # measured 2026-11-14) — pre-existing, not bug-216's, so the twin is allowed; any doc row
    # from another file under `.claude/` is not.
    prof = (proj / ".claude" / "PROJECT_PROFILE.md").resolve()
    s = _open(root)
    try:
        rows = [(str(k), str(n), str(Path(pth).resolve())) for k, n, pth in s._connect().execute(
            "SELECT kind, name, path FROM entities WHERE kind = 'doc' AND path IS NOT NULL")
            .fetchall() if str(Path(pth).resolve()).startswith(str(proj / ".claude") + "/")]
    finally:
        s.close()
    others = sorted({(n, pth) for _k, n, pth in rows if pth != str(prof)})
    assert others == [], f"`rmx ingest <proj>/.claude` landed doc rows from other files: {others}"
    assert ("doc", "project-profile", str(prof)) in rows, (
        f"the GMD profile (built-in include, R11) did not land as `project-profile`: {rows}")


# ---------------------------------------------------------------- 2. S1, the reingest procedure


@pytest.fixture
def gmd_built_old_store(base):
    """The ingest-gmd-built old store of aac951c's S1 RED: 758bca1's `ingest_gmd_paths` over the
    citer, with the 2026-09-04 ignore file. The citer carries its GMD doc with a matching
    content hash and NO legacy relpath row."""
    proj = base / "proj"
    _write(proj, "CLAUDE.md", CLAUDE_MD)
    _write(proj, ".claude/PROJECT_PROFILE.md", PROFILE_MD)
    _write(proj, "docs/finding.md", FINDING_MD)
    root = proj / ".refmatrix"
    root.mkdir()
    (root / ".refmatrix_ignore").write_text(OLD_SPEC)
    p = subprocess.run([sys.executable, "-c", _OLD_BUILD, str(_old_src(base)), str(root),
                        str(proj), "ingest-gmd"], capture_output=True, text=True,
                       env=dict(os.environ), timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    s = _open(root)
    try:
        assert s.get_entity("concept", "finding#swallow") is not None, "old build: no citer"
        assert s.get_entity("doc", "docs/finding.md") is None, "old build: a relpath row exists"
        assert s.get_entity("concept", "claude#no-silent-failures") is None
    finally:
        s.close()
    return {"proj": proj, "root": root}


def test_l86_r4_edit_then_reingest_force_binds_both_citers(gmd_built_old_store, monkeypatch):
    o = gmd_built_old_store
    f = o["root"] / ".refmatrix_ignore"
    t = f.stat().st_mtime
    f.write_text(R4_SPEC)
    os.utime(f, (t + 5, t + 5))
    _point_cli_at(monkeypatch, o["root"])
    monkeypatch.chdir(o["proj"])
    r = CliRunner().invoke(cli_mod.main, ["reingest", "--force", "--no-sessions"],
                           catch_exceptions=False)
    got = _bound(o["root"])
    assert all(v > 0 for v in got.values()), (
        f"the R4 procedure (edit, then `rmx reingest --force --no-sessions`) left citers "
        f"unbound: {got}\n--- reingest output (exit {r.exit_code}) ---\n{r.output[-3000:]}")
