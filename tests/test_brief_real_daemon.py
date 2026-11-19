"""`memory_brief` against a REAL spawned daemon — the test ch-bsd r1 #b-8 asked for.

Every other daemon-op test in this range monkeypatches `daemon._read_with_fallback`,
which is the exact function whose use IS the claim ("derivation runs on the read
path"). Per CLAUDE.md #no-mocks, a test that patches the thing under test is not
a test. This one spawns a daemon on a short tmp root and drives the op over the
socket.

Short root: macOS `sun_path` is ~104 bytes (CLAUDE.md #system-dependent-tests).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import rmx_sandbox  # tests/sandbox_site, on sys.path via tests/conftest.py (task-29.4 #r5)
from devbin import dev_env, dev_rmx  # bug-253: the dev rmx, defined once (tests/devbin.py)
from tests.test_brief_detectors import LONERS, SUBJECT, UNEMBEDDED, seed_compilable
from tests.test_memory_compile_scope import _cli, spawn  # noqa: F401 (spawn is a fixture)

RMX = dev_rmx()


@pytest.fixture
def daemon_root():
    tmp = Path(rmx_sandbox.short_root("bd."))
    root = tmp / ".refmatrix"
    env = {**dev_env(), "REFMATRIX_ROOT": str(root),
           "RMX_INVOCATION_SOURCE": "eval"}
    subprocess.run([str(RMX), "init", "--path", str(tmp), "--no-hooks",
                    "--no-agents", "--no-memory-hooks"],
                   env=env, capture_output=True, timeout=120)
    _seed(root, env)                      # edges BEFORE the daemon opens it
    subprocess.run([str(RMX), "daemon", "start", "--no-watch"],
                   env=env, capture_output=True, timeout=180)
    for _ in range(60):
        if list(root.glob("*.sock")):
            break
        time.sleep(1)
    yield root, env
    subprocess.run([str(RMX), "daemon", "stop"], env=env,
                   capture_output=True, timeout=120)
    shutil.rmtree(tmp, ignore_errors=True)


def _rmx(env, *args, timeout=180):
    return subprocess.run([str(RMX), *args], env=env, capture_output=True,
                          text=True, timeout=timeout)


def _seed(root: Path, env) -> None:
    """Give the store edges, not just rows.

    ch-bsd r2: this file passed with BOTH the #b-1 and #b-4 fixes REVERTED,
    because `rmx memory add` writes no linkage fragments — so every fixture
    yielded zero briefs, `--gmd` rendered the empty-document branch and never
    reached `_as_brief`, and `--save` saved nothing so nothing could re-enter.
    A real daemon with no data is not coverage. Seed through the store the
    daemon is serving, then let the daemon read it.
    """
    from refmatrix.store import Store
    s = Store(root)
    part = root.parent.name
    with s.with_partition(part):
        orphan = s.add_concept("orphanterm")
        for i in range(6):
            m = s.add_memory(f"seed{i}", f"body mentioning orphanterm {i}",
                             mtype="project")
            s.link("mentions", orphan, m)
        a = s.add_memory("claim-a", "the fix is X", mtype="project")
        b = s.add_memory("claim-b", "the fix is not X", mtype="project")
        s.link("contradicts", a, b)
        s.flush_fragments()
    s.close()


def test_brief_runs_end_to_end_through_a_real_daemon(daemon_root):
    root, env = daemon_root
    assert list(root.glob("*.sock")), "daemon never bound"

    _rmx(env, "memory", "add", "note-a", "the daemon owns the duckdb catalog")
    _rmx(env, "memory", "add", "note-b", "the catalog is owned by one writer")

    p = _rmx(env, "memory", "brief", "--json", "--min-mentions", "3")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    # NOT just "the keys exist" — the seeded corpus must actually produce
    # briefs, or every assertion below is vacuous (ch-bsd r2).
    assert payload["briefs"], payload["stats"]
    classes = {b["class"] for b in payload["briefs"]}
    assert {"orphan-concept", "contradicted"} & classes, classes


def test_the_gmd_flag_does_not_crash_through_a_real_daemon(daemon_root):
    """#b-1 died here on every real invocation while a unit test passed."""
    root, env = daemon_root
    p = _rmx(env, "memory", "brief", "--gmd", "--min-mentions", "3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "AttributeError" not in (p.stdout + p.stderr)
    # must reach _as_brief, i.e. render a real brief — not the empty branch
    assert "### " in p.stdout, p.stdout[:400]
    assert "no briefs" not in p.stdout.lower()
    # AND the edges must survive the renderer. `console.print` parsed
    # `[[name]]` as rich markup and emitted `[]`, deleting every wikilink and
    # every `rel:` target — while tools/gmd/lint.py reported 0 errors on the
    # wreckage, because `[[]]` is not a wikilink (ch-bsd r3 #b-1-r3).
    assert "rel: evidence-for -> [[" in p.stdout, p.stdout[:800]
    assert "-> []" not in p.stdout, "rich ate the wikilink"


def test_saved_briefs_do_not_grow_the_corpus_on_rerun(daemon_root):
    """#b-4 live, now that the replica lag is waited out rather than dodged."""
    root, env = daemon_root
    first = json.loads(_rmx(env, "memory", "brief", "--json",
                            "--min-mentions", "3", "--save").stdout)
    assert first.get("saved", 0) > 0, "nothing was saved; the test is vacuous"

    # Poll the DAEMON until the replica carries the saved rows. This is a
    # daemon read — nothing feedback_store_calls_via_daemon forbids — and it
    # closes the gap I previously documented as unclosable (ch-bsd r3).
    for _ in range(30):
        listing = _rmx(env, "memory", "list", "--type", "brief/orphan-concept")
        if "brief-" in listing.stdout:
            break
        time.sleep(1)
    else:
        pytest.fail("saved briefs never reached the replica; test is vacuous")

    second = json.loads(_rmx(env, "memory", "brief", "--json",
                             "--min-mentions", "3").stdout)
    assert second["stats"]["memories"] == first["stats"]["memories"], (
        "a saved brief re-entered its own corpus")


def test_an_unknown_class_fails_loudly_through_the_daemon(daemon_root):
    """#m-17: the MCP schema has no enum, so this path is reachable.

    bug-127 (task-t0-suite-trust-sweep `#t0-2` R2.3, ruling L142): the library's raise is
    reached THROUGH the daemon, the way MCP reaches it -- `verbs.memory(..., "brief",
    classes=[…])` -> the daemon's `memory_brief` op -> `brief.compile_briefs`. The test used to
    open `Store()` on the catalog its own daemon holds, and DuckDB refused it (`Conflicting
    lock is held in … (PID <the test's daemon>)`). The asserted text is the library's own
    message, so a library that stops raising (mutation M2.3) fails here, not just a missing
    error."""
    root, env = daemon_root
    # click.Choice already rejects this, so exit!=0 proved nothing about the
    # ValueError (ch-bsd r2). Assert the LIBRARY raises, where MCP reaches it.
    from refmatrix import verbs
    with pytest.raises(verbs.VerbError) as e:
        verbs.memory(root, "brief", classes=["bogus-class"])
    assert "unknown brief class(es): bogus-class" in str(e.value), str(e.value)
    assert _rmx(env, "memory", "brief", "--class", "bogus-class").returncode != 0


def test_bug127_no_test_opens_the_catalog_its_daemon_holds():
    """bug-127 (task-t0-suite-trust-sweep `#t0-2` R2.3, AC-2.3): a test that runs against
    `daemon_root` reaches the store THROUGH the daemon, the way MCP does, and never opens
    `Store()` on the catalog that daemon holds. At c4b44d0
    `test_an_unknown_class_fails_loudly_through_the_daemon` did, and DuckDB refused it
    (`Could not set lock … Conflicting lock is held in … (PID <the test's daemon>)`, 0.82.0
    and 0.83.0 dev-tree suites; a symlinked clone 2/2). Seeding before the daemon starts
    (`_seed`, called by the fixture) is not under the daemon and is not a hit. Mutation M2.4
    (re-add the direct opener while the daemon runs) turns this red without needing the lock
    to contend."""
    import ast
    tree = ast.parse(Path(__file__).read_text())
    hits = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or "daemon_root" not in \
                [a.arg for a in fn.args.args]:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name == "Store":
                    hits.append(f"{fn.name}:{node.lineno}")
    assert not hits, ("tests open Store() on the catalog their own daemon holds (bug-127); "
                      f"reach it through the daemon op instead: {hits}")


# ── T0.5 R5.3 / AC-5.2: `compile` is verb-first ─────────────────────────────

def _brief_via(surface: str, root: Path) -> dict:
    """One `brief` with a plan, through one entry point a user calls: the `compile` switch on
    the verb, the CLI and MCP, or (`verb-plan`) a caller-built plan -- the dry-run
    `rmx_memory_compile` verb's plan handed to the verb as `plan=`."""
    from refmatrix import mcp, verbs
    if surface == "verb":
        return verbs.memory(root, "brief", compile=True)
    if surface == "verb-plan":
        plan = verbs.memory_compile(root)["plan"]
        return verbs.memory(root, "brief", plan=plan)
    if surface == "cli":
        code, out = _cli("memory", "brief", "--compile", "--json")
        assert code == 0, f"`rmx memory brief --compile --json` exited {code}:\n{out}"
        return json.loads(out)
    reply = mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "rmx_memory",
                   "arguments": {"action": "brief", "compile": True, "root": str(root)}}})
    result = reply["result"]
    text = result["content"][0]["text"]
    assert not result["isError"], text
    return json.loads(text)


