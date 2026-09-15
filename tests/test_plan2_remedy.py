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
import tempfile as _tempfile
import threading as _threading
import time as _time


class _SilentDaemon:
    """A live pid + a listening socket that never answers: the state
    `daemon.ping` conflates with dead (index rebuild at startup, writer
    holding the lock). Short /tmp path so the unix socket binds."""

    def __init__(self):
        from refmatrix import daemon as daemon_mod
        self.base = Path(_tempfile.mkdtemp(prefix="rmxs-", dir="/tmp"))
        self.root = self.base / ".refmatrix"
        self.root.mkdir()
        daemon_mod.pid_path(self.root).write_text(str(_os.getpid()))
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
    assert f"busy pid={_os.getpid()}" in r.output
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
    assert f"busy pid={_os.getpid()}" in r.output
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
    assert st["busy"] is True and st["up"] is False and st["pid"] == _os.getpid()


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
                c.sendall((_json.dumps({"ok": True, "result": {"pid": _os.getpid(), "version": "x"}}) + "\n").encode())
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
    assert "Traceback" not in r.output and "busy" in r.output and f"pid={_os.getpid()}" in r.output
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
