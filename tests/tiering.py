"""Run tiers: the ONE place a test file's tier is decided (plan-29 task 29.4 `#r1`, sub-task 29.4a).

WHY. The suite had one way to run: every test, one process, file order (58:37 for the 0.83.0
release). The user asked on 2026-11-14 for the tests to run modularly; the sharded runner
(`scripts/ptest.py`, task-29.4 `#r2`) needs to know, per FILE, which tests may run beside
others and which need the owning checkout. `tier_of(path)` is an ORDERED rule, the first match
wins, so a file has exactly one tier by construction (plan-29 D11):

1. `devtree` -- the verdict depends on the checkout being the owning one: a skip pinned in the
   conftest (`_FOREIGN_HOOKS_PINS`; the spec's `_CLONE_ONLY_SKIPS` was retired by bug-253), a
   read of the real home (`rmx_sandbox.real_home(` or the `RMX_SANDBOX_REAL_HOME` key), or an
   entry in `DEVTREE_FILES`. The real-home rule is narrowed by `SANDBOX_SELF_TESTS` (ruling
   L192 (1), 2026-11-23): the sandbox's own refusal probes read the real home to name the
   target they must be REFUSED, and the refusal fires before any live touch.
2. `timing` -- the file holds a `legacy` or `feature-bound` entry in `wallclock_allow.json`.
   Derived from that list only; `budget-outcome` entries do not count (ruling L192 (5): they
   are real-daemon outcome tests, not wall-clock bounds).
3. `daemon` -- the file, or a `tests/` helper it imports (followed transitively), carries a
   process or socket signal from `SIGNALS`, matched on the syntax tree (`_TEXT_SIGNALS` on the
   source text for the argv shapes a tree walk cannot name).
4. `unit` -- everything else.

Everything read besides the file itself comes from the file's OWN `tests/` directory, so a
throwaway checkout (tests/suite_health_tree.py) is tiered by its own conftest, allow list and
helpers. A test file in a subdirectory, a missing file or one that does not parse is a
`TierError`, never a default (`#r1-also`). Stdlib only: the runner loads this module by path
into whatever interpreter runs it.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

TIERS = ("unit", "daemon", "devtree", "timing")


class TierError(ValueError):
    """A test file `tier_of` cannot place: not directly in a `tests/` directory, missing, not
    readable or not parseable (task-29.4 `#r1-also`: an error, not a default tier)."""


# ---- the named lists (repo-relative path -> reason) ------------------------------------------

DEVTREE_FILES: dict = {
    "tests/test_bug230_repo_scope_gate.py":
        "bug-230: rebuilds the dev-tree shape of the repo-scope GMD gate, whose parity step "
        "reads the owning checkout's .refmatrix/.refmatrix_ignore",
}
# Not listed (task-29.4 #r1 "a file leaves the list when its dependency is removed"):
# tests/test_search_hooks.py (bug-168): T0.2 R2.2 (ruling L142 (5), 2026-11-15) made its
# rewriter tests independent of the ambient learn switch under the real home.

SANDBOX_SELF_TESTS: dict = {
    "tests/test_sandbox_children.py":
        "reads the real home only to name the hub socket a child must be REFUSED; the refusal "
        "fires before any live touch (ruling L192 (1))",
    "tests/test_sandbox_refusal.py":
        "the 23.0 refusal probes: the real home names the targets they must be refused on, and "
        "the refusal fires before any live touch (ruling L192 (1))",
    "tests/test_sandbox_hardening.py":
        "reads the real home to name a denied path; the probe is refused before it touches it "
        "(ruling L192 (1))",
    "tests/test_sandbox_child_extensions.py":
        "reads the real home to name the denied hub socket and connect log; refused before any "
        "live touch (ruling L192 (1))",
    "tests/test_sandbox_redirect.py":
        "proves the redirect moved HOME off the real home (and plants a decoy real home); it "
        "compares paths, it does not open the live ones (ruling L192 (1))",
}

ALWAYS_FILES: dict = {
    "tests/test_docs_generated.py":
        "generated artifacts: the CLI tree and the hooks table (task-29.4 #r6-parts always)",
    "tests/test_verb_parity.py": "MCP / CLI parity over the verb registry (#r6-parts always)",
    "tests/test_bug212_r4_red.py": "the catalog-opener census (#r6-parts always)",
    "tests/test_repo_hooks_in_sync.py":
        "the installed hooks equal the generated ones (#r6-parts always)",
    "tests/test_gmd_lint_requires_version.py":
        "the repo-scope GMD gate is clean (#r6-parts always)",
    "tests/test_version_single_source.py": "one version string (#r6-parts always)",
    "tests/test_wallclock_census.py": "task-29.4's wall-clock census (#r3-census)",
    "tests/test_budget_outcome_census.py": "task-29.4's budget-outcome census (#r3-budget-census)",
    "tests/test_tmp_root_census.py": "task-29.4's tmp-root census (#r5)",
    "tests/test_suite_discipline.py":
        "CLAUDE.md #test-discipline census (a repo-wide guard; a merged-master verify set "
        "always carries it)",
    "tests/test_mock_registry_coverage.py":
        "every double is in workflow/test_mock_registry.md (a repo-wide guard)",
    "tests/test_deferrals_clean.py": "workflow/deferral_registry.md is clean (a repo-wide guard)",
}

# The serial group (task-29.4 #r2-shared): files that may not run beside another shard. It runs
# as one extra shard after the others finish; it is not a tier. EMPTY at 29.4a's base
# (33825985), measured 2026-11-23 rather than copied from the spec's f3709d2 count:
# - fixed TCP ports: no test binds one. Every `.bind(` in tests/ is an AF_UNIX path under a
#   per-test root; the `port=7777` / `7799` / `9999` literals render plists, set an attribute
#   on an object that never serves, or probe a port with no listener.
# - shared logs: the one test reading `live-socket-touches.log` (test_sandbox_refusal.py)
#   reads it from its own offset and filters on its own test names; none asserts a size.
SERIAL_GROUP: dict = {}


# ---- the signal table ------------------------------------------------------------------------

# Imported modules whose presence is a process / socket signal.
_SIGNAL_MODULES = {
    "subprocess": "spawn", "multiprocessing": "spawn", "socketserver": "socket",
    "uvicorn": "socket",
}
# `module.attr` references (a call or not): `os.exec*` / `os.spawn*` are prefixes.
_SIGNAL_DOTTED = {
    "os.fork": "spawn", "os.forkpty": "spawn", "os.posix_spawn": "spawn",
    "os.posix_spawnp": "spawn", "os.system": "spawn", "os.popen": "spawn", "pty.fork": "spawn",
    "socket.socket": "socket", "socket.AF_UNIX": "socket", "socket.socketpair": "socket",
}
_SIGNAL_DOTTED_PREFIX = {"os.exec": "spawn", "os.spawn": "spawn"}
# Bare names: a Name, an attribute's last part, an imported name, or a function argument.
_SIGNAL_NAMES = {
    "Popen": "spawn", "pytester": "spawn", "testdir": "spawn", "runpytest": "spawn",
    "runpytest_subprocess": "spawn", "spawn_daemon_subprocess": "daemon",
    "SandboxDaemon": "daemon", "serve_forever": "daemon", "serve_foreground": "daemon",
    "AF_UNIX": "socket", "SentenceTransformer": "models", "CrossEncoder": "models",
    "models_local": "models", "start_worker": "models", "SharedWorkerClient": "models",
    "SubprocWorker": "models",
}
# argv shapes a tree walk cannot name: `["daemon", "start"]`, `["hub", "start"]`.
_TEXT_SIGNALS = {
    "daemon": re.compile(r"[\"']daemon[\"'],\s*[\"']start[\"']"),
    "hub": re.compile(r"[\"']hub[\"'],\s*[\"']start[\"']|\bhub(?:_mod)?\.(?:serve|run|main)\("),
}
SIGNALS = {"modules": _SIGNAL_MODULES, "dotted": _SIGNAL_DOTTED,
           "dotted_prefix": _SIGNAL_DOTTED_PREFIX, "names": _SIGNAL_NAMES,
           "text": {k: v.pattern for k, v in _TEXT_SIGNALS.items()}}

# The conftest dicts whose keys pin a skip (`tests/<file>::<test>`).
_PIN_DICTS = ("_FOREIGN_HOOKS_PINS", "_CLONE_ONLY_SKIPS")
_REAL_HOME_KEY = "RMX_SANDBOX_REAL_HOME"
_TIMING_KINDS = ("legacy", "feature-bound")
# Loaded by every test, never imported for its own signals: following it would put every file
# that imports `source_of` from it in tier `daemon`.
_NOT_A_HELPER = {"conftest"}


# ---- reading a file --------------------------------------------------------------------------

_CACHE: dict = {}


def _stamp(p: Path) -> tuple:
    st = p.stat()
    return (st.st_mtime_ns, st.st_size)


def _parse(p: Path) -> "tuple[ast.AST, str]":
    """The syntax tree and source of `p`, cached by (path, mtime, size)."""
    key = str(p)
    try:
        stamp = _stamp(p)
    except OSError as exc:
        raise TierError(f"{p}: cannot read ({exc})") from exc
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1], hit[2]
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(p))
    except (OSError, UnicodeDecodeError) as exc:
        raise TierError(f"{p}: cannot read ({exc})") from exc
    except SyntaxError as exc:
        raise TierError(f"{p}: does not parse ({exc.msg}, line {exc.lineno})") from exc
    _CACHE[key] = (stamp, tree, src)
    return tree, src


def _dotted(node: ast.AST) -> "str | None":
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _own_signals(tree: ast.AST, src: str) -> set:
    """The signal kinds (`spawn`, `daemon`, `socket`, `hub`, `models`) in ONE module."""
    kinds: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                root = a.name.split(".")[0]
                if root in _SIGNAL_MODULES:
                    kinds.add(_SIGNAL_MODULES[root])
        elif isinstance(n, ast.ImportFrom):
            mod = (n.module or "").split(".")[0]
            if mod in _SIGNAL_MODULES and n.level == 0:
                kinds.add(_SIGNAL_MODULES[mod])
            for a in n.names:
                if a.name in _SIGNAL_NAMES:
                    kinds.add(_SIGNAL_NAMES[a.name])
                full = f"{n.module}.{a.name}" if n.module else a.name
                if full in _SIGNAL_DOTTED:
                    kinds.add(_SIGNAL_DOTTED[full])
        elif isinstance(n, ast.Attribute):
            if n.attr in _SIGNAL_NAMES:
                kinds.add(_SIGNAL_NAMES[n.attr])
            d = _dotted(n)
            if d is not None:
                if d in _SIGNAL_DOTTED:
                    kinds.add(_SIGNAL_DOTTED[d])
                for pre, k in _SIGNAL_DOTTED_PREFIX.items():
                    if d.startswith(pre):
                        kinds.add(k)
        elif isinstance(n, ast.Name):
            if n.id in _SIGNAL_NAMES:
                kinds.add(_SIGNAL_NAMES[n.id])
        elif isinstance(n, ast.arg):
            if n.arg in _SIGNAL_NAMES:
                kinds.add(_SIGNAL_NAMES[n.arg])
    for k, rx in _TEXT_SIGNALS.items():
        if rx.search(src):
            kinds.add(k)
    return kinds


def _helpers(tree: ast.AST, tests_dir: Path) -> set:
    """The `tests/` helper modules ONE module imports: `from tests.x import …`,
    `from tests import x`, `import tests.x` (lazy imports inside functions count)."""
    names: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            if n.module == "tests":
                names |= {a.name for a in n.names}
            elif n.module.startswith("tests."):
                names.add(n.module.split(".")[1])
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("tests."):
                    names.add(a.name.split(".")[1])
    return {tests_dir / f"{m}.py" for m in names - _NOT_A_HELPER
            if (tests_dir / f"{m}.py").is_file()}


def signals_of(path) -> set:
    """Every signal kind in `path` and the `tests/` helpers it imports, followed transitively.
    A helper that does not parse is a `TierError` too: its signals cannot be read."""
    p = Path(path)
    tests_dir = p.parent
    seen = {p}
    todo = [p]
    kinds: set = set()
    while todo:
        cur = todo.pop()
        tree, src = _parse(cur)
        kinds |= _own_signals(tree, src)
        for h in _helpers(tree, tests_dir):
            if h not in seen:
                seen.add(h)
                todo.append(h)
    return kinds


def _is_environ(node: ast.AST) -> bool:
    """`os.environ` / `environ` (the mapping an env lookup reads)."""
    d = _dotted(node)
    return d is not None and d.split(".")[-1] == "environ"


def _is_key(node: "ast.AST | None") -> bool:
    return isinstance(node, ast.Constant) and node.value == _REAL_HOME_KEY


def _reads_real_home(tree: ast.AST) -> bool:
    """A call of `real_home(...)` (bare or as an attribute), or an ENVIRONMENT LOOKUP of the
    `RMX_SANDBOX_REAL_HOME` key: `environ[KEY]`, `environ.get(KEY…)`, `getenv(KEY…)`, or
    `KEY in environ`. The key as a plain string elsewhere is not a read: a docstring, or an
    assert that a source text holds it (bsd-294a r1 s-1, ruling L197, 2026-11-24: that assert
    put test_suite_tiers.py in devtree, a seventh file, and devtree does not run in a clone)."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name == "real_home":
                return True
            first = n.args[0] if n.args else None
            if name == "getenv" and _is_key(first):
                return True
            if (name == "get" and isinstance(f, ast.Attribute) and _is_environ(f.value)
                    and _is_key(first)):
                return True
        elif isinstance(n, ast.Subscript) and _is_environ(n.value) and _is_key(n.slice):
            return True
        elif (isinstance(n, ast.Compare) and _is_key(n.left)
              and any(isinstance(o, ast.In) for o in n.ops)
              and any(_is_environ(c) for c in n.comparators)):
            return True
    return False


