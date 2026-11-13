"""bug-216 AC-1 (R1) and R2's static half — `!path` re-include lines in `.refmatrix_ignore`.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#r1, #r2, #ac-1).

WHY. 247 authored `rel:` lines target `[[claude#…]]` / `[[project-profile#…]]` and never land:
`.refmatrix_ignore` lists `CLAUDE.md` and `.claude` (2026-09-04, "program data, not knowledge"),
and `ingest._is_ignored` drops EVERY hidden-dir segment, so `.claude/PROJECT_PROFILE.md` stays out
even with the ignore file fixed. R1 adds an anchored `!path` re-include that beats every spec
pattern AND the built-in hidden-dir rule, and never beats `INGEST_IGNORE_DIRS`.

Every case goes through `should_ignore(p, root)` — the one predicate (R2) — never through
`IgnoreSpec.match`, whose semantics for a re-included path the spec does not fix.

Mutations this file must kill (spec #ac-1):
  M1 drop the hidden-dir override  -> test_reinclude_beats_the_hidden_dir_rule_with_no_spec_line
                                      and test_ac1_profile_reincluded_under_an_ignored_claude_dir
  M2 let a re-include beat INGEST_IGNORE_DIRS -> test_reinclude_never_beats_ingest_ignore_dirs

Roots are short `/tmp` mkdtemp dirs: `should_ignore` reads `p.parts` of the ABSOLUTE path for the
hidden-dir rule, so a root under any dot-dir would ignore everything and prove nothing.
"""
from __future__ import annotations

import ast
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from refmatrix import ingest as ingest_mod
from refmatrix.ingest import INGEST_IGNORE_DIRS, load_ignore_spec, should_ignore

SRC = Path(ingest_mod.__file__).resolve().parent


@pytest.fixture
def root():
    base = Path(tempfile.mkdtemp(prefix="b216i", dir="/tmp")).resolve()
    assert not any(seg.startswith(".") for seg in base.parts[1:]), base
    yield base
    shutil.rmtree(base)


def _spec(root: Path, *lines: str) -> Path:
    d = root / ".refmatrix"
    d.mkdir(parents=True, exist_ok=True)
    f = d / ".refmatrix_ignore"
    if f.exists():
        # load_ignore_spec caches by (path, mtime): a rewrite inside the same mtime tick is
        # invisible, so bump it explicitly.
        old = f.stat().st_mtime
        f.write_text("\n".join(lines) + "\n")
        os.utime(f, (old + 5, old + 5))
    else:
        f.write_text("\n".join(lines) + "\n")
    return f


