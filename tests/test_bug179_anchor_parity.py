"""bug-179 — lint and the store ingester must agree on what a block anchor IS.

On 2026-11-09 commit `efa5f33` packed 200 former-anchor ids onto 12 lines of
`workflow/bullshit/IMPRESSIONS.md` (7-30 per line) to fit a 50-line cap.
`tools/gmd/lint.py` registers EVERY `{#id}` on a line and passed with 0 errors;
`parse_gmd` registers only the first, so 188 ids resolved to `(unknown symbol)`.
It is the second time the two parsers disagreed (bug-036 was the first), and
the one-file parity test bug-036 left behind never runs on a docs-only commit.

Spec: workflow/plans/task-bug179-lint-ingest-anchor-parity.md (R1-R7, AC-1..11).

What this file pins:
  * R1  more than one block id on a line is a lint ERROR; only the first registers.
  * R2  a `{#id}` on ANY `rel:`-prefixed line is a lint ERROR and registers in
        neither tool (well-formed or malformed).
  * R3  the ingester (and upstream `slice.py`) read a heading's anchor past inline
        code, and cut only that span out of the title.
  * R3b inline code is a CommonMark backtick RUN in every parser.
  * R5  corpus-wide parity via `scripts/check-gmd-parity.py`, run by
        `scripts/lint-gmd.sh` — exercised through the REAL shell script (AC-10).

THE FIXTURES QUOTING DOUBLE/TRIPLE BACKTICK SPANS LIVE ONLY HERE, as string
literals (AC-3b): a GMD doc quoting one trips the very bug it tests.

Upstream location: the canonical GMD repo is `~/claude_tools/gmd`. Set
`GMD_UPSTREAM=<path>` to point these tests at another checkout (an isolated
clone during development). A missing upstream FAILS — it is never skipped.
"""

from __future__ import annotations

import importlib.util
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from refmatrix.ingest_gmd import parse_gmd

REPO = Path(__file__).resolve().parents[1]
LINT = REPO / "tools" / "gmd" / "lint.py"
SLICE = REPO / "tools" / "gmd" / "slice.py"
PARITY = REPO / "scripts" / "check-gmd-parity.py"
LINT_GMD_SH = REPO / "scripts" / "lint-gmd.sh"
# The default is the REAL user's checkout, read from the password database: task 23.0's
# sandbox replaces HOME with a decoy before this module imports, so `Path.home()` would name
# a path that never exists and every AC-8/AC-11 test would fail in a normal suite run
# (found at the bug-179 merge, 2026-11-09).
_REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
UPSTREAM = Path(os.environ.get("GMD_UPSTREAM",
                               str(_REAL_HOME / "claude_tools" / "gmd"))).expanduser()

# The base the spec measures against (AC-6/AC-9). Its vendored lint is the
# pre-bug-179 linter: it registers every id on a line and every id on a rel:
# line — i.e. R1 and R2 reverted. AC-10 uses it as the planted mutant.
BASE_SHA = "9901589"
INCIDENT_SHA = "efa5f33"

SCOPE = ["CLAUDE.md", "docs", "workflow", "eval", ".claude/PROJECT_PROFILE.md"]
AUTO_ID = re.compile(r"^_h\d+(?:_\d+)?$")
# Spec R3b's reference matcher, used ONLY by the data scan below (AC-5b) so that
# scan does not borrow the linter's stripper it is checking.
CM_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
ANCHOR = re.compile(r"\{#([a-z0-9][a-z0-9._/-]*)([^}]*)\}")

HEAD = '---\ngmd: "0.1"\nid: fx\ntitle: "Fx"\ntags: [t]\n---\n\n# Fx {#root}\n\n'


# ---------------------------------------------------------------- helpers

def _load(name: str, path: Path):
    assert path.is_file(), f"{path} is missing"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


def _lint_mod():
    return _load("_b179_lint", LINT)


def _slice_mod():
    return _load("_b179_slice", SLICE)


def _parity_mod():
    assert PARITY.is_file(), (
        f"{PARITY.relative_to(REPO)} does not exist — R5 puts the corpus parity "
        "check there (spec #d6)")
    return _load("_b179_parity", PARITY)


def _doc(tmp_path: Path, body: str, name: str = "fx.md") -> Path:
    p = tmp_path / name
    p.write_text(HEAD + body)
    return p


