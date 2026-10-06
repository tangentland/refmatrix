"""Every site that can learn honours the toggle (task 14.2).

The resolver is tested in `tests/test_learn_switch.py`. What matters here is
that each of the five places that can teach the graph actually asks it. A
toggle that one site ignores is worse than no toggle: the arm of a measurement
that is supposed to have learning OFF would quietly keep learning, and the
difference between the arms would be attributed to something else.

The sites:
    cli._broker_learn_from_grep          the grep fallback
    cli._maybe_learn_grep_backstop       the `rmx context` grep backstop
    daemon._drain_learn_queue            the queue drain (per TICK, not at boot)
    daemon._op_learn_from_grep           the write op
    daemon._op_context's ref-path learn  the context op's own teach
"""
from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import types

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import learn_queue as lq
from refmatrix import learn_switch as ls
from refmatrix.store import Store


@pytest.fixture
def project(monkeypatch):
    """A real store in a real tree, cwd'd into it, with a clean HOME so the
    global marker cannot leak in from the developer's own machine."""
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    monkeypatch.delenv("REFMATRIX_ROOT", raising=False)
    monkeypatch.delenv("REFMATRIX_NO_TELEMETRY", raising=False)
    td = pathlib.Path(tempfile.mkdtemp(prefix="rmxT"))
    home = td / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    root = td / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root, backend="duckdb")
    s.init()
    s.close()
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(root.parent)
    yield root.parent
    shutil.rmtree(td, ignore_errors=True)


def _queue_depth(root) -> int:
    return lq.pending_lines(root)


def _last_grep_row(root) -> dict:
    rows = [json.loads(l) for l in (root / "query.log").read_text().splitlines() if l.strip()]
    greps = [r for r in rows if r.get("kind") == "grep"]
    assert greps, "no grep row"
    return greps[-1]


def _run(args, **kw):
    return CliRunner().invoke(cli_mod.main, args, **kw)


# ---- site 1: the grep fallback -------------------------------------------

def test_the_default_path_learns_with_the_toggle_on(project):
    """The control. Without this the OFF cases below pass against a build that
    never learns at all."""
    (project / "t.txt").write_text("alpha beta\n")
    root = project / ".refmatrix"

    res = _run(["grep", "alpha"])

    assert res.exit_code == 0, res.output
    assert _queue_depth(root) >= 1, "the toggle is ON and nothing was queued"
    assert _last_grep_row(root)["learn"] is True


@pytest.mark.parametrize("how", ["env", "store-marker", "global-marker"])
def test_the_grep_fallback_does_not_learn_when_off(project, monkeypatch, how):
    (project / "t.txt").write_text("alpha beta\n")
    root = project / ".refmatrix"
    if how == "env":
        monkeypatch.setenv("RMX_LEARN", "0")
    elif how == "store-marker":
        ls.set_enabled(root, False, scope="store")
    else:
        ls.set_enabled(root, False, scope="global")

    res = _run(["grep", "alpha"])

    assert res.exit_code == 0, res.output
    assert "alpha beta" in res.output, "the READ must be unaffected"
    assert _queue_depth(root) == 0, f"{how}: the graph still learned"
    assert _last_grep_row(root)["learn"] is False


def test_an_explicit_learn_flag_overridden_by_the_toggle_says_so_once(project, monkeypatch):
    """A default-on invocation silenced by the operator's own marker stays
    quiet — a line per grep would make the toggle unusable. An EXPLICIT
    `--learn` is a different thing: the caller asked for something the toggle
    refused, and that conflict is said out loud, on stderr, exactly once."""
    (project / "t.txt").write_text("alpha beta\n")
    root = project / ".refmatrix"
    monkeypatch.setenv("RMX_LEARN", "0")

    res = _run(["grep", "--learn", "alpha"], catch_exceptions=False)

    assert res.exit_code == 0
    assert _queue_depth(root) == 0
    said = [l for l in res.output.splitlines() if "learning is disabled" in l.lower()]
    assert len(said) == 1, res.output


def test_a_default_on_invocation_silenced_by_a_marker_stays_quiet(project):
    (project / "t.txt").write_text("alpha beta\n")
    ls.set_enabled(project / ".refmatrix", False, scope="store")

    res = _run(["grep", "alpha"])

    assert "learning is disabled" not in res.output.lower()


# ---- site 2: the context grep backstop -----------------------------------