def _touch(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n")
    return p


# ---------------------------------------------------------------- AC-1 as worded


def test_ac1_profile_reincluded_under_an_ignored_claude_dir(root):
    """`.claude` in the spec + `!.claude/PROJECT_PROFILE.md`: the profile is NOT ignored and
    `.claude/agents/x.md` IS. The override has to beat BOTH the spec's `.claude` line and the
    built-in hidden-dir rule (spec #why-hidden)."""
    _spec(root, ".claude", "!.claude/PROJECT_PROFILE.md")
    prof = _touch(root, ".claude/PROJECT_PROFILE.md")
    agent = _touch(root, ".claude/agents/x.md")
    assert should_ignore(prof, root) is False, "re-included profile is still ignored"
    assert should_ignore(agent, root) is True, "a re-include of one file let the whole dir in"


def test_ac1_claude_md_removed_from_the_spec_is_not_ignored(root):
    """The R4 config drops the `CLAUDE.md` line; a root CLAUDE.md is then not ignored (it is not
    under a hidden dir, so no override is needed). Re-asserted, not new: green at HEAD."""
    _spec(root, ".claude", "!.claude/PROJECT_PROFILE.md", "src/refmatrix/templates")
    cm = _touch(root, "CLAUDE.md")
    assert should_ignore(cm, root) is False


def test_reinclude_never_beats_ingest_ignore_dirs(root):
    """`!node_modules/x.md` stays ignored (mutation M2). Every INGEST_IGNORE_DIRS member, at the
    root and nested."""
    assert set(INGEST_IGNORE_DIRS) >= {"node_modules", "venv"}
    lines = []
    paths = []
    for d in INGEST_IGNORE_DIRS:
        for rel in (f"{d}/x.md", f"pkg/{d}/y.md"):
            lines.append(f"!{rel}")
            paths.append(_touch(root, rel))
    _spec(root, *lines)
    for p in paths:
        assert should_ignore(p, root) is True, f"re-include beat INGEST_IGNORE_DIRS: {p}"


def test_a_reinclude_naming_a_directory_is_reported_once_and_reincludes_nothing(root, capfd):
    """R1: a re-include applies to files only; a `!dir` line re-includes nothing and is reported
    ONCE, loudly (stderr), when the spec loads — not once per walked file."""
    (root / ".claude" / "agents").mkdir(parents=True)
    inside = _touch(root, ".claude/agents/a.md")
    _spec(root, ".claude", "!.claude/agents")
    capfd.readouterr()
    load_ignore_spec(root)
    load_ignore_spec(root)          # cached: same (path, mtime)
    for _ in range(3):
        should_ignore(inside, root)
    err = capfd.readouterr().err
    assert err.count("!.claude/agents") == 1, (
        f"a `!dir` line must be reported exactly once on stderr; got:\n{err!r}")
    assert should_ignore(inside, root) is True, "a `!dir` line re-included the files under it"


# ---------------------------------------------------------------- R1 semantics the AC relies on


def test_reinclude_beats_the_hidden_dir_rule_with_no_spec_line(root):
    """Mutation M1 in isolation: no ignore pattern at all, only the re-include. The ONLY rule
    that excludes the profile is the built-in hidden-dir rule, so only the hidden-dir override
    can make this pass. (Also pins that a spec holding nothing but re-includes is not dropped as
    empty — `load_ignore_spec` returns None for a spec it judges empty.)"""
    _spec(root, "# rule docs", "!.claude/PROJECT_PROFILE.md")
    prof = _touch(root, ".claude/PROJECT_PROFILE.md")
    other = _touch(root, ".claude/settings.md")
    assert should_ignore(prof, root) is False
    assert should_ignore(other, root) is True, "the hidden-dir rule still covers the rest"


def test_reinclude_beats_every_spec_pattern_shape_wherever_it_appears(root):
    """R1 (a): bare name, basename glob and anchored path are all overridden, and the re-include
    line may come BEFORE the pattern it overrides."""
    _spec(root,
          "!docs/keep.md",             # before the line it overrides
          "docs",                      # bare name -> segment anywhere
          "*.draft.md",                # basename glob
          "notes/private",             # anchored
          "!notes/private/ok.md",
          "!a.draft.md")
    keep = _touch(root, "docs/keep.md")
    drop = _touch(root, "docs/drop.md")
    ok = _touch(root, "notes/private/ok.md")
    secret = _touch(root, "notes/private/secret.md")
    draft_root = _touch(root, "a.draft.md")
    draft_other = _touch(root, "b.draft.md")
    assert should_ignore(keep, root) is False
    assert should_ignore(drop, root) is True
    assert should_ignore(ok, root) is False
    assert should_ignore(secret, root) is True
    assert should_ignore(draft_root, root) is False
    assert should_ignore(draft_other, root) is True


def test_reinclude_is_anchored_to_the_project_root(root):
    """R1: `!path` is anchored. `!CLAUDE.md` re-includes the ROOT CLAUDE.md, not a nested one a
    bare `CLAUDE.md` pattern still excludes."""
    _spec(root, "CLAUDE.md", "!CLAUDE.md")
    top = _touch(root, "CLAUDE.md")
    nested = _touch(root, "pkg/CLAUDE.md")
    assert should_ignore(top, root) is False
    assert should_ignore(nested, root) is True


def test_reinclude_accepts_a_glob(root):
    """R1: 'a glob is allowed'."""
    _spec(root, ".claude", "!.claude/*PROFILE*.md")
    prof = _touch(root, ".claude/PROJECT_PROFILE.md")
    other = _touch(root, ".claude/settings.md")
    assert should_ignore(prof, root) is False
    assert should_ignore(other, root) is True


def test_without_a_root_only_the_builtin_rules_apply(root):
    """`should_ignore(p)` with no root has no spec to read, so nothing re-includes: unchanged."""
    _spec(root, "!.claude/PROJECT_PROFILE.md")
    prof = _touch(root, ".claude/PROJECT_PROFILE.md")
    assert should_ignore(prof) is True


# ---------------------------------------------------------------- R2: one predicate (static)
#
# The behavioural half (each walker includes exactly the same files on one fixture tree) is in
# tests/test_bug216_rule_docs_e2e.py. These pin the SHAPE: no walk keeps its own copy of the
# hidden-dir rule or reads the spec itself.


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "templates" not in p.parts)


