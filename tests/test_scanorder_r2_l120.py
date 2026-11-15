"""scan-prompt order fix, ch-bsd r1 fold (ruling L120): REDs for S1, S2, S3 and M1.

Report: `workflow/bullshit/2026-11-15-0340-scanorder-r1-ca22b79.md` (#s1 #s2 #s3 #m1); ruling
L120 in `workflow/plan-review-2026-11-13.md#lead`. Everything is tested through behaviour, never
through a predicate's name.

S1 (#s1). "Named identifier" was `_token_shape_score(name) > 0`, and the score gives +0.5 to any
token of 12+ characters and +1.0 to any `-` / `.`. So `implementation`, `architecture`,
`measurements`, `relationships` took tier 1 ahead of the content matches, and in the composite a
topic whose only "grounded" members were dotted fragments (`e.g`, `t.repla`) or long plain words
was emitted. Pinned: those words are never in the tier-1 section (the first `context for
prompt-mentioned symbols` header, which is tier 1 whenever the prompt names an identifier);
real identifiers (`widget_registry`, `scan-prompt`, `KeyError`, `bug-241`, a path) are (guard);
such a topic is not emitted; a topic with a real identifier still is (guard). `max_concepts=10`
here so S2's cut cannot be the reason.

S2 (#s2). The reorder ran AFTER `_ppr_rerank(...)[:max_concepts]`, so a named identifier that
PageRank ranks below five central plain words was cut before it could be ordered: the real hook
run had an EMPTY tier 1. Pinned at the default `max_concepts=5`: a prompt naming
`widget_registry` / `scan-prompt` next to five or more central plain words gets that
identifier's bundle, and as the first bundle of the output.

S3 (#s3). The composite was marked "sent" when rendered, not when delivered: a `max_bytes` that
drops the composite block still wrote the marker, and the next prompt, with room, suppressed it
as unchanged. Pinned: capped call (composite dropped) then uncapped call -> composite delivered.

M1 (#m1). The marker survives compaction (same session id), so after `/compact` an unchanged
composite is never re-sent. Pinned through the observable: the composite is delivered, the same
call again delivers nothing (unchanged), then EVERY command the generated hook config
(`hooks._claude_hook_block`) binds to PreCompact and to SessionStart `compact|clear` runs (real
dev `rmx`, a Claude Code envelope on stdin), and the next call delivers the same composite again.
Where the fix lives (PreCompact or SessionStart) is GREEN's choice; both event sets run.

Throwaway stores under SHORT `short_root()` roots; in-process `Store`, no daemon; hook commands
run with the dev `rmx` first on PATH and `REFMATRIX_ROOT` naming the throwaway store. No mocks.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import rmx_sandbox  # tests/sandbox_site, on sys.path via tests/conftest.py (task-29.4 #r5)
from refmatrix import stm as stm_mod
from refmatrix.composite import build_topic_composite
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.scan import scan_prompt
from refmatrix.store import Store

from devbin import dev_bin, dev_env  # bug-253: the dev rmx, defined once (tests/devbin.py)

REPO = Path(__file__).resolve().parents[1]
DEV_BIN = dev_bin()

LONG_WORDS = ["implementation", "architecture", "measurements", "relationships"]
IDENTS = ["widget_registry", "scan-prompt", "KeyError", "bug-241", "src/pkg/widget.py"]

P_LONG = ("Please review the implementation and architecture of widget_registry; "
          "follow-up on daemon measurements and relationships")
P_IDENTS = "why does scan-prompt raise KeyError for bug-241 in src/pkg/widget.py and widget_registry"
P_HYPHEN = ("check scan-prompt against the implementation architecture measurements "
            "relationships daemon")

# Plain words are central (every doc mentions them); each identifier is peripheral.
BODIES = [
    "The widget_registry implementation keeps every widget; architecture notes.",
    "Implementation architecture measurements relationships daemon overview.",
    "Daemon measurements and relationships across the implementation architecture.",
    "Architecture relationships implementation measurements daemon daemon.",
    "More implementation, architecture, measurements, relationships and the daemon.",
    "A KeyError in scan-prompt was bug-241; see src/pkg/widget.py.",
]
# Concepts the GMD body pass does not mint (hyphenated, path, mixed case): added explicitly,
# each linked to the one doc that names it.
EXPLICIT = {"scan-prompt": 5, "bug-241": 5, "src/pkg/widget.py": 5, "KeyError": 5}


def _doc(i: int, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: doc-{i}\ntitle: "D{i}"\ntags: [t]\n'
            f'metadata: {{node_type: memory, type: test/doc}}\n---\n\n# D{i} {{#root}}\n\n'
            f'{body}\n')


@pytest.fixture
def env():
    base = Path(rmx_sandbox.short_root("sco.")).resolve()
    proj = base / "proj"
    docs = proj / "docs"
    docs.mkdir(parents=True)
    for i, b in enumerate(BODIES):
        (docs / f"doc-{i}.md").write_text(_doc(i, b), encoding="utf8")
    root = proj / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    ingest_gmd_paths(s, sorted(docs.glob("*.md")), as_memory=True,
                     memory_mtype_default="test/doc")
    for name, i in EXPLICIT.items():
        cid = s.add_concept(name)
        ent = s.get_entity("memory", f"doc-{i}")
        assert ent is not None, f"no memory row doc-{i}"
        s.link("mentions", cid, ent.id)
    s.flush_fragments()
    c = {"s": s, "root": root, "proj": proj}
    try:
        yield c
    finally:
        if c["s"] is not None:
            c["s"].close()
        shutil.rmtree(base, ignore_errors=True)


_SYM_HDR = re.compile(r"^# refmatrix context for prompt-mentioned symbols: (.*)$", re.M)
_BUNDLE = re.compile(r"^=== context for `([^`]+)` ===$", re.M)


def _tier1(out: str) -> "list[str]":
    """Names in the tier-1 header: the first symbol header, when it precedes the content
    matches (or there are none)."""
    m = _SYM_HDR.search(out)
    if not m:
        return []
    content = out.find("# refmatrix content matches for prompt")
    if content != -1 and content < m.start():
        return []
    return [t.strip().lower() for t in m.group(1).split(",")]


# ---- S1 ---------------------------------------------------------------------------------


def test_s1_long_plain_words_are_not_placed_in_tier_1(env):
    out = scan_prompt(env["s"], P_LONG, composite=False, max_concepts=10)
    tier1 = _tier1(out)
    assert "widget_registry" in tier1, f"fixture: widget_registry not in tier 1: {tier1}\n{out}"
    plain = [w for w in LONG_WORDS if w in tier1]
    assert not plain, (f"plain long words placed in tier 1 ahead of the content matches: "
                       f"{plain} (tier 1: {tier1})")


def test_s1_guard_real_identifiers_are_placed_in_tier_1(env):
    out = scan_prompt(env["s"], P_IDENTS, composite=False, max_concepts=10)
    tier1 = _tier1(out)
    missing = [i for i in IDENTS if i.lower() not in tier1]
    assert not missing, f"identifiers missing from tier 1: {missing} (tier 1: {tier1})\n{out}"


def _ring(root: Path, refs: "list[str]", session: str = "sess") -> None:
    s = stm_mod.Stm(root, session)
    s.record("input", " ".join(refs), refs=refs)
    s.record("tool", "again " + " ".join(refs), refs=refs)


@pytest.mark.parametrize("refs", [
    ["implementation", "e.g", "architecture"],
    ["measurements", "t.repla", "relationships"],
    ["implementation", "architecture", "relationships"],
    ["p.read", "e.g", "measurements"],
], ids=["long+e.g", "long+t.repla", "long-only", "dotted-fragments"])
def test_s1_a_topic_grounded_only_by_fragments_or_long_words_is_not_emitted(tmp_path, refs):
    root = tmp_path / ".refmatrix"
    _ring(root, refs)
    out = build_topic_composite(None, root, expand=False, session="sess")
    assert out == "", f"topic {refs} was emitted as grounded:\n{out}"


@pytest.mark.parametrize("ident", ["widget_registry", "bug-241", "KeyError", "src/pkg/a.py"])
def test_s1_guard_a_topic_with_a_real_identifier_is_emitted(tmp_path, ident):
    root = tmp_path / ".refmatrix"
    _ring(root, [ident, "implementation", "architecture"])
    out = build_topic_composite(None, root, expand=False, session="sess")
    assert ident in out, f"a topic holding {ident} was not emitted:\n{out}"


# ---- S2 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("prompt,ident", [(P_HYPHEN, "scan-prompt"), (P_LONG, "widget_registry")],
                         ids=["scan-prompt", "widget_registry"])
def test_s2_a_named_identifier_survives_the_ppr_cut_and_comes_first(env, prompt, ident):
    out = scan_prompt(env["s"], prompt, composite=False)          # max_concepts=5
    # A name with a space is the content bundle (its ref is the candidate bag), not a concept.
    bundles = [b.lower() for b in _BUNDLE.findall(out) if " " not in b]
    assert ident.lower() in bundles, (
        f"the named identifier {ident!r} was cut before ordering; bundles: {bundles}\n"
        f"headers: {_SYM_HDR.findall(out)}")
    assert bundles[0] == ident.lower(), f"{ident!r} is not the first bundle: {bundles}"


# ---- S3 / M1 helpers ------------------------------------------------------------------------

COMP_MARK = "# STM topic composite"
GROUNDED = ["parser.py", "lexer_table", "token_stream"]


SCAN_PROMPT = "what does the daemon implementation do"


def _scan(env, **kw) -> str:
    return scan_prompt(env["s"], SCAN_PROMPT, composite=True, composite_root=env["root"], **kw)


# ---- S3 ---------------------------------------------------------------------------------


def test_s3_a_composite_the_cap_dropped_is_delivered_when_there_is_room(env):
    _ring(env["root"], GROUNDED)
    sections = scan_prompt(env["s"], SCAN_PROMPT, composite=False)
    assert sections, "fixture: no sections"
    cap = len(sections.encode("utf-8")) + 80          # sections + trailer, not the composite
    capped = _scan(env, max_bytes=cap)
    assert COMP_MARK not in capped, f"fixture: the cap did not drop the composite:\n{capped}"
    again = _scan(env)
    assert COMP_MARK in again, (
        "the composite dropped by the byte cap was marked sent and is suppressed as "
        f"unchanged on the next prompt with room:\n{again[-1500:]}")


# ---- M1 ---------------------------------------------------------------------------------


def _event_commands() -> "list[tuple[str, dict, str]]":
    """(event, stdin envelope, command) for every command the generated config binds to
    PreCompact and to SessionStart `compact|clear`."""
    from refmatrix.hooks import _claude_hook_block
    block = _claude_hook_block(Path("/nonexistent/.refmatrix"))["hooks"]
    out = []
    for entry in block.get("PreCompact", []):
        for h in entry["hooks"]:
            out.append(("PreCompact", {"hook_event_name": "PreCompact", "trigger": "manual"},
                        h["command"]))
    for entry in block.get("SessionStart", []):
        if set(entry.get("matcher", "").split("|")) >= {"compact"}:
            for h in entry["hooks"]:
                out.append(("SessionStart", {"hook_event_name": "SessionStart",
                                             "source": "compact"}, h["command"]))
    return out


def _cli_scan(run_env: dict, proj: Path) -> str:
    """The hook's scan path: `rmx scan-prompt` (composite on, every turn) through the real CLI,
    which reads through the daemon's store."""
    r = subprocess.run([str(DEV_BIN / "rmx"), "scan-prompt", "--composite-every", "1",
                        "--max-tokens", "2000", "--text", SCAN_PROMPT],
                       capture_output=True, text=True, cwd=proj, env=run_env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_m1_an_unchanged_composite_is_delivered_again_after_compaction(env):
    home = Path(os.environ["HOME"])
    for shadow in (home / "bin" / "rmx", home / ".local" / "bin" / "rmx"):
        assert not shadow.exists(), f"{shadow} would shadow the dev rmx in the hook PATH"
    _ring(env["root"], GROUNDED)
    env["s"].close()
    env["s"] = None
    run_env = {**dev_env(), "REFMATRIX_ROOT": str(env["root"]),
               "RMX_INVOCATION_SOURCE": "eval",
               # The session the envelope names; a live hook resolves it from its pid pointer.
               "RMX_SESSION": "sess",
               "PATH": f"{DEV_BIN}:{os.environ.get('PATH', '')}"}
    r = subprocess.run([str(DEV_BIN / "rmx"), "daemon", "start", "--no-watch"],
                       capture_output=True, text=True, env=run_env, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    try:
        for _ in range(120):
            if list(env["root"].glob("*.sock")):
                break
            time.sleep(0.5)
        first = _cli_scan(run_env, env["proj"])
        assert COMP_MARK in first, f"fixture: no composite on the first call:\n{first}"
        assert COMP_MARK not in _cli_scan(run_env, env["proj"]), (
            "fixture: an unchanged composite was re-sent")
        cmds = _event_commands()
        assert any(e == "PreCompact" for e, _, _ in cmds), cmds
        assert any(e == "SessionStart" for e, _, _ in cmds), cmds
        ran = []
        for event, envelope, cmd in cmds:
            payload = {"session_id": "sess", "cwd": str(env["proj"]),
                       "transcript_path": str(env["proj"] / "t.jsonl"), **envelope}
            h = subprocess.run(["bash", "-c", cmd], input=json.dumps(payload), text=True,
                               capture_output=True, cwd=env["proj"], env=run_env, timeout=180)
            ran.append((event, cmd.split("; ")[-1], h.returncode, h.stderr[-200:]))
        again = _cli_scan(run_env, env["proj"])
    finally:
        subprocess.run([str(DEV_BIN / "rmx"), "daemon", "stop"], capture_output=True,
                       text=True, env=run_env, timeout=120)
    assert COMP_MARK in again, (
        "after PreCompact + SessionStart compact the unchanged composite is still "
        f"suppressed; hook commands run (event, command, rc, stderr tail): {ran}")