def _lint_ids(path: Path) -> set[str]:
    d, _ = _lint_mod().parse_doc(path)
    return set(d.node_ids)


def _ingest_ids(path: Path) -> set[str]:
    return {n.id for n in parse_gmd(path).nodes
            if n.id != "__root__" and not AUTO_ID.match(n.id)}


def _run_lint(*targets: Path | str, lint: Path = LINT, cwd: Path = REPO):
    p = subprocess.run([sys.executable, str(lint), *map(str, targets)],
                       capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def _memdir(root: Path) -> Path:
    """The memory dir `scripts/lint-gmd.sh` adds to its scope, computed the
    same way (`tr '/_' '--'` over ROOT)."""
    slug = str(root).replace("/", "-").replace("_", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


def _scope_paths() -> tuple[list[Path], list[Path]]:
    paths = [REPO / s for s in SCOPE]
    mem = _memdir(REPO)
    return paths, ([mem] if mem.is_dir() else [])


def _error_texts(out: str) -> set[str]:
    return {ln.strip() for ln in out.splitlines() if ": error: [" in ln}


# ---------------------------------------------------------------- AC-1 (R1)

def test_ac1_two_ids_on_a_body_line_is_a_lint_error(tmp_path):
    doc = _doc(tmp_path, "- a {#one} b {#two}\n")
    code, out = _run_lint(doc)
    assert code != 0, f"lint exit {code} (expected non-zero):\n{out}"
    assert "[multi-anchor] 2 block ids on one line" in out, out
    assert "registers only the first" in out, out


def test_ac1_only_the_first_body_id_registers_in_lint(tmp_path):
    ids = _lint_ids(_doc(tmp_path, "- a {#one} b {#two}\n"))
    assert "one" in ids and "two" not in ids, sorted(ids)


def test_ac1_two_ids_on_a_heading_is_a_lint_error(tmp_path):
    doc = _doc(tmp_path, "## T {#h1} {#h2}\n\nBody.\n")
    code, out = _run_lint(doc)
    assert code != 0, f"lint exit {code} (expected non-zero):\n{out}"
    assert "[multi-anchor]" in out, out
    ids = _lint_ids(doc)
    assert "h1" in ids and "h2" not in ids, sorted(ids)


def test_ac1_a_link_to_the_second_id_dangles(tmp_path):
    """The store does not have the 2nd id; hiding that recreates the incident."""
    doc = _doc(tmp_path, "- a {#one} b {#two}\n\nSee [[#two]].\n")
    code, out = _run_lint(doc)
    assert code != 0 and "dangling-local" in out, f"lint exit {code}, no dangling-local:\n{out}"


def test_ac1_multi_anchor_lines_register_the_same_id_in_both_tools(tmp_path):
    doc = _doc(tmp_path, "## T {#h1} {#h2}\n\n- a {#one} b {#two}\n")
    assert _lint_ids(doc) == _ingest_ids(doc)


# ---------------------------------------------------------------- AC-2 (R2)

def test_ac2_an_id_on_a_rel_line_is_a_lint_error_and_not_registered(tmp_path):
    doc = _doc(tmp_path, "## Sec {#sec}\n\nrel: related-to -> [[#sec]] {#on-rel}\n")
    code, out = _run_lint(doc)
    assert code != 0, f"lint exit {code} (expected non-zero):\n{out}"
    assert "[anchor-on-rel]" in out, out
    assert "on-rel" not in _lint_ids(doc)
    assert "on-rel" not in _ingest_ids(doc)


def test_ac2_an_id_on_a_malformed_rel_line_registers_in_neither_tool(tmp_path):
    doc = _doc(tmp_path, "## Sec {#sec}\n\nrel: this is not an edge {#on-bad}\n")
    code, out = _run_lint(doc)
    assert code != 0 and "malformed-rel" in out, f"lint exit {code}, no malformed-rel:\n{out}"
    assert "on-bad" not in _lint_ids(doc), "lint registered a malformed rel: line id"
    assert "on-bad" not in _ingest_ids(doc), "parse_gmd registered a malformed rel: line id"


def test_ac2_a_rel_attribute_block_is_not_an_anchor(tmp_path):
    """SPEC §5's `{...}` slot: an attribute list must not trip anchor-on-rel."""
    doc = _doc(tmp_path, "## Sec {#sec}\n\nrel: related-to -> [[#sec]] {weight=0.5}\n")
    code, out = _run_lint(doc)
    assert code == 0, f"lint exit {code} (expected clean):\n{out}"


# ---------------------------------------------------------------- AC-3 (R3)

QUOTED_HEADING = "## The `{#x}` form {#real}\n\nBody.\n"


def test_ac3_ingester_reads_the_heading_anchor_past_inline_code(tmp_path):
    doc = _doc(tmp_path, QUOTED_HEADING)
    by_id = {n.id: n for n in parse_gmd(doc).nodes}
    assert "real" in by_id and "x" not in by_id, sorted(by_id)


def test_ac3_ingester_heading_title_keeps_the_quoted_span(tmp_path):
    """Only the matched anchor span is cut; `_ID_RE.sub` would eat `{#x}` too."""
    doc = _doc(tmp_path, QUOTED_HEADING)
    by_id = {n.id: n for n in parse_gmd(doc).nodes}
    assert "real" in by_id, sorted(by_id)
    assert by_id["real"].title == "The `{#x}` form", repr(by_id["real"].title)


def test_ac3_slice_gives_the_same_id_and_title(tmp_path):
    doc = _doc(tmp_path, QUOTED_HEADING)
    _lines, nodes, _by_id, _start = _slice_mod().parse(doc)
    h2 = [n for n in nodes if n.level == 2]
    assert [n.id for n in h2] == ["real"], [n.id for n in h2]
    assert h2[0].title == "The `{#x}` form", repr(h2[0].title)


def test_ac3_lint_agrees_on_the_quoted_heading(tmp_path):
    doc = _doc(tmp_path, QUOTED_HEADING)
    assert _lint_ids(doc) == _ingest_ids(doc) == {"root", "real"}


# ---------------------------------------------------------------- AC-3b (R3b)
# String literals only — never quote these spans in a GMD doc.

DBL_LIST_ITEM = "- a ``{#x}`` b {#y}\n"
DBL_HEADING = "## The ``{#x}`` form {#y}\n\nBody.\n"
TRIPLE_LIST_ITEM = "- a ```{#x}``` b {#y}\n"
DBL_WIKILINK = "- see ``[[#nowhere]]`` here {#y}\n"


def test_ac3b_lint_registers_only_the_real_anchor(tmp_path):
    ids = _lint_ids(_doc(tmp_path, DBL_LIST_ITEM))
    assert "y" in ids and "x" not in ids, sorted(ids)


def test_ac3b_ingester_registers_only_the_real_anchor(tmp_path):
    ids = _ingest_ids(_doc(tmp_path, DBL_LIST_ITEM))
    assert "y" in ids and "x" not in ids, sorted(ids)


def test_ac3b_slice_reads_past_a_double_backtick_heading_span(tmp_path):
    """slice.py builds nodes for headings only, so its R3b case is a heading."""
    doc = _doc(tmp_path, DBL_HEADING)
    _lines, nodes, _by_id, _start = _slice_mod().parse(doc)
    h2 = [n for n in nodes if n.level == 2]
    assert [n.id for n in h2] == ["y"], [n.id for n in h2]
    assert "``{#x}``" in h2[0].title, repr(h2[0].title)


def test_ac3b_double_backtick_heading_parity(tmp_path):
    doc = _doc(tmp_path, DBL_HEADING)
    assert _lint_ids(doc) == _ingest_ids(doc) == {"root", "y"}


def test_ac3b_triple_backtick_run_is_code_in_both_tools(tmp_path):
    doc = _doc(tmp_path, TRIPLE_LIST_ITEM)
    assert _lint_ids(doc) == _ingest_ids(doc) == {"root", "y"}


def test_ac3b_a_wikilink_quoted_in_double_backticks_is_not_a_link(tmp_path):
    code, out = _run_lint(_doc(tmp_path, DBL_WIKILINK))
    assert code == 0, f"lint exit {code} (expected clean):\n{out}"


# ---------------------------------------------------------------- AC-4 (incident)

def test_ac4_the_incident_blob_fails_lint_with_twelve_multi_anchor_errors(tmp_path):
    """Regenerated from git, NOT committed under tests/: tests/ is a corpus root,
    and a second copy carrying doc id `bsd-impressions` would enter the graph."""
    p = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{INCIDENT_SHA}:workflow/bullshit/IMPRESSIONS.md"],
        capture_output=True, text=True)
    assert p.returncode == 0, f"git show {INCIDENT_SHA} failed: {p.stderr}"
    blob = tmp_path / "IMPRESSIONS.md"
    blob.write_text(p.stdout)
    code, out = _run_lint(blob)
    n = sum(1 for ln in out.splitlines() if "error: [multi-anchor]" in ln)
    assert code != 0 and n == 12, (
        f"lint exit {code}, {n} [multi-anchor] errors (expected non-zero, 12)\n{out[-1500:]}")


# ---------------------------------------------------------------- AC-5 (R5 parity)

SYNTHETIC = (
    "## Multi heading {#mh1} {#mh2}\n\n"
    "- a body line {#mb1} with two {#mb2}\n\n"
    "A paragraph above the edge.\n\n"
    "rel: related-to -> [[#mh1]] {#on-rel}\n"
    "rel: this is not an edge {#on-bad}\n\n"
    "## The `{#qx}` quoted heading {#qreal}\n\n"
    "## The ``{#dx}`` double heading {#dreal}\n\n"
    "- a ``{#lx}`` b {#lreal}\n\n"
    "- **d-1. Bold lead** {#d-1}. Body after the anchor.\n"
)


def test_ac5_parity_script_exposes_find_divergences():
    mod = _parity_mod()
    assert callable(getattr(mod, "find_divergences", None)), dir(mod)
    assert callable(getattr(mod, "main", None)), dir(mod)


def test_ac5_synthetic_fixture_with_every_shape_has_parity(tmp_path):
    """The real corpus is clean, so it cannot show a one-sided revert. This can
    (feedback_clean_corpus_hides_a_dead_gate)."""
    doc = _doc(tmp_path, SYNTHETIC)
    divergent = _parity_mod().find_divergences([doc])
    assert divergent == [], divergent


def test_ac5_synthetic_fixture_registers_the_spec_set_in_both_tools(tmp_path):
    """Parity alone holds if BOTH tools regress the same way; pin the set."""
    doc = _doc(tmp_path, SYNTHETIC)
    want = {"root", "mh1", "mb1", "qreal", "dreal", "lreal", "d-1"}
    assert _lint_ids(doc) == want, sorted(_lint_ids(doc))
    assert _ingest_ids(doc) == want, sorted(_ingest_ids(doc))


def test_ac5_real_corpus_has_parity_over_the_gate_scope():
    """At HEAD this is exactly the two plan-14 rel:-line anchors (spec
    #f-rel-anchor); GREEN after R2."""
    paths, mem = _scope_paths()
    divergent = _parity_mod().find_divergences(paths, memory_dirs=mem)
    shown = [(str(Path(p).relative_to(REPO)) if str(p).startswith(str(REPO)) else str(p),
              sorted(a), sorted(b)) for p, a, b in divergent]
    assert divergent == [], shown


# ---------------------------------------------------------------- AC-5b (R4)

def _fence_aware_lines(path: Path):
    in_code = False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if not in_code:
            yield no, line


def test_ac5b_no_rel_line_in_the_corpus_carries_an_anchor():
    """Data check, independent of the linter: R4 moves the 2 plan-14 ids."""
    paths, mem = _scope_paths()
    hits = []
    for root in paths + mem:
        files = [root] if root.is_file() else sorted(root.rglob("*.md"))
        for f in files:
            for no, line in _fence_aware_lines(f):
                if not line.startswith("rel:"):
                    continue
                masked = CM_CODE.sub(lambda m: " " * len(m.group(0)), line)
                if ANCHOR.search(masked):
                    hits.append(f"{f.relative_to(REPO) if REPO in f.parents else f}:{no}")
    assert hits == [], hits


def test_ac5b_lint_reports_no_multi_anchor_or_anchor_on_rel_over_the_scope():
    paths, mem = _scope_paths()
    _code, out = _run_lint(*paths, *mem)
    bad = [ln for ln in out.splitlines()
           if "[multi-anchor]" in ln or "[anchor-on-rel]" in ln]
    assert bad == [], bad[:10]


# ---------------------------------------------------------------- AC-6 (no FPs)

def test_ac6_bold_lead_mid_line_anchor_lints_clean_and_agrees(tmp_path):
    doc = _doc(tmp_path, "- **d-1. Title** {#d-1}. Body text after the anchor.\n")
    code, out = _run_lint(doc)
    assert code == 0, f"lint exit {code} (expected clean):\n{out}"
    assert _lint_ids(doc) == _ingest_ids(doc) == {"root", "d-1"}


def test_ac6_lint_adds_no_error_text_over_the_base_linter(tmp_path):
    """Same corpus, base linter vs current linter: the current error-text set
    is a subset (compared by text, not count — the base set is not fixed)."""
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE_SHA}:tools/gmd/lint.py"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    base_lint = tmp_path / "lint.py"
    base_lint.write_text(p.stdout)
    paths, mem = _scope_paths()
    _c0, base_out = _run_lint(*paths, *mem, lint=base_lint)
    _c1, cur_out = _run_lint(*paths, *mem)
    new = sorted(_error_texts(cur_out) - _error_texts(base_out))
    assert new == [], new[:10]


