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
    """AC-6b: exit 1 (unset) and exit 0 naming a ref that resolves are not errors:
    `trunk_error` stays empty in both. (Until r2 this test also pinned the DANGLING
    case silent; ruling L96 S1 reversed that, so the dangling case moved to
    `test_r2_s1a_dangling_origin_head_is_said_and_the_list_still_picks`.)"""
    _, work = repos
    assert handoff._ss_git_facts(work, None)["trunk_error"] == ""      # origin/master
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


# ==== remedy r2 (ruling L96, on bsd-225 r1 at db411ad) ========================
#
# bsd-225 r1 (workflow/bullshit/2026-11-14-0210-bug225-r1-db411ad.md):
#   S1  the candidate verify and the ahead `git log` go through the swallowing
#       `_ss_sh`; a dangling origin/HEAD falls back with no word; `rev-parse
#       --verify` passes a ref to a missing object, which then reads "0 ahead —
#       in sync".
#   M1  save-state's own result and console never show trunk_error.
#   M2  the shipped template's "if it resolves" leaves out the commit check.
#   M3  the non-git gate (`if facts["branch"]`) is unpinned; `if True` survived.
#
# The git PATH shim below is the one fake: it stands in for the git BINARY (an
# external process) so a verify / ahead call can fail with a non-0/1 exit, which
# a real repo cannot be made to do on demand. Every other git call it sees is
# exec'd to the real git unchanged. Registered in workflow/test_mock_registry.md.

import json
import os
import re
import sys

from click.testing import CliRunner

BAD_SHA = "1" * 40          # a well-formed object id no object has
SHIM_MARK = "b225-shim: forced failure"
DANGLING_NOTE = (r"origin/HEAD names `?{x}`?, which does not resolve; "
                 r"measured against `?{y}`?")


def _flat(text: str) -> str:
    """Whitespace-normalised text, so a console wrap cannot split a phrase."""
    return " ".join(text.split())


@pytest.fixture
def git_shim(tmp_path, monkeypatch):
    """Install a `git` on PATH that fails chosen calls with exit 2 and execs the
    real git for everything else. Returns `arm(mode, log=None)`:

    - mode "verify": `rev-parse` carrying `--verify` or a `^{...}` peel, and any
      `cat-file` (every way to verify a candidate ref) exit 2.
    - mode "ahead": `log` / `rev-list` with a `A..B` range exit 2.
    - mode "": nothing fails; with `log`, every argv is recorded as a JSON line.
    PATH is changed only when `arm` is called, after the fixture repos are built."""
    real = shutil.which("git")
    assert real, "git must be installed"
    bindir = tmp_path / "shim-bin"
    bindir.mkdir()
    shim = bindir / "git"
    shim.write_text(f"""#!{sys.executable} -I
import json, os, sys
REAL = {real!r}
args = sys.argv[1:]
log = os.environ.get("B225_GIT_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps(args) + "\\n")
i = 0
while i < len(args) and args[i].startswith("-"):
    i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
mode = os.environ.get("B225_GIT_FAIL", "")
fail = False
if mode == "verify":
    fail = (sub == "rev-parse" and ("--verify" in rest or any("^{{" in a for a in rest))) \\
        or sub == "cat-file"
elif mode == "ahead":
    fail = sub in ("log", "rev-list") and any(".." in a for a in rest)
if fail:
    sys.stderr.write({SHIM_MARK!r} + " of git " + " ".join(args) + "\\n")
    sys.exit(2)
os.execv(REAL, [REAL] + args)
""")
    shim.chmod(0o755)

    def arm(mode: str, log: "Path | None" = None) -> None:
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("B225_GIT_FAIL", mode)
        if log is not None:
            monkeypatch.setenv("B225_GIT_LOG", str(log))
        assert shutil.which("git") == str(shim), shutil.which("git")
    return arm


def _no_zero_ahead(doc: str) -> None:
    """A failed measurement must never read as a measured zero."""
    assert "**0** commit(s) ahead" not in doc, doc
    assert "in sync" not in doc, doc


# ---- S1(a): a dangling origin/HEAD is said, and the list still picks --------


def test_r2_s1a_dangling_origin_head_is_said_and_the_list_still_picks(repos):
    """origin/HEAD names origin/gone (deleted and pruned on the remote). The list
    decides (origin/master, 5 ahead) AND trunk_error says the declared trunk was
    skipped. At d735ce5 trunk_error is "" (the case was pinned silent)."""
    _, work = repos
    _git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))
    assert re.search(DANGLING_NOTE.format(x="origin/gone", y="origin/master"),
                     facts["trunk_error"]), facts


