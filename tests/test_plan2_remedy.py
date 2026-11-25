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
import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)


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


def _hwq_session(root: Path, prefix: str, *, subject: "str | None" = None):
    """An STM session with one input event (and an active subject) on `root`; returns
    (session, digest name) as `focus summarize --promote` derives the name."""
    import re as _re
    import uuid as _uuid
    from refmatrix import stm as stm_mod
    sess = f"{prefix}{_uuid.uuid4().hex[:6]}"
    s = stm_mod.Stm(root, sess)
    s.record("input", "turn-end promote under a held writer")
    if subject:
        s.set_subject(subject)
    return sess, "focus_summary_" + (_re.sub(r"[^A-Za-z0-9]+", "", sess)[:12] or "default")


def _stop_promote_cmd(root: Path, seconds: float) -> str:
    """The GENERATED Stop-hook promote with a test-sized budget (`tests.timing.with_budget`
    raises unless the command carries exactly one `--timeout`: the bound stays pinned)."""
    from tests.task21_1_support import generated_cmd
    from tests.timing import with_budget
    return with_budget(generated_cmd(root, "Stop", "focus summarize --promote"), seconds)


def test_focus_summarize_promote_refuses_without_daemon():
    """Stop runs `focus summarize --promote` every turn; with the daemon down
    it must refuse loudly, not open the active slot from a CLI process.

    task-hook-writes-queue AC-5 (L212, 2026-11-24): graduated from a patched `daemon.ping` to
    NO daemon at all, through the generated Stop command. An absent daemon will not drain a
    queue and constitution VII forbids the hook's Store open, so `_write_or_local(local=None)`
    raises absent: today's refusal, exit 1, and NO spool entry. A GUARD: it passes at the base
    by design. Mutation: an entry appended before the absent check (or `local=None` falling
    back to a Store) fails it."""
    from tests.held_writer import flat, spool_dir
    from tests.task21_1_support import run_hook
    root = Path(_os.environ["REFMATRIX_ROOT"])
    sess, _name = _hwq_session(root, "hwqac5")
    r = run_hook(_stop_promote_cmd(root, 3), root=root,
                 envelope={"session_id": sess, "hook_event_name": "Stop"}, RMX_SESSION=sess)
    out = flat(r.stdout + r.stderr)
    assert r.returncode == 1, out
    assert "daemon not running for" in out and "rmx daemon start" in out, out
    assert "queued" not in out, out
    sp = spool_dir(root)
    assert not sp.exists() or not any(sp.iterdir()), list(sp.rglob("*"))


# ---- round 2 (bsd-plan2-r2) ----

# `test_stop_promote_is_bounded_and_fails_loud_when_busy` (patched `daemon.call` raising
# TimeoutError) and `test_promote_timeout_message_says_not_confirmed` were RETIRED by
# task-hook-writes-queue (L212, 2026-11-24): a busy daemon no longer fails the Stop hook, it
# queues the digest and exits 0 (D6). Their replacement runs on a REAL daemon whose writer is
# REALLY held (`test_stop_promote_queues_and_exits_0_while_the_writer_is_held`); the "not
# confirmed / may still complete" wording itself stays pinned on the classifier
# (`test_task3_6_r9_remedy.py::test_a_write_timeout_is_not_confirmed_and_may_still_complete`).