# ---------------------------------------------------------------- AC-8 (upstream)

SPEC_RULE_3 = "A block carries at most one ID; more than one `{#id}` on a line is an error."
SPEC_RULE_5 = "A `rel:` line carries no block ID; `{#…}` there is not an anchor."


def _upstream() -> Path:
    assert (UPSTREAM / "lint.py").is_file(), (
        f"upstream GMD repo not found at {UPSTREAM} — set GMD_UPSTREAM")
    return UPSTREAM


def _blob_history(up: Path, rel: str) -> set[str]:
    shas = subprocess.run(["git", "-C", str(up), "log", "--format=%H", "--", rel],
                          capture_output=True, text=True, check=True).stdout.split()
    out = set()
    for c in shas:
        r = subprocess.run(["git", "-C", str(up), "rev-parse", f"{c}:{rel}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            out.add(r.stdout.strip())
    return out


@pytest.mark.parametrize("name", ["lint.py", "slice.py"])
def test_ac8_vendored_tool_is_a_committed_upstream_blob(name):
    """Re-vendored from a sha (R6), never hand-edited downstream (bug-068)."""
    up = _upstream()
    mine = subprocess.run(["git", "hash-object", str(REPO / "tools" / "gmd" / name)],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert mine in _blob_history(up, name), (
        f"tools/gmd/{name} ({mine[:10]}) matches no committed upstream {name}")


def test_ac8_upstream_gate_test_passes_with_the_bug179_cases():
    up = _upstream()
    gate = up / "scripts" / "test-lint-gates.py"
    src = gate.read_text()
    for needle in ("multi-anchor", "anchor-on-rel", "``{#x}``", "slice"):
        assert needle in src, f"upstream gate test lacks a {needle!r} case"
    p = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True)
    assert p.returncode == 0, (p.stdout + p.stderr)[-3000:]


def test_ac8_spec_carries_the_two_rule_lines_upstream_and_here():
    up = _upstream()
    for spec in (REPO / "docs" / "gmd" / "SPEC.md", up / "SPEC.md"):
        text = spec.read_text()
        assert SPEC_RULE_3 in text, f"{spec}: missing §3 rule line"
        assert SPEC_RULE_5 in text, f"{spec}: missing §5 rule line"


def test_ac8_spec_differs_from_upstream_only_in_its_id_line():
    up = _upstream()
    mine = [ln for ln in (REPO / "docs" / "gmd" / "SPEC.md").read_text().splitlines()
            if not ln.startswith("id:")]
    theirs = [ln for ln in (up / "SPEC.md").read_text().splitlines()
              if not ln.startswith("id:")]
    assert mine == theirs


# ---------------------------------------------------------------- AC-11 (rollout)

CONSUMER_LINES = [
    "adr-0051-numeric-facet-unit-designation.md:1883",
    "first-principles-reconstruction.md:389",
    "p32.t5-designator-fold-spec.md:66",
    "p32.t4-materialize-read-spec.md:50",
    "OPEN.md:495",
    "OPEN.md:508",
]


def test_ac11_upstream_migration_guide_names_the_vendoring_consumer_lines():
    guide = (_upstream() / "gmd-migration-guide.md").read_text()
    missing = [c for c in CONSUMER_LINES if c not in guide]
    assert not missing, f"gmd-migration-guide.md does not name {missing}"
    for repo in ("cliquedb", "cliquet"):
        assert repo in guide, f"gmd-migration-guide.md does not name {repo}"


# ---------------------------------------------------------------- AC-10 (the gate)

PLANTED = (
    '---\ngmd: "0.1"\nid: planted\ntitle: "Planted"\ntags: [t]\n---\n\n'
    "# Planted {#root}\n\n## Sec {#sec}\n\nA paragraph.\n\n"
    "rel: related-to -> [[#sec]] {#on-rel}\n"
)
PLANTED_FIXED = (
    '---\ngmd: "0.1"\nid: planted\ntitle: "Planted"\ntags: [t]\n---\n\n'
    "# Planted {#root}\n\n## Sec {#sec}\n\nA paragraph. {#on-rel}\n\n"
    "rel: related-to -> [[#sec]]\n"
)


def _mini(name: str) -> str:
    return (f'---\ngmd: "0.1"\nid: {name}\ntitle: "{name}"\ntags: [t]\n---\n\n'
            f"# {name} {{#root}}\n\nBody.\n")


def _gate_root(*, lint_src: str | None, doc: str, venv: bool = True) -> Path:
    """A throwaway ROOT under a SHORT mkdtemp holding the real gate scripts."""
    root = Path(tempfile.mkdtemp(prefix="b179", dir="/tmp"))
    (root / "scripts").mkdir()
    shutil.copy2(LINT_GMD_SH, root / "scripts" / "lint-gmd.sh")
    if PARITY.is_file():
        shutil.copy2(PARITY, root / "scripts" / "check-gmd-parity.py")
    (root / "tools" / "gmd").mkdir(parents=True)
    (root / "tools" / "gmd" / "lint.py").write_text(
        lint_src if lint_src is not None else LINT.read_text())
    (root / "src").symlink_to(REPO / "src")
    if venv:
        prefix = Path(sys.prefix)
        assert (prefix / "bin" / "python").exists(), f"no venv python under {prefix}"
        (root / ".venv-eval").symlink_to(prefix)
    (root / "CLAUDE.md").write_text(_mini("claude-md"))
    (root / ".claude").mkdir()
    (root / ".claude" / "PROJECT_PROFILE.md").write_text(_mini("project-profile"))
    for d in ("docs", "workflow", "eval"):
        (root / d).mkdir()
        (root / d / f"{d}-index.md").write_text(_mini(f"{d}-index"))
    (root / "docs" / "planted.md").write_text(doc)
    return root


def _base_lint_src() -> str:
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE_SHA}:tools/gmd/lint.py"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _run_gate(root: Path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run(["bash", str(root / "scripts" / "lint-gmd.sh")],
                       capture_output=True, text=True, cwd=root, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def gate_roots():
    made: list[Path] = []
    yield made
    for r in made:
        shutil.rmtree(r, ignore_errors=False)


def test_ac10_the_gate_catches_a_divergence_lint_alone_misses(gate_roots):
    """The planted lint is the base linter: it registers rel:-line ids and
    raises no error for them, so ONLY the parity step can fail this ROOT."""
    root = _gate_root(lint_src=_base_lint_src(), doc=PLANTED)
    gate_roots.append(root)
    lint_alone = subprocess.run(
        [sys.executable, str(root / "tools/gmd/lint.py"), "docs/planted.md"],
        capture_output=True, text=True, cwd=root)
    assert lint_alone.returncode == 0, "precondition: the planted lint must pass alone"
    code, out = _run_gate(root)
    assert code != 0, f"gate passed a lint/ingest divergence:\n{out}"
    assert "planted.md" in out and "on-rel" in out, out


def test_ac10_the_gate_passes_when_the_planted_id_is_on_its_paragraph(gate_roots):
    root = _gate_root(lint_src=_base_lint_src(), doc=PLANTED_FIXED)
    gate_roots.append(root)
    code, out = _run_gate(root)
    assert code == 0, out


def test_ac10_the_unmutated_gate_passes_a_clean_root(gate_roots):
    root = _gate_root(lint_src=None, doc=PLANTED_FIXED)
    gate_roots.append(root)
    code, out = _run_gate(root)
    assert code == 0, out


def test_ac10_lint_and_parity_both_run_when_both_fail(gate_roots):
    """One failure must not hide the other (R5: both are always run)."""
    doc = PLANTED + "\nSee [[#nowhere]].\n"
    root = _gate_root(lint_src=_base_lint_src(), doc=doc)
    gate_roots.append(root)
    code, out = _run_gate(root)
    assert code != 0, out
    assert "dangling-local" in out, f"lint output missing:\n{out}"
    assert "on-rel" in out, f"parity output missing:\n{out}"


def test_ac10_a_missing_dev_interpreter_exits_2_and_names_it(gate_roots):
    """Never skipped silently: same contract as the missing-linter branch."""
    root = _gate_root(lint_src=None, doc=PLANTED_FIXED, venv=False)
    gate_roots.append(root)
    code, out = _run_gate(root)
    assert code == 2, f"exit {code}:\n{out}"
    assert ".venv-eval" in out, out


# ------------------------------------------- audit s3: a crash never passes

def _run_parity(*args: str, script: Path = PARITY, cwd: Path = REPO):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                       cwd=cwd, env=env, timeout=120)
    return p.returncode, p.stdout, p.stderr


