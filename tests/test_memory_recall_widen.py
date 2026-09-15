"""plan-5 task 5.3 — the CLI `--session-start` widen rule on a real daemon
(the verb-level test lives in test_verbs_memory_recall.py; this is the
hook's actual command line)."""
from __future__ import annotations

import json
import shutil

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from tests.test_verbs_memory_recall import _spawn, DAY


@pytest.fixture
def live_old(monkeypatch):
    base, root = _spawn(8 * DAY)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


def test_session_start_widens_to_newest_k_when_the_7d_window_is_empty(live_old):
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "--session-start", "--k", "10",
                                          "--scope", "project", "--json"])
    assert r.exit_code == 0, r.output
    assert [m["name"] for m in json.loads(r.stdout)] == ["fresh", "old", "older"]
    assert "widened" in (r.stderr or "")


def test_explicit_since_is_honored_not_widened(live_old):
    r = CliRunner().invoke(cli_mod.main, ["memory", "recall", "--session-start", "--since", "7d",
                                          "--k", "10", "--scope", "project", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == []
    assert "widened" not in (r.stderr or "")