def test_r2_s1a_dangling_note_reaches_the_doc_and_the_recall_anomalies(repos):
    """The note is printed by both composers, not only stored."""
    base, work = repos
    _git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    note = DANGLING_NOTE.format(x="origin/gone", y="origin/master")
    s, root = _stm(base, "sess-b225-r2-dangle")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    assert re.search(note, _flat(doc)), doc
    rep = handoff.compose_recall_state(s, root, repo=work, memdir=base / "memory",
                                       pointer_anomalies=[])
    assert [a for a in rep["anomalies"] if re.search(note, a)], rep["anomalies"]


# ---- S1(b): a ref to a missing object does not verify -----------------------


def _point_at_missing_object(work: Path, ref: str) -> None:
    """A loose ref (it shadows packed-refs) holding an id no object has. At
    d735ce5 `rev-parse --verify --quiet` still prints it (exit 0)."""
    path = work / ".git" / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BAD_SHA + "\n")
    r = subprocess.run(["git", "cat-file", "-e", f"{BAD_SHA}^{{commit}}"], cwd=str(work),
                       capture_output=True, text=True)
    assert r.returncode != 0, "precondition: the object must not exist"


def test_r2_s1b_origin_head_to_a_missing_object_falls_back_and_is_said(repos):
    """origin/HEAD → origin/develop, and origin/develop holds a missing object id.
    At d735ce5 it verifies, the ahead `git log` fails and is swallowed, and the
    handoff says "0 commit(s) ahead of origin/develop — in sync"."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    _point_at_missing_object(work, "refs/remotes/origin/develop")
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))
    assert re.search(DANGLING_NOTE.format(x="origin/develop", y="origin/master"),
                     facts["trunk_error"]), facts
    s, root = _stm(base, "sess-b225-r2-badobj")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    _no_zero_ahead(doc)


def test_r2_s1b_list_candidate_to_a_missing_object_is_skipped(repos):
    """origin/HEAD unset; origin/main (first in the list) holds a missing object
    id. It must not verify: the list goes on to origin/master. At d735ce5 it picks
    origin/main and reports 0 ahead, in sync."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "-d")
    _point_at_missing_object(work, "refs/remotes/origin/main")
    facts = handoff._ss_git_facts(work, None)
    assert facts["ahead_base"] == "origin/master", facts
    assert _subjects(facts["ahead"]) == list(reversed(FEATURE)) + list(reversed(DEVELOP))
    s, root = _stm(base, "sess-b225-r2-badlist")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    _no_zero_ahead(doc)


# ---- S1(c): a verify or ahead call that FAILS is surfaced, never "0 ahead" ---


def test_r2_s1c_failing_verify_is_surfaced(repos, git_shim):
    """Every verify exits 2 (not "does not resolve", which is exit 1 / no output):
    trunk_error carries the failure. At d735ce5 `_ss_sh` drops it and trunk_error
    is "" while no trunk is measured at all."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    git_shim("verify")
    facts = handoff._ss_git_facts(work, None)
    err = facts["trunk_error"]
    assert SHIM_MARK in err or "exited 2" in err, facts
    s, root = _stm(base, "sess-b225-r2-verify")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    _no_zero_ahead(doc)


def test_r2_s1c_failing_ahead_log_is_surfaced_not_read_as_zero(repos, git_shim):
    """origin/HEAD → origin/develop verifies; the `git log origin/develop..HEAD`
    exits 2. At d735ce5 that reads as "**0** commit(s) ahead of `origin/develop` —
    in sync" with trunk_error "". Both surfaces must say the measurement failed."""
    base, work = repos
    _git(work, "remote", "set-head", "origin", "develop")
    git_shim("ahead")
    facts = handoff._ss_git_facts(work, None)
    err = facts["trunk_error"]
    assert SHIM_MARK in err or "exited 2" in err, facts
    s, root = _stm(base, "sess-b225-r2-ahead")
    doc = handoff.compose_save_state(s, root, repo=work, memdir=base / "memory",
                                     today="2026-11-14", promote=False, dry_run=True)["doc"]
    _no_zero_ahead(doc)
    rep = handoff.compose_recall_state(s, root, repo=work, memdir=base / "memory",
                                       pointer_anomalies=[])
    assert [a for a in rep["anomalies"] if SHIM_MARK in a or "exited 2" in a], \
        rep["anomalies"]


# ---- M1: save-state's own result and console carry trunk_error --------------


def _save_args(base: Path, session: str) -> dict:
    return {"session": session, "memory_dir": str(base / "memory"), "promote": False,
            "lint": False, "sync": False}


def test_r2_m1_save_state_verb_result_carries_trunk_error(repos, monkeypatch):
    """The verb both the CLI and MCP call returns trunk_error (exit-128 fixture).
    At d735ce5 the key is absent from compose_save_state's result."""
    base, work = repos
    _break_origin_head(work, UNREADABLE["outside-refs"])
    from refmatrix import verbs
    root = work / ".refmatrix"
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    res = verbs.VERBS["rmx_save_state"].run(root, _save_args(base, "sess-b225-m1-verb"))
    assert "exited 128" in (res.get("trunk_error") or ""), sorted(res)
    assert "No such ref" in res["trunk_error"], res["trunk_error"]