def _non_utf8_gmd(tmp_path: Path) -> Path:
    """A doc that declares `gmd:` and then carries a Latin-1 byte: both parsers read UTF-8
    strictly, so each raises UnicodeDecodeError on it."""
    p = tmp_path / "latin1.md"
    p.write_bytes(HEAD.encode() + b"Caf\xe9 au lait {#cafe}\n")
    return p


def test_s3_a_non_utf8_gmd_doc_fails_the_parity_script(tmp_path):
    """bug-179 audit s3 (2026-11-09): mutating `n = len(divergences) + len(failures)` to
    `n = len(divergences)` left all 38 tests green, so "a crash never passes" was pinned by
    nothing. A parse failure must exit 1 and name the file, with no divergence to lean on."""
    _non_utf8_gmd(tmp_path)
    (tmp_path / "clean.md").write_text(HEAD + "A clean paragraph. {#ok}\n")
    code, out, err = _run_parity(str(tmp_path))
    assert code == 1, f"exit {code} on a parse failure:\nstdout:\n{out}\nstderr:\n{err}"
    fails = [l for l in out.splitlines() if "[parity-parse-fail]" in l]
    assert len(fails) == 1 and "latin1.md" in fails[0], out
    assert "0 divergent doc(s), 1 parse failure(s)" in err, err


