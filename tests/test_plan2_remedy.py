"""plan-2 remediation (ch-bsd bsd-plan2-hooks-reproducible-03f46b8: #b-1, #b-2,
#s-4, #s-6, #m-7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import hooks as hooks_mod
from refmatrix.hooks import _claude_hook_block, install
from tests.test_hooks_reproducible import _cmds, _project, _apply


def test_enforce_forced_on_emits_entries_without_scripts(tmp_path):
    proj = _project(tmp_path)                      # no .claude/hooks on disk
    block = _claude_hook_block(proj / ".refmatrix", project_root=proj, enforce=True)
    cmds = [c for _, _, c in _cmds(block)]
    assert any(".claude/hooks/enforce-test-to-file.sh" in c for c in cmds)
    assert any(".claude/hooks/enforce-rmx-grep.sh" in c for c in cmds)
    assert any(".claude/hooks/adr-gate.sh" in c for c in cmds)
    assert any("compile_guardrails.py" in c for c in cmds)


def test_force_keeps_a_same_prefix_foreign_hook(tmp_path):
    """#bs-4 one layer down: a user's `enforce-my-own-policy.sh` is NOT rmx's."""
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    settings = proj / ".claude" / "settings.json"
    mine = '[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-my-own-policy.sh" ] && "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-my-own-policy.sh" || true'
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": mine}]}]}}))
    _apply(proj); _apply(proj)
    assert "enforce-my-own-policy" in settings.read_text()
    assert not hooks_mod._is_rmx_hook(mine)


