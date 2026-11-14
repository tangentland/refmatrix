"""bug-225: save-state / recall-state measure commits-ahead against the repo's
own trunk, read from `refs/remotes/origin/HEAD`, not a hard-coded name list.

At HEAD `handoff._ss_git_facts` walks `("origin/main", "origin/master", "main",
"master")` and takes the first that resolves. In atlftpd, whose trunk is
`develop`, that reported 24 commits ahead of `origin/master` instead of 12
ahead of `origin/develop` (bug-225, workflow/bug_registry.md). The fix reads
`git symbolic-ref --short refs/remotes/origin/HEAD` first and falls back to the
list only when origin/HEAD is unset or names a ref that does not resolve.

Every test drives REAL git repos under a short `mkdtemp(dir="/tmp")` root: a
bare "remote" with `master` and `develop` (develop 3 commits ahead), a clone of
it, and a feature branch 2 commits ahead of develop. Git is never mocked; the
only environment change pins git's identity and hides the user's global/system
git config so `init.defaultBranch` and friends cannot leak in.

RED at HEAD: the origin/HEAD tests (develop, and master-over-main ordering) and
the two compose_* path tests. GUARDS (pass at HEAD by design, must stay green
after the fix): origin/HEAD unset, and origin/HEAD dangling.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from refmatrix import handoff

FEATURE = ["feature commit 1", "feature commit 2"]
DEVELOP = ["develop commit 1", "develop commit 2", "develop commit 3"]


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, f"git {' '.join(args)} failed in {cwd}: {r.stderr}"
    return r.stdout.strip()


def _commit(repo: Path, subject: str) -> None:
    f = repo / "log.txt"
    with f.open("a") as fh:
        fh.write(subject + "\n")
    _git(repo, "add", "log.txt")
    _git(repo, "commit", "-q", "-m", subject)


def _subjects(ahead: str) -> list[str]:
    """`git log --oneline` lines → subjects, newest first."""
    return [ln.split(" ", 1)[1] for ln in ahead.splitlines() if ln.strip()]


@pytest.fixture
def hermetic_git(monkeypatch, tmp_path):
    """Pin identity and hide global/system config for every git process,
    including the ones `handoff._ss_sh` spawns (it inherits os.environ)."""
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "bug225")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "bug225@example.invalid")
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def repos(hermetic_git):
    """(base, work): a bare remote with master + develop (develop 3 ahead), and a
    clone `work` checked out on `feature`, 2 commits ahead of origin/develop.
    origin/HEAD in the clone is whatever `git clone` set: origin/master."""
    base = Path(tempfile.mkdtemp(prefix="b225-", dir="/tmp")).resolve()
    try:
        remote, seed, work = base / "remote.git", base / "seed", base / "work"
        _git(base, "init", "-q", "--bare", "-b", "master", str(remote))
        _git(base, "init", "-q", "-b", "master", str(seed))
        _commit(seed, "root commit")
        _git(seed, "remote", "add", "origin", str(remote))
        _git(seed, "push", "-q", "origin", "master")
        _git(seed, "checkout", "-q", "-b", "develop")
        for s in DEVELOP:
            _commit(seed, s)
        _git(seed, "push", "-q", "origin", "develop")

        _git(base, "clone", "-q", str(remote), str(work))
        assert _git(work, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") \
            == "origin/master"  # precondition: the remote's HEAD is master
        _git(work, "checkout", "-q", "-b", "feature", "origin/develop")
        for s in FEATURE:
            _commit(work, s)
        yield base, work
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- _ss_git_facts: the one place save-state and recall-state read git -----


def test_origin_head_develop_is_the_trunk(repos):
    """AC-1 (RED): origin/HEAD → origin/develop. The handoff measures against
    origin/develop and lists exactly the 2 feature commits. At HEAD the list
    finds origin/master first and reports 5 (3 develop + 2 feature)."""
    _, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/develop", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)), facts["ahead"]


def test_origin_head_beats_list_order(repos):
    """AC-1b (RED): origin/HEAD is read, not appended to the list. The remote
    also carries `main` (an old branch); origin/HEAD names master. At HEAD the
    list picks origin/main because it comes first. A fix that only adds
    `origin/develop` to the list also fails here."""
    base, work = repos
    seed = base / "seed"
    _git(seed, "push", "-q", "origin", "master:main")
    _git(work, "fetch", "-q", "origin")
    assert _git(work, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") \
        == "origin/master"
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))


def test_origin_head_unset_falls_back_to_the_list(repos):
    """AC-2 (GUARD, green at HEAD): no origin/HEAD → the existing list decides,
    unchanged: origin/master (no origin/main on this remote), 5 commits ahead."""
    _, work = repos
    _git(work, "remote", "set-head", "origin", "-d")
    r = subprocess.run(["git", "symbolic-ref", "-q", "refs/remotes/origin/HEAD"],
                       cwd=str(work), capture_output=True, text=True)
    assert r.returncode != 0, "precondition: origin/HEAD must be unset"
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))


def test_origin_head_dangling_falls_back_to_the_list(repos):
    """AC-3 (GUARD, green at HEAD): origin/HEAD names a ref that does not exist
    (a trunk deleted and pruned on the remote). `git symbolic-ref --short` still
    PRINTS `origin/gone` for it, so a fix that trusts that output without
    verifying it would measure against nothing. Must fall back, never raise."""
    _, work = repos
    _git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    assert _git(work, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") == "origin/gone"
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))


# ---- the save-state / recall-state paths that consume the facts ------------


def _stm(base: Path, session: str):
    from refmatrix.stm import Stm
    root = base / ".refmatrix"
    s = Stm(root, session)
    s.record("input", "bug-225 handoff trunk")
    return s, root


def test_save_state_handoff_names_origin_develop(repos):
    """AC-4 (RED): the save-state handoff doc (what the next session reads)
    says 2 commits ahead of origin/develop, not 5 ahead of origin/master."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    s, root = _stm(base, "sess-b225-save")
    res = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)
    doc = res["doc"]
    assert "- **2** commit(s) ahead of `origin/develop`" in doc, doc
    assert "origin/master" not in doc, doc
    assert not (base / "memory").exists()  # dry run wrote nothing


