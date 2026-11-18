"""Task 6.1 — stale deferrals are gone, and the memory path says so out loud.

Two failures were hiding behind the same prose. `src/` carried four phrases
describing phases that ended months ago ("Phase A stub", "Phase 2 will",
"deferred to v1", "unused for now"), and each one was load-bearing in a
different way:

- `embedder._extract_memory`'s "Phase A stub" comment sat on top of two bare
  `except Exception: pass` branches. That function is on the PRODUCTION path
  (`embedder.extract_batch`, `context.py:553`, `reranker.py:418`), so a memory
  whose `memory_content` sidecar is missing, or whose coref sidecar fails to
  apply, was silently embedded as its bare entity NAME — a wrong vector, no
  log line, no count. That is exactly what CLAUDE.md#no-silent-failures
  forbids on a memory path.
- `sync.py`'s "unused for now" marked `yield_lock`/`yield_every` on FOUR
  public signatures that no caller anywhere passes (the daemon passes those to
  `ingest_path` / `ingest_gmd_paths`, which do use them). Dead parameters that
  look plumbed are worse than absent ones: they suggest the sync loop yields
  the store lock, and it does not.

The grep guard exists so the prose cannot rot back.
"""
from __future__ import annotations

import importlib.util
import inspect
import re
import shutil
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "refmatrix"

_HAS_DENSE = (
    importlib.util.find_spec("sentence_transformers") is not None
    and importlib.util.find_spec("numpy") is not None
)
_skip_no_dense = pytest.mark.skipif(
    not _HAS_DENSE, reason="[dense] extra not installed"
)

# Phrases that describe a phase boundary that has already passed. Each one was true when written
# and false by the time it was read. Task 6.1 froze five literals; ch-bsd plan-6 r1 #s-3 found three
# stale deferrals the literals could not see ("for now", "later phases") and showed that the old
# meta-test (`len(BANNED) >= 4`) stayed green with a literal replaced by one that never matches.
# T0.4 R4.5 widens the guard to phrase FAMILIES and compares the family SET.
LEGACY_LITERALS = [
    "deferred to v1",
    "Phase 2 will",
    "Phase A stub",
    "unused for now",
    "Phase B memory entities will add",
]

# family name -> (regex, a line it must match). Case-insensitive except TODO, which is a marker
# only in capitals. "TODO with no plan id": a TODO that names plan-N / task-N / bug-N is anchored.
FAMILIES: "dict[str, tuple[str, str]]" = {
    "for now": (r"(?i)\bfor now\b", "ANN search is L2-distance based for now."),
    "in v1": (r"(?i)\bin v1\b", "the retry budget lands in v1"),
    "later phase(s)": (r"(?i)\blater phases?\b", "routing land in later phases."),
    "eventually": (r"(?i)\beventually\b", "we will eventually index this"),
    "when needed": (r"(?i)\bwhen needed\b", "add the cache when needed"),
    "not yet": (r"(?i)\bnot yet\b", "this flag is not yet wired"),
    "TODO without a plan id": (r"\bTODO\b(?!.*\b(?:plan-\d+|task-\d[\w.]*|bug-\d+)\b)",
                               "# TODO: handle the empty case"),
}
for _lit in LEGACY_LITERALS:
    FAMILIES[_lit] = (re.escape(_lit), f"x {_lit} y")

# The family set this guard bans. Spelled out separately from FAMILIES so that emptying or
# renaming a family is a visible diff here, not a silent loss of coverage (r1 #s-3 M3).
EXPECTED_FAMILIES = {
    "for now", "in v1", "later phase(s)", "eventually", "when needed", "not yet",
    "TODO without a plan id", *LEGACY_LITERALS,
}

_PASS_OWNER = "task-29.2-mypy-gate#ac-29"
_PASS_REASON = "derive pass module: the edit is made by 29.2's R7 release"