def test_check_detects_a_duplicated_managed_block(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"].append(json.loads(json.dumps(d["hooks"]["Stop"][0])))
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "duplicate" in diff.lower()


def test_check_detects_extra_key_drift(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 5
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "timeout" in diff


def test_check_reports_unmanaged_entries_without_failing(tmp_path):
    proj = _project(tmp_path); _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    d["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "rmx context foo"}]})
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert ok is True
    assert "? Stop" in diff and "rmx context foo" in diff


def test_flags_recorded_without_claude(tmp_path):
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=False,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    assert (proj / ".claude" / "rmx-hooks.json").exists()


def test_check_covers_the_search_scripts(tmp_path, monkeypatch):
    """The three ~/.claude/hooks scripts are the second author of runtime
    behaviour; a modified one is drift."""
    from refmatrix import search_hooks
    hd = tmp_path / "userhooks"
    monkeypatch.setattr(search_hooks, "hooks_dir", lambda: hd)
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=True,
            briefing=False, agent_env=False, search=True, scope="project", apply=True, force=True)
    ok, diff = hooks_mod.check(proj)
    assert ok, diff
    (hd / search_hooks.GUARD_NAME).write_text("#!/bin/sh\nexit 0\n")
    ok, diff = hooks_mod.check(proj)
    assert not ok and search_hooks.GUARD_NAME in diff


def test_focus_summarize_promote_refuses_without_daemon(tmp_path, monkeypatch):
    """Stop runs `focus summarize --promote` every turn; with the daemon down
    it must refuse loudly, not open the active slot from a CLI process."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote"])
    assert r.exit_code != 0
    assert "daemon" in r.output.lower()


# ---- round 2 (bsd-plan2-r2) ----

def test_stop_promote_is_bounded_and_fails_loud_when_busy(tmp_path, monkeypatch):
    """Live: the Stop hook's `focus summarize --promote` took 55 s / 15 s / 6 s
    while the daemon was busy with a bridge + sync (Q4 assumed 0.13 s). The
    hook path is bounded; a timeout is a loud skip, not a wait."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: True)
    def slow_call(root, op, args=None, timeout=60.0, **kw):
        raise TimeoutError(f"no answer in {timeout}s")
    monkeypatch.setattr(daemon_mod, "call", slow_call)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    assert r.exit_code != 0
    assert "busy" in r.output.lower() and "not confirmed" in r.output.lower()
    # the generator passes the bound on the Stop hook
    block = _claude_hook_block(tmp_path / ".refmatrix")
    stop = [c for _, _, c in _cmds(block, "Stop") if "focus summarize --promote" in c][0]
    assert "--timeout" in stop


def test_promote_refusal_names_a_real_flag(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote"])
    assert r.exit_code != 0 and "--no-promote" not in r.output


def test_no_claude_apply_then_check_is_clean(tmp_path):
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=False,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["claude"] is False
    ok, diff = hooks_mod.check(proj)
    assert ok, diff


# (r2's `test_detach_busy_branch_waits_wall_clock_and_names_the_pid`, which
# patched `discovery.daemon_status` and `daemon.ping`, graduated in r3 to
# `test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget` below —
# a real pid + a real silent socket, no patches.)


def test_intuition_doc_describes_the_shipped_stop_hook():
    text = (Path(__file__).resolve().parents[1] / "docs" / "hooks" / "intuition-style-hooks.md").read_text()
    assert "Phase C4" not in text and "out of scope" not in text
    assert "focus summarize --promote" in text


# ---- round 3 (bsd-plan2-r3): the bound covers the whole hook path ----

import os as _os
import socket as _socket
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time


def rmx_lookalike_process() -> "_subprocess.Popen":
    """A real live process whose argv names rmx, as a daemon's does
    (`.../bin/rmx daemon start --no-detach`, `python -m refmatrix.cli daemon
    start`). `discovery.pid_is_rmx` reads the command line (bsd-plan5-r2
    #b-1-r2), so a fixture's pid file must point at such a process — not at
    the pytest process. Waits for the interpreter to exec: the venv
    launcher's argv[0] sits under the repo path for a moment."""
    p = _subprocess.Popen([_sys.executable, "-c",
                           "import sys,time; print('ready', flush=True); time.sleep(300)",
                           "rmx", "daemon", "start"],
                          stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL, text=True)
    assert p.stdout.readline().strip() == "ready"
    return p


class _SilentDaemon:
    """A live pid + a listening socket that never answers: the state
    `daemon.ping` conflates with dead (index rebuild at startup, writer
    holding the lock). Short /tmp path so the unix socket binds."""

    def __init__(self, seeded: bool = False):
        from refmatrix import daemon as daemon_mod
        self.base = Path(_tempfile.mkdtemp(prefix="rmxs-", dir="/tmp"))
        self.root = self.base / ".refmatrix"
        self.root.mkdir()
        if seeded:
            # a real catalog, so "the slot was not touched" is a file
            # assertion, not a constant (bsd-plan5-r2 #s-4-r2)
            from refmatrix.store import Store
            st = Store(self.root); st.init(); st.close()
        self.proc = rmx_lookalike_process()
        self.pid = self.proc.pid
        daemon_mod.pid_path(self.root).write_text(str(self.pid))
        self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self.sock.bind(str(daemon_mod.socket_path(self.root)))
        self.sock.listen(16)
        self.held: list = []
        self._stop = False
        _threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
                self.held.append(c)      # never read, never reply
            except OSError:
                return

    def close(self):
        self._stop = True
        for c in self.held:
            try:
                c.close()
            except OSError:
                pass
        self.sock.close()
        self.proc.kill(); self.proc.wait()
        import shutil
        shutil.rmtree(self.base, ignore_errors=True)


@pytest.fixture
def silent():
    d = _SilentDaemon()
    yield d
    d.close()


def test_stop_promote_bounds_subject_filing_and_is_loud(tmp_path, monkeypatch):
    """#b-1: with an active subject the promote made two more daemon calls at
    60 s x 3. Every call on the hook path carries the bound; a stalled
    subject_upsert is a loud, bounded failure."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    s = stm_mod.Stm(root, "s1"); s.record("input", "hi"); s.set_subject("topic-x")
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda root, **kw: {"up": True, "busy": False, "pid": 1})
    seen = []

    def call(root, op, args=None, timeout=60.0, retries=2, **kw):
        seen.append((op, timeout, retries))
        if op == "memory_add":
            return {"ok": True, "result": {"id": 42}}
        raise TimeoutError(f"no answer in {timeout}s")
    monkeypatch.setattr(daemon_mod, "call", call)
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    assert _time.monotonic() - t0 < 3.0
    assert r.exit_code != 0, r.output
    assert "subject" in r.output.lower() and "not confirmed" in r.output.lower()
    # every call carries the bound (the second gets what is LEFT of it — r4 #m-3)
    assert seen and all(0 < t <= 0.5 and rt == 0 for _, t, rt in seen), seen
    assert [op for op, _, _ in seen] == ["memory_add", "subject_upsert"]


def test_stop_promote_says_busy_not_absent_on_a_silent_daemon(silent, monkeypatch):
    """#s-2: a daemon that is alive but not answering is BUSY; the hook must
    not tell the operator to start one. Real pid + real silent socket."""
    from refmatrix import cli as cli_mod
    from refmatrix import stm as stm_mod
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(silent.root, "s1").record("input", "hi")
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    elapsed = _time.monotonic() - t0
    assert r.exit_code != 0
    assert f"busy pid={silent.pid}" in r.output
    assert "not running" not in r.output and "daemon start" not in r.output
    assert "not confirmed" in r.output
    assert elapsed < 2.5, elapsed


def test_promote_timeout_message_says_not_confirmed(tmp_path, monkeypatch):
    """#m-6: the daemon may still complete the write; say so."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(root, "s1").record("input", "hi")
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda root, **kw: {"up": True, "busy": False, "pid": 1})
    def slow(root, op, args=None, timeout=60.0, **kw):
        raise TimeoutError("x")
    monkeypatch.setattr(daemon_mod, "call", slow)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    assert r.exit_code != 0
    assert "not confirmed within 0.5s" in r.output and "may still complete" in r.output
    assert "skipped" not in r.output


def test_detach_on_a_silent_daemon_costs_one_probe_plus_the_budget(silent, monkeypatch):
    """#s-3 (graduates the daemon_status patch): timed against a REAL silent
    socket. One cheap probe + the budget, and the message reports the
    wall the operator actually waited."""
    from refmatrix import cli as cli_mod
    memdir = silent.base / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    monkeypatch.setenv("RMX_DETACH_WAIT_S", "1")
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    elapsed = _time.monotonic() - t0
    assert r.exit_code != 0
    assert f"busy pid={silent.pid}" in r.output
    assert elapsed < 3.0, f"waited {elapsed:.1f}s for a 1s budget"
    import re
    m = re.search(r"not answering for ([0-9.]+)s", r.output)
    assert m, r.output
    assert abs(float(m.group(1)) - elapsed) < 0.6, (m.group(1), elapsed)


def test_precompact_promote_is_bounded_too(tmp_path):
    """#m-5: PreCompact is the catch-up, so its budget is longer — but it is
    a budget, not the 180 s default the harness kills at 60 s."""
    block = _claude_hook_block(tmp_path / ".refmatrix")
    pre = [c for _, _, c in _cmds(block, "PreCompact") if "focus summarize --promote" in c][0]
    assert "--timeout 30" in pre


def test_no_claude_apply_reaps_a_previously_installed_block(tmp_path):
    """#m-7: `--no-claude --apply --force` on a project that carries the rmx
    block removes it; `--check` is clean afterwards."""
    proj = _project(tmp_path)
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=True,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    assert hooks_mod._managed_entries(json.loads((proj / ".claude" / "settings.json").read_text())["hooks"])
    install(project_root=proj, refmatrix_root=proj / ".refmatrix", git=False, claude=False,
            briefing=False, agent_env=False, search=False, scope="project", apply=True, force=True)
    data = json.loads((proj / ".claude" / "settings.json").read_text())
    assert not hooks_mod._managed_entries(data.get("hooks") or {})
    ok, diff = hooks_mod.check(proj)
    assert ok, diff


def test_daemon_status_takes_a_probe_budget(silent):
    from refmatrix import discovery
    t0 = _time.monotonic()
    st = discovery.daemon_status(silent.root, retries=0)
    assert _time.monotonic() - t0 < 1.2
    assert st["busy"] is True and st["up"] is False and st["pid"] == silent.pid


# ---- round 4 (bsd-plan2-r4): the bound covers every call on the hook path ----

class _PingOnlyDaemon(_SilentDaemon):
    """Answers `ping` (so `daemon_status` says up) and stalls every other op
    — the writer-lock state: the bridge ingest or a post-commit sync holds
    the store while the hooks fire."""

    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            _threading.Thread(target=self._serve_one, args=(c,), daemon=True).start()

    def _serve_one(self, c):
        import json as _json
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = c.recv(65536)
                if not chunk:
                    return
                buf += chunk
            req = _json.loads(buf.decode() or "{}")
            self.held.append(c)
            if req.get("op") == "ping":
                c.sendall((_json.dumps({"ok": True, "result": {"pid": self.pid, "version": "x"}}) + "\n").encode())
        except OSError:
            pass


@pytest.fixture
def pingonly():
    d = _PingOnlyDaemon()
    yield d
    d.close()


def test_detach_is_bounded_when_the_daemon_answers_ping_but_holds_the_store(pingonly, monkeypatch):
    """#s-1: partition_list (writer lock) and ingest_gmd_start ran with the
    library defaults behind the "one cheap probe": 30 s, then 180 s with a
    blank traceback. Every call on the path carries the budget and a stall
    is the same loud busy message."""
    from refmatrix import cli as cli_mod
    memdir = pingonly.base / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: pingonly.root)
    monkeypatch.setenv("RMX_DETACH_WAIT_S", "1")
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    elapsed = _time.monotonic() - t0
    assert r.exit_code != 0
    assert "Traceback" not in r.output and "busy" in r.output and f"pid={pingonly.pid}" in r.output
    assert elapsed < 4.0, f"waited {elapsed:.1f}s for a 1s budget"


def test_save_state_surfaces_a_subject_filing_failure(tmp_path, monkeypatch):
    """#s-2: `filed_subject_error` was written by finalize_save_state and
    read by nothing. The verb carries it and the CLI prints it."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    from refmatrix import verbs
    root = tmp_path / "proj" / ".refmatrix"; root.mkdir(parents=True)
    memdir = tmp_path / "mem"; memdir.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    s = stm_mod.Stm(root, "s1"); s.record("input", "hi"); s.set_subject("topic-x")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: True)

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        if op == "memory_add":
            return {"ok": True, "result": {"id": 42}}
        if op == "subject_upsert":
            return {"ok": False, "error": "boom"}
        return {"ok": True, "result": {}}
    monkeypatch.setattr(daemon_mod, "call", call)
    res = verbs.save_state(root, session="s1", memory_dir=str(memdir), lint=False, sync=False)
    assert "boom" in (res.get("filed_subject_error") or "")
    r = CliRunner().invoke(cli_mod.main, ["save-state", "--memory-dir", str(memdir), "--no-lint", "--no-sync"])
    assert r.exit_code == 0, r.output
    assert "subject filing failed" in r.output and "boom" in r.output


def test_stop_promote_never_exceeds_its_timeout_across_calls(tmp_path, monkeypatch):
    """#m-3: the budget is a DEADLINE for the command, not a per-call
    allowance (probe + 3 x --timeout worst case before)."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    s = stm_mod.Stm(root, "s1"); s.record("input", "hi"); s.set_subject("topic-x")
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda root, **kw: {"up": True, "busy": False, "pid": 1})
    seen = []

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        seen.append((op, timeout))
        _time.sleep(min(0.4, timeout))
        if op == "memory_add":
            return {"ok": True, "result": {"id": 42}}
        return {"ok": True, "result": {"id": 7}}
    monkeypatch.setattr(daemon_mod, "call", call)
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    elapsed = _time.monotonic() - t0
    assert elapsed < 1.2, elapsed
    # the second call got only what was left of the budget
    assert seen[0][1] == 0.5 and seen[1][1] < 0.5, seen


