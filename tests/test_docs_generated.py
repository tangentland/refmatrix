"""plan-6 task 6.2: the CLI tree in docs/ARCHITECTURE.md and the hooks table
in README.md are RENDERED from the code, never hand-drawn. The hand-drawn
tree that lived at ARCHITECTURE.md {#cli-hook-surface} until 2026-09-14 was
missing `hub`, `focus`, `bus`, `task`, `schedule`, `refine`, ... — every
command added after it was written. These tests fail the moment a command
or a hook is added without re-running `scripts/gen-cli-tree.py`."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import click

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "gen-cli-tree.py"
ARCH = REPO / "docs" / "ARCHITECTURE.md"
README = REPO / "README.md"


def _load():
    spec = importlib.util.spec_from_file_location("gen_cli_tree", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_tree_section_equals_its_render():
    gen = _load()
    assert gen.extract(ARCH.read_text(), "cli-tree") == gen.render_cli_tree()


def test_hooks_table_section_equals_its_render():
    gen = _load()
    assert gen.extract(README.read_text(), "hooks-table") == gen.render_hooks_table()


def test_render_lists_every_visible_command_and_no_hidden_alias():
    """The render walks the click tree — a hand list would miss new groups."""
    from refmatrix.cli import main
    gen = _load()
    tree = gen.render_cli_tree()
    visible, hidden = [], []

    def walk(grp: click.Group, prefix: str) -> None:
        for name, cmd in grp.commands.items():
            (hidden if cmd.hidden else visible).append(name)
            if isinstance(cmd, click.Group) and not cmd.hidden:
                walk(cmd, prefix + name + " ")
    walk(main, "")
    assert visible and hidden
    for name in visible:
        assert f" {name} " in tree or f"── {name}\n" in tree or f"── {name} " in tree, name
    for name in hidden:
        assert f"── {name}" not in tree, name
    # the alias count is rendered, not asserted by hand
    assert f"{len(hidden)} hidden hyphenated aliases" in tree


def test_render_follows_the_click_tree_it_is_given():
    """Shape check on a tiny group: nesting, one-line help, group expansion."""
    gen = _load()

    @click.group()
    def root():
        """root help"""

    @root.group()
    def grp():
        """a group"""

    @grp.command()
    def leaf():
        """leaf help line one.

        line two must not appear."""

    @root.command(hidden=True)
    def old_alias():
        """hidden"""

    out = gen.render_cli_tree(root, name="tool")
    assert "tool\n" in out
    assert "└── grp" in out and "a group" in out
    assert "leaf" in out and "leaf help line one." in out
    assert "line two" not in out
    assert "── old-alias" not in out and "1 hidden hyphenated aliases (`old-alias`)" in out


def test_hooks_table_rows_come_from_the_generator_defaults():
    """Every event the generator emits is a row; commands are rendered without
    the hook env prefix and without this machine's home directory."""
    from refmatrix.hooks import _claude_hook_block, HOOK_ENV
    gen = _load()
    table = gen.render_hooks_table()
    block = _claude_hook_block(Path("/proj/.refmatrix"), enforce=False)
    for ev in block["hooks"]:
        assert f"| `{ev}` |" in table, ev
    assert HOOK_ENV.strip() not in table
    assert str(Path.home()) not in table
    assert "~/.claude/projects/<slug>/memory" in table


def test_check_mode_reports_drift_and_apply_fixes_it(tmp_path):
    gen = _load()
    arch = tmp_path / "ARCHITECTURE.md"
    readme = tmp_path / "README.md"
    shutil.copy(ARCH, arch)
    shutil.copy(README, readme)
    targets = {"cli-tree": arch, "hooks-table": readme}
    assert gen.check(targets) == []
    # drift: a command line edited by hand
    arch.write_text(arch.read_text().replace("├── daemon", "├── deamon", 1))
    drift = gen.check(targets)
    assert drift and "cli-tree" in drift[0] and "deamon" in drift[0]
    assert gen.apply(targets) == ["cli-tree"]
    assert gen.check(targets) == []


def test_missing_markers_fail_loud(tmp_path):
    gen = _load()
    doc = tmp_path / "x.md"
    doc.write_text("no markers here\n")
    try:
        gen.extract(doc.read_text(), "cli-tree")
    except gen.MarkerError as e:
        assert "cli-tree" in str(e)
    else:
        raise AssertionError("extract() must refuse a doc without the markers")