def test_the_broker_itself_refuses_when_off(project, monkeypatch):
    """The broker is the funnel both the grep fallback and the context backstop
    reach, and it carries its OWN guard so a future caller that forgets to ask
    cannot teach behind the operator.

    Pinned separately because the two guards are deliberately redundant: a
    mutation check showed that removing either one alone left the backstop test
    green, which is what redundancy does to coverage. Each layer now has a test
    that fails when only that layer is broken."""
    root = project / ".refmatrix"
    hits = [{"file": str(project / "sample.py"), "line": 1}]
    (project / "sample.py").write_text("x = 1\n")

    assert cli_mod._broker_learn_from_grep(root, "target", hits) is True
    assert _queue_depth(root) == 1
    lq.drain(root)

    monkeypatch.setenv("RMX_LEARN", "0")
    out = cli_mod._broker_learn_from_grep(root, "target", hits)

    assert out is False
    assert _queue_depth(root) == 0


def test_the_backstop_does_not_even_walk_the_bundle_when_off(project, monkeypatch):
    """The guard sits before the hits are built, not just before the write —
    with learning off there is no reason to walk the bundle at all. Asserted by
    handing it a bundle that RAISES if its groups are touched, which is what
    makes this test fail when only the backstop's own guard is removed."""
    root = project / ".refmatrix"
    fake_daemon = types.SimpleNamespace(ping=lambda *a, **k: True)

    class _ExplodingBundle:
        @property
        def groups(self):
            raise AssertionError("the backstop walked the bundle with learning off")

    monkeypatch.setenv("RMX_LEARN", "0")
    cli_mod._maybe_learn_grep_backstop(root, fake_daemon, "target",
                                       _ExplodingBundle(), True)

    assert _queue_depth(root) == 0


def test_the_context_backstop_does_not_learn_when_off(project, monkeypatch):
    """Only `ping` is stubbed — the backstop requires a daemon to be up, and
    the broker's default path then APPENDS to the queue, so the assertion is
    about the real queue rather than about a stub."""
    root = project / ".refmatrix"
    f = project / "sample.py"
    f.write_text("def target():\n    return 1\n")
    fake_daemon = types.SimpleNamespace(ping=lambda *a, **k: True)
    entry = types.SimpleNamespace(
        entity=types.SimpleNamespace(path=str(f)), lines=[1], line=1)
    bundle = types.SimpleNamespace(groups={"grep": [entry]})

    # control: ON learns
    cli_mod._maybe_learn_grep_backstop(root, fake_daemon, "target", bundle, True)
    assert _queue_depth(root) >= 1, "toggle ON: the backstop queued nothing"

    lq.drain(root)
    assert _queue_depth(root) == 0
    monkeypatch.setenv("RMX_LEARN", "0")

    cli_mod._maybe_learn_grep_backstop(root, fake_daemon, "target", bundle, True)
    assert _queue_depth(root) == 0, "toggle OFF: the backstop still learned"


# ---- site 3: the daemon's queue drain ------------------------------------

def _daemon_with_store(root):
    from refmatrix.daemon import Daemon

    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    d._log = lambda m: d.__dict__.setdefault("_logs", []).append(m)
    return d


def test_the_drain_skips_and_keeps_the_queue_when_off(project, monkeypatch):
    """Nothing is DROPPED. A drain that ate the queue while learning was off
    would lose the operator's backlog, and a test asserting only "nothing was
    added" would pass against exactly that."""
    root = project / ".refmatrix"
    f = project / "sample.py"
    f.write_text("def target():\n    return 1\n")
    d = _daemon_with_store(root)
    for i in range(3):
        lq.enqueue(root, f"target{i}", [{"file": str(f), "line": 1}])
    depth_before = _queue_depth(root)
    assert depth_before == 3
    monkeypatch.setenv("RMX_LEARN", "0")

    report = d._drain_learn_queue()
    d.store.close()

    assert report.get("skipped") == "learning-disabled"
    assert report.get("pending") == depth_before
    assert report["applied"] == 0
    assert _queue_depth(root) == depth_before, "the drain ate a queue it refused to apply"
    logs = d.__dict__.get("_logs") or []
    assert any("learning-disabled" in m and str(depth_before) in m for m in logs), logs


def test_the_drain_resolves_the_toggle_per_tick_not_at_boot(project, monkeypatch):
    """A long-lived daemon that cached the value at startup is how a shipped
    switch does nothing. Flip it between two ticks on ONE daemon instance."""
    root = project / ".refmatrix"
    f = project / "sample.py"
    f.write_text("def target():\n    return 1\n")
    d = _daemon_with_store(root)

    monkeypatch.setenv("RMX_LEARN", "0")
    lq.enqueue(root, "target", [{"file": str(f), "line": 1}])
    first = d._drain_learn_queue()
    assert first.get("skipped") == "learning-disabled"

    monkeypatch.setenv("RMX_LEARN", "1")
    second = d._drain_learn_queue()
    d.store.close()

    assert second.get("skipped") is None
    assert second["applied"] >= 1, second
    assert _queue_depth(root) == 0


