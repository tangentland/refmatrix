"""Surface-action capture: verbatim `detail` on the timeline + PreToolUse parking.

Two gaps this closes:

1. `terse` drops the actual command as soon as any path ref is extractable
   (`f"{tool} {' '.join(refs) or cmd}"`), so five different greps against one
   file all recorded as `Bash <path>` — the WHERE survived, the WHAT did not.
   `detail` keeps the verbatim action on the timeline while the focus graph
   still sees only the path refs, so no `Bash`/`grep`/path-segment noise is
   admitted as concept nodes.

2. PostToolUse fires only for calls that COMPLETE. A hang, a denial, or a
   session-killing call left no trace at all. PreToolUse parks the call; the
   matching post clears it; leftovers land as `abandoned`.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from refmatrix.cli import main
from refmatrix.stm import Stm


def _hook(tmp_path, event: str, envelope: dict):
    return CliRunner().invoke(
        main, ["focus", "hook", "--event", event],
        input=json.dumps(envelope),
        env={"REFMATRIX_ROOT": str(tmp_path / ".refmatrix")},
    )


def _ring(tmp_path, session="s1") -> list[dict]:
    p = tmp_path / ".refmatrix" / "stm" / f"{session}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


BASH = {
    "session_id": "s1", "tool_use_id": "toolu_1", "tool_name": "Bash",
    "tool_input": {"command": "grep -n 'decay' src/refmatrix/stm.py | head -40"},
}


def test_detail_keeps_the_command_terse_throws_away(tmp_path):
    r = _hook(tmp_path, "tool", BASH)
    assert r.exit_code == 0, r.output
    ev = _ring(tmp_path)[-1]
    # terse is the graph-facing summary: tool + path, command gone.
    assert ev["terse"] == "Bash src/refmatrix/stm.py"
    # detail is the verbatim action.
    assert ev["detail"] == "grep -n 'decay' src/refmatrix/stm.py | head -40"


def test_detail_never_enters_the_focus_graph(tmp_path):
    """The whole reason the command was dropped: shell words as concept nodes."""
    _hook(tmp_path, "tool", BASH)
    ev = _ring(tmp_path)[-1]
    assert ev["refs"] == ["src/refmatrix/stm.py"]
    graph = json.loads(
        (tmp_path / ".refmatrix" / "stm" / "s1.focus.json").read_text())
    nodes = set(graph.get("nodes") or {})
    for junk in ("grep", "head", "decay", "-n"):
        assert junk not in nodes, f"{junk!r} leaked into the focus graph"


def test_structured_tool_input_becomes_detail(tmp_path):
    """Grep/Read carry no `command`; keep their input, minus bulk payloads."""
    _hook(tmp_path, "tool", {
        "session_id": "s1", "tool_use_id": "toolu_2", "tool_name": "Grep",
        "tool_input": {"pattern": "half_life", "glob": "*.py",
                       "content": "x" * 5000},
    })
    ev = _ring(tmp_path)[-1]
    assert "half_life" in ev["detail"]
    assert "xxxxx" not in ev["detail"], "bulk payload not stripped from detail"


def test_pre_parks_without_touching_the_ring_and_post_clears(tmp_path):
    assert _hook(tmp_path, "tool-pre", BASH).exit_code == 0
    assert _ring(tmp_path) == [], "PreToolUse must not append to the ring"
    parked = json.loads(
        (tmp_path / ".refmatrix" / "stm" / "s1.inflight.json").read_text())
    assert "toolu_1" in parked
    assert parked["toolu_1"]["detail"].startswith("grep -n")

    assert _hook(tmp_path, "tool", BASH).exit_code == 0
    assert len(_ring(tmp_path)) == 1, "pre/post pair must record exactly once"
    assert json.loads(
        (tmp_path / ".refmatrix" / "stm" / "s1.inflight.json").read_text()) == {}


def test_abandoned_call_reaches_the_timeline_at_the_next_turn(tmp_path):
    """A call that hung/was denied never gets a PostToolUse. It must still show
    up — that is the whole point of parking it."""
    hang = {
        "session_id": "s1", "tool_use_id": "toolu_hang", "tool_name": "Bash",
        "tool_input": {"command": "sleep 999 && ./scripts/deploy.sh"},
    }
    _hook(tmp_path, "tool-pre", hang)
    # Age it past the sweep window.
    p = tmp_path / ".refmatrix" / "stm" / "s1.inflight.json"
    d = json.loads(p.read_text())
    for v in d.values():
        v["t"] = 0
    p.write_text(json.dumps(d))

    _hook(tmp_path, "input", {"session_id": "s1", "prompt": "what happened?"})
    ring = _ring(tmp_path)
    abandoned = [e for e in ring if e.get("abandoned")]
    assert len(abandoned) == 1
    assert abandoned[0]["detail"] == "sleep 999 && ./scripts/deploy.sh"
    # Ordered ahead of the prompt that asked about it.
    assert ring.index(abandoned[0]) < ring.index(
        next(e for e in ring if e["kind"] == "input"))
    assert json.loads(p.read_text()) == {}


def test_live_call_is_not_swept_prematurely(tmp_path):
    """A tool still running when the user types must not be declared dead."""
    _hook(tmp_path, "tool-pre", BASH)
    _hook(tmp_path, "input", {"session_id": "s1", "prompt": "meanwhile…"})
    assert not [e for e in _ring(tmp_path) if e.get("abandoned")]
    parked = json.loads(
        (tmp_path / ".refmatrix" / "stm" / "s1.inflight.json").read_text())
    assert "toolu_1" in parked


def test_call_key_falls_back_without_tool_use_id(tmp_path):
    """Envelopes lacking tool_use_id must still pair pre with post."""
    env = {"session_id": "s1", "tool_name": "Bash",
           "tool_input": {"command": "ls /tmp/x.txt"}}
    _hook(tmp_path, "tool-pre", env)
    _hook(tmp_path, "tool", env)
    assert json.loads(
        (tmp_path / ".refmatrix" / "stm" / "s1.inflight.json").read_text()) == {}
    assert len(_ring(tmp_path)) == 1


def test_inflight_is_bounded(tmp_path):
    from refmatrix import stm as stm_mod
    s = Stm(tmp_path / ".refmatrix", "s1")
    for i in range(stm_mod.INFLIGHT_BUDGET + 20):
        s.inflight_begin(f"k{i}", terse=f"Bash f{i}.py", refs=[f"f{i}.py"])
    assert len(s._read_inflight()) <= stm_mod.INFLIGHT_BUDGET + 1