@pytest.mark.parametrize("surface", ["verb", "cli", "mcp", "verb-plan"])
def test_compile_reaches_the_plan_derived_classes_through_every_entry_point(spawn, surface):
    """AC-5.2 (ch-bsd plan-8 r5 #s-4): the verb, the CLI and the MCP `rmx_memory` brief
    action, each with `compile` on, over a REAL spawned daemon serving a seeded throwaway
    store, return `corroborated` (the four-day subject) and `singleton` (the fourteen
    loners), and neither sits in `classes_not_run`. Before T0.5 only the CLI built the plan:
    the verb had no `compile` parameter, and MCP dropped the unknown key and answered with
    both classes under `classes_not_run`. The CLI case is the regression guard for the
    pass-through: it must keep working once the CLI stops planning in its own process.

    bsd-t05 r1 #b-1: the three memories with no vector are COUNTED on every surface and for a
    caller-supplied plan too (`skipped_by["unembedded"] == 3`, inside `skipped`), and the CLI
    table says so on its "counted, not dropped" line. At `61b0666c` they were in
    `stats.memories` and in nothing else: `skipped: 0`, `skipped_by: {}`."""
    ctx = spawn(seed_compilable)
    res = _brief_via(surface, ctx.root)
    stats = res.get("stats") or {}
    not_run = stats.get("classes_not_run") or {}
    assert "corroborated" not in not_run and "singleton" not in not_run, not_run
    names = {str(k): v for k, v in (res.get("names") or {}).items()}
    by_cls: dict = {}
    for b in res.get("briefs") or []:
        by_cls.setdefault(b["class"], []).append(b)
    assert [sorted(names.get(str(e)) for e in b["evidence"])
            for b in by_cls.get("corroborated", [])] == [sorted(SUBJECT)], (
        by_cls.get("corroborated"), stats)
    assert sorted(b["label"] for b in by_cls.get("singleton", [])) == sorted(LONERS), stats
    skipped_by = stats.get("skipped_by") or {}
    assert skipped_by.get("unembedded") == len(UNEMBEDDED), stats
    assert stats.get("skipped") == sum(skipped_by.values()), stats
    if surface == "cli":
        code, out = _cli("memory", "brief", "--compile")
        assert code == 0, out
        line = next((ln for ln in out.splitlines() if "counted, not dropped" in ln), "")
        assert f"unembedded={len(UNEMBEDDED)}" in line, out


