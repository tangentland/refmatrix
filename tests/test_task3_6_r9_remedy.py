"""Task 3.6 (ch-bsd plan-3 r9 remedy) and task 3.7's pin (the verb-it backlog).

r9 at 1acadd2 was DIRTY (1B/4S/1M). This file is the RED half of the remedy:

#2 (r9 #s-1)  "THE one classifier" covered three of the sites that word a
              store-daemon transport error. The rest still call a refused or
              missing socket "did not answer within Ns" or "busy". Each site gets
              a probe in the race that reaches it — the liveness check said UP,
              then the dial failed — on a REAL refused socket file (bound, then
              closed: a daemon that died without unlinking). A guard scans
              `src/refmatrix` with `ast` so the next site cannot word it itself.
#3 (r9 #s-2)  `spawn_daemon_subprocess` gives the launcher `W + 5` s and the
              readiness poll a FRESH `W`: worst case `2W + 5`, 25.2 s measured
              against promote's 10 s. The slow launcher is an environment fault
              (a `sitecustomize` that sleeps only in the `rmx daemon start`
              interpreter), not a src seam.
#4 (r9 #s-3)  Mutants ME / MD / ML / MF survived the plan-3 set. Each gets a test
              that kills it; ME uses a REAL held global daemon (SIGSTOPped), not
              `_PingOnlyDaemon` (which answers ping, so it is UP and never reaches
              the busy branch).
#5 (r9 #s-4)  `rmx memory add` on a store with no daemon and no replica crashes
              with `StaleDuckDBInstanceError … already attached by database
              "rmx_ro"` — plan-3's own bootstrap promise (bug-135).
#6 (r9 #m-1)  Four LEGACY decisions recorded with false reasons.
3.7 (r9 #b-1) Every `verb-it` path names its task-3.7 family.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, search, verbs
from refmatrix import hub as hub_mod
from refmatrix.store import Store
from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r4 import _snapshot
from tests.test_task3_5_r8_remedy import (  # noqa: F401 — fixtures
    _short_dir, cold_global, live_project)

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "refmatrix"
_TRANSPORT_WORDS = ("did not answer", "busy")


def _status_up(monkeypatch):
    """The race every #2 probe runs in: the liveness check said UP."""
    monkeypatch.setattr(discovery, "daemon_status",
                        lambda r, **kw: {"up": True, "busy": False, "pid": 4242})


def _refused_root(prefix: str) -> "tuple[Path, Path]":
    base = _short_dir(prefix)
    root = base / "p" / ".refmatrix"
    root.mkdir(parents=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(dm.socket_path(root)))
    s.close()                      # a socket FILE with no listener
    return base, root


def _says_not_running(text: str) -> None:
    assert "not running" in text, text
    for w in _TRANSPORT_WORDS:
        assert w not in text, f"{w!r} in {text!r}"


@contextlib.contextmanager
def _held(root: Path):
    """A REAL held daemon: pid alive, socket present, nothing answers."""
    pid = dm.read_pid(root)
    assert pid, f"no daemon pid for {root}"
    os.kill(pid, signal.SIGSTOP)
    try:
        yield pid
    finally:
        os.kill(pid, signal.SIGCONT)


# ---- #2: every store-daemon transport site words through the classifier ----

def test_where_project_leg_names_a_refused_socket_not_running():
    """search.py `_where_one_project` memory leg — 20 lines above the global
    leg r8 fixed, still "memory_search did not answer within 3s"."""
    base, root = _refused_root("rmxw-")
    try:
        _rows, reasons = search._where_one_project(root, "held")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    mem = [r for r in reasons if "memory_search" in r]
    assert mem, reasons
    _says_not_running(mem[0])


def test_federated_query_names_a_refused_socket_not_running(monkeypatch):
    base, root = _refused_root("rmxq-")
    monkeypatch.setattr(search, "_live_roots", lambda: ([root], []))
    try:
        out = search.federated_query("mentions:x")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    reasons = [s.get("reason", "") for s in out["skipped"]]
    assert reasons, out
    _says_not_running(reasons[0])


def test_memory_partition_names_a_refused_socket_not_running(monkeypatch):
    """No replica, status UP, the `partition_list` dial refused: the classifier's
    absent, not "daemon busy … partition_list did not answer"."""
    base, root = _refused_root("rmxm-")
    _status_up(monkeypatch)
    try:
        with pytest.raises(verbs.VerbError) as ei:
            verbs.memory_partition(root, timeout=5.0)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    _says_not_running(str(ei.value))
    assert isinstance(ei.value, verbs.VerbAbsentError), type(ei.value)


