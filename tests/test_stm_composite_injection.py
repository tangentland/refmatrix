"""The STM composite keeps its mechanism but stops spending context on every prompt.

Why (the user, 2026-11-15: "if the stm block is never relevant drop it" / "keep the
mechanism, just don't burn context on every input with it"): in session 070141d0 the
composite's lead topic was the prompt's own plain words (`context, don, relevant, keep,
mechanism, burn, …`) linked to unrelated nodes, re-sent every third turn. Now a topic is
emitted only when it holds at least one grounded member (a file, a path, or an
identifier-shaped name), and a composite whose topics are unchanged since the last one this
session emitted is not sent again. The focus graph still updates every turn.
"""
from __future__ import annotations

from refmatrix import stm as stm_mod
from refmatrix.composite import build_topic_composite


def test_a_plain_word_only_topic_is_not_emitted(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    s.record("input", "keep the mechanism relevant", refs=["mechanism", "relevant", "keep"])
    s.record("input", "mechanism relevant again", refs=["mechanism", "relevant", "keep"])
    assert build_topic_composite(None, root, expand=False, session="sess") == ""


def test_a_grounded_topic_is_emitted(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    s.record("input", "parser and lexer", refs=["parser.py", "lexer"])
    s.record("tool", "edit parser", refs=["parser.py", "lexer", "tokens"])
    out = build_topic_composite(None, root, expand=False, session="sess")
    assert "parser.py" in out, out


def test_an_unchanged_composite_is_not_sent_twice(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    s.record("input", "parser and lexer", refs=["parser.py", "lexer"])
    s.record("tool", "edit parser", refs=["parser.py", "lexer", "tokens"])
    first = build_topic_composite(None, root, expand=False, session="sess")
    assert first
    assert build_topic_composite(None, root, expand=False, session="sess") == ""


def test_a_changed_composite_is_sent_again(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess")
    s.record("input", "parser and lexer", refs=["parser.py", "lexer"])
    s.record("tool", "edit parser", refs=["parser.py", "lexer", "tokens"])
    assert build_topic_composite(None, root, expand=False, session="sess")
    s.record("input", "daemon socket", refs=["daemon.py", "socket_server"])
    s.record("tool", "bind", refs=["daemon.py", "socket_server", "bind"])
    again = build_topic_composite(None, root, expand=False, session="sess")
    assert "daemon.py" in again, again


def test_the_unchanged_check_is_per_session(tmp_path):
    root = tmp_path / ".refmatrix"
    for sess in ("a", "b"):
        s = stm_mod.Stm(root, sess)
        s.record("input", "parser and lexer", refs=["parser.py", "lexer"])
        s.record("tool", "edit parser", refs=["parser.py", "lexer", "tokens"])
    assert build_topic_composite(None, root, expand=False, session="a")
    assert build_topic_composite(None, root, expand=False, session="b")