def test_stop_promote_queues_and_exits_0_while_the_writer_is_held():
    """task-hook-writes-queue AC-1 (bug-309: 72 of 136 turn-end promotes timed out at 8.04 s
    on a held writer, each a hook error). With the daemon's REAL `_store_lock` held, the
    generated Stop command exits 0 WHILE THE WRITER IS STILL HELD (an ordering check, no
    clock), prints `queued: focus_summary_<slug>` and `QUEUED_WRITE_MSG`, and leaves ONE spool
    entry: the R11.2 shape, `args.updated_at == ts`, the session's active subject riding in
    the entry, `origin` "stop-hook" (decided: the Stop hook is this command's only generated
    caller since PreCompact promotes inside save-state). After the release the daemon's flush
    tick drains it: the spool is empty, `rmx memory get` shows the digest, it is filed under
    the subject, and facts.log holds ONE `memory_content` event for it (the timed-out dial
    lands too; the authoring-time guard skips the second write, AC-4).
    Mutations: the hook dials with no `queue=` (times out, exit 1); the drain never deletes
    (spool not empty)."""
    import json as _json
    from refmatrix import discovery, verbs
    from tests.held_writer import HeldWriterDaemon, facts_events, flat, spool_files
    from tests.task21_1_support import run_hook, run_rmx
    from tests.timing import wait_for
    root = Path(_os.environ["REFMATRIX_ROOT"])
    label = "hwq subject"
    sess, name = _hwq_session(root, "hwqac1", subject=label)
    cmd = _stop_promote_cmd(root, 3)
    with HeldWriterDaemon(root, flush_s=1.0) as hd:
        hd.hold()
        r = run_hook(cmd, root=root, envelope={"session_id": sess, "hook_event_name": "Stop"},
                     RMX_SESSION=sess)
        out = flat(r.stdout + r.stderr)
        assert r.returncode == 0, (
            f"the Stop promote must enqueue and exit 0 on a held writer; rc={r.returncode}: "
            f"{out}")
        assert hd.is_held(), "the hook returned only after the writer was released"
        assert f"queued: {name}" in out, out
        assert flat(verbs.QUEUED_WRITE_MSG.format(name=name)) in out, out
        files = spool_files(root)
        assert len(files) == 1, files
        e = _json.loads(files[0].read_text(encoding="utf-8"))
        assert (e["op"], e["name"], e["partition"]) == (
            "memory_add", name, discovery.resolve_partition(root, cwd=root.parent)), e
        assert e["subject"] == label and e["origin"] == "stop-hook", e
        assert e["args"]["name"] == name and e["args"]["updated_at"] == e["ts"], e
        assert e["args"]["mtype"] == "session/digest", e

        hd.release()
        wait_for(lambda: not spool_files(root), timeout=30.0,
                 what="the daemon's flush tick to drain the spool")
        wait_for(lambda: (lambda p: p.returncode == 0
                          and f"Session summary — {sess}" in p.stdout)(
            run_rmx(["memory", "get", name], root=root)), timeout=30.0,
            what=f"`rmx memory get {name}` to show the digest")
        wait_for(lambda: (lambda p: p.returncode == 0 and name in p.stdout)(
            run_rmx(["memory", "recall", "--subject", label, "--json"], root=root)),
            timeout=30.0, what=f"the digest to be filed under {label!r}")
        assert hd.proc.poll() is None, hd.stderr_tail()
    evs = facts_events(root, op="memory_content", name=name)
    assert len(evs) == 1, f"one authoring time, {len(evs)} memory_content events: {evs}"


def test_stop_promote_fails_loud_when_the_enqueue_fails():
    """task-hook-writes-queue AC-6 / D6: a queue that cannot take the entry is not a queued
    promote. With the writer held and the spool directory unwritable, the Stop command exits 1
    naming the cause (the OS error on the spool), prints no `queued:` line and leaves no
    entry. Nothing on a memory path fails silently."""
    from tests.held_writer import HeldWriterDaemon, flat, spool_dir, spool_files
    from tests.task21_1_support import run_hook
    root = Path(_os.environ["REFMATRIX_ROOT"])
    sess, _name = _hwq_session(root, "hwqac6")
    sp = spool_dir(root)
    sp.mkdir()
    _os.chmod(sp, 0o500)
    try:
        with HeldWriterDaemon(root, flush_s=3600) as hd:
            hd.hold()
            r = run_hook(_stop_promote_cmd(root, 3), root=root,
                         envelope={"session_id": sess, "hook_event_name": "Stop"},
                         RMX_SESSION=sess)
    finally:
        _os.chmod(sp, 0o700)
    out = flat(r.stdout + r.stderr)
    assert r.returncode == 1, out
    assert "Permission denied" in out and "hook_writes.spool" in out, (
        f"the failed enqueue's cause is not named: {out}")
    assert "queued:" not in out, out
    assert not spool_files(root), spool_files(root)


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
        self.base = Path(rmx_sandbox.short_root("rmxs-"))
        self.root = self.base / ".refmatrix"
        self.root.mkdir()
        self.writer = None
        if seeded:
            # a real catalog, so "the slot was not touched" is a file
            # assertion, not a constant (bsd-plan5-r2 #s-4-r2) — and the
            # writer HOLDS it open, the way the held daemon holds its slot:
            # a seeded-but-closed legacy `catalog.duckdb` read as a replica
            # (2026-09-15: the replica-first probe answered from the "held"
            # writer's own file and the hook returned [] without a busy
            # word — a state no live daemon permits, its lock refuses the
            # read-only open). Same-process DuckDB refuses the read-only
            # open of a file another connection holds read-write, which is
            # the cross-process lock conflict's in-process twin.
            from refmatrix.store import Store
            self.writer = Store(self.root); self.writer.init()
        self.proc = rmx_lookalike_process()
        self.pid = self.proc.pid
        daemon_mod.pid_path(self.root).write_text(str(self.pid))
        self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        self.sock.bind(str(daemon_mod.socket_path(self.root)))
        self.sock.listen(16)
        self.held: list = []
        self.ops: list = []          # every op name the daemon was asked (r6: probe counts)
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
        if self.writer is not None:
            try:
                self.writer.close()
            except Exception:
                pass
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
    # --timeout 2, not 0.5 (task-hook-writes-queue, L212): under R11.4 a budget whose dial
    # would get less than MIN_DIAL_S after ENQUEUE_RESERVE_S enqueues without dialing, and the
    # subject filing rides in the entry, so 0.5 would no longer reach the filing leg this
    # test is about. 2 s leaves the dial ~1 s and the filing what is left.
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "2"])
    assert _time.monotonic() - t0 < 3.0
    assert r.exit_code != 0, r.output
    assert "subject" in r.output.lower() and "not confirmed" in r.output.lower()
    # every call carries the bound (the second gets what is LEFT of it — r4 #m-3)
    assert seen and all(0 < t <= 2.0 and rt == 0 for _, t, rt in seen), seen
    assert [op for op, _, _ in seen] == ["memory_add", "subject_upsert"]