def test_s3_find_divergences_raises_on_a_parse_failure(tmp_path):
    bad = _non_utf8_gmd(tmp_path)
    with pytest.raises(RuntimeError, match="parse failures") as ei:
        _parity_mod().find_divergences([tmp_path])
    assert str(bad) in str(ei.value), ei.value


# ------------------------------------------- audit m5: parity over a memory dir

def _memfile(memdir: Path, stem: str, body: str, *, with_id: bool = True) -> Path:
    fm = ['---', 'gmd: "0.1"']
    if with_id:
        fm.append(f"id: {stem}")
    fm += [f'title: "{stem}"', "tags: [feedback, test]", "metadata:", "  node_type: memory",
           "  type: feedback", "  originSessionId: 00000000-0000-0000-0000-000000000000",
           "  created: 2026-11-09", "  updated: 2026-11-09", "---", "", f"# {stem} {{#root}}",
           ""]
    p = memdir / f"{stem}.md"
    p.write_text("\n".join(fm) + "\n" + body)
    return p


# Memory-shaped bodies: the MEMORY-RULES lead/Why/How paragraphs with inline anchors, a
# sub-heading, a list item, typed edges between memories by id. One file carries no `id:`, so
# the ingester names it by its STEM (the `memory_ids=True` fallback) and lint by its stem too.
MEM_CLEAN = {
    "feedback_fx_rule": ("The rule lead-line. {#lead}\n\n**Why:** because. {#why}\n\n"
                         "**How to apply:** do it. {#how}\n\n"
                         "rel: related-to -> [[project_fx_fact]]\n"),
    "project_fx_fact": ("## A sub-section {#sub}\n\n- a list item {#li}\n\n"
                        "rel: amends -> [[feedback_fx_rule#why]]\n"),
}
MEM_NOID = ("reference_fx_noid", "A paragraph named by stem. {#para}\n")
MEM_IDS = {"feedback_fx_rule": {"root", "lead", "why", "how"},
           "project_fx_fact": {"root", "sub", "li"},
           "reference_fx_noid": {"root", "para"}}


