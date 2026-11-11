"""Task 26.2, ch-bsd r2 remedy (`workflow/bullshit/2026-11-10-1915-task26.2-r2-remedy-9204814.md`):
b2-1, s2-1, m2-1.

WHY. The user's rule (2026-11-10, verbatim): "if the sync stops in an error, it needs to fail
loudly on the commandline or console, not just logs". r1 made four sync surfaces loud. The fifth
is the most frequent sync in the fleet: the Stop / SubagentStop / SessionStart hooks run
`rmx sync --flush-queue --async`. The daemon runs that flush on a background thread whose only
failure output is one `rmxd.log` line, and the generated hooks discard the CLI's stderr with
`>/dev/null 2>&1 || true` (b2-1). The PostToolUse hook enqueues every edited path, memory files
included, so the r1 fail-closed raise reaches that flush in every project. The same raise, inside
`_sync_paths`'s one transaction, rolls back EVERY path in the batch, and the queue was already
drained -- one corrupt memory row drops the sync of every unrelated file queued with it (s2-1).

Lead's contract (2026-11-10), pinned as behaviour, not as field names:
- b2-1 (a): a failed async flush is recorded on the daemon (route, time, error naming the
  memory), and `rmx daemon status` prints it until that route's next clean flush clears it.
- b2-1 (b): the NEXT `rmx sync --flush-queue --async`, while such an error is recorded, prints
  it to STDERR and exits non-zero (that is how it reaches the console: the hook runs it).
- b2-1 (c): the generated Claude hook commands that run the flush neither discard its stderr nor
  `|| true` its failure, and a hook run over a recorded error fails naming the memory.
- s2-1: one batch of broken x + healthy `docs/d.py`: d.py IS synced; x is refused and named
  (exit != 0 on the CLI route, recorded on the async route); x's anchors are kept; on the queue
  route x is put back on the queue and d.py is not.

Setup as the auditor's probe (`26.2-bsd-r2-probe-async-flush.log`): the memdir sits OUTSIDE the
project tree, under `<base>/.claude/projects/slug/memory` (refmatrix's live layout); x's
`memory_content.metadata` is `'{not json'`; x.md and `docs/d.py` are enqueued together; a
throwaway daemon (no watcher) under a short `mkdtemp(dir="/tmp")` root runs the flush. Children
import this checkout through an absolute PYTHONPATH (m2-1). Nothing is mocked; the hook leg runs
the generated command with `$HOME/bin/rmx` a launcher that execs this checkout's CLI.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hooks as hooks_mod
from refmatrix import sync as syncmod
from tests.test_bridge_move_safety import _anchor_paths, _bridge, _invoke, _memdir, _with_store
from tests.test_bridge_move_safety_r1 import (  # noqa: F401 -- fixtures are used by name
    ANCHORS, CHECKOUT_SRC, MEMORY_X, _restart, _set_metadata_raw, absolute_pythonpath, gitproj,
    gitproj_inproc,
)
from tests.test_sync_fails_loudly_r1 import _DISCARD, _cli_env

D_PY = "def d():\n    return 1\n"


# ---- setup: the auditor's probe, as fixtures ------------------------------------------------

def _outside_memdir(base: Path) -> Path:
    """Outside the project tree, as refmatrix's own memdir under ~/.claude/projects/."""
    return _memdir(base, marker=False, name=".claude/projects/slug/memory")


def _setup(base: Path, proj: Path, root: Path, *, daemon_up: bool) -> tuple[Path, str, str]:
    """Bridge x and y, write `docs/d.py`, break x's metadata. Returns (memdir, x.md, d.py), the
    paths resolved. The daemon is stopped for the metadata write and restarted after."""
    memdir = _outside_memdir(base)
    _bridge(memdir)
    (proj / "docs").mkdir()
    d = proj / "docs" / "d.py"
    d.write_text(D_PY, encoding="utf-8")
    if daemon_up:
        dm.stop_daemon(root)
    _set_metadata_raw(root, "x", "{not json")
    if daemon_up:
        _restart(root)
    return memdir, str((memdir / "a" / "x.md").resolve()), str(d.resolve())


def _enqueue(*paths: str) -> None:
    out = _invoke(["sync", "--enqueue-only", *[a for p in paths for a in ("-f", p)]])
    assert "enqueued" in out, f"fixture: enqueue failed: {out}"


