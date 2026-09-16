"""ch-bsd r4 remedy — plans 7-10, round 4 (report 2026-09-16-0142).

Every test here is anchored to a finding that was PROVEN on the live corpus or
by a mutation the auditor ran, not to a hypothetical. The through-line of the
whole lineage is in r1's opening line: the tests passed and the command still
died on its first real invocation. So each assertion below reads the surface a
user reads — CLI output, the committed file, the parser the store actually
runs — rather than the helper underneath it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from refmatrix import brief
from refmatrix.cli import main as cli_main
from refmatrix.store import Store

from click.testing import CliRunner

pytest.importorskip("lance")

REPO = Path(__file__).resolve().parents[1]
PART = "memory-proj"


@pytest.fixture(autouse=True)
def _no_live_cli_log(monkeypatch):
    """`_memory_intent` writes a row to the REAL `.refmatrix/cli.log`.

    Not cosmetic: r3 #m-5 was a test suite appending to the live telemetry the
    context-cost report is computed from.
    """
    from refmatrix import telemetry
    monkeypatch.setattr(telemetry, "log_cli_intent", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr(telemetry, "log_cli_invocation", lambda *a, **k: None,
                        raising=False)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_BACKEND", "sqlite")
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    yield s
    s.close()


# ── #b-1-r4: render_gmd(stats=) had no production caller ───────────────────

def _fake_brief_payload(root, action, **kw):
    """The daemon's real shape, INCLUDING `stats.memories`.

    The r3 fake omitted `names` and the rich-markup defect had nothing to eat.
    This one carries the COUNT, because the fake that drops the field under
    test proves nothing — the same lesson, one field over (ch-bsd r4 #b-1-r4).
    """
    return {"briefs": [{"class": "singleton", "label": "x", "finding": "f",
                        "evidence": [1], "detail": {},
                        "mtype": "brief/singleton"}],
            "names": {"1": "note-one"},
            "stats": {"skipped": 0, "briefs": 1, "partition": "p",
                      "memories": 5}}


def test_cli_gmd_headline_carries_the_memory_count(monkeypatch):
    """`--json` said 243 and `--gmd` said "an unrecorded number of" — on the
    same store, in the same command. The GMD one is the surface that becomes a
    node in the graph (ch-bsd r4 #b-1-r4)."""
    from refmatrix import verbs
    monkeypatch.setattr(verbs, "memory", _fake_brief_payload)
    res = CliRunner().invoke(cli_main, ["memory", "brief", "--gmd"])
    assert res.exit_code == 0, res.output + str(res.exception)
    assert "over 5 memories" in res.output, res.output
    assert "an unrecorded number of" not in res.output, res.output


def test_gmd_fallback_still_fires_when_the_count_is_genuinely_absent():
    """The honest-fallback string is not deleted — it is restored to meaning
    what it says. It must fire when, and only when, the count is unknown."""
    wire = [{"class": "singleton", "label": "x", "finding": "f",
             "evidence": [1], "detail": {}, "mtype": "brief/singleton"}]
    out = brief.render_gmd(wire, names={1: "note-one"}, stats={})
    assert "an unrecorded number of memories" in out


# ── #b-2-r4: the fixing commit deleted a graph node ────────────────────────

GMD_DOCS_OUTSIDE_LINT_SCOPE = [
    REPO / "eval" / "production" / "longmemeval" / "REPORT.md",
]


@pytest.mark.parametrize("doc", GMD_DOCS_OUTSIDE_LINT_SCOPE,
                         ids=lambda p: p.name)
def test_committed_gmd_doc_has_balanced_fences(doc):
    """An odd fence count silently swallows every heading after it. `eval/` is
    a corpus root, so the doc IS ingested — and no gate linted it (#b-2-r4)."""
    fences = [ln for ln in doc.read_text().splitlines()
              if re.match(r"^\s*```", ln)]
    assert len(fences) % 2 == 0, (
        f"{doc.name} has {len(fences)} code fences; an odd count puts every "
        f"heading after the last one inside a code block")


def test_report_next_node_is_visible_to_the_stores_own_parser():
    """Proven by the auditor with this exact parser: `next` was in the anchor
    set at 4f451c5 and gone at 05bef34 (#b-2-r4)."""
    from refmatrix.ingest_gmd import parse_gmd
    doc = parse_gmd(REPO / "eval" / "production" / "longmemeval" / "REPORT.md")
    assert doc is not None, "REPORT.md carries gmd: frontmatter"
    anchors = {n.id for n in doc.nodes}
    assert "next" in anchors, sorted(anchors)


def test_lint_scope_covers_every_corpus_root_carrying_gmd():
    """`eval/` holds a `gmd: "0.1"` doc with four `rel:` edges and was never
    linted. A gate that cannot see a file cannot gate it (#b-2-r4)."""
    scope_line = next(
        ln for ln in (REPO / "scripts" / "lint-gmd.sh").read_text().splitlines()
        if ln.startswith("SCOPE="))
    assert "eval/" in scope_line, scope_line


def test_linter_reports_an_unbalanced_fence(tmp_path):
    """r3: "a linter that only reports malformed constructs cannot report
    absent ones". An odd fence count is the one-line assertion that would have
    caught #b-2-r4, so the linter now makes it (#b-2-r4)."""
    doc = tmp_path / "broken.md"
    doc.write_text(
        '---\ngmd: "0.1"\nid: broken\ntitle: "Broken"\ntags: [t]\n---\n\n'
        '# Broken {#root}\n\n```\nfenced\n```\n\n```\n\n'
        '## Swallowed {#swallowed}\n\ntext\n')
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "gmd" / "lint.py"), str(doc)],
        capture_output=True, text=True)
    assert out.returncode != 0, out.stdout + out.stderr
    assert "fence" in (out.stdout + out.stderr).lower(), out.stdout + out.stderr