def test_stop_promote_says_busy_not_absent_on_a_silent_daemon(silent, monkeypatch):
    """#s-2: a daemon that is alive but not answering is BUSY; the hook must
    not tell the operator to start one. Real pid + real silent socket.

    task-hook-writes-queue (L212, 2026-11-24; R11.4 / D6): busy now QUEUES. The probe that
    answers `busy` enqueues WITHOUT a dial and the command exits 0 with `queued:`; still never
    "not running" / "daemon start". ONE probe: `focus_summarize` drops its own
    `discovery.daemon_status` call and `_write_or_local` -> `require_daemon(retries=0)` is the
    only one (a pass-through spy counts it; mutation: the command keeps its own probe -> 2)."""
    from refmatrix import cli as cli_mod
    from refmatrix import discovery
    from refmatrix import stm as stm_mod
    from tests.held_writer import flat, spool_files
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    monkeypatch.setenv("RMX_SESSION", "s1")
    stm_mod.Stm(silent.root, "s1").record("input", "hi")
    probes: list = []
    real_status = discovery.daemon_status

    def _spy(root, **kw):
        probes.append(kw)
        return real_status(root, **kw)
    monkeypatch.setattr(discovery, "daemon_status", _spy)
    t0 = _time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "0.5"])
    elapsed = _time.monotonic() - t0
    assert r.exit_code == 0, r.output
    assert "queued: focus_summary_s1" in flat(r.output), r.output
    assert "not running" not in r.output and "daemon start" not in r.output
    assert len(spool_files(silent.root)) == 1, list(silent.root.iterdir())
    assert len(probes) == 1, f"one probe classifies the daemon; saw {len(probes)}: {probes}"
    assert elapsed < 2.5, elapsed


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


def _unbounded_precompact_promotes(block: dict) -> "list[str]":
    """The PreCompact hook entries that promote without a bound, or one problem line when NO
    generated PreCompact entry promotes. Empty = bounded. Bounded means: exactly one
    `--timeout N` (N > 0) on the command, and the entry's Claude Code `timeout` above N, so
    rmx fails loud before the harness kills it. No numeric ceiling on N: the default is
    measured, not pinned (L203). bsd-cah r1 #s-2: the earlier amended form asserted
    `all(...)` over an EMPTY list once the promote moved into save-state."""
    import re as _re
    entries = [hk for e in block["hooks"].get("PreCompact", []) for hk in e.get("hooks", [])]
    promoting = [hk for hk in entries
                 if ("rmx save-state" in hk["command"] and "--no-promote" not in hk["command"])
                 or "focus summarize --promote" in hk["command"]]
    if not promoting:
        return ["no PreCompact command promotes"]
    bad = []
    for hk in promoting:
        found = _re.findall(r"--timeout (\d+)", hk["command"])
        ht = hk.get("timeout")
        if len(found) != 1 or int(found[0]) <= 0 or not isinstance(ht, (int, float)) \
                or ht <= int(found[0]):
            bad.append(hk["command"])
    return bad


