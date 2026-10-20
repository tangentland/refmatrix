"""Task 3.7 batch A — folded deferral row R53 (RED).

Spec #folded-r53 (ch-bsd plan-3 r12 #m-2):
  - `verbs.global_recall_rows` routes its transport exception through
    `classify_transport_error(e, op=op, root=groot, timeout=timeout)` and re-raises its
    TYPE (r12 probe: held → "failed: timed out", stopped → "[Errno 2]", refused →
    "[Errno 61]", all one plain `VerbError` with a raw errno);
  - `cli._file_under_active_subject`'s catch-all narrows to the `RuntimeError` that
    `_subject_upsert` / `_subject_link` raise for `ok:false` — a non-OSError transport
    failure (the empty-reply `JSONDecodeError` of a daemon dying mid-request) is not
    "the daemon refused".

R52 (the guard plants) lives beside the other plants in tests/test_task3_6_r9_remedy.py.
"""
from __future__ import annotations

import json

import click
import pytest

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import hub as hub_mod
from refmatrix import stm as stm_mod
from refmatrix import verbs


@pytest.fixture
def global_store():
    """The sandbox's global store exists (conftest initialises it)."""
    g = hub_mod.global_store_root()
    assert g.exists(), g
    return g


@pytest.mark.parametrize("exc,typ", [
    (ConnectionRefusedError(61, "Connection refused"), verbs.VerbAbsentError),
    (FileNotFoundError(2, "No such file or directory"), verbs.VerbAbsentError),
    (TimeoutError("timed out"), verbs.VerbBusyError),
])
def test_global_recall_rows_types_its_transport_error(global_store, monkeypatch, exc, typ):
    def raising(*a, **k):
        raise exc
    monkeypatch.setattr(hub_mod, "global_call", raising)
    with pytest.raises(typ) as ei:
        verbs.global_recall_rows("x", k=3, recent=False, since_s=None, timeout=3.0, retries=0)
    assert str(global_store) in str(ei.value), ("worded by THE classifier (it names the root)",
                                                str(ei.value))


def test_global_recall_rows_keeps_an_answered_refusal_plain(global_store, monkeypatch):
    monkeypatch.setattr(hub_mod, "global_call",
                        lambda *a, **k: {"ok": False, "error": "CANARY-refused"})
    with pytest.raises(verbs.VerbError) as ei:
        verbs.global_recall_rows("x", k=3, recent=False, since_s=None)
    assert "CANARY-refused" in str(ei.value)
    assert not isinstance(ei.value, (verbs.VerbBusyError, verbs.VerbAbsentError))


def _subject_session(tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    s = stm_mod.Stm(root, "sA")
    s.record("input", "x Alpha")
    s.set_subject("Topic Q")
    return root, s


def test_a_non_oserror_transport_failure_is_not_called_a_refusal(tmp_path, monkeypatch):
    root, s = _subject_session(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)

    def dying(*a, **k):
        raise json.JSONDecodeError("Expecting value", "", 0)
    monkeypatch.setattr(dm, "call", dying)
    try:
        cli_mod._file_under_active_subject(s, 5, timeout=2.0, retries=0, daemon_up=True)
    except click.ClickException as e:
        assert "refused" not in e.message, ("a dying daemon's empty reply was labelled a "
                                            "refusal", e.message)
    except json.JSONDecodeError:
        pass        # narrowed: the catch-all no longer swallows a transport failure
    else:
        pytest.fail("the failure vanished")


def test_an_ok_false_refusal_is_still_named_a_refusal(tmp_path, monkeypatch):
    """The guard that keeps holding: the narrowed handler still names a real refusal."""
    root, s = _subject_session(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dm, "call", lambda *a, **k: {"ok": False, "error": "CANARY-no"})
    with pytest.raises(click.ClickException) as ei:
        cli_mod._file_under_active_subject(s, 5, timeout=2.0, retries=0, daemon_up=True)
    assert "refused" in ei.value.message and "CANARY-no" in ei.value.message
