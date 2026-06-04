"""--degree flag on `rmx memory recall` and `rmx memory get`.

Both commands gain a --degree flag that, when >0, attaches a context
bundle (body + neighbors with bodies) to each returned memory. The
recall path makes one daemon context call per hit; the get path
appends a "--- context ---" block to its output. Default 0 = current
behavior, no extra round trips.

These tests cover the CLI argument plumbing + the helper logic.
End-to-end behavior runs against an in-process Store with the daemon
ping mocked to False so the degraded `_read_store()` branch fires.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.store import Store


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """Set up a small partition with one memory + one linked concept so
    a context bundle has something to walk. Seed lands in
    `memory-proj` to match what `_apply_memory_partition_default()`
    picks for a project rooted at tmp_path/proj."""
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    with s.with_partition("memory-proj"):
        concept = s.add_concept("parser")
        mid = s.add_memory(
            "parser-quirk", "Tabs in indentation break it.",
            mtype="observation",
        )
        s.link("mentions", concept, mid)
    yield root, s
    s.close()


def _invoke(runner, seeded, args, monkeypatch):
    """Invoke the rmx CLI with daemon-down so the in-process branches
    fire. Forces _root() to return the seeded partition."""
    root, _ = seeded
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    from refmatrix import daemon as daemon_mod
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **kw: False)
    return runner.invoke(cli_mod.main, args)


# ---- memory get --degree --------------------------------------------------


def test_memory_get_default_omits_context(runner, seeded, monkeypatch):
    out = _invoke(runner, seeded,
                  ["-p", "memory-proj", "memory", "get", "parser-quirk"],
                  monkeypatch)
    assert out.exit_code == 0, out.output
    assert "Tabs in indentation break it." in out.output
    assert "--- context ---" not in out.output


def test_memory_get_with_degree_appends_context_block(
    runner, seeded, monkeypatch,
):
    out = _invoke(runner, seeded,
                  ["-p", "memory-proj", "memory", "get",
                   "parser-quirk", "--degree", "1"],
                  monkeypatch)
    assert out.exit_code == 0, out.output
    assert "Tabs in indentation break it." in out.output
    assert "--- context ---" in out.output
    # The context render carries the anchor header + graph footer.
    assert "anchor: parser-quirk" in out.output
    assert "degree=" in out.output


# ---- memory recall --degree -----------------------------------------------
# Recall in degree-0 / recent mode round-trips through _store() which
# the daemon-bypass branch already handles; the degree>0 branch lands
# on the same `_attach_context` helper that the daemon path uses.


def test_memory_recall_recent_degree_zero_no_context_field(
    runner, seeded, monkeypatch,
):
    out = _invoke(runner, seeded,
                  ["-p", "memory-proj", "memory", "recall",
                   "--recent", "--since", "30d", "--json"],
                  monkeypatch)
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert len(data) >= 1
    assert "context" not in data[0]


def test_memory_recall_recent_degree_one_attaches_context_per_row(
    runner, seeded, monkeypatch,
):
    out = _invoke(runner, seeded,
                  ["-p", "memory-proj", "memory", "recall",
                   "--recent", "--since", "30d", "--json", "--degree", "1"],
                  monkeypatch)
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert len(data) >= 1
    # Daemon-down branch builds the context in-process; "context" lands
    # as a text block carrying the anchor header.
    assert data[0].get("context")
    assert "anchor:" in data[0]["context"]


def test_memory_recall_recent_degree_one_gmd_includes_fenced_context(
    runner, seeded, monkeypatch,
):
    out = _invoke(runner, seeded,
                  ["-p", "memory-proj", "memory", "recall",
                   "--recent", "--since", "30d", "--gmd", "--degree", "1"],
                  monkeypatch)
    assert out.exit_code == 0, out.output
    # GMD output folds the context into a fenced block under each H2.
    assert "## parser-quirk" in out.output
    assert "```" in out.output
    assert "anchor:" in out.output
