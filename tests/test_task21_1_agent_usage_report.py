"""Task 21.1 RED: R5's ONE row classifier and R7's `rmx telemetry --agent-usage` report.

AC-6 (the frozen fixture + a synthetic companion proving its mechanisms) and AC-7 (the
classifier: five query.log rows, the unit cases, the event leg, the import/no-check test).

Every test runs inside task 23.0's sandbox (the per-test `REFMATRIX_ROOT` is a store under
`/private/tmp/rmx-*`, i.e. R5's sandbox test base) and ends by asserting the live logs did not
move (the AC preamble; `os.stat` only, see tests/task21_1_support.py).
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import telemetry
from refmatrix.cli import main
from tests import task21_1_support as h

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "agent_usage"
PYTEST_A = "/private/var/folders/x/pytest-of-u/pytest-7/test_a0"
PYTEST_B = "/private/var/folders/x/pytest-of-u/pytest-7/test_b0"
LIVE_ROOT = "/Users/x/proj/.refmatrix"


@pytest.fixture(autouse=True)
def _guard(monkeypatch):
    for k in h.CLAUDE_ENV:
        monkeypatch.delenv(k, raising=False)
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


@pytest.fixture
def R() -> Path:
    """The reader's store root: the per-test sandbox store (`/private/tmp/rmx-*/r/N/...`)."""
    r = Path(os.environ["REFMATRIX_ROOT"])
    assert "/tmp/rmx-" in str(r), r
    return r


def _need(name: str) -> None:
    assert hasattr(telemetry, name), f"R5: telemetry.{name} is not built"


def _prov(row, **kw):
    _need("row_provenance")
    return telemetry.row_provenance(row, **kw)


def _report(*args) -> "tuple[int, str]":
    r = CliRunner().invoke(main, ["telemetry", "--agent-usage", *args])
    return r.exit_code, r.output


def _write_jsonl(path: Path, rows, extra_lines=()) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
        for ln in extra_lines:
            f.write(ln + "\n")


def _grep_row(**kw) -> dict:
    row = {"ts": "2026-10-15T10:00:00", "kind": "grep", "body": "foo", "source": "grep-replica",
           "invocation": "unknown", "cardinality": 1, "latency_ms": 3, "outcome": "ok",
           "error": None, "answered_by": "floor"}
    row.update(kw)
    return row


def _five_rows(R: Path) -> list[dict]:
    """AC-7's (a)-(e). (b)'s cwd/root are inside R's project."""
    a = _grep_row(body="a-row", cwd=PYTEST_A, root=PYTEST_A + "/.refmatrix")
    b = _grep_row(body="b-row", cwd=str(R.parent), root=str(R))
    c = _grep_row(body="foo")
    d = _grep_row(body="alpha|beta")
    e = _grep_row(body="alpha")
    return [a, b, c, d, e]


def _line_with(out: str, *needles: str) -> list[str]:
    return [ln for ln in out.splitlines() if all(n in ln for n in needles)]


# ---- AC-7: the report over five rows ----------------------------------------------------------

def test_ac7_report_counts_b_c_e_and_prints_the_three_exclusion_counts(R):
    """AC-7: on a sandbox store R, five query.log rows -> the report counts 3 (b, c, e) and
    prints `excluded_test_rows=1 legacy_fixture_rows=1 legacy_unattributed=2`. The count is
    matched tolerantly (the spec fixes no per-source line format): a `grep-replica` line holding
    the number 3 as a word."""
    _need("row_provenance")
    _write_jsonl(R / "query.log", _five_rows(R))
    code, out = _report()
    assert "excluded_test_rows=1 legacy_fixture_rows=1 legacy_unattributed=2" in out, out
    hits = [ln for ln in _line_with(out, "grep-replica") if re.search(r"\b3\b", ln)]
    assert hits, f"no grep-replica line counting 3 (b, c, e):\n{out}"
    assert not [ln for ln in _line_with(out, "grep-replica") if re.search(r"\b5\b", ln)], out
    assert code == 0, out


# ---- AC-7: row_provenance unit cases ----------------------------------------------------------

def test_ac7_the_five_rows_classify_as_the_spec_lists(R):
    """AC-7 (a)-(e) through row_provenance with reader_root=R."""
    a, b, c, d, e = _five_rows(R)
    got = [_prov(r, reader_root=R) for r in (a, b, c, d, e)]
    assert got == ["test_artifact", "attributed", "legacy_unattributed", "legacy_fixture",
                   "legacy_unattributed"], got


