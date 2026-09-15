#!/usr/bin/env python3
"""gmd init — scaffold a project for Graph Markdown authoring.

Operations (all idempotent, additive, dry-run by default):

  gmd init <root>                   # CLAUDE.md + .gmd/ scaffolding
  gmd init <root> --memory          # migrate this project's memory files
  gmd init <root> --agents          # splice §output-format into doc agents
  gmd init <root> --with-rmx        # rmx init + hooks + initial ingest
  gmd init <root> --all             # memory + agents (NOT --with-rmx)
  gmd init <root> --all --with-rmx  # everything
  gmd init <root> ... --apply       # actually write (default: dry-run)
  gmd init <root> ... --force       # overwrite existing config

Exit codes: 0=ok, 1=errors, 2=invocation error.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================================
# locked text blocks (drafts approved 2026-05-16)
# ============================================================================

TEXT_AUTHORING_FORMAT = """\
## Authoring Format {#authoring-format}

Persistent prose docs in this project use **GMD** (Graph Markdown).
Spec: `docs/gmd/SPEC.md`. Lint: `python3 tools/gmd/lint.py <path>`.

### When required

ADRs, concept docs, glossary, design tenets, plan/task specs, post-mortems,
memory files, agent review findings, and any markdown file other docs will reference.

### When NOT required

Code files, commit messages, PR descriptions, README at repo root, agent
transcripts, throwaway notes, generated reports.

### Mandatory frontmatter

Every GMD file MUST open with:

```yaml
---
gmd: "0.1"
id: <kebab-slug>      # globally unique within this project
title: <human title>
---
```

Optional: `tags`, `imports` (list of other GMD doc IDs referenced freely),
plus any domain fields (`status`, `governs`, `originSessionId`, etc.).

### Stable anchors

Any heading another doc may reference MUST carry `{#stable-id}`:

```
## ADR-FIRST gate {#adr-first-gate}
```

Renaming the heading text is fine. Renaming the `{#id}` is a breaking change —
treat it like a function rename. Use `kebab-case`, lowercase, alnum + `._-`.

### Typed edges

Assert cross-doc relationships with `rel:` lines (one per line, starting at
column 0):

```
rel: derives-from -> [[adr-0087]]
rel: supersedes -> [[old-design#stateless]] {confidence=high}
rel: evidence-for -> [[#failure-session-53]]
```

Recommended verbs: `supports`, `contradicts`, `derives-from`, `supersedes`,
`depends-on`, `instance-of`, `part-of`, `defines`, `defined-in`,
`evidence-for`, `motivates`, `example-of`. Custom verbs allowed; `gmd lint`
warns on unknowns.

### References

- Local: `[[#section-id]]`
- Cross-doc: `[[doc-id#section-id]]` or `[[doc-id]]` for whole doc
- External: standard markdown link `[text](url)`

### Validation gate

Before declaring an authoring task complete: `gmd lint <file>` MUST report
zero errors. Warnings (unknown verbs, missing `gmd:` frontmatter) acceptable
with rationale.
"""

TEXT_VS_DOC_WRITER = """\
## Output Format {#output-format}

All persistent docs you author are **GMD**. See project CLAUDE.md
§authoring-format for the full rule. Specific to your role:

### ADRs

Frontmatter MUST include `gmd: "0.1"`, `id: adr-NNNN`, plus the existing
ADR header fields (`Status`, `Governs`, `Date`).

Every accepted ADR carries a `{#adr-NNNN}` anchor on its title heading so
cross-refs from CLAUDE.md, concept docs, and other ADRs resolve as
`[[adr-NNNN]]`.

When this ADR supersedes a prior one, add `rel: supersedes -> [[adr-MMMM]]`
in the body — not a prose-only note.

When this ADR derives from a concept doc, add
`rel: derives-from -> [[concept-doc-id#section]]`.

### Concept docs

Frontmatter `id: concept-<name>`. Sections that define types/classes carry
`{#<TypeName>}` anchors so ADRs can link them as
`[[concept-<name>#TypeName]]`.

