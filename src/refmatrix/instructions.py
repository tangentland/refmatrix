"""Instruction units: the one source file of a rule, its compiler, its fixture runner, and the
read-only replay of its pattern over the STM ring.

task-I1.b1 (plan-32; ADR-0007 `#units`, `#binding`, `#fixtures`, `#layers`,
`#installed-equals-generated`; bug-209). Before this module a rule lived as prose in several
places at once (CLAUDE.md, an agent file, a memory, a hand-written hook script), and nothing
proved that a hook which claimed to enforce it could fire at all. A **unit** is one markdown
file: GMD frontmatter plus a `unit:` map that carries the rule's binding (event, tool, the
`tool_input` patterns, who, where, when), its priority, the census rows it carries, and the
`fire` / `pass` envelopes that prove it fires. Its text is the body, or a skill's anchored
section named by `from:`.

Two layers, one schema (ADR-0007 `#layers`): packaged units under
`refmatrix/templates/{triggers,checks,rules,skills,practices/<name>}/`, found through
`importlib.resources` so the package a process imports is the package whose units it compiles
(never a path into another tree); and a project's own under `.claude/{triggers,checks,rules,
skills}/`. A file under `.claude/rules/` or `.claude/skills/` with no `unit:` map is a native
Claude Code rule or skill: local, listed, neither compiled nor refused (lead ruling on RED's
trap 4, 2026-11-25).

`compile_layers` turns every unit of both layers into `.claude/rmx-instructions.json`: units
sorted by id, each with its bindings, text and sha, and the per-event prefilter built from the
dispatchable kinds (deny, ask, inject; trap 5). The bytes depend on the unit files only, so a
second `--apply` writes the same bytes and `--check` can compare the tracked file with a fresh
compile. A bad unit is REFUSED with the file and the rule named and nothing written
(`CompileRefused`); no partial table ever reaches a hook.

`decide` is the one decision the dispatcher makes (I1.b3 calls it from `rmx rules fire`);
`run_fixtures` puts each of a unit's envelopes through it, building `repo:` and `store:` states
in a temp directory with real `git` (every call bounded by `GIT_TIMEOUT_S`). Nothing here calls
the daemon or opens the store: `install-hooks --check` must work beside a held writer and in a
clone with no store.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

# ---- the probe constants (task-I1.b0 #verdicts) ----------------------------------------------
#
# Each is a literal that a commit flips only together with the probe's committed evidence. While
# one is off, the delivery it gates is refused at compile (ADR-0007 #dispatcher-allow,
# #t3-fallbacks; task-I1.b3 #d4).

# Probe P2: does an `ask` decision from a PreToolUse hook prompt the user? Evidence not committed.
ASK_VERIFIED = False
# Probe P1: does a `context` inject (additionalContext with no permissionDecision) reach the
# model? Only the headless half is committed (I1.b0), so a `context` unit needs a `fallback`.
CONTEXT_VERIFIED = False

KINDS = ("deny", "ask", "inject", "check", "rule", "skill")
# The directory of each kind, in both layers (ADR-0007 #units).
KIND_DIR = {"deny": "triggers", "ask": "triggers", "inject": "triggers", "check": "checks",
            "rule": "rules", "skill": "skills"}
LAYER_DIRS = ("triggers", "checks", "rules", "skills")
# Directories that hold units only: a file there with no `unit:` map is refused. `rules/` and
# `skills/` are also Claude Code's own directories, so a plain file there is a native one.
UNIT_ONLY_DIRS = ("triggers", "checks")
# Packaged files of these directories are installed into the project (`--apply` writes them and
# `--check` compares them); triggers and checks reach a project only through the compiled file.
INSTALLED_DIRS = ("rules", "skills")
DISPATCHABLE = ("deny", "ask", "inject")

# ADR-0007 #contract: the size of each type's text, in UTF-8 bytes. At the limit is accepted.
SIZE_LIMITS = {"deny": 600, "ask": 600, "inject": 2000, "rule": 4000, "skill": 20000,
               "check": 1000}
SIZE_NAMES = {"deny": "reason", "ask": "reason", "inject": "checklist", "rule": "rule",
              "skill": "skill body", "check": "check message"}

UNIT_KEYS = frozenset({"kind", "bind", "priority", "census", "fixtures", "from", "on", "run"})
BIND_KEYS = frozenset({"event", "tool", "match", "unless", "prefilter", "who", "where", "when",
                       "mode", "fallback"})
FIXTURE_SIDES = ("fire", "pass")
FIXTURE_KEYS = frozenset({"envelope", "repo", "store"})
REPO_KEYS = frozenset({"files", "commits", "dirty", "branch"})
WHEN_KEYS = frozenset({"git-dirty", "git-head"})
WHEN_STATE_KEYS = frozenset({"repo", "paths"})
MODES = ("gate", "context", "post")
FALLBACKS = ("gate", "post")
CHECK_ON = ("commit", "merge", "release", "stop", "subagent-stop")
# The ring records tool calls (PreToolUse parks them, PostToolUse writes them): replay can read
# binds on these events only.
TOOL_EVENTS = ("PreToolUse", "PostToolUse")

# Deny beats ask beats gate beats context (task-I1.b3 #d3); the non-dispatchable kinds after.
PRECEDENCE = {"deny": 0, "ask": 1, "gate": 2, "context": 3, "post": 4, "check": 5, "rule": 6,
              "skill": 7}

# Every git call a stateful fixture or a `when:` state makes is bounded (task-I1.b1 #risks 4).
GIT_TIMEOUT_S = 2.0
COMPILED_REL = ".claude/rmx-instructions.json"
COMPILED_SCHEMA = 1
TEMPLATE_PKG = "refmatrix.templates"

_INSTEAD_RE = re.compile(r"(?m)^[ \t]*Instead:")
_UNIT_LINE_RE = re.compile(r"(?m)^unit:")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]")
_WHO_RE = re.compile(r"^(any|main|subagent|agent:[A-Za-z0-9_.:-]+)$")
# Variables that would point a fixture's git at another repository (bug-212's lesson).
_GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_COMMON_DIR", "GIT_PREFIX")


# ---- errors ----------------------------------------------------------------------------------

class UnitError(Exception):
    """One refused unit file: `where` (the file, project-relative when it is in a project),
    `rule` (which D3 rule) and `detail`. Its text is one line, so a refusal on stderr names the
    file and the rule together."""

    def __init__(self, where: str, rule: str, detail: str):
        self.where, self.rule, self.detail = where, rule, detail
        super().__init__(f"{where}: {rule}: {detail}")


class CompileRefused(Exception):
    """The compile refused one or more unit files; nothing was written (task-I1.b1 #d3)."""

    def __init__(self, errors: "list[UnitError]"):
        self.errors = sorted(errors, key=lambda e: (e.where, e.rule, e.detail))
        lines = [f"rmx install-hooks: refused {len(self.errors)} instruction unit problem(s); "
                 "nothing was written:"]
        lines += [f"  {e}" for e in self.errors]
        super().__init__("\n".join(lines))


class StateUnreadable(Exception):
    """A `when:` state (git) could not be read: the decision cannot be made. The fixture runner
    fails the envelope with it; the dispatcher (I1.b3) counts it and allows the call."""


class FixtureStateError(Exception):
    """A fixture's `repo:` / `store:` state could not be built."""


# ---- the unit model --------------------------------------------------------------------------

@dataclass
class Unit:
    """One loaded unit. `where` names its file for messages; `rel` is its path inside its layer
    (`triggers/x.md`, `skills/<id>/SKILL.md`); `body` is the markdown after the frontmatter;
    `text` is that body with its leading H1 (the title, already in the frontmatter) dropped and
    stripped, before any `from:` is resolved."""
    id: str
    kind: str
    spec: dict
    body: str
    text: str
    where: str
    rel: str
    layer: str

    @property
    def bind(self) -> list:
        return self.spec.get("bind") or []

    @property
    def fixtures(self) -> dict:
        return self.spec.get("fixtures") or {}

    @property
    def priority(self) -> int:
        return int(self.spec.get("priority") or 0)

    def decision_entry(self) -> dict:
        """What `decide` reads of a unit: the same keys a compiled entry carries."""
        return {"id": self.id, "kind": self.kind, "bind": self.bind, "priority": self.priority}


@dataclass
class LocalFile:
    """A project file of the local layer: a unit, a native rule or skill (no `unit:` map), or a
    file the loader refused (`error` holds why)."""
    where: str
    rel: str
    unit: "Unit | None"
    error: "str | None" = None


@dataclass
class PackagedFile:
    """One packaged file: its path under `templates/`, where it lands in a project
    (`.claude/...`), its bytes, and whether `--apply` installs it (rules and skills) or it
    reaches the project only through the compiled file (triggers and checks)."""
    rel: str
    installed: str
    data: bytes
    installs: bool


@dataclass
class Layers:
    packaged: "list[PackagedFile]" = field(default_factory=list)
    units: "list[Unit]" = field(default_factory=list)
    local: "list[LocalFile]" = field(default_factory=list)
    errors: "list[UnitError]" = field(default_factory=list)


def _split_frontmatter(text: str, where: str) -> "tuple[str | None, str]":
    """(frontmatter block, body). The block is the text between the opening `---` line and
    the next `---` line; no opening line means no frontmatter."""
    if not text.startswith("---\n"):
        return None, text
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        if head.endswith("\n---"):
            return head[:-4], ""
        raise UnitError(where, "frontmatter not closed", "no closing `---` line")
    return head, body


def _drop_title(body: str) -> str:
    """The body without its leading H1 line, stripped."""
    lines = body.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _decode(data: bytes, where: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise UnitError(where, "not valid UTF-8", f"cannot decode the file as UTF-8 ({e})") from e


def _read_bytes(path: Path, where: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as e:
        raise UnitError(where, "cannot read the file",
                        f"{type(e).__name__}: {e.strerror or e}") from e


_LOADER = None


def _yaml_loader():
    """`yaml.SafeLoader` with YAML 1.2 booleans: only true/false are booleans. Under YAML 1.1 a
    check's `on: commit` key parsed as the boolean True (`on`, `off`, `yes`, `no` are booleans
    there), which turned a valid unit into an unknown-key refusal."""
    global _LOADER
    if _LOADER is None:
        import yaml

        class _UnitLoader(yaml.SafeLoader):
            pass

        bool_tag = "tag:yaml.org,2002:bool"
        _UnitLoader.yaml_implicit_resolvers = {
            ch: [(tag, rx) for tag, rx in rs if tag != bool_tag]
            for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()}
        _UnitLoader.add_implicit_resolver(
            bool_tag, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
        _LOADER = _UnitLoader
    return _LOADER


def _parse(data: bytes, where: str, rel: str, layer: str, *,
           require_unit: bool) -> "Unit | None":
    """Parse one file. Returns None for a native file (no `unit:` map) when `require_unit` is
    false; raises UnitError for anything that is not a valid unit."""
    text = _decode(data, where)
    head, body = _split_frontmatter(text, where)
    if head is None or not _UNIT_LINE_RE.search(head):
        if require_unit:
            raise UnitError(where, "not a unit",
                            "no `unit:` map in its frontmatter (this directory holds units only)")
        return None
    import yaml
    try:
        fm = yaml.load(head, Loader=_yaml_loader())
    except yaml.YAMLError as e:
        raise UnitError(where, "frontmatter is not valid YAML",
                        " ".join(str(e).split())) from e
    if not isinstance(fm, dict) or not isinstance(fm.get("unit"), dict):
        raise UnitError(where, "bad unit map", "`unit:` must be a map")
    uid = fm.get("id")
    if not isinstance(uid, str) or not uid.strip():
        raise UnitError(where, "no id", "the frontmatter needs a GMD `id:`")
    spec = fm["unit"]
    _validate_spec(spec, where)
    try:
        json.dumps(spec, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise UnitError(where, "unit map is not plain data", str(e)) from e
    return Unit(id=uid.strip(), kind=spec["kind"], spec=spec, body=body,
                text=_drop_title(body), where=where, rel=rel, layer=layer)


def load_unit(path: "Path | str") -> Unit:
    """Load one unit file (any layer, or a fixture file outside both). Raises UnitError when
    the file cannot be read, is not UTF-8, or is not a valid unit. `from:` is resolved at
    compile, where the skill it names is in reach."""
    p = Path(path)
    where = str(p)
    unit = _parse(_read_bytes(p, where), where, p.name, "file", require_unit=True)
    assert unit is not None
    return unit


# ---- schema ----------------------------------------------------------------------------------

def _unknown(where: str, found, allowed, what: str) -> None:
    extra = sorted(set(found) - set(allowed), key=str)
    if extra:
        raise UnitError(where, "unknown key",
                        f"{', '.join(f'`{k}`' for k in extra)} in {what} "
                        f"(allowed: {', '.join(sorted(allowed))})")


def _regex(where: str, pattern, what: str) -> None:
    if not isinstance(pattern, str) or not pattern:
        raise UnitError(where, "bad pattern", f"{what} must be a non-empty ERE string")
    try:
        re.compile(pattern)
    except re.error as e:
        raise UnitError(where, "bad pattern", f"{what} {pattern!r} does not compile: {e}") from e


def _validate_spec(spec: dict, where: str) -> None:
    """Structure of the `unit:` map (task-I1.b1 #d1). Compile-time rules that need every unit
    (duplicate ids, `from:`) or the probe constants are in `compile_layers`."""
    _unknown(where, spec, UNIT_KEYS, "unit")
    kind = spec.get("kind")
    if kind not in KINDS:
        raise UnitError(where, "bad kind", f"`kind` is {kind!r}; one of {', '.join(KINDS)}")
    binds = spec.get("bind")
    if not isinstance(binds, list) or not binds:
        raise UnitError(where, "no binding", "`bind` must be a non-empty list")
    for i, b in enumerate(binds):
        _validate_bind(b, kind, where, i)
    pr = spec.get("priority", 0)
    if not isinstance(pr, int) or isinstance(pr, bool):
        raise UnitError(where, "bad priority", f"`priority` must be an integer, not {pr!r}")
    census = spec.get("census", [])
    if not isinstance(census, list) or not all(isinstance(c, str) for c in census):
        raise UnitError(where, "bad census", "`census` must be a list of row ids")
    frm = spec.get("from")
    if frm is not None and (not isinstance(frm, str) or "#" not in frm
                            or not all(frm.split("#", 1))):
        raise UnitError(where, "bad from", f"`from` must be `<skill id>#<anchor>`, not {frm!r}")
    if kind == "check":
        if spec.get("on") not in CHECK_ON:
            raise UnitError(where, "bad check", f"a check needs `on`, one of {', '.join(CHECK_ON)}")
        if not isinstance(spec.get("run"), str) or not spec["run"].strip():
            raise UnitError(where, "bad check", "a check needs `run`, the command it runs")
    else:
        for k in ("on", "run"):
            if k in spec:
                raise UnitError(where, "unknown key", f"`{k}` belongs to a check, not a {kind}")
    _validate_fixtures(spec.get("fixtures"), where)


def _validate_bind(b, kind: str, where: str, i: int) -> None:
    what = f"bind[{i}]"
    if not isinstance(b, dict):
        raise UnitError(where, "bad binding", f"{what} must be a map")
    _unknown(where, b, BIND_KEYS, what)
    if not isinstance(b.get("event"), str) or not b["event"]:
        raise UnitError(where, "bad binding", f"{what} needs an `event`")
    if "tool" in b:
        _regex(where, b["tool"], f"{what}.tool")
    match = b.get("match", {})
    if not isinstance(match, dict):
        raise UnitError(where, "bad binding", f"{what}.match must map a tool_input key to an ERE")
    for k, ere in match.items():
        _regex(where, ere, f"{what}.match.{k}")
    if "unless" in b:
        _regex(where, b["unless"], f"{what}.unless")
    if "prefilter" in b and (not isinstance(b["prefilter"], str) or not b["prefilter"]):
        raise UnitError(where, "bad binding", f"{what}.prefilter must be a non-empty literal")
    who = b.get("who", "any")
    if not isinstance(who, str) or not _WHO_RE.match(who):
        raise UnitError(where, "bad binding",
                        f"{what}.who is {who!r}; any, main, subagent or agent:<type>")
    wh = b.get("where", "any")
    if not isinstance(wh, str) or not (wh in ("any", "store", "no-store")
                                        or (wh.startswith("path:") and len(wh) > 5)):
        raise UnitError(where, "bad binding",
                        f"{what}.where is {wh!r}; any, store, no-store or path:<glob>")
    when = b.get("when")
    if when is not None:
        if not isinstance(when, dict) or not when:
            raise UnitError(where, "bad binding", f"{what}.when must be a map of states")
        _unknown(where, when, WHEN_KEYS, f"{what}.when")
        for state, arg in when.items():
            if not isinstance(arg, dict):
                raise UnitError(where, "bad binding", f"{what}.when.{state} must be a map")
            _unknown(where, arg, WHEN_STATE_KEYS, f"{what}.when.{state}")
            paths = arg.get("paths", [])
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise UnitError(where, "bad binding", f"{what}.when.{state}.paths must be a list")
            if "repo" in arg and not isinstance(arg["repo"], str):
                raise UnitError(where, "bad binding", f"{what}.when.{state}.repo must be a path")
    if kind == "inject":
        if b.get("mode") not in MODES:
            raise UnitError(where, "bad binding",
                            f"{what}: an inject needs `mode`, one of {', '.join(MODES)}")
    elif "mode" in b:
        raise UnitError(where, "unknown key", f"{what}.mode belongs to an inject, not a {kind}")
    if "fallback" in b:
        if b.get("mode") != "context":
            raise UnitError(where, "unknown key", f"{what}.fallback belongs to a `context` inject")
        if b["fallback"] not in FALLBACKS:
            raise UnitError(where, "bad binding",
                            f"{what}.fallback is {b['fallback']!r}; one of {', '.join(FALLBACKS)}")


def _validate_fixtures(fx, where: str) -> None:
    if fx is None:
        fx = {}
    if not isinstance(fx, dict):
        raise UnitError(where, "missing fixture", "`fixtures` must map fire and pass to envelopes")
    _unknown(where, fx, FIXTURE_SIDES, "fixtures")
    for side in FIXTURE_SIDES:
        items = fx.get(side)
        if not isinstance(items, list) or not items:
            raise UnitError(where, "missing fixture",
                            f"no `{side}` envelope: a unit proves it can fire with at least one "
                            "`fire` and one `pass` fixture (ADR-0007 #fixtures)")
        for i, item in enumerate(items):
            what = f"fixtures.{side}[{i}]"
            if not isinstance(item, dict) or not isinstance(item.get("envelope"), dict):
                raise UnitError(where, "bad fixture", f"{what} needs an `envelope` map")
            _unknown(where, item, FIXTURE_KEYS, what)
            if not isinstance(item["envelope"].get("hook_event_name"), str):
                raise UnitError(where, "bad fixture", f"{what}.envelope needs `hook_event_name`")
            if "store" in item and item["store"] not in ("present", "absent"):
                raise UnitError(where, "bad fixture", f"{what}.store is present or absent")
            if "repo" in item:
                repo = item["repo"]
                if not isinstance(repo, dict):
                    raise UnitError(where, "bad fixture", f"{what}.repo must be a map")
                _unknown(where, repo, REPO_KEYS, f"{what}.repo")


# ---- the two layers --------------------------------------------------------------------------

def _walk_traversable(node, prefix: str) -> "list[tuple[str, object]]":
    """(path under templates/, Traversable) of every file under `node`, sorted; package
    plumbing (`__init__.py`, `__pycache__`) excluded."""
    out: list = []
    try:
        children = sorted(node.iterdir(), key=lambda c: c.name)
    except (FileNotFoundError, NotADirectoryError):
        return out
    for c in children:
        if c.name in ("__init__.py", "__pycache__") or c.name.endswith(".pyc"):
            continue
        rel = f"{prefix}/{c.name}"
        if c.is_dir():
            out.extend(_walk_traversable(c, rel))
        elif c.is_file():
            out.append((rel, c))
    return out


def _unit_rel(rel_in_dir: str, d: str) -> bool:
    """Is a file at `<d>/<rel_in_dir>` a unit candidate? Skills: `<id>/SKILL.md`; the other
    directories: any `.md`."""
    if d == "skills":
        parts = rel_in_dir.split("/")
        return len(parts) == 2 and parts[1] == "SKILL.md"
    return rel_in_dir.endswith(".md")


def packaged_files() -> "list[PackagedFile]":
    """Every packaged file of the unit directories, from the package this process imports
    (`importlib.resources`, RED's trap 1): `templates/<d>/…` and
    `templates/practices/<name>/<d>/…`, each with the `.claude/<d>/…` path it has in a project."""
    root = resources.files(TEMPLATE_PKG)
    bases: list = [(d, root / d, d) for d in LAYER_DIRS]
    practices = root / "practices"
    if practices.is_dir():
        for p in sorted(practices.iterdir(), key=lambda c: c.name):
            if p.is_dir() and p.name not in ("__pycache__",):
                bases += [(d, p / d, f"practices/{p.name}/{d}") for d in LAYER_DIRS]
    out: list[PackagedFile] = []
    for d, node, prefix in bases:
        if not node.is_dir():
            continue
        for rel, trav in _walk_traversable(node, prefix):
            inner = rel[len(prefix) + 1:]
            out.append(PackagedFile(rel=rel, installed=f".claude/{d}/{inner}",
                                    data=trav.read_bytes(), installs=d in INSTALLED_DIRS))
    return out


def _local_candidates(project_root: Path) -> "list[tuple[str, str, Path]]":
    """(dir, path under `.claude/<dir>/`, file) of every local unit candidate, sorted."""
    out = []
    base = Path(project_root) / ".claude"
    for d in LAYER_DIRS:
        top = base / d
        if not top.is_dir():
            continue
        for p in sorted(top.rglob("*")):
            if not p.is_file():
                continue
            inner = p.relative_to(top).as_posix()
            if _unit_rel(inner, d):
                out.append((d, inner, p))
    return out


def load_layers(project_root: "Path | str") -> Layers:
    """Both layers of `project_root`. Never raises for a bad unit: each problem is an entry of
    `.errors` (the compile refuses on them; `--check` prints them). A local file whose
    `.claude/` path is a packaged file's is that file's installed copy, not a local unit."""
    project_root = Path(project_root)
    layers = Layers(packaged=packaged_files())
    for pf in layers.packaged:
        d = pf.installed.split("/")[1]
        inner = pf.installed.split("/", 2)[2]
        if not _unit_rel(inner, d):
            continue
        where = f"refmatrix/templates/{pf.rel}"
        try:
            unit = _parse(pf.data, where, pf.rel, "packaged", require_unit=d in UNIT_ONLY_DIRS)
        except UnitError as e:
            layers.errors.append(e)
            continue
        if unit is not None:
            layers.units.append(unit)
    installed = {pf.installed for pf in layers.packaged}
    for d, inner, path in _local_candidates(project_root):
        rel = f".claude/{d}/{inner}"
        if rel in installed:
            continue
        try:
            unit = _parse(_read_bytes(path, rel), rel, f"{d}/{inner}", "local",
                          require_unit=d in UNIT_ONLY_DIRS)
        except UnitError as e:
            layers.errors.append(e)
            layers.local.append(LocalFile(where=rel, rel=f"{d}/{inner}", unit=None,
                                          error=f"{e.rule}: {e.detail}"))
            continue
        layers.local.append(LocalFile(where=rel, rel=f"{d}/{inner}", unit=unit))
        if unit is not None:
            layers.units.append(unit)
    return layers


# ---- compile ---------------------------------------------------------------------------------

def section(body: str, anchor: str) -> "str | None":
    """The text under the heading that carries `{#anchor}`, up to the next heading of the same
    or a higher level, stripped; None when no heading carries the anchor."""
    lines = body.splitlines()
    tag = "{#" + anchor + "}"
    for i, ln in enumerate(lines):
        m = _HEADING_RE.match(ln)
        if m and ln.rstrip().endswith(tag):
            level = len(m.group(1))
            out = []
            for nxt in lines[i + 1:]:
                m2 = _HEADING_RE.match(nxt)
                if m2 and len(m2.group(1)) <= level:
                    break
                out.append(nxt)
            return "\n".join(out).strip()
    return None


def _resolve_text(u: Unit, skills: "dict[str, Unit]") -> str:
    frm = u.spec.get("from")
    if frm is None:
        if not u.text:
            raise UnitError(u.where, "no text", "the unit has no body and no `from:`")
        return u.text
    if u.text:
        raise UnitError(u.where, "two texts",
                        "the unit has both a body and `from:`; the text comes from one of them")
    sid, anchor = frm.split("#", 1)
    skill = skills.get(sid)
    if skill is None:
        raise UnitError(u.where, "bad from", f"`from: {frm}` names no skill unit `{sid}`")
    text = section(skill.body, anchor)
    if not text:
        raise UnitError(u.where, "bad from",
                        f"`from: {frm}`: {skill.where} has no non-empty section `{{#{anchor}}}`")
    return text


def _check_text(u: Unit, text: str) -> None:
    size = len(text.encode("utf-8"))
    limit = SIZE_LIMITS[u.kind]
    if size > limit:
        raise UnitError(u.where, "text over its size limit",
                        f"the {SIZE_NAMES[u.kind]} is {size:,} B; the limit for {u.kind} units is "
                        f"{limit:,} B (ADR-0007 #contract)")
    if u.kind in ("deny", "ask") and not _INSTEAD_RE.search(text):
        raise UnitError(u.where, "no Instead: line",
                        f"a {u.kind}'s text states the command to run instead, on a line that "
                        "starts `Instead:`")


def _check_probes(u: Unit) -> None:
    if u.kind == "ask" and not ASK_VERIFIED:
        raise UnitError(u.where, "ask is probe-gated",
                        "an `ask` unit compiles only once ASK_VERIFIED is on (probe P2's "
                        "committed evidence, task-I1.b0); it is off")
    for i, b in enumerate(u.bind):
        if b.get("mode") == "context" and not CONTEXT_VERIFIED and "fallback" not in b:
            raise UnitError(u.where, "context without a fallback",
                            f"bind[{i}] is a `context` inject with no `fallback`, and "
                            "CONTEXT_VERIFIED is off (probe P1): name `fallback: gate` or "
                            "`fallback: post`")


def _entry(u: Unit, text: str) -> dict:
    e = {"id": u.id, "kind": u.kind, "bind": u.bind, "priority": u.priority,
         "census": list(u.spec.get("census") or []), "text": text,
         "source": u.where}
    for k in ("from", "on", "run"):
        if k in u.spec:
            e[k] = u.spec[k]
    e["sha"] = hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False)
                              .encode("utf-8")).hexdigest()
    return e


def prefilter_table(entries: "list[dict]") -> "dict[str, list[str] | None]":
    """Per event, the sorted literals a raw envelope must contain for the dispatcher to read it;
    None for an event where some dispatchable bind has no prefilter (every envelope is read).
    Built from the dispatchable kinds only (lead ruling on RED's trap 5)."""
    lits: "dict[str, set | None]" = {}
    for e in entries:
        if e["kind"] not in DISPATCHABLE:
            continue
        for b in e["bind"]:
            ev = b["event"]
            if "prefilter" not in b:
                lits[ev] = None
            elif ev not in lits or lits[ev] is not None:
                lits.setdefault(ev, set()).add(b["prefilter"])
    return {ev: (sorted(v) if v is not None else None) for ev, v in sorted(lits.items())}


def compile_layers(layers: Layers) -> bytes:
    """The compiled file's bytes for `layers`, or CompileRefused naming every bad file and
    rule. Deterministic: units sorted by id, keys sorted, no time, no absolute path."""
    errors = list(layers.errors)
    by_id: "dict[str, list[Unit]]" = {}
    for u in layers.units:
        by_id.setdefault(u.id, []).append(u)
    for uid, us in sorted(by_id.items()):
        if len(us) > 1:
            names = ", ".join(sorted(x.where for x in us))
            for x in us:
                errors.append(UnitError(x.where, "duplicate id",
                                        f"the id `{uid}` is used by {len(us)} units ({names})"))
    skills = {u.id: u for u in layers.units if u.kind == "skill" and len(by_id[u.id]) == 1}
    entries = []
    for uid in sorted(by_id):
        if len(by_id[uid]) > 1:
            continue
        u = by_id[uid][0]
        try:
            text = _resolve_text(u, skills)
            _check_text(u, text)
            _check_probes(u)
        except UnitError as e:
            errors.append(e)
            continue
        entries.append(_entry(u, text))
    if errors:
        raise CompileRefused(errors)
    doc = {"schema": COMPILED_SCHEMA,
           "generated_by": "rmx install-hooks --apply (task-I1.b1; do not edit)",
           "units": entries, "prefilter": prefilter_table(entries)}
    return (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def compile_project(project_root: "Path | str") -> bytes:
    """`compile_layers(load_layers(project_root))`."""
    return compile_layers(load_layers(project_root))


# ---- decide ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Fired:
    unit: str
    kind: str
    outcome: str
    bind: int
    priority: int


def _outcome(kind: str, b: dict) -> "str | None":
    if kind in ("deny", "ask", "check", "rule", "skill"):
        return kind
    mode = b.get("mode")
    if mode == "context" and not CONTEXT_VERIFIED:
        return b.get("fallback")        # None: no verified route, so nothing is delivered
    return mode


def _input_matches(b: dict, tool_input: dict) -> bool:
    """`match` (every pair a `tool_input` string value searched by its ERE) and `unless` (an ERE
    over the matched values, or over every string value when there is no `match`)."""
    match = b.get("match") or {}
    vals = []
    for key, ere in match.items():
        v = tool_input.get(key)
        if not isinstance(v, str) or not re.search(ere, v):
            return False
        vals.append(v)
    unless = b.get("unless")
    if unless:
        if not match:
            vals = [v for v in tool_input.values() if isinstance(v, str)]
        if any(re.search(unless, v) for v in vals):
            return False
    return True


def _who(spec: str, env: dict) -> bool:
    if spec == "any":
        return True
    agent_id = env.get("agent_id")
    if spec == "main":
        return not agent_id
    if spec == "subagent":
        return bool(agent_id)
    want = spec[len("agent:"):]
    have = str(env.get("agent_type") or "")
    return bool(agent_id) and (have == want or have.endswith(":" + want))


def store_tree(cwd: "str | None") -> "Path | None":
    """The nearest directory at or above `cwd` that holds a project store (`.refmatrix/`), the
    user-level home store excluded; None when there is none or no cwd."""
    if not cwd:
        return None
    p = Path(cwd)
    if not p.is_dir():
        return None
    from refmatrix.taxonomy import user_home
    home = user_home()
    for d in (p, *p.parents):
        st = d / ".refmatrix"
        if st.is_dir() and st != home:
            return d
    return None


def _where(spec: str, cwd: "str | None") -> bool:
    if spec == "any":
        return True
    if spec == "store":
        return store_tree(cwd) is not None
    if spec == "no-store":
        return bool(cwd) and Path(cwd).is_dir() and store_tree(cwd) is None
    glob = spec[len("path:"):]
    return bool(cwd) and (fnmatch.fnmatch(cwd, glob)
                          or fnmatch.fnmatch(str(Path(cwd).resolve()), glob))


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(cwd: Path, *args: str) -> str:
    """One git call, bounded by GIT_TIMEOUT_S; a timeout, a missing git or a non-zero exit
    raises StateUnreadable naming the call."""
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
           "-c", "user.name=rmx-fixture", "-c", "user.email=rmx-fixture@localhost", *args]
    try:
        r = subprocess.run(cmd, cwd=str(cwd), env=_git_env(), capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise StateUnreadable(f"`git {' '.join(args)}` in {cwd} timed out after "
                              f"{GIT_TIMEOUT_S}s") from e
    except OSError as e:
        raise StateUnreadable(f"`git {' '.join(args)}` in {cwd} could not run: {e}") from e
    if r.returncode != 0:
        err = " / ".join(ln.strip() for ln in (r.stderr or r.stdout).splitlines() if ln.strip())
        raise StateUnreadable(f"`git {' '.join(args)}` in {cwd} exited {r.returncode}: "
                              f"{err or '(no output)'}")
    return r.stdout


def _when(when: dict, cwd: "str | None") -> bool:
    """Every named state holds. `git-dirty`: a tracked file under `paths` differs from HEAD
    (staged or not). `git-head`: the HEAD commit touched a file under `paths`. `repo` is
    relative to the envelope's cwd. A state that cannot be read raises StateUnreadable."""
    if not cwd:
        raise StateUnreadable("the envelope has no cwd, so its `when:` state cannot be read")
    for state, arg in when.items():
        repo = Path(cwd) / arg.get("repo", ".")
        paths = list(arg.get("paths") or [])
        if state == "git-dirty":
            out = _git(repo, "status", "--porcelain", "--untracked-files=no", "--", *paths)
        else:
            out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root",
                       "HEAD", "--", *paths)
        if not out.strip():
            return False
    return True


def _bind_fires(b: dict, env: dict) -> bool:
    if env.get("hook_event_name") != b["event"]:
        return False
    tool = b.get("tool")
    if tool and not re.fullmatch(tool, str(env.get("tool_name") or "")):
        return False
    ti = env.get("tool_input")
    if not _input_matches(b, ti if isinstance(ti, dict) else {}):
        return False
    if not _who(b.get("who", "any"), env):
        return False
    cwd = env.get("cwd")
    if not _where(b.get("where", "any"), cwd):
        return False
    if b.get("when") and not _when(b["when"], cwd):
        return False
    return True


def decide(entries: "list[dict]", envelope: dict) -> "list[Fired]":
    """The decision for one hook envelope over compiled entries (or `Unit.decision_entry()`s):
    every unit that fires, by its first firing bind, most decisive first (deny, ask, gate,
    context, post, then the rest), higher `priority` first within an outcome. The ONE decision
    the fixture runner and the dispatcher (I1.b3) share. Raises StateUnreadable when a `when:`
    state cannot be read."""
    out = []
    for e in entries:
        for i, b in enumerate(e["bind"]):
            if _bind_fires(b, envelope):
                oc = _outcome(e["kind"], b)
                if oc:
                    out.append(Fired(e["id"], e["kind"], oc, i, int(e.get("priority") or 0)))
                break
    out.sort(key=lambda f: (PRECEDENCE[f.outcome], -f.priority, f.unit))
    return out


# ---- the fixture runner ----------------------------------------------------------------------

@dataclass(frozen=True)
class FixtureResult:
    unit: str
    side: str
    index: int
    ok: bool
    outcome: "str | None"
    reason: str


def _safe_rel(rel: str) -> str:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise FixtureStateError(f"repo path {rel!r} must stay inside the fixture repo")
    return rel


def _build_state(tmp: Path, fx: dict) -> None:
    repo = fx.get("repo")
    if repo is not None:
        files = repo.get("files") or {}
        for rel, content in files.items():
            p = tmp / _safe_rel(str(rel))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(content), encoding="utf-8")
        try:
            _git(tmp, "init", "-q")
            _git(tmp, "symbolic-ref", "HEAD", f"refs/heads/{repo.get('branch') or 'main'}")
            commits = int(repo.get("commits") or 0)
            for n in range(commits):
                if n == 0:
                    _git(tmp, "add", "-A")
                    _git(tmp, "commit", "-q", "--allow-empty", "-m", "fixture commit 1")
                else:
                    _git(tmp, "commit", "-q", "--allow-empty", "-m", f"fixture commit {n + 1}")
        except StateUnreadable as e:
            raise FixtureStateError(str(e)) from e
        for rel in repo.get("dirty") or []:
            if str(rel) not in {str(k) for k in files} or commits < 1:
                raise FixtureStateError(f"dirty path {rel!r} is not a committed file of the "
                                        "fixture repo")
            with (tmp / _safe_rel(str(rel))).open("a", encoding="utf-8") as f:
                f.write("fixture: modified after the commits\n")
    if fx.get("store") == "present":
        (tmp / ".refmatrix").mkdir(exist_ok=True)


def _run_one(entry: dict, side: str, index: int, fx: dict) -> FixtureResult:
    uid = entry["id"]
    env = dict(fx["envelope"])
    tmp = None
    try:
        if "repo" in fx or "store" in fx:
            tmp = Path(tempfile.mkdtemp(prefix="rmx-fx-"))
            try:
                _build_state(tmp, fx)
            except (FixtureStateError, OSError, ValueError) as e:
                return FixtureResult(uid, side, index, False, None,
                                     f"its repo/store state could not be built: {e}")
            env["cwd"] = str(tmp)
        try:
            fired = decide([entry], env)
        except StateUnreadable as e:
            return FixtureResult(uid, side, index, False, None, f"decide() failed: {e}")
        outcome = fired[0].outcome if fired else None
        if side == "pass":
            if outcome:
                return FixtureResult(uid, side, index, False, outcome,
                                     f"a pass envelope fired ({outcome})")
            return FixtureResult(uid, side, index, True, None, "")
        if not outcome:
            return FixtureResult(uid, side, index, False, None,
                                 "a fire envelope gave no outcome: no bind matched it")
        pre = entry["bind"][fired[0].bind].get("prefilter")
        raw = json.dumps(env, ensure_ascii=False)
        if pre and pre not in raw:
            return FixtureResult(uid, side, index, False, outcome,
                                 f"the raw envelope does not contain the prefilter {pre!r}, so "
                                 "the dispatcher would never read it")
        return FixtureResult(uid, side, index, True, outcome, "")
    finally:
        if tmp is not None:
            try:
                shutil.rmtree(tmp)
            except OSError as e:
                print(f"rmx: fixture temp dir {tmp} not removed: {e}", file=sys.stderr)


def run_fixtures(unit: Unit) -> "list[FixtureResult]":
    """Every `fire` and `pass` envelope of `unit` through `decide` (task-I1.b1 #d4): a fire
    envelope must give the unit's outcome AND carry the fired bind's prefilter in its raw JSON;
    a pass envelope must give nothing. `repo:` / `store:` states are built in a temp directory
    (real files, real `git`) and the envelope's `cwd` is set to it."""
    entry = unit.decision_entry()
    out = []
    for side in FIXTURE_SIDES:
        for i, fx in enumerate(unit.fixtures.get(side) or []):
            out.append(_run_one(entry, side, i, fx))
    return out


# ---- replay ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplayHit:
    ts: str
    session_hash: str
    text_sha: str
    text: str


@dataclass
class ReplayReport:
    unit: Unit
    ring_dir: Path
    days: int
    files: int = 0
    scanned: int = 0
    unreadable: int = 0
    hits: "list[ReplayHit]" = field(default_factory=list)
    tool_binds: int = 0


def find_unit(project_root: "Path | str", uid: str) -> Unit:
    """The unit `uid` of either layer, compiled or not (a deny is replayed before it ships,
    ADR-0007 #fixtures). Raises LookupError naming the unreadable files when it is absent."""
    layers = load_layers(project_root)
    hits = [u for u in layers.units if u.id == uid]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise LookupError(f"the id `{uid}` is used by {len(hits)} units: "
                          + ", ".join(u.where for u in hits))
    msg = f"no unit `{uid}` in the packaged or the local layer of {project_root}"
    if layers.errors:
        msg += "; unreadable unit files: " + "; ".join(str(e) for e in layers.errors)
    raise LookupError(msg)


def _ring_call(ev: dict) -> "tuple[str, dict] | None":
    """(tool name, tool_input) of a ring tool event, rebuilt from its `terse` and `detail`
    (`cli._tool_event_fields`: Bash keeps the command, other tools a JSON of their input)."""
    detail = ev.get("detail")
    if not isinstance(detail, str):
        return None
    if ev.get("kind") == "git":
        return "Bash", {"command": detail}
    tool = str(ev.get("terse") or "").split(" ", 1)[0] or "tool"
    if tool == "Bash":
        return tool, {"command": detail}
    try:
        ti = json.loads(detail)
    except json.JSONDecodeError:
        return tool, {"command": detail}
    return tool, (ti if isinstance(ti, dict) else {"command": detail})


def replay(store_root: "Path | str", unit: Unit, *, days: int = 30,
           now: "float | None" = None) -> ReplayReport:
    """Read-only over `<store>/stm/*.jsonl` as files (task-I1.b1 #d7): every tool event of the
    last `days` days, matched against the unit's tool-event binds (tool, `match`, `unless`).
    `who`, `where` and `when` are not evaluated: the ring holds no agent id, no cwd and no git
    state. No daemon, no store open."""
    ring = Path(store_root) / "stm"
    rep = ReplayReport(unit=unit, ring_dir=ring, days=days)
    binds = [b for b in unit.bind if b.get("event") in TOOL_EVENTS]
    rep.tool_binds = len(binds)
    cutoff = (now if now is not None else time.time()) - days * 86400
    if not ring.is_dir():
        return rep
    for path in sorted(ring.glob("*.jsonl")):
        rep.files += 1
        try:
            fh = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            rep.unreadable += 1
            continue
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    rep.unreadable += 1
                    continue
                if not isinstance(ev, dict) or ev.get("kind") not in ("tool", "git"):
                    continue
                if ev.get("kind") == "git" and not isinstance(ev.get("detail"), str):
                    continue
                ts = str(ev.get("ts") or "")
                try:
                    t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    rep.unreadable += 1
                    continue
                if t < cutoff:
                    continue
                rep.scanned += 1
                call = _ring_call(ev)
                if call is None:
                    continue
                tool, ti = call
                for b in binds:
                    if b.get("tool") and not re.fullmatch(b["tool"], tool):
                        continue
                    if not _input_matches(b, ti):
                        continue
                    text = ev["detail"]
                    rep.hits.append(ReplayHit(
                        ts=ts,
                        session_hash=hashlib.sha256(
                            str(ev.get("session") or path.stem).encode()).hexdigest()[:12],
                        text_sha=hashlib.sha256(text.encode()).hexdigest()[:12],
                        text=text))
                    break
    return rep


def format_replay(rep: ReplayReport, *, show: bool) -> "list[str]":
    """The replay's lines. The matched text is printed only with `show` (to the terminal; the
    hashes are what a report may carry)."""
    from refmatrix import stm
    u = rep.unit
    out = [f"rules replay {u.id} ({u.kind}, {u.where}): the last {rep.days} days of "
           f"{rep.ring_dir}"]
    if not rep.ring_dir.is_dir():
        out.append(f"no STM ring directory at {rep.ring_dir}")
    if rep.tool_binds == 0:
        out.append("the unit binds no tool event (PreToolUse / PostToolUse): nothing in the "
                   "ring can match it")
    out.append(f"scanned {rep.scanned} tool events in {rep.files} ring file(s); "
               f"hits {len(rep.hits)}")
    if rep.unreadable:
        out.append(f"unreadable: {rep.unreadable} ring line(s) or file(s) could not be parsed "
                   "and were not scanned")
    for h in rep.hits:
        out.append(f"  {h.ts}  session {h.session_hash}  sha256 {h.text_sha}")
        if show:
            out.append(f"      {h.text}")
    out.append(f"limits: each event's detail is cut at stm.DETAIL_MAX = {stm.DETAIL_MAX} "
               "characters, so text past it is not matched; ring events carry no agent id, so "
               "a `who`-bound unit's count is an upper bound; `when` (git state) and `where` "
               "(the call's directory) are not evaluated.")
    return out
