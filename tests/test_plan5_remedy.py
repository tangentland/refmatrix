"""bsd-plan5-r2 remedy (round 3 of plan 5).

#b-1-r2  a BOOTING daemon (live pid, socket not bound yet) was "absent" to the
         write control point, so the in-process writer opened the live slot in
         the window plan 4 opens on every relaunch — the lock-collision boots
         in daemon.stderr.log. A live rmx pid is busy with or without a socket;
         a foreign process that reused the pid is not.
#b-2-r2  `memory sync-disk` was deleted while the p20-0 guardrail compiler of
         nine projects called it behind `>/dev/null 2>&1 || true`. The alias is
         back (thin: it IS the bridge), the compiler calls the canonical
         command and fails when the seed step fails, and the generated
         SessionStart entry no longer hides the script's exit.
#s-3-r2  the dead 60-line body is gone (the alias is the 15 lines that matter).
#s-4-r2  the silent-socket fixture is SEEDED so "the slot was not touched" is
         an assertion on a real file, not on a constant.
#m-5-r2  "retry shortly" once; hand docs teach the canonical command.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery
from refmatrix.store import Store

REPO = Path(__file__).resolve().parents[1]
GMD = "---\ngmd: \"0.1\"\nid: {id}\ntitle: t\ntags: [x]\n---\n\n# T {{#root}}\n\n{body}\n"


def _seeded_root() -> tuple[Path, Path]:
    """A real initialised store on a short /tmp path (unix-socket length)."""
    base = Path(tempfile.mkdtemp(prefix="rmxb-", dir="/tmp"))
    root = base / ".refmatrix"
    s = Store(root); s.init(); s.close()
    return base, root


def _slot_stat(root: Path) -> dict:
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in root.glob("catalog*.duckdb")}


def _child(*argv_tail: str) -> subprocess.Popen:
    """A real live process; argv decides whether it looks like an rmx daemon.
    Waits for the interpreter to exec: the venv launcher's argv[0] lives under
    the repo path (`.../refmatrix/.venv-eval/...`) for a moment, and `ps`
    would report that as rmx."""
    p = subprocess.Popen([sys.executable, "-c",
                          "import sys,time; print('ready', flush=True); time.sleep(300)",
                          *argv_tail], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    assert p.stdout.readline().strip() == "ready"
    return p


class _BootingDaemon:
    """serve_forever's boot window: pid file written, Store open, socket NOT
    bound yet. The pid is a real process whose argv names rmx, as the
    supervised daemon's does (`.../bin/rmx daemon start --no-detach`)."""

    def __init__(self):
        self.base, self.root = _seeded_root()
        self.proc = _child("rmx", "daemon", "start")
        dm.pid_path(self.root).write_text(str(self.proc.pid))
        assert not dm.socket_path(self.root).exists()

    def close(self):
        self.proc.kill(); self.proc.wait()
        shutil.rmtree(self.base, ignore_errors=True)


@pytest.fixture
def booting():
    d = _BootingDaemon()
    try:
        yield d
    finally:
        d.close()


# ---- #b-1-r2 ---------------------------------------------------------------

def test_booting_daemon_is_busy_not_absent(booting):
    st = discovery.daemon_status(booting.root, retries=0)
    assert st["up"] is False and st["busy"] is True and st["pid"] == booting.proc.pid, st
    assert st["socket"] is False


def test_write_control_point_refuses_a_booting_daemon(booting, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: booting.root)
    before = _slot_stat(booting.root)
    assert before, "fixture must be seeded"
    with pytest.raises(click.ClickException, match="busy"):
        cli_mod._store(write=True)
    memdir = booting.base / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text(GMD.format(id="m", body="x"))
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] and "busy" in out["error"] and f"pid={booting.proc.pid}" in out["error"], out
    assert _slot_stat(booting.root) == before, "the slot was written under a booting daemon"


def test_stale_pid_reused_by_a_foreign_process_is_absent():
    base, root = _seeded_root()
    proc = _child("not-a-daemon")
    try:
        dm.pid_path(root).write_text(str(proc.pid))
        st = discovery.daemon_status(root, retries=0)
        assert st["busy"] is False and st["up"] is False, st
        proc.kill(); proc.wait()
        st = discovery.daemon_status(root, retries=0)
        assert st["busy"] is False and st["up"] is False, st
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
        shutil.rmtree(base, ignore_errors=True)


def test_pid_is_rmx_reads_the_process_command_line():
    a = _child("rmx", "daemon", "start"); b = _child("something-else")
    try:
        assert discovery.pid_is_rmx(a.pid) is True
        assert discovery.pid_is_rmx(b.pid) is False
    finally:
        for p in (a, b):
            p.kill(); p.wait()
    assert discovery.pid_is_rmx(a.pid) is False   # gone → not rmx


def test_daemon_status_command_says_starting_for_a_booting_daemon(booting, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: booting.root)
    r = CliRunner().invoke(cli_mod.main, ["daemon", "status"])
    assert "busy" in r.output and "stale" not in r.output, r.output
    assert f"pid={booting.proc.pid}" in r.output


# ---- #s-4-r2: the silent-socket case on a SEEDED store -----------------------