# Reviewed exceptions: (path, family, anchor, line, reason, owner). `anchor` is a substring of
# the one line the entry excuses; `line` pins it for the two derive pass modules (their bytes are
# frozen until 29.2 R7, ruling L122). Each entry is self-expiring: when its line no longer holds
# its phrase the guard fails naming it, so the fix and the entry's deletion land together.
ALLOW: "list[tuple[str, str, str, int | None, str, str | None]]" = [
    ("src/refmatrix/session_ingest.py", "later phase(s)", "routing land in later phases.", 5,
     _PASS_REASON, _PASS_OWNER),
    ("src/refmatrix/vectors.py", "for now", "ANN search is L2-distance based for now.", 14,
     _PASS_REASON, _PASS_OWNER),
    ("src/refmatrix/daemon.py", "eventually", "must eventually flip `status` to `done` or `error`",
     None, "states the caller's obligation on an ingest job; no deferral", None),
    ("src/refmatrix/launchctl.py", "not yet", "support (systemd user unit) is not yet implemented",
     None, "the user-facing refusal of the Linux supervisor gap, a registered fail-closed seam "
     "(workflow/deferral_registry.md, Linux supervisor support)", None),
    ("src/refmatrix/memory_layout.py", "not yet", "not yet respawned",
     None, "describes a runtime state (a stale MCP server), not deferred work", None),
    ("src/refmatrix/stm.py", "not yet", "owners not yet shown",
     None, "describes a runtime state (errors an owner has not seen), not deferred work", None),
    ("src/refmatrix/stm.py", "not yet", "had not yet touched",
     None, "describes a runtime state (what the input hook has seen), not deferred work", None),
    ("src/refmatrix/telemetry.py", "not yet", "NOT yet written",
     None, "describes a runtime state (events buffered before emit), not deferred work", None),
    ("src/refmatrix/cli.py", "TODO without a plan id", "`ok`, `TODO`, closing markers",
     None, "names the token as data the rationale filter skips", None),
    ("src/refmatrix/cli.py", "TODO without a plan id", 'rg -l TODO | rmx grep "FIXME"',
     None, "a usage example in the grep help text", None),
]

# The derive pass modules whose lines may be held (ruling L122, #r4-5-derive-hold): exactly these.
_HELD_PASS_LINES = {("src/refmatrix/session_ingest.py", 5, "later phase(s)"),
                    ("src/refmatrix/vectors.py", 14, "for now")}


def _rel(pkg: Path, p: Path) -> str:
    return "src/refmatrix/" + p.relative_to(pkg).as_posix()


def _lines(pkg: Path, rel: str) -> "list[str]":
    f = pkg / rel.removeprefix("src/refmatrix/")
    return f.read_text(encoding="utf-8", errors="replace").splitlines() if f.exists() else []


def _entry_line(pkg: Path, entry) -> "int | None":
    """The 1-based line an entry excuses, or None when it no longer holds its phrase."""
    path, family, anchor, line, _reason, _owner = entry
    lines = _lines(pkg, path)
    pat = re.compile(FAMILIES[family][0])
    if line is not None:
        ok = 0 < line <= len(lines) and anchor in lines[line - 1] and pat.search(lines[line - 1])
        return line if ok else None
    at = [i for i, ln in enumerate(lines, 1) if anchor in ln]
    if len(at) != 1 or not pat.search(lines[at[0] - 1]):
        return None
    return at[0]


def stale_entries(pkg: Path, allow=None) -> "list[str]":
    """Allow-list entries whose line no longer holds their phrase."""
    return [f"{e[0]} ({e[1]!r}, {e[2]!r})"
            for e in (ALLOW if allow is None else allow) if _entry_line(pkg, e) is None]


