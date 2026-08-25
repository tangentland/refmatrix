"""Harvest the WHY from channels that are already mandatory.

`rmx focus note` requires the agent to remember to call it, and empirically it
doesn't — the rule has existed since 2026-06-20 and goes whole sessions unused.
Extended thinking is redacted from the transcript, so there is no fallback.

The reliable channels are the ones written to finish the task anyway: the
commit message body (global rationale) and comments added in the diff (local
rationale, sitting next to the code they explain). Both are mined, not asked
for, so they cost no discipline.
"""
from __future__ import annotations

import json
import subprocess

from click.testing import CliRunner

from refmatrix.cli import main


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, body: str, source: str):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _git_init = ["init", "-q", "."]
    subprocess.run(["git", "init", "-q", str(repo)], check=True,
                   capture_output=True)
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    (repo / "src" / "gate.py").write_text("def gate():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "src" / "gate.py").write_text(source)
    _git(repo, "add", "-A")
    msg = repo / "msg.txt"
    msg.write_text(body)
    _git(repo, "commit", "-q", "-F", str(msg))
    return repo


def _fire(tmp_path, repo, subject="fix(gate): tighten the gate"):
    env = {"REFMATRIX_ROOT": str(tmp_path / ".refmatrix")}
    return CliRunner().invoke(
        main, ["focus", "hook", "--event", "tool"], env=env,
        input=json.dumps({
            "session_id": "w1", "tool_use_id": "t1", "tool_name": "Bash",
            "cwd": str(repo), "tool_input": {"command": "git commit -F msg.txt"},
            "tool_response": {"stdout": f"[master abc1234] {subject}\n"
                                        " 1 file changed, 4 insertions(+)"},
        }))


def _events(tmp_path, kind=None):
    p = tmp_path / ".refmatrix" / "stm" / "w1.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return [r for r in rows if kind is None or r["kind"] == kind]


BODY = """fix(gate): stop the gate re-firing at its minimal size

Gating on size alone loops forever when the compacted form can never get back
under the threshold. The gate now asks whether the pass HELPED.

Co-Authored-By: Someone <x@y.z>
Signed-off-by: Someone <x@y.z>
"""

SOURCE = """def gate(size, threshold, floor=0):
    # A pass that reclaims nothing must not re-fire: the size gate alone
    # loops forever once the minimal form already exceeds the threshold.
    # ---------
    # type: ignore
    # ok
    return size >= max(threshold, floor)
"""


def test_commit_body_becomes_a_reason_event(tmp_path):
    repo = _repo(tmp_path, BODY, SOURCE)
    assert _fire(tmp_path, repo).exit_code == 0
    why = [r for r in _events(tmp_path, "reason")
           if r["terse"].startswith("why commit")]
    assert len(why) == 1
    assert "loops forever" in why[0]["detail"]
    # The git event kept only the subject; the reason event carries the body.
    assert "loops forever" not in _events(tmp_path, "git")[0]["terse"]


def test_trailers_are_not_rationale(tmp_path):
    repo = _repo(tmp_path, BODY, SOURCE)
    _fire(tmp_path, repo)
    why = next(r for r in _events(tmp_path, "reason")
               if r["terse"].startswith("why commit"))
    assert "Co-Authored-By" not in why["detail"]
    assert "Signed-off-by" not in why["detail"]


def test_added_comments_are_mined_and_denoised(tmp_path):
    repo = _repo(tmp_path, BODY, SOURCE)
    _fire(tmp_path, repo)
    com = next(r for r in _events(tmp_path, "reason")
               if r["terse"].startswith("comments added"))
    assert "must not re-fire" in com["detail"]
    # Directives, rules and stubs carry no rationale.
    for junk in ("type: ignore", "---------", ": ok"):
        assert junk not in com["detail"], f"{junk!r} kept as rationale"
    assert com["refs"] == ["src/gate.py"], "rationale must attach to its file"


def test_no_body_no_comments_means_no_reason_events(tmp_path):
    """A bare `-m` commit that adds no comments must not manufacture a why."""
    repo = _repo(tmp_path, "chore: bump\n",
                 "def gate():\n    return 2\n")
    _fire(tmp_path, repo, subject="chore: bump")
    assert _events(tmp_path, "reason") == []
    assert len(_events(tmp_path, "git")) == 1


def test_merge_body_is_not_harvested(tmp_path):
    """Merge bodies are generated, not authored — no rationale to mine."""
    repo = _repo(tmp_path, BODY, SOURCE)
    env = {"REFMATRIX_ROOT": str(tmp_path / ".refmatrix")}
    CliRunner().invoke(
        main, ["focus", "hook", "--event", "tool"], env=env,
        input=json.dumps({
            "session_id": "w1", "tool_use_id": "t2", "tool_name": "Bash",
            "cwd": str(repo), "tool_input": {"command": "git merge origin/x"},
            "tool_response": {"stdout": "Fast-forward\n 1 file changed"},
        }))
    assert _events(tmp_path, "reason") == []