def _names_used(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.name)
    return out


def test_r2_only_ingest_reads_the_ignore_spec():
    """`load_ignore_spec` is read by `should_ignore` and nothing else. At HEAD `watch.py` calls
    it and re-implements the match (`is_relevant`)."""
    users = [p.relative_to(SRC).as_posix() for p in _src_files()
             if p.name != "ingest.py" and "load_ignore_spec" in _names_used(p)]
    assert users == [], f"walks reading the ignore spec themselves: {users}"


def test_r2_only_ingest_uses_the_builtin_segment_rule():
    users = [p.relative_to(SRC).as_posix() for p in _src_files()
             if p.name != "ingest.py" and "_is_ignored" in _names_used(p)]
    assert users == [], f"walks calling the private segment rule directly: {users}"


def _func_src(mod_path: Path, qualname: str) -> ast.AST:
    tree = ast.parse(mod_path.read_text())
    head, *rest = qualname.split(".")
    found = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == head]
    assert len(found) == 1, f"{mod_path.name}: expected one `def {head}`, found {len(found)}"
    node = found[0]
    for name in rest:
        inner = [n for n in ast.walk(node)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        assert len(inner) == 1, f"{qualname}: expected one nested `def {name}`"
        node = inner[0]
    return node


def _calls(node: ast.AST) -> list[ast.Call]:
    return [c for c in ast.walk(node) if isinstance(c, ast.Call)]


def _call_name(c: ast.Call) -> str | None:
    f = c.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _has_private_hidden_dir_rule(node: ast.AST) -> bool:
    """A `<x>.startswith(".")` call — the shape every private copy of the hidden-dir rule has."""
    for c in _calls(node):
        if (_call_name(c) == "startswith" and c.args and isinstance(c.args[0], ast.Constant)
                and c.args[0].value == "."):
            return True
    return False


# The walkers R2 enumerates (spec #r2): ingest_path's walk, the watchers, `_sync_paths` (its
# per-path body `_sync_one`, including the purge of a path that became ignored) and ingest-gmd's
# walk. Each must call `should_ignore` and must not carry a private hidden-dir rule. `is_relevant`
# is listed because both watchers filter through it; it may stay, as a thin wrapper.
WALKERS = [
    ("ingest.py", "_ingest_tree"),
    ("sync.py", "_sync_one"),
    ("watch.py", "is_relevant"),
    ("ingest_gmd.py", "collect_gmd_files"),
]


@pytest.mark.parametrize("module,func", WALKERS, ids=[f"{m}:{f}" for m, f in WALKERS])
def test_r2_each_walker_goes_through_should_ignore(module, func):
    node = _func_src(SRC / module, func)
    names = {_call_name(c) for c in _calls(node)}
    assert "should_ignore" in names, f"{module}:{func} does not call should_ignore"
    assert not _has_private_hidden_dir_rule(node), (
        f"{module}:{func} keeps a private copy of the hidden-dir rule")


def test_r2_the_daemon_watcher_filters_against_its_owning_root():
    """The daemon's watcher handler (`_start_watcher` -> `_Handler._maybe`) called
    `is_relevant(p)` with NO root, so the spec — and with it any re-include — never reached
    the watcher's first filter. Whatever it calls (`is_relevant` or `should_ignore`), it must
    pass a root."""
    maybe = _func_src(SRC / "daemon.py", "_start_watcher._maybe")
    filt = [c for c in _calls(maybe) if _call_name(c) in ("is_relevant", "should_ignore")]
    assert filt, "the daemon watcher handler no longer filters at all"
    for c in filt:
        n = len(c.args) + len([k for k in c.keywords if k.arg == "root"])
        assert n >= 2, f"daemon watcher filter called without a root: {ast.unparse(c)}"