### Glossary entries

Each term gets its own H3 with `{#term-<slug>}`. Define cross-term references
with `rel: instance-of -> [[#parent-term]]` or
`rel: example-of -> [[#parent-term]]`.

### Verification

Run `gmd lint <file>` before reporting done. Any dangling `[[ref]]` = broken
output. If a target genuinely doesn't exist yet, either create the stub or
use external markdown link and note the dependency.
"""

TEXT_VS_ALIGNMENT = """\
## Output Format {#output-format}

The `pseudocode/*.pseudo` files you maintain are NOT GMD — pseudocode has
its own format. But every doc you author or amend ABOUT pseudocode is GMD.

When you write or update:
- ADR amendments → see §output-format of vs-doc-writer
- Concept doc revisions → GMD frontmatter + anchors
- Drift reports / actualization findings in `docs/alignment/*.md` → GMD

For pseudocode files themselves, you MAY include `gmd: "0.1"` and `id:` in a
`# Header` comment block at top for retrieval purposes, but body syntax stays
`.pseudo`. The graph treats the file as a single addressable unit, not
section-by-section.

When pseudocode supersedes a prior approach, add a top-of-file comment:

```
# rel: supersedes -> [[pseudocode-prior]]
```

The ingester recognizes this convention. Without it, the supersession is
invisible to the graph.
"""

TEXT_VS_BSD = """\
## Output Format {#output-format}

Findings in `docs/bullshit/*.md` are GMD. Each finding file:

```
---
gmd: "0.1"
id: bsd-<plan>-<task>-<short-slug>
title: <one-line finding>
severity: BULLSHIT|SKETCHY|OBS
plan: <plan-id>
task: <task-id>
---

# <Finding title> {#root}

<concrete description, file:line evidence>

rel: contradicts -> [[<rule-the-finding-violates>]]
rel: evidence-for -> [[<failure-mode-doc-anchor>]]
```

The `contradicts` edge points at the CLAUDE.md rule or ADR the bullshit
violates. Without this edge, the finding is just a complaint — with it, the
rule's "this is why I exist" graph populates over time.

`docs/bullshit/INDEX.md` is the rollup. Add a `[[bsd-<id>]]` row when filing
each finding. Auto-derivable from graph; keep manual until tooling catches up.

`docs/bullshit/IMPRESSIONS.md` (your pre-spec read) follows the same GMD
shape — frontmatter, anchors, optional `rel:` lines on each impression that
links to suspected anti-pattern entries.
"""

AGENT_TEMPLATES: dict[str, str] = {
    "vs-doc-writer": TEXT_VS_DOC_WRITER,
    "vs-alignment": TEXT_VS_ALIGNMENT,
    "vs-bsd": TEXT_VS_BSD,
}

GMD_CONFIG_YML = """\
# .gmd/config.yml — project-local GMD config (optional, all keys defaulted)

# Extra recommended verbs for this project. Added to lint's vocab without
# triggering unknown-verb warnings.
extra_verbs: []

# Globs to skip when running `gmd lint .` recursively.
ignore:
  - "node_modules/**"
  - ".venv/**"
  - "**/.refmatrix/**"
  - "**/dist/**"
  - "**/build/**"