# ---- site 4: the write op ------------------------------------------------

def test_the_learn_op_refuses_by_name_when_off(project, monkeypatch):
    from refmatrix.daemon import _op_learn_from_grep

    root = project / ".refmatrix"
    f = project / "sample.py"
    f.write_text("def target():\n    return 1\n")
    d = _daemon_with_store(root)
    monkeypatch.setenv("RMX_LEARN", "0")

    out = _op_learn_from_grep(d, {"pattern": "target",
                                  "hits": [{"file": str(f), "line": 1}],
                                  "project_root": str(project)})

    assert out == {"added": 0, "skipped": "learning-disabled"}
    # And the concept genuinely is not there. Asserted through the op that
    # READS the index, so the claim does not depend on a Store attribute this
    # test happens to guess right (an earlier version guarded the check with
    # `hasattr`, which is a vacuous assertion dressed as a strict one).
    from refmatrix.daemon import _op_grep_indexed
    rows = _op_grep_indexed(d, {"pattern": "query/target"})["rows"]
    assert rows == [], rows
    d.store.close()


# ---- site 5: the context op's OWN teach ----------------------------------

def test_the_context_op_does_not_learn_when_off(project, monkeypatch):
    """`_op_context` has its own `_learn_grep_hits` call — a sixth site, found
    by sweeping callers rather than by any finding, and the only one the
    mutation check could not kill because nothing tested it at all.

    Driven through the real op against a real store whose index is empty, so
    the grep backstop is what produces the hits."""
    from refmatrix.daemon import _op_context, _op_grep_indexed

    root = project / ".refmatrix"
    # BOTH refs must be present in the corpus. An earlier version of this test
    # used a second ref that matched nothing, so the OFF arm learned nothing
    # whether the guard was there or not — the mutation check passed with the
    # guard deleted, which is the "verification that cannot observe the defect"
    # shape (feedback_red_test_must_fail_at_head).
    (project / "sample.py").write_text(
        "def target_symbol():\n    return 1\n\n\ndef other_symbol():\n    return 2\n")
    d = _daemon_with_store(root)

    # control: with learning ON the op teaches the graph what grep found
    _op_context(d, {"ref": "target_symbol", "grep_backstop": True})
    learned_on = _op_grep_indexed(d, {"pattern": "query/target_symbol"})["rows"]
    assert learned_on, "toggle ON: the context op taught nothing, so the OFF " \
                       "assertion below would be vacuous"

    monkeypatch.setenv("RMX_LEARN", "0")
    _op_context(d, {"ref": "other_symbol", "grep_backstop": True})
    learned_off = _op_grep_indexed(d, {"pattern": "query/other_symbol"})["rows"]
    d.store.close()

    assert learned_off == [], learned_off


# ---- the CLI surface -----------------------------------------------------

def test_learn_status_names_the_deciding_rule(project, monkeypatch):
    res = _run(["learn", "status"])
    assert res.exit_code == 0, res.output
    assert "on" in res.output.lower()
    assert "default" in res.output.lower()

    monkeypatch.setenv("RMX_LEARN", "0")
    res = _run(["learn", "status"])
    assert "off" in res.output.lower()
    assert "env" in res.output.lower()


def test_learn_off_then_status_agree(project):
    res = _run(["learn", "off"])
    assert res.exit_code == 0, res.output

    res = _run(["learn", "status"])
    assert "off" in res.output.lower()
    assert "store-marker" in res.output.lower()

    res = _run(["learn", "on"])
    assert res.exit_code == 0, res.output
    res = _run(["learn", "status"])
    assert "on" in res.output.lower()
    assert "default" in res.output.lower()


def test_learn_status_names_a_rejected_env_value(project, monkeypatch):
    """An operator who typed `RMX_LEARN=of` must see the typo, not a toggle
    that reads ON while they believe they turned it off."""
    monkeypatch.setenv("RMX_LEARN", "of")

    res = _run(["learn", "status"])

    assert res.exit_code == 0, res.output
    assert "of" in res.output
    assert "reject" in res.output.lower() or "ignored" in res.output.lower()


def test_learn_off_global_targets_the_user_scope(project):
    res = _run(["learn", "off", "--global"])
    assert res.exit_code == 0, res.output
    assert ls.global_marker().exists()
    assert not ls.store_marker(project / ".refmatrix").exists()