# ── `plan` with `compile` is refused, loudly (T0.5 ruling, 2026-11-19) ─────

_A_PLAN = {"scope": "memory", "clusters": [], "unclustered": []}


def _names_both(text: str) -> bool:
    return "exclusive" in text and "`plan`" in text and "`compile`" in text


def test_the_verb_refuses_plan_with_compile_before_any_daemon_call():
    """Two plan sources in one call: refused with the typed args error, never resolved by
    picking one. The root has NO store and no daemon, so a verb that reached for the daemon
    first answers with a daemon error instead of the refusal (mutation G5)."""
    from refmatrix import verbs
    root = Path(rmx_sandbox.short_root("bnp.")) / "proj" / ".refmatrix"
    with pytest.raises(verbs.VerbArgsError) as e:
        verbs.memory(root, "brief", plan=_A_PLAN, compile=True)
    assert _names_both(str(e.value)), str(e.value)


def test_mcp_brief_with_plan_and_compile_is_an_error_naming_both():
    """The same refusal over the MCP `rmx_memory` tool: `isError`, and the text names both
    parameters. No daemon behind the root, as above."""
    from refmatrix import mcp
    root = Path(rmx_sandbox.short_root("bnm.")) / "proj" / ".refmatrix"
    reply = mcp.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "rmx_memory",
                   "arguments": {"action": "brief", "plan": _A_PLAN, "compile": True,
                                 "root": str(root)}}})
    result = reply["result"]
    text = result["content"][0]["text"]
    assert result["isError"], text
    assert _names_both(text), text


