"""bug-216 rev 6 — R14 (the `denotes_link` derive is a verb with a CLI and an MCP twin) and R6b
(prestage counts and names what its walk excluded, in the RESULT).

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#rev-6, #r14, #r6b, #ac-15, #ac-16).

WHY.
- R14 (green-216 flag 5, lead decision): "every capability an agent can call is a verb first;
  CLI and MCP expose it" (.claude/PROJECT_PROFILE.md #constraints). The derive ran only as
  `daemon.call(root, "denotes_link", ...)`, reachable by no agent and no operator command.
- R6b (flag 6, CLAUDE.md #no-silent-failures): the ingest walk returns what its ignore rules
  excluded (`ignored`), but prestage walked the same tree and sent its exclusions to the
  daemon's stderr log, which no caller reads.

Contracts these tests assume (confirm or rename in the spec):
- verb `rmx_derive_denotes`, function `verbs.derive_denotes(root, *, partition=None,
  timeout=None)`, CLI twin `rmx derive denotes` (the partition rides on the `rmx -p` group, as
  for `memory compile`), MCP tool generated from the verb;
- the result carries the op's counts `{added, concepts, targets, multi_target}` and the CLI
  prints each as `key=value`;
- prestage's result adds `ignored` (count) and `ignored_paths` (names), the shape of
  `_skip_fields`' `skipped` / `skipped_paths`; the CLI prints `render_ignored_line`.

The counts tests run the REAL op on an in-process `Daemon`; only the transport is replaced
(`verbs.require_daemon` -> up, `daemon.call` -> the op registry), the process boundary
registered as `external` in the mock registry. The daemon-down tests replace nothing.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import verbs
from refmatrix.ingest_gmd import ingest_gmd_paths
from refmatrix.store import Store

VERB = "rmx_derive_denotes"
COUNT_KEYS = ("added", "concepts", "targets", "multi_target")


def _gmd(doc_id: str, body: str = "Body.\n") -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "Fixture document"\ntags: [t]\n---\n\n'
            f"# Fixture document {{#root}}\n\n{body}")


@pytest.fixture
def env(monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="b216s", dir="/tmp")).resolve()
    proj = base / "proj"
    (proj / "docs").mkdir(parents=True)
    root = proj / ".refmatrix"
    root.mkdir()
    b = proj / "docs" / "b.md"
    b.write_text(_gmd("b-doc"))
    s = Store(root)
    s.init()
    try:
        ingest_gmd_paths(s, [b])
        s.add_concept("b-doc")          # + `b_doc` / `b doc` variants: 3 path-less concepts
    finally:
        s.close()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    monkeypatch.setattr(cli_mod, "_partition_override", None, raising=False)
    yield {"base": base, "proj": proj, "root": root}
    shutil.rmtree(base)


def _denotes_count(root: Path) -> int:
    s = Store(root)
    s.init()
    try:
        r = s._connect().execute(
            "SELECT count(*) FROM entity_links el JOIN linkage_types lt "
            "ON lt.id = el.linkage_id WHERE lt.name = 'denotes'").fetchone()
        return int(r[0])
    finally:
        s.close()


@pytest.fixture
def in_process_daemon(env, monkeypatch):
    """The daemon transport answered by the REAL op registry on an in-process Daemon."""
    d = daemon_mod.Daemon(env["root"])
    d.store = Store(env["root"])
    d.store.init()

    def _call(root, op, args, **kw):
        assert Path(root).resolve() == env["root"].resolve(), root
        return {"ok": True, "result": daemon_mod.OPS[op](d, dict(args))}
    monkeypatch.setattr(verbs, "require_daemon", lambda *a, **k: None)
    monkeypatch.setattr(daemon_mod, "call", _call)
    monkeypatch.setattr(daemon_mod, "ping", lambda *a, **k: True)
    yield d
    d.store.close()


# ---------------------------------------------------------------- AC-15 (R14)


def test_ac15_the_derive_is_a_verb_with_cli_and_mcp_twins():
    """Registration — after which tests/test_verb_parity.py's generic gates (tool == verb,
    schema, CLI twin resolves, wiring, click defaults) cover it."""
    import refmatrix.mcp as mcp
    assert VERB in verbs.VERBS, f"no `{VERB}` verb"
    assert verbs.CLI_MAP.get(VERB) == ("derive", "denotes"), verbs.CLI_MAP.get(VERB)
    assert verbs.CLI_WIRING.get(VERB) == "calls"
    assert VERB in mcp.TOOLS
    assert verbs.VERBS[VERB].fn.__name__ == "derive_denotes"


def test_ac15_the_verb_returns_the_ops_counts(env, in_process_daemon):
    res = verbs.VERBS[VERB].fn(env["root"])
    assert {k: res.get(k) for k in COUNT_KEYS} == \
        {"added": 3, "concepts": 3, "targets": 1, "multi_target": 0}, res
    assert _denotes_count(env["root"]) == 3


def test_ac15_the_cli_prints_the_ops_counts(env, in_process_daemon):
    r = CliRunner().invoke(cli_mod.main, ["derive", "denotes"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    for k, v in {"added": 3, "concepts": 3, "targets": 1, "multi_target": 0}.items():
        assert re.search(rf"\b{k}=({v})\b", r.output), f"`{k}={v}` not in:\n{r.output}"
    r2 = CliRunner().invoke(cli_mod.main, ["derive", "denotes"], catch_exceptions=False)
    assert r2.exit_code == 0 and re.search(r"\badded=0\b", r2.output), r2.output


def test_ac15_the_mcp_tool_returns_the_ops_counts(env, in_process_daemon):
    import refmatrix.mcp as mcp
    res = mcp.TOOLS[VERB]["fn"]({"root": str(env["root"])})
    assert "error" not in res, res
    assert {k: res.get(k) for k in COUNT_KEYS} == \
        {"added": 3, "concepts": 3, "targets": 1, "multi_target": 0}, res


def test_ac15_daemon_down_the_cli_fails_loudly_and_writes_nothing(env):
    """No daemon for this throwaway store: non-zero exit, the reason on stderr, and no
    in-process fallback (the store is untouched)."""
    r = CliRunner().invoke(cli_mod.main, ["derive", "denotes"])
    assert r.exit_code != 0, f"exit 0 with no daemon:\n{r.output}"
    assert r.exit_code != 2 or "No such command" not in (r.stderr or ""), (
        f"the command does not exist:\n{r.stderr}")
    assert "daemon" in (r.stderr or "").lower(), f"stderr does not say why:\n{r.stderr!r}"
    assert _denotes_count(env["root"]) == 0, "the CLI wrote links without a daemon"


def test_ac15_daemon_down_the_mcp_tool_returns_an_error(env):
    import refmatrix.mcp as mcp
    assert VERB in mcp.TOOLS, f"no `{VERB}` tool"
    res = mcp.TOOLS[VERB]["fn"]({"root": str(env["root"])})
    assert "error" in res and "daemon" in str(res["error"]).lower(), res
    assert _denotes_count(env["root"]) == 0


# ---------------------------------------------------------------- AC-16 (R6b)


@pytest.fixture
def memdir(env):
    mem = env["proj"] / "notes" / "memory"
    (mem / ".hidden").mkdir(parents=True)
    (mem / "keep_top.md").write_text(_gmd("keep_top"))
    (mem / ".hidden" / "y.md").write_text(_gmd("hidden_y"))
    return mem


def test_ac16_the_prestage_op_names_its_ignored_path_in_the_result(env, memdir):
    from refmatrix.daemon import Daemon, _op_prestage_hashes
    d = Daemon(env["root"])
    d.store = Store(env["root"])
    d.store.init()
    try:
        res = _op_prestage_hashes(d, {"targets": [str(memdir)]})
    finally:
        d.store.close()
    hidden = str(memdir / ".hidden" / "y.md")
    assert res.get("ignored") == 1, res
    assert [str(p) for p in res.get("ignored_paths") or []] == [hidden], res


def _prestage_cli(memdir: Path) -> str:
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--prestage", str(memdir)])
    assert r.exit_code == 0, r.output
    return r.stdout


def test_ac16_the_prestage_cli_names_its_ignored_path_daemon_down(env, memdir):
    """The CLI's no-daemon branch: the line is in the command's STDOUT (what it reports), not
    left to a stderr print inside the walk."""
    out = _prestage_cli(memdir)
    assert "ignored 1 path(s)" in out and str(memdir / ".hidden" / "y.md") in out, out


def test_ac16_the_prestage_cli_names_its_ignored_path_daemon_up(env, memdir, in_process_daemon):
    """The CLI's daemon branch prints what the OP returned."""
    out = _prestage_cli(memdir)
    assert "ignored 1 path(s)" in out and str(memdir / ".hidden" / "y.md") in out, out


def test_ac16_guard_the_memory_prestage_still_names_its_skips(env, memdir):
    """GUARD: `--as-memory` prestage already returns the memory walk's skips."""
    from refmatrix.daemon import Daemon, _op_prestage_hashes
    d = Daemon(env["root"])
    d.store = Store(env["root"])
    d.store.init()
    try:
        res = _op_prestage_hashes(d, {"targets": [str(memdir)], "as_memory": True})
    finally:
        d.store.close()
    skipped = (res.get("walk_skipped") or {}).get("skipped_paths") or []
    assert str(memdir / ".hidden" / "y.md") in [str(p) for p in skipped], res