def test_r2_m1_mcp_save_state_result_carries_trunk_error(repos, monkeypatch):
    """The MCP tool, through the JSON-RPC dispatcher, returns trunk_error."""
    base, work = repos
    _break_origin_head(work, UNREADABLE["outside-refs"])
    from refmatrix import mcp
    root = work / ".refmatrix"
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    resp = mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "rmx_save_state",
                   "arguments": {"root": str(root), **_save_args(base, "sess-b225-m1-mcp")}}})
    result = resp["result"]
    assert not result["isError"], result
    out = json.loads(result["content"][0]["text"])
    assert "exited 128" in (out.get("trunk_error") or ""), sorted(out)


def test_r2_m1_cli_save_state_console_prints_trunk_error(repos, monkeypatch):
    """`rmx save-state` (not --dry-run, which echoes the doc) prints the error on
    the console. At d735ce5 it is only inside the written file."""
    base, work = repos
    _break_origin_head(work, UNREADABLE["outside-refs"])
    from refmatrix import cli as cli_mod
    monkeypatch.setenv("REFMATRIX_ROOT", str(work / ".refmatrix"))
    r = CliRunner().invoke(cli_mod.main, ["save-state", "-s", "sess-b225-m1-cli",
                                          "--memory-dir", str(base / "memory"),
                                          "--no-lint", "--no-promote", "--no-sync"])
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    out = _flat(r.output)
    assert "exited 128" in out and "No such ref: refs/remotes/origin/HEAD" in out, r.output


# ---- M3: the non-git gate ----------------------------------------------------


@pytest.fixture
def nongit(hermetic_git, monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="b225n-", dir="/tmp")).resolve()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(base))
    d = base / "plain"
    d.mkdir()
    (d / "file.txt").write_text("not a repo\n")
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(d),
                           capture_output=True, text=True)
        assert r.returncode != 0, f"precondition: {d} must not be in a work tree"
        yield base, d
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_r2_m3_non_git_dir_gives_all_empty_facts_and_no_trunk_error(nongit):
    """A store whose parent is not a git work tree: every fact is empty, and
    trunk_error is empty (not "origin/HEAD unreadable … not a git repository").
    Kills the `if facts["branch"]:` → `if True:` mutation bsd-225 r1 saw survive."""
    _, d = nongit
    facts = handoff._ss_git_facts(d, None)
    assert "trunk_error" in facts, facts
    assert {k: v for k, v in facts.items() if v} == {}, facts


def test_r2_m3_non_git_dir_never_asks_git_for_origin_head(nongit, git_shim):
    """No `symbolic-ref` subprocess at all for a non-git dir (recorded by the
    PATH shim, which fails nothing in mode "")."""
    base, d = nongit
    log = base / "git-argv.jsonl"
    git_shim("", log=log)
    handoff._ss_git_facts(d, None)
    calls = [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []
    assert calls, "the shim recorded no git call at all; is it on PATH?"
    assert not [c for c in calls if "symbolic-ref" in c], calls


def test_r2_m3_non_git_recall_state_has_no_trunk_anomaly(nongit):
    """And recall-state on such a store reports no trunk anomaly."""
    base, d = nongit
    s, root = _stm(base, "sess-b225-m3-recall")
    rep = handoff.compose_recall_state(s, root, repo=d, memdir=base / "memory",
                                       pointer_anomalies=[])
    assert not [a for a in rep["anomalies"] if "trunk" in a or "origin/HEAD" in a], \
        rep["anomalies"]


# ---- M2: the SHIPPED template says origin/HEAD only when it is a commit -----


def test_r2_m2_shipped_recall_template_checks_origin_head_resolves_to_a_commit():
    """Content check on the package template (never ~/.claude). bsd-225 r1 #m-2:
    for a dangling origin/HEAD `git symbolic-ref --short` exits 0 and prints a
    name, so "if it resolves" sends an agent to `rev-list origin/gone..HEAD`. Step 2
    must tell the agent to check the name resolves to a COMMIT."""
    import refmatrix
    tpl = Path(refmatrix.__file__).parent / "templates" / "commands" / "recall-state.md"
    text = tpl.read_text()
    m = re.search(r"^2\. \*\*Git state\*\*(.*?)^3\. ", text, re.S | re.M)
    assert m, "step 2 (Git state) not found in the shipped recall-state template"
    step2 = _flat(m.group(1))
    assert "refs/remotes/origin/HEAD" in step2, step2
    assert "^{commit}" in step2 or "resolves to a commit" in step2, step2
