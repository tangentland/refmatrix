"""Place packaged subagent descriptions into a project's .claude/agents/.

Bundled assets live under refmatrix/templates/agents/*.md. `rmx init`
copies each into <project>/.claude/agents/ so Claude Code can dispatch
them per-project without further setup.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path


TEMPLATE_PKG = "refmatrix.templates.agents"


def _iter_template_names() -> list[str]:
    """Names of every .md asset shipped under refmatrix/templates/agents/."""
    pkg = resources.files(TEMPLATE_PKG)
    return sorted(
        p.name for p in pkg.iterdir()
        if p.is_file() and p.name.endswith(".md")
    )


def install_agents(project_root: Path, force: bool = False) -> list[str]:
    """Copy bundled agent definitions into <project>/.claude/agents/.

    Returns a list of human-readable plan lines for the CLI to render.
    Skips files that already exist unless `force=True`.
    """
    return _install_pkg_md(TEMPLATE_PKG, project_root / ".claude" / "agents",
                           force=force, kind="agents")


COMMANDS_PKG = "refmatrix.templates.commands"


def install_commands(project_root: Path, force: bool = False) -> list[str]:
    """Copy bundled slash-command definitions into <project>/.claude/commands/
    so `/stash`, `/unstash`, `/save-state`, `/recall-state` are available
    per-project — the standardized workflow rituals shipped with rmx."""
    return _install_pkg_md(COMMANDS_PKG, project_root / ".claude" / "commands",
                           force=force, kind="commands")


def _install_pkg_md(pkg_name: str, dest_dir: Path, *, force: bool,
                    kind: str) -> list[str]:
    out: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    pkg = resources.files(pkg_name)
    names = sorted(p.name for p in pkg.iterdir()
                   if p.is_file() and p.name.endswith(".md"))
    if not names:
        out.append(f"[yellow]no packaged {kind} found[/]")
        return out
    for name in names:
        target = dest_dir / name
        if target.exists() and not force:
            out.append(
                f"[yellow]skip[/] {target} (exists; pass --force to overwrite)"
            )
            continue
        target.write_text((pkg / name).read_text(encoding="utf-8"),
                          encoding="utf-8")
        out.append(f"[green]write[/] {target}")
    return out
