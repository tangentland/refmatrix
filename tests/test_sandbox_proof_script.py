"""Task 23.0 AC-4: `scripts/sandbox-proof.sh` proves the whole suite left no row in a live log,
judged by CONTENT (ns23-2), and its detector is proven to fire with no live write.

Size and mtime cannot be the check: the live logs grow from normal activity during a 13-minute
run. The wrapper draws `RMX_SANDBOX_TAG`, records each log's `(inode, size)`, runs the suite,
and fails if any DELTA line (bytes past the recorded size; the whole file if the inode changed)
carries the tag, `/pytest-of-`, the sandbox root, or (query.log) the d9g fixture shape -- a
learn/grep row whose body has `alpha|beta` and no `cwd`.

These tests are AC-4's pre-registered detector check: `--live-logs <decoy>` points the wrapper
at copies, and a small inner test (standing in for "one grep test mutated to write into the
decoy") writes the leak. Nothing here reads or writes a real log.

Interface assumed beyond the spec text (spec names only `--live-logs <dir>`), see the RED
report: the decoy dir holds `global/{query,facts}.log` (for `~/.refmatrix`) and
`repo/{query,facts}.log` (for the repo's `.refmatrix/`); arguments after `--` replace the
full-suite selection; `RMX_PYTEST_PY` names the interpreter (as `scripts/ptest.sh` does).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_PROOF = _REPO / "scripts" / "sandbox-proof.sh"
_LOGS = [("global", "query.log"), ("global", "facts.log"),
         ("repo", "query.log"), ("repo", "facts.log")]
_BENIGN = {"ts": "2026-10-14T12:42:00", "kind": "context", "body": "build_context",
           "cwd": "/Users/someone/proj", "outcome": "ok"}


def _decoy(tmp_path: Path) -> Path:
    d = tmp_path / "decoy"
    for sub, name in _LOGS:
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / name).write_text(json.dumps(_BENIGN) + "\n" + json.dumps(_BENIGN) + "\n")
    return d


def _inner(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "inner" / "test_leak.py"
    f.parent.mkdir()
    f.write_text(body)
    return f


def _proof(decoy: Path, inner: Path) -> subprocess.CompletedProcess:
    assert _PROOF.is_file(), f"{_PROOF} does not exist"
    assert os.access(_PROOF, os.X_OK), f"{_PROOF} is not executable"
    env = dict(os.environ)
    env["RMX_PYTEST_PY"] = sys.executable
    return subprocess.run(
        [str(_PROOF), "--live-logs", str(decoy), "--",
         str(inner), "-q", "-p", "no:cacheprovider"],
        cwd=str(_REPO), capture_output=True, text=True, env=env, timeout=600)


def _writer(decoy: Path, sub: str, name: str, row_expr: str) -> str:
    return f'''
import json, os
def test_leak(tmp_path):
    tag = os.environ["RMX_SANDBOX_TAG"]
    row = {row_expr}
    with open({str(decoy / sub / name)!r}, "a") as fh:
        fh.write(json.dumps(row) + "\\n")
'''


@pytest.mark.parametrize("sub,name,row_expr", [
    pytest.param("repo", "query.log",
                 '{"kind": "grep", "body": "x", "root": f"/tmp/rmx-{tag}-q1/s/.refmatrix"}',
                 id="tagged-sandbox-path"),
    pytest.param("global", "query.log",
                 '{"kind": "grep", "body": "alpha|beta", "source": "grep", "outcome": "ok"}',
                 id="d9g-fixture-shape"),
    pytest.param("global", "facts.log",
                 '{"op": "link", "path": str(tmp_path / "f.md")}',
                 id="pytest-temp-path"),
])
def test_detector_fails_a_leaked_row(tmp_path, sub, name, row_expr):
    """AC-4 detector: a leaked row carrying the run tag, the fixture shape, or a pytest temp
    path in a decoy log makes the wrapper FAIL. A detector that passes it is the defect."""
    decoy = _decoy(tmp_path)
    r = _proof(decoy, _inner(tmp_path, _writer(decoy, sub, name, row_expr)))
    assert r.returncode != 0, f"wrapper passed a leaked row:\n{r.stdout[-3000:]}"
    assert str(decoy / sub / name) in r.stdout + r.stderr, (
        f"wrapper did not name the leaking log:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")


def test_detector_reads_the_whole_file_when_the_inode_changed(tmp_path):
    """AC-4: 'if the inode changed because a compaction rewrote facts.log, the whole new
    file'. The tagged row is placed BEFORE the recorded size, so only a whole-file read sees
    it; a reader that seeks to the old offset misses it."""
    decoy = _decoy(tmp_path)
    target = decoy / "repo" / "facts.log"
    old_size = target.stat().st_size
    body = f'''
import json, os
def test_compact():
    tag = os.environ["RMX_SANDBOX_TAG"]
    first = json.dumps({{"op": "link", "root": f"/tmp/rmx-{{tag}}-c1/s"}}) + "\\n"
    assert len(first) < {old_size}
    pad = json.dumps({{"op": "benign", "cwd": "/Users/someone/proj"}}) + "\\n"
    new = {str(target)!r} + ".compact"
    with open(new, "w") as fh:
        fh.write(first + pad * 10)
    os.replace(new, {str(target)!r})
'''
    r = _proof(decoy, _inner(tmp_path, body))
    assert r.returncode != 0, f"a compacted log's tagged row was missed:\n{r.stdout[-3000:]}"


def test_live_activity_without_markers_passes_and_counts_are_printed(tmp_path):
    """AC-4 negative control: other sessions' rows (a cwd, no tag, no pytest path, not the
    fixture shape) cannot fail the check, and the wrapper prints a per-log line for all four."""
    decoy = _decoy(tmp_path)
    paths = [str(decoy / sub / name) for sub, name in _LOGS]
    body = f'''
import json
def test_live_activity():
    for p in {paths!r}:
        with open(p, "a") as fh:
            fh.write(json.dumps({{"kind": "grep", "body": "foo", "cwd": "/Users/someone/proj",
                                  "outcome": "ok"}}) + "\\n")
'''
    r = _proof(decoy, _inner(tmp_path, body))
    assert r.returncode == 0, f"benign live rows failed the check:\n{r.stdout[-3000:]}\n" \
                              f"{r.stderr[-2000:]}"
    for p in paths:
        assert p in r.stdout, f"no per-log report line for {p}:\n{r.stdout[-3000:]}"