def test_the_memory_brief_op_refuses_plan_with_compile_itself(spawn):
    """Any caller of the op, not only the verb: a direct `memory_brief` op call with both, on
    a REAL spawned daemon, answers `ok: False` naming both. Without the op's own check the
    compile plan silently replaces the caller's (mutation G6)."""
    from refmatrix import daemon as dm
    ctx = spawn(seed_compilable)
    resp = dm.call(ctx.root, "memory_brief",
                   {"partition": ctx.part, "plan": _A_PLAN, "compile": True},
                   timeout=60, retries=0)
    assert resp.get("ok") is False, resp
    assert _names_both(str(resp.get("error"))), resp


def test_a_compiling_brief_gets_the_compile_budget_in_one_attempt(spawn, monkeypatch):
    """The clustering pass runs inside the op now, which the 10 s read budget was never sized
    for: a compiling brief's one `memory_brief` call carries MORE than the read budget (up to
    `MEMORY_COMPILE_TIMEOUT_S`) and is one attempt; a plain brief stays inside the read budget.
    Observed at the transport (`tests.timing.record_transport`, the 29.4 class-B observer) on a
    REAL daemon, so no test waits out either budget (rule 6). Mutation G8 (the compiling budget
    back to `MEMORY_READ_BUDGET_S`) fails here."""
    from refmatrix import daemon as dm, verbs
    from tests.timing import record_transport
    ctx = spawn(seed_compilable)
    calls = record_transport(monkeypatch, dm)
    verbs.memory(ctx.root, "brief", compile=True)
    verbs.memory(ctx.root, "brief")
    briefs = [c for c in calls if c["op"] == "memory_brief"]
    assert len(briefs) == 2, calls
    compiling, plain = briefs
    assert compiling["retries"] == 0 and plain["retries"] == 0, briefs
    assert verbs.MEMORY_READ_BUDGET_S < compiling["timeout"] <= verbs.MEMORY_COMPILE_TIMEOUT_S, \
        briefs
    assert plain["timeout"] <= verbs.MEMORY_READ_BUDGET_S, briefs
