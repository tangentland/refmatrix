"""Task 3.7 batch A — `rmx_taxonomy` and the tag-warning parity fix (RED).

Spec #fam-taxonomy:
  - `rmx_taxonomy(action=list|add|remove)` over `~/.refmatrix/taxonomy.json`
    (`$RMX_HOME/taxonomy.json` — the redirect is an env input, not a patch);
  - #fam-taxonomy-admin: add / remove write atomically (temp + rename) under an
    `fcntl` lock on the sidecar `taxonomy.json.lock`, never deleted (r6 M3);
  - #fam-taxonomy-corrupt (data loss): add / remove REFUSE to write over a corrupt
    file (`VerbError` naming it); list and tag validation DEGRADE (a warning, validate
    against nothing — never block `memory add` / `retag`); a read never writes;
  - parity: `memory_add` AND `rmx_memory` `retag` return `tag_warnings` for
    off-vocabulary tags, pointing at `rmx_taxonomy` (action `add`).

Result shapes pinned: list → {categories, path, warnings}; add → {added, tag,
category}; remove → {removed, tag}.
"""
from __future__ import annotations

import fcntl
import threading
import time

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import taxonomy as tax
from refmatrix import verbs
from tests.task3_7_helpers import FakeDaemon, rm, short_root

CORRUPT = b'{"categories": {"mine": {"tags": {"precious": {}}}  <-- truncated'


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "rmxhome"
    h.mkdir()
    monkeypatch.setenv("RMX_HOME", str(h))
    assert tax.taxonomy_path() == h / "taxonomy.json"
    return h


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37t-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


def test_list_on_a_missing_file_returns_the_defaults_and_writes_nothing(home, root):
    out = verbs.taxonomy(root, action="list")
    assert out["categories"], out
    assert not (home / "taxonomy.json").exists(), "a READ wrote the taxonomy file"


def test_add_then_list_then_remove(home, root):
    a = verbs.taxonomy(root, action="add", category="mine", tag="shiny", desc="d",
                       color="#123456")
    assert a["added"] is True and a["tag"] == "shiny" and a["category"] == "mine", a
    cats = verbs.taxonomy(root, action="list")["categories"]
    assert cats["mine"]["tags"]["shiny"] == {"description": "d", "color": "#123456"}
    r = verbs.taxonomy(root, action="remove", tag="shiny")
    assert r == {"removed": True, "tag": "shiny"}, r
    assert verbs.taxonomy(root, action="remove", tag="shiny")["removed"] is False


def test_add_uses_a_sidecar_lock_that_is_never_deleted(home, root):
    verbs.taxonomy(root, action="add", category="mine", tag="t1")
    assert (home / "taxonomy.json.lock").exists(), "no sidecar lock"
    verbs.taxonomy(root, action="add", category="mine", tag="t2")
    assert (home / "taxonomy.json.lock").exists(), "the sidecar lock was deleted"
    assert not list(home.glob("*.tmp")), "a temp file was left behind"


def test_add_waits_for_the_sidecar_lock(home, root):
    """r6 M3: the lock is on `taxonomy.json.lock`, not on the file the rename
    replaces. Held here, an add must not complete until it is released."""
    lock = home / "taxonomy.json.lock"
    fh = open(lock, "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)
    done: list = []
    t = threading.Thread(target=lambda: done.append(
        verbs.taxonomy(root, action="add", category="mine", tag="waited")))
    t.start()
    time.sleep(0.5)
    finished_while_held = bool(done)
    fcntl.flock(fh, fcntl.LOCK_UN)
    fh.close()
    t.join(10)
    assert not finished_while_held, "add ran while another writer held the sidecar lock"
    assert done and done[0]["added"] is True


@pytest.mark.parametrize("action,kw", [("add", {"category": "c", "tag": "t"}),
                                       ("remove", {"tag": "precious"})])
def test_a_corrupt_file_is_never_overwritten(home, root, action, kw):
    p = home / "taxonomy.json"
    p.write_bytes(CORRUPT)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.taxonomy(root, action=action, **kw)
    assert str(p) in str(ei.value), ("the refusal names the file", str(ei.value))
    assert p.read_bytes() == CORRUPT, "the user's vocabulary was overwritten"


def test_list_degrades_on_a_corrupt_file_with_a_warning(home, root):
    p = home / "taxonomy.json"
    p.write_bytes(CORRUPT)
    out = verbs.taxonomy(root, action="list")
    assert out["warnings"] and any(str(p) in w for w in out["warnings"]), out
    assert out["categories"] == {}, "a corrupt vocabulary must validate against nothing"
    assert p.read_bytes() == CORRUPT


def test_cli_add_on_a_corrupt_file_fails_and_keeps_the_file(home, root):
    p = home / "taxonomy.json"
    p.write_bytes(CORRUPT)
    r = CliRunner().invoke(cli_mod.main, ["taxonomy", "add", "c", "t"])
    assert r.exit_code != 0, r.output
    assert p.read_bytes() == CORRUPT


# ---- tag_warnings parity -----------------------------------------------------------


def _memory_daemon(monkeypatch, root):
    from refmatrix import discovery
    return FakeDaemon({
        "partition_list": {"ok": True, "result": {"rows": [{"name": discovery.store_name(root)}]}},
        "memory_add": {"ok": True, "result": {"id": 11}},
        "memory_retag": lambda a: {"ok": True, "result": {"tags": list(a.get("add") or [])}},
    }).install(monkeypatch)


def test_memory_add_returns_tag_warnings_for_off_vocabulary_tags(home, root, monkeypatch):
    fd = _memory_daemon(monkeypatch, root)
    out = verbs.memory_add(root, "n", "c", tags=["bug", "zzz-unknown"])
    assert fd.last("memory_add"), "the write must still happen"
    warns = out.get("tag_warnings")
    assert warns, out
    joined = " ".join(warns)
    assert "zzz-unknown" in joined and "bug" not in joined.replace("zzz-unknown", "")
    assert "rmx_taxonomy" in joined, "the warning points at rmx_taxonomy (action add)"


def test_memory_add_with_known_tags_has_no_tag_warnings(home, root, monkeypatch):
    _memory_daemon(monkeypatch, root)
    out = verbs.memory_add(root, "n", "c", tags=["bug"])
    assert not out.get("tag_warnings"), out


def test_retag_returns_tag_warnings(home, root, monkeypatch):
    _memory_daemon(monkeypatch, root)
    out = verbs.memory(root, action="retag", name="n", add=["zzz-unknown"])
    assert any("zzz-unknown" in w for w in out.get("tag_warnings") or []), out


def test_a_corrupt_vocabulary_never_blocks_memory_add(home, root, monkeypatch):
    p = home / "taxonomy.json"
    p.write_bytes(CORRUPT)
    fd = _memory_daemon(monkeypatch, root)
    out = verbs.memory_add(root, "n", "c", tags=["zzz-unknown"])
    assert fd.last("memory_add")
    assert any(str(p) in w for w in out.get("tag_warnings") or []), (
        "the corruption is reported as a warning", out)
    assert p.read_bytes() == CORRUPT