def _pinned_files(tests_dir: Path) -> set:
    """Test file names with a skip pin in `tests_dir/conftest.py` (the `_PIN_DICTS` keys)."""
    conf = tests_dir / "conftest.py"
    if not conf.is_file():
        return set()
    tree, _ = _parse(conf)
    out: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            targets, value = n.targets, n.value
        elif isinstance(n, ast.AnnAssign):
            targets, value = [n.target], n.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id in _PIN_DICTS for t in targets):
            continue
        if not isinstance(value, ast.Dict):
            raise TierError(f"{conf}: a skip-pin dict is not a literal dict; its keys cannot "
                            f"be read")
        for k in value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                out.add(Path(k.value.split("::", 1)[0]).name)
    return out


def _timing_files(tests_dir: Path) -> set:
    """Test file names holding a `legacy` / `feature-bound` entry in `wallclock_allow.json`."""
    allow = tests_dir / "wallclock_allow.json"
    if not allow.is_file():
        return set()
    try:
        data = json.loads(allow.read_text(encoding="utf-8"))
        entries = data["entries"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TierError(f"{allow}: cannot read the wall-clock allow list ({exc})") from exc
    return {Path(str(e["key"]).split("::", 1)[0]).name for e in entries
            if e.get("kind") in _TIMING_KINDS}


def _rel(p: Path) -> str:
    return f"tests/{p.name}"


def check_test_file(path) -> Path:
    """`path` as a Path, or `TierError` when it is not a readable top-level `tests/test_*.py`."""
    p = Path(path)
    if not p.name.startswith("test_") or p.suffix != ".py":
        raise TierError(f"{p}: not a test file (test_*.py)")
    if p.parent.name != "tests":
        raise TierError(f"{p}: a test file must sit directly in a tests/ directory, not in "
                        f"{p.parent.name}/ (task-29.4 #r1-also)")
    if not p.is_file():
        raise TierError(f"{p}: no such file")
    return p


def tier_of(path) -> str:
    """The run tier of one test file (module docstring; task-29.4 `#r1`)."""
    p = check_test_file(path)
    tree, _ = _parse(p)
    tests_dir = p.parent
    rel = _rel(p)
    if p.name in _pinned_files(tests_dir):
        return "devtree"
    if _reads_real_home(tree) and rel not in SANDBOX_SELF_TESTS:
        return "devtree"
    if rel in DEVTREE_FILES:
        return "devtree"
    if p.name in _timing_files(tests_dir):
        return "timing"
    if signals_of(p) & {"spawn", "daemon", "socket", "hub", "models"}:
        return "daemon"
    return "unit"


def loads_models(path) -> bool:
    """The file (or a helper it imports) starts a real model worker: the runner keeps such files
    in shards 0 and 1 (task-29.4 `#r2-shared`, at most 2 shards hold model-loading files)."""
    return "models" in signals_of(check_test_file(path))


def list_test_files(tests_dir) -> list:
    """Every `test_*.py` directly in `tests_dir`, sorted."""
    return sorted(Path(tests_dir).glob("test_*.py"))


if __name__ == "__main__":                      # pragma: no cover - a reading aid
    import sys
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    by: dict = {t: [] for t in TIERS}
    for f in list_test_files(d):
        by[tier_of(f)].append(f.name)
    for t in TIERS:
        print(f"{t:8s} {len(by[t]):4d}")
    print("devtree:", " ".join(by["devtree"]))
    print("timing:", " ".join(by["timing"]))
    print("models:", " ".join(f.name for f in list_test_files(d) if loads_models(f)))