# ── #s-1-r4: the `memory compile --out -` sibling has no CLI test at all ───

def _fake_plan():
    return {
        "params": {"signal": "fused"},
        "stats": {"partition": "p", "candidates": 2, "embedded": 2,
                  "concept_space": 1, "edges": 1, "confirmed": 1,
                  "bridges": 0, "unembedded": 0},
        "clusters": [{
            "label": "daemon", "size": 2,
            "evidence": [{"concept": "daemon", "lift": 2.0, "df_in": 2}],
            "members": [{"name": "note-one", "mtype": "project"},
                        {"name": "note-two", "mtype": "project"}],
        }],
        "crosscutting": [],
        "unclustered": [],
    }


def test_cli_memory_compile_out_dash_keeps_its_wikilinks(monkeypatch):
    """The brief site got the `click.echo` fix AND three assertions; the
    compile sibling got the fix and nothing. Reverting it to `console.print`
    left 95 tests green (mutation M2, ch-bsd r4 #s-1-r4)."""
    from refmatrix import cli as cli_mod
    from refmatrix import consolidate
    from refmatrix import daemon as daemon_mod

    plan = _fake_plan()
    monkeypatch.setattr(consolidate, "compile_memories",
                        lambda *a, **k: plan)
    monkeypatch.setattr(consolidate, "apply_plan",
                        lambda *a, **k: {"subjects": [1], "linked": 2,
                                         "unlinked": 0})
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **k: False)
    monkeypatch.setattr(cli_mod, "_read_store", lambda *a, **k: object())
    monkeypatch.setattr(cli_mod, "_store", lambda *a, **k: object())

    res = CliRunner().invoke(
        cli_main, ["memory", "compile", "--apply", "--out", "-"])
    assert res.exit_code == 0, res.output + str(res.exception)
    assert "[[note-one]]" in res.output, res.output
    assert "rel: catalogs -> [[note-two]]" in res.output, res.output
    assert "-> []" not in res.output, "rich ate the wikilink"


# ── #s-2-r4: skipped_by does not cover the detector that skips ─────────────

