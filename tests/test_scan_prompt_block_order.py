"""scan-prompt puts the most precise block first, keeps each header with its body, and gets
the 9.5k command budget.

Why (the user, 2026-11-15: "fix the scan-prompt ordering right now" / "make sure the 9.5k
constraint is added with it"): in session 070141d0 nearly every scan-prompt output ended
`[+N block(s) omitted by --max-bytes 4499]`. The cap kept the FIRST blocks: the keyword
content-match bundle (built from every prompt word, stopwords included) and the bare header of
the symbol section, and dropped the bundles for the identifiers the prompt actually named. The
command budget was 0.9 x the measured 10,000-unit harness cap with scan-prompt given only 4,500 B
of the 9,000. Order now: bundles for identifier-shaped tokens the prompt names → the content
matches → the other matched concepts (plain words, PPR expansions) → the composite. A header is
part of its section's block, so the budget never keeps a header without its body.
"""
from __future__ import annotations

import os
import re

import pytest

from refmatrix import hook_budget as hb
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.scan import _PROMPT_STOPWORDS, scan_prompt
from refmatrix.store import Store

PROMPT = "how does widget_registry relate to the common closet"


def _doc(i: int, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: doc-{i}\ntitle: "D{i}"\ntags: [t]\n'
            f'metadata: {{node_type: memory, type: test/doc}}\n---\n\n# D{i} {{#root}}\n\n'
            f'{body}\n')


BODIES = [
    "The widget_registry holds every widget; see widget_registry for the table.",
    "widget_registry is rebuilt nightly by the scheduler.",
    "The common closet holds common things, common common common.",
    "Another common note about the closet and common words.",
]


@pytest.fixture
def store(tmp_path):
    os.environ.pop("REFMATRIX_ROOT", None)
    docs = tmp_path / "docs"
    docs.mkdir()
    for i, b in enumerate(BODIES):
        (docs / f"doc-{i}.md").write_text(_doc(i, b), encoding="utf8")
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    ingest_gmd_paths(s, sorted(docs.glob("*.md")), as_memory=True,
                     memory_mtype_default="test/doc")
    yield s
    s.close()


# ---- the 9.5k budget ---------------------------------------------------------------------

def test_command_budget_is_095_of_the_measured_cap():
    assert hb.HOOK_CAP_UNITS == 10_000
    assert hb.HOOK_COMMAND_BUDGET_BYTES == 9_500


def test_scan_cmd_gets_the_whole_9500():
    chans = hb.HOOK_COMMAND_CHANNELS["scan_cmd"]
    assert sum(hb.CHANNEL_BUDGET_BYTES[c] for c in chans) == 9_500
    assert hb.CHANNEL_BUDGET_BYTES["scan_prompt"] == 9_000
    assert hb.budget("scan_prompt") == 9_000 or os.environ.get(hb.ENV_VAR)


# ---- the order ---------------------------------------------------------------------------

def test_the_named_identifier_bundle_comes_before_the_content_matches(store):
    out = scan_prompt(store, PROMPT, composite=False)
    ident = out.find("=== context for `widget_registry` ===")
    content = out.find("content matches for prompt")
    assert ident != -1, out
    assert content != -1, out
    assert ident < content, out


def test_plain_word_bundles_come_after_the_content_matches(store):
    out = scan_prompt(store, PROMPT, composite=False)
    plain = out.find("=== context for `closet` ===")
    content = out.find("content matches for prompt")
    assert plain != -1 and content != -1, out
    assert content < plain, out


def test_a_prompt_with_no_identifier_keeps_the_content_matches_first(store):
    out = scan_prompt(store, "the common closet", composite=False)
    assert out.lstrip().startswith("# refmatrix content matches for prompt"), out


# ---- the budget keeps whole sections ------------------------------------------------------

_HEADER = re.compile(r"^# refmatrix (content matches for prompt|context for )", re.M)


def _headers_have_bodies(out: str) -> bool:
    """Every section header is followed by a `=== context for` line before the next header,
    the omission trailer, or the end."""
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if _HEADER.match(ln):
            rest = lines[i + 1:]
            for nxt in rest:
                if nxt.startswith("=== context for"):
                    break
                if _HEADER.match(nxt) or nxt.startswith("# [+"):
                    return False
            else:
                return False
    return True


@pytest.mark.parametrize("cap", [400, 700, 1000, 1400, 2000])
def test_the_budget_never_keeps_a_header_without_its_body(store, cap):
    out = scan_prompt(store, PROMPT, composite=False, max_bytes=cap)
    assert len(out.encode("utf-8")) <= cap
    assert _headers_have_bodies(out), out


def test_a_tight_budget_keeps_the_named_identifier_first(store):
    full = scan_prompt(store, PROMPT, composite=False)
    cap = full.find("content matches for prompt") + 120   # room for the first section only
    out = scan_prompt(store, PROMPT, composite=False, max_bytes=max(cap, 600))
    assert "=== context for `widget_registry` ===" in out, out


# ---- the content header names the terms, not the stopwords ---------------------------------

def test_the_content_header_lists_no_stopwords(store):
    out = scan_prompt(store, PROMPT, composite=False)
    m = re.search(r"^# refmatrix content matches for prompt: (.*)$", out, re.M)
    assert m, out
    terms = [t.strip() for t in m.group(1).split(",")]
    assert terms, out
    assert not [t for t in terms if t.lower() in _PROMPT_STOPWORDS], terms
