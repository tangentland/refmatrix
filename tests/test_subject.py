"""Subject — memory-scoped working/durable container (ADR-0002).

Covers the three faces:
  * STM partition (stm.py): change-subject rebinds the ring; clear reverts;
    latest_session stays the Claude session despite the subject suffix.
  * durable store ops (store.py): upsert_subject / link_part_of / list_subjects
    / subject_leaves walk the `part-of` index.
  * CLI roundtrip (cli.py): change-subject → subjects → promote files the digest
    under the active subject → recall --subject surfaces it.

All daemon-down (in-proc) — the CliRunner path the suite uses elsewhere.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from refmatrix import stm as stm_mod
from refmatrix.store import Store, default_partition_name


# ---- STM partition ----

def test_set_subject_rebinds_ring(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess1")
    s.record("input", "working on parser.py")
    bare = s._path
    rec = s.set_subject("Explore External Functionality")
    assert rec["subject"] == "explore_external_functionality"
    # ring now points at the composite partition file
    assert s._path != bare
    assert s._path.name == "sess1__explore_external_functionality.jsonl"
    s.record("input", "touch connector.py")
    assert s._path.exists()
    # a fresh handle for the same session inherits the active subject
    s2 = stm_mod.Stm(root, "sess1")
    assert s2.subject == "explore_external_functionality"
    assert s2._path == s._path


def test_clear_subject_reverts_to_bare_ring(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "sess1")
    s.set_subject("thing one")
    assert s.subject == "thing_one"
    had = s.clear_subject()
    assert had is True
    assert s.subject is None
    assert s._path.name == "sess1.jsonl"
    # subsequent handle is bare again
    assert stm_mod.Stm(root, "sess1").subject is None


def test_latest_session_strips_subject_suffix(tmp_path):
    root = tmp_path / ".refmatrix"
    s = stm_mod.Stm(root, "abc-123")
    s.set_subject("a subject")
    s.record("input", "x")
    # the newest ring on disk is the composite, but the resumable unit is the
    # Claude session id, not session__subject
    assert stm_mod.latest_session(root) == "abc-123"


# ---- durable store ops ----

def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    return s


def test_upsert_subject_idempotent(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    a = s.upsert_subject("Explore X")
    b = s.upsert_subject("Explore X")
    assert a["id"] == b["id"]
    assert a["slug"] == "explore_x"
    m = s.get_memory(a["id"])
    assert m["mtype"] == "subject"
    assert m["metadata"]["label"] == "Explore X"


def test_part_of_index_and_leaves(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    subj = s.upsert_subject("pursuit")
    leaf1 = s.add_memory("digest-a", "a", mtype="session/digest")
    leaf2 = s.add_memory("handoff-b", "b", mtype="session/recall-state")
    s.link_part_of(leaf1, subj["id"])
    s.link_part_of(leaf2, subj["id"])

    subs = s.list_subjects()
    assert len(subs) == 1
    assert subs[0]["leaves"] == 2

    leaves = s.subject_leaves(subj["id"])
    names = {m["name"] for m in leaves}
    assert names == {"digest-a", "handoff-b"}
    # resolvable by bare label too
    assert {m["name"] for m in s.subject_leaves("pursuit")} == names


def test_subject_leaves_unknown_is_empty(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    assert s.subject_leaves("nope") == []


# ---- CLI roundtrip ----

def _cli_env(monkeypatch, tmp_path):
    root = tmp_path / ".refmatrix"
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setenv("RMX_PARTITION", default_partition_name(root))
    monkeypatch.setenv("RMX_SESSION", "clisess")
    Store(root).init()
    return root


def test_cli_change_subject_and_list(tmp_path, monkeypatch):
    _cli_env(monkeypatch, tmp_path)
    from refmatrix.cli import main as cli
    r = CliRunner()
    out = r.invoke(cli, ["focus", "change-subject", "Explore Ext"])
    assert out.exit_code == 0, out.output
    assert "Explore Ext" in out.output

    shown = r.invoke(cli, ["focus", "subject"])
    assert "Explore Ext" in shown.output

    lst = r.invoke(cli, ["focus", "subjects"])
    assert lst.exit_code == 0, lst.output
    assert "Explore Ext" in lst.output


def test_cli_promote_refuses_without_a_daemon(tmp_path, monkeypatch):
    """plan-2 Q4 (2026-09-14): the Stop hook runs `focus summarize --promote`
    every turn; with the daemon down it must refuse loudly, never open the
    active slot from a CLI process."""
    root = _cli_env(monkeypatch, tmp_path)
    from refmatrix.cli import main as cli
    stm_mod.Stm(root, "clisess").record("input", "something to summarize")
    prom = CliRunner().invoke(cli, ["focus", "summarize", "--promote"])
    assert prom.exit_code != 0
    assert "daemon not running" in prom.output


def test_cli_promote_files_under_subject_and_recall(monkeypatch):
    """Real path: a spawned daemon on a short tmp root (unix socket sun_path
    limit), promote through it, then recall the leaves filed under the
    subject through the same daemon."""
    import shutil
    import tempfile
    from refmatrix import daemon as dm
    from refmatrix.cli import main as cli
    base = Path(tempfile.mkdtemp(prefix="rmxs-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.setenv("RMX_SESSION", "clisess")
    monkeypatch.chdir(root.parent)
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        r = CliRunner()
        s = stm_mod.Stm(root, "clisess")
        s.record("input", "build the subject feature in stm.py and cli.py")
        assert r.invoke(cli, ["focus", "change-subject", "subject feature"]).exit_code == 0

        prom = r.invoke(cli, ["focus", "summarize", "--promote"])
        assert prom.exit_code == 0, prom.output
        assert "filed under subject" in prom.output

        # The daemon serves subject_leaves from the read snapshot, which
        # follows the write after the snapshot debounce: poll briefly.
        import time
        rows = []
        for _ in range(40):
            rec = r.invoke(cli, ["memory", "recall", "--subject", "subject feature", "--json"])
            assert rec.exit_code == 0, rec.output
            rows = json.loads(rec.output)
            if rows:
                break
            time.sleep(0.25)
        assert any(m["mtype"] == "session/digest" for m in rows), rows
    finally:
        dm.stop_daemon(root)
        shutil.rmtree(base, ignore_errors=True)