"""

# ============================================================================
# planning
# ============================================================================

@dataclass
class PlannedOp:
    kind: str            # "write" | "edit" | "skip" | "warn" | "exec"
    target: str
    detail: str = ""

    def fmt(self) -> str:
        sym = {"write": "+", "edit": "~", "skip": "·",
               "warn": "!", "exec": ">"}.get(self.kind, "?")
        return f"  {sym} {self.target}{' — ' + self.detail if self.detail else ''}"


@dataclass
class Plan:
    ops: list[PlannedOp] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, op: PlannedOp) -> None:
        self.ops.append(op)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def print(self) -> None:
        for op in self.ops:
            print(op.fmt())
        if self.errors:
            print("\nERRORS:")
            for e in self.errors:
                print(f"  ! {e}")


# ============================================================================
# operations
# ============================================================================

def slug_from_path(path: Path) -> str:
    """Derive Claude Code project slug from a repo path."""
    s = str(path.resolve())
    return "-" + s.lstrip("/").replace("/", "-")


def _has_anchor(text: str, anchor: str) -> bool:
    return f"{{#{anchor}}}" in text


def op_claude_md(root: Path, plan: Plan, apply: bool, force: bool) -> None:
    """Ensure CLAUDE.md exists with §authoring-format inserted."""
    target = root / "CLAUDE.md"
    if target.exists():
        text = target.read_text(encoding="utf-8")
        if _has_anchor(text, "authoring-format") and not force:
            plan.add(PlannedOp("skip", str(target),
                               "§authoring-format already present"))
            return
        new_text = text.rstrip() + "\n\n" + TEXT_AUTHORING_FORMAT
        plan.add(PlannedOp("edit", str(target),
                           "append §authoring-format"))
        if apply:
            target.write_text(new_text, encoding="utf-8")
    else:
        new_text = (
            "# CLAUDE.md\n\n"
            + "<!-- gmd init scaffolding -->\n\n"
            + TEXT_AUTHORING_FORMAT
        )
        plan.add(PlannedOp("write", str(target), "create scaffolded"))
        if apply:
            target.write_text(new_text, encoding="utf-8")


def op_gmd_dir(root: Path, plan: Plan, apply: bool, force: bool) -> None:
    """Create .gmd/ with config.yml."""
    d = root / ".gmd"
    cfg = d / "config.yml"
    if cfg.exists() and not force:
        plan.add(PlannedOp("skip", str(cfg), "exists"))
        return
    plan.add(PlannedOp("write", str(cfg), "default config"))
    if apply:
        d.mkdir(exist_ok=True)
        cfg.write_text(GMD_CONFIG_YML, encoding="utf-8")


def op_memory(root: Path, plan: Plan, apply: bool, force: bool) -> None:
    """Migrate this project's memory files (~/.claude/projects/<slug>/memory/)."""
    slug = slug_from_path(root)
    mem_dir = Path.home() / ".claude" / "projects" / slug / "memory"
    if not mem_dir.is_dir():
        plan.add(PlannedOp("warn", str(mem_dir),
                           "no memory dir for this project; skipped"))
        return
    try:
        from migrate_memory import collect, needs_migration, migrate
    except ImportError:
        # add this file's dir to path
        import importlib.util
        here = Path(__file__).parent
        spec = importlib.util.spec_from_file_location(
            "migrate_memory", here / "migrate_memory.py",
        )
        if spec is None or spec.loader is None:
            plan.err("could not import migrate_memory.py")
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        collect = mod.collect
        needs_migration = mod.needs_migration
        migrate = mod.migrate

    files = collect([mem_dir])
    if not files:
        plan.add(PlannedOp("warn", str(mem_dir), "no memory files found"))
        return

    for f in files:
        should, reason = needs_migration(f)
        if not should:
            plan.add(PlannedOp("skip", str(f), reason))
            continue
        plan.add(PlannedOp("edit", str(f), "add gmd: + id:"))
        if apply:
            migrate(f, dry_run=False)


def _parse_agent_frontmatter(text: str) -> tuple[dict[str, str], int]:
    """Tiny YAML reader. Returns (fields, body_start_index)."""
    if not text.startswith("---"):
        return {}, 0
    lines = text.splitlines(keepends=False)
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fields: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            fields[k.strip()] = v.strip().strip('"').strip("'")
        i += 1
    body_start = i + 1 if i < len(lines) else i
    return fields, body_start