@pytest.mark.parametrize("body", ["alpha", "alpha|GAMMA", "alpha.beta", "alpha|beta "])
def test_ac7_d9g_shape_is_exact_string_equality(R, body):
    """AC-7 / R5 class 2: only `body == "alpha|beta"` exactly is a legacy fixture row."""
    assert _prov(_grep_row(body=body), reader_root=R) == "legacy_unattributed"


def test_ac7_d9g_shape_needs_kind_grep(R):
    """R5 class 2: `kind == "grep"` is part of the shape."""
    assert _prov(_grep_row(body="alpha|beta", kind="context"), reader_root=R) \
        == "legacy_unattributed"


def test_ac7_another_sandbox_is_a_test_artifact_for_R_and_for_a_live_reader(R):
    """AC-7: a row whose root is ANOTHER /tmp/rmx-* sandbox is test_artifact for a reader at R
    and for a reader at a non-temp root."""
    other = "/private/tmp/rmx-zzother9/r/1/.refmatrix"
    row = _grep_row(cwd=str(Path(other).parent), root=other)
    assert _prov(row, reader_root=R) == "test_artifact"
    assert _prov(row, reader_root=Path(LIVE_ROOT)) == "test_artifact"
    assert _prov(row) == "test_artifact"          # reader_root=None: a live reader


def test_ac7_own_sandbox_row_is_attributed_for_R(R):
    """AC-7 (mutation: reader_root ignored -> a sandbox reader drops its own rows)."""
    row = _grep_row(cwd=str(R.parent), root=str(R))
    assert _prov(row, reader_root=R) == "attributed"


def test_ac7_a_sibling_store_in_R_s_own_sandbox_is_attributed(R):
    """AC-7: the test base of R is its `/tmp/rmx-*` dir, so another store under the SAME
    sandbox root shares the base and is attributed for a reader at R."""
    sandbox = Path(str(R).split("/r/", 1)[0])
    sib = sandbox / "r" / "999" / ".refmatrix"
    row = _grep_row(cwd=str(sib.parent), root=str(sib))
    assert _prov(row, reader_root=R) == "attributed"


def test_ac7_two_test_bases_keyed_on_root_not_cwd(R):
    """AC-7 two-test-base cases (round-3 #s-3; mutation: classifier keyed on cwd)."""
    in_r = _grep_row(cwd=PYTEST_B, root=str(R))
    assert _prov(in_r, reader_root=R) == "attributed"
    from_repo = _grep_row(cwd=str(REPO), root=str(R))
    assert _prov(from_repo, reader_root=R) == "attributed"
    pytest_root = _grep_row(cwd=str(R.parent), root=PYTEST_A + "/.refmatrix")
    assert _prov(pytest_root, reader_root=R) == "test_artifact"


def test_ac7_cwd_is_the_key_only_without_root(R):
    """AC-7 cwd fallback: cwd in pytest temp and no root -> test_artifact for a reader at R."""
    row = _grep_row(cwd=PYTEST_A)
    assert _prov(row, reader_root=R) == "test_artifact"


def test_ac7_a_live_tree_row_is_never_a_test_artifact(R):
    """AC-7 live-tree case (mutation: a base-None row classified test_artifact)."""
    row = _grep_row(cwd="/Users/x/proj", root=LIVE_ROOT)
    assert _prov(row, reader_root=R) == "attributed"
    _need("is_test_artifact_row")
    assert telemetry.is_test_artifact_row(row, reader_root=R) is False


def test_ac7_is_test_artifact_row_default_call_is_23_0_s_call(R):
    """R5 / 23.0 AC-4: `telemetry.is_test_artifact_row(row)` is valid as written (reader_root
    and source default) and equals `row_provenance(row) == "test_artifact"`."""
    _need("is_test_artifact_row")
    a = _grep_row(cwd=PYTEST_A, root=PYTEST_A + "/.refmatrix")
    live = _grep_row(cwd="/Users/x/proj", root=LIVE_ROOT)
    assert telemetry.is_test_artifact_row(a) is True
    assert telemetry.is_test_artifact_row(live) is False
    assert telemetry.is_test_artifact_row(_grep_row(body="alpha|beta")) is False


def test_ac7_malformed_is_only_for_events(R):
    """R5 class 0 applies to `source="events"` only: a query.log row is never `malformed`."""
    row = _grep_row(channel="cli")
    assert _prov(row, reader_root=R) == "legacy_unattributed"


# ---- AC-7: the event leg ----------------------------------------------------------------------

