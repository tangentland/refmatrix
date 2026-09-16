"""Regressions for ch-bsd r1 findings in plan-9 (telemetry) and plan-7 (eval).

#b-7 the "per-prompt hook budget" counted every hook EVENT, not prompts: on the
     real cli.log only 11.8% of windows contained a scan-prompt at all, and 75%
     of hook rows are `focus hook --event tool/tool-pre` fired per tool call.
#b-6 `--depth` was inert for the `scan` surface while the table printed
     depth=50 and REPORT.md's #1 next step depends on raising it.
#s-12 the new tests wrote rows into the LIVE .refmatrix/cli.log.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from refmatrix import telemetry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "eval" / "production" / "longmemeval"))
import run as lme  # noqa: E402


def _log(tmp_path, rows):
    root = tmp_path / ".refmatrix"
    root.mkdir(exist_ok=True)
    (root / telemetry.CLI_LOG_NAME).write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return root


def _rec(argv, *, out_bytes=100, ts="2026-09-16T10:00:00", source="hook"):
    return {"ts": ts, "argv": argv, "cwd": "/x", "exit_code": 0,
            "latency_ms": 10, "error": None, "pid": 1, "source": source,
            "out_bytes": out_bytes, "out_tokens_est": out_bytes // 4}


# ── #b-7: the budget must count PROMPTS, not every hook event ──────────────

def test_hook_budget_ignores_windows_with_no_prompt(tmp_path):
    """75% of real hook rows are `focus hook --event tool-pre` pairs fired by a
    single tool call. A window with no prompt in it is not a prompt."""
    root = _log(tmp_path, [
        _rec(["focus", "hook", "--event", "tool-pre"], ts="2026-09-16T10:00:00"),
        _rec(["focus", "hook", "--event", "tool"], ts="2026-09-16T10:00:01"),
        _rec(["scan-prompt", "a real prompt"], out_bytes=2000,
             ts="2026-09-16T10:00:30"),
        _rec(["memory", "recall"], out_bytes=3000, ts="2026-09-16T10:00:31"),
    ])
    s = telemetry.summarize_context(root, window_s=5)
    hb = s["hook_budget"]
    assert hb["windows"] == 1, "the tool-pre/tool pair is not a prompt"
    assert hb["max_bytes"] == 5000


def test_hook_budget_names_the_population_it_counted(tmp_path):
    root = _log(tmp_path, [_rec(["scan-prompt", "q"], out_bytes=10)])
    hb = telemetry.summarize_context(root, window_s=5)["hook_budget"]
    assert "scan-prompt" in hb["grouping"], hb["grouping"]
    assert hb["anchored_on"], hb


def test_a_log_of_only_tool_hooks_reports_zero_prompt_windows(tmp_path):
    root = _log(tmp_path, [
        _rec(["focus", "hook", "--event", "tool"], ts=f"2026-09-16T10:0{i}:00")
        for i in range(5)])
    hb = telemetry.summarize_context(root, window_s=5)["hook_budget"]
    assert hb["windows"] == 0
    assert hb["p50_bytes"] == 0


# ── #b-6: depth must reach every method, or not be claimed ─────────────────

@pytest.mark.parametrize("method",
                         sorted(set(lme.METHODS) - lme.DEPTH_UNCONTROLLED))
def test_every_method_carries_the_depth_it_is_labelled_with(method):
    """`scan`/`scan-nocontent` ignored k while the table printed depth=50 and
    REPORT.md's next step is 're-run at --depth 200'."""
    small = lme.METHODS[method].argv("a query", k=7)
    big = lme.METHODS[method].argv("a query", k=700)
    assert small != big, f"{method} ignores depth entirely: {small}"

    # The knob differs per surface (`--max-entities` for context, `-k` for
    # recall, `--max-tokens` for scan-prompt), so assert the invariant that
    # holds for all of them: the depth-bearing number scales with k.
    def _nums(argv):
        return [int(x) for x in argv if str(x).isdigit()]

    lo, hi = _nums(small), _nums(big)
    assert lo and hi, f"{method} carries no numeric depth: {small}"
    assert max(hi) > max(lo), f"{method} depth does not scale: {lo} -> {hi}"


@pytest.mark.parametrize("method", sorted(lme.DEPTH_UNCONTROLLED))
def test_a_depth_uncontrolled_surface_records_null_depth(method):
    """ch-bsd r2 #b-6-r2: --max-tokens is inert in JSON mode, so `scan` has no
    depth knob this harness can turn. It must not be LABELLED with one."""
    questions = [{"question_id": "q0", "question_type": "multi-session",
                  "question": "q"}]
    s = lme.score({"q0": ["g"]}, questions, {"q0": ["g"]}, {"q0": ["g"]},
                  ks=[1], mode="union", depth=None)
    assert s["_meta"]["depth"] is None


# ── #s-13: a dead surface must not look like an empty one in the ARTIFACT ──

def test_failures_are_counted_into_meta_not_just_printed_to_stderr(tmp_path):
    """run.py prints `! {method} {qid}: {exc}` to stderr and returns [].
    `_meta` carried only mode/depth/ceiling/retrieve_s/n_questions, so a surface
    that failed on all 120 questions produced recall 0.000 and no reader of the
    committed JSON could tell (ch-bsd r1 #s-13)."""
    questions = [{"question_id": f"q{i}", "question_type": "multi-session",
                  "question": "q"} for i in range(4)]
    qrels = {q["question_id"]: ["g"] for q in questions}
    hs = {q["question_id"]: ["g"] for q in questions}
    rankings = {"q0": ["g"], "q1": [], "q2": [], "q3": ["g"]}
    s = lme.score(rankings, questions, qrels, hs, ks=[1], mode="union",
                  failed=["q1", "q2"])
    assert s["_meta"]["n_failed"] == 2
    assert sorted(s["_meta"]["failed_ids"]) == ["q1", "q2"]


def test_meta_reports_zero_failures_when_every_surface_answered():
    questions = [{"question_id": "q0", "question_type": "multi-session",
                  "question": "q"}]
    s = lme.score({"q0": ["g"]}, questions, {"q0": ["g"]}, {"q0": ["g"]},
                  ks=[1], mode="union", failed=[])
    assert s["_meta"]["n_failed"] == 0


def test_rank_all_reports_which_questions_failed():
    """The caller must be able to distinguish 'found nothing' from 'blew up'."""
    calls = {"n": 0}

    class _M:
        @staticmethod
        def argv(q, *, k):
            return ["context", q, "--format", "json"]

    def boom(argv, rmx, root):
        calls["n"] += 1
        raise RuntimeError("surface is dead")

    import run as _run
    orig_json, orig_methods = _run._rmx_json, _run.METHODS
    _run._rmx_json = boom
    _run.METHODS = {"fake": _M()}
    try:
        rankings, failed = _run.rank_all(
            "fake", [{"question_id": "q0", "question": "x"}],
            rmx="rmx", root=Path("/tmp"), depth=5, workers=1)
    finally:
        _run._rmx_json, _run.METHODS = orig_json, orig_methods
    assert rankings == {"q0": []}
    assert failed == ["q0"]