def _rmx(proj: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    """The real CLI in a child, as a hook runs it (cwd = the project)."""
    return subprocess.run([sys.executable, "-m", "refmatrix.cli", *args], capture_output=True,
                          text=True, cwd=str(proj), env=_cli_env(root), timeout=180)


def _log_lines(root: Path) -> list[str]:
    p = root / dm.LOG_NAME
    return p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []


def _async_lines(root: Path) -> list[str]:
    return [ln for ln in _log_lines(root) if "async flush" in ln]


def _status() -> str:
    return CliRunner().invoke(cli_mod.main, ["daemon", "status"]).output


def _await_failed_flush(root: Path, n0: int, *, bound: float = 90.0) -> None:
    """Until the async flush over broken x has finished: `daemon status` names x (the fixed
    daemon), or `rmxd.log` gained an `async flush` line (497f7f0..440d816 log only failures).
    Then a short settle, so the runner has released the store lock."""
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        if len(_async_lines(root)) > n0 or MEMORY_X.search(_status()):
            time.sleep(1.0)
            return
        time.sleep(0.5)
    raise AssertionError(f"the async flush gave no sign of finishing in {bound}s; rmxd.log:\n"
                         + "\n".join(_log_lines(root)[-15:]))


def _failed_async_flush(gitproj) -> tuple[Path, Path, Path, Path, str, str]:
    base, proj, root = gitproj
    memdir, x, d = _setup(base, proj, root, daemon_up=True)
    _enqueue(x, d)
    n0 = len(_async_lines(root))
    r = _rmx(proj, root, "sync", "--flush-queue", "--async", "--project-root", str(proj))
    assert "Traceback" not in r.stderr, f"fixture: the async flush CLI crashed:\n{r.stderr}"
    _await_failed_flush(root, n0)
    return base, proj, root, memdir, x, d


def _entities_at(root: Path, path: str) -> int:
    return _with_store(root, lambda s: s._connect().execute(
        "SELECT count(*) FROM entities WHERE path = ?", (path,)).fetchone()[0])


def _queued(root: Path) -> list[str]:
    q = root / syncmod.QUEUE_FILE
    if not q.exists():
        return []
    return [str(Path(ln.strip()).resolve()) for ln in q.read_text().splitlines() if ln.strip()]


# =============================================================================================
# b2-1 (a): `rmx daemon status` prints a failed async flush until a clean one clears it
# =============================================================================================

def test_b21a_failed_async_flush_is_printed_by_daemon_status_until_a_clean_flush(gitproj):
    base, proj, root, memdir, x, d = _failed_async_flush(gitproj)
    log = [ln for ln in _async_lines(root) if MEMORY_X.search(ln)]
    out = _status()
    assert re.search(r"async", out, re.I) and MEMORY_X.search(out), \
        f"`rmx daemon status` does not print the failed async flush naming memory x " \
        f"(rmxd.log has it: {log}):\n{out}"
    # The route's next CLEAN flush clears it. Forget x through the daemon (the memory verb),
    # so the next flush of x.md has no unreadable owner; queue x.md and d.py again.
    _invoke(["memory", "forget", "x", "--yes"])
    _enqueue(x, d)
    deadline = time.monotonic() + 60
    queued = False
    while not queued and time.monotonic() < deadline:     # wait out a flush still pending
        resp = dm.call(root, "flush_queue_async", {"project_root": str(proj), "semantic": False},
                       timeout=30.0, retries=0)
        assert resp.get("ok"), f"flush_queue_async op failed: {resp}"
        queued = bool(resp["result"].get("queued"))
        if not queued:
            time.sleep(0.5)
    assert queued, "no async flush could be queued in 60s"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and MEMORY_X.search(_status()):
        time.sleep(0.5)
    out = _status()
    assert not MEMORY_X.search(out), \
        f"`rmx daemon status` still prints the failure after a clean async flush:\n{out}"


# =============================================================================================
# b2-1 (b): the next async-flush invocation is loud while an error is recorded
# =============================================================================================

def test_b21b_next_async_flush_cli_prints_the_recorded_error_and_exits_nonzero(gitproj):
    base, proj, root, memdir, x, d = _failed_async_flush(gitproj)
    r = _rmx(proj, root, "sync", "--flush-queue", "--async", "--project-root", str(proj))
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode != 0, \
        f"`rmx sync --flush-queue --async` exited 0 while a failed async flush is recorded\n{text}"
    assert MEMORY_X.search(r.stderr), f"the recorded error naming memory x is not on stderr\n{text}"
    assert "Traceback (most recent call last)" not in r.stderr, f"a crash, not a report\n{text}"


# =============================================================================================
# b2-1 (c): the generated Claude hooks that run the flush keep its failure
# =============================================================================================

def _flush_hook_commands(root: Path) -> dict[str, str]:
    block = hooks_mod._claude_hook_block(root)["hooks"]
    out: dict[str, str] = {}
    for event in ("Stop", "SubagentStop", "SessionStart"):
        for group in block.get(event, []):
            for h in group.get("hooks", []):
                cmd = h.get("command", "")
                if "--flush-queue" in cmd:
                    out[event] = cmd
    return out


def test_b21c_generated_flush_hooks_do_not_discard_the_flush_failure(tmp_path):
    cmds = _flush_hook_commands(tmp_path / ".refmatrix")
    assert set(cmds) == {"Stop", "SubagentStop", "SessionStart"}, f"flush hooks found: {cmds}"
    bad = {}
    for event, cmd in cmds.items():
        # the flush invocation up to the next command separator / group close
        segs = [m.group(0) for m in re.finditer(r"rmx sync --flush-queue[^;)]*", cmd)]
        assert segs, f"{event}: no flush invocation in {cmd!r}"
        hits = [sg for sg in segs if _DISCARD.search(sg)]
        if hits:
            bad[event] = hits
    assert not bad, f"generated hooks discard the flush's failure: {bad}"


@pytest.mark.parametrize("event", ["Stop", "SessionStart"])
def test_b21c_generated_flush_hook_run_over_a_recorded_error_fails_naming_it(gitproj, event):
    """The hook command as generated, run by bash the way Claude Code runs it, with `$HOME/bin/rmx`
    (HOOK_ENV puts it first on PATH) a launcher that execs this checkout's CLI."""
    base, proj, root, memdir, x, d = _failed_async_flush(gitproj)
    cmd = _flush_hook_commands(root)[event]
    home = base / "home"
    (home / "bin").mkdir(parents=True)
    shim = home / "bin" / "rmx"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m refmatrix.cli "$@"\n',
                    encoding="utf-8")
    shim.chmod(0o755)
    env = {**_cli_env(root), "HOME": str(home)}
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=str(proj),
                       env=env, timeout=240)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode != 0, f"the {event} hook exited 0 over a recorded async-flush error\n{text}"
    assert MEMORY_X.search(r.stderr), f"the {event} hook's stderr does not name memory x\n{text}"


