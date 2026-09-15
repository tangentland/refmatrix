"""bsd-plan3-r6 remedy (round 7 of plan 3): the memory group's last two read
paths, and the two fan-out legs the round-6 universal claimed but did not cover.

#b-1  `rmx memory get <name> --degree 1` printed the body and then died with a
      bare `NameError: name 'daemon_mod' is not defined` at cli.py:9708 on the
      DEPLOYED build, in every daemon state: the r5 remedy dropped the
      function-local import above the surviving call, and no test invoked the
      flag. The tail routes through `verbs.attach_context` — the verb the
      recall twin already uses — so the capability has ONE implementation.
      (bug-026)
#b-2  `rmx memory promote` waited 180.2 s on a held writer and exited 1 with
      EMPTY output (an unhandled TimeoutError): the memory group's third read
      path, still behind the bare ping gate + `_memory_daemon_call` at
      60 s x 3. It calls the verb, whose promote read is single-attempt under
      the action's budget. (bug-027)
#s-3  `federated_concept` is the module's fourth fan-out: it produced a
      `skipped` list its only consumer (`canon find`) discarded, and kept the
      silent per-root `except: pass` the other three lost. A busy store made
      `rmx canon find X` answer "no live project hosts X".
#s-4  three of the four "said, never mute" branches in `federated_where` were
      guarded by nothing — mutations M3 (replica-bundle leg back to `pass`),
      M4 (global memory leg back to `pass`) and M5 (delete the straggler
      naming) each left the suite green. One test per leg.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, search, verbs
from tests.test_plan2_remedy import _PingOnlyDaemon, _SilentDaemon
from tests.test_plan3_remedy_r4 import _snapshot


@pytest.fixture
def held():
    d = _PingOnlyDaemon(seeded=True)
    try:
        yield d
    finally:
        d.close()


@pytest.fixture
def held_replica(held):
    _snapshot(held.root)
    return held


@pytest.fixture
def answering(tmp_path, monkeypatch):
    """A store whose daemon answers: `discovery.daemon_status` up plus a
    `daemon.call` that serves the three ops this path uses. The socket-level
    fixtures in this suite all simulate a daemon that does NOT answer; the
    crash in #b-1 lives on the branch a HEALTHY daemon takes."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    seen: list[str] = []
    row = {"id": 7, "name": "held_row", "mtype": "project", "tags": ["t"],
           "metadata": {}, "content": "body of held_row"}

    def call(root_, op, args=None, timeout=60.0, retries=2, **kw):
        seen.append(op)
        if op == "partition_list":
            return {"ok": True, "result": {"rows": [{"name": discovery.store_name(root_)}]}}
        if op == "memory_get":
            return {"ok": True, "result": {"memory": dict(row)}}
        if op == "context":
            return {"ok": True, "result": {"body": "CONTEXT BUNDLE for held_row"}}
        return {"ok": False, "error": f"unexpected op {op}"}

    monkeypatch.setattr(discovery, "daemon_status",
                        lambda r, **kw: {"up": True, "busy": False, "pid": 4242})
    monkeypatch.setattr(dm, "call", call)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    return type("Answering", (), {"root": root, "ops": seen, "row": row})()


# ---- #b-1 the --degree tail runs, and runs through the verb -----------------------------

def test_memory_get_degree_renders_the_context_bundle_on_a_healthy_daemon(answering):
    """The deployed build printed the body, then a NameError traceback. The
    flag's whole point is body + graph in one command."""
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row", "--degree", "1"])
    assert r.exit_code == 0, r.output
    assert "NameError" not in r.output, r.output
    assert r.exception is None, repr(r.exception)
    assert "body of held_row" in r.output, r.output
    assert "--- context ---" in r.output, r.output
    assert "CONTEXT BUNDLE for held_row" in r.output, r.output
    assert "context" in answering.ops, answering.ops


def test_memory_get_degree_routes_through_the_attach_context_verb(answering, monkeypatch):
    """Wiring, not behaviour: `rmx context`'s bundle is a verb, and the
    capability has one implementation (project-profile #constraints). A CLI
    that re-implements the daemon call is how the import went missing."""
    seen = []
    real = verbs.attach_context

    def spy(root, rows, degree, *a, **kw):
        seen.append((degree, [r.get("name") for r in rows]))
        return real(root, rows, degree, *a, **kw)
    monkeypatch.setattr(verbs, "attach_context", spy)
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row", "--degree", "1"])
    assert r.exit_code == 0, r.output
    assert seen == [(1, ["held_row"])], seen


@pytest.mark.timeout(60)
def test_memory_get_degree_on_a_held_writer_degrades_by_name(held_replica, monkeypatch):
    """The held-writer probe reached the same crash line (10.1 s, replica rows
    rendered, then NameError). Busy is a named degradation, never a traceback."""
    monkeypatch.setattr(cli_mod, "_root", lambda: held_replica.root)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row", "--degree", "1"])
    elapsed = time.monotonic() - t0
    assert "NameError" not in r.output, r.output
    assert not isinstance(r.exception, NameError), repr(r.exception)
    assert "held_row" in r.output, r.output
    assert "busy" in r.output.lower(), r.output
    assert elapsed < 36.0, f"{elapsed:.1f}s"


# ---- #b-2 promote is a bounded read like its three siblings ------------------------------