def op_agents(root: Path, plan: Plan, apply: bool, force: bool) -> None:
    """Splice §output-format into doc-authoring agent definitions."""
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        plan.add(PlannedOp("warn", str(agents_dir),
                           "no .claude/agents dir; skipped"))
        return

    for agent_path in sorted(agents_dir.glob("*.md")):
        text = agent_path.read_text(encoding="utf-8")
        fields, body_start = _parse_agent_frontmatter(text)
        name = fields.get("name", agent_path.stem)
        template = AGENT_TEMPLATES.get(name)
        if template is None:
            plan.add(PlannedOp("skip", str(agent_path),
                               f"no template for '{name}'"))
            continue
        if _has_anchor(text, "output-format") and not force:
            plan.add(PlannedOp("skip", str(agent_path),
                               "§output-format already present"))
            continue
        new_text = text.rstrip() + "\n\n" + template
        plan.add(PlannedOp("edit", str(agent_path),
                           f"append §output-format ({name})"))
        if apply:
            agent_path.write_text(new_text, encoding="utf-8")


def op_with_rmx(root: Path, plan: Plan, apply: bool, force: bool) -> None:
    """rmx init + install-hooks + ingest-gmd. Subprocess; fails soft."""
    rmx = shutil.which("rmx")
    if rmx is None:
        plan.err("`rmx` not on PATH — install refmatrix first")
        return

    rmx_dir = root / ".refmatrix"
    if not rmx_dir.exists():
        plan.add(PlannedOp("exec", "rmx init", f"in {root}"))
        if apply:
            subprocess.run(
                [rmx, "init"], cwd=root, check=False,
            )
    else:
        plan.add(PlannedOp("skip", str(rmx_dir), "already initialized"))

    plan.add(PlannedOp("exec", "rmx install-hooks --apply",
                       "PostToolUse / Stop / SessionStart / UserPromptSubmit"))
    if apply:
        subprocess.run(
            [rmx, "install-hooks", "--apply"], cwd=root, check=False,
        )

    plan.add(PlannedOp("exec", "rmx ingest-gmd .",
                       "initial GMD graph build"))
    if apply:
        subprocess.run(
            [rmx, "ingest-gmd", "."], cwd=root, check=False,
        )


# ============================================================================
# driver
# ============================================================================

def run_init(
    root: Path, *, memory: bool, agents: bool, with_rmx: bool,
    apply: bool, force: bool,
) -> int:
    plan = Plan()

    print(f"gmd init: project root = {root}")
    print(f"          mode = {'APPLY' if apply else 'DRY-RUN (preview)'}")
    print()

    # always run base scaffolding
    op_claude_md(root, plan, apply, force)
    op_gmd_dir(root, plan, apply, force)

    if memory:
        op_memory(root, plan, apply, force)
    if agents:
        op_agents(root, plan, apply, force)
    if with_rmx:
        op_with_rmx(root, plan, apply, force)

    plan.print()

    print()
    if plan.errors:
        print(f"gmd init: {len(plan.errors)} error(s); aborted")
        return 1
    if not apply:
        print("gmd init: dry-run complete. re-run with --apply to commit.")
    else:
        print(f"gmd init: {len([o for o in plan.ops if o.kind != 'skip'])} "
              f"change(s) applied. run `gmd lint .` to validate.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="gmd init", description=__doc__)
    ap.add_argument("root", type=Path, nargs="?", default=Path.cwd(),
                    help="project root (default: cwd)")
    ap.add_argument("--memory", action="store_true",
                    help="migrate this project's memory files")
    ap.add_argument("--agents", action="store_true",
                    help="splice §output-format into doc-authoring agents")
    ap.add_argument("--with-rmx", action="store_true",
                    help="rmx init + hooks + initial ingest")
    ap.add_argument("--all", action="store_true",
                    help="implies --memory --agents (NOT --with-rmx)")
    ap.add_argument("--apply", action="store_true",
                    help="actually write changes (default: dry-run)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing config / anchored sections")
    args = ap.parse_args(argv[1:])

    if not args.root.is_dir():
        print(f"gmd init: not a directory: {args.root}", file=sys.stderr)
        return 2

    memory = args.memory or args.all
    agents = args.agents or args.all
    with_rmx = args.with_rmx  # NOT pulled in by --all

    return run_init(
        args.root.resolve(),
        memory=memory, agents=agents, with_rmx=with_rmx,
        apply=args.apply, force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
