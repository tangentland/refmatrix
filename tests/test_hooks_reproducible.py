"""plan-2 hooks-reproducible (ch-bsd #bs-4, #sk-5).

The Claude Code hook config a project runs is PRODUCED by `rmx install-hooks`
and PROVEN by `rmx install-hooks --check`. Four hand-authored hooks lived only
in this repo's settings.local.json on 2026-09-14; a forced reinstall would have
deleted them, and the PreCompact save-state swallowed the bridge failure the
code was built to shout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import hooks as hooks_mod
from refmatrix.hooks import _claude_hook_block, install


def _cmds(block, event=None):
    out = []
    for ev, entries in block["hooks"].items():
        if event and ev != event:
            continue
        for e in entries:
            for h in e.get("hooks", []):
                out.append((ev, e.get("matcher"), h["command"]))
    return out


MEMORY_PATH_MARKERS = ("memory recall", "ingest-gmd", "save-state", "focus summarize")


def _project(tmp_path, *, enforce_scripts=False):
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    if enforce_scripts:
        hd = proj / ".claude" / "hooks"
        hd.mkdir(parents=True)
        for n in ("enforce-test-to-file.sh", "enforce-rmx-grep.sh", "adr-gate.sh"):
            (hd / n).write_text("#!/bin/sh\nexit 0\n")
        (proj / ".claude" / "p20-0").mkdir()
        (proj / ".claude" / "p20-0" / "compile_guardrails.py").write_text("")
    return proj


# ---- 2.1 the production hooks are first-class generator options ----

def test_precompact_checkpoint_is_loud_and_no_sync(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    pre = [c for _, _, c in _cmds(block, "PreCompact")]
    ss = [c for c in pre if "rmx save-state" in c]
    assert ss, "PreCompact must checkpoint via save-state"
    # task-compaction-as-handoff R1 (L195, 2026-11-24): PreCompact's save-state runs WITH
    # promote, first; it was `--no-promote` beside a separate `focus summarize --promote`.
    assert "--no-sync" in ss[0] and "--no-promote" not in ss[0], ss[0]
    assert ">/dev/null" not in ss[0] and "|| true" not in ss[0]
    off = _claude_hook_block(tmp_path / ".refmatrix", precompact_checkpoint=False)
    assert not [c for _, _, c in _cmds(off, "PreCompact") if "save-state" in c]


def test_stop_promotes_stm_loud(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    stop = [c for _, _, c in _cmds(block, "Stop")]
    prom = [c for c in stop if "focus summarize --promote" in c]
    assert prom and "2>/dev/null" not in prom[0] and "|| true" not in prom[0]
    off = _claude_hook_block(tmp_path / ".refmatrix", stop_promote=False)
    assert not [c for _, _, c in _cmds(off, "Stop") if "focus summarize" in c]


def test_resume_focus_context_entry(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    hits = [(m, c) for _, m, c in _cmds(block, "SessionStart") if "focus context --top 15" in c]
    assert hits and hits[0][0] == "resume"
    assert "2>/dev/null" not in hits[0][1]


def test_scan_prompt_composite_every(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    scan = [c for _, _, c in _cmds(block, "UserPromptSubmit") if "scan-prompt" in c]
    assert scan and "--composite-every 3" in scan[0]
    none = _claude_hook_block(tmp_path / ".refmatrix", composite_every=None)
    assert "--composite-every" not in [c for _, _, c in _cmds(none, "UserPromptSubmit") if "scan-prompt" in c][0]


def test_bridge_catch_up_is_detached_and_loud(tmp_path):
    block = _claude_hook_block(tmp_path / ".refmatrix")
    bridge = [c for _, _, c in _cmds(block, "SessionStart") if "ingest-gmd --as-memory" in c]
    assert bridge, "SessionStart bridge catch-up missing"
    assert "--detach" in bridge[0]
    assert ">/dev/null" not in bridge[0] and "|| true" not in bridge[0]
    # and it is NOT buried in the sync/primer background group
    assert "rmx primer" not in bridge[0]


def test_enforce_entries_follow_scripts_on_disk(tmp_path):
    with_scripts = _project(tmp_path, enforce_scripts=True)
    block = _claude_hook_block(with_scripts / ".refmatrix", project_root=with_scripts)
    pre = [c for _, _, c in _cmds(block, "PreToolUse")]
    assert any("enforce-test-to-file.sh" in c for c in pre)
    assert any("enforce-rmx-grep.sh" in c for c in pre)
    assert any("adr-gate.sh" in c for _, _, c in _cmds(block, "PostToolUse"))
    assert any("compile_guardrails.py" in c for _, _, c in _cmds(block, "SessionStart"))
    bare = _project(tmp_path / "b")
    block2 = _claude_hook_block(bare / ".refmatrix", project_root=bare)
    # match the script paths, not bare substrings: pytest's tmp dir carries
    # this test's own name ("…test-enforce-entries…") inside the memdir path.
    leaked = [c for _, _, c in _cmds(block2)
              if ".claude/hooks/enforce-" in c or ".claude/hooks/adr-gate" in c
              or "compile_guardrails" in c]
    assert not leaked, leaked
    forced_off = _claude_hook_block(with_scripts / ".refmatrix", project_root=with_scripts, enforce=False)
    assert not any(".claude/hooks/enforce-" in c for _, _, c in _cmds(forced_off))


def test_no_memory_path_hook_is_silenced(tmp_path):
    """Everything between a memory file and the store shouts. Non-memory
    plumbing (sync flush, primer, focus events) may stay quiet."""
    block = _claude_hook_block(tmp_path / ".refmatrix")
    for ev, _, c in _cmds(block):
        if any(m in c for m in MEMORY_PATH_MARKERS):
            assert "2>/dev/null" not in c, f"{ev}: silenced memory path: {c}"
            assert "|| true" not in c, f"{ev}: swallowed exit on memory path: {c}"


# ---- 2.2 settings.json target, recorded flags, --check ----

def _apply(proj, **flags):
    return install(project_root=proj, refmatrix_root=proj / ".refmatrix",
                   git=False, claude=True, briefing=False, agent_env=False,
                   search=False, scope="project", apply=True, force=True, **flags)


def test_apply_writes_settings_json_and_records_flags(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    assert settings.exists()
    assert not (proj / ".claude" / "settings.local.json").exists()
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["memory_hooks"] is True and "version" in rec
    ok, diff = hooks_mod.check(proj)
    assert ok, diff


def test_check_detects_hand_edit(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    ent = d["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    ent["command"] = ent["command"] + " --composite-every 9"
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "--composite-every 9" in diff


def test_check_reports_missing_generated_entry(tmp_path):
    proj = _project(tmp_path)
    _apply(proj)
    settings = proj / ".claude" / "settings.json"
    d = json.loads(settings.read_text())
    del d["hooks"]["PreCompact"]
    settings.write_text(json.dumps(d))
    ok, diff = hooks_mod.check(proj)
    assert not ok and "PreCompact" in diff


def test_force_keeps_foreign_hooks_and_other_keys(tmp_path):
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    settings = proj / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "x.sh"},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
    }))
    _apply(proj); _apply(proj)
    d = json.loads(settings.read_text())
    assert d["statusLine"]["command"] == "x.sh"
    cmds = [h["command"] for blks in d["hooks"].values() for b in blks for h in b["hooks"]]
    assert cmds.count("echo mine") == 1
    assert sum("focus hook --event say" in c for c in cmds) == 1


def test_apply_strips_rmx_hooks_from_legacy_local_file(tmp_path):
    """Pre-0.67 installs wrote settings.local.json; leaving that copy in place
    would fire every rmx hook twice."""
    proj = _project(tmp_path)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    local = proj / ".claude" / "settings.local.json"
    local.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "export RMX_INVOCATION_SOURCE=hook; rmx focus hook --event say"},
            {"type": "command", "command": "echo keep-me"}]}]},
    }))
    _apply(proj)
    d = json.loads(local.read_text())
    assert d["permissions"]["allow"] == ["Bash(ls:*)"]
    cmds = [h["command"] for blks in d.get("hooks", {}).values() for b in blks for h in b["hooks"]]
    assert cmds == ["echo keep-me"]


def test_enforce_entries_are_rmx_managed(tmp_path):
    """The template's enforcement hooks count as rmx-managed so --force
    replaces them and --check covers them."""
    for c in ('[ -x "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-rmx-grep.sh" ] && ...',
              '"$CLAUDE_PROJECT_DIR/.claude/hooks/adr-gate.sh" 2>/dev/null || true',
              'python3 "$CLAUDE_PROJECT_DIR/.claude/p20-0/compile_guardrails.py"'):
        assert hooks_mod._is_rmx_hook(c)


# ---- CLI surface ----

def test_install_hooks_cli_check_exit_code(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    proj = _project(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: proj / ".refmatrix")
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--check"])
    assert r.exit_code == 1 and "rmx-hooks.json" in r.output
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--no-git", "--no-briefing",
                                          "--no-agent-env", "--no-search", "--apply", "--force"])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--check"])
    assert r.exit_code == 0, r.output


def test_install_hooks_cli_flags_reach_the_block(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    proj = _project(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda: proj / ".refmatrix")
    r = CliRunner().invoke(cli_mod.main, ["install-hooks", "--no-git", "--no-briefing",
                                          "--no-agent-env", "--no-search", "--no-memory-hooks",
                                          "--no-precompact-checkpoint", "--composite-every", "5",
                                          "--apply", "--force"])
    assert r.exit_code == 0, r.output
    d = json.loads((proj / ".claude" / "settings.json").read_text())
    rendered = json.dumps(d)
    assert "memory recall" not in rendered and "save-state" not in rendered
    assert "--composite-every 5" in rendered
    rec = json.loads((proj / ".claude" / "rmx-hooks.json").read_text())
    assert rec["flags"]["memory_hooks"] is False and rec["flags"]["composite_every"] == 5


def test_ingest_gmd_detach_without_daemon_fails_loud(tmp_path, monkeypatch):
    """The SessionStart bridge uses --detach so it returns immediately; with
    no daemon that must be an error line, not a 25 s foreground ingest."""
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod
    memdir = tmp_path / "mem"; memdir.mkdir()
    (memdir / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\n')
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: False)
    r = CliRunner().invoke(cli_mod.main, ["ingest-gmd", "--as-memory", "--detach", str(memdir)])
    assert r.exit_code != 0
    assert "no daemon" in r.output.lower()


# ---- task-I1.b1: --check over every instruction artifact (ADR-0007 #installed-equals-generated)
#
# Through the dev `rmx` in the sandbox project (tests/instruction_units_support.py). AC-4: a
# file is generated (equal to its render), drift (a template name whose content differs: a
# failure for rules, skills and git hooks, printed only for agents and commands until H1.c,
# #agents-leg) or local (listed; its fixtures run); a compiled file that differs from a fresh
# compile fails and names `--apply`. AC-5: every `.git/hooks/<name>` carrying the refmatrix
# marker is compared (bug-209).

import shutil as _shutil  # noqa: E402
import subprocess as _subprocess  # noqa: E402
import sys as _sys  # noqa: E402
from importlib import resources as _resources  # noqa: E402

from tests import instruction_units_support as _iu  # noqa: E402

_LOCAL_TOKENS = ("sample-deny.md", "sample-gate.md", "sample-context.md", "sample-check.md",
                 "sample-rule.md", "sample-skill")
_PACKAGED_RULE = Path(".claude") / "rules" / "sample-packaged-rule.md"
_AGENT = Path(".claude") / "agents" / "gmd-curator.md"


@pytest.fixture(scope="module")
def _overlay(tmp_path_factory):
    """A refmatrix that ships one packaged rule (see `build_overlay_site`): the child PYTHONPATH."""
    site = _iu.build_overlay_site(tmp_path_factory.mktemp("site"))
    return _iu.overlay_pythonpath(site)


def _held_writer(root: Path):
    """The sandbox store opened read-write in THIS process: its catalog's writer lock is held
    until `close()`. Proven held: a second process cannot open the catalog file."""
    from refmatrix.store import Store
    s = Store(root)
    s.init()          # opens the connection (Store connects lazily) and keeps it open
    probe = _subprocess.run([_sys.executable, "-c",
                             "import duckdb, sys; duckdb.connect(sys.argv[1])", str(s.db_path)],
                            capture_output=True, text=True, timeout=30)
    assert probe.returncode != 0, "the writer lock is not held; the case would prove nothing"
    return s


_CLASS_CASES = ["clean", "clean-beside-held-writer", "rule-drift", "local-edited",
                "fire-broken", "agent-drift", "rule-edited-apply-without-force"]


@pytest.mark.parametrize("case", _CLASS_CASES)
def test_check_classes(case, _overlay):
    """AC-4 (task-I1.b1 #d5 #d6). After `--apply`, `--check` exits 0 and lists the local
    files; then one change per case: a generated rule edited is `drift` with its diff, exit 1;
    a local unit edited leaves the compiled file out of sync, exit 1, the line names
    `--apply`; a local unit's `fire` envelope broken (and re-applied) fails naming the unit
    and the envelope; a packaged agent edited is printed as drift, exit 0. No daemon is up;
    one clean run is made beside a held writer lock to show `--check` does not wait on it."""
    root, proj = _iu.sandbox()
    pp = dict(PYTHONPATH=_overlay)
    _iu.install_local(proj)
    agent = proj / _AGENT
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text(_resources.files("refmatrix.templates.agents")
                     .joinpath("gmd-curator.md").read_text(encoding="utf-8"), encoding="utf-8")
    r = _iu.apply(root, **pp)
    assert r.returncode == 0, _iu.out_of(r)
    rule = proj / _PACKAGED_RULE

    if case.startswith("clean"):
        held = _held_writer(root) if case == "clean-beside-held-writer" else None
        try:
            r = _iu.check(root, timeout=30, **pp)
        finally:
            if held is not None:
                held.close()
        out = _iu.out_of(r)
        assert r.returncode == 0, out
        for tok in _LOCAL_TOKENS:
            assert _iu.lines_with(out, "local", tok), f"{tok} is not listed as local:\n{out}"
        assert not [ln for ln in out.splitlines() if "drift" in ln.lower()
                    and "hooks drift" not in ln], f"a freshly applied project shows drift:\n{out}"
        return

    if case == "rule-drift":
        assert rule.exists(), f"--apply did not install the packaged rule at {rule}"
        r = _iu.check(root, **pp)
        assert r.returncode == 0, _iu.out_of(r)
        rule.write_text(rule.read_text() + "\nHAND-EDIT-7c1: a local exception.\n")
        r = _iu.check(root, **pp)
        out = _iu.out_of(r)
        assert r.returncode == 1, f"an edited generated rule did not fail --check:\n{out}"
        assert _iu.lines_with(out, "drift", "sample-packaged-rule.md"), out
        assert not _iu.lines_with(out, "local", "sample-packaged-rule.md"), (
            f"a template-named rule was classed local:\n{out}")
        assert "HAND-EDIT-7c1" in out, f"the drift's diff is not shown:\n{out}"
    elif case == "local-edited":
        f = proj / ".claude" / "triggers" / "sample-deny.md"
        f.write_text(f.read_text().replace("SAMPLE-DENY-TEXT:", "SAMPLE-DENY-TEXT (edited):"))
        r = _iu.check(root, **pp)
        out = _iu.out_of(r)
        assert r.returncode == 1, f"a stale compiled file read as in sync:\n{out}"
        assert _iu.lines_with(out, "rmx-instructions.json", "--apply"), (
            f"no line names the compiled file and --apply:\n{out}")
    elif case == "fire-broken":
        f = proj / ".claude" / "triggers" / "sample-deny.md"
        text = f.read_text()
        broken = text.replace('{command: "rmfoo --all build/"}', '{command: "echo nothing"}', 1)
        assert broken != text
        f.write_text(broken)
        r = _iu.apply(root, **pp)
        assert r.returncode == 0, _iu.out_of(r)
        r = _iu.check(root, **pp)
        out = _iu.out_of(r)
        assert r.returncode == 1, f"a failing fire fixture did not fail --check:\n{out}"
        assert _iu.lines_with(out, "sample-deny", "fire"), (
            f"no line names the unit and its envelope:\n{out}")
    elif case == "agent-drift":
        agent.write_text(agent.read_text() + "\nHAND-EDIT-a9: a project-local line.\n")
        r = _iu.check(root, **pp)
        out = _iu.out_of(r)
        assert r.returncode == 0, f"agent drift failed --check before H1.c (#agents-leg):\n{out}"
        assert _iu.lines_with(out, "drift", "gmd-curator.md"), (
            f"the edited packaged agent is not printed as drift:\n{out}")
    elif case == "rule-edited-apply-without-force":
        # g-3 (bsd-i1b1 r1, mutant X1): every other case applies with --force, so the guard that
        # keeps a hand-edited installed rule from a plain `--apply` was unpinned.
        assert rule.exists(), f"--apply did not install the packaged rule at {rule}"
        edited = rule.read_bytes() + b"\nHAND-EDIT-g3: kept until --force.\n"
        rule.write_bytes(edited)
        args = [a for a in _iu.APPLY_ARGS if a != "--force"]
        args.insert(1, "--no-git")
        r = _iu.rmx(root, *args, **pp)
        out = _iu.out_of(r)
        assert "--force" not in r.args, r.args
        assert rule.read_bytes() == edited, (
            f"a plain --apply (no --force) overwrote a hand-edited installed rule:\n{out}")
        assert _iu.lines_with(out, "skip", "sample-packaged-rule.md"), (
            f"no `skip` line names the rule --apply left alone:\n{out}")
    else:
        raise AssertionError(case)


_GIT_CASES = ["marked-body-rewritten", "unmarked-hook-listed", "marked-hook-unknown-name"]


@pytest.mark.parametrize("case", _GIT_CASES)
def test_check_covers_git_hooks(case):
    """AC-5 (bug-209). Installed git hooks compare clean; a hook that keeps the refmatrix marker
    but runs another body (the pre-26.2 silent one) fails `--check`, named; a hook without the
    marker is listed, not failed."""
    root, proj = _iu.sandbox()
    _subprocess.run(["git", "init", "-q", str(proj)], check=True, capture_output=True,
                    timeout=10)
    r = _iu.apply(root, git=True)
    assert r.returncode == 0, _iu.out_of(r)
    hooks_dir = proj / ".git" / "hooks"
    hook = hooks_dir / "post-merge"
    assert hook.exists() and "# refmatrix" in hook.read_text(), hook
    r = _iu.check(root)
    assert r.returncode == 0, _iu.out_of(r)
    if case == "marked-body-rewritten":
        hook.write_text("#!/usr/bin/env bash\n# refmatrix: refresh after merge\n"
                        'rmx sync --since ORIG_HEAD >/dev/null 2>&1 || true\n')
        r = _iu.check(root)
        out = _iu.out_of(r)
        assert r.returncode == 1, f"a rewritten refmatrix git hook read as in sync:\n{out}"
        assert _iu.lines_with(out, "post-merge"), f"the drifted hook is not named:\n{out}"
        # m-1 (bsd-i1b1 r1): settings.json is in sync here; the failure line must not blame it.
        assert not _iu.lines_with(out, "hooks drift", "settings.json"), (
            f"a git-hook-only drift is reported as settings.json drift:\n{out}")
    elif case == "marked-hook-unknown-name":
        # g-4 (bsd-i1b1 r1, mutant X3): a refmatrix-marked hook this version does not render
        # (one an older version installed) is drift: bug-209's own class.
        stale = hooks_dir / "pre-push"
        stale.write_text("#!/usr/bin/env bash\n# refmatrix: an older version's hook\n"
                         "rmx sync >/dev/null 2>&1 || true\n")
        stale.chmod(0o755)
        r = _iu.check(root)
        out = _iu.out_of(r)
        assert r.returncode == 1, f"a marked hook with no generated counterpart passed:\n{out}"
        assert _iu.lines_with(out, "pre-push"), f"the stale marked hook is not named:\n{out}"
    else:
        mine = hooks_dir / "pre-push"
        mine.write_text("#!/bin/sh\necho mine\n")
        mine.chmod(0o755)
        r = _iu.check(root)
        out = _iu.out_of(r)
        assert r.returncode == 0, f"a hook without the marker failed --check:\n{out}"
        assert _iu.lines_with(out, "pre-push"), f"the unmarked hook is not listed:\n{out}"


# ---- the fold of bsd-i1b1 r1: s-1 (no compiled file) and s-3 (a local unit at a packaged path)

@pytest.mark.parametrize("units", ["zero-units", "one-unit"])
def test_check_compiled_file_absent(units):
    """s-1 (bsd-i1b1 r1, lead ruling (a)). A git project whose layers compile to zero units
    and that holds no `.claude/rmx-instructions.json` is in sync: the compiled file is
    `generated`, so release step 3 drops no new file into a consumer with no units (spec
    risk 3). With one local unit and no compiled file, `--check` exits 1 naming it `missing`."""
    root, proj = _iu.sandbox()
    _subprocess.run(["git", "init", "-q", str(proj)], check=True, capture_output=True,
                    timeout=10)
    if units == "one-unit":
        _iu.install_local(proj, ids=("sample-deny",))
    r = _iu.apply(root, git=True)
    assert r.returncode == 0, _iu.out_of(r)
    (proj / _iu.COMPILED).unlink(missing_ok=True)
    r = _iu.check(root)
    out = _iu.out_of(r)
    if units == "zero-units":
        assert r.returncode == 0, f"a unit-less project without a compiled file fails:\n{out}"
        assert _iu.lines_with(out, "generated", "rmx-instructions.json"), (
            f"the absent zero-unit compiled file is not classed generated:\n{out}")
    else:
        assert r.returncode == 1, f"a missing compiled file with a unit read as in sync:\n{out}"
        assert _iu.lines_with(out, "missing", "rmx-instructions.json"), out


@pytest.fixture(scope="module")
def _overlay_with_triggers(tmp_path_factory):
    """A refmatrix that ships a packaged deny and a packaged check (never installed: they
    compile from the package) beside the packaged rule."""
    site = _iu.build_overlay_site(tmp_path_factory.mktemp("site-s3"),
                                  ships=("rules/sample-packaged-rule.md",
                                         "triggers/sample-packaged-deny.md",
                                         "checks/sample-packaged-check.md"))
    return _iu.overlay_pythonpath(site)


@pytest.mark.parametrize("layer", ["triggers/sample-packaged-deny.md",
                                   "checks/sample-packaged-check.md"])
def test_apply_refuses_a_local_unit_at_a_packaged_path(layer, _overlay_with_triggers):
    """s-3 (bsd-i1b1 r1). Packaged triggers and checks are never installed, so a local file at
    a packaged trigger's or check's `.claude/` path is not an installed copy: it is a local
    unit the loader used to drop silently (`--apply` exit 0, `--check` then asked for
    `--apply --force`, which installs no trigger). It is refused, named."""
    root, proj = _iu.sandbox()
    pp = dict(PYTHONPATH=_overlay_with_triggers)
    r = _iu.apply(root, **pp)
    assert r.returncode == 0, _iu.out_of(r)
    before = _iu.compiled_bytes(proj)
    kind = "deny" if layer.startswith("triggers/") else "check"
    sample = _iu.sample_path("sample-deny" if kind == "deny" else "sample-check")
    local = proj / ".claude" / layer
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(sample.read_text().replace(f"id: sample-{kind}\n", "id: local-shadow\n", 1))
    r = _iu.apply(root, **pp)
    err = r.stderr or ""
    assert r.returncode != 0, (
        f"a local unit at a packaged path was accepted (dropped):\n{_iu.out_of(r)}")
    assert "duplicate path with a packaged unit" in err, err
    assert layer in err, f"stderr does not name {layer}:\n{err}"
    assert _iu.compiled_bytes(proj) == before, "a refused --apply changed the compiled file"
