"""What rmx spends of the model's context window, measured at the real boundary.

RED first for task 9.2 (plan-9). Three hooks fire on every prompt and each one
writes its output straight into the context window. `query.log` and `cli.log`
have always recorded LATENCY and never BYTES, so this project can say a hook
took 1.7 s and cannot say whether it charged 400 bytes or 40 KB of the window it
was supposed to be enriching.

Counting happens ONCE, around `sys.stdout` in `cli_entry` — not at N renderers.
That is the honest boundary: a hook captures this process's stdout and injects
exactly those bytes, so the count is the real payload rather than an estimate of
it, covers every command uniformly, and cannot drift. An `out_bytes` set at each
render site is the four-copies-of-one-thing failure
`feedback_reuse_shared_stoplist` records.

What these tests pin:

  * A `rich.Console` built BEFORE the wrapper is installed is still counted —
    `cli.py`'s `console` is module-level, so if rich bound stdout eagerly the
    wrapper would measure only bare `print` and silently under-report every
    table the CLI emits.
  * BYTES, not characters. A UTF-8 prompt must not under-count.
  * The proxy is transparent. `isatty()` in particular changes how rich
    renders, so a wrapper that lied about it would change the very bytes it
    exists to measure.
  * Restoration on `SystemExit` — click exits that way on every single run.
  * Telemetry stays best-effort: a counting failure must never fail the command.
"""
from __future__ import annotations

import io
import json
import sys

import pytest

from refmatrix import telemetry


# ── the proxy ──────────────────────────────────────────────────────────────

def test_the_proxy_counts_bytes_written_by_print():
    inner = io.StringIO()
    p = telemetry.CountingStream(inner)
    print("hello", file=p)
    assert p.out_bytes == len("hello\n".encode())


def test_a_rich_console_built_before_the_wrapper_is_still_counted(monkeypatch):
    """`cli.py`'s `console` is created at import time. If rich bound stdout
    eagerly, this wrapper would miss every table the CLI prints."""
    from rich.console import Console

    console = Console()                      # bound before the swap, as in cli.py
    inner = io.StringIO()
    proxy = telemetry.CountingStream(inner)
    monkeypatch.setattr(sys, "stdout", proxy)
    console.print("a rendered line")
    assert proxy.out_bytes > 0
    assert "a rendered line" in inner.getvalue()


def test_multibyte_output_is_counted_in_bytes_not_characters():
    inner = io.StringIO()
    p = telemetry.CountingStream(inner)
    text = "→ café ✓"                        # 8 chars, more than 8 bytes
    p.write(text)
    assert p.out_bytes == len(text.encode("utf-8"))
    assert p.out_bytes > len(text)


def test_the_proxy_is_transparent_about_ttyness_and_encoding():
    """rich branches on isatty() to decide colour and width — a wrapper that
    lied would change the bytes it is measuring."""
    class Inner(io.StringIO):
        def isatty(self): return True
        def fileno(self): return 7
        @property
        def encoding(self): return "utf-8"

    p = telemetry.CountingStream(Inner())
    assert p.isatty() is True
    assert p.encoding == "utf-8"
    assert p.fileno() == 7
    p.flush()                                 # must not raise


def test_a_stream_without_fileno_does_not_break_the_proxy():
    """pytest's captured stdout has no real fd."""
    class NoFd(io.StringIO):
        def fileno(self): raise io.UnsupportedOperation("no fileno")

    p = telemetry.CountingStream(NoFd())
    with pytest.raises(io.UnsupportedOperation):
        p.fileno()
    p.write("still works")
    assert p.out_bytes == len("still works")


def test_write_returns_what_the_inner_stream_returned():
    inner = io.StringIO()
    p = telemetry.CountingStream(inner)
    assert p.write("abc") == 3


# ── the record ─────────────────────────────────────────────────────────────

