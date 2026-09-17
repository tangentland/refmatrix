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

# Phrases that describe a phase boundary that has already passed. Each one was
# true when written and false by the time it was read.
BANNED = [
    "deferred to v1",
    "Phase 2 will",
    "Phase A stub",
    "unused for now",
    "Phase B memory entities will add",
]


def test_no_stale_phase_language_in_src():
    offenders: list[str] = []
    for p in sorted(_SRC.rglob("*.py")):
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for phrase in BANNED:
                if phrase in line:
                    offenders.append(f"{p.relative_to(_SRC.parent.parent)}:{i}: {phrase!r}")
    assert offenders == [], (
        "stale phase language in src/ — the phase it describes is over:\n  "
        + "\n  ".join(offenders)
    )


def test_this_guard_names_the_phrases_it_bans():
    """A guard whose banned list is empty passes forever. Fail loudly if it
    is ever emptied to get green."""
    assert len(BANNED) >= 4


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