@pytest.mark.parametrize("argv", [["derive", "log"], ["derive", "status"]],
                         ids=["derive-log", "derive-status"])
def test_derive_reads_name_a_refused_socket_not_running(argv, monkeypatch):
    """cli.py derive log / derive status: ping said UP (the gate these two use),
    the op's dial was refused. They still degrade to the replica — the NOTE on
    stderr is what must say "not running" rather than "did not answer"."""
    base = _short_dir("rmxd-")
    root = base / "p" / ".refmatrix"
    root.mkdir(parents=True)
    _snapshot(root)                  # a replica, so the degraded read can answer
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(dm.socket_path(root)))
    s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "ping", lambda *a, **k: True)
    try:
        r = CliRunner().invoke(cli_mod.main, argv)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    note = [ln for ln in r.stderr.splitlines() if ln.startswith("# rmx:")]
    assert note, (r.output, r.stderr)
    _says_not_running(note[0])


# The guard lives in tests/transport_guard.py (widened by #r10-amend after r10
# #s-2 planted eight evasions of the r9 version and it passed all of them).
from tests import transport_guard as _tg  # noqa: E402

_second_classifiers = _tg.second_classifiers


def test_no_site_words_a_daemon_transport_error_itself():
    """AC-5 / AC-R10-4. At 1081a05 the widened guard names `cli.py:1341`
    (focus summarize --promote, through `_memory_daemon_call`) and
    `cli.py:12270` (memory recall's dense leg, `_degrade_or_raise`): both word a
    raw OSError — a refused or missing socket — as "daemon busy"."""
    files = {str(p.relative_to(_SRC)): p.read_text() for p in sorted(_SRC.rglob("*.py"))}
    bad = _second_classifiers(files)
    assert not bad, ("these handlers word a store-daemon transport error themselves; route "
                     "them through verbs.classify_transport_error:\n" + "\n".join(bad))