def test_log_cli_invocation_records_out_bytes_and_an_estimate(tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    telemetry.log_cli_invocation(
        root, argv=["scan-prompt"], cwd=str(tmp_path), exit_code=0,
        latency_ms=12, error=None, pid=1, out_bytes=4000)
    row = json.loads((root / telemetry.CLI_LOG_NAME).read_text().splitlines()[-1])
    assert row["out_bytes"] == 4000
    assert row["out_tokens_est"] == 1000            # bytes // 4, approximate


def test_out_bytes_is_optional_so_callers_that_do_not_count_still_log(tmp_path):
    root = tmp_path / ".refmatrix"
    root.mkdir()
    telemetry.log_cli_invocation(
        root, argv=["stats"], cwd=str(tmp_path), exit_code=0,
        latency_ms=3, error=None, pid=1)
    row = json.loads((root / telemetry.CLI_LOG_NAME).read_text().splitlines()[-1])
    assert row["out_bytes"] is None
    assert row["out_tokens_est"] is None


# ── cli_entry wiring ───────────────────────────────────────────────────────

def test_cli_entry_installs_and_restores_the_proxy_around_a_normal_run(monkeypatch):
    from refmatrix import cli as cli_mod

    seen: dict = {}
    original = sys.stdout

    def fake_main():
        seen["during"] = sys.stdout
        print("some output")

    monkeypatch.setattr(cli_mod, "main", fake_main)
    # `cli_entry` imports the module locally as `_tel`; `cli.telemetry` is the
    # click COMMAND of that name, so the module is the patch target.
    monkeypatch.setattr(telemetry, "log_cli_invocation",
                        lambda root, **kw: seen.update(kw))
    monkeypatch.setattr(cli_mod, "_reexec_for_fork_safety", lambda: None)

    cli_mod.cli_entry()
    assert isinstance(seen["during"], telemetry.CountingStream)
    assert sys.stdout is original, "stdout was not restored"
    assert seen["out_bytes"] >= len("some output\n")


def test_cli_entry_restores_stdout_even_when_click_exits(monkeypatch):
    """Click raises SystemExit on EVERY run. If restoration lived only on the
    happy path, stdout would stay wrapped for the whole process."""
    from refmatrix import cli as cli_mod

    original = sys.stdout
    seen: dict = {}

    def fake_main():
        print("before exit")
        raise SystemExit(0)

    monkeypatch.setattr(cli_mod, "main", fake_main)
    # `cli_entry` imports the module locally as `_tel`; `cli.telemetry` is the
    # click COMMAND of that name, so the module is the patch target.
    monkeypatch.setattr(telemetry, "log_cli_invocation",
                        lambda root, **kw: seen.update(kw))
    monkeypatch.setattr(cli_mod, "_reexec_for_fork_safety", lambda: None)

    with pytest.raises(SystemExit):
        cli_mod.cli_entry()
    assert sys.stdout is original
    assert seen["out_bytes"] >= len("before exit\n")


def test_a_counting_failure_does_not_fail_the_command(monkeypatch):
    """These logs are diagnostics, not memory."""
    from refmatrix import cli as cli_mod

    original = sys.stdout

    class Exploding(telemetry.CountingStream):
        @property
        def out_bytes(self):
            raise RuntimeError("counter exploded")

    monkeypatch.setattr(telemetry, "CountingStream", Exploding)
    monkeypatch.setattr(cli_mod, "main", lambda: print("ok"))
    monkeypatch.setattr(cli_mod, "_reexec_for_fork_safety", lambda: None)
    # ch-bsd r1 #s-12: without this, cli_entry's finally block calls the REAL
    # logger with _root() -> this project, and 32 pytest runs became rows in
    # the live .refmatrix/cli.log that `rmx telemetry --context` reads.
    monkeypatch.setattr(telemetry, "log_cli_invocation",
                        lambda root, **kw: None)
    # SIBLING: `log_cli_intent` writes a phase:"start" row BEFORE the command
    # body runs, and patching only the end-phase logger left it leaking
    # (ch-bsd r2). Harmless to the report — `phase == "start"` is skipped — but
    # a leak into the live log all the same.
    monkeypatch.setattr(telemetry, "log_cli_intent",
                        lambda root, **kw: None, raising=False)

    cli_mod.cli_entry()                        # must not raise
    assert sys.stdout is original


# ── the report (task 9.3) ──────────────────────────────────────────────────

def _cli_log(tmp_path, rows):
    root = tmp_path / ".refmatrix"
    root.mkdir(exist_ok=True)
    (root / telemetry.CLI_LOG_NAME).write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return root


def _rec(argv, *, out_bytes=None, source="hook", ts="2026-09-15T10:00:00",
         pid=1, legacy=False):
    r = {"ts": ts, "argv": argv, "cwd": "/x", "exit_code": 0,
         "latency_ms": 10, "error": None, "pid": pid, "source": source}
    if not legacy:
        r["out_bytes"] = out_bytes
        r["out_tokens_est"] = (out_bytes // 4) if out_bytes is not None else None
    return r


def test_per_command_totals_and_percentiles_match_hand_computed_values(tmp_path):
    root = _cli_log(tmp_path, [
        _rec(["scan-prompt"], out_bytes=100),
        _rec(["scan-prompt"], out_bytes=300),
        _rec(["scan-prompt"], out_bytes=200),
        _rec(["memory", "recall"], out_bytes=1000),
    ])
    s = telemetry.summarize_context(root)
    assert s["total_bytes"] == 1600
    scan = s["by_command"]["scan-prompt"]
    assert scan["n"] == 3
    assert scan["total_bytes"] == 600
    assert scan["p50_bytes"] == 200
    assert s["by_command"]["memory recall"]["total_bytes"] == 1000


def test_rows_without_out_bytes_are_counted_as_uncounted_not_as_zero(tmp_path):
    """Every row before plan-9 lacks the field. Folding them in as zeros would
    halve every average and make the surface look free."""
    root = _cli_log(tmp_path, [
        _rec(["scan-prompt"], out_bytes=400),
        _rec(["scan-prompt"], legacy=True),
        _rec(["scan-prompt"], legacy=True),
    ])
    s = telemetry.summarize_context(root)
    assert s["uncounted"] == 2
    scan = s["by_command"]["scan-prompt"]
    assert scan["n"] == 1, "legacy rows must not enter the counted set"
    assert scan["mean_bytes"] == 400, "a legacy row averaged in as 0 would give 133"


def test_a_log_that_is_entirely_legacy_reports_nothing_counted(tmp_path):
    root = _cli_log(tmp_path, [_rec(["stats"], legacy=True) for _ in range(5)])
    s = telemetry.summarize_context(root)
    assert s["total_bytes"] == 0
    assert s["uncounted"] == 5
    assert s["by_command"] == {}


def test_the_hook_budget_sums_only_hook_rows_inside_one_window(tmp_path):
    """The number that answers 'what does rmx charge me every turn'."""
    root = _cli_log(tmp_path, [
        _rec(["scan-prompt"], out_bytes=2000, ts="2026-09-15T10:00:00"),
        _rec(["memory", "recall"], out_bytes=3000, ts="2026-09-15T10:00:01"),
        # a human command in the same second must NOT enter the hook budget
        _rec(["context", "foo"], out_bytes=9000, source="interactive",
             ts="2026-09-15T10:00:01"),
        # a later prompt is a different window
        _rec(["scan-prompt"], out_bytes=1000, ts="2026-09-15T10:05:00"),
    ])
    s = telemetry.summarize_context(root, window_s=5)
    assert s["hook_budget"]["windows"] == 2
    assert s["hook_budget"]["p50_bytes"] in (1000, 5000)
    assert s["hook_budget"]["max_bytes"] == 5000
    assert 9000 not in (s["hook_budget"]["max_bytes"],)


def test_the_summary_states_its_grouping_rule(tmp_path):
    """A reader must not have to infer how a 'prompt' was defined."""
    root = _cli_log(tmp_path, [_rec(["scan-prompt"], out_bytes=10)])
    s = telemetry.summarize_context(root, window_s=7)
    assert s["hook_budget"]["window_s"] == 7
    assert "window" in s["hook_budget"]["grouping"].lower()


def test_token_estimates_are_labelled_as_estimates(tmp_path):
    root = _cli_log(tmp_path, [_rec(["scan-prompt"], out_bytes=4000)])
    s = telemetry.summarize_context(root)
    assert s["total_tokens_est"] == 1000
    assert not any(k == "total_tokens" for k in s), "an exact-sounding key would be a lie"


def test_an_absent_cli_log_is_an_empty_report_not_a_crash(tmp_path):
    s = telemetry.summarize_context(tmp_path / ".refmatrix")
    assert s["total_bytes"] == 0 and s["uncounted"] == 0


def test_the_cli_exposes_the_report(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from refmatrix.cli import main as cli_main

    root = _cli_log(tmp_path, [_rec(["scan-prompt"], out_bytes=2048)])
    monkeypatch.setattr("refmatrix.cli._root", lambda: root)
    res = CliRunner().invoke(cli_main, ["telemetry", "--context", "--format", "json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["total_bytes"] == 2048


def test_a_command_is_its_subcommand_path_never_its_arguments(tmp_path):
    """`scan-prompt <the user's whole prompt>` must not become one row per
    prompt: that scatters the highest-volume surface in the product into
    samples of one and makes every percentile meaningless."""
    root = _cli_log(tmp_path, [
        _rec(["scan-prompt", "how does the daemon own the catalog"], out_bytes=100),
        _rec(["scan-prompt", "what is the memory bridge"], out_bytes=300),
        _rec(["scan-prompt", "scan prompt ranking"], out_bytes=200),
    ])
    s = telemetry.summarize_context(root)
    assert list(s["by_command"]) == ["scan-prompt"]
    assert s["by_command"]["scan-prompt"]["n"] == 3
    assert s["by_command"]["scan-prompt"]["p50_bytes"] == 200


def test_a_group_keeps_its_subcommand_but_drops_the_value(tmp_path):
    """`memory recall <query>` is `memory recall`, not `memory recall <query>`."""
    root = _cli_log(tmp_path, [
        _rec(["memory", "recall", "daemon catalog"], out_bytes=10),
        _rec(["memory", "recall", "something else"], out_bytes=20),
        _rec(["memory", "list"], out_bytes=30),
    ])
    s = telemetry.summarize_context(root)
    assert sorted(s["by_command"]) == ["memory list", "memory recall"]
    assert s["by_command"]["memory recall"]["n"] == 2
