"""Task 21.1 AC-4b (ix)-(xii): the user-level pointer-error log's lifecycle.

(ix)   ended sessions: a root's DEAD-owner rows surface once on the next SessionStart in that
       root, consumed by OWNER (round-9 #s9-2), never a live other owner's; the 24 h prune of
       `consumed`; the lookup-unavailable guard (round-9 #m9-1, round-11 #m11-2).
(x)    ONE locked writer under two concurrent processes: no append lost to a halving, no count
       lost with a dropped truncation row (round-9 #m9-3), and `unseen_dropped` as a news
       counter (round-10 #m10-3).
(xi)   the one-shot migration of bug-109's legacy log, claimed once by rename (round-8 #nm-2,
       round-9 #m9-4).
(xii)  the AST bypass checks of D8 / D6 / D9, each also run on a planted fixture it must report.

Every SessionStart run is the GENERATED `rmx focus hook --event session-start` command (D4),
run as Claude Code runs it (`/bin/bash -c`, envelope on stdin, cwd = the project). Owners are
real processes: P1 = this test process (`CLAUDE_PID` = its pid, a real ancestor of the hook
child); P2/P3 = helper processes the test starts, each running its own resolver child with
`CLAUDE_PID` = its own pid, so every row's `owner` / `owner_start` is a live kernel identity.

Isolation: the pointer log is MACHINE-wide by design (D3), so every test here points `RMX_HOME`
(the global store root, `hub.global_store_root()`) at its own fresh directory: the line-count
identities of (x) and the "exactly one row" assertions must not see another test's rows. That
is an environment input (the sandbox already redirects it once per session), not a mock.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests import task21_1_support as h

SS_NEEDLE = "focus hook --event session-start"
SRC_PKG = h.SRC / "refmatrix"


# ---- fixtures -------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _live_guard(monkeypatch):
    """AC preamble: the live logs do not move; Claude env stripped from this process."""
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


@pytest.fixture
def X() -> Path:
    return Path(os.environ["REFMATRIX_ROOT"])


@pytest.fixture
def ghome(X, monkeypatch) -> Path:
    """A fresh, EXISTING global store root for this test (see the module docstring)."""
    g = X.parent / "gh" / ".refmatrix"
    g.mkdir(parents=True)
    monkeypatch.setenv("RMX_HOME", str(g))
    return g


def _pdir(g: Path) -> Path:
    return g / "by-pid"


def _log(g: Path) -> Path:
    return _pdir(g) / "_errors.jsonl"


def _rows(g: Path) -> list[dict]:
    p = _log(g)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _root_file(g: Path, root: Path) -> Path:
    return _pdir(g) / f"_errors.seen.root.{hashlib.sha1(str(root).encode()).hexdigest()[:12]}"


def _ss_cmd(root: Path) -> str:
    """D4: the generated SessionStart writer. Absent at HEAD -- this assertion is the first
    observable-state failure of every SessionStart-driven leg below."""
    m, cmd = h.generated_entry(root, "SessionStart", SS_NEEDLE)
    assert m == "startup|resume|clear|compact", m
    assert "2>/dev/null" not in cmd, cmd
    return cmd


def _ss(root: Path, cmd: str, *, session: str = "sess-P1", source: str = "startup",
        owner: int | None = None, **extra) -> subprocess.CompletedProcess:
    env = {"session_id": session, "source": source, "hook_event_name": "SessionStart"}
    return h.run_hook(cmd, root=root, envelope=env,
                      CLAUDE_PID=str(owner if owner is not None else os.getpid()), **extra)


def _lines(text: str, needle: str) -> list[str]:
    return [l for l in text.splitlines() if needle in l]


def _start(pid: int) -> str:
    from refmatrix import stm
    s = stm._proc_start(pid)
    assert s is not None, pid
    return s


# ---- helper owners P2 / P3 ------------------------------------------------------------------

_HELPER = r'''
import os, subprocess, sys
CHILD = ("import sys; from pathlib import Path; from refmatrix import verbs; "
         "print(verbs.resolve_session_source(Path(sys.argv[1]), None, purpose='event'))")
print("READY", os.getpid(), flush=True)
for line in sys.stdin:
    cmd = line.strip()
    if cmd == "exit":
        break
    if cmd.startswith("row "):
        env = dict(os.environ)
        env["CLAUDE_PID"] = str(os.getpid())          # this helper owns its child's rows
        env.pop("RMX_SESSION", None)
        r = subprocess.run([sys.executable, "-c", CHILD, cmd[4:]], env=env,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + " " + r.stderr).replace("\n", " ")[-400:]
        print("DONE", r.returncode, out, flush=True)
'''


class Owner:
    """A helper Claude-owner process (P2 / P3): writes one resolver-miss row scoped to a root
    through its OWN child (`CLAUDE_PID` = the helper's pid), and stays alive until told."""

    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, "-c", _HELPER, "rmx-owner-helper"],
                                     env=h.clean_env(), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
        ready = self.proc.stdout.readline().split()
        assert ready[:1] == ["READY"], ready
        self.pid = int(ready[1])
        self.start = _start(self.pid)

    def row(self, root: Path) -> str:
        self.proc.stdin.write(f"row {root}\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip()

    def exit(self) -> None:
        if self.proc.poll() is None:
            self.proc.stdin.write("exit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=30)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=30)


def _owned(g: Path, pid: int) -> list[dict]:
    return [r for r in _rows(g) if r.get("owner") == pid]


# ---- (ix) ended sessions --------------------------------------------------------------------

def test_ac4b_ix_ended_sessions_consumed_by_owner_never_a_live_one(X, ghome):
    """AC-4b (ix) steps 1-5 (round-8 #ns-2, reordered round-9 #s9-2). P3 (alive) writes FIRST,
    P2 writes later and exits; P1's run prints P2's row once as `ended_sessions`, not P3's;
    `consumed` == [[P2, P2_start, P2_t]]; a second run prints none; after P3 exits its OLDER
    row prints once; recall-state still reports every row."""
    cmd = _ss_cmd(X)
    p3, p2 = Owner(), Owner()
    try:
        d3 = p3.row(X)
        assert len(_owned(ghome, p3.pid)) == 1, (d3, _rows(ghome))
        time.sleep(0.05)
        d2 = p2.row(X)
        assert len(_owned(ghome, p2.pid)) == 1, (d2, _rows(ghome))
        p2_row = _owned(ghome, p2.pid)[0]
        p3_row = _owned(ghome, p3.pid)[0]
        assert p2_row["t"] > p3_row["t"]
        assert p2_row["root"] == str(X) and p2_row["owner_start"] == p2.start, p2_row
        p2.exit()

        r1 = _ss(X, cmd)
        ended = _lines(r1.stdout, "ended_sessions:")
        assert len(ended) == 1 and "pointer-unresolved=1" in ended[0], r1.stdout + r1.stderr
        rf = json.loads(_root_file(ghome, X).read_text())
        assert rf["root"] == str(X)
        assert rf["consumed"] == [[p2.pid, p2.start, p2_row["t"]]], rf     # P3 is alive

        r2 = _ss(X, cmd)
        assert _lines(r2.stdout, "ended_sessions:") == [], r2.stdout

        p3.exit()
        r3 = _ss(X, cmd)
        ended = _lines(r3.stdout, "ended_sessions:")
        assert len(ended) == 1 and "pointer-unresolved=1" in ended[0], r3.stdout + r3.stderr
        r4 = _ss(X, cmd)
        assert _lines(r4.stdout, "ended_sessions:") == [], r4.stdout

        from refmatrix import handoff
        anomalies = " ".join(handoff.session_pointer_anomalies(X))
        assert "pointer-unresolved x2" in anomalies, anomalies     # consumption is SessionStart's only
    finally:
        p2.kill()
        p3.kill()


def test_ac4b_ix_consumed_entries_pruned_past_the_24h_window(X, ghome):
    """AC-4b (ix) pruning leg (round-9 #s9-2): a `consumed` entry whose `t_max` is 25 h old is
    gone after the next run, and that owner's rows (also 25 h old) are not printed again."""
    cmd = _ss_cmd(X)
    from refmatrix import stm
    assert hasattr(stm, "_append_error_rows"), "D8: the ONE locked writer is not built"
    dead = h.reaped_pid()
    old = time.time() - 25 * 3600
    _pdir(ghome).mkdir(parents=True, exist_ok=True)
    assert stm._append_error_rows([{"t": old, "reason": "pointer-unresolved", "root": str(X),
                                    "owner": dead, "owner_start": "1.000000"}]) is True
    _root_file(ghome, X).write_text(json.dumps(
        {"root": str(X), "consumed": [[dead, "1.000000", old]]}))
    r = _ss(X, cmd)
    assert _lines(r.stdout, "ended_sessions:") == [], r.stdout
    rf = json.loads(_root_file(ghome, X).read_text())
    assert all(e[0] != dead for e in rf["consumed"]), rf


def test_ac4b_ix_lookup_unavailable_skips_every_liveness_decision(X, ghome, monkeypatch):
    """AC-4b (ix) lookup-unavailable leg (round-9 #m9-1; round-11 #m11-2). With
    `stm._proc_info` -> None for every pid (in process), the SessionStart run prints
    `ended_sessions skipped`, `own rows skipped` and, with a legacy log present, `migration
    skipped`, each `... process lookup unavailable`; the legacy file, the owner's watermark
    and the per-root file are unchanged, and a LIVE owner's row is not consumed."""
    _ss_cmd(X)
    from refmatrix import stm
    from refmatrix.cli import main
    live = h.spawn_rmx_named_helper()
    try:
        assert stm.record_pointer_error("pointer-unresolved", root=X, owner=live.pid) is True
        legacy = X / "stm" / "by-pid" / "_errors.jsonl"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({"t": time.time() - 60, "reason": "no-owner"}) + "\n")
        own_wm = _pdir(ghome) / f"_errors.seen.{os.getpid()}"
        own_wm.write_text(json.dumps({"pid_start": _start(os.getpid()), "t": 0.0}))
        rootf = _root_file(ghome, X)
        rootf.write_text(json.dumps({"root": str(X), "consumed": []}))
        before = {p: p.read_bytes() for p in (legacy, own_wm, rootf)}

        monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
        monkeypatch.setattr(stm, "_proc_info", lambda pid: None)       # registered mock
        env = {"session_id": "sess-P1", "source": "startup", "hook_event_name": "SessionStart"}
        r = CliRunner().invoke(main, ["focus", "hook", "--event", "session-start"],
                               input=json.dumps(env))
        out = r.output
        assert "ended_sessions skipped: process lookup unavailable" in out, out
        assert "own rows skipped: process lookup unavailable" in out, out
        assert "migration skipped: process lookup unavailable" in out, out
        assert "Traceback" not in out and not isinstance(r.exception, TypeError), out
        for p, b in before.items():
            assert p.read_bytes() == b, f"{p} changed with the lookup unavailable"
        assert not list(legacy.parent.glob("_errors.migrating.*")), "claimed without identity"
    finally:
        live.kill()
        live.wait(timeout=30)


# ---- (x) one writer, concurrent -------------------------------------------------------------

_WRITER = r'''
import sys
from pathlib import Path
from refmatrix import stm
root, owner, n, tag = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
bad = 0
for i in range(n):
    if not stm.record_pointer_error("pointer-unresolved", root=Path(root), owner=owner,
                                    seq=f"{tag}-{i}", pad="x" * 120):
        bad += 1
print("FAILED", bad, flush=True)
'''


def test_ac4b_x_two_writers_lose_no_append_and_no_count(X, ghome):
    """AC-4b (x) (round-8 #nm-2; round-9 #m9-3). Two processes x 2,000 rows through
    `record_pointer_error` (~1.2 MB against 256 KiB: several halvings, so earlier
    `errors-truncated` rows are themselves dropped). Non-truncation rows + sum(`dropped`) over
    the truncation rows still present == 4,000; per root over `dropped_by_root` == 2,000 each;
    every line parses."""
    from refmatrix import stm
    assert hasattr(stm, "_errors_locked") and hasattr(stm, "_append_error_rows"), (
        "D8: the ONE locked writer (_errors_locked + _append_error_rows) is not built")
    Y = X.parent / "y" / ".refmatrix"
    procs = [subprocess.Popen([sys.executable, "-c", _WRITER, str(r), str(os.getpid()), "2000",
                               tag], env=h.clean_env(), stdout=subprocess.PIPE, text=True)
             for r, tag in ((X, "a"), (Y, "b"))]
    outs = [p.communicate(timeout=180)[0] for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    assert all(o.strip() == "FAILED 0" for o in outs), outs
    lines = [l for l in _log(ghome).read_text().splitlines() if l.strip()]
    rows = [json.loads(l) for l in lines]                         # every line parses
    assert all(isinstance(r, dict) for r in rows)
    trunc = [r for r in rows if r.get("reason") == "errors-truncated"]
    plain = [r for r in rows if r.get("reason") != "errors-truncated"]
    assert trunc, "no errors-truncated row: the file never halved (fixture vacuous)"
    dropped = sum(int(t["dropped"]) for t in trunc)
    avg = sum(len(l) + 1 for l in lines) / len(lines)
    per_half = (stm._ERRORS_MAX_BYTES / 2) / avg
    assert dropped >= 3 * per_half * 0.8, ("fewer than three halvings", dropped, per_half)
    assert len(plain) + dropped == 4000, (len(plain), dropped)
    for r in (X, Y):
        kept = sum(1 for p in plain if p.get("root") == str(r))
        lost = sum(int(t.get("dropped_by_root", {}).get(str(r), 0)) for t in trunc)
        assert kept + lost == 2000, (str(r), kept, lost)


def test_ac4b_x_news_leg_unseen_dropped_is_never_reported_twice(X, ghome):
    """AC-4b (x) news leg (round-10 #m10-3). After the first halving the owner's SessionStart
    surfaces truncation row T1 (its watermark passes t1); when a later halving drops T1, the new
    truncation row's `unseen_dropped["<pid>:<start>"]` equals the owned rows removed with `t`
    above the watermark (recounted here) and does NOT include T1's count, while `dropped`
    rolls T1's `dropped` up."""
    cmd = _ss_cmd(X)
    from refmatrix import stm
    assert hasattr(stm, "_append_error_rows"), "D8: the ONE locked writer is not built"
    pid = os.getpid()
    key = f"{pid}:{_start(pid)}"
    n = 0

    def write():
        nonlocal n
        n += 1
        assert stm.record_pointer_error("pointer-unresolved", root=X, owner=pid,
                                        seq=n, pad="y" * 2000) is True

    def file_lines():
        return [l for l in _log(ghome).read_text().splitlines() if l.strip()]

    t1 = None
    for _ in range(3000):
        write()
        tr = [json.loads(l) for l in file_lines() if '"errors-truncated"' in l]
        if tr:
            t1 = tr[0]
            break
    assert t1 is not None, "the file never halved"
    assert t1["unseen_dropped"].get(key, 0) > 0, t1
    r = _ss(X, cmd)
    assert "errors-truncated" in r.stdout, r.stdout + r.stderr
    w = json.loads((_pdir(ghome) / f"_errors.seen.{pid}").read_text())["t"]
    assert w >= t1["t"]
    t1_line = json.dumps(t1, sort_keys=True)
    for _ in range(3000):
        halves = _log(ghome).stat().st_size > stm._ERRORS_MAX_BYTES
        old = file_lines()
        write()
        if not halves:
            continue
        new = file_lines()
        new_set = set(new)
        removed = [json.loads(l) for l in old if l not in new_set]
        added = [json.loads(l) for l in new if l not in set(old)]
        tn = [a for a in added if a.get("reason") == "errors-truncated"]
        assert len(tn) == 1, added
        tn = tn[0]
        if any(json.dumps(x, sort_keys=True) == t1_line for x in removed):
            plain = [x for x in removed if x.get("reason") != "errors-truncated"]
            rtr = [x for x in removed if x.get("reason") == "errors-truncated"]
            exp_unseen = (sum(1 for x in plain if x.get("owner") == pid and x["t"] > w)
                          + sum(int(x.get("unseen_dropped", {}).get(key, 0))
                                for x in rtr if x["t"] > w))
            assert tn["unseen_dropped"].get(key, 0) == exp_unseen, (tn, exp_unseen, t1)
            assert tn["dropped"] == len(plain) + sum(int(x["dropped"]) for x in rtr), tn
            return
    pytest.fail("T1 was never dropped by a later halving")


# ---- (xi) migration claimed once ------------------------------------------------------------

def _legacy(X: Path, lines: list[str], *, age_s: float) -> Path:
    p = X / "stm" / "by-pid" / "_errors.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(l + "\n" for l in lines))
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


def _migrated(g: Path, X: Path) -> list[dict]:
    return [r for r in _rows(g) if r.get("migrated_from")
            and str(r["migrated_from"]).endswith("stm/by-pid/_errors.jsonl")
            and r.get("root") == str(X)]


def test_ac4b_xi_two_concurrent_runs_migrate_once(X, ghome, tmp_path):
    """AC-4b (xi) (round-8 #nm-2; round-9 #m9-4): the legacy log is one DAY old (an mtime
    adoption rule would take the live claim); two SessionStart runs released together by a
    barrier file migrate exactly two rows between them, exactly one prints `migrated=2`.
    Tolerance stated: the other prints `migrate-claim-lost=1` when it saw the legacy file
    before the winner's claim rename; one that starts after the rename sees no legacy file
    and prints neither (the barrier makes overlap likely, not certain)."""
    cmd = _ss_cmd(X)
    now = time.time()
    _legacy(X, [json.dumps({"t": now - 3600, "reason": "pointer-unresolved", "owner": 1}),
                json.dumps({"t": now - 7200, "reason": "no-owner"})], age_s=86400)
    barrier = tmp_path / "go"
    wrapped = f'while [ ! -e "{barrier}" ]; do sleep 0.005; done; {cmd}'
    procs = []
    for i in range(2):
        env = h.rmx_env(X, CLAUDE_PID=str(os.getpid()))
        p = subprocess.Popen(["/bin/bash", "-c", wrapped], env=env, cwd=str(X.parent),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({"session_id": f"sess-{i}", "source": "startup",
                                  "hook_event_name": "SessionStart"}))
        p.stdin.close()
        procs.append(p)
    barrier.touch()
    outs = []
    for p in procs:
        p.wait(timeout=120)
        outs.append(p.stdout.read() + p.stderr.read())
    assert len(_migrated(ghome, X)) == 2, (_rows(ghome), outs)
    assert {r["t"] for r in _migrated(ghome, X)} == {now - 3600, now - 7200}
    winners = [o for o in outs if "migrated=2" in o]
    assert len(winners) == 1, outs
    loser = outs[1 - outs.index(winners[0])]
    assert "migrated=" not in loser or "migrated=0" in loser, loser
    assert (X / "stm" / "by-pid" / "_errors.migrated.jsonl").exists()


def test_ac4b_xi_absent_global_root_leaves_the_claim_then_a_dead_claim_is_adopted(X, ghome):
    """AC-4b (xi): with the global store root absent a run appends nothing, leaves
    `_errors.migrating.<pid>.<token>.jsonl` (no `.migrated`) and prints `migration
    incomplete`; once the root exists the next run adopts that claim (its pid is dead) and
    migrates both rows."""
    cmd = _ss_cmd(X)
    now = time.time()
    _legacy(X, [json.dumps({"t": now - 3600, "reason": "pointer-unresolved", "owner": 1}),
                json.dumps({"t": now - 7200, "reason": "no-owner"})], age_s=86400)
    g2 = X.parent / "gh2" / ".refmatrix"
    r1 = _ss(X, cmd, RMX_HOME=str(g2))
    bp = X / "stm" / "by-pid"
    claims = list(bp.glob("_errors.migrating.*.jsonl"))
    assert len(claims) == 1, (list(bp.iterdir()), r1.stdout, r1.stderr)
    assert not (bp / "_errors.migrated.jsonl").exists()
    assert "migration incomplete" in r1.stderr, r1.stderr
    assert not _log(g2).exists()
    g2.mkdir(parents=True)
    r2 = _ss(X, cmd, RMX_HOME=str(g2))
    assert len(_migrated(g2, X)) == 2, (_rows(g2), r2.stdout, r2.stderr)
    assert "migrated=2" in r2.stdout, r2.stdout
    assert not list(bp.glob("_errors.migrating.*.jsonl"))
    assert (bp / "_errors.migrated.jsonl").exists()


def test_ac4b_xi_a_live_claimants_claim_is_not_adopted(X, ghome):
    """AC-4b (xi): a claim file named with the pid and start token of a LIVE helper process
    is left alone: not renamed, not migrated."""
    cmd = _ss_cmd(X)
    live = h.spawn_rmx_named_helper()
    try:
        token = hashlib.sha1(_start(live.pid).encode()).hexdigest()[:8]
        bp = X / "stm" / "by-pid"
        bp.mkdir(parents=True, exist_ok=True)
        claim = bp / f"_errors.migrating.{live.pid}.{token}.jsonl"
        body = json.dumps({"t": time.time() - 60, "reason": "no-owner"}) + "\n"
        claim.write_text(body)
        r = _ss(X, cmd)
        assert claim.exists() and claim.read_text() == body, (list(bp.iterdir()), r.stdout)
        assert _migrated(ghome, X) == [], _rows(ghome)
        assert "migrated=1" not in r.stdout, r.stdout
    finally:
        live.kill()
        live.wait(timeout=30)


def test_ac4b_xi_legacy_unreadable_row_migrates_once(X, ghome):
    """AC-4b (xi) (round-9 #m9-4): the `legacy-unreadable` row's `t` is the legacy file's
    mtime, so a repeated run (the legacy name restored with the same mtime, as after an
    interruption) does not append it again."""
    cmd = _ss_cmd(X)
    p = _legacy(X, [json.dumps({"t": time.time() - 3600, "reason": "no-owner"}), "not json"],
                age_s=7200)
    m = p.stat().st_mtime
    r1 = _ss(X, cmd)
    unr = [r for r in _rows(ghome) if r.get("reason") == "legacy-unreadable"
           and r.get("root") == str(X)]
    assert len(unr) == 1 and unr[0].get("n") == 1, (_rows(ghome), r1.stdout, r1.stderr)
    assert abs(float(unr[0]["t"]) - m) < 1.0, (unr, m)
    done = p.parent / "_errors.migrated.jsonl"
    assert done.exists()
    p.write_text(done.read_text())
    os.utime(p, (m, m))
    r2 = _ss(X, cmd)
    unr = [r for r in _rows(ghome) if r.get("reason") == "legacy-unreadable"
           and r.get("root") == str(X)]
    assert len(unr) == 1, (_rows(ghome), r2.stdout, r2.stderr)
    assert sum(1 for r in _migrated(ghome, X) if r.get("reason") == "no-owner") == 1


# ---- (xii) AST bypass checks ----------------------------------------------------------------

def _func_stack_walk(tree):
    """Yield (node, innermost enclosing function name or None)."""
    def rec(node, fn):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield child, fn
                yield from rec(child, child.name)
            else:
                yield child, fn
                yield from rec(child, fn)
    yield from rec(tree, None)


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


_ERR_PATH_CALLS = {"errors_log_path", "pointer_dir"}


def _tainted_expr(e, tainted: set) -> bool:
    for n in ast.walk(e):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "_errors" in n.value:
            return True
        if isinstance(n, ast.Call) and _call_name(n) in _ERR_PATH_CALLS:
            return True
        if isinstance(n, ast.Name) and n.id in tainted:
            return True
    return False


def _function_taint(fn_node) -> set:
    tainted: set = set()
    assigns = [n for n in ast.walk(fn_node)
               if isinstance(n, (ast.Assign, ast.AnnAssign, ast.withitem))]
    for _ in range(4):                       # fixed point over chained assignments
        for a in assigns:
            if isinstance(a, ast.withitem):
                val, tgts = a.context_expr, [a.optional_vars] if a.optional_vars else []
            else:
                val = a.value
                tgts = a.targets if isinstance(a, ast.Assign) else [a.target]
            if val is None or not _tainted_expr(val, tainted):
                continue
            for t in tgts:
                if isinstance(t, ast.Name):
                    tainted.add(t.id)
    return tainted


def _mode_writes(call: ast.Call, pos: int) -> bool:
    mode = None
    if len(call.args) > pos:
        mode = call.args[pos]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode = kw.value
    return (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
            and any(c in mode.value for c in "wax"))


def errors_write_sites(path: Path) -> list[tuple[str, str | None, int]]:
    """D8's list: every WRITE operation whose path expression holds an `_errors` constant or
    derives from `errors_log_path()` / `pointer_dir()` -- `open(...)`/`.open(...)` with a
    w/a/x mode, `.write_text`, `.write_bytes`, `.unlink`, `os.replace`, `os.rename`, and the
    Path `.replace`/`.rename` method on such a path. Docstrings and messages are not writes."""
    tree = ast.parse(path.read_text())
    taint_by_fn: dict = {None: _function_taint(tree)}
    out = []
    for node, fn in _func_stack_walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            taint_by_fn[node.name] = _function_taint(node)
            continue
        if not isinstance(node, ast.Call):
            continue
        tainted = taint_by_fn.get(fn, set())
        f = node.func
        target = None
        if isinstance(f, ast.Name) and f.id == "open" and node.args and _mode_writes(node, 1):
            target = [node.args[0]]
        elif isinstance(f, ast.Attribute):
            recv_is_os = isinstance(f.value, ast.Name) and f.value.id == "os"
            if recv_is_os and f.attr in ("replace", "rename"):
                target = list(node.args[:2])
            elif f.attr == "open" and _mode_writes(node, 0):
                target = [f.value]
            elif f.attr in ("write_text", "write_bytes", "unlink", "replace", "rename"):
                target = [f.value] + (list(node.args[:1]) if f.attr in ("replace", "rename")
                                      else [])
        if target and any(_tainted_expr(t, tainted) for t in target):
            out.append((path.name, fn, node.lineno))
    return out


_ALLOWED_EXACT = {"_errors_locked", "_append_error_rows"}
_ALLOWED_PATTERN = re.compile(r"(watermark|consumed|migrat|prune)")


def _write_allowed(module: str, fn: str | None) -> bool:
    """D8's allow-list. The spec names `_errors_locked` and `_append_error_rows` and describes
    the rest by role (the watermark and `consumed` advance, the migration, D7's prune) without
    names; those are matched by role words in the function name, in `stm.py` only."""
    return module == "stm.py" and fn is not None and (
        fn in _ALLOWED_EXACT or bool(_ALLOWED_PATTERN.search(fn)))


def errors_path_joins(path: Path) -> list[tuple[str, str | None, int]]:
    """A path join of the literal `_errors.jsonl` (`/`, `os.path.join`, `.joinpath`)."""
    tree = ast.parse(path.read_text())
    out = []

    def lit(e):
        return isinstance(e, ast.Constant) and isinstance(e.value, str) and \
            "_errors.jsonl" in e.value
    for node, fn in _func_stack_walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and lit(node.right):
            out.append((path.name, fn, node.lineno))
        elif isinstance(node, ast.Call) and _call_name(node) in ("join", "joinpath") and \
                any(lit(a) for a in node.args):
            out.append((path.name, fn, node.lineno))
    return out


def _src_modules():
    return sorted(SRC_PKG.rglob("*.py"))


def test_ac4b_xii_a_every_errors_write_sits_in_the_allow_listed_stm_functions():
    """AC-4b (xii)(a) (round-8 #nm-2; round-9 #m9-2). RED at HEAD: the halving's `write_text`
    and the append's `open("a")` sit in `record_pointer_error`, outside any `_errors_locked`.
    Second check (in the same assertion): no module outside `stm.py` joins `_errors.jsonl` onto
    a path (handoff takes it from `errors_log_path()`)."""
    bad = []
    for p in _src_modules():
        for mod, fn, line in errors_write_sites(p):
            if not _write_allowed(mod, fn):
                bad.append(f"{p.relative_to(h.SRC)}:{line} in {fn}")
    joins = [f"{p.relative_to(h.SRC)}:{line} in {fn}" for p in _src_modules()
             if p.name != "stm.py" for _m, fn, line in errors_path_joins(p)]
    assert (bad, joins) == ([], []), {"writes outside the allow-list": bad,
                                      "_errors.jsonl joined outside stm.py": joins}


def test_ac4b_xii_a_control_the_write_scan_reports_a_planted_bypass(tmp_path):
    """AC-4b (xii)(a) non-vacuity control: a planted `open(pointer_dir() / "_errors.jsonl",
    "a")` is reported (and a join of the literal is reported by the second check). Passes at
    HEAD by design: the scanner is test code; this proves the RED scan above can fail."""
    f = tmp_path / "planted.py"
    f.write_text(textwrap.dedent('''
        def sneaky():
            with open(pointer_dir() / "_errors.jsonl", "a") as fh:
                fh.write("x")

        def reader():
            return open(errors_log_path()).read()     # a read: not listed
    '''))
    sites = errors_write_sites(f)
    assert [(fn, ln) for _m, fn, ln in sites] == [("sneaky", 3)], sites
    assert not _write_allowed("planted.py", "sneaky")
    assert [fn for _m, fn, _l in errors_path_joins(f)] == ["sneaky"]


def callers_of(name: str, files) -> set:
    """Functions (bare names in stm.py, `module.func` elsewhere) that call `name(`."""
    out = set()
    for p in files:
        tree = ast.parse(p.read_text())
        for node, fn in _func_stack_walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == name:
                label = fn if p.name == "stm.py" else f"{p.stem}.{fn}"
                out.add(label)
    return out


def test_ac4b_xii_b_liveness_and_identity_have_one_accessor_each():
    """AC-4b (xii)(b) (round-9 #m9-1; round-10 #m10-2). Callers of `_proc_start(` ==
    {owner_alive, liveness_available, proc_identity}; callers of `_proc_info(` ==
    {_proc_start, owner_lookup}. RED at HEAD: `owner_alive` does not exist and
    `read_pid_pointer` / `write_pid_pointer` call `_proc_start` themselves."""
    files = _src_modules()
    got = (callers_of("_proc_start", files), callers_of("_proc_info", files))
    assert got == ({"owner_alive", "liveness_available", "proc_identity"},
                   {"_proc_start", "owner_lookup"}), got


def test_ac4b_xii_b_control_a_planted_private_liveness_check_is_reported(tmp_path):
    """AC-4b (xii)(b) non-vacuity control (passes at HEAD by design: scanner is test code)."""
    f = tmp_path / "stm.py"
    f.write_text("def prune_mine(pid, s):\n    return _proc_start(pid) == s\n")
    assert callers_of("_proc_start", [f]) == {"prune_mine"}


def _stdin_derived(e) -> bool:
    for n in ast.walk(e):
        if isinstance(n, ast.Attribute) and n.attr == "stdin":
            return True
        if isinstance(n, ast.Name) and "stdin" in n.id:
            return True
        if isinstance(n, ast.Call) and "stdin" in (_call_name(n) or ""):
            return True
    return False


def stdin_json_parses(path: Path) -> list[tuple[str, str | None, int]]:
    """Every `json.load(<stdin>)` / `json.loads(<stdin read>)`: the argument is a stdin
    expression, or a name assigned in the same function from one (`raw = sys.stdin.read()`,
    `raw = _read_stdin_text()`)."""
    tree = ast.parse(path.read_text())
    stdin_names: dict = {}
    for node, fn in _func_stack_walk(tree):
        if isinstance(node, ast.Assign) and _stdin_derived(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    stdin_names.setdefault(fn, set()).add(t.id)
    out = []
    for node, fn in _func_stack_walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "json"
                and node.func.attr in ("load", "loads") and node.args):
            continue
        a = node.args[0]
        if _stdin_derived(a) or (isinstance(a, ast.Name) and a.id in stdin_names.get(fn, ())):
            out.append((path.name, fn, node.lineno))
    return out


def prompt_reads(path: Path) -> set:
    """`.get("prompt")` / `["prompt"]` sites as (file, function)."""
    tree = ast.parse(path.read_text())
    out = set()
    for node, fn in _func_stack_walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr == "get" and node.args and \
                isinstance(node.args[0], ast.Constant) and node.args[0].value == "prompt":
            out.add((path.name, fn))
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and \
                node.slice.value == "prompt":
            out.add((path.name, fn))
    return out


# The reviewed list of `prompt` reads in cli.py / scan.py that are NOT on a stdin envelope.
# Read at HEAD d4bf001 there are exactly two prompt reads and BOTH are on a stdin envelope, so
# both must move into `stm.read_hook_envelope` / `HookEnvelope.prompt` (D9) and this list is
# empty:
#   cli.py focus_hook      `d.get("prompt")`   -- the UserPromptSubmit envelope (input branch)
#   cli.py _resolve_query  `env.get("prompt")` -- the `--stdin-json` / `{`-prefixed envelope
# (scan.read_stdin_prompt reads the four keys through a loop variable, so it is caught by the
# "user_prompt" constant check and the stdin-parse check instead.) A new private prompt read
# fails here until it is reviewed and added with its reason.
KEPT_PROMPT_READS: set = set()


def test_ac4b_xii_c_one_hook_envelope_reader():
    """AC-4b (xii)(c) (round-8 #nm-4; round-9 #s9-4). RED at HEAD: `cli.focus_hook`,
    `cli._resolve_query` and `scan.read_stdin_prompt` parse their own envelopes; scan.py holds
    the constant "user_prompt"; the two prompt reads above are private."""
    files = [SRC_PKG / "cli.py", SRC_PKG / "scan.py"]
    parses = [s for f in files for s in stdin_json_parses(f) if s[1] != "read_hook_envelope"]
    user_prompt = sorted(
        f"{p.relative_to(h.SRC)}:{n.lineno}" for p in _src_modules() if p.name != "stm.py"
        for n in ast.walk(ast.parse(p.read_text()))
        if isinstance(n, ast.Constant) and n.value == "user_prompt")
    reads = set().union(*(prompt_reads(f) for f in files))
    assert (parses, user_prompt, reads) == ([], [], KEPT_PROMPT_READS), {
        "private stdin envelope parses": parses, "user_prompt outside stm.py": user_prompt,
        "prompt reads != reviewed list": sorted(reads ^ KEPT_PROMPT_READS)}


def test_ac4b_xii_c_control_a_planted_stdin_parse_is_reported(tmp_path):
    """AC-4b (xii)(c) non-vacuity control (passes at HEAD by design: scanner is test code)."""
    f = tmp_path / "planted.py"
    f.write_text(textwrap.dedent('''
        import json, sys
        def hook():
            return json.loads(sys.stdin.read())
        def hook2():
            raw = sys.stdin.read()
            env = json.loads(raw)
            return env.get("prompt")
    '''))
    assert [(fn, ln) for _m, fn, ln in stdin_json_parses(f)] == [("hook", 4), ("hook2", 7)]
    assert prompt_reads(f) == {("planted.py", "hook2")}
