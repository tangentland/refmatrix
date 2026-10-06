"""The learning toggle: ONE resolver, four rules, stated precedence (task 14.2).

`--learn/--no-learn` has always existed per invocation. What was missing is
state that outlives one process: the daemon's drain and a hook-spawned child
both learn without ever seeing a shell flag, so there was no way to turn the
grep→graph loop off and measure the system without it.

A marker FILE rather than a key in the catalog, because the two callers that
most need the answer cannot open a store: the PreToolUse rewrite hook (a `[ -f ]`
test, no Python import, on every bare grep in every session) and a CLI whose
daemon is down.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import learn_switch as ls


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_LEARN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    r = tmp_path / ".refmatrix"
    r.mkdir()
    return r


# ---- the default ---------------------------------------------------------

def test_learning_is_on_by_default(root):
    assert ls.learning_enabled(root) is True
    assert ls.decision(root).rule == "default"


# ---- each rule on its own ------------------------------------------------

def test_the_env_turns_it_off(root, monkeypatch):
    for val in ("0", "off", "false", "no", "OFF", "False"):
        monkeypatch.setenv("RMX_LEARN", val)
        d = ls.decision(root)
        assert d.enabled is False, val
        assert d.rule == "env"


def test_the_env_turns_it_on(root, monkeypatch):
    for val in ("1", "on", "true", "yes", "ON"):
        monkeypatch.setenv("RMX_LEARN", val)
        d = ls.decision(root)
        assert d.enabled is True, val
        assert d.rule == "env"


def test_the_store_marker_turns_it_off(root):
    ls.store_marker(root).write_text("off\n")
    d = ls.decision(root)
    assert d.enabled is False
    assert d.rule == "store-marker"


def test_the_global_marker_turns_it_off(root):
    ls.global_marker().parent.mkdir(parents=True, exist_ok=True)
    ls.global_marker().write_text("off\n")
    d = ls.decision(root)
    assert d.enabled is False
    assert d.rule == "global-marker"


# ---- precedence ----------------------------------------------------------

def test_the_env_beats_both_markers(root, monkeypatch):
    """A one-off override has to be able to turn learning back ON for a single
    command without the operator deleting their own marker."""
    ls.store_marker(root).write_text("off\n")
    ls.global_marker().parent.mkdir(parents=True, exist_ok=True)
    ls.global_marker().write_text("off\n")
    monkeypatch.setenv("RMX_LEARN", "1")

    d = ls.decision(root)
    assert d.enabled is True
    assert d.rule == "env"


def test_the_store_marker_beats_the_global_marker(root):
    ls.global_marker().parent.mkdir(parents=True, exist_ok=True)
    ls.global_marker().write_text("off\n")
    ls.store_marker(root).write_text("off\n")

    assert ls.decision(root).rule == "store-marker"


def test_a_global_off_reaches_a_store_with_no_marker(root):
    ls.global_marker().parent.mkdir(parents=True, exist_ok=True)
    ls.global_marker().write_text("off\n")

    assert ls.learning_enabled(root) is False


# ---- a malformed value is NAMED, not guessed -----------------------------

def test_a_malformed_env_value_does_not_silently_decide(root, monkeypatch):
    """`RMX_LEARN=banana` must not read as either answer. It falls through to
    the next rule and the decision SAYS the value was rejected, so
    `rmx learn status` can show an operator their typo instead of a toggle that
    looks on while they believe it is off (CLAUDE.md#no-silent-failures)."""
    monkeypatch.setenv("RMX_LEARN", "banana")

    d = ls.decision(root)
    assert d.enabled is True            # the default, not the env
    assert d.rule == "default"
    assert d.rejected_env == "banana"


def test_a_malformed_env_value_still_lets_a_marker_decide(root, monkeypatch):
    monkeypatch.setenv("RMX_LEARN", "banana")
    ls.store_marker(root).write_text("off\n")

    d = ls.decision(root)
    assert d.enabled is False
    assert d.rule == "store-marker"
    assert d.rejected_env == "banana"


# ---- writing the state ---------------------------------------------------

def test_set_enabled_round_trips_the_store_marker(root):
    ls.set_enabled(root, False)
    assert ls.learning_enabled(root) is False

    ls.set_enabled(root, True)
    assert ls.learning_enabled(root) is True
    assert not ls.store_marker(root).exists()


def test_set_enabled_round_trips_the_global_marker(root):
    ls.set_enabled(root, False, scope="global")
    assert ls.global_marker().exists()
    assert ls.learning_enabled(root) is False

    ls.set_enabled(root, True, scope="global")
    assert not ls.global_marker().exists()
    assert ls.learning_enabled(root) is True


def test_turning_it_on_at_store_scope_does_not_clear_a_global_off(root):
    """Scopes are independent: a project saying "learn here" must not silently
    delete the machine-wide setting. The resolver still reports OFF, and
    `rmx learn status` names the global marker as the reason."""
    ls.set_enabled(root, False, scope="global")
    ls.set_enabled(root, True, scope="store")

    assert ls.global_marker().exists()
    assert ls.learning_enabled(root) is False
    assert ls.decision(root).rule == "global-marker"


# ---- the resolver must stay cheap and store-free -------------------------

def test_the_resolver_imports_nothing_from_refmatrix_and_no_database():
    """The rewrite hook and a CLI with a dead daemon both ask this question.
    Importing or opening a store to answer it would put a database attach on the
    path of every bare grep.

    Asserted over the module's IMPORTS via the AST, not over its prose — an
    earlier version of this test grepped the source text and failed on the word
    appearing in a docstring, which is a test measuring the wrong thing."""
    import ast
    import refmatrix.learn_switch as mod

    tree = ast.parse(Path(mod.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [m for m in imported if m.split(".")[0] in ("refmatrix", "duckdb")], \
        imported
    assert imported <= {"os", "dataclasses", "pathlib", "__future__"}, imported