_HDR = "from refmatrix import daemon as daemon_mod\nfrom refmatrix import verbs\n"
# One plant per evasion shape r10 #s-2 listed, plus the r9 baseline. Each MUST
# be flagged — a clean corpus cannot show the guard can fail.
_PLANTS_FLAGGED = {
    "baseline": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(f"daemon busy: x did not answer ({e})")
""",
    "fstring_helper": _HDR + """
def _busy_msg(root, e):
    return f"daemon for {root} did not answer ({e})"

def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(_busy_msg(root, e))
""",
    "module_constant": _HDR + """
BUSY_MSG = "daemon busy: %s"

def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except OSError as e:
        raise RuntimeError(BUSY_MSG % e)
""",
    "unlisted_alias": """
import refmatrix.daemon as rd2

def f(root):
    try:
        rd2.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(f"store is busy ({e})")
""",
    "from_imported_call": """
from refmatrix.daemon import call as dcall

def f(root):
    try:
        dcall(root, "x", {})
    except Exception as e:
        raise RuntimeError(f"daemon did not answer ({e})")
""",
    "dial_wrapper": _HDR + """
def _memory_daemon_call(op, args):
    return daemon_mod.call("/r", op, args)

def f():
    try:
        _memory_daemon_call("memory_add", {})
    except (TimeoutError, OSError) as e:
        raise RuntimeError(f"daemon busy: promote not confirmed ({e})")
""",
    "synonym_down": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(f"the daemon is down ({e})")
""",
    "synonym_wedged": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(f"the daemon looks wedged ({e})")
""",
    "mixed_delegate": _HDR + """
def _reason(root, e):
    if isinstance(e, TimeoutError):
        return "daemon wedged"
    return str(verbs.classify_transport_error(e, op="x", root=root, timeout=1.0))

def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise RuntimeError(_reason(root, e))
""",
    "mixed_handler": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        if isinstance(e, TimeoutError):
            raise RuntimeError("daemon busy")
        raise verbs.classify_transport_error(e, op="x", root=root, timeout=1.0)
""",
    "discarded_result_N8": _HDR + """
def f(root, pid):
    try:
        daemon_mod.call(root, "ingest_gmd_start", {})
    except OSError as e:
        c = verbs.classify_transport_error(e, op="ingest_gmd_start", root=root, timeout=1.0)
        raise RuntimeError(f"daemon busy (pid={pid}; the ingest job was not accepted)")
""",
    "discarded_bare_call": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except OSError as e:
        verbs.classify_transport_error(e, op="x", root=root, timeout=1.0)
        raise RuntimeError(f"x failed: busy ({e})")
""",
}
_PLANTS_CLEAN = {
    "raises_the_classifier": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        raise verbs.classify_transport_error(e, op="x", root=root, timeout=1.0) from e
""",
    "uses_the_result_in_its_words": _HDR + """
def f(root, pid):
    try:
        daemon_mod.call(root, "x", {})
    except OSError as e:
        c = verbs.classify_transport_error(e, op="x", root=root, timeout=1.0)
        raise RuntimeError(f"{c} (pid={pid}; the daemon may still complete it)") from e
""",
    "clean_delegate": _HDR + """
def _reason(root, e):
    c = verbs.classify_transport_error(e, op="x", root=root, timeout=1.0)
    return f"global store: {c}"

def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception as e:
        return _reason(root, e)
""",
    "silent": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except Exception:
        return None
""",
    "typed_only": _HDR + """
def f(root):
    try:
        daemon_mod.call(root, "x", {})
    except verbs.VerbBusyError as e:
        raise RuntimeError(f"recall not confirmed — daemon busy ({e})")
""",
}


@pytest.mark.parametrize("shape", sorted(_PLANTS_FLAGGED))
def test_the_guard_flags_every_evasion_shape(shape):
    """r10 #s-2: each shape passed the r9 guard. Each must be flagged now."""
    assert _second_classifiers({f"{shape}.py": _PLANTS_FLAGGED[shape]}), (
        f"the guard does not see the {shape!r} evasion")


@pytest.mark.parametrize("shape", sorted(_PLANTS_CLEAN))
def test_the_guard_passes_a_handler_that_delegates(shape):
    assert _second_classifiers({f"{shape}.py": _PLANTS_CLEAN[shape]}) == [], shape


def test_ingest_gmd_detach_names_a_refused_socket_not_running(tmp_path, monkeypatch):
    """The behavioural pin r10's N8 survived (cli.py ingest-gmd start op: the
    classifier's result computed and discarded, "daemon busy (pid=…" back)."""
    base, root = _refused_root("rmxi-")
    d = tmp_path / "mem"
    d.mkdir()
    (d / "a.md").write_text("# a\n\nbody\n")
    _status_up(monkeypatch)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("RMX_PARTITION", "p")
    monkeypatch.setenv("RMX_DETACH_WAIT_S", "2")
    try:
        r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", str(d), "--detach"])
    finally:
        shutil.rmtree(base, ignore_errors=True)
    out = r.output + (r.stderr or "")
    assert r.exit_code != 0, out
    assert "not running" in out, out
    assert "daemon busy" not in out, out


# ---- #3: one deadline for the launcher AND the readiness poll ---------------

def _slow_launcher_env(tmp: Path, monkeypatch, delay_s: float) -> None:
    """A `sitecustomize` FIRST on the children's PYTHONPATH that sleeps only in
    the `rmx daemon start` interpreter, then chains the sandbox's own
    `sitecustomize` so the child keeps the sandbox refusal (task 23.0 R4)."""
    site = tmp / "slowsite"
    site.mkdir()
    sandbox_site = _REPO / "tests" / "sandbox_site" / "sitecustomize.py"
    (site / "sitecustomize.py").write_text(
        "import os, sys, time, runpy\n"
        "_argv = list(getattr(sys, 'orig_argv', sys.argv))\n"
        "if 'daemon' in _argv and 'start' in _argv:\n"
        "    time.sleep(float(os.environ.get('RMX_TEST_LAUNCHER_DELAY_S', '0')))\n"
        f"runpy.run_path({str(sandbox_site)!r})\n")
    pp = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(site) + (os.pathsep + pp if pp else ""))
    monkeypatch.setenv("RMX_TEST_LAUNCHER_DELAY_S", str(delay_s))