def _event(**kw) -> dict:
    ev = {"v": 1, "ts": "2026-10-15T10:00:00.000Z", "session": "s1", "turn": 0,
          "query_id": "q" * 32, "channel": "prompt_recall", "invocation": "hook",
          "name": "feedback_alpha_rule", "entity_id": 7, "kind": "memory", "scope": "project",
          "partition": "intuition", "rank": 1, "stage": "delivered"}
    ev.update(kw)
    return ev


def _seven_events(R: Path) -> list[dict]:
    """AC-7 event leg: a-e as events (c-e stripped of cwd/root), f channel=cli, g legacy ts."""
    a = _event(name="a", cwd=PYTEST_A, root=PYTEST_A + "/.refmatrix")
    b = _event(name="b", cwd=str(R.parent), root=str(R))
    c = _event(name="foo")
    d = _event(name="alpha|beta")
    e = _event(name="alpha")
    f = _event(name="f", channel="cli", cwd=str(R.parent), root=str(R))
    g = _event(name="g", ts="2026-10-14T14:04:41", cwd=str(R.parent), root=str(R))
    return [a, b, c, d, e, f, g]


def test_ac7_event_leg_classes(R):
    """AC-7 event leg: c-g are malformed, a test_artifact, b attributed (mutations: the
    channel-enum check dropped -> f folded; ts in local naive form -> g folded)."""
    evs = _seven_events(R)
    got = [_prov(ev, reader_root=R, source="events") for ev in evs]
    assert got == ["test_artifact", "attributed", "malformed", "malformed", "malformed",
                   "malformed", "malformed"], got


@pytest.mark.parametrize("missing", ["v", "stage", "name", "channel", "cwd", "root", "ts"])
def test_ac7_event_missing_a_required_field_is_malformed(R, missing):
    """R5 class 0: any of v, stage, name, channel, cwd, root, ts absent -> malformed."""
    ev = _event(cwd=str(R.parent), root=str(R))
    del ev[missing]
    assert _prov(ev, reader_root=R, source="events") == "malformed"


@pytest.mark.parametrize("bad", [{"v": 2}, {"channel": "mcp"}, {"ts": "2026-10-15T10:00:00Z"},
                                 {"ts": "2026-10-15T10:00:00.000+00:00"}])
def test_ac7_event_wrong_version_channel_or_ts_form_is_malformed(R, bad):
    """R5 class 0: v != 1, a channel outside R10's enum, a ts not `YYYY-MM-DDTHH:MM:SS.mmmZ`."""
    ev = _event(cwd=str(R.parent), root=str(R), **bad)
    assert _prov(ev, reader_root=R, source="events") == "malformed"


def test_ac7_event_reader_prints_malformed_and_unparseable(R):
    """AC-7 event leg through the report: `malformed=5 unparseable=1` (one garbage line added),
    and only b folds (the other attributed-looking events are a test artifact or malformed)."""
    _need("row_provenance")
    _write_jsonl(R / "recall-events.jsonl", _seven_events(R), extra_lines=["{not json"])
    code, out = _report()
    assert "malformed=5 unparseable=1" in out, out
    assert code == 0, out


# ---- AC-7: no reader carries its own copy of the predicate -------------------------------------

_CHANNELS = {"session_start", "prompt_recall", "scan_prompt", "precompact", "context", "recall",
             "nudge"}


def _reader_modules() -> list[Path]:
    """Every module that reads query.log / recall-events.jsonl for a report or fold: the
    --agent-usage report (wherever it lives), 19.2's fold module and 21.4's draw script. 19.2
    and 21.4 are not built at this HEAD; the globs pick them up once they exist."""
    out = []
    for p in sorted((REPO / "src" / "refmatrix").glob("*.py")):
        txt = p.read_text()
        if "agent_usage" in txt or "agent-usage" in txt or "recall-events.jsonl" in txt:
            out.append(p)
    for pat in ("src/refmatrix/*fold*.py", "eval/**/*fold*.py", "eval/**/*draw*.py",
                "scripts/*draw*.py"):
        out.extend(sorted(REPO.glob(pat)))
    return sorted(set(out))