# =============================================================================================
# s2-1: one bad memory is refused per path; the rest of the batch is synced
# =============================================================================================

def test_s21_in_process_sync_refuses_x_and_still_syncs_the_rest_of_the_batch(gitproj_inproc):
    base, proj, root = gitproj_inproc
    memdir, x, d = _setup(base, proj, root, daemon_up=False)
    r = _rmx(proj, root, "sync", "--project-root", str(proj), "-f", x, "-f", d)
    text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.returncode != 0, f"`rmx sync -f x.md -f d.py` exited 0 over a refused path\n{text}"
    assert any(MEMORY_X.search(ln + " ") for ln in r.stderr.splitlines()
               if ln.startswith("Error:")), f"no `Error:` line naming memory x\n{text}"
    assert _entities_at(root, d) >= 1, f"docs/d.py was not synced: x's refusal took the batch\n{text}"
    assert set(_anchor_paths(root, "x")) == ANCHORS, \
        f"x's anchors after the refused sync: {_anchor_paths(root, 'x')}"


def test_s21_async_flush_refuses_x_requeues_it_and_syncs_d_py(gitproj):
    base, proj, root, memdir, x, d = _failed_async_flush(gitproj)
    dm.stop_daemon(root)
    assert _entities_at(root, d) >= 1, \
        f"docs/d.py was not synced: x's refusal took the async batch (queue now {_queued(root)})"
    assert set(_anchor_paths(root, "x")) == ANCHORS, \
        f"x's anchors after the refused flush: {_anchor_paths(root, 'x')}"
    q = _queued(root)
    assert x in q, f"x.md was not put back on the queue (the next flush must retry it): {q}"
    assert d not in q, f"d.py was re-queued although it synced: {q}"


# =============================================================================================
# m2-1: a child leg imports this checkout whatever PYTHONPATH the caller set
# =============================================================================================

def test_m21_child_env_imports_this_checkout_under_a_relative_pythonpath(monkeypatch, tmp_path):
    """The caller ran pytest with `PYTHONPATH=src` (relative). A child in a throwaway cwd must
    still import `<checkout>/src/refmatrix`, through the env the tests hand down."""
    # ONLY the relative entry for the checkout: the caller's absolute one is removed, or it
    # would mask the defect (the sandbox's own absolute entries stay).
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        ["src", *[e for e in os.environ.get("PYTHONPATH", "").split(os.pathsep)
                  if e and os.path.normpath(e) != CHECKOUT_SRC]]))
    env = _cli_env(tmp_path / ".refmatrix")
    r = subprocess.run([sys.executable, "-c", "import refmatrix; print(refmatrix.__file__)"],
                       capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    got = Path(r.stdout.strip()).resolve()
    assert got == Path(CHECKOUT_SRC, "refmatrix", "__init__.py").resolve(), \
        f"the child imported {got}, not this checkout ({CHECKOUT_SRC}); env PYTHONPATH=" \
        f"{env.get('PYTHONPATH')!r}"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == CHECKOUT_SRC
    assert all(os.path.isabs(e) for e in env["PYTHONPATH"].split(os.pathsep) if e)
