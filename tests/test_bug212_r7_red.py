"""bug-212 r7 RED: ch-bsd r6 confirm-lite (`workflow/bullshit/2026-11-14-0533-bug212-r6-282589b.md`,
DIRTY 0B/0S/2M, GO) and the lead's ruling L102 (`workflow/plan-review-2026-11-13.md`,
2026-11-14).

WHY:

m-1. r6 aimed migrate-to-duckdb's check at `dst.parent`, but it still asked git about the
    writer-catalog NAMES in that folder, not about `dst` itself. So `--out <repo B>/x.duckdb`
    where repo B commits `x.duckdb` exited 0 with ` M x.duckdb` (a committed file rewritten),
    and `--out <repo B>/.refmatrix/foo.duckdb` beside a tracked `catalog.duckdb` was refused
    although `foo.duckdb` is untracked and nothing committed changes. The question is "does
    git track the file being replaced". The default dst (`<root>/catalog.duckdb`) keeps its
    refusal (r5 `test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog`).
m-2. L98 made a bridge deferred behind a running ingest job a stderr warning in BOTH save-state
    and `rmx memory sync-disk`; only save-state's was pinned. bsd's M3 (the sync-disk warning
    replaced with `pass`) survived: a deferred sync-disk would print nothing and exit 0. This
    is a GUARD -- it passes at bcd861c, where GREEN already built the warning -- proven by M3.

Everything is real: git, the CLI, a throwaway daemon with a REAL running `ingest_gmd_start`
job (the wait shortened through the existing `RMX_BRIDGE_WAIT_S`, nothing patched). No mock.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import store as store_mod
from refmatrix.store import Store
from tests.test_bug212_hooks_in_worktrees import TRACEBACK, Repo, _base_env, _quiet
from tests.test_bug212_r1_remedy import _refusal_head, _refusal_lines, _status_refmatrix_catalogs
from tests.test_bug212_r4_red import _changed, _cli, _digests, _errors
from tests.test_bug212_r5_red import _text
from tests.test_bug212_r6_red import _start_running_job
from tests.test_memory_bridge import GMD, live  # noqa: F401 -- `live` is used by name


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _status(repo_dir: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo_dir), "status", "--porcelain",
                        "--untracked-files=all"], env=_base_env(), capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture
def two_migrate_repos():
    """Repo A: a SQLite `catalog.db` store, IGNORED by git (the migrate source). Repo B: commits
    a DuckDB file `x.duckdb` at its top level AND a store whose `.refmatrix/catalog.duckdb` is
    tracked. No daemon. Short resolved `/tmp` root."""
    base = Path(tempfile.mkdtemp(prefix="b212n-", dir="/tmp")).resolve()
    a = Repo(base)
    try:
        a.proj.mkdir()
        _quiet(a.proj, a, "init", "-q", "--template=", "-b", "main")
        (a.proj / ".gitignore").write_text(".refmatrix/\n", encoding="utf-8")
        _quiet(a.proj, a, "add", "-A")
        _quiet(a.proj, a, "commit", "-q", "-m", "A c0 (store ignored)")
        s = Store(a.store, backend="sqlite")
        s.init()
        s.add_concept("bug212_r7_source")
        s.close()
        assert store_mod.git_tracked_catalogs(a.store) == [], "fixture: A's catalog tracked"
        b = base / "repob"
        b.mkdir()
        _quiet(b, a, "init", "-q", "--template=", "-b", "main")
        d = Store(b / ".refmatrix", backend="duckdb")
        d.init()
        d.close()
        shutil.copyfile(b / ".refmatrix" / "catalog.duckdb", b / "x.duckdb")
        _quiet(b, a, "add", "-A")
        _quiet(b, a, "commit", "-q", "-m", "B c0 (x.duckdb + .refmatrix/catalog.duckdb committed)")
        tracked = subprocess.run(["git", "-C", str(b), "ls-files"], env=_base_env(),
                                 capture_output=True, text=True).stdout.split()
        assert "x.duckdb" in tracked and ".refmatrix/catalog.duckdb" in tracked, tracked
        assert _status(b) == "", "fixture: repo B dirty"
        yield a, b
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(300)
def test_migrate_out_onto_a_committed_non_catalog_named_file_is_refused(two_migrate_repos):
    """m-1 (a): `rmx migrate-to-duckdb --out <repo B>/x.duckdb --overwrite`, where repo B
    COMMITS `x.duckdb`: one `Error:` line `refusing to open <that file> read-write in-process:
    ...`, exit non-zero, `x.duckdb` byte-identical, repo B's status clean. At bcd861c the check
    asks only about writer-catalog NAMES in repo B's top level, finds none, and the migration
    rewrites the committed `x.duckdb`."""
    a, b = two_migrate_repos
    dst = (b / "x.duckdb").resolve()
    before = _sha(dst)
    r = _cli(a, ["migrate-to-duckdb", "--out", str(dst), "--overwrite"])
    text = _text(r)
    status = _status(b)
    assert TRACEBACK not in r.stderr, f"migrate-to-duckdb crashed\n{text}"
    assert _sha(dst) == before and status == "", (
        f"`--out` onto repo B's committed x.duckdb rewrote it (exit {r.returncode})\n"
        f"repo B git status:\n{status}\n{text}")
    assert r.returncode != 0, f"`migrate-to-duckdb --out <committed file>` exited 0\n{text}"
    errs = _errors(r.stderr)
    assert len(errs) == 1 and _refusal_lines(r.stderr, dst) == errs, \
        f"expected ONE `Error:` line `{_refusal_head(dst)} ...`; got {errs}\n{text}"


@pytest.mark.timeout(300)
def test_migrate_out_to_an_untracked_file_beside_a_tracked_catalog_is_allowed(two_migrate_repos):
    """m-1 (b): `rmx migrate-to-duckdb --out <repo B>/.refmatrix/foo.duckdb`, beside repo B's
    TRACKED `catalog.duckdb`; `foo.duckdb` is untracked, so nothing committed changes: exit 0,
    `foo.duckdb` written, repo B's `catalog.duckdb` byte-identical and not modified in git. At
    bcd861c it is refused, because the folder holds a tracked writer-catalog name."""
    a, b = two_migrate_repos
    dst = (b / ".refmatrix" / "foo.duckdb").resolve()
    assert not dst.exists()
    before = _digests(b / ".refmatrix")
    r = _cli(a, ["migrate-to-duckdb", "--out", str(dst)])
    text = _text(r)
    assert _changed(before, _digests(b / ".refmatrix")) == [], \
        f"repo B's tracked catalog changed\n{text}"
    assert _status_refmatrix_catalogs(b) == "", f"repo B's catalog shows modified\n{text}"
    assert r.returncode == 0 and TRACEBACK not in r.stderr and not _errors(r.stderr), \
        f"`--out` to an untracked file beside a tracked catalog was refused or failed\n{text}"
    assert dst.is_file(), f"{dst} was not written\n{text}"


@pytest.mark.timeout(300)
def test_memory_sync_disk_deferred_behind_a_running_job_warns_on_stderr(live, monkeypatch):
    """m-2, GUARD (passes at bcd861c; proven by bsd's M3, the warning replaced with `pass`):
    `rmx memory sync-disk <dir>` while a REAL ingest job holds the daemon's single-active-ingest
    slot, with the wait shortened through `RMX_BRIDGE_WAIT_S`. Exactly one stderr line
    `warning: memory bridge deferred: ...` naming the job id, exit 0, no `Error:` line -- a
    deferral is neither silent nor a failure (L98)."""
    base, root = live
    jid = _start_running_job(base, root)
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "0.2")
    memdir = base / "memory"
    memdir.mkdir()
    (memdir / "mine_r7.md").write_text(GMD.format(id="mine_r7", body="mine"), encoding="utf-8")
    r = CliRunner().invoke(cli_mod.main, ["memory", "sync-disk", str(memdir)])
    text = f"exit {r.exit_code}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    warn = [ln for ln in r.stderr.splitlines()
            if ln.startswith("warning: memory bridge deferred:")]
    assert len(warn) == 1 and jid in warn[0], \
        f"expected ONE stderr `warning: memory bridge deferred:` line naming job {jid}\n{text}"
    assert r.exit_code == 0, f"a deferred sync-disk exited {r.exit_code}\n{text}"
    assert not _errors(r.stderr), f"a deferred sync-disk printed an `Error:` line\n{text}"
