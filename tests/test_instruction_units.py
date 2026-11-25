"""task-I1.b1 (plan-32; ADR-0007 #units #binding #fixtures #layers): a rule has ONE source file, a
unit; `rmx install-hooks --apply` compiles the units into `.claude/rmx-instructions.json`; the
fixture runner proves every unit can fire; `rmx rules replay` reads a unit's pattern over the
STM ring, read-only. (The `--check` classes and the git-hook leg are in
`tests/test_hooks_reproducible.py`; this checkout's own artifacts in
`tests/test_repo_hooks_in_sync.py`.)

Every AC enters through the dev `rmx` in a sandbox project (`tests/instruction_units_support.py`).
The fixture runner is called directly (AC-3) in addition, as the spec allows (#risks 2).

What these tests pin for the implementation (task-I1.b1 #d1-#d7), beyond the spec's words:

- The compiled file is JSON with `units` (a list sorted by `id`; each entry has `id`, `kind`,
  `bind`, `text`, `sha`) and `prefilter` (keyed by event; each dispatchable unit's literal
  appears in its event's value). Every unit of every kind is in `units` ("every unit", #d3).
- A refusal exits non-zero, names the file (absolute or project-relative path) on stderr with
  the rule, and leaves the compiled file byte-for-byte as it was. Text size is the UTF-8 length
  of the stripped body (or of the `from:` section): reason 600, checklist 2,000, rule 4,000,
  skill 20,000, check 1,000 bytes. At the limit is accepted.
- `refmatrix.instructions.load_unit(path)` returns a unit with `.id` and `.kind`;
  `refmatrix.instructions.run_fixtures(unit)` returns one result per envelope with `.side`
  (`"fire"` / `"pass"`), `.index` (position in that list), `.ok`, `.outcome` (what `decide()`
  gave: `None` when nothing fires) and `.reason` (why it failed; a prefilter miss says
  "prefilter").
- `rmx rules replay <unit id>` resolves the unit from the layers (it need not be compiled yet:
  a deny is replayed BEFORE it ships, ADR-0007 #fixtures).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import pytest
import yaml

from tests import instruction_units_support as u
from tests import task21_1_support as h


@pytest.fixture
def proj():
    return u.sandbox()


def _compiled(proj_dir: Path) -> dict:
    p = proj_dir / u.COMPILED
    assert p.exists(), f"--apply wrote no compiled file at {p}"
    return json.loads(p.read_text())


# ---- AC-1: compile ---------------------------------------------------------------------------

_KIND = {"sample-deny": "deny", "sample-gate": "inject", "sample-context": "inject",
         "sample-check": "check", "sample-rule": "rule", "sample-skill": "skill"}
_TEXT = {"sample-deny": "SAMPLE-DENY-TEXT", "sample-gate": "SKILL-CHECKLIST-SENTINEL",
         "sample-context": "SAMPLE-CONTEXT-TEXT", "sample-check": "SAMPLE-CHECK-TEXT",
         "sample-rule": "SAMPLE-RULE-TEXT", "sample-skill": "SAMPLE-SKILL-TEXT"}
_PREFILTER = {"sample-deny": "rmfoo", "sample-gate": "shipit", "sample-context": "migrations/"}


def test_apply_compiles_local_units(proj):
    """AC-1: after `--apply` the compiled file holds each local unit (one of each kind the
    probes allow) with its bindings, text and sha, sorted, and each event's prefilter; a second
    `--apply` writes identical bytes. The gate's text is the skill's `#checklist` section,
    copied in at compile, and nothing beyond it."""
    root, p = proj
    u.install_local(p)
    r = u.apply(root)
    assert r.returncode == 0, u.out_of(r)
    data = _compiled(p)
    units = data["units"]
    ids = [x["id"] for x in units]
    assert ids == sorted(ids), f"units are not sorted by id: {ids}"
    assert set(ids) == set(u.LOCAL_SAMPLES), ids
    by_id = {x["id"]: x for x in units}
    for uid, kind in _KIND.items():
        unit = by_id[uid]
        assert unit["kind"] == kind, (uid, unit["kind"])
        fm, _ = u.frontmatter(u.sample_path(uid))
        bind_json = json.dumps(unit["bind"])
        for b in fm["unit"]["bind"]:
            assert b["event"] in bind_json, (uid, unit["bind"])
            for ere in (b.get("match") or {}).values():
                assert json.dumps(ere)[1:-1] in bind_json, (uid, ere, unit["bind"])
        assert _TEXT[uid] in unit["text"], (uid, unit["text"])
        assert re.fullmatch(r"[0-9a-f]{12,64}", str(unit["sha"])), (uid, unit["sha"])
    assert "SKILL-BACKGROUND-SENTINEL" not in by_id["sample-gate"]["text"], (
        "`from: sample-skill#checklist` copied more than the #checklist section")
    assert len({x["sha"] for x in units}) == len(units), "two units share a sha"
    pre = json.dumps(data["prefilter"]["PreToolUse"])
    for uid, lit in _PREFILTER.items():
        assert lit in pre, (uid, lit, data["prefilter"])
    first = u.compiled_bytes(p)
    r2 = u.apply(root)
    assert r2.returncode == 0, u.out_of(r2)
    assert u.compiled_bytes(p) == first, "a second --apply wrote different bytes"


# ---- AC-2: a bad unit is refused, loudly ------------------------------------------------------

_SIZE = {"deny": 600, "inject": 2000, "rule": 4000, "skill": 20000, "check": 1000}
_LIMIT_SPELLINGS = {600: ("600",), 2000: ("2000", "2,000"), 4000: ("4000", "4,000"),
                    20000: ("20000", "20,000"), 1000: ("1000", "1,000")}


def _env(cmd: str) -> dict:
    return {"envelope": {"hook_event_name": "PreToolUse", "session_id": "fixture-session",
                         "tool_name": "Bash", "tool_input": {"command": cmd}}}


def _unit(kind: str, **over) -> dict:
    """A valid unit map of `kind`, bound to `zapme +now` on Bash."""
    bind = {"event": "PreToolUse", "tool": "Bash", "match": {"command": "zapme +now"},
            "prefilter": "zapme"}
    if kind == "inject":
        bind["mode"] = "gate"
    unit = {"kind": kind, "bind": [bind], "priority": 5,
            "fixtures": {"fire": [_env("zapme now")], "pass": [_env("ls now")]}}
    if kind == "check":
        unit.update(on="commit", run="true")
    unit.update(over)
    return unit


def _md(uid: str, unit: dict, body: str) -> str:
    fm = {"gmd": "0.1", "id": uid, "title": f"AC-2 unit {uid}",
          "tags": ["instruction-unit", "ac-2"], "unit": unit}
    return "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body + "\n"


def _text(n: int) -> str:
    """A body whose stripped UTF-8 length is exactly `n` bytes, carrying an `Instead:` line."""
    head = "Instead: run `zapme --dry-run` first.\n"
    return head + "a" * (n - len(head))


_DIR = {"deny": "triggers", "ask": "triggers", "inject": "triggers", "check": "checks",
        "rule": "rules"}


def _place(proj_dir: Path, kind: str, uid: str) -> Path:
    if kind == "skill":
        return proj_dir / ".claude" / "skills" / uid / "SKILL.md"
    return proj_dir / ".claude" / _DIR[kind] / f"{uid}.md"


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


def _commits_unit(n: int) -> dict:
    """A deny whose fire fixture builds a repo of `n` commits."""
    un = _unit("deny")
    un["fixtures"]["fire"][0]["repo"] = {"files": {"a.txt": "a\n"}, "commits": n}
    return un


def _bad(case: str, proj_dir: Path) -> "tuple[list[Path], list[tuple[str, ...]]]":
    """Write the refused unit for `case`; return (the file(s) it may be named by, the token
    groups stderr must carry: every group matched, any token of a group)."""
    ok_text = _text(200)
    if case == "unknown-key":
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", _unit("deny", bogus_key=1), ok_text))], [("bogus_key",)]
    if case == "unknown-bind-key":
        un = _unit("deny")
        un["bind"][0]["binder"] = "x"
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", un, ok_text))], [("binder",)]
    if case in ("no-fire-fixture", "no-pass-fixture"):
        side = "fire" if case == "no-fire-fixture" else "pass"
        un = _unit("deny")
        del un["fixtures"][side]
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", un, ok_text))], [("fixture",), (side,)]
    if case.startswith("size-"):
        kind = case[len("size-"):]
        lim = _SIZE[kind]
        return [_write(_place(proj_dir, kind, "refused-case"),
                       _md("refused-case", _unit(kind), _text(lim + 1)))], [_LIMIT_SPELLINGS[lim]]
    if case == "deny-without-instead":
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", _unit("deny"), "Never zap now. " * 10))], [("instead",)]
    if case == "duplicate-id":
        # a second unit carrying sample-deny's id, in another kind's directory
        f = _write(_place(proj_dir, "check", "second-of-an-id"),
                   _md("sample-deny", _unit("check"), ok_text))
        return [f, proj_dir / ".claude" / "triggers" / "sample-deny.md"], [("sample-deny",)]
    if case == "ask-unverified":
        return [_write(_place(proj_dir, "ask", "refused-case"),
                       _md("refused-case", _unit("ask"), ok_text))], [("ASK_VERIFIED",)]
    if case == "context-without-fallback":
        un = _unit("inject")
        un["bind"][0]["mode"] = "context"
        return [_write(_place(proj_dir, "inject", "refused-case"),
                       _md("refused-case", un, ok_text))], [("CONTEXT_VERIFIED", "fallback")]
    if case == "non-utf8":
        raw = _md("refused-case", _unit("deny"), ok_text).encode() + b"\xff\xfe broken\n"
        return [_write(_place(proj_dir, "deny", "refused-case"), raw)], [("utf",)]
    if case.startswith("kind-dir-"):
        # b-2 (bsd-i1b1 r1): a unit whose kind belongs in another layer directory. A deny in
        # `.claude/rules/` is a compiled deny AND an always-on native rule.
        kind, there = {"kind-dir-deny-in-rules": ("deny", "rules"),
                       "kind-dir-check-in-triggers": ("check", "triggers")}[case]
        right = "triggers" if kind == "deny" else "checks"
        f = _write(proj_dir / ".claude" / there / "refused-case.md",
                   _md("refused-case", _unit(kind), ok_text))
        return [f], [(right,)]
    if case in ("not-a-unit-trigger", "not-a-unit-check", "units-misspelt"):
        # g-2 (bsd-i1b1 r1, mutant X2): `triggers/` and `checks/` hold units only; a file
        # there with no `unit:` map is a mistyped unit, never a silently skipped native file.
        d = "checks" if case == "not-a-unit-check" else "triggers"
        if case == "units-misspelt":
            text = _md("refused-case", _unit("deny"), ok_text).replace("\nunit:\n", "\nunits:\n", 1)
            assert "\nunits:\n" in text
        else:
            text = ('---\ngmd: "0.1"\nid: refused-case\ntitle: "plain"\ntags: [x]\n---\n\n'
                    "# Plain {#root}\n\nA plain note, no unit map.\n")
        return [_write(proj_dir / ".claude" / d / "refused-case.md", text)], [("not a unit",)]
    if case.startswith("prefilter-"):
        # s-2 (bsd-i1b1 r1, lead ruling): the dispatcher (I1.b3) tests raw stdin bytes, the
        # fixture runner a json.dumps; a prefilter spanning JSON structure (`"`, `\`, `:`)
        # cannot be checked the same way in both, so it is refused at compile.
        lit = {"prefilter-quote": 'zap"me', "prefilter-backslash": "zap\\me",
               "prefilter-colon": "zap: me"}[case]
        un = _unit("deny")
        un["bind"][0]["prefilter"] = lit
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", un, ok_text))], [("prefilter",)]
    if case == "fixture-commits-over-cap":
        # s-4 (bsd-i1b1 r1, lead ruling): `commits` is capped at 10 at parse; each commit is a
        # bounded `git` call and `--check` runs every local unit's fixtures.
        return [_write(_place(proj_dir, "deny", "refused-case"),
                       _md("refused-case", _commits_unit(11), ok_text))], [("commits",), ("10",)]
    if case == "unreadable":
        f = _write(_place(proj_dir, "deny", "refused-case"),
                   _md("refused-case", _unit("deny"), ok_text))
        f.chmod(0)
        return [f], [("permission", "cannot read", "unreadable", "not readable")]
    raise AssertionError(case)


_REFUSALS = ["unknown-key", "unknown-bind-key", "no-fire-fixture", "no-pass-fixture",
             *(f"size-{k}" for k in _SIZE), "deny-without-instead", "duplicate-id",
             "ask-unverified", "context-without-fallback", "non-utf8", "unreadable",
             # the fold of bsd-i1b1 r1 (b-2, g-2, s-2, s-4)
             "kind-dir-deny-in-rules", "kind-dir-check-in-triggers",
             "not-a-unit-trigger", "not-a-unit-check", "units-misspelt",
             "prefilter-quote", "prefilter-backslash", "prefilter-colon",
             "fixture-commits-over-cap"]


@pytest.mark.parametrize("case", _REFUSALS)
def test_apply_refuses(case, proj):
    """AC-2: one case per refusal in #d3. `--apply` exits non-zero, stderr names the file and
    the rule, and the compiled file is unchanged.

    `ask-unverified` / `context-without-fallback` hold while `ASK_VERIFIED` /
    `CONTEXT_VERIFIED` are off (probe P2 / P1 not yet committed, task-I1.b0 #verdicts): the
    commit that flips a constant on its evidence turns its case into an acceptance case."""
    root, p = proj
    u.install_local(p)
    r0 = u.apply(root)
    assert r0.returncode == 0, u.out_of(r0)
    before = u.compiled_bytes(p)
    settings_before = (p / ".claude" / "settings.json").read_bytes()
    files, groups = _bad(case, p)
    try:
        r = u.apply(root)
    finally:
        for f in files:
            if f.exists():
                f.chmod(0o644)
    assert r.returncode != 0, (
        f"--apply accepted a bad unit ({case}); exit {r.returncode}:\n{u.out_of(r)}")
    err = r.stderr or ""
    named = [f for f in files if str(f) in err or str(f.relative_to(p)) in err]
    assert named, f"stderr names none of {[str(f) for f in files]}:\n{err}"
    rest = err
    for f in files:
        rest = rest.replace(str(f), "").replace(str(f.relative_to(p)), "")
    for group in groups:
        assert any(t.lower() in rest.lower() for t in group), (
            f"stderr does not name the rule ({' | '.join(group)}):\n{err}")
    assert u.compiled_bytes(p) == before, "a refused --apply changed the compiled file"
    assert (p / ".claude" / "settings.json").read_bytes() == settings_before, (
        "a refused --apply rewrote settings.json")


@pytest.mark.parametrize("kind", sorted(_SIZE))
def test_apply_accepts_text_at_its_size_limit(kind, proj):
    """AC-2's other edge: text of exactly the limit compiles, so each size rule is the
    contract's number (ADR-0007 #contract) and not a stricter one."""
    root, p = proj
    _write(_place(p, kind, "at-limit"), _md("at-limit", _unit(kind), _text(_SIZE[kind])))
    r = u.apply(root)
    assert r.returncode == 0, u.out_of(r)
    ids = [x["id"] for x in _compiled(p)["units"]]
    assert "at-limit" in ids, ids


def test_apply_accepts_fixture_commits_at_the_cap(proj):
    """s-4's other edge (bsd-i1b1 r1): `commits: 10` is the cap, accepted."""
    root, p = proj
    _write(_place(p, "deny", "at-cap"), _md("at-cap", _commits_unit(10), _text(200)))
    r = u.apply(root)
    assert r.returncode == 0, u.out_of(r)
    assert "at-cap" in [x["id"] for x in _compiled(p)["units"]]


# ---- AC-3: every unit proves it can fire ----------------------------------------------------

def _packaged_unit_files() -> "list[Path]":
    out = []
    for d in u.PACKAGED_DIRS:
        if (u.TEMPLATES / d).is_dir():
            out.extend(u.unit_files(u.TEMPLATES / d))
    return out


def _fixture_cases() -> list:
    cases = []
    for path in _packaged_unit_files() + u.unit_files(u.SAMPLE):
        fm, _ = u.frontmatter(path)
        fx = fm["unit"].get("fixtures") or {}
        for side in ("fire", "pass"):
            for i, _ in enumerate(fx.get(side) or []):
                cases.append(pytest.param(path, side, i, id=f"{fm['id']}/{side}[{i}]"))
    return cases


_SAMPLE_KINDS = {u.frontmatter(p)[0]["unit"]["kind"] for p in u.unit_files(u.SAMPLE)}
assert _SAMPLE_KINDS >= {"deny", "ask", "inject", "check", "rule", "skill"}, (
    f"the sample directory must hold one unit per kind; it has {sorted(_SAMPLE_KINDS)}")

# The outcome a firing envelope must give, where the kind fixes it (#d4). `sample-context` may
# take its declared fallback while CONTEXT_VERIFIED is off.
_OUTCOME = {"deny": {"deny"}, "ask": {"ask"}}
_OUTCOME_BY_ID = {"sample-gate": {"gate"}, "sample-context": {"context", "post"}}


def _result(unit, results, side: str, index: int):
    hit = [x for x in results if x.side == side and x.index == index]
    assert len(hit) == 1, f"{unit.id}: expected one result for {side}[{index}], got {results}"
    return hit[0]


@pytest.mark.parametrize("path,side,index", _fixture_cases())
def test_packaged_unit_fixtures(path, side, index):
    """AC-3: every packaged unit's envelopes and the sample directory's (one unit per kind, the
    check and the gate stateful: a dirty repo, a store present or absent) go through the
    runner: `fire` gives the unit's outcome and carries its prefilter, `pass` gives nothing."""
    from refmatrix import instructions
    unit = instructions.load_unit(path)
    res = _result(unit, instructions.run_fixtures(unit), side, index)
    assert res.ok, f"{unit.id} {side}[{index}]: {res.reason}"
    if side == "pass":
        assert not res.outcome, f"{unit.id} pass[{index}] fired: {res.outcome}"
        return
    want = _OUTCOME_BY_ID.get(unit.id) or _OUTCOME.get(unit.kind)
    assert res.outcome, f"{unit.id} fire[{index}] gave no outcome"
    if want:
        assert res.outcome in want, (unit.id, res.outcome, want)


_PLANTED = [
    ("planted-fire-nomatch", "fire", 1, None),
    ("planted-fire-noprefilter", "fire", 1, "prefilter"),
    ("planted-pass-fires", "pass", 1, None),
]


@pytest.mark.parametrize("name,side,index,why", _PLANTED, ids=[c[0] for c in _PLANTED])
def test_planted_unit_fixture_fails(name, side, index, why):
    """AC-3's three planted units: a `fire` envelope its pattern does not match, a `fire`
    envelope that matches but lacks its own prefilter, a `pass` envelope that fires. Each
    fails on exactly that envelope; every other envelope of the unit passes."""
    from refmatrix import instructions
    unit = instructions.load_unit(u.PLANTED / f"{name}.md")
    results = instructions.run_fixtures(unit)
    bad = [(x.side, x.index) for x in results if not x.ok]
    assert bad == [(side, index)], f"{name}: failing envelopes {bad}; results {results}"
    if why:
        assert why in str(_result(unit, results, side, index).reason).lower(), results


# ---- AC-7: replay ----------------------------------------------------------------------------

_SECRET = "SECRET-7f3a"
# The 4th command is a near miss through `unless` (g-1, bsd-i1b1 r1: a replay that dropped
# `unless` survived with three commands).
_COMMANDS = ("echo alpha-one", "ls beta-two", f"rmfoo --all {_SECRET}/",
             "rmfoo --all x/ --dry-run")


def _count(word: str, out: str) -> int:
    """The one number printed right after `word` (`scanned 4`, `hits 1`)."""
    found = re.findall(rf"\b{word} (\d+)\b", out)
    assert len(found) == 1, f"expected one `{word} <n>` in the output, found {found}:\n{out}"
    return int(found[0])


def _ring_by_the_generated_focus_entries(root: Path, session: str) -> "list[dict]":
    """Three Bash calls through the GENERATED PreToolUse / PostToolUse focus entries, as Claude
    Code runs them; returns the ring they wrote."""
    pre = h.generated_cmd(root, "PreToolUse", "focus hook --event tool-pre")
    post = h.generated_cmd(root, "PostToolUse", "focus hook --event tool")
    for i, cmd in enumerate(_COMMANDS):
        env = {"session_id": session, "tool_name": "Bash", "tool_input": {"command": cmd},
               "tool_use_id": f"toolu_replay_{i}", "cwd": str(root.parent)}
        for event, c in (("PreToolUse", pre), ("PostToolUse", post)):
            e = dict(env, hook_event_name=event)
            if event == "PostToolUse":
                e["tool_response"] = {"stdout": "", "stderr": "", "interrupted": False}
            r = h.run_hook(c, root=root, envelope=e, timeout=60)
            assert r.returncode == 0, (event, cmd, r.stderr)
    ring = h.jsonl(root / "stm" / f"{session}.jsonl")
    tools = [ev for ev in ring if ev.get("kind") == "tool"]
    assert [ev.get("detail") for ev in tools] == list(_COMMANDS), ring
    return tools


@pytest.mark.parametrize("case", ["hashes-only", "show"])
def test_replay(case, proj):
    """AC-7: over a ring the generated focus entries wrote (four Bash events, one matching
    sample-deny, one cancelled by its `unless`): scanned 4, hits 1, the hit's time and sha256 and no command text; `--show`
    adds the text; the limits line names DETAIL_MAX, the `who` upper bound and the unevaluated
    `when`."""
    from refmatrix import stm
    root, p = proj
    u.install_local(p, ids=("sample-deny",))
    session = f"replay-{uuid.uuid4().hex[:12]}"
    h.mark_token(session)
    tools = _ring_by_the_generated_focus_entries(root, session)
    args = ["rules", "replay", "sample-deny"] + (["--show"] if case == "show" else [])
    r = u.rmx(root, *args)
    assert r.returncode == 0, f"rmx {' '.join(args)}: exit {r.returncode}\n{u.out_of(r)}"
    out = u.out_of(r)
    # s-5 (bsd-i1b1 r1): the counts are read, not matched loosely; a loose regex let a replay
    # that counted every event as a hit pass (M27a).
    assert _count("scanned", out) == 4, out
    assert _count("hits", out) == 1, out
    assert "unmeasurable" not in out, f"a `command` bind is measurable from the ring:\n{out}"
    hit = tools[2]
    full = hashlib.sha256(hit["detail"].encode()).hexdigest()
    span = hashlib.sha256(re.search(r"rmfoo +--all", hit["detail"]).group(0).encode()).hexdigest()
    assert full[:12] in out or span[:12] in out, f"no sha256 of the matched text:\n{out}"
    assert hit["ts"] in out, f"the hit's time {hit['ts']} is not printed:\n{out}"
    if case == "show":
        assert _SECRET in out, f"--show did not print the matched text:\n{out}"
    else:
        assert _SECRET not in out, f"replay printed command text without --show:\n{out}"
    low = out.lower()
    assert str(stm.DETAIL_MAX) in out, f"the limits line does not name DETAIL_MAX:\n{out}"
    assert "upper bound" in low, f"the limits line does not say `who` is an upper bound:\n{out}"
    assert re.search(r"\bwhen\b", low), f"the limits line does not say `when` is unread:\n{out}"


# ---- b-1 (bsd-i1b1 r1): replay names the binds the ring cannot measure ---------------------
#
# The ring writer (`cli._tool_event_fields`) keeps a Bash call's `command` and every other
# tool's input minus `content`, `new_string`, `old_string` and `edits`. A unit bound to one of
# those keys can never be hit by replay; a bare "hits 0" read as "safe to ship" before a deny
# went live. The ring here is written by the GENERATED focus entries from a real envelope.

_UNMEASURABLE = {
    "write-content": ("Write", "content",
                      {"file_path": "/w/app/a.py", "content": "x = 'rmfoo --all build/'\n"}),
    "edit-new_string": ("Edit", "new_string",
                        {"file_path": "/w/app/a.py", "old_string": "a",
                         "new_string": "rmfoo --all build/"}),
}


@pytest.mark.parametrize("case", sorted(_UNMEASURABLE))
def test_replay_names_unmeasurable_binds(case, proj):
    root, p = proj
    tool, key, tool_input = _UNMEASURABLE[case]
    fire = {"envelope": {"hook_event_name": "PreToolUse", "session_id": "fixture-session",
                         "tool_name": tool, "tool_input": tool_input}}
    calm = {"envelope": {"hook_event_name": "PreToolUse", "session_id": "fixture-session",
                         "tool_name": tool, "tool_input": dict(tool_input, **{key: "ls"})}}
    unit = {"kind": "deny", "priority": 5,
            "bind": [{"event": "PreToolUse", "tool": tool, "match": {key: "rmfoo +--all"},
                      "prefilter": "rmfoo"}],
            "fixtures": {"fire": [fire], "pass": [calm]}}
    _write(_place(p, "deny", "replay-unmeasurable"),
           _md("replay-unmeasurable", unit, _text(200)))
    session = f"replay-{uuid.uuid4().hex[:12]}"
    h.mark_token(session)
    pre = h.generated_cmd(root, "PreToolUse", "focus hook --event tool-pre")
    post = h.generated_cmd(root, "PostToolUse", "focus hook --event tool")
    env = {"session_id": session, "tool_name": tool, "tool_input": tool_input,
           "tool_use_id": "toolu_unmeasurable", "cwd": str(p)}
    for event, c in (("PreToolUse", pre), ("PostToolUse", post)):
        e = dict(env, hook_event_name=event)
        if event == "PostToolUse":
            e["tool_response"] = {"success": True}
        r = h.run_hook(c, root=root, envelope=e, timeout=60)
        assert r.returncode == 0, (event, r.stderr)
    tools = [ev for ev in h.jsonl(root / "stm" / f"{session}.jsonl") if ev.get("kind") == "tool"]
    assert len(tools) == 1 and "rmfoo" not in str(tools[0].get("detail")), (
        f"precondition: the ring writer drops `{key}` from a {tool} event: {tools}")
    r = u.rmx(root, "rules", "replay", "replay-unmeasurable")
    out = u.out_of(r)
    assert r.returncode == 0, out
    assert f"unmeasurable: bind[0].match.{key} is not stored in the ring" in out, (
        f"replay does not name the bind it cannot measure:\n{out}")
    assert _count("hits", out) == 0, out
