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

import pytest
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


# ---- bug-318: a `git` milestone is a real ref-moving event with its subject -----------------
#
# The PostToolUse capture used to file a `git` event for `git <verb>` anywhere in the command
# text, with the first output line as its terse ("git commit: 0 errors", "git checkout: ??
# .venv-eval"). Now: the command must RUN that verb, the ref state must have moved (read from
# git before/after, PreToolUse snapshot), and the terse is `<verb> <short-sha> <subject>`.

def _hook(tmp_path, event, repo, cmd, stdout="", sid="m1", tid="t9"):
    env = {"REFMATRIX_ROOT": str(tmp_path / ".refmatrix")}
    d = {"session_id": sid, "tool_use_id": tid, "tool_name": "Bash", "cwd": str(repo),
         "tool_input": {"command": cmd}}
    if event == "tool":
        d["tool_response"] = {"stdout": stdout}
    r = CliRunner().invoke(main, ["focus", "hook", "--event", event], env=env,
                           input=json.dumps(d))
    assert r.exit_code == 0, r.output
    return r


def _gits(tmp_path, sid="m1"):
    p = tmp_path / ".refmatrix" / "stm" / f"{sid}.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return [r for r in rows if r["kind"] == "git"]


def _head(repo):
    r = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %s"],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


JUNK = [
    # (command as Claude Code ran it, the output the old code filed as the milestone)
    ("git commit -m x; echo '0 errors'", "nothing to commit, working tree clean\n0 errors"),
    ("git commit -m x && echo done", "1"),
    ("git checkout -- src/gate.py", "?? .venv-eval"),
    ("git merge 9edfdbf1 master", "fatal: Not a valid object name 9edfdbf1"),
    ("rmx focus note 'git init later'; ls", "Usage: rmx install-hooks [OPTIONS]"),
    ("grep -rn 'git commit' src | head", "gmd lint: 1 files, 1 GMD docs, 0 errors, 8 warnings"),
    ("echo \"git push origin master\"", "git push origin master"),
    ("git pull", "Already up to date."),
]


@pytest.mark.parametrize("cmd,stdout", JUNK)
def test_non_moving_or_quoted_git_is_not_a_milestone(tmp_path, cmd, stdout):
    """The six junk lines of bug-318 (and a quoted/grep/echo mention) yield no `git` event:
    the verb did not run, or it moved no ref."""
    repo = _repo(tmp_path, BODY, SOURCE)
    _hook(tmp_path, "tool-pre", repo, cmd)
    _hook(tmp_path, "tool", repo, cmd, stdout)
    assert _gits(tmp_path) == []


@pytest.mark.parametrize("verb,run", [
    ("commit", "git add -A && git commit -q -m 'feat: real subject'"),
    ("tag", "git tag -a v1 -m rel"),
])
def test_a_ref_moving_git_verb_in_a_compound_command_records_its_subject(
        tmp_path, verb, run):
    """`cd repo && <verb>; echo 0 errors`: ONE event, `<verb> <short-sha> <subject>` read
    from git, with none of the command's output in it."""
    repo = _repo(tmp_path, BODY, SOURCE)
    (repo / "src" / "gate.py").write_text(SOURCE + "# more\n")
    cmd = f"cd {repo} && {run}; echo '0 errors'"
    _hook(tmp_path, "tool-pre", repo, cmd)
    subprocess.run(["bash", "-c", run], cwd=repo, check=True, capture_output=True)
    _hook(tmp_path, "tool", repo, cmd, "0 errors\n[master abc1234] bogus\n 9 files changed")
    rows = _gits(tmp_path)
    assert len(rows) == 1, rows
    assert rows[0]["terse"].startswith(f"{verb} "), rows[0]["terse"]
    assert rows[0]["terse"] == f"{verb} {_head(repo)}", rows[0]["terse"]
    assert "errors" not in rows[0]["terse"] and "bogus" not in rows[0]["terse"]


def test_git_dash_C_runs_in_that_repo_not_cwd(tmp_path):
    """`git -C <clone> commit` from another cwd: the pre and post hooks read the CLONE's refs
    (~ and relative paths expanded), and the event carries the clone's commit."""
    repo = _repo(tmp_path, BODY, SOURCE)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (repo / "src" / "gate.py").write_text(SOURCE + "# more\n")
    cmd = f"git -C {repo} add -A && git -C ../repo commit -q -m 'feat: via dash C'"
    _hook(tmp_path, "tool-pre", other, cmd)
    subprocess.run(["bash", "-c", "git add -A && git commit -q -m 'feat: via dash C'"],
                   cwd=repo, check=True, capture_output=True)
    _hook(tmp_path, "tool", other, cmd, "")
    rows = _gits(tmp_path)
    assert [r["terse"] for r in rows] == [f"commit {_head(repo)}"], rows


def test_unreadable_ref_state_is_recorded_not_dropped(tmp_path):
    """A `git commit` whose repo cannot be read (not a repo) is a visible event, never a
    silent drop (STM capture is a memory path)."""
    notrepo = tmp_path / "plain"
    notrepo.mkdir()
    cmd = "git commit -m x"
    _hook(tmp_path, "tool-pre", notrepo, cmd)
    _hook(tmp_path, "tool", notrepo, cmd, "fatal: not a git repository")
    rows = _gits(tmp_path)
    assert [r["terse"] for r in rows] == ["commit (ref state unreadable: RuntimeError)"], rows