def test_subject_filing_refusal_is_not_reported_as_a_timeout(tmp_path, monkeypatch):
    """#m-4: an ok:false reply is a refusal; it will not "still complete"."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    s = stm_mod.Stm(root, "s1"); s.record("input", "hi"); s.set_subject("topic-x")
    monkeypatch.setattr("refmatrix.discovery.daemon_status",
                        lambda root, **kw: {"up": True, "busy": False, "pid": 1})

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        if op == "memory_add":
            return {"ok": True, "result": {"id": 42}}
        return {"ok": False, "error": "boom"}
    monkeypatch.setattr(daemon_mod, "call", call)
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    assert r.exit_code != 0
    assert "refused" in r.output and "boom" in r.output
    assert "still complete" not in r.output


# ---- round 5 (bsd-plan2-r5): the per-prompt recall hook is bounded ----------------

def test_recall_hook_modes_are_bounded_and_degrade_to_empty(pingonly, monkeypatch):
    """#b-1: `memory recall --stdin-json` (UserPromptSubmit) and
    `--session-start` (SessionStart) held the turn ~20 s p50 live with no
    bound. On a daemon that answers ping but holds the store: wall < budget
    + 1, exit 0 (never 2 — that erases the prompt), `[]` on stdout, a
    warning on stderr."""
    import json as _json
    from refmatrix import cli as cli_mod
    monkeypatch.setattr(cli_mod, "_root", lambda: pingonly.root)
    for argv, stdin in ((["memory", "recall", "--stdin-json", "--k", "5", "--scope", "both",
                          "--json", "--timeout", "1"], _json.dumps({"prompt": "hello world"})),
                        (["memory", "recall", "--session-start", "--k", "10", "--scope", "both",
                          "--json", "--timeout", "1"], None)):
        t0 = _time.monotonic()
        r = CliRunner().invoke(cli_mod.main, argv, input=stdin)
        elapsed = _time.monotonic() - t0
        assert r.exit_code == 0, (argv, r.output, r.stderr)
        assert elapsed < 1.6, (argv, elapsed)      # budget + 0.6 (r6 #s-2)
        assert _json.loads(r.stdout) == []
        assert "warning" in (r.stderr or "") and "busy" in (r.stderr or ""), (argv, r.stderr)


def test_recall_hook_modes_default_to_a_five_second_budget_and_the_generator_says_so(tmp_path):
    from refmatrix.cli import main as cli_main
    cmd = cli_main.commands["memory"].commands["recall"]
    opt = next(p for p in cmd.params if p.name == "timeout")
    assert opt.default == 30.0      # == verbs.memory_recall's default; hooks pass their own
    block = _claude_hook_block(tmp_path / ".refmatrix")
    ups = [c for _, _, c in _cmds(block, "UserPromptSubmit") if "memory recall --stdin-json" in c]
    ss = [c for _, _, c in _cmds(block, "SessionStart") if "memory recall --session-start" in c]
    assert ups and all("--timeout 5" in c for c in ups), ups
    assert ss and all("--timeout 10" in c for c in ss), ss


def test_verb_recall_timeout_is_a_deadline_across_calls(tmp_path, monkeypatch):
    """The budget covers partition probe + recall + per-hit get + global,
    not each call separately."""
    from refmatrix import daemon as daemon_mod
    from refmatrix import verbs
    monkeypatch.setattr("refmatrix.discovery.daemon_status", lambda r, **kw: {"up": True, "busy": False, "pid": 1})
    monkeypatch.setattr("refmatrix.discovery.store_name", lambda r: "p")
    monkeypatch.setattr(daemon_mod, "ping", lambda r, **kw: True)
    seen = []

    def call(r, op, args=None, timeout=60.0, retries=2, **kw):
        seen.append((op, round(timeout, 2), retries))
        if timeout < 0.3:
            raise TimeoutError("timed out")
        _time.sleep(0.3)
        if op == "partition_list":
            return {"ok": True, "result": {"rows": []}}
        if op == "memory_recent":
            return {"ok": True, "result": {"rows": [{"id": 1, "name": "a", "mtype": "note"}]}}
        return {"ok": True, "result": {}}
    monkeypatch.setattr(daemon_mod, "call", call)
    t0 = _time.monotonic()
    with pytest.raises(verbs.VerbBusyError, match="within 0.5s"):
        verbs.memory_recall(tmp_path, recent=True, k=3, timeout=0.5)
    assert _time.monotonic() - t0 < 1.5
    assert all(rt == 0 for _, _, rt in seen) and seen[0][1] <= 0.5 and seen[-1][1] < seen[0][1], seen


def test_detach_path_has_one_deadline_and_reports_the_wait(pingonly, monkeypatch):
    """#m-3: probe + partition_list + ingest_gmd_start under ONE budget; the
    message says what the operator waited."""
    import re
    from refmatrix import cli as cli_mod
    memdir = pingonly.base / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: pingonly.root)
    monkeypatch.setenv("RMX_DETACH_WAIT_S", "1")
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    elapsed = _time.monotonic() - t0
    assert r.exit_code != 0 and "busy" in r.output
    assert elapsed < 2.5, elapsed
    m = re.search(r"waited ([0-9.]+)s", r.output)
    assert m and abs(float(m.group(1)) - elapsed) < 0.6, (r.output, elapsed)


def test_legacy_partition_probe_warns_and_does_not_cache_a_timeout(tmp_path, monkeypatch, capsys):
    """#m-4: a probe that timed out is not 'no legacy partition' for the
    rest of the process, and it says so on stderr."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    cli_mod._legacy_memory_partition_exists._cache = {}
    calls = []

    def call(r, op, args=None, **kw):
        calls.append(op)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return {"ok": True, "result": {"rows": [{"name": "memory-" + root.parent.name}]}}
    monkeypatch.setattr(daemon_mod, "call", call)
    assert cli_mod._legacy_memory_partition_exists(root, "memory-" + root.parent.name, daemon_up=True) is False
    assert "warning" in capsys.readouterr().err
    assert cli_mod._legacy_memory_partition_exists(root, "memory-" + root.parent.name, daemon_up=True) is True
    assert calls == ["partition_list", "partition_list"]