def test_silent_daemon_on_a_seeded_store_leaves_the_slot_untouched(monkeypatch):
    from tests.test_plan2_remedy import _SilentDaemon
    d = _SilentDaemon(seeded=True)
    try:
        before = _slot_stat(d.root)
        assert before, "seeded fixture has catalog files"
        monkeypatch.setattr(cli_mod, "_root", lambda: d.root)
        memdir = d.base / "mem"; memdir.mkdir()
        (memdir / "m.md").write_text(GMD.format(id="m", body="x"))
        out = cli_mod._sync_memory_dir(memdir)
        assert out["error"] and "busy" in out["error"], out
        with pytest.raises(click.ClickException, match="busy"):
            cli_mod._store(write=True)
        assert _slot_stat(d.root) == before
    finally:
        d.close()


# ---- #m-5-r2: wording ---------------------------------------------------------

def test_busy_message_says_retry_once(booting, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: booting.root)
    with pytest.raises(click.ClickException) as ei:
        cli_mod._store(write=True)
    assert str(ei.value).count("retry shortly") == 1, str(ei.value)
    memdir = booting.base / "mem2"; memdir.mkdir()
    (memdir / "m.md").write_text(GMD.format(id="m", body="x"))
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"].count("retry shortly") == 1, out["error"]


# ---- #b-2-r2 / #s-3-r2: the alias is back, thin, and the compiler is loud ----

def test_sync_disk_is_a_thin_alias_of_the_bridge(tmp_path, monkeypatch):
    """No daemon at all → the bridge runs in-process; the row lands; the old
    --mtype/--dry-run knobs are gone."""
    root = tmp_path / ".refmatrix"
    s = Store(root); s.init(); s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    memdir = tmp_path / "mem"; memdir.mkdir()
    (memdir / "alias_row.md").write_text(GMD.format(id="alias_row", body="hello"))
    r = CliRunner().invoke(cli_mod.main, ["memory", "sync-disk", str(memdir)])
    assert r.exit_code == 0, r.output
    s = Store(root)
    try:
        assert s.get_entity("memory", "alias_row") is not None
    finally:
        s.close()
    for bad in (["--mtype", "x"], ["--dry-run"]):
        r = CliRunner().invoke(cli_mod.main, ["memory", "sync-disk", *bad, str(memdir)])
        assert r.exit_code == 2, (bad, r.output)
    src = (REPO / "src" / "refmatrix" / "cli.py").read_text()
    assert "Kept as an alias for one release" not in src
    assert "hand-rolled walker" not in src


def test_sync_disk_alias_fails_loud_when_the_bridge_fails(booting, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: booting.root)
    memdir = booting.base / "mem3"; memdir.mkdir()
    (memdir / "m.md").write_text(GMD.format(id="m", body="x"))
    r = CliRunner().invoke(cli_mod.main, ["memory", "sync-disk", str(memdir)])
    assert r.exit_code != 0 and "busy" in r.output, r.output


def _fake_rmx(bin_dir: Path, *, ingest_exit: int) -> Path:
    """A PATH shim standing in for `rmx`: records argv, fails the bridge step
    on demand, answers the list/get calls with nothing."""
    log = bin_dir / "calls.log"
    sh = bin_dir / "rmx"
    sh.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$@" >> "{log}"
        case "$1" in
          ingest-gmd) echo "bridge said no" >&2; exit {ingest_exit} ;;
          memory) exit 0 ;;
        esac
        exit 0
        """))
    sh.chmod(sh.stat().st_mode | stat.S_IEXEC)
    return log


def _compiler_copy(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / ".claude" / "p20-0" / "guardrails").mkdir(parents=True)
    shutil.copy(REPO / ".claude" / "p20-0" / "compile_guardrails.py",
                proj / ".claude" / "p20-0" / "compile_guardrails.py")
    (proj / ".claude" / "p20-0" / "guardrails" / "g.md").write_text("# g\n")
    return proj


def test_compile_guardrails_seeds_via_the_bridge_and_fails_when_it_fails(tmp_path):
    proj = _compiler_copy(tmp_path)
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    script = proj / ".claude" / "p20-0" / "compile_guardrails.py"

    log = _fake_rmx(bin_dir, ingest_exit=2)
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env)
    calls = log.read_text()
    assert calls.startswith("ingest-gmd --as-memory "), calls
    assert "sync-disk" not in calls
    assert r.returncode != 0, r.stdout + r.stderr
    assert "bridge said no" in r.stderr and "ingest-gmd" in r.stderr

    log.unlink()
    _fake_rmx(bin_dir, ingest_exit=0)
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "memory sync-disk" not in script.read_text()


def test_session_start_guardrail_entry_is_not_silenced(tmp_path):
    from refmatrix.hooks import _claude_hook_block
    proj = _compiler_copy(tmp_path)
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj)
    cmds = [h["command"] for e in block["hooks"]["SessionStart"] for h in e["hooks"]]
    guard = [c for c in cmds if "compile_guardrails.py" in c]
    assert len(guard) == 1, cmds
    assert "|| true" not in guard[0], guard[0]
    # the script's own stdout/stderr/exit reach the session; only `command -v` is quiet
    assert guard[0].rstrip().endswith('compile_guardrails.py"; fi'), guard[0]
    # absent p20-0 dir → exit 0 (the guard is a plain `if`), present → the script's exit
    assert guard[0].lstrip().startswith("if [ -d")


def test_hand_docs_teach_the_canonical_bridge_command():
    for rel in (".claude/agents/ch-bsd.md", ".claude/p20-0/README.md",
                ".claude/p20-0/compile_guardrails.py"):
        text = (REPO / rel).read_text()
        assert "memory sync-disk" not in text, rel
    reg = (REPO / "workflow" / "deferral_registry.md").read_text()
    assert "sync-disk" in reg, "the alias needs a registry row naming its removal trigger"
