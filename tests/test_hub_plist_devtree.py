"""bug-028 — the hub plist had no dev-tree refusal and nothing ever checked it.

plan-4 Q15 built `_refuse_dev_tree` and wired it into the eight per-daemon
plists. The same commit edited `render_hub_plist` two lines below the
untouched `_rmx_path()` call, so the HUB plist kept rendering whatever `which
rmx` returned — with `RMX_BIN` pointing at a dev binary, `ProgramArguments[0]`
became the dev tree, unrefused. Quoted-line sibling, and worse than the daemon
case: a drifted daemon plist is caught by `check(root, rmx=)` on every
`relaunch-fleet`, while nothing ever compared the hub plist to its render —
and the hub is the fleet's watchdog, the owner of the shared model workers,
and the version handshake.
"""

from __future__ import annotations

import plistlib

import pytest

from refmatrix import launchctl as lc


DEV = "/dev/tree/.venv/bin/rmx"
DEPLOY = "/deploy/.venv/bin/rmx"


@pytest.fixture(autouse=True)
def _identities(monkeypatch):
    """`binary_identity` asks the binary itself; pin the two answers."""
    def _ident(rmx: str) -> dict:
        if rmx == DEV:
            return {"dev_tree": True, "import_path": "/dev/tree/src/refmatrix"}
        return {"dev_tree": False, "import_path": "/deploy/src/refmatrix"}
    monkeypatch.setattr(lc, "binary_identity", _ident)
    monkeypatch.setattr(lc, "_rmx_path", lambda: DEPLOY)


def _args(blob: bytes) -> list[str]:
    return plistlib.loads(blob)["ProgramArguments"]


def test_render_hub_plist_takes_the_callers_binary():
    """It rendered `_rmx_path()` unconditionally, so a caller holding the
    deployed binary could not make it use that one."""
    assert _args(lc.render_hub_plist(rmx=DEPLOY))[0] == DEPLOY


def test_render_hub_plist_refuses_a_dev_tree_binary():
    with pytest.raises(RuntimeError, match="dev tree"):
        lc.render_hub_plist(rmx=DEV)


def test_install_hub_refuses_a_dev_binary_before_touching_anything(
        monkeypatch, tmp_path):
    """The refusal must come BEFORE the stop order and before the write, or a
    refused install has already torn down a working hub. Asserted as: plist
    not written, zero launchctl calls (bug-023's shape)."""
    calls: list = []
    monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", tmp_path)
    monkeypatch.setattr(lc, "hub_plist_path", lambda: tmp_path / "hub.plist")
    monkeypatch.setattr(lc, "_require_darwin", lambda: None)
    monkeypatch.setattr(lc.subprocess, "run",
                        lambda *a, **k: calls.append(a) or None)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: calls.append("loaded") or True)
    monkeypatch.setattr(lc, "_stop_hub_before_bootout",
                        lambda *a, **k: calls.append("stop"))

    with pytest.raises(RuntimeError, match="dev tree"):
        lc.install_hub(rmx=DEV)

    assert not (tmp_path / "hub.plist").exists(), "a refused install wrote a plist"
    assert calls == [], f"a refused install touched the system: {calls}"


def test_install_hub_allows_a_dev_binary_when_asked(monkeypatch, tmp_path):
    """`allow_dev` is the documented escape on the daemon side; the hub gets
    the same one so a deliberate dev install is possible and explicit."""
    monkeypatch.setattr(lc, "LAUNCH_AGENTS_DIR", tmp_path)
    monkeypatch.setattr(lc, "hub_plist_path", lambda: tmp_path / "hub.plist")
    monkeypatch.setattr(lc, "_require_darwin", lambda: None)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: False)
    monkeypatch.setattr(lc.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(lc, "_wait_hub_loaded", lambda **k: True)
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    p = lc.install_hub(rmx=DEV, allow_dev=True)
    assert _args(p.read_bytes())[0] == DEV


# ---- check_hub: nothing ever compared the hub plist to its render ----------

def test_check_hub_reports_a_missing_plist(monkeypatch, tmp_path):
    monkeypatch.setattr(lc, "hub_plist_path", lambda: tmp_path / "absent.plist")
    ok, why = lc.check_hub(rmx=DEPLOY)
    assert ok is False and "absent.plist" in why


def test_check_hub_is_clean_when_the_installed_plist_matches_its_render(
        monkeypatch, tmp_path):
    p = tmp_path / "hub.plist"
    p.write_bytes(lc.render_hub_plist(rmx=DEPLOY))
    monkeypatch.setattr(lc, "hub_plist_path", lambda: p)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: True)
    ok, why = lc.check_hub(rmx=DEPLOY)
    assert ok is True, why


def test_check_hub_reports_drift_when_the_plist_does_not_match(
        monkeypatch, tmp_path):
    p = tmp_path / "hub.plist"
    p.write_bytes(lc.render_hub_plist(rmx=DEPLOY, port=7777))
    monkeypatch.setattr(lc, "hub_plist_path", lambda: p)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: True)
    ok, why = lc.check_hub(rmx=DEPLOY, port=9999)
    assert ok is False and "drift" in why.lower()


def test_check_hub_names_a_dev_binary_as_drift_that_must_not_be_fixed(
        monkeypatch, tmp_path):
    """Mirrors `check(root, rmx=)`: from a dev shell every plist reads as
    drifted, and 'fixing' it would point the hub at the dev venv."""
    p = tmp_path / "hub.plist"
    p.write_bytes(lc.render_hub_plist(rmx=DEPLOY))
    monkeypatch.setattr(lc, "hub_plist_path", lambda: p)
    ok, why = lc.check_hub(rmx=DEV)
    assert ok is False and "dev tree" in why


def test_check_hub_flags_an_installed_but_unloaded_label(monkeypatch, tmp_path):
    """bug-013's shape: the file is current and the job is not running."""
    p = tmp_path / "hub.plist"
    p.write_bytes(lc.render_hub_plist(rmx=DEPLOY))
    monkeypatch.setattr(lc, "hub_plist_path", lambda: p)
    monkeypatch.setattr(lc, "hub_is_loaded", lambda: False)
    ok, why = lc.check_hub(rmx=DEPLOY)
    assert ok is False and "not loaded" in why
