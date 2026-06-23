"""rmx save-state: the session-handoff compiler (STM + git + memory → one
stable-id GMD memory). Unit-level checks on the pure helpers + render."""
from __future__ import annotations

from refmatrix import cli, handoff


def test_clean_focus_drops_shell_noise_keeps_code():
    nodes = [
        {"name": "Bash", "kind": "concept", "count": 50, "weight": 2.3},
        {"name": "echo", "kind": "concept", "count": 20, "weight": 1.6},
        {"name": "src/refmatrix/cli.py", "kind": "code", "count": 13, "weight": 1.3},
        {"name": "daemon", "kind": "concept", "count": 5, "weight": 1.1},
        {"name": "tholley", "kind": "concept", "count": 23, "weight": 1.5},
    ]
    out = [n["name"] for n in handoff._ss_clean_focus(nodes)]
    assert "Bash" not in out and "echo" not in out and "tholley" not in out
    assert "src/refmatrix/cli.py" in out  # code always kept
    assert "daemon" in out                # real concept kept


def test_frozen_created_preserves_existing(tmp_path):
    p = tmp_path / "savestate_abc.md"
    p.write_text("---\nid: savestate_abc\n  created: 2026-01-01\n---\n")
    assert handoff._ss_frozen_created(p, "2026-06-20") == "2026-01-01"


def test_frozen_created_defaults_today_when_absent(tmp_path):
    assert handoff._ss_frozen_created(tmp_path / "nope.md", "2026-06-20") == "2026-06-20"


def test_render_has_gmd_frontmatter_and_sections():
    doc = handoff._ss_render(
        mem_id="savestate_x", session="sess-x", repo=__import__("pathlib").Path("/r/proj"),
        message="headline", git={"branch": "master", "head": "abc123 msg",
                                  "dirty": "M f.py", "ahead_base": "origin/main",
                                  "ahead": "abc123 msg", "session_commits": "abc123 msg"},
        focus={"events": 9, "nodes": [{"name": "f.py", "kind": "code",
                                       "count": 3, "weight": 1.2}]},
        tasks=[{"desc": "do the thing", "ts": "2026-06-20T10:00:00"}],
        recents=[("other_mem", "Other Memory")],
        created="2026-06-20", today="2026-06-20")
    assert 'gmd: "0.1"' in doc
    assert "id: savestate_x" in doc
    assert "originSessionId: sess-x" in doc
    assert "# Save-state 2026-06-20: headline {#root}" in doc
    assert "## Session {#session}" in doc
    assert "## Focus {#focus}" in doc
    assert "## Tasks {#tasks}" in doc
    assert "[[other_mem]]" in doc
    assert "rel: realizes -> [[feedback_save_state_means_handoff]]" in doc


def test_update_index_replaces_not_duplicates(tmp_path):
    idx = tmp_path / "MEMORY.md"
    idx.write_text("- [Old](savestate_x.md) — old hook\n- [Keep](other.md) — keep\n")
    handoff._ss_update_index(tmp_path, "savestate_x", "New Title", "new hook")
    body = idx.read_text()
    assert body.count("savestate_x.md") == 1
    assert "New Title" in body and "old hook" not in body
    assert "other.md" in body  # untouched


# ---- say capture: assistant transcript → STM (full-dialogue STM) ----


def test_last_assistant_text_extracts_latest(tmp_path):
    import json as _j
    tp = tmp_path / "t.jsonl"
    tp.write_text("\n".join([
        _j.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        _j.dumps({"type": "assistant", "message": {"role": "assistant",
                  "content": [{"type": "text", "text": "first reply"}]}}),
        _j.dumps({"type": "assistant", "message": {"role": "assistant",
                  "content": [{"type": "tool_use", "name": "Bash"}]}}),  # no text
        _j.dumps({"type": "assistant", "message": {"role": "assistant",
                  "content": [{"type": "text", "text": "latest  reply\nline2"}]}}),
    ]))
    assert cli._last_assistant_text(str(tp)) == "latest reply line2"


def test_last_assistant_text_missing_file():
    assert cli._last_assistant_text("/no/such/transcript.jsonl") == ""


def test_stop_hook_template_records_say():
    from refmatrix import hooks
    from pathlib import Path
    block = hooks._claude_hook_block(Path("/proj/.refmatrix"))
    stop_cmds = [h["command"] for blk in block["hooks"]["Stop"]
                 for h in blk["hooks"]]
    assert any("focus hook --event say" in c for c in stop_cmds)


