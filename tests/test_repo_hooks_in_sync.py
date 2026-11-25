"""plan-2 task 2.3 — THIS repo's installed hooks equal what its own generator
renders. Drift (a hand-edited or hand-added hook) fails the suite, which is
the point: hooks are generated, never authored (constitution X).

bug-170 (task-t0-suite-trust-sweep `#t0-2` R2.1, AC-2.1): the 23.0 sandbox moves `HOME` to
`/private/tmp/rmx-*/h`, and this test undid only `RMX_CLAUDE_HOOKS_DIR`, so the generator
rendered every `~`-relative path (the two `~/.claude/hooks/*.sh` commands and the SessionStart
memory dir) under the sandbox home and compared it with hooks installed under the real one:
3 HOME lines and 3 `script … differs` lines in every dev-tree run since 0.79.1 (2026-11-08
onward; 0.83.0 release suite, 2026-11-14). Clones skip the test, so no release saw it.

The comparison is `installed_hooks_diff(project_root, hooks_dir)`: the render with the REAL
home, captured before the redirect (`RMX_SANDBOX_REAL_HOME`), restored for that one render,
and the three user-global scripts read from `hooks_dir`; no `src/` change (`hooks.check` takes
no home, `hooks.py:737`); read-only. The tests below build an installed checkout in a tmp dir
the way an install under the real home writes it, so the main-tree condition is reproduced in
any checkout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from refmatrix import hooks as hooks_mod

REPO = Path(__file__).resolve().parents[1]

# `.claude/settings.json` is committed and its commands carry absolute paths,
# so a SECOND checkout of this commit (a detached `git worktree`, a clone)
# holds hooks belonging to the first. Comparing them there measures the path
# prefix, not drift — and failed the suite at the very sha under test
# (bug-054 / ch-bsd #m-5). The check runs where it means something.
_OWNER = hooks_mod.installed_root(REPO)


def installed_hooks_diff(project_root: Path, hooks_dir: Path) -> "tuple[bool, str]":
    """`hooks.check(project_root)` as the hooks were installed: rendered with the real home
    (`RMX_SANDBOX_REAL_HOME`) and the user-global scripts read from `hooks_dir`. Reads only;
    `HOME` and `RMX_CLAUDE_HOOKS_DIR` are what they were when it returns.

    bug-170 (T0.2 R2.1, 2026-11-15): this used to undo only `RMX_CLAUDE_HOOKS_DIR`, so the
    render ran under the sandbox `HOME` and every `~`-relative path differed from hooks
    installed under the real one. `hooks.check` takes no home (`hooks.py:737`; no `src/`
    change, ruling L122), so the real home is restored for this ONE render, and
    `RMX_CLAUDE_HOOKS_DIR` (which `search_hooks.hooks_dir()` reads) names the scripts compared.
    Every later test runs sandboxed again."""
    keys = ("HOME", "RMX_CLAUDE_HOOKS_DIR")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["HOME"] = os.environ["RMX_SANDBOX_REAL_HOME"]
    os.environ["RMX_CLAUDE_HOOKS_DIR"] = str(hooks_dir)
    try:
        return hooks_mod.check(project_root)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _real_home() -> Path:
    return Path(os.environ["RMX_SANDBOX_REAL_HOME"])


@pytest.mark.skipif(not (REPO / ".claude" / "rmx-hooks.json").exists(),
                    reason="not an rmx-hooks-managed checkout")
@pytest.mark.skipif(_OWNER is not None and _OWNER != REPO,
                    reason="hooks belong to another checkout of this commit")
def test_installed_hooks_match_generated():
    # This test checks the REAL checkout against the REAL ~/.claude/hooks (read-only), rendered
    # with the real home the hooks were installed under (bug-170).
    ok, diff = installed_hooks_diff(REPO, _real_home() / ".claude" / "hooks")
    assert ok, "hooks drift — run `rmx install-hooks --apply --force`:\n" + diff


# ---- bug-170: the comparison, on a checkout installed under the real home ------------------

def _install_under_real_home(tmp_path: Path, monkeypatch) -> "tuple[Path, Path, dict]":
    """A tmp checkout whose `.claude/settings.json` and user-global scripts are what
    `rmx install-hooks --apply` writes under the REAL home, with this repo's recorded flags:
    the main tree's state, reproduced in any checkout. Renders with `HOME` set to the real home
    (read-only: nothing is written there), and writes only under `tmp_path`."""
    from refmatrix import search_hooks
    proj = (tmp_path / "proj").resolve()
    hooks_dir = (tmp_path / "installed-hooks").resolve()
    (proj / ".claude").mkdir(parents=True)
    hooks_dir.mkdir()
    flags_file = REPO / ".claude" / "rmx-hooks.json"
    (proj / ".claude" / "rmx-hooks.json").write_text(flags_file.read_text())
    flags = json.loads(flags_file.read_text()).get("flags") or {}
    with monkeypatch.context() as m:
        m.setenv("HOME", str(_real_home()))
        m.setenv("RMX_CLAUDE_HOOKS_DIR", str(hooks_dir))
        block = hooks_mod.render_managed(proj, flags)
        scripts = search_hooks.render_scripts()
    (proj / ".claude" / "settings.json").write_text(json.dumps({"hooks": block["hooks"]}))
    for name, content in scripts.items():
        (hooks_dir / name).write_text(content)
    return proj, hooks_dir, scripts


def _drift(diff: str) -> list:
    """The lines that make `check` fail (`? ` lines are foreign hooks, listed, never failed)."""
    return [ln for ln in diff.splitlines() if ln and not ln.startswith("? ")]


def test_bug170_the_comparison_renders_with_the_home_the_hooks_were_installed_with(
        tmp_path, monkeypatch):
    """R2.1: hooks installed under the real home compare clean. At c4b44d0 the render ran under
    the sandbox home: `- PostToolUse/Grep: …<real home>/.claude/hooks/grep-tool-teach.sh` /
    `+ …/private/tmp/rmx-…/h/.claude/hooks/…`, the same for `grep-rewrite-guard.sh` and the
    SessionStart memory dir, plus `script … differs` x3 (bug-170's E lines)."""
    proj, hooks_dir, _ = _install_under_real_home(tmp_path, monkeypatch)
    ok, diff = installed_hooks_diff(proj, hooks_dir)
    assert ok and not _drift(diff), (
        "hooks installed under the real home do not compare clean; the render is not using "
        "the home they were installed with (bug-170):\n" + diff)


def test_bug170_ac21_one_changed_script_byte_is_the_only_drift(tmp_path, monkeypatch):
    """AC-2.1: with the scripts dir a copy of the installed one with ONE byte of one script
    changed, the comparison reports that script `differs`, and nothing else: it looks at real
    content, and the HOME-derived entries match. (Mutation M2.2, the comparison skips the
    scripts: this goes green, so the test is red.)"""
    proj, hooks_dir, scripts = _install_under_real_home(tmp_path, monkeypatch)
    name = sorted(scripts)[0]
    f = hooks_dir / name
    data = bytearray(f.read_bytes())
    i = data.index(b"#") if b"#" in data else 0
    data[i] = ord("@") if data[i] != ord("@") else ord("#")
    f.write_bytes(bytes(data))
    ok, diff = installed_hooks_diff(proj, hooks_dir)
    assert not ok, f"a changed byte in {name} was not reported:\n{diff}"
    assert _drift(diff) == [f"- script {name} differs from the generator's render "
                            "(rmx install-hooks --apply --force)"], (
        f"expected exactly one drift line, for {name}; got:\n{diff}")


def test_bug170_the_comparison_restores_the_sandbox_and_writes_nothing(tmp_path,
                                                                       monkeypatch):
    """R2.1: the real home is restored for ONE render. After the call, `HOME` and
    `RMX_CLAUDE_HOOKS_DIR` are the sandbox's again (every later test still runs sandboxed),
    and the installed files it read are byte-for-byte and mtime unchanged."""
    proj, hooks_dir, _ = _install_under_real_home(tmp_path, monkeypatch)
    files = [proj / ".claude" / "settings.json", proj / ".claude" / "rmx-hooks.json",
             *sorted(hooks_dir.iterdir())]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    env_before = {k: os.environ.get(k) for k in ("HOME", "RMX_CLAUDE_HOOKS_DIR")}
    installed_hooks_diff(proj, hooks_dir)
    assert {k: os.environ.get(k) for k in env_before} == env_before
    assert sorted(hooks_dir.iterdir()) == files[2:], "the comparison wrote into the hooks dir"
    for p, (data, mtime) in before.items():
        assert (p.read_bytes(), p.stat().st_mtime_ns) == (data, mtime), f"{p} was written"


# ---- H1.a AC-2: this checkout's agents and commands are the packaged ones (bug-319) --------
#
# `rmx init` installs refmatrix/templates/{agents,commands}/*.md; this repo is one more project
# that installed them, so each `.claude/` file with a packaged name equals what the installer
# writes, byte for byte. At 8c4c9eb3 the template's gmd-curator.md lacked the GMD frontmatter,
# the MCP tools, the overlay and the raw-`git` sections this repo's copy had, and cat-herder
# shipped a third, pre-task-3.7 copy (bug-319, task-H1.a AC-2). The ONE allowed difference is the
# frontmatter `id:` line: an installed GMD doc carries its project's id (`refmatrix/gmd-curator`).
# The comparison needs no hooks and no home, so it runs in any checkout (a clone included).

def _without_frontmatter_id(text: str) -> str:
    """`text` with the `id:` line of its leading frontmatter block removed (nothing else)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            break
        if lines[i].startswith("id: "):
            return "".join(lines[:i] + lines[i + 1:])
    return text


def installed_template_drift(checkout: Path,
                             tmp_path: Path) -> "tuple[list[str], list[str]]":
    """(drift, written): one drift line per `<checkout>/.claude/{agents,commands}/<name>` that
    differs from what `install_agents` + `install_commands` write for <name>, the frontmatter
    `id:` line excepted.
    `written` names every file the installer wrote (`agents/x.md`, `commands/y.md`). It writes
    into a fresh tmp project and a tmp user dir; `checkout` is only read."""
    from refmatrix.init_agents import install_agents, install_commands
    proj = tmp_path / "fresh"
    user = tmp_path / "user-commands"
    install_agents(proj, force=True)
    install_commands(proj, force=True, user_dir=user, backup_dir=tmp_path / "backups")
    written = {f"agents/{p.name}": p for p in (proj / ".claude" / "agents").glob("*.md")}
    written |= {f"commands/{p.name}": p for p in (proj / ".claude" / "commands").glob("*.md")}
    written |= {f"commands/{p.name}": p for p in user.glob("*.md")}
    drift = []
    for rel, packaged in sorted(written.items()):
        mine = checkout / ".claude" / rel
        if not mine.is_file():
            continue
        want = _without_frontmatter_id(packaged.read_text(encoding="utf-8"))
        have = _without_frontmatter_id(mine.read_text(encoding="utf-8"))
        if have != want:
            pairs = zip(have.splitlines() + [None], want.splitlines() + [None])
            first = next((i for i, (a, b) in enumerate(pairs, 1) if a != b),
                         "end (line endings)")
            drift.append(f".claude/{rel} differs from the packaged copy (first at line {first})")
    return drift, sorted(written)


def test_installed_agents_and_commands_equal_the_packaged_templates(tmp_path):
    drift, written = installed_template_drift(REPO, tmp_path)
    # the installer really wrote the nine files H1.a reconciles; an empty install passes nothing
    assert {"agents/gmd-curator.md", "commands/commit-state.md", "commands/save-state.md",
            "commands/recall-state.md"} <= set(written), written
    assert (REPO / ".claude" / "agents" / "gmd-curator.md").is_file()
    assert not drift, ("installed copies drifted from src/refmatrix/templates/ — edit the "
                       "template, then reinstall it here:\n" + "\n".join(drift))


@pytest.mark.parametrize("rel", ["agents/gmd-curator.md", "commands/commit-state.md"])
def test_installed_template_drift_fails_on_a_planted_one_line_edit(tmp_path, rel):
    """AC-2's must-fail case: a checkout whose copy equals the package except ONE body line
    is reported, and an `id:` line that differs is not (the one allowed difference)."""
    from importlib import resources
    kind, name = rel.split("/")
    text = (resources.files(f"refmatrix.templates.{kind}") / name).read_text(encoding="utf-8")
    checkout = tmp_path / "checkout"
    (checkout / ".claude" / kind).mkdir(parents=True)
    target = checkout / ".claude" / rel
    lines = text.splitlines(keepends=True)
    if lines[0] == "---\n" and not any(ln.startswith("id: ") for ln in lines[1:8]):
        lines.insert(1, "id: some-project/x\n")      # a project's id never counts as drift
    else:
        lines = [("id: some-project/x\n" if ln.startswith("id: ") else ln) for ln in lines]
    target.write_text("".join(lines), encoding="utf-8")
    assert installed_template_drift(checkout, tmp_path / "a")[0] == [], "the id line counted"
    body = len(lines) - 3
    lines[body] = lines[body].rstrip("\n") + " (edited)\n"
    target.write_text("".join(lines), encoding="utf-8")
    drift = installed_template_drift(checkout, tmp_path / "b")[0]
    assert len(drift) == 1 and drift[0].startswith(f".claude/{rel} differs"), drift