@pytest.mark.timeout(90)
def test_spawn_holds_one_deadline_for_launcher_and_readiness(monkeypatch):
    """W = 3 s, launcher stalls 20 s: one deadline set at entry fails by ~W.
    At 1acadd2 the launcher alone may take W + 5 = 8 s and then the poll starts
    a fresh W: ~11 s."""
    base = _short_dir("rmxs-")
    root = base / "p" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    _slow_launcher_env(base, monkeypatch, 20.0)
    t0 = time.monotonic()
    try:
        with pytest.raises(RuntimeError):
            dm.spawn_daemon_subprocess(root, watch_root=[], wait_for_ready=3.0)
        elapsed = time.monotonic() - t0
    finally:
        if dm.ping(root):
            dm.stop_daemon(root)
        shutil.rmtree(base, ignore_errors=True)
    assert elapsed < 3.0 + 2.0, f"{elapsed:.1f}s for a 3s readiness window"


@pytest.mark.timeout(120)
def test_promote_with_a_slow_launcher_stays_inside_its_budget(cold_global, live_project,
                                                              monkeypatch):
    """r9 probe: launcher delay 20 s → promote took 25.24 s against its 10 s
    promise, and said "within 10s" at 25 s."""
    site_root = _short_dir("rmxss-")
    try:
        _slow_launcher_env(site_root, monkeypatch, 20.0)
        t0 = time.monotonic()
        r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
        elapsed = time.monotonic() - t0
    finally:
        shutil.rmtree(site_root, ignore_errors=True)
    assert r.exit_code != 0, r.output
    assert elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0, (
        f"{elapsed:.1f}s against a promised {verbs.MEMORY_READ_BUDGET_S:g}s: {r.output!r}")


# ---- #4: kill the four surviving mutants ------------------------------------

@pytest.mark.timeout(120)
def test_a_held_real_global_daemon_is_busy_and_never_spawned_over(cold_global, live_project,
                                                                  monkeypatch):
    """ME (drop the busy branch in `global_write`): a held global store was
    spawned over — the in-process bootstrap hit `Conflicting lock is held` on
    the live catalog, reported as "not running". The 2026-09-14 lock-crash
    shape. REAL global daemon, SIGSTOPped."""
    assert hub_mod.ensure_global_daemon(), "could not start the global daemon"
    spawns: list = []
    real_spawn = dm.spawn_daemon_subprocess

    def spy(*a, **kw):
        spawns.append(a)
        return real_spawn(*a, **kw)
    monkeypatch.setattr(dm, "spawn_daemon_subprocess", spy)
    with _held(cold_global):
        t0 = time.monotonic()
        r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
        elapsed = time.monotonic() - t0
    assert r.exit_code != 0, r.output
    assert "busy" in r.output, r.output
    assert "not running" not in r.output, r.output
    # The busy message itself may say "holding the store lock"; the spawn-over
    # symptom is DuckDB's lock conflict from the in-process bootstrap.
    assert "Conflicting lock" not in r.output and "IOException" not in r.output, r.output
    assert spawns == [], f"spawned over a held global store: {spawns}"
    assert elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0, f"{elapsed:.1f}s"


@pytest.mark.timeout(120)
def test_promote_cannot_start_a_real_overlong_global_root_within_budget(live_project,
                                                                       monkeypatch):
    """MD (spawn readiness back to the 30 s default): 30.45 s. No spawn patch —
    a global root whose socket path exceeds AF_UNIX's ~104 bytes cannot start."""
    base = _short_dir("rmxo-")
    groot = base / ("g" * 110)
    groot.mkdir()
    monkeypatch.setenv("RMX_HOME", str(groot))
    assert len(str(dm.socket_path(groot))) > 104
    try:
        t0 = time.monotonic()
        r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
        elapsed = time.monotonic() - t0
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert r.exit_code != 0, r.output
    assert "not running" in r.output, r.output
    assert "Errno" not in r.output.splitlines()[-1], r.output
    assert elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0, f"{elapsed:.1f}s"