# ---- git milestone capture ----


def test_git_milestone_detects_mutating_ops():
    assert cli._git_milestone_subcmd("git commit -m x") == "commit"
    assert cli._git_milestone_subcmd("git -C /r push origin master") == "push"
    assert cli._git_milestone_subcmd("git merge --ff-only origin/master") == "merge"
    # read-only ops are NOT milestones
    assert cli._git_milestone_subcmd("git status --short") is None
    assert cli._git_milestone_subcmd("git log --oneline") is None
    assert cli._git_milestone_subcmd("echo git commit") is None  # not a git cmd


def test_tool_output_text_flattens():
    assert cli._tool_output_text({"stdout": "a", "stderr": "b"}) == "a\nb"
    assert cli._tool_output_text("plain") == "plain"
    assert cli._tool_output_text(None) == ""


# ---- focus summarize (STM → LTM digest) ----


def test_focus_digest_has_sections(tmp_path):
    from refmatrix.stm import Stm
    s = Stm(tmp_path / ".refmatrix", "sess")
    s.record("input", "build the thing")
    s.record("tool", "x", refs=["a.py", "b.py"])
    s.record("git", "git commit: [m abc] done", refs=["a.py"])
    s.record("input", "ship it")
    digest = cli._focus_digest(s)
    assert "# Session summary" in digest
    assert "## Top (by strength)" in digest      # strength-ranked top-N
    assert "1. `" in digest and "w=" in digest
    assert "## Milestones" in digest and "git commit" in digest
    assert "## Arc" in digest
    assert "build the thing" in digest and "ship it" in digest


# ---- compose: the shared CLI+MCP save/recall core ----


def test_compose_save_state_writes_handoff_and_index(tmp_path):
    from refmatrix.stm import Stm
    root = tmp_path / ".refmatrix"
    repo = tmp_path
    s = Stm(root, "sess-compose")
    s.record("input", "do work")
    s.record("tool", "x", refs=["a.py"])
    memdir = tmp_path / "memory"
    res = handoff.compose_save_state(
        s, root, repo=repo, memdir=memdir, today="2026-06-23",
        message="hand off", promote=False, dry_run=False)
    target = memdir / f"{res['mem_id']}.md"
    assert res["mem_id"] == "savestate_sesscompose"
    assert target.exists()
    assert "hand off" in target.read_text()
    assert (memdir / "MEMORY.md").read_text().count(f"{res['mem_id']}.md") == 1
    assert res["promoted"] is None  # promote=False


def test_compose_save_state_dry_run_writes_nothing(tmp_path):
    from refmatrix.stm import Stm
    root = tmp_path / ".refmatrix"
    s = Stm(root, "sess-dry")
    s.record("input", "peek")
    memdir = tmp_path / "memory"
    res = handoff.compose_save_state(
        s, root, repo=tmp_path, memdir=memdir, today="2026-06-23",
        promote=False, dry_run=True)
    assert res["dry_run"] is True
    assert 'gmd: "0.1"' in res["doc"]
    assert not memdir.exists()  # nothing written


def test_compose_recall_state_pulls_latest_handoff(tmp_path):
    from refmatrix.stm import Stm
    root = tmp_path / ".refmatrix"
    s = Stm(root, "sess-recall")
    s.record("input", "resume")
    memdir = tmp_path / "memory"
    memdir.mkdir()
    (memdir / "savestate_old.md").write_text(
        "---\nid: savestate_old\n---\n\n# Old handoff {#root}\n\nbody here\n")
    rep = handoff.compose_recall_state(s, root, repo=tmp_path, memdir=memdir)
    assert rep["session"] == "sess-recall"
    assert rep["savestate"]["id"] == "savestate_old"
    assert "body here" in rep["savestate"]["body"]
    assert "Old handoff" in rep["savestate"]["body"]
    assert rep["stm_digest"] is not None  # session has events
    assert isinstance(rep["anomalies"], list)
    assert rep["daemon"]["running"] is False  # no daemon for tmp root


def test_compose_recall_state_no_handoff(tmp_path):
    from refmatrix.stm import Stm
    root = tmp_path / ".refmatrix"
    s = Stm(root, "sess-empty")
    rep = handoff.compose_recall_state(
        s, root, repo=tmp_path, memdir=tmp_path / "memory")
    assert rep["savestate"] is None
    assert rep["stm_digest"] is None  # no events
    assert rep["recent_memories"] == []
