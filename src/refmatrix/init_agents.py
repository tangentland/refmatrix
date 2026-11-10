"""Place packaged subagent descriptions and slash commands where Claude Code finds them.

Bundled assets live under refmatrix/templates/{agents,commands}/*.md. `rmx init`
copies agents into <project>/.claude/agents/ and most commands into
<project>/.claude/commands/. The session-handoff pair (`/save-state`, `/recall-state`)
installs ONCE at user level, into ~/.claude/commands/ (2026-11-10, user): per-project copies
drifted, and the user-level rewrite had lost the memory-dir rules the project copies carried.
"""
from __future__ import annotations

from datetime import datetime
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

# Commands one copy serves every project: they read the project from cwd and its CLAUDE.md, so
# a per-project copy only adds a place for a fix to be missing (2026-11-10, user).
USER_LEVEL_COMMANDS = frozenset({"save-state.md", "recall-state.md"})


def user_commands_dir() -> Path:
    """Claude Code's user-level commands dir, `~/.claude/commands/`."""
    return Path.home() / ".claude" / "commands"


def command_backup_dir() -> Path:
    """Where `--force` keeps the user-level copy it replaces: `<user_home>/backups/commands/`
    (outside ~/.claude/commands, so a backup is never itself a command)."""
    from refmatrix import taxonomy

    return taxonomy.user_home() / "backups" / "commands"


def install_commands(project_root: Path, force: bool = False, *,
                     user_dir: Path | None = None,
                     backup_dir: Path | None = None) -> list[str]:
    """Copy bundled slash-command definitions where they belong: USER_LEVEL_COMMANDS into
    `user_dir` (default ~/.claude/commands/), every other command into
    <project>/.claude/commands/ so `/stash`, `/detour`, `/commit-state` ... are available
    per-project.

    A user-level file is shared by every project, so one project's `rmx init` never replaces it
    silently: an identical copy is left alone, a differing copy is kept unless `force`, and
    `force` writes the old copy to `backup_dir` first (a failed backup raises and replaces
    nothing). A project-local copy of a user-level command is named, never deleted: it is the
    user's file, and it would run instead of the user-level one in that project."""
    user_dir = user_dir if user_dir is not None else user_commands_dir()
    backup_dir = backup_dir if backup_dir is not None else command_backup_dir()
    project_dir = project_root / ".claude" / "commands"
    out = _install_pkg_md(COMMANDS_PKG, project_dir, force=force, kind="commands",
                          skip=USER_LEVEL_COMMANDS)
    pkg = resources.files(COMMANDS_PKG)
    for name in sorted(USER_LEVEL_COMMANDS):
        text = (pkg / name).read_text(encoding="utf-8")
        out.append(_install_user_level(user_dir / name, text, force=force,
                                       backup_dir=backup_dir))
        local = project_dir / name
        if local.exists():
            out.append(
                f"[yellow]warn[/] {local} is a project-local copy of the user-level "
                f"/{name[:-3]}; remove it so {user_dir / name} is the one that runs here"
            )
    return out


def _install_user_level(target: Path, text: str, *, force: bool, backup_dir: Path) -> str:
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current == text:
            return f"[green]ok[/] {target} (current)"
        if not force:
            return (f"[yellow]skip[/] {target} (differs from the packaged command; pass "
                    f"--force to overwrite it, the current file is backed up first)")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        backup = backup_dir / f"{target.name}.{stamp}"
        backup.write_text(current, encoding="utf-8")
        target.write_text(text, encoding="utf-8")
        return f"[green]write[/] {target} (previous copy backed up to {backup})"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return f"[green]write[/] {target}"


def _install_pkg_md(pkg_name: str, dest_dir: Path, *, force: bool,
                    kind: str, skip: frozenset[str] = frozenset()) -> list[str]:
    out: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    pkg = resources.files(pkg_name)
    names = sorted(p.name for p in pkg.iterdir()
                   if p.is_file() and p.name.endswith(".md") and p.name not in skip)
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
