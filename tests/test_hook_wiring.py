"""Phase 4/wiring: hook templates carry the invocation form, focus capture,
and scope=both recall; `rmx focus hook` parses Claude envelopes."""
from __future__ import annotations

import json

from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix.hooks import _claude_hook_block
from refmatrix.stm import Stm


def _all_commands(block):
    cmds = []
    for entries in block["hooks"].values():
        for e in entries:
            for h in e.get("hooks", []):
                cmds.append(h["command"])
    return cmds


def test_hook_block_tags_invocation_source(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    rmx_cmds = [c for c in _all_commands(block) if "rmx " in c]
    assert rmx_cmds
    assert all("RMX_INVOCATION_SOURCE=hook" in c for c in rmx_cmds)


def test_hook_block_has_focus_capture(tmp_path):
    cmds = _all_commands(_claude_hook_block(tmp_path / ".refmatrix"))
    assert any("focus hook --event tool" in c for c in cmds)
    assert any("focus hook --event input" in c for c in cmds)


def test_hook_block_recall_scope_both(tmp_path):
    cmds = _all_commands(_claude_hook_block(tmp_path / ".refmatrix"))
    recalls = [c for c in cmds if "memory recall" in c]
    assert recalls and all("--scope both" in c for c in recalls)


def test_focus_hook_input_event(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    envelope = json.dumps({"prompt": "work on build_context in context.py",
                           "session_id": "S1"})
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"],
                           input=envelope)
    assert r.exit_code == 0
    rows = Stm(root, "S1").tail()
    assert rows and rows[-1]["kind"] == "input"
    assert "build_context" in rows[-1]["refs"]


def test_focus_hook_tool_event(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    envelope = json.dumps({"tool_name": "Edit", "session_id": "S2",
                           "tool_input": {"file_path": "/proj/store.py"}})
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "tool"],
                           input=envelope)
    assert r.exit_code == 0
    rows = Stm(root, "S2").tail()
    assert rows and rows[-1]["kind"] == "tool"
    assert "/proj/store.py" in rows[-1]["refs"]


def test_focus_hook_empty_envelope_noop(tmp_path, monkeypatch):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    r = CliRunner().invoke(main, ["focus", "hook", "--event", "input"], input="")
    assert r.exit_code == 0  # malformed stdin = silent no-op
