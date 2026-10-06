"""Smoke test for the two-arm replay harness (task 14.4).

The harness produces a MEASUREMENT, and a measurement is not asserted in the
suite — the report carries the numbers. What is asserted here is the only thing
that would silently invalidate every number it produces: that the two arms
really do differ in the learning bit.

So: arm A ends with learned `query/*` concepts and arm B ends with EXACTLY
zero. The zero is the load-bearing half — if the toggle leaked, both arms would
learn and the whole comparison would be measuring nothing while looking
perfectly healthy.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "production"))

import grep_learning_replay as glr  # noqa: E402


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    """A corpus small enough to ingest in a test, and a query log to replay."""
    monkeypatch.delenv("RMX_LEARN", raising=False)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "alpha.py").write_text(
        "def target_symbol():\n    return 1\n\n\ndef other_symbol():\n    return 2\n")
    (corpus / "beta.py").write_text("x = target_symbol()\ny = other_symbol()\n")
    log = tmp_path / "query.log"
    rows = []
    for i, pat in enumerate(["target_symbol", "other_symbol", "target_symbol"]):
        rows.append(json.dumps({"ts": f"2026-10-05T00:00:0{i}", "kind": "grep",
                                "body": pat, "source": "grep-replica",
                                "cardinality": 1, "latency_ms": 5,
                                "outcome": "ok", "error": None}))
    rows.append(json.dumps({"ts": "2026-10-05T00:00:09", "kind": "scan",
                            "body": "not a grep row", "source": "scan-prompt"}))
    log.write_text("\n".join(rows) + "\n")
    return corpus, log


def test_the_workload_is_grep_rows_in_timestamp_order(tiny):
    _, log = tiny

    pats = glr.read_patterns(log)

    # The scan row is not part of the workload, and order is preserved because
    # learning is sequential — a shuffled replay measures a different system.
    assert pats == ["target_symbol", "other_symbol", "target_symbol"]


def test_repeated_only_keeps_the_patterns_that_can_ever_pay_off(tiny):
    _, log = tiny

    assert glr.repeated_patterns(log) == ["target_symbol"]


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx").exists(),
                    reason="needs the dev venv's rmx console script")
def test_arm_a_learns_and_arm_b_learns_exactly_nothing(tiny):
    """The one assertion that protects every number the harness reports.

    Runs the real thing: real stores, the production ingest, real `rmx grep`
    subprocesses, the real drain. If the toggle leaked into arm B the two arms
    would both learn and the comparison would be vacuous while looking healthy.
    """
    corpus, log = tiny
    patterns = glr.read_patterns(log)
    # SHORT root: macOS caps unix socket paths at ~104 bytes.
    root = Path(tempfile.mkdtemp(prefix="rmxTr"))
    hooks = root / "hooks"
    hooks.mkdir()
    try:
        results = {}
        for name, learn in (("A", True), ("B", False)):
            arm = root / name
            glr.build_arm(arm, [corpus], hooks, learn)
            results[name] = glr.replay(arm, patterns, hooks, learn,
                                       verbose=False, drain_every=1)
        a, b = results["A"], results["B"]

        assert b["learned_concepts"] == 0, \
            f"the toggle leaked: arm B learned {b['learned_concepts']} concepts"
        assert a["learned_concepts"] > 0, \
            "arm A learned nothing, so the comparison has no signal"
        # And the rows themselves say which arm wrote them, so the claim does
        # not rest on the harness's own bookkeeping (task 14.1's `learn` field).
        assert a["learn_field"] == {"True": len(patterns)}, a["learn_field"]
        assert b["learn_field"] == {"False": len(patterns)}, b["learn_field"]
        # Exploration calls only: the index is never eligible for a drop-in
        # read, so a non-zero `dropin`/`stdin` here means the harness built
        # calls it did not intend to.
        for arm_stats in (a, b):
            assert "dropin" not in arm_stats["answered_by"], arm_stats
            assert "stdin" not in arm_stats["answered_by"], arm_stats
            assert "missing" not in arm_stats["answered_by"], arm_stats
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_harness_never_points_at_the_live_store():
    """`REFMATRIX_ROOT` is always an arm under the replay root, and the hooks
    dir is always redirected — `rmx init` writes the user-global hooks dir
    otherwise, which bug-008's guard refuses from a dev tree and which no
    measurement has any business touching."""
    env = glr._env(Path("/tmp/rmxX/A"), Path("/tmp/rmxX/hooks"), True)

    assert env["REFMATRIX_ROOT"] == "/tmp/rmxX/A/.refmatrix"
    assert env["RMX_CLAUDE_HOOKS_DIR"] == "/tmp/rmxX/hooks"
    assert env["RMX_LEARN"] == "1"
    assert glr._env(Path("/tmp/rmxX/B"), Path("/tmp/rmxX/hooks"), False)["RMX_LEARN"] == "0"
    # Telemetry is the instrument; a developer's env must not switch it off.
    assert "REFMATRIX_NO_TELEMETRY" not in env


def test_the_harness_uses_the_dev_venv_rmx_not_the_deployed_one():
    """The deployed `rmx` on PATH runs ~/refmatrix. A harness verifying dev code
    with it would measure the wrong tree (feedback_rmx_binary_is_deploy), and a
    dev-version rmx pointed at the live store trips the hub version handshake."""
    assert glr.RMX.parts[-3:] == (".venv-eval", "bin", "rmx")