@pytest.mark.timeout(60)
def test_promote_on_a_held_writer_says_busy_within_the_budget(held_replica, monkeypatch):
    """180.2 s and an EMPTY message on the deployed build. The group's other
    three read paths answer inside the verb's budget with a typed word."""
    monkeypatch.setattr(cli_mod, "_root", lambda: held_replica.root)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    elapsed = time.monotonic() - t0
    assert r.exit_code != 0, r.output
    assert r.output.strip(), "exit 1 with no output is the defect"
    assert "busy" in r.output.lower(), r.output
    assert elapsed < 36.0, f"{elapsed:.1f}s — was 180.2 s (ping + memory_get 60 s x 3)"
    assert held_replica.ops.count("memory_get") <= 1, held_replica.ops


def test_promote_twin_routes_through_the_memory_verb(held_replica, monkeypatch):
    """The parity gate pairs `rmx_memory` with `get`; the promote wiring is
    asserted here. `grep -n "_verbs.memory(" cli.py` returned get/list/search
    and never promote (r6 #b-2)."""
    seen = []
    real = verbs.memory

    def spy(root, action, **kw):
        seen.append((action, kw.get("timeout")))
        return real(root, action, **kw)
    monkeypatch.setattr(verbs, "memory", spy)
    monkeypatch.setattr(cli_mod, "_root", lambda: held_replica.root)
    CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    assert [a for a, _ in seen] == ["promote"], seen
    assert all(t is not None and t <= verbs.MEMORY_READ_BUDGET_S for _, t in seen), seen


@pytest.mark.timeout(60)
def test_promote_verb_read_is_single_attempt_under_the_action_budget(held_replica):
    """Q11 says the promote read uses `retries=0`; the code took the library
    default, so the verb itself waited 90.2 s (ping, ping, memory_get x 3)."""
    t0 = time.monotonic()
    with pytest.raises(verbs.VerbBusyError):
        verbs.memory(held_replica.root, action="promote", name="held_row")
    elapsed = time.monotonic() - t0
    assert elapsed < 20.0, f"{elapsed:.1f}s — was 90.2 s"
    assert held_replica.ops.count("memory_get") <= 1, held_replica.ops


# ---- #s-3 the fourth fan-out, and the consumer that reads its skipped list ---------------

@pytest.mark.timeout(60)
def test_canon_find_names_the_skipped_store(monkeypatch):
    """`rmx canon find X` told the operator a concept exists nowhere when the
    truth was that the only store was busy — verbatim the r3 #b-2 defect,
    fixed for `locate` and left standing one command over.

    `_SilentDaemon`, not `_PingOnlyDaemon`: a daemon that answers ping is
    classified UP and goes into the fan-out's roots. `busy` is the state that
    never answers at all, which is what `_live_roots` skips."""
    d = _SilentDaemon(seeded=True)
    try:
        _snapshot(d.root)
        monkeypatch.setattr(discovery, "discover_roots", lambda: [d.root])
        r = CliRunner().invoke(cli_mod.main, ["canon", "find", "held_row"])
        assert "skipped" in r.output, r.output
        assert str(d.pid) in r.output or "busy" in r.output.lower(), r.output
    finally:
        d.close()


def test_federated_concept_names_a_failing_root(tmp_path, monkeypatch):
    """The per-root `except Exception: pass` the other three fan-outs lost."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(search, "_live_roots", lambda: ([root], []))

    def boom(*a, **kw):
        raise RuntimeError("replica bundle exploded")
    monkeypatch.setattr(search, "_replica_bundle", boom)
    out = search.federated_concept("held_row")
    assert out["projects"] == []
    reasons = " ".join(s.get("reason", "") for s in out["skipped"])
    assert "replica bundle exploded" in reasons, out["skipped"]


# ---- #s-4 one test per "said, never mute" leg of federated_where -------------------------

def test_federated_where_names_a_failing_replica_bundle_leg(tmp_path, monkeypatch):
    """Mutation M3: the leg back to `except Exception: pass` left the suite
    green. It is also the unbounded leg (`build_context` on a cold big
    store), so it is the one most likely to fail in the field."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(search, "_live_roots", lambda: ([root], []))

    def boom(*a, **kw):
        raise RuntimeError("bundle leg exploded")
    monkeypatch.setattr(search, "_replica_bundle", boom)
    out = search.federated_where("held")
    reasons = " ".join(s.get("reason", "") for s in out["skipped"])
    assert "bundle leg exploded" in reasons, out["skipped"]


def test_federated_where_names_a_failing_global_memory_leg(tmp_path, monkeypatch):
    """Mutation M4."""
    from refmatrix import hub as hub_mod
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(search, "_live_roots", lambda: ([], []))
    monkeypatch.setattr(hub_mod, "global_store_root", lambda: root)

    def boom(*a, **kw):
        raise TimeoutError("global leg did not answer")
    monkeypatch.setattr(hub_mod, "global_call", boom)
    out = search.federated_where("held")
    globals_ = [s for s in out["skipped"] if s.get("project") == "global"]
    assert globals_, out["skipped"]
    assert "did not answer" in globals_[0]["reason"], globals_


def test_federated_where_names_pool_stragglers(tmp_path, monkeypatch):
    """Mutation M5: deleting `_name_stragglers` from `federated_where` left
    the suite green — the straggler mutation was caught only at the `locate`
    call site."""
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setattr(discovery, "discover_roots", lambda: [root])
    monkeypatch.setattr(search, "_live_roots", lambda: ([root], []))
    monkeypatch.setattr(search, "WHERE_FANOUT_S", 0.5)

    def sleeper(*a, **kw):
        time.sleep(5.0)
        return [], []
    monkeypatch.setattr(search, "_where_one_project", sleeper)
    t0 = time.monotonic()
    out = search.federated_where("held")
    elapsed = time.monotonic() - t0
    roots = [s.get("root") for s in out["skipped"]]
    assert str(root) in roots, out["skipped"]
    assert elapsed < 4.0, f"{elapsed:.1f}s — the fan-out deadline must not wait for it"