def _offending_literals(path: Path, allowed_funcs: set[str]) -> list[str]:
    tree = ast.parse(path.read_text())
    bad = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def _allowed(self):
            return any(f in allowed_funcs for f in self.stack)

        def visit_Constant(self, node):
            if isinstance(node.value, str) and not self._allowed():
                if any(lit in node.value for lit in ("pytest-of-", "/tmp/rmx-")):
                    bad.append(f"{path.name}:{node.lineno} {node.value!r}")

        def _collection(self, node):
            vals = {e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if len(vals & _CHANNELS) >= 5 and not self._allowed():
                bad.append(f"{path.name}:{node.lineno} channel enum {sorted(vals)}")
            if {"cwd", "root"} <= vals and not self._allowed():
                bad.append(f"{path.name}:{node.lineno} cwd/root presence check {sorted(vals)}")
            self.generic_visit(node)

        visit_Tuple = visit_List = visit_Set = _collection

    V().visit(tree)
    return bad


def test_ac7_every_reader_imports_row_provenance_and_owns_no_predicate():
    """AC-7 (mutations: each reader given its own copy of the predicate; the `malformed` rule
    moved out of row_provenance into a reader). Every reader module imports/calls
    `row_provenance` from telemetry and holds no test-base literal, no channel-enum collection
    and no cwd/root presence check of its own. In telemetry.py itself only row_provenance and
    its test-base helper may hold them (the channel enum's ONE definition, a module-level
    constant, is allowed). 19.2's fold module and 21.4's draw script do not exist yet: they are
    checked when the globs find them."""
    _need("row_provenance")
    readers = _reader_modules()
    report = [p for p in readers if "agent_usage" in p.read_text()
              or "agent-usage" in p.read_text()]
    assert report, "R7: no module implements --agent-usage"
    tel = REPO / "src" / "refmatrix" / "telemetry.py"
    problems = []
    for p in readers:
        txt = p.read_text()
        if p != tel:
            if "row_provenance" not in txt and "is_test_artifact_row" not in txt:
                problems.append(f"{p.name}: reads the logs but never calls row_provenance")
            problems += _offending_literals(p, allowed_funcs=set())
        else:
            allowed = {"row_provenance", "is_test_artifact_row"} | {
                n.name for n in ast.walk(ast.parse(txt))
                if isinstance(n, ast.FunctionDef) and "test_base" in n.name}
            # module-level constants (the enum's ONE definition) are not inside a function:
            tree = ast.parse(txt)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name not in allowed:
                    seg = ast.get_source_segment(txt, node) or ""
                    for lit in ("pytest-of-", "/tmp/rmx-"):
                        if lit in seg:
                            problems.append(f"telemetry.{node.name} holds {lit!r}")
    assert not problems, problems


def test_ac7_the_bypass_check_can_fail(tmp_path):
    """AC-7 control: the literal scan reports a planted private predicate (so the check above
    cannot pass vacuously)."""
    planted = tmp_path / "planted_reader.py"
    planted.write_text(
        "CH = ('session_start', 'prompt_recall', 'scan_prompt', 'precompact', 'context')\n"
        "def mine(row):\n"
        "    return '/pytest-of-' in row.get('cwd', '') or not {'cwd', 'root'} <= set(row)\n")
    bad = _offending_literals(planted, allowed_funcs=set())
    assert len(bad) == 3, bad


# ---- AC-6: the frozen fixture -----------------------------------------------------------------

def test_ac6_frozen_fixture_prints_the_exact_counts(R):
    """AC-6. BLOCKED, not RED, while the fixture is absent: the RED-phase agent was refused a
    read of the live project logs (2026-10-16), so `tools/cut_agent_usage_fixture.py` must be
    run by the user to commit tests/fixtures/agent_usage/{query.log,cli.log,manifest.json}.
    With the fixture: `--since 2026-09-23 --until 2026-10-07T11:06:35` prints EXACTLY 3
    context calls (context-replica), 1,119 grep-replica greps, 34 memory recalls (not 68:
    phase=start excluded) and `excluded_test_rows=0 legacy_fixture_rows=0
    legacy_unattributed=<L>` (L from the manifest). Count lines matched tolerantly (the spec
    fixes no per-route format): a line naming the surface and holding the number as a word."""
    manifest = FIXTURE / "manifest.json"
    assert manifest.is_file(), (
        "AC-6 BLOCKED: the redacted fixture is not committed; run "
        "`python3 tools/cut_agent_usage_fixture.py` (reads this project's .refmatrix logs, "
        "writes tests/fixtures/agent_usage/)")
    L = json.loads(manifest.read_text())["L"]
    for name in ("query.log", "cli.log"):
        (R / name).write_bytes((FIXTURE / name).read_bytes())
    code, out = _report("--since", "2026-09-23", "--until", "2026-10-07T11:06:35")
    assert f"excluded_test_rows=0 legacy_fixture_rows=0 legacy_unattributed={L}" in out, out
    assert [ln for ln in _line_with(out, "context-replica") if re.search(r"\b3\b", ln)], out
    assert [ln for ln in _line_with(out, "grep-replica")
            if re.search(r"\b1,?119\b", ln)], out
    rec = [ln for ln in out.splitlines() if "recall" in ln.lower()]
    assert [ln for ln in rec if re.search(r"\b34\b", ln)], out
    assert not [ln for ln in rec if re.search(r"\b68\b", ln)], out
    assert code == 0, out


def _cli_row(ts, argv, *, phase=None, source="unknown"):
    if phase == "start":
        return {"ts": ts, "phase": "start", "op": "recall", "argv": argv, "pid": 1,
                "source": source}
    return {"ts": ts, "argv": argv, "cwd": "/Users/x/proj", "exit_code": 0, "latency_ms": 40,
            "outcome": "ok", "error": None, "pid": 1, "source": source, "out_bytes": 10,
            "out_tokens_est": 2}


def test_ac6_synthetic_mechanisms_window_phase_start_and_legacy_counts(R):
    """AC-6 companion (RED at HEAD: --agent-usage does not parse). A hand-built legacy store:
    query.log holds 2 context-replica + 3 grep-replica rows inside the window, one
    context-replica row before --since and one grep-replica row after --until; cli.log holds
    4 `memory recall` end rows inside the window, EACH with its phase=start intent row, plus
    one pair after --until. The report prints context-replica 2, grep-replica 3, recalls 4 (not
    8: phase=start excluded; not 5: windowed) and `excluded_test_rows=0 legacy_fixture_rows=0
    legacy_unattributed=5` (the five in-window legacy query.log rows, counted, not dropped:
    mutation "legacy rule flipped to EXCLUDE")."""
    q = [
        {"ts": "2026-09-20T09:00:00", "kind": "context", "body": "x", "source": "context-replica",
         "invocation": "unknown", "cardinality": 1, "latency_ms": 5, "error": None},
        {"ts": "2026-09-24T09:00:00", "kind": "context", "body": "y", "source": "context-replica",
         "invocation": "unknown", "cardinality": 1, "latency_ms": 5, "error": None},
        {"ts": "2026-10-01T09:00:00", "kind": "context", "body": "z", "source": "context-replica",
         "invocation": "unknown", "cardinality": 1, "latency_ms": 7, "error": None},
    ]
    for i in range(3):
        q.append({"ts": f"2026-10-0{2 + i}T09:00:00", "kind": "grep", "body": f"g{i}",
                  "source": "grep-replica", "invocation": "unknown", "cardinality": 2,
                  "latency_ms": 9, "error": None})
    q.append({"ts": "2026-10-07T11:07:00", "kind": "grep", "body": "late",
              "source": "grep-replica", "invocation": "unknown", "cardinality": 2,
              "latency_ms": 9, "error": None})
    cli = []
    for i in range(4):
        ts = f"2026-10-0{1 + i}T10:00:00"
        argv = ["memory", "recall", "--stdin-json", "--k", "5"]
        cli += [_cli_row(ts, argv, phase="start"), _cli_row(ts, argv)]
    cli += [_cli_row("2026-10-07T11:07:05", ["memory", "recall", "q"], phase="start"),
            _cli_row("2026-10-07T11:07:05", ["memory", "recall", "q"])]
    _write_jsonl(R / "query.log", q)
    _write_jsonl(R / "cli.log", cli)
    code, out = _report("--since", "2026-09-23", "--until", "2026-10-07T11:06:35")
    assert "excluded_test_rows=0 legacy_fixture_rows=0 legacy_unattributed=5" in out, out
    assert [ln for ln in _line_with(out, "context-replica") if re.search(r"\b2\b", ln)], out
    assert not [ln for ln in _line_with(out, "context-replica") if re.search(r"\b3\b", ln)], out
    assert [ln for ln in _line_with(out, "grep-replica") if re.search(r"\b3\b", ln)], out
    assert not [ln for ln in _line_with(out, "grep-replica") if re.search(r"\b4\b", ln)], out
    rec = [ln for ln in out.splitlines() if "recall" in ln.lower()]
    assert [ln for ln in rec if re.search(r"\b4\b", ln)], out
    assert not [ln for ln in rec if re.search(r"\b[58]\b", ln)], out
    assert code == 0, out
