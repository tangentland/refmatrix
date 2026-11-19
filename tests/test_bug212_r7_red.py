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

S1 (2026-11-19, one catalog backend) deleted m-1's two tests with `rmx migrate-to-duckdb`;
m-2's guard stays.
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import tempfile

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from tests.test_bug212_r4_red import _errors
from tests.test_bug212_r6_red import _start_running_job
from tests.test_memory_bridge import GMD, live  # noqa: F401 -- `live` is used by name


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
