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
    out: list[str] = []
    project_root = project_root.resolve()
    agents_dir = project_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    names = _iter_template_names()
    if not names:
        out.append("[yellow]no packaged agents found[/]")
        return out

    pkg = resources.files(TEMPLATE_PKG)
    for name in names:
        target = agents_dir / name
        if target.exists() and not force:
            out.append(
                f"[yellow]skip[/] {target} (exists; pass --force to overwrite)"
            )
            continue
        content = (pkg / name).read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        out.append(f"[green]write[/] {target}")
    return out