def offenders(pkg: Path, allow=None) -> "list[str]":
    """`path:line: family` for every phrase-family hit in `pkg` no live entry excuses."""
    excused = set()
    for e in (ALLOW if allow is None else allow):
        ln = _entry_line(pkg, e)
        if ln is not None:
            excused.add((e[0], ln, e[1]))
    pats = {name: re.compile(rx) for name, (rx, _sample) in FAMILIES.items()}
    out: list[str] = []
    for p in sorted(pkg.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = _rel(pkg, p)
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for name, pat in pats.items():
                if pat.search(line) and (rel, i, name) not in excused:
                    out.append(f"{rel}:{i}: {name!r}: {line.strip()[:100]}")
    return out


def held_pass_entries_beyond_the_two(allow=None) -> "list[str]":
    """Allow-list entries on a derive pass module other than the two #r4-5-derive-hold names."""
    from refmatrix.store import _DERIVE_PASS_MODULES
    pass_files = {f"src/refmatrix/{m}" for mods in _DERIVE_PASS_MODULES.values() for m in mods}
    return [f"{e[0]}:{e[3]} {e[1]!r}" for e in (ALLOW if allow is None else allow)
            if e[0] in pass_files and (e[0], e[3], e[1]) not in _HELD_PASS_LINES]


def test_no_stale_phase_language_in_src():
    found = offenders(_SRC)
    assert found == [], (
        "stale phase language in src/: the phase it describes is over, or it names no plan. "
        "Fix the line, or add a reviewed ALLOW entry with its reason:\n  " + "\n  ".join(found)
    )


def test_every_allow_list_entry_still_holds_its_phrase():
    """Self-expiring entries (#r4-5-derive-hold): the release that fixes an excused line deletes
    its entry in the same commit."""
    stale = stale_entries(_SRC)
    assert stale == [], "allow-list entries whose line no longer holds the phrase:\n  " + \
        "\n  ".join(stale)


def test_this_guard_bans_the_phrase_families_not_a_count():
    """The meta-test compares the SET of families and proves each pattern still fires on its own
    sample line. Replacing one with a never-matching literal (r1 #s-3 M3, T0.4 M4.5a) is red."""
    assert set(FAMILIES) == EXPECTED_FAMILIES
    dead = [name for name, (rx, sample) in FAMILIES.items() if not re.search(rx, sample)]
    assert dead == [], f"families whose pattern no longer matches their own sample: {dead}"
    # TODO is anchored by a plan id, and only then.
    assert not re.search(FAMILIES["TODO without a plan id"][0], "# TODO(plan-29): wire it")
    # every entry is reviewed: a family the guard knows, and a reason
    for e in ALLOW:
        assert e[1] in FAMILIES and e[4], e


def test_only_the_two_held_pass_module_lines_are_allow_listed():
    """M4.5d: ruling L122 holds exactly two derive-pass-module lines until 29.2 R7; any other
    entry on a pass module is red. 29.2's deletion of both keeps this green."""
    assert held_pass_entries_beyond_the_two() == []
    for e in ALLOW:
        if (e[0], e[3], e[1]) in _HELD_PASS_LINES:
            assert e[5] == _PASS_OWNER, e
    planted = ALLOW + [("src/refmatrix/embedder.py", "for now", "x", 3, _PASS_REASON, _PASS_OWNER)]
    assert held_pass_entries_beyond_the_two(planted) == ["src/refmatrix/embedder.py:3 'for now'"]


def _tree_copy(tmp_path: Path) -> Path:
    pkg = tmp_path / "src" / "refmatrix"
    shutil.copytree(_SRC, pkg, ignore=shutil.ignore_patterns("__pycache__"))
    return pkg


def test_a_stale_entry_is_named_on_a_tree_copy(tmp_path):
    """M4.5c: on a tmp copy of the tree whose vectors.py line 14 no longer says "for now", with
    the allow-list unchanged, the guard is red naming that entry. No pass module in the checkout
    is edited (their bytes feed the derive pass hash)."""
    pkg = _tree_copy(tmp_path)
    f = pkg / "vectors.py"
    lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
    assert "for now" in lines[13]
    lines[13] = lines[13].replace("for now", "by design")
    f.write_text("".join(lines), encoding="utf-8")
    assert stale_entries(pkg) == [
        "src/refmatrix/vectors.py ('for now', 'ANN search is L2-distance based for now.')"]


def test_a_new_for_now_in_src_is_named_on_a_tree_copy(tmp_path):
    """M4.5b, planted: a `# for now` appended to a src/ file is red, naming the file."""
    pkg = _tree_copy(tmp_path)
    f = pkg / "helix.py"
    n = len(f.read_text(encoding="utf-8").splitlines())
    f.write_text(f.read_text(encoding="utf-8") + "# for now\n", encoding="utf-8")
    assert [o.split(": ")[0] for o in offenders(pkg)
            if o.startswith("src/refmatrix/helix.py")] == [f"src/refmatrix/helix.py:{n + 1}"]


# --- sync.py: the dead yield parameters are gone ---------------------------


@pytest.mark.parametrize("fn_name", ["sync_files", "sync_since", "flush_queue", "_sync_paths"])
def test_sync_signatures_carry_no_dead_yield_params(fn_name):
    from refmatrix import sync as syncmod

    fn = getattr(syncmod, fn_name)
    params = set(inspect.signature(fn).parameters)
    dead = params & {"yield_lock", "yield_every"}
    assert dead == set(), (
        f"sync.{fn_name} still declares {sorted(dead)}; no caller passes them "
        "and _sync_paths never invoked them"
    )


def test_no_caller_passes_yield_args_to_sync():
    """The signature change is only safe because nothing supplies them."""
    root = _SRC.parent.parent
    pat = re.compile(
        r"(sync_files|sync_since|flush_queue)\((?:[^()]|\([^()]*\))*yield_(?:lock|every)",
        re.S,
    )
    offenders = [
        str(p.relative_to(root))
        for p in sorted((root / "src").rglob("*.py")) + sorted((root / "tests").rglob("*.py"))
        if pat.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == [], f"callers still pass yield args to sync: {offenders}"


# --- embedder: a degraded memory extraction is counted and named ------------


@pytest.fixture
def store(tmp_path):
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


@_skip_no_dense
def test_memory_without_a_content_row_is_counted_not_silently_renamed(store, caplog):
    """No `memory_content` row: the extractor may still fall back to the entity
    name, but it must SAY so — a wrong vector with no log line is the defect."""
    from refmatrix import embedder as emb

    emb.reset_degraded()
    eid = store.upsert_entity(kind="memory", name="feedback_some_rule")
    with caplog.at_level("WARNING", logger="refmatrix.embedder"):
        text = emb.extract_text_for_entity(store, eid, "memory")

    assert emb.degraded_report().get("memory_content_missing") == 1
    assert str(eid) in caplog.text
    assert "memory_content" in caplog.text
    # the fallback text itself is unchanged — this test is about the silence
    assert "feedback_some_rule" in text


@_skip_no_dense
def test_a_failing_coref_apply_is_named_and_the_raw_content_survives(store, caplog, monkeypatch):
    """coref is an optimization. When it breaks, embed the RAW content and name
    the failure; never swallow it and never lose the row."""
    from refmatrix import embedder as emb

    emb.reset_degraded()
    eid = store.add_memory(name="feedback_some_rule",
                           content="the daemon owns the writer", mtype="feedback")

    def _boom(*_a, **_k):
        raise ValueError("offsets do not match this content")

    from refmatrix.coref import Resolution
    monkeypatch.setattr(store, "load_coref",
                        lambda _eid: [Resolution(offset=4, pronoun="daemon",
                                                 antecedent="the daemon", confidence=1.0)])
    monkeypatch.setattr("refmatrix.coref.apply", _boom, raising=False)

    with caplog.at_level("WARNING", logger="refmatrix.embedder"):
        text = emb.extract_text_for_entity(store, eid, "memory")

    assert emb.degraded_report().get("coref_apply_failed") == 1
    assert "the daemon owns the writer" in text
    assert str(eid) in caplog.text


@_skip_no_dense
def test_a_healthy_memory_row_reports_no_degradation(store):
    """The counter must not fire on the happy path, or it is noise."""
    from refmatrix import embedder as emb

    emb.reset_degraded()
    eid = store.add_memory(name="feedback_some_rule",
                           content="the daemon owns the writer", mtype="feedback")

    text = emb.extract_text_for_entity(store, eid, "memory")

    assert emb.degraded_report() == {}
    assert "the daemon owns the writer" in text


# --- the count reaches a human -------------------------------------------


def test_degraded_line_is_empty_on_a_clean_run():
    from refmatrix.cli import _degraded_embed_line

    assert _degraded_embed_line({}) == ""


def test_degraded_line_names_every_reason_and_the_total():
    from refmatrix.cli import _degraded_embed_line

    line = _degraded_embed_line({"memory_content_missing": 3, "coref_apply_failed": 1})
    assert "4 row(s)" in line
    assert "memory_content_missing=3" in line
    assert "coref_apply_failed=1" in line


_HAS_LANCE = importlib.util.find_spec("lance") is not None
_OFFLINE = __import__("os").environ.get("RMX_EMBED_OFFLINE") == "1"


@pytest.mark.skipif(not (_HAS_DENSE and _HAS_LANCE), reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_op_embed_reports_degraded_rows_to_its_caller(tmp_path):
    """The count is useless if it stays in the daemon: embed runs daemon-side
    in the common case, so a CLI-process counter always reads zero."""
    from refmatrix.daemon import Daemon, _op_embed
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s

    # A memory entity with NO memory_content sidecar — embeds as its slug.
    s.upsert_entity(kind="memory", name="feedback_orphan_slug")

    result = _op_embed(d, {"kinds": ["memory"], "limit": 32})

    assert result.get("degraded", {}).get("memory_content_missing") == 1
    s.close()


@pytest.mark.skipif(not (_HAS_DENSE and _HAS_LANCE), reason="[dense] extra not installed")
@pytest.mark.skipif(_OFFLINE, reason="RMX_EMBED_OFFLINE=1")
def test_op_embed_reports_no_degradation_for_healthy_memories(tmp_path):
    from refmatrix.daemon import Daemon, _op_embed
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s

    s.add_memory(name="feedback_real", content="the daemon owns the writer",
                 mtype="feedback")

    result = _op_embed(d, {"kinds": ["memory"], "limit": 32})

    assert result["embedded"] == 1
    assert result.get("degraded") == {}
    s.close()


def test_op_embed_carries_degraded_on_a_shutdown_cancel(tmp_path):
    """T0.4 R4.6 (ch-bsd plan-6 r1 #m-2): extraction has already counted its degradations when a
    stop cancels the batch before the model runs, so the cancel return carries `degraded` as the
    `skipped_empty` return does. The stop is the daemon's real `_shutdown_event`, set before the
    op: no embedder is asked for, phase 1 extracts, phase 2 returns `cancelled`. M4.6 (drop
    `degraded` from that return) is red here."""
    from refmatrix.daemon import Daemon, _op_embed
    from refmatrix.store import Store

    root = tmp_path / ".refmatrix"
    root.mkdir(parents=True, exist_ok=True)
    d = Daemon(root)
    s = Store(root)
    s.init()
    d.store = s
    try:
        # A memory entity with NO memory_content sidecar: extraction falls back to its slug and
        # counts it.
        s.upsert_entity(kind="memory", name="feedback_orphan_slug")
        d._shutdown_event.set()

        result = _op_embed(d, {"kinds": ["memory"], "limit": 32})

        assert result.get("cancelled") is True, result
        assert result.get("degraded") == {"memory_content_missing": 1}, result
    finally:
        s.close()


# --- plan-6 Q1 "Delete": the DuckDB read facade is gone (T0.4 R4.1, AC-4.1) --------------

# Spelled in two halves so this file does not name the flag it bans.
_FACADE_FLAG = "RMX_READ_VIA_" + "DUCKDB"


def _files_naming(token: str, *dirs: Path, root: "Path | None" = None) -> "list[str]":
    root = root or _SRC.parent.parent
    out: list[str] = []
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if token in text:
                out.append(str(p.relative_to(root)))
    return out


def test_the_duckdb_read_facade_flag_is_named_nowhere_in_src_or_tests():
    """plan-6 Q1 was decided "Delete" (r1 #b-1): `duckdb_view.py` mounts the old SQLite catalog,
    no production path sets its flag, and two tests kept it alive. AC-4.1: the flag appears in
    no file under src/ or tests/, and the module is gone."""
    root = _SRC.parent.parent
    assert _files_naming(_FACADE_FLAG, root / "src", root / "tests") == []
    assert importlib.util.find_spec("refmatrix.duckdb_view") is None


def test_the_facade_flag_scan_names_a_planted_file(tmp_path):
    """The scan above can fail: a planted file naming the flag is listed."""
    sub = tmp_path / "tests"
    sub.mkdir()
    (sub / "planted.py").write_text(f'os.environ.get("{_FACADE_FLAG}")\n')
    (sub / "clean.py").write_text("x = 1\n")
    assert _files_naming(_FACADE_FLAG, sub, root=tmp_path) == ["tests/planted.py"]