def _clean_memdir(base: Path) -> Path:
    memdir = base / "memory"
    memdir.mkdir()
    for stem, body in MEM_CLEAN.items():
        _memfile(memdir, stem, body)
    _memfile(memdir, MEM_NOID[0], MEM_NOID[1], with_id=False)
    # The flat index: lint exempts it by name, so parity must skip it, not fail on it.
    (memdir / "MEMORY.md").write_text("- [Fx rule](feedback_fx_rule.md) — hook\n")
    return memdir


def test_m5_a_clean_memory_dir_has_parity_through_the_script(tmp_path):
    """bug-179 audit m5 (2026-11-09): the sandbox HOME has no memory dir, so the suite never ran
    the `--memory-dir` branch; it was reached only through bug-155's test, which s1 showed could
    pass without running. A synthetic dir runs it here, through the real CLI."""
    memdir = _clean_memdir(tmp_path)
    code, out, err = _run_parity("--memory-dir", str(memdir))
    assert code == 0, f"exit {code}:\nstdout:\n{out}\nstderr:\n{err}"
    assert "gmd parity: 0 divergent doc(s), 0 parse failure(s)" in out, out


def test_m5_memory_files_are_parsed_the_way_the_bridge_parses_them(tmp_path, monkeypatch):
    """0 divergences is also what a skipped dir gives. Pin that every memory file reached the
    ingester with the bridge's flags (`lenient=True, memory_ids=True`), the scope doc with the
    strict default, and that both tools registered the expected id set. The recorder is a
    pass-through spy around the real `parse_gmd` (it substitutes nothing)."""
    memdir = _clean_memdir(tmp_path)
    docdir = tmp_path / "docs"
    docdir.mkdir()
    (docdir / "scoped.md").write_text(HEAD + "A scoped paragraph. {#sp}\n")
    mod = _parity_mod()
    real = mod.parse_gmd
    calls: dict[str, dict] = {}

    def spy(path, **kw):
        calls[Path(path).name] = kw
        return real(path, **kw)

    monkeypatch.setattr(mod, "parse_gmd", spy)
    assert mod.find_divergences([docdir], memory_dirs=[memdir]) == []
    want_mem = {f"{s}.md" for s in MEM_IDS}
    assert set(calls) == want_mem | {"scoped.md"}, sorted(calls)
    for name in want_mem:
        assert calls[name] == {"lenient": True, "memory_ids": True}, (name, calls[name])
    assert calls["scoped.md"] == {}, calls["scoped.md"]
    for stem, ids in MEM_IDS.items():
        p = memdir / f"{stem}.md"
        assert set(_lint_mod().parse_doc(p)[0].node_ids) == ids, stem
        assert mod._ingest_ids(p, memory=True) == ids, stem
    # the no-id file is named by its stem in the ingester (memory-id parsing)
    assert real(memdir / f"{MEM_NOID[0]}.md", lenient=True, memory_ids=True).doc_id == MEM_NOID[0]


def test_m5_a_lint_ingester_disagreement_in_a_memory_dir_fails_the_script(gate_roots):
    """The planted divergence of AC-10 (the base linter registers an id on a `rel:` line, the
    ingester does not), put in a MEMORY file and found only through `--memory-dir`."""
    root = _gate_root(lint_src=_base_lint_src(), doc=PLANTED_FIXED)
    gate_roots.append(root)
    memdir = _clean_memdir(root)
    _memfile(memdir, "feedback_fx_planted",
             "A paragraph.\n\nrel: related-to -> [[feedback_fx_rule]] {#on-rel}\n")
    script = root / "scripts" / "check-gmd-parity.py"
    code, out, err = _run_parity("--memory-dir", str(memdir), script=script, cwd=root)
    assert code == 1, f"exit {code}:\nstdout:\n{out}\nstderr:\n{err}"
    hits = [l for l in out.splitlines() if "[anchor-parity]" in l]
    assert len(hits) == 1 and "feedback_fx_planted.md" in hits[0] and "on-rel" in hits[0], out
    # the clean memory files beside it agree even under the base linter
    assert "1 divergent doc(s), 0 parse failure(s)" in err, err
