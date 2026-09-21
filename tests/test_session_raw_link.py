"""Hard-link every ingested transcript so deleting the original cannot lose it.

Session cards are a ~2% summary; the JSONL is the only full record. Transcripts
DO disappear — viascope has 155 session rows and zero `.jsonl` (archived to zip
by hand), and atldb has 5 rmx STM rings proving sessions ran with an empty
transcript directory. rmx does not delete them (audited 2026-09-20: the only
write in `session_ingest` is the card), but something does, and a card cannot be
re-derived from a card.

A hard link costs ZERO bytes — it is a second name for the same inode — and it
keeps the data alive after the original name is removed. Claude Code appends to
the transcript in place (verified: inode stable across writes), so the link
stays live rather than freezing a snapshot.

The cost this accepts, deliberately: a linked inode is never reclaimed while our
name exists, so deleted transcripts keep occupying disk. That is the trade the
feature exists to make.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from refmatrix import session_ingest as si


def _jsonl(tmp_path: Path, sid: str = "abc123", body: str = "hello") -> Path:
    p = tmp_path / "src" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "user", "sessionId": sid, "cwd": str(tmp_path),
         "timestamp": "2026-09-20T10:00:00Z",
         "message": {"role": "user", "content": body}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_ingesting_a_session_hard_links_the_source(tmp_path):
    src = _jsonl(tmp_path)
    dest = tmp_path / "store" / "sessions"
    status, linked = si.link_raw(src, dest)

    assert status == "linked", status
    assert linked is not None and linked.exists()
    assert os.stat(linked).st_ino == os.stat(src).st_ino, "must be a hard link, not a copy"


def test_the_link_survives_deletion_of_the_original(tmp_path):
    """The whole point: the transcript outlives its original name."""
    src = _jsonl(tmp_path, body="irreplaceable")
    dest = tmp_path / "store" / "sessions"
    _, linked = si.link_raw(src, dest)

    src.unlink()
    assert not src.exists()
    assert linked.exists()
    assert "irreplaceable" in linked.read_text()


def test_appends_to_the_original_are_visible_through_the_link(tmp_path):
    """Claude Code appends in place, so the link is a LIVE second name — not a
    snapshot taken at ingest time."""
    src = _jsonl(tmp_path)
    dest = tmp_path / "store" / "sessions"
    _, linked = si.link_raw(src, dest)

    with src.open("a") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user",
                                                        "content": "later turn"}}) + "\n")
    assert "later turn" in linked.read_text()


def test_linking_twice_is_idempotent_and_reported_as_present(tmp_path):
    src = _jsonl(tmp_path)
    dest = tmp_path / "store" / "sessions"
    si.link_raw(src, dest)
    status, linked = si.link_raw(src, dest)
    assert status == "present", status
    assert os.stat(linked).st_ino == os.stat(src).st_ino


def test_a_REPLACED_source_is_kept_alongside_the_old_one(tmp_path):
    """If the transcript is replaced (new inode, same name), the old link still
    holds the old content and must NOT be clobbered — that content exists
    nowhere else. Both are kept."""
    src = _jsonl(tmp_path, body="original")
    dest = tmp_path / "store" / "sessions"
    _, first = si.link_raw(src, dest)

    src.unlink()
    src = _jsonl(tmp_path, body="replacement")      # same name, new inode
    status, second = si.link_raw(src, dest)

    assert status == "rotated", status
    assert second != first
    assert "original" in first.read_text()
    assert "replacement" in second.read_text()


def test_a_failure_is_REPORTED_not_swallowed(tmp_path, monkeypatch):
    """No silent failures on a data-preservation path."""
    src = _jsonl(tmp_path)
    dest = tmp_path / "store" / "sessions"

    def _boom(a, b):
        raise OSError(18, "Cross-device link")

    monkeypatch.setattr(os, "link", _boom)
    status, linked = si.link_raw(src, dest)
    assert status.startswith("failed"), status
    assert "cross-device" in status.lower()
    assert linked is None


def test_ingest_session_protects_the_source_on_the_MAIN_path(tmp_path):
    """Not an optional flag: `rmx session ingest` — which is what the launchd
    job runs — protects by default, so the scheduled backfill protects too."""
    src = _jsonl(tmp_path)
    dest = tmp_path / "store" / "sessions"

    out, data, link_status = si.ingest_session(src, dest)
    assert out.exists()
    raw = dest / "raw" / f"{data.session_id}.jsonl"
    assert raw.exists(), "the main ingest path did not protect the transcript"
    assert os.stat(raw).st_ino == os.stat(src).st_ino
    assert link_status == "linked"


def test_the_cli_protects_ALREADY_CARDED_transcripts_too(tmp_path, monkeypatch):
    """The skip path is the one that matters. A session whose card already
    exists `continue`s before ingest, so without a link there, every
    previously-ingested transcript — the OLD ones, the most likely to be
    removed upstream and the least likely to be re-ingested — would stay
    unprotected forever."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    proj.mkdir()
    s = Store(root)
    s.init()
    s.close()

    home = tmp_path / "home"
    slug = str(proj).replace("/", "-").replace("_", "-")
    tdir = home / ".claude" / "projects" / slug
    tdir.mkdir(parents=True)
    src = tdir / "sess1.jsonl"
    src.write_text(json.dumps({
        "type": "user", "sessionId": "sess1", "cwd": str(proj),
        "timestamp": "2026-09-20T10:00:00Z",
        "message": {"role": "user", "content": "only copy"}}) + "\n")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.setenv("RMX_SESSION_INGEST_QUIET_S", "0")

    runner = CliRunner()
    first = runner.invoke(cli_mod.main, ["session", "ingest", "--no-index"])
    assert first.exit_code == 0, first.output
    raw = root / "sessions" / "raw" / "sess1.jsonl"
    assert raw.exists(), first.output

    # Remove the link, leave the card: the "already carded" state.
    raw.unlink()
    second = runner.invoke(cli_mod.main, ["session", "ingest", "--no-index"])
    assert second.exit_code == 0, second.output
    assert "skipped=1" in second.output, second.output
    assert raw.exists(), (
        "an already-carded transcript was left unprotected:\n" + second.output)
    assert os.stat(raw).st_ino == os.stat(src).st_ino