def test_global_write_types_a_daemon_that_vanished_after_the_probe(cold_global, monkeypatch):
    """ML (`global_write` raises a raw VerbError, classifier bypassed): the
    probe said UP, the socket is gone by the write — absent, said so."""
    _status_up(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.global_write("memory_add", {"name": "n", "content": "c"}, timeout=5.0)
    assert isinstance(ei.value, verbs.VerbAbsentError), (type(ei.value), str(ei.value))
    assert "not running" in str(ei.value), str(ei.value)


@pytest.mark.timeout(60)
def test_global_write_types_a_stalled_write_busy(monkeypatch):
    """ML's other half: a write that does not answer is busy, typed."""
    g = _PingOnlyDaemon(seeded=True)
    try:
        monkeypatch.setenv("RMX_HOME", str(g.root))
        with pytest.raises(verbs.VerbError) as ei:
            verbs.global_write("memory_add", {"name": "n", "content": "c"}, timeout=2.0)
    finally:
        g.close()
    assert isinstance(ei.value, verbs.VerbBusyError), (type(ei.value), str(ei.value))


def test_memory_write_falls_back_only_on_absent(tmp_path, monkeypatch):
    """MF (`_memory_write` falls back to `local()` on ANY VerbError). Q11: only
    ABSENT may open the store in-process."""
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setenv("RMX_PARTITION", "p")
    calls: list = []

    def local():
        calls.append(1)
        return {"forgotten": True}

    def busy(*a, **kw):
        raise verbs.VerbBusyError("held (test)")
    monkeypatch.setattr(verbs, "memory", busy)
    import click
    with pytest.raises(click.ClickException):
        cli_mod._memory_write("forget", local, name="x")
    assert calls == [], "busy fell back to the in-process store"

    def absent(*a, **kw):
        raise verbs.VerbAbsentError("no daemon (test)")
    monkeypatch.setattr(verbs, "memory", absent)
    assert cli_mod._memory_write("forget", local, name="x") == {"forgotten": True}
    assert calls == [1]


@pytest.mark.timeout(120)
def test_a_write_on_a_real_held_project_daemon_never_opens_the_store(live_project,
                                                                     monkeypatch):
    """MF on real daemons: a SIGSTOPped project daemon, `rmx memory forget`.
    The in-process store must never be opened."""
    monkeypatch.setenv("RMX_PARTITION", discovery.store_name(live_project))
    opened: list = []

    def no_store(*a, **kw):
        opened.append(a)
        raise AssertionError("the in-process store was opened under a held daemon")
    monkeypatch.setattr(cli_mod, "_store", no_store)
    with _held(live_project):
        r = CliRunner().invoke(cli_mod.main, ["memory", "forget", "held_row", "--yes"])
    assert opened == [], r.output
    assert r.exit_code != 0, r.output
    assert "busy" in r.output, r.output


# ---- #5: `memory add` bootstraps a store with no daemon and no replica ------

@pytest.mark.timeout(60)
def test_memory_add_bootstraps_a_store_with_no_daemon_and_no_replica(monkeypatch):
    """plan-3 r2 #b-2's promise (cli.py memory_add): "a fresh store has NO daemon
    and the first memory must still land". r9: StaleDuckDBInstanceError …
    "already attached by database rmx_ro" (bug-135)."""
    base = _short_dir("rmxa-")
    root = base / "p" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    try:
        assert not dm.ping(root)
        assert not (root / "catalog.read.duckdb").exists()
        r = CliRunner().invoke(cli_mod.main, ["memory", "add", "z1", "-c", "bootstrap body"])
        out = r.output + (r.stderr or "")
        assert "rmx_ro" not in out and "StaleDuckDB" not in out, out
        assert r.exit_code == 0, (out, repr(r.exception))
        s = Store(root)
        try:
            with s.with_partition(discovery.store_name(root)):
                m = s.get_memory("z1")
        finally:
            s.close()
        assert m is not None and m["content"] == "bootstrap body", m
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- #6: four LEGACY decisions recorded with true reasons --------------------

_REFILED = {
    ("focus", "record"): "harness",
    ("install-hooks",): "operator",
    ("memory", "sync-disk"): "maintenance",
    ("curator", "scan"): "maintenance",
}


def test_four_legacy_reasons_are_true_against_the_code():
    """r9 #m-1. The category IS the decision; a wrong reason is a wrong record.
    - no generated hook runs `focus record` or `install-hooks`;
    - `memory sync-disk` is not the SessionStart/save-state bridge;
    - `curator scan` is driven by the scheduler, not the gmd-curator agent."""
    for path, cat in _REFILED.items():
        got_cat, reason = verbs.LEGACY_UNPAIRED[path]
        assert got_cat == cat, f"{' '.join(path)}: {got_cat!r}, expected {cat!r}"
        assert "generated Claude Code hook" not in reason, (path, reason)
    assert "SessionStart" not in verbs.LEGACY_UNPAIRED[("memory", "sync-disk")][1]
    assert "scheduler" in verbs.LEGACY_UNPAIRED[("curator", "scan")][1]
    hook_src = (_SRC / "hooks.py").read_text() + (_SRC / "search_hooks.py").read_text()
    for cmd in ('"record"', "focus record"):
        assert cmd not in hook_src, f"a generated hook does reference {cmd}"
    sched = (_SRC / "scheduler.py").read_text()
    assert '["curator", "scan"]' in sched


# ---- task 3.7: every verb-it path names its backlog family ------------------

# Mirrors task-3.7-verb-it-backlog.md#families (r9 #b-1). `curator scan` is not
# here: 3.6 #6 re-files it as maintenance (49 paths).
VERB_IT_FAMILIES = {
    "fam-graph-read": {("neighbors",), ("co-occur",), ("top",), ("describe",), ("recall",),
                       ("search-dense",), ("concept", "timeline"), ("pairs", "show")},
    "fam-canon": {("canon", "find"), ("canon", "siblings"), ("canon", "link")},
    "fam-matrix-edit": {("add", "concept"), ("add", "entity"), ("add", "linkage-type"),
                        ("link",), ("unlink",), ("list", "entities"), ("list", "linkages"),
                        ("list", "queries"), ("run",), ("save-query",)},
    "fam-curation": {("protect",), ("unprotect",), ("noise",), ("unnoise",), ("forget",)},
    "fam-focus": {("focus", "tail"), ("focus", "topics"), ("focus", "show"),
                  ("focus", "subject"), ("focus", "subjects"), ("focus", "clear-subject"),
                  ("focus", "composite"), ("focus", "detour"), ("focus", "detours"),
                  ("focus", "return"), ("focus", "clear")},
    "fam-session": {("session", "list"), ("session", "recall"), ("session", "show"),
                    ("session", "stats")},
    "fam-refine": {("refine", "list"), ("refine", "show"), ("refine", "accept"),
                   ("refine", "reject"), ("curator", "drain")},
    "fam-taxonomy": {("taxonomy", "list"), ("taxonomy", "add"), ("taxonomy", "remove")},
}
_SPEC_37 = (_REPO / "workflow" / "plans" / "plan-3-verbs-parity-tasks"
            / "task-3.7-verb-it-backlog.md")


def test_the_backlog_families_partition_and_are_anchored_in_the_spec():
    spec = _SPEC_37.read_text()
    union: set = set()
    for fam, paths in VERB_IT_FAMILIES.items():
        assert "{#" + fam + "}" in spec, f"task-3.7 has no anchor {fam}"
        assert not (union & paths), f"{fam} overlaps another family"
        union |= paths
    assert len(union) == 49


def test_every_verb_it_path_names_its_task_3_7_family():
    """r9 #b-1: "owes a verb" with no task behind it is a parking lot. Every
    `verb-it` entry's reason carries `task-3.7#fam-…`, the family that path is
    in. A family re-decided under 3.7 leaves `verb-it`, so it drops out here."""
    where = {p: fam for fam, paths in VERB_IT_FAMILIES.items() for p in paths}
    bad = []
    for path, (cat, reason) in verbs.LEGACY_UNPAIRED.items():
        if cat != "verb-it":
            continue
        fam = where.get(path)
        if fam is None:
            bad.append(f"{' '.join(path)}: verb-it but in no task-3.7 family")
        elif f"task-3.7#{fam}" not in reason:
            bad.append(f"{' '.join(path)}: reason does not name task-3.7#{fam}")
    assert not bad, "\n" + "\n".join(bad)


def test_the_deferral_registry_points_the_backlog_at_task_3_7():
    text = (_REPO / "workflow" / "deferral_registry.md").read_text()
    assert "[[task-3.7-verb-it-backlog]]" in text


# ---- #r10-amend S1: ONE legacy-partition detector for CLI, MCP and verbs ----
#
# ch-bsd plan-3 r10 #s-1: bug-135's fix made `cached_replica` refuse the writer's
# primary catalog, which was the only thing `verbs.memory_partition` used to see a
# legacy `memory-<project>` partition on a never-snapshotted store. With no daemon
# it now falls to absent → the project partition, while the CLI's own detector
# (`cli._legacy_memory_partition_exists`) still finds the legacy one: MCP
# `rmx_memory_add` lands in `p`, CLI `memory add` in `memory-p`. Split brain.
# Decision: ONE detector, `verbs.legacy_memory_partition_exists(root, legacy)` —
# a read-only open, CLOSED afterwards, never cached — used by both.

def _legacy_store(prefix: str) -> "tuple[Path, Path]":
    """No daemon, no snapshot, a pre-merge `memory-p` partition holding a row."""
    base = _short_dir(prefix)
    root = base / "p" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    with s.with_partition("memory-p"):
        s.add_memory(name="legacy_row", content="pre-merge")
    s.close()
    assert not dm.ping(root)
    assert not (root / "catalog.read.duckdb").exists()
    return base, root


def _get_in(s: Store, part: str, name: str) -> bool:
    with s.with_partition(part):
        return s.get_memory(name) is not None


def test_memory_partition_sees_a_legacy_partition_on_a_never_snapshotted_store():
    base, root = _legacy_store("rmxl1-")
    try:
        assert verbs.memory_partition(root) == "memory-p"
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.timeout(60)
def test_mcp_and_cli_bootstrap_writes_land_in_the_same_partition(monkeypatch):
    """r10 probe_r10_mcp: MCP `rmx_memory_add` → `p`, CLI `memory add` →
    `memory-p`, on the same store state. Both must land in `memory-p`. And the
    detector must leave no attach behind: an in-process WRITE in this same
    process afterwards succeeds (bug-135 stays fixed)."""
    from refmatrix import mcp
    base, root = _legacy_store("rmxl2-")
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    try:
        out = mcp._t_memory_add({"root": str(root), "name": "mcp_row", "content": "via mcp"})
        assert "error" not in out, out
        r = CliRunner().invoke(cli_mod.main, ["memory", "add", "cli_row", "-c", "via cli"])
        assert r.exit_code == 0, (r.output, r.stderr)
        s = Store(root)
        try:
            where = {n: [p for p in ("p", "memory-p") if _get_in(s, p, n)]
                     for n in ("mcp_row", "cli_row")}
            assert where == {"mcp_row": ["memory-p"], "cli_row": ["memory-p"]}, where
            with s.with_partition("memory-p"):
                s.add_memory(name="after_row", content="no stale attach")
        finally:
            s.close()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_legacy_detector_is_shared_closed_and_never_cached(monkeypatch):
    """One helper; it reports the CURRENT state (a legacy partition created after
    the first call is seen by the second — no process cache), and between the
    calls a writer opens the same catalog in-process (no lingering attach)."""
    base = _short_dir("rmxl3-")
    root = base / "p" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    try:
        assert verbs.legacy_memory_partition_exists(root, "memory-p") is False
        s = Store(root)
        with s.with_partition("memory-p"):
            s.add_memory(name="late_legacy", content="x")
        s.close()
        assert verbs.legacy_memory_partition_exists(root, "memory-p") is True
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_cli_and_verbs_both_use_the_shared_detector(monkeypatch):
    """Converged: the CLI's memory-partition default and `verbs.memory_partition`
    both reach `verbs.legacy_memory_partition_exists` (pass-through spy)."""
    base, root = _legacy_store("rmxl4-")
    real = verbs.legacy_memory_partition_exists
    seen: list = []

    def spy(*a, **kw):
        seen.append(a)
        return real(*a, **kw)
    monkeypatch.setattr(verbs, "legacy_memory_partition_exists", spy)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    try:
        verbs.memory_partition(root)
        assert seen, "verbs.memory_partition does not use the shared detector"
        n = len(seen)
        r = CliRunner().invoke(cli_mod.main, ["memory", "add", "cli_row2", "-c", "b"])
        assert r.exit_code == 0, (r.output, r.stderr)
        assert len(seen) > n, "the CLI memory-partition default does not use the shared detector"
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- #r10-amend M1: bug-135's registry row is closed ------------------------

def test_bug_135_is_not_left_open_in_the_registry():
    rows = [ln for ln in (_REPO / "workflow" / "bug_registry.md").read_text().splitlines()
            if ln.startswith("| bug-135 |")]
    assert len(rows) == 1, rows
    status = rows[0].split(" | ")[6].strip()
    assert not status.startswith("open"), f"bug-135 status is {status!r}"
