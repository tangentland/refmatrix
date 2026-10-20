"""Task 21.1 AC-4b (i)-(viii) and (xiii): the user-level pointer location, the SessionStart
writer's surfacing, scope, one-shot migration and cleanup, and the ONE hook-envelope reader.

Spec: workflow/plans/plan-21-agent-context-usage-tasks/task-21.1-context-usage-telemetry.md,
R9 deltas D3 (pointer_dir), D4 (SessionStart writer), D5, D6 (scoped surfacing, migration),
D7 (prune), D8 (scoped locked writer), D9 (read_hook_envelope). Revision rounds 7-12 win.

Isolation: the sandbox's global store (`$RMX_HOME`) is ONE directory for the whole session, and
D3 moves pointers and `_errors.jsonl` THERE, keyed by the (shared) test pid. Every test here
therefore gets its OWN `$RMX_HOME` (a fresh, initialized store under the sandbox root), so the
pointer files, watermarks and the error log of one test are invisible to the next.

RED ordering (spec #test-strategy): every leg that needs the SessionStart writer first looks up
the GENERATED `focus hook --event session-start` entry; its absence is the recorded failure.
Legs whose first observable is an in-process write through D8's new signature first assert that
signature (the missing behaviour, named), never a TypeError from a positional mismatch.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests import task21_1_support as h

SS_NEEDLE = "focus hook --event session-start"


# ---- fixtures -------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _live_logs_untouched():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


def _init_store(root: Path) -> None:
    from refmatrix.store import Store
    s = Store(root)
    try:
        s.init()
    finally:
        s.close()


def _new_root() -> Path:
    sys.path.insert(0, str(h.REPO / "tests" / "sandbox_site"))
    import rmx_sandbox
    r = rmx_sandbox.new_store_root(Path(os.environ["RMX_SANDBOX_ROOT"]))
    _init_store(r)
    return r


@pytest.fixture(autouse=True)
def ghome(monkeypatch):
    """A per-test global store root (`$RMX_HOME`), existing (D3: `pointer_dir()` creates only
    `by-pid/`, and only when the global root already exists)."""
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    g = _new_root()
    monkeypatch.setenv("RMX_HOME", str(g))
    return g


@pytest.fixture
def X() -> Path:
    r = Path(os.environ["REFMATRIX_ROOT"])
    (r / "stm").mkdir(exist_ok=True)
    return r


@pytest.fixture
def Y() -> Path:
    r = _new_root()
    (r / "stm").mkdir(exist_ok=True)
    return r


# ---- helpers --------------------------------------------------------------------------------

ME = os.getpid()


def pdir() -> Path:
    """D3: `<hub.global_store_root()>/by-pid/` (sandbox: `$RMX_HOME/by-pid`)."""
    return Path(os.environ["RMX_HOME"]) / "by-pid"


def errlog() -> Path:
    return pdir() / "_errors.jsonl"


def err_rows() -> list[dict]:
    p = errlog()
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            out.append({"reason": "<unparseable>"})
    return out


def ss_cmd(root: Path) -> str:
    """D4: the GENERATED SessionStart writer. RED at HEAD: no such entry."""
    m, cmd = h.generated_entry(root, "SessionStart", SS_NEEDLE)
    assert m == "startup|resume|clear|compact", m
    return cmd


def run_ss(root: Path, *, session="sess-S", source="startup", claude_pid=ME,
           cmd: str | None = None) -> subprocess.CompletedProcess:
    cmd = cmd or ss_cmd(root)
    return h.run_hook(cmd, root=root, envelope={"session_id": session, "source": source,
                                                "hook_event_name": "SessionStart"},
                      CLAUDE_PID=claude_pid, RMX_HOME=os.environ["RMX_HOME"])


def run_input(root: Path, *, session="sess-S", prompt="a prompt", claude_pid=ME,
              cwd: Path | None = None):
    cmd = h.generated_cmd(root, "UserPromptSubmit", "focus hook --event input")
    return h.run_hook(cmd, root=root, cwd=cwd,
                      envelope={"session_id": session, "prompt": prompt,
                                "hook_event_name": "UserPromptSubmit"},
                      CLAUDE_PID=claude_pid, RMX_HOME=os.environ["RMX_HOME"])


def rmx(args, root: Path, *, input=None, claude_pid=ME, timeout=180):
    return h.run_rmx(args, root=root, input=input, timeout=timeout,
                     CLAUDE_PID=claude_pid, RMX_HOME=os.environ["RMX_HOME"])


def assert_d8_signature():
    from refmatrix import stm
    params = list(inspect.signature(stm.record_pointer_error).parameters)
    assert params[:1] == ["reason"] and "root" in params and "owner" in params, (
        "D8: record_pointer_error(reason, *, root, owner, **fields) not built "
        f"(signature is {params})")


def record(reason: str, *, root: Path, owner, **fields) -> bool:
    from refmatrix import stm
    assert_d8_signature()
    return stm.record_pointer_error(reason, root=root, owner=owner, **fields)


def raw_append(row: dict) -> None:
    """A writer-defect fixture row appended by the TEST (not through src/)."""
    errlog().parent.mkdir(parents=True, exist_ok=True)
    with errlog().open("a") as f:
        f.write(json.dumps(row) + "\n")


def recall_state_anomalies(root: Path) -> list[str]:
    r = rmx(["recall-state", "--json"], root)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)["anomalies"]


def count_of(text: str, reason: str) -> int | None:
    """A reason's count on a surfacing line, tolerant of `reason=n`, `reason xn`, `reason: n`
    (the spec fixes `ended_sessions: <reason>=<n>` only)."""
    m = re.search(rf"{re.escape(reason)}\s*(?:=|x|:)\s*(\d+)", text)
    return int(m.group(1)) if m else None


def proc_start(pid: int) -> str:
    from refmatrix import stm
    s = stm._proc_start(pid)
    assert s is not None
    return s


# ---- (i) one location for every store root -------------------------------------------------

def test_ac4b_i_input_hook_pointer_lands_in_the_global_by_pid_and_another_tree_resolves_it(X, Y):
    """AC-4b (i), D3: the input hook run in tree X writes `<global>/by-pid/<pid>.json`; an MCP
    server spawned with cwd in tree Y (its owner = the test pid, its parent) resolves it."""
    run_input(X, session="sess-I")
    ptr = pdir() / f"{ME}.json"
    assert ptr.is_file(), (
        f"D3: pointer not under the global by-pid/ ({ptr}); legacy location has: "
        f"{sorted(p.name for p in (X / 'stm' / 'by-pid').glob('*'))}")
    assert json.loads(ptr.read_text())["session"] == "sess-I"
    with h.McpServer(Y, cwd=Y.parent, RMX_HOME=os.environ["RMX_HOME"]) as m:
        r = m.tool("rmx_focus_note", {"text": "noted from tree Y"})
    assert not r["isError"], r["text"]
    assert (Y / "stm" / "sess-I.jsonl").is_file(), r["text"]


# ---- (ii) legacy pointer dropped, not read --------------------------------------------------

def test_ac4b_ii_legacy_pointer_is_not_read_and_the_first_sessionstart_drops_it(X, monkeypatch):
    """AC-4b (ii), D3 migration: bug-109's `X/stm/by-pid/<pid>.json` is never read; the first
    SessionStart in X deletes it (`legacy_pointers_dropped=1`); an input hook then writes the
    new-location pointer, and the same resolve finds it. RED: bug-109 resolves the legacy file."""
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    monkeypatch.setenv("CLAUDE_PID", str(ME))
    legacy = X / "stm" / "by-pid" / f"{ME}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"session": "sess-L", "pid": ME, "pid_start": proc_start(ME),
                                  "t": time.time()}))
    kw = ({"purpose": "event"}
          if "purpose" in inspect.signature(verbs.resolve_session_source).parameters else {})
    before = len(err_rows())
    res = verbs.resolve_session_source(X, None, **kw)
    assert tuple(res)[0] is None, f"D3: the legacy pointer was read: {tuple(res)}"
    assert tuple(res) == (None, "none"), tuple(res)
    new = err_rows()[before:]
    assert [r["reason"] for r in new] == ["pointer-unresolved"], new
    r = run_ss(X)
    assert not legacy.exists(), r.stdout + r.stderr
    assert "legacy_pointers_dropped=1" in r.stdout, r.stdout
    run_input(X, session="sess-N")
    assert tuple(verbs.resolve_session_source(X, None, **kw)) == ("sess-N", "pointer")


# ---- (iii) and (iii-b) own-row surfacing, and the halving -----------------------------------

def test_ac4b_iii_owner_rows_surface_once_then_iii_b_after_a_halving(X):
    """AC-4b (iii): three rows owned by the test pid print on ONE stdout line with reasons and
    counts, and a second run prints none. (iii-b): N more owned rows until the log halves once;
    the next run prints each SURVIVING owned row above the watermark exactly once plus the
    `errors-truncated` row, whose `dropped` = removed lines and whose `unseen_dropped[pid:start]`
    = removed owned rows above the watermark; surfaced + unseen_dropped = N."""
    cmd = ss_cmd(X)
    from refmatrix import stm
    record("pointer-unresolved", root=X, owner=ME)
    record("pointer-unresolved", root=X, owner=ME)
    record("write-failed", root=X, owner=ME, error="disk full")
    r1 = run_ss(X, cmd=cmd)
    own = [ln for ln in r1.stdout.splitlines() if "pointer-unresolved" in ln]
    assert len(own) == 1, r1.stdout
    assert count_of(own[0], "pointer-unresolved") == 2 and count_of(own[0], "write-failed") == 1, own
    r2 = run_ss(X, cmd=cmd)
    assert "pointer-unresolved" not in r2.stdout and "write-failed" not in r2.stdout, r2.stdout
    assert (pdir() / f"_errors.seen.{ME}").is_file()

    # (iii-b): real 256 KiB bound, one reason for the N new rows
    n = 0
    prev_lines = len(errlog().read_text().splitlines())
    lines_before_halving = None
    while n < 20000:
        record("pointer-stale", root=X, owner=ME, pad="x" * 120)
        n += 1
        rows = err_rows()
        if any(r.get("reason") == "errors-truncated" for r in rows):
            lines_before_halving = prev_lines
            break
        prev_lines = len(rows)
    assert lines_before_halving is not None, "the log never halved"
    rows = err_rows()
    trunc = [r for r in rows if r.get("reason") == "errors-truncated"]
    assert len(trunc) == 1, trunc
    # after = kept + truncation row + the appended row
    removed = lines_before_halving - (len(rows) - 2)
    assert trunc[0]["dropped"] == removed, (trunc[0], removed)
    surviving = sum(1 for r in rows if r.get("reason") == "pointer-stale")
    key = f"{ME}:{proc_start(ME)}"
    # the 3 surfaced rows (at/below the watermark) were the oldest, so they were removed
    assert trunc[0]["unseen_dropped"].get(key) == removed - 3, (trunc[0], removed)
    r3 = run_ss(X, cmd=cmd)
    assert count_of(r3.stdout, "pointer-stale") == surviving, r3.stdout
    assert "errors-truncated" in r3.stdout, r3.stdout
    assert surviving + trunc[0]["unseen_dropped"][key] == n
    r4 = run_ss(X, cmd=cmd)
    assert "pointer-stale" not in r4.stdout, r4.stdout
    _ = stm  # (import kept: the module under test)


# ---- (iv) and (iv-b) prune ------------------------------------------------------------------

def test_ac4b_iv_dead_pointer_and_watermark_are_pruned(X):
    """AC-4b (iv), D7: a pointer AND an `_errors.seen.<pid>` file of a reaped pid are removed by
    the SessionStart run, which prints `pruned=2`."""
    cmd = ss_cmd(X)
    dead = h.reaped_pid()
    pdir().mkdir(parents=True, exist_ok=True)
    ptr = pdir() / f"{dead}.json"
    seen = pdir() / f"_errors.seen.{dead}"
    ptr.write_text(json.dumps({"session": "sess-D", "pid": dead, "pid_start": "123.000001",
                               "t": time.time(), "hook": "input"}))
    seen.write_text(json.dumps({"pid_start": "123.000001", "t": time.time()}))
    r = run_ss(X, cmd=cmd)
    assert not ptr.exists() and not seen.exists(), r.stdout + r.stderr
    assert "pruned=2" in r.stdout, r.stdout


def test_ac4b_iv_b_prune_skipped_when_the_process_lookup_is_unavailable(X, monkeypatch):
    """AC-4b (iv-b), D7 + #m9-1: with `stm._proc_info` returning None for every pid (in process),
    the SessionStart writer removes no file and prints `prune skipped: process lookup
    unavailable`. `_proc_info` is a DEPENDENCY of the prune (the kernel lookup), registered."""
    ss_cmd(X)                                   # RED: the generated writer is absent
    from click.testing import CliRunner
    from refmatrix import stm
    from refmatrix.cli import main
    pdir().mkdir(parents=True, exist_ok=True)
    live = pdir() / f"{ME}.json"
    live.write_text(json.dumps({"session": "sess-S", "pid": ME, "pid_start": proc_start(ME),
                                "t": time.time(), "hook": "input"}))
    dead = h.reaped_pid()
    deadp = pdir() / f"{dead}.json"
    deadp.write_text(json.dumps({"session": "sess-D", "pid": dead, "pid_start": "1.000001",
                                 "t": time.time(), "hook": "input"}))
    monkeypatch.setattr(stm, "_proc_info", lambda pid: None)
    monkeypatch.setenv("CLAUDE_PID", str(ME))
    monkeypatch.setenv("REFMATRIX_ROOT", str(X))
    env = {"session_id": "sess-S", "source": "startup", "hook_event_name": "SessionStart"}
    res = CliRunner().invoke(main, ["focus", "hook", "--event", "session-start"],
                             input=json.dumps(env))
    assert live.exists() and deadp.exists(), res.output
    assert "prune skipped: process lookup unavailable" in res.output, res.output


# ---- (v) recall-state and focus topics read the new location --------------------------------

def test_ac4b_v_new_location_row_reaches_recall_state_and_focus_topics(X, tmp_path):
    """AC-4b (v), D6/D8: a row written through `record_pointer_error` (now under the global
    by-pid/) with root = X appears in `handoff.compose_recall_state`'s anomalies, in `rmx
    recall-state` for X, and as the LAST line of `rmx focus topics` for X, after "no topics
    yet"."""
    from refmatrix import handoff, stm
    assert record("pointer-unresolved", root=X, owner=ME) is True
    assert any(r.get("reason") == "pointer-unresolved" and r.get("root") == str(X)
               for r in err_rows()), err_rows()
    s = stm.Stm(X, "sess-V")
    rep = handoff.compose_recall_state(s, X, repo=tmp_path, memdir=tmp_path / "mem")
    assert any("pointer-unresolved x1" in a for a in rep["anomalies"]), rep["anomalies"]
    assert any("pointer-unresolved x1" in a for a in recall_state_anomalies(X))
    t = rmx(["focus", "topics"], X)
    lines = [ln for ln in t.stdout.splitlines() if ln.strip()]
    assert "no topics yet" in t.stdout, t.stdout
    assert lines and "pointer-unresolved" in lines[-1], t.stdout


# ---- (vi) one-shot migration ----------------------------------------------------------------

def test_ac4b_vi_one_shot_migration_of_the_legacy_log(X):
    """AC-4b (vi), D6 migration: two parseable legacy rows + one unparseable line move to the
    global log with ORIGINAL `t`, root = X, migrated_from = the legacy path, plus one
    `legacy-unreadable` row (n = 1); the file becomes `_errors.migrated.jsonl`; `migrated=2`
    prints; recall-state in X reports both. A second run migrates nothing; an interrupted run
    (legacy name restored) appends nothing again and renames; afterwards no read of
    `X/stm/by-pid/` happens (directory made unreadable, recall-state still succeeds)."""
    cmd = ss_cmd(X)
    leg_dir = X / "stm" / "by-pid"
    leg_dir.mkdir(parents=True, exist_ok=True)
    legacy = leg_dir / "_errors.jsonl"
    now = time.time()
    t1, t2 = now - 3600, now - 7200
    legacy.write_text(json.dumps({"t": t1, "reason": "pointer-unresolved", "owner": 1}) + "\n"
                      + json.dumps({"t": t2, "reason": "no-owner"}) + "\n"
                      + "not json\n")
    r = run_ss(X, cmd=cmd)
    mig = [x for x in err_rows() if x.get("migrated_from") == str(legacy)]
    assert sorted(x["t"] for x in mig if x["reason"] != "legacy-unreadable") == [t2, t1], mig
    assert all(x.get("root") == str(X) for x in mig), mig
    unread = [x for x in mig if x["reason"] == "legacy-unreadable"]
    assert len(unread) == 1 and unread[0]["n"] == 1, mig
    assert not legacy.exists() and (leg_dir / "_errors.migrated.jsonl").is_file()
    assert "migrated=2" in r.stdout, r.stdout
    an = " | ".join(recall_state_anomalies(X))
    assert "pointer-unresolved" in an and "no-owner" in an, an

    n_global = h.line_count(errlog())
    r2 = run_ss(X, cmd=cmd)
    assert h.line_count(errlog()) == n_global and "migrated=0" in r2.stdout, r2.stdout

    # interrupted run: the rows are present in both files
    (leg_dir / "_errors.migrated.jsonl").rename(legacy)
    r3 = run_ss(X, cmd=cmd)
    assert h.line_count(errlog()) == n_global, r3.stdout
    assert not legacy.exists() and (leg_dir / "_errors.migrated.jsonl").is_file()

    an_before = recall_state_anomalies(X)
    mode = leg_dir.stat().st_mode
    try:
        os.chmod(leg_dir, 0)
        an_unreadable = recall_state_anomalies(X)
    finally:
        os.chmod(leg_dir, stat.S_IMODE(mode))
    assert an_unreadable == an_before, (an_before, an_unreadable)


# ---- (vii) scope ----------------------------------------------------------------------------

def test_ac4b_vii_recall_state_is_scoped_by_root_and_unscoped_rows_are_counted_apart(X, Y):
    """AC-4b (vii), D6: one `pointer-unresolved` row scoped to each root; recall-state in X
    reports exactly X's (x1), in Y exactly Y's. A row with no `root` is counted as
    `unscoped-row` in both, never under either's pointer clause."""
    record("pointer-unresolved", root=X, owner=ME)
    record("pointer-unresolved", root=Y, owner=ME)
    raw_append({"t": time.time(), "reason": "pointer-unresolved", "owner": ME})
    for r in (X, Y):
        an = recall_state_anomalies(r)
        ptr = [a for a in an if "pointer-unresolved" in a]
        assert len(ptr) == 1 and "pointer-unresolved x1" in ptr[0], (r, an)
        assert any("unscoped" in a for a in an), (r, an)


_HELPER = r"""
import json, os, subprocess, sys
cmd = sys.argv[1]
env = dict(os.environ); env["CLAUDE_PID"] = str(os.getpid())
print(os.getpid(), flush=True)
for line in sys.stdin:
    if line.strip() == "exit":
        break
    r = subprocess.run(["/bin/bash", "-c", cmd], input=line, env=env, capture_output=True,
                       text=True)
    print(json.dumps({"rc": r.returncode, "out": r.stdout, "err": r.stderr}), flush=True)
"""


class Helper:
    """A helper Claude stand-in: it runs the generated SessionStart hook as its OWN child with
    CLAUDE_PID = its own pid, and stays alive until told to exit."""

    def __init__(self, root: Path, cmd: str):
        self.p = subprocess.Popen([sys.executable, "-c", _HELPER, cmd, "rmx-sandbox-helper"],
                                  env=h.rmx_env(root, RMX_HOME=os.environ["RMX_HOME"]),
                                  cwd=str(root.parent), stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
        self.pid = int(self.p.stdout.readline())

    def run_ss(self, session="sess-P2", source="startup") -> dict:
        self.p.stdin.write(json.dumps({"session_id": session, "source": source,
                                       "hook_event_name": "SessionStart"}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def exit(self):
        if self.p.poll() is None:
            self.p.stdin.write("exit\n")
            self.p.stdin.flush()
            self.p.wait(timeout=30)


def test_ac4b_vii_two_owners_and_an_unowned_row(X):
    """AC-4b (vii), D6 per-owner watermark: P1 (the test) and P2 (a helper) own one row each
    in X. P1's SessionStart surfaces only P1's row and writes only `_errors.seen.<P1>`; P2's run
    afterwards still surfaces P2's. A `no-owner` row (owner null) is surfaced by neither
    (`unowned_in_root=1` on each) and reported by recall-state in X."""
    cmd = ss_cmd(X)
    p2 = Helper(X, cmd)
    try:
        record("pointer-unresolved", root=X, owner=ME)
        record("write-failed", root=X, owner=p2.pid, error="x")
        record("no-owner", root=X, owner=None)
        r1 = run_ss(X, cmd=cmd)
        assert count_of(r1.stdout, "pointer-unresolved") == 1, r1.stdout
        assert "write-failed" not in r1.stdout, r1.stdout
        assert "unowned_in_root=1" in r1.stdout, r1.stdout
        assert (pdir() / f"_errors.seen.{ME}").is_file()
        assert not (pdir() / f"_errors.seen.{p2.pid}").exists()
        r2 = p2.run_ss()
        assert count_of(r2["out"], "write-failed") == 1, r2
        assert "pointer-unresolved" not in r2["out"], r2
        assert "unowned_in_root=1" in r2["out"], r2
    finally:
        p2.exit()
    assert any("no-owner" in a for a in recall_state_anomalies(X))


def test_ac4b_vii_ps_failed_row_is_unowned_never_consumed(X, monkeypatch):
    """AC-4b (vii) ps-failed sub-leg, #nm-1: with `stm._proc_info` returning None for ONE helper
    pid only, `write_pid_pointer` for it writes a `ps-failed` row with owner = that pid and
    `owner_start` null; P1's SessionStart in X does not print it under its own reasons, counts
    it in `unowned_in_root`, and does not consume it (a second run counts it again);
    recall-state in X reports it."""
    cmd = ss_cmd(X)
    from refmatrix import stm
    helper = h.spawn_rmx_named_helper()
    try:
        real = stm._proc_info
        monkeypatch.setattr(stm, "_proc_info",
                            lambda pid: None if int(pid) == helper.pid else real(pid))
        assert stm.write_pid_pointer(helper.pid, "sess-H", root=X) is False
        monkeypatch.setattr(stm, "_proc_info", real)
        rows = [r for r in err_rows() if r.get("reason") == "ps-failed"]
        assert len(rows) == 1 and rows[0]["owner"] == helper.pid, rows
        assert rows[0]["owner_start"] is None and rows[0]["root"] == str(X), rows
        for _ in range(2):
            r = run_ss(X, cmd=cmd)
            assert "ps-failed" not in r.stdout, r.stdout
            assert "unowned_in_root=1" in r.stdout, r.stdout
    finally:
        helper.kill()
        helper.wait(timeout=30)
    assert any("ps-failed" in a for a in recall_state_anomalies(X))


# ---- (viii) two clauses ---------------------------------------------------------------------

def test_ac4b_viii_session_pointer_and_stm_hook_failures_are_two_clauses(X):
    """AC-4b (viii), D6: one `pointer-unresolved` and one `sweep-failed` row in X: recall-state
    prints a session-pointer clause counting 1 with the "could not be resolved" text, and an
    STM-hook clause `sweep-failed x1` with none of the words session / guessed / newest."""
    record("pointer-unresolved", root=X, owner=ME)
    record("sweep-failed", root=X, owner=ME, error="boom")
    an = recall_state_anomalies(X)
    ptr = [a for a in an if "pointer-unresolved" in a]
    hook = [a for a in an if "sweep-failed" in a]
    assert len(ptr) == 1 and "pointer-unresolved x1" in ptr[0], an
    assert "could not be resolved" in ptr[0] and "sweep-failed" not in ptr[0], ptr
    assert len(hook) == 1 and "sweep-failed x1" in hook[0], an
    low = hook[0].lower()
    assert not any(w in low for w in ("session", "guessed", "newest")), hook


# ---- (xiii) prose is not an error; one prompt-key tuple -------------------------------------

def _no_error_rows_for(root: Path, before: int) -> list:
    """The `envelope-*` rows added since `before` (round 13, #b2: AC-4b (xiii)'s "adds no row"
    means no ENVELOPE error. The `rmx(..)` children carry `CLAUDE_PID`, so R9 records its
    resolver miss (`pointer-unresolved`) for them like for every other call -- that row is not
    a prose error and is allowed). The legacy per-root file is read too: no row of any reason
    may land there (D3)."""
    new = [x for x in err_rows()[before:] if str(x.get("reason") or "").startswith("envelope-")]
    legacy = root / "stm" / "by-pid" / "_errors.jsonl"
    return new + (h.jsonl(legacy) if legacy.exists() else [])


def test_ac4b_xiii_brace_prose_to_scan_prompt_is_not_an_error(X):
    """AC-4b (xiii) prose leg on scan-prompt: `printf 'fix the {braces' | rmx scan-prompt` adds
    no `envelope-*` row to `_errors.jsonl` (round 13 #b2), and the prompt it uses (its
    query.log `scan` row body) is the text.
    GREEN regression guard, not counted as RED (no envelope reader records anything today)."""
    before = len(err_rows())
    r = rmx(["scan-prompt"], X, input="fix the {braces")
    assert _no_error_rows_for(X, before) == [], r.stderr
    bodies = [q.get("body") for q in h.query_rows(X) if q.get("kind") == "scan"]
    assert bodies == ["fix the {braces"], (bodies, r.stderr[-1000:])


def test_ac4b_xiii_brace_prose_to_memory_recall_is_not_an_error(X):
    """AC-4b (xiii) prose leg on `rmx memory recall` without --stdin-json: no `envelope-*`
    row in `_errors.jsonl` (round 13 #b2) and no invalid-JSON message. (That command does
    not read stdin without --stdin-json, `read_stdin=False` at cli.py `memory_recall`, so
    "the prompt it uses" is unobservable here; see the report.) GREEN regression guard, not
    counted as RED."""
    before = len(err_rows())
    r = rmx(["memory", "recall"], X, input="fix the {braces")
    assert _no_error_rows_for(X, before) == [], r.stderr
    assert "invalid JSON" not in r.stdout + r.stderr


def test_ac4b_xiii_brace_prose_to_stdin_json_records_envelope_unreadable(X):
    """AC-4b (xiii) `--stdin-json` leg, D9 + #m10-5: the same text to `rmx memory recall
    --stdin-json` exits nonzero with `--stdin-json: invalid JSON on stdin` AND adds one
    `envelope-unreadable` row scoped to X. RED: no row is written today."""
    before = len(err_rows())
    r = rmx(["memory", "recall", "--stdin-json"], X, input="fix the {braces")
    new = [x for x in err_rows()[before:] if x.get("reason") == "envelope-unreadable"]
    assert len(new) == 1 and new[0].get("root") == str(X), (err_rows()[before:], r.stderr)
    assert r.returncode != 0 and "--stdin-json: invalid JSON on stdin" in r.stderr, r.stderr


def test_ac4b_xiii_text_key_envelope_on_scan_prompt(X):
    """AC-4b (xiii), D9 `HOOK_PROMPT_KEYS`: envelope {"text": "abc"} yields the prompt `abc` on
    the scan-prompt path (its query.log `scan` row body). At HEAD `_resolve_query` reads only
    `prompt` from a `{`-prefixed stdin, so the prompt is empty."""
    r = rmx(["scan-prompt"], X, input=json.dumps({"text": "abc"}))
    bodies = [q.get("body") for q in h.query_rows(X) if q.get("kind") == "scan"]
    assert bodies == ["abc"], (bodies, r.stderr[-1000:])


def test_ac4b_xiii_text_key_envelope_on_the_recall_path(X):
    """AC-4b (xiii), D9 on `memory recall --stdin-json`: {"text": "abc"} yields the prompt
    `abc` (observed as the call's `kind=recall` query.log row body, R3, against a live sandbox
    daemon). RED: `_resolve_query` reads `prompt` only, so the hook short-circuits to `[]`."""
    with h.SandboxDaemon(X, RMX_HOME=os.environ["RMX_HOME"]):
        r = rmx(["memory", "recall", "--stdin-json", "--json", "--timeout", "30"], X,
                input=json.dumps({"text": "abc"}))
    bodies = [q.get("body") for q in h.query_rows(X) if q.get("kind") == "recall"]
    assert bodies == ["abc"], (bodies, r.stdout[-500:], r.stderr[-1000:])


# ---- round 13 #b2: R9 records a miss for EVERY invocation (no `record_miss` switch) --------

def _miss_rows(before: int, root: Path) -> list[dict]:
    """Resolver-miss rows (R9: `pointer-unresolved`, or `owner-lookup-failed` when the process
    lookup failed) added since `before`, scoped to `root` (compared canonically, #s3)."""
    want = os.path.realpath(str(root))
    return [x for x in err_rows()[before:]
            if x.get("reason") in ("pointer-unresolved", "owner-lookup-failed")
            and os.path.realpath(str(x.get("root") or "")) == want]


class _TtyStdin:
    """`sys.stdin` answering `isatty()` True (registered: pytest cannot own a real tty), so
    `invocation_source()` -- unpatched -- classifies the call `interactive`."""

    def isatty(self) -> bool:
        return True

    def read(self, *a) -> str:
        return ""


INVOCATIONS = {
    "hook": {"RMX_INVOCATION_SOURCE": "hook"},
    "mcp": {"RMX_INVOCATION_SOURCE": "mcp"},
    "agent": {"CLAUDECODE": "1"},
    "internal": {"RMX_INVOCATION_SOURCE": "internal"},
    "unknown": {},
    "interactive": {},
}


def test_r9_resolver_signature_has_no_miss_switch():
    """Round 13 #b2 / D1: the resolver's signature is EXACTLY `(root, session=None, *,
    envelope=None, purpose)`. A `record_miss`-style parameter is the per-invocation switch
    round 13 removed (a miss is recorded the same way for every purpose and invocation). RED
    at HEAD: `record_miss` exists."""
    from refmatrix import verbs
    params = list(inspect.signature(verbs.resolve_session_source).parameters)
    assert params == ["root", "session", "envelope", "purpose"], (
        f"R9/D1: resolve_session_source takes exactly root, session, envelope, purpose; got "
        f"{params}")


@pytest.mark.parametrize("inv", list(INVOCATIONS), ids=list(INVOCATIONS))
def test_r9_event_purpose_miss_is_recorded_for_every_invocation(X, monkeypatch, inv):
    """Round 13 #b2: a telemetry row's / event's session (`telemetry.resolve_event_session`,
    R9's resolver with purpose=event) that misses -- `$CLAUDE_PID` set, no pointer for it, no
    `RMX_SESSION`, not long-lived -- records ONE resolver-miss row scoped to the store, whatever
    `invocation_source()` says (hook, mcp, agent, internal, unknown, interactive). The answer
    stays null. RED at HEAD for internal / unknown / interactive: `record_miss` is keyed on
    invocation in (hook, mcp, agent), so those three record nothing."""
    from refmatrix import telemetry, verbs
    monkeypatch.setattr(verbs, "_LONG_LIVED", False)
    for k, v in INVOCATIONS[inv].items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CLAUDE_PID", str(os.getppid()))
    if inv == "interactive":
        monkeypatch.setattr(sys, "stdin", _TtyStdin())
    assert telemetry.invocation_source() == inv, telemetry.invocation_source()
    assert not (pdir() / f"{os.getppid()}.json").exists()
    before = len(err_rows())
    got = telemetry.resolve_event_session(X)
    assert got is None, got
    rows = _miss_rows(before, X)
    assert len(rows) == 1, (
        f"R9 (round 13 #b2): an unresolved purpose=event call under invocation={inv} records "
        f"exactly one resolver-miss row; got {err_rows()[before:]}")
    assert rows[0].get("purpose") == "event", rows[0]


def test_r9_cli_call_with_claude_pid_and_no_pointer_records_a_miss(X):
    """Round 13 #b2, the end-to-end CLI shape the r1 audit named: a plain `rmx scan-prompt`
    child with `$CLAUDE_PID` set (this test's pid, a real ancestor), no invocation hint, no
    pointer and no `RMX_SESSION` (so `invocation=unknown`) records a resolver-miss row for its
    query.log row's session. RED at HEAD: the `record_miss` switch drops it."""
    assert not (pdir() / f"{ME}.json").exists()
    before = len(err_rows())
    r = rmx(["scan-prompt"], X, input="hello zorbulate widget")
    rows = [q for q in h.query_rows(X) if q.get("kind") == "scan"]
    assert rows and rows[-1].get("invocation") == "unknown", (rows[-1:], r.stderr[-800:])
    assert _miss_rows(before, X), (
        f"R9 (round 13 #b2): no resolver-miss row for a CLAUDE_PID-owned unknown-invocation "
        f"call; rows added: {err_rows()[before:]}; stderr={r.stderr[-800:]}")


# ---- round 13 / r1 #s2 (D8): a failed pointer-error write is never silent -----------------

def _make_errors_log_unwritable() -> None:
    """The log path is a DIRECTORY: `_append_error_rows`'s open fails (an OSError), so every
    `record_pointer_error` returns False -- the real failure, no patch."""
    pdir().mkdir(parents=True, exist_ok=True)
    errlog().mkdir()
    assert errlog().is_dir()


def _lines_naming(text: str, reason: str) -> list[str]:
    return [ln for ln in text.splitlines() if reason in ln]


def test_d8_unrecorded_pointer_unresolved_is_printed(X):
    """D8 ("printed once at every call site that has a stderr"), r1 #s2 site `verbs.py:589`:
    an agent `rmx scan-prompt` whose session misses (CLAUDE_PID set, no pointer) while the
    error log cannot be written prints a stderr line naming `pointer-unresolved`. RED at HEAD:
    the resolver drops the False return and prints nothing."""
    _make_errors_log_unwritable()
    r = h.run_rmx(["scan-prompt"], root=X, input="hello zorbulate widget", CLAUDECODE="1",
                  CLAUDE_PID=ME, RMX_HOME=os.environ["RMX_HOME"])
    assert _lines_naming(r.stderr, "pointer-unresolved"), (
        f"D8: a pointer-unresolved row that could not be written was dropped silently; "
        f"rc={r.returncode} stderr={r.stderr[-1200:]!r}")


def test_d8_unrecorded_envelope_unreadable_is_printed(X):
    """D8, r1 #s2 site `stm.py:1845` (`read_hook_envelope`): prose to `rmx memory recall
    --stdin-json` with an unwritable error log still exits nonzero with the invalid-JSON
    message AND prints a line naming `envelope-unreadable` (the row it could not keep). RED at
    HEAD: the False return is dropped."""
    _make_errors_log_unwritable()
    r = rmx(["memory", "recall", "--stdin-json"], X, input="fix the {braces")
    assert r.returncode != 0 and "--stdin-json: invalid JSON on stdin" in r.stderr, r.stderr
    assert _lines_naming(r.stderr, "envelope-unreadable"), (
        f"D8: an envelope-unreadable row that could not be written was dropped silently; "
        f"stderr={r.stderr[-1200:]!r}")


def test_d8_unrecorded_pointer_unreadable_is_printed(X):
    """D8, r1 #s2 site `stm.py:651` (`read_pid_pointer`): a pointer for this test's pid that is
    not a JSON object, read by an agent `rmx scan-prompt` (CLAUDE_PID = this pid, a real
    ancestor) while the error log cannot be written, prints a line naming
    `pointer-unreadable`. RED at HEAD: the False return is dropped."""
    _make_errors_log_unwritable()
    (pdir() / f"{ME}.json").write_text("not json at all")
    r = h.run_rmx(["scan-prompt"], root=X, input="hello zorbulate widget", CLAUDECODE="1",
                  CLAUDE_PID=ME, RMX_HOME=os.environ["RMX_HOME"])
    assert _lines_naming(r.stderr, "pointer-unreadable"), (
        f"D8: a pointer-unreadable row that could not be written was dropped silently; "
        f"stderr={r.stderr[-1200:]!r}")


def _unconsumed_record_calls(source: str, filename: str) -> list[str]:
    """Every `record_pointer_error(...)` call (bare name or attribute) whose result is
    discarded: the call IS an expression statement."""
    import ast
    out = []
    for node in ast.walk(ast.parse(source, filename)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name == "record_pointer_error":
                out.append(f"{filename}:{node.lineno}")
    return out


def _all_record_calls(source: str, filename: str) -> int:
    import ast
    n = 0
    for node in ast.walk(ast.parse(source, filename)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            n += name == "record_pointer_error"
    return n


def test_d8_every_record_pointer_error_result_is_consumed():
    """D8 / r1 #s2 guard: no `record_pointer_error(` call in `src/refmatrix/` discards its bool
    (a bare expression statement), so a failed write cannot be dropped silently at a NEW site
    either. The checker is first run on a planted module that it must report, so it cannot
    pass vacuously. RED at HEAD: 10 of 11 sites are bare statements."""
    planted = ("from refmatrix import stm\n"
               "def f(root):\n"
               "    stm.record_pointer_error('x', root=root, owner=None)\n"
               "    if not stm.record_pointer_error('y', root=root, owner=None):\n"
               "        print('rmx: not recorded')\n")
    assert _unconsumed_record_calls(planted, "planted.py") == ["planted.py:3"]
    total, bad = 0, []
    for p in sorted((h.SRC / "refmatrix").rglob("*.py")):
        text = p.read_text(encoding="utf-8")
        total += _all_record_calls(text, str(p))
        bad += _unconsumed_record_calls(text, str(p.relative_to(h.REPO)))
    assert total >= 5, f"guard: only {total} record_pointer_error calls found under src/"
    assert bad == [], (
        "D8: these record_pointer_error calls discard the False a failed write returns "
        f"(print it, or route through one wrapper that does): {bad}")


# ---- round 13 / r1 #s3: the error-log scope key is canonical ------------------------------

def _other_spelling(root: Path) -> Path:
    s = str(root)
    if s.startswith("/private/tmp/"):
        return Path("/tmp/" + s[len("/private/tmp/"):])
    if s.startswith("/tmp/"):
        return Path("/private/tmp/" + s[len("/tmp/"):])
    raise AssertionError(f"fixture: store root {s} is not under /tmp (macOS symlink)")


def test_s3_a_row_scoped_by_tmp_is_seen_by_a_private_tmp_reader(X):
    """r1 #s3 (D6/D8 scope): one store spelled `/tmp/...` by its writer and `/private/tmp/...`
    by its reader (macOS: /tmp -> /private/tmp) is ONE scope. A row written under either
    spelling is returned by `stm.read_pointer_errors(root=<the other>)` and named by
    `handoff.session_pointer_anomalies(<the other>)`. RED at HEAD: the writer keeps
    `abspath` and the readers compare `str(root)`, so the row is invisible."""
    from refmatrix import handoff, stm
    other = _other_spelling(X)
    assert os.path.realpath(other) == os.path.realpath(X), (other, X)
    assert stm.record_pointer_error("pointer-unresolved", root=other, owner=None,
                                    purpose="event")
    assert stm.record_pointer_error("sweep-failed", root=X, owner=None)
    seen_x = [r.get("reason") for r in stm.read_pointer_errors(root=X)]
    seen_other = [r.get("reason") for r in stm.read_pointer_errors(root=other)]
    assert "pointer-unresolved" in seen_x and "sweep-failed" in seen_x, (
        f"#s3: a reader spelling the root {X} misses the row written as {other}: {seen_x}")
    assert "pointer-unresolved" in seen_other and "sweep-failed" in seen_other, (
        f"#s3: a reader spelling the root {other} misses the row written as {X}: {seen_other}")
    an = handoff.session_pointer_anomalies(X)
    assert any("pointer-unresolved" in a for a in an), an


# ---- ch-bsd r2 #s1: guards for the r1 remedies (M5b prune count, handoff clause path) -------

def test_r2_session_start_line_counts_an_unreadable_pointer_file(X):
    """ch-bsd r2 #s1 (M5b; r1 #s2): a `by-pid/` pointer file that cannot be parsed is not
    judged dead and is COUNTED on the SessionStart writer's status line
    (`prune_unreadable=1`), never skipped silently. Kills the mutation that drops the count."""
    pdir().mkdir(parents=True, exist_ok=True)
    (pdir() / "99999.json").write_text("{not json")
    r = run_ss(X)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("rmx session-pointer:")]
    assert line and "prune_unreadable=1" in line[-1], (line, r.stderr[-800:])
    assert (pdir() / "99999.json").exists(), "an unreadable pointer was judged dead"


def test_r2_session_start_line_counts_an_undroppable_legacy_pointer(X):
    """ch-bsd r2 #s1 (r1 #s2, `drop_legacy_pointers_migration`): a legacy per-store pointer
    whose unlink fails is counted (`legacy_pointers_undropped=1`), never skipped silently."""
    ld = X / "stm" / "by-pid"
    ld.mkdir(parents=True, exist_ok=True)
    (ld / "424242.json").write_text(json.dumps({"session": "old", "pid": 424242}))
    ld.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        r = run_ss(X)
    finally:
        ld.chmod(stat.S_IRWXU)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("rmx session-pointer:")]
    assert line and "legacy_pointers_undropped=1" in line[-1], (line, r.stderr[-800:])


def test_r2_hook_failure_clause_names_the_errors_log_path():
    """ch-bsd r2 #s1 (r1 #m4, D8 / round-9 #m9-2): recall-state's STM-hook-failure clause
    takes the log path from `stm.errors_log_path()`, never a hand-typed name."""
    from refmatrix import handoff, stm
    X = Path(os.environ["REFMATRIX_ROOT"])
    assert stm.record_pointer_error("sweep-failed", root=X, owner=None)
    clause = [ln for ln in handoff.session_pointer_anomalies(X)
              if ln.startswith("STM hook failures")]
    assert clause == [f"STM hook failures in 24h: sweep-failed x1; see {stm.errors_log_path()}"], \
        clause


# ---- ch-bsd r2 #m3: an empty / null root is attributed to NO store ---------------------------

def test_r2_empty_or_null_root_is_unscoped_not_the_cwd(X, monkeypatch):
    """ch-bsd r2 #m3 (D6: a row with no root is counted apart, never attributed): a log row
    whose `root` is "" or null is returned to a scoped reader as `unscoped-row`, even when the
    reader's cwd IS the store root; `stm.scope_key("")` does not resolve to the cwd. RED at
    HEAD: `scope_key("")` = realpath(cwd), so a reader at cwd = X attributes both rows to X."""
    from refmatrix import stm
    monkeypatch.chdir(X)
    try:
        k = stm.scope_key("")
    except (ValueError, TypeError):
        k = None
    assert k != os.path.realpath(os.getcwd()), f"scope_key('') resolved to the cwd: {k}"
    pdir().mkdir(parents=True, exist_ok=True)
    t = time.time()
    with open(errlog(), "a") as f:
        for root in ("", None):
            f.write(json.dumps({"t": t, "reason": "pointer-unresolved", "root": root,
                                "owner": None, "owner_start": None}) + "\n")
    got = [r.get("reason") for r in stm.read_pointer_errors(root=X)]
    assert got == ["unscoped-row", "unscoped-row"], (
        f"#m3: an empty/null-root row was attributed to the store at the cwd: {got}")