def test_recall_state_anomaly_names_origin_develop(repos):
    """AC-5 (RED): recall-state's anomaly line (the CLI and the MCP tool both
    render it from compose_recall_state) reports 2 ahead of origin/develop."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    s, root = _stm(base, "sess-b225-recall")
    rep = handoff.compose_recall_state(s, root, repo=work, memdir=base / "memory",
                                       pointer_anomalies=[])
    assert rep["git"]["ahead_base"] == "origin/develop", rep["git"]
    ahead = [a for a in rep["anomalies"] if "ahead of" in a]
    assert ahead == ["2 commit(s) ahead of origin/develop (unmerged/undeployed?)"], \
        rep["anomalies"]


# ---- trunk_error: origin/HEAD unreadable is surfaced, never dropped ---------
#
# Pins the GREEN path (81c3e95) that the implementation summary left open
# (workflow/implementation_summaries/bug-225-handoff-trunk.md #open-test): when
# `git symbolic-ref` exits other than 0 (a symref) or 1 (unset), `_ss_origin_head`
# returns the error, `_ss_git_facts` stores it as `trunk_error`, the fallback list
# still picks the trunk, the save-state doc prints a `- trunk:` line and
# recall-state adds an anomaly. These guard GREEN code, so they pass at HEAD; each
# is proven by mutation (workflow/review-output/bug225-trunk-error-mut*.log).
#
# Fixture: the loose ref file is overwritten so git cannot read it as a ref. Probed
# with git 2.50.1 on 2026-11-14: each content below makes `git symbolic-ref --quiet
# --short refs/remotes/origin/HEAD` exit 128 with "fatal: No such ref:
# refs/remotes/origin/HEAD", while `rev-parse --verify origin/master` and
# `git status` still succeed. (`ref: outside/thing`, by contrast, exits 0.)

UNREADABLE = {
    "outside-refs": "ref: ../outside\n",   # a symref pointing outside refs/
    "self-loop": "ref: refs/remotes/origin/HEAD\n",
    "garbage": "garbage\n",                # neither `ref:` nor an object id
}
TRUNK_LINE = "trunk: origin/HEAD unreadable, measured by the fallback list"


def _break_origin_head(work: Path, content: str) -> None:
    (work / ".git" / "refs" / "remotes" / "origin" / "HEAD").write_text(content)
    r = subprocess.run(["git", "symbolic-ref", "--quiet", "--short",
                        "refs/remotes/origin/HEAD"],
                       cwd=str(work), capture_output=True, text=True)
    assert r.returncode == 128, f"precondition: exit 128, got {r.returncode}: {r.stderr}"


@pytest.mark.parametrize("content", list(UNREADABLE.values()), ids=list(UNREADABLE))
def test_unreadable_origin_head_sets_trunk_error_and_list_still_picks(repos, content):
    """AC-6: the facts carry the error, and the list still decides the trunk:
    origin/master (no origin/main on this remote), 5 commits ahead."""
    _, work = repos
    _break_origin_head(work, content)
    facts = handoff._ss_git_facts(work, None)
    err = facts["trunk_error"]
    assert "exited 128" in err, facts
    assert "No such ref: refs/remotes/origin/HEAD" in err, facts
    assert "git symbolic-ref --quiet --short refs/remotes/origin/HEAD" in err, facts
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))


def test_origin_head_unset_or_readable_has_no_trunk_error(repos):
    """AC-6b: exit 1 (unset) and exit 0 (a readable symref, dangling or not) are
    not errors: `trunk_error` stays empty in all three."""
    _, work = repos
    assert handoff._ss_git_facts(work, None)["trunk_error"] == ""      # origin/master
    _git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    assert handoff._ss_git_facts(work, None)["trunk_error"] == ""      # dangling
    _git(work, "remote", "set-head", "origin", "-d")
    assert handoff._ss_git_facts(work, None)["trunk_error"] == ""      # unset


def test_save_state_doc_prints_the_trunk_error(repos):
    """AC-7: the save-state handoff says origin/HEAD could not be read and which
    command failed, under the ahead-of line the fallback list produced."""
    base, work = repos
    _break_origin_head(work, UNREADABLE["outside-refs"])
    s, root = _stm(base, "sess-b225-terr-save")
    res = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)
    lines = res["doc"].splitlines()
    trunk = [ln for ln in lines if TRUNK_LINE in ln]
    assert len(trunk) == 1, res["doc"]
    assert trunk[0].startswith(f"- {TRUNK_LINE} — `git symbolic-ref"), trunk
    assert "exited 128" in trunk[0] and "No such ref" in trunk[0], trunk
    assert "- **5** commit(s) ahead of `origin/master`" in lines, res["doc"]


def test_recall_state_reports_the_trunk_error_as_an_anomaly(repos):
    """AC-8: recall-state lists the unreadable origin/HEAD as an anomaly, next to
    the ahead-of anomaly measured against the fallback trunk."""
    base, work = repos
    _break_origin_head(work, UNREADABLE["outside-refs"])
    s, root = _stm(base, "sess-b225-terr-recall")
    rep = handoff.compose_recall_state(s, root, repo=work, memdir=base / "memory",
                                       pointer_anomalies=[])
    trunk = [a for a in rep["anomalies"] if a.startswith("trunk:")]
    assert len(trunk) == 1, rep["anomalies"]
    assert trunk[0].startswith(f"{TRUNK_LINE} (`git symbolic-ref"), trunk
    assert "exited 128" in trunk[0] and "No such ref" in trunk[0], trunk
    assert "5 commit(s) ahead of origin/master (unmerged/undeployed?)" in rep["anomalies"]


def test_no_trunk_error_line_when_origin_head_reads(repos):
    """AC-7/8 negative: a readable origin/HEAD adds no trunk line to either surface."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    s, root = _stm(base, "sess-b225-terr-clean")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    rep = handoff.compose_recall_state(s, root, repo=work, memdir=base / "memory",
                                       pointer_anomalies=[])
    assert TRUNK_LINE not in doc, doc
    assert not [a for a in rep["anomalies"] if a.startswith("trunk:")], rep["anomalies"]