def test_precompact_promote_is_bounded_too(tmp_path):
    """#m-5: PreCompact is the catch-up, so its budget is longer — but it is
    a budget, not the 180 s default the harness kills at 60 s. Since
    task-compaction-as-handoff R1 the promote runs inside PreCompact's save-state, which
    must carry the bound (bsd-cah r1 #s-2, shape per L203). Must-fail cases: no promoting
    entry, a promote without `--timeout`, two `--timeout`s, and a hook timeout not above N."""
    block = _claude_hook_block(tmp_path / ".refmatrix")
    assert _unbounded_precompact_promotes(block) == []

    def planted(*hks):
        return {"hooks": {"PreCompact": [{"hooks": list(hks)}]}}

    for bad in (planted(),
                planted({"command": "rmx save-state --precompact --no-sync", "timeout": 60}),
                planted({"command": "rmx save-state --precompact --timeout 9 --timeout 9",
                         "timeout": 60}),
                planted({"command": "rmx save-state --precompact --timeout 20", "timeout": 20}),
                planted({"command": "rmx save-state --precompact --timeout 20"}),
                planted({"command": "rmx focus summarize --promote", "timeout": 60})):
        assert _unbounded_precompact_promotes(bad), bad
    ok = planted({"command": "rmx save-state --precompact --no-sync --timeout 20", "timeout": 40})
    assert _unbounded_precompact_promotes(ok) == []


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
            self.ops.append(req.get("op"))
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
        _time.sleep(min(0.2, timeout))
        if op == "memory_add":
            return {"ok": True, "result": {"id": 42}}
        return {"ok": True, "result": {"id": 7}}
    monkeypatch.setattr(daemon_mod, "call", call)
    t0 = _time.monotonic()
    # task-hook-writes-queue (L212, R11.4): --timeout 2 (0.5 now enqueues without a dial). The
    # dial gets `deadline - now - ENQUEUE_RESERVE_S` (1.0), never the whole --timeout, so a
    # timed-out dial still leaves the reserve to enqueue inside the budget; the filing gets
    # what is left. Mutation: the dial given the whole --timeout (seen[0] == 2.0).
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "2"])
    elapsed = _time.monotonic() - t0
    assert elapsed < 1.2, elapsed
    assert r.exit_code == 0, r.output
    assert seen[0][0] == "memory_add" and 0 < seen[0][1] <= 2.0 - 1.0 + 1e-6, (
        f"the dial must get deadline - now - ENQUEUE_RESERVE_S (1.0 s), not the whole "
        f"--timeout: {seen}")
    from refmatrix import verbs as _verbs
    assert (getattr(_verbs, "ENQUEUE_RESERVE_S", None),
            getattr(_verbs, "MIN_DIAL_S", None)) == (1.0, 0.5)
    # the second call got only what was left of the budget
    assert seen[1][1] < 2.0 - 0.2, seen


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
    # --timeout 2 (task-hook-writes-queue, R11.4): 0.5 now enqueues without a dial.
    r = CliRunner().invoke(cli_mod.main, ["focus", "summarize", "--promote", "--timeout", "2"])
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
    rest of the process, and it says so on stderr.

    Retargeted (task 3.6 #r10-amend S1): the CLI's own detector and its process
    cache are gone; `cli._memory_partition_default` asks `verbs.memory_partition`
    (replica -> daemon `partition_list` -> the shared closed-after detector). The
    contract is unchanged: a failed probe WARNS, uses the project partition for
    THIS command, and caches nothing -- the next command asks again."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    from refmatrix import discovery
    from refmatrix.store import default_partition_name
    root = tmp_path / ".refmatrix"; root.mkdir()
    legacy = "memory-" + discovery.store_name(root)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(discovery, "daemon_status",
                        lambda r, **kw: {"up": True, "busy": False, "pid": 4242})
    calls = []

    def call(r, op, args=None, **kw):
        calls.append(op)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return {"ok": True, "result": {"rows": [{"name": legacy}]}}
    monkeypatch.setattr(daemon_mod, "call", call)
    assert cli_mod._memory_partition_default(timeout=1.0) == default_partition_name(root)
    err = capsys.readouterr().err
    assert "warning" in err and "THIS command only" in err, err
    assert cli_mod._memory_partition_default(timeout=1.0) == legacy
    assert calls == ["partition_list", "partition_list"], calls