def test_skipped_by_accounts_for_every_skip(store):
    """`sum(skipped_by.values()) == skipped` is the whole point of the
    breakdown and nothing asserted it. When `singleton` skipped, the CLI
    printed a literal `(?)` — the fourth wording of that sentence and the
    first that does not attempt an explanation (#s-2-r4)."""
    with store.with_partition(PART):
        store.add_memory("kept", "a daemon note", mtype="project")
        plan = {"clusters": [], "crosscutting": [],
                "unclustered": ["kept", "vanished-one", "vanished-two"],
                "stats": {"partition": PART}, "params": {}}
        res = brief.compile_briefs(
            store, classes=["singleton"], plan=plan)
    stats = res["stats"]
    assert stats["skipped"] == 2, stats
    assert sum(stats["skipped_by"].values()) == stats["skipped"], stats


def test_cli_never_prints_a_bare_question_mark_for_skips(monkeypatch):
    """What the user saw: `2 row(s) skipped (?) — counted, not dropped`."""
    from refmatrix import verbs

    def _payload(root, action, **kw):
        return {"briefs": [], "names": {},
                "stats": {"skipped": 2, "briefs": 0, "partition": "p",
                          "memories": 3,
                          "skipped_by": {"singleton_unresolved": 2}}}

    monkeypatch.setattr(verbs, "memory", _payload)
    res = CliRunner().invoke(cli_main, ["memory", "brief"])
    assert res.exit_code == 0, res.output + str(res.exception)
    assert "(?)" not in res.output, res.output
    assert "singleton_unresolved=2" in res.output, res.output


# ── #s-3-r4: the bucket carrying 51/51 of real drops has no assertion ──────

def test_workflow_authored_bucket_counts_what_it_drops(store):
    """On the live replica this bucket is 51 of 51 skips and the suite could
    delete it green (mutation M3). The two assertions that existed covered the
    bucket that is always ZERO in production (#s-3-r4)."""
    with store.with_partition(PART):
        a = store.add_concept("bsd-pattern-partial-bound#cause")
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        _, skipped, why = brief.contradicted(store, count_skips=True)
    assert skipped == 1, why
    assert why == {"workflow_authored": 1}, why


def test_operational_bucket_counts_what_it_drops(store):
    """The sibling bucket, same shape. Both were deletable with a green
    suite; neither is now (#s-3-r4)."""
    op_name = "session-2026-09-16"
    assert brief.OPERATIONAL_RE.match(op_name), "fixture must hit the bucket"
    with store.with_partition(PART):
        a = store.add_concept(op_name)
        b = store.add_concept("adr-0087#zone-class")
        store.link("contradicts", a, b)
        _, skipped, why = brief.contradicted(store, count_skips=True)
    assert skipped == 1, why
    assert why == {"operational": 1}, why


# ── #m-4-r4: inspect.getsource makes the suite non-hermetic ────────────────

def test_no_test_reinterprets_a_loaded_code_object_against_an_edited_file():
    """`inspect.getsource` slices the CURRENT file with an ALREADY-LOADED code
    object's `co_firstlineno`. Edit `src/` mid-suite — this workflow's normal
    state — and the assertion reads lines from an unrelated function and fails
    with no hint why. That cost a handoff section and a round of audit time
    (ch-bsd r4 #m-4-r4, and it is what produced the phantom 6th failure)."""
    offenders = [
        p.name for p in sorted((REPO / "tests").glob("test_*.py"))
        if p.name != Path(__file__).name and "inspect.getsource(" in p.read_text()
    ]
    assert offenders == [], (
        f"{offenders} assert on inspect.getsource; snapshot the module source "
        f"at import (Path(mod.__file__).read_text()) or assert on behaviour")


def test_this_guard_names_the_mechanism_it_replaces():
    """Snapshotting at module import is the fix, so prove the replacement
    reads the whole file rather than a stale slice."""
    import refmatrix.daemon as dm
    src = Path(dm.__file__).read_text()
    assert "def serve_foreground" in src
    assert len(src.splitlines()) > 100
