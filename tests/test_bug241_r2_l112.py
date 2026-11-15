"""0.83.1 ch-bsd r1 fold (ruling L112): REDs for S1, S2 and M1.

Report: `workflow/bullshit/2026-11-14-2324-bug241-bug240-r1-13ffd77.md` (#s1 #s2 #m1); ruling
L112 in `workflow/plan-review-2026-11-13.md#lead`.

S1 (#s1). bug-241 moved markdown onto the GMD pass on EVERY code+docs ingest. On the daemon's
cooperative route (`_op_ingest_path` passes a yield hook; `ingest_path` wraps it in
`_CommitWindow`), `_ingest_markdown_gmd` takes no hook, so `ingest_gmd_paths` runs inside one
commit window with the store lock held throughout: measured 733 docs in 1027.7 s on a
repo-sized tree. That is the lock-holding wedge class of bug-085. Pinned here: a cooperative
`ingest_path` with a counting `yield_lock` sees yields DURING the GMD pass, on the cached route
(`_ingest_path_inner` -> `_ingest_markdown_gmd`) and on the tree route (`_ingest_tree` ->
`_ingest_markdown_gmd`). Attribution is by the `progress_cb` phase current at each yield.

S2 (#s2). A GMD pass that raises is printed to the daemon's stderr log and nowhere else; the
caller sees `ingested N entities`, exit 0. Pinned: through the REAL daemon, a tree holding one
markdown file whose frontmatter `id:` is a list (`id: [a, b]`) -- real input; it makes
`ingest_gmd_paths` raise `TypeError: cannot use 'list' as a dict key` (probed 2026-11-14), so
nothing is patched -- the `ingest_path` op's result carries a GMD-failure count > 0 (any int
field whose key names `gmd`), and `rmx ingest <dir>` prints an `Error:` line naming the GMD
pass and exits non-zero (the `_say_vector_delete_failures` shape).

M1 (#m1). `rmx ingest <FILE>` reaches `refuse_file_target` only inside `ingest_path`, after
`_store(write=True)`: with the daemon BUSY the user reads "busy -- writes go through the
daemon", not the `rmx sync -f` refusal. Pinned with a real busy daemon: the spawned daemon is
SIGSTOPped, so it is alive and does not answer ping -- the state `require_daemon` classifies as
busy -- and resumed before teardown.

Every store is a throwaway under a SHORT `/tmp` mkdtemp root (macOS `sun_path`); the daemons are
spawned by the dev `rmx` with this checkout's code (PYTHONPATH). No mocks.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RMX = REPO / ".venv-eval" / "bin" / "rmx"

N_MD = 25          # > 10: the GMD pass's own yield cadence, and > yield_every below
YIELD_EVERY = 5

METADATA = (".tldr/cache/semantic/metadata.json", {"units": [
    {"qualified_name": "src/pkg/a.py::hello", "file": "src/pkg/a.py", "name": "hello",
     "unit_type": "function", "line": 1, "language": "python"}]})
CALL_GRAPH = (".tldr/cache/call_graph.json", {"edges": [
    {"from_file": "src/pkg/a.py", "from_func": "hello",
     "to_file": "src/pkg/a.py", "to_func": "bye"}]})
CACHES = {"metadata": METADATA, "call_graph": CALL_GRAPH, "none": None}

# Real input that makes `ingest_gmd_paths` raise (a list-valued frontmatter `id:`).
BAD_MD = ('---\ngmd: "0.1"\nid: [a, b]\ntitle: "bad"\ntags: [t]\n---\n\n'
          "# Bad {#root}\n\nA list id.\n")


def _gmd(doc_id: str, i: int) -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "{doc_id}"\ntags: [t]\n---\n\n'
            f"# {doc_id} {{#root}}\n\n## Part {i} {{#p{i}}}\n\nBody {i} about frobnication.\n")


def _project(base: Path, cache: str, *, bad: bool = False, n_md: int = 3) -> Path:
    proj = base / "proj"
    files = {"src/pkg/a.py": "def hello():\n    return bye()\n\n\ndef bye():\n    return 1\n"}
    for i in range(n_md):
        files[f"docs/d{i:02d}.md"] = _gmd(f"d{i:02d}", i)
    if bad:
        files["docs/bad.md"] = BAD_MD
    for rel, text in files.items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if CACHES[cache] is not None:
        rel, payload = CACHES[cache]
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
    return proj


def _env(root: Path) -> dict:
    return {**os.environ, "REFMATRIX_ROOT": str(root), "RMX_INVOCATION_SOURCE": "eval",
            "PYTHONPATH": str(REPO / "src")}


def _rmx(env: dict, *args: str, timeout: int = 300, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(RMX), *args], env=env, capture_output=True, text=True,
                          timeout=timeout, **kw)


def _init(proj: Path) -> tuple[Path, dict]:
    root = proj / ".refmatrix"
    env = _env(root)
    r = _rmx(env, "init", "--path", str(proj), "--no-hooks", "--no-agents", "--no-memory-hooks")
    assert r.returncode == 0, r.stdout + r.stderr
    return root, env


def _start(root: Path, env: dict) -> None:
    r = _rmx(env, "daemon", "start", "--no-watch", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    for _ in range(120):
        if list(root.glob("*.sock")):
            return
        time.sleep(0.5)
    raise AssertionError(f"daemon socket never appeared under {root}")


@pytest.fixture
def base():
    assert RMX.exists(), f"dev rmx missing at {RMX}"
    b = Path(tempfile.mkdtemp(prefix="b241r2.", dir="/tmp")).resolve()
    yield b
    shutil.rmtree(b, ignore_errors=True)


# ---- S1 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("cache,phase", [
    ("metadata", "code+docs: markdown/gmd"),     # `_ingest_path_inner` -> the GMD pass
    ("call_graph", "code+docs: markdown/gmd"),
    ("none", "code+docs: tldr/tree"),            # `_ingest_tree` -> the GMD pass
])
def test_s1_a_cooperative_ingest_yields_during_the_markdown_gmd_pass(base, cache, phase):
    from refmatrix.ingest import ingest_path
    from refmatrix.store import Store
    proj = _project(base, cache, n_md=N_MD)
    root = proj / ".refmatrix"
    root.mkdir()
    current = {"phase": None}
    yields: dict = {}

    def _progress(name: str, done: int = 0, total: int = 0) -> None:
        current["phase"] = name

    def _yield() -> None:
        yields[current["phase"]] = yields.get(current["phase"], 0) + 1

    s = Store(root)
    try:
        with s.with_partition("proj"):
            ingest_path(s, proj, yield_lock=_yield, yield_every=YIELD_EVERY,
                        progress_cb=_progress)
            gmd_docs = sum(1 for i in range(N_MD) if s.get_entity("doc", f"d{i:02d}"))
    finally:
        s.close()
    assert gmd_docs == N_MD, f"the GMD pass ingested {gmd_docs}/{N_MD} docs (fixture broken)"
    # >= 2, not > 0: one yield after the whole pass would still hold the lock throughout.
    assert yields.get(phase, 0) >= 2, (
        f"no yield during the markdown GMD pass ({N_MD} docs, yield_every={YIELD_EVERY}, "
        f"cache={cache}): the store lock is held for the whole pass; yields by phase: {yields}")


# ---- S2 ---------------------------------------------------------------------------------


@pytest.fixture(params=["metadata", "none"])
def bad_tree_daemon(base, request):
    proj = _project(base, request.param, bad=True)
    root, env = _init(proj)
    _start(root, env)
    try:
        yield {"proj": proj, "root": root, "env": env}
    finally:
        _rmx(env, "daemon", "stop", timeout=120)


def test_s2_the_ingest_op_result_counts_a_failed_gmd_pass(bad_tree_daemon):
    from refmatrix import daemon as daemon_mod
    c = bad_tree_daemon
    r = daemon_mod.call(c["root"], "ingest_path", {"path": str(c["proj"])},
                        timeout=180, retries=0)
    assert r.get("ok"), f"the ingest op itself failed: {r}"
    res = r.get("result") or {}
    counts = {k: v for k, v in res.items()
              if "gmd" in k.lower() and isinstance(v, int) and not isinstance(v, bool)}
    assert any(v > 0 for v in counts.values()), (
        f"a GMD pass that raised is not counted in the op result: {res}")


@pytest.mark.parametrize("route", ["daemon", "in_process"])
def test_s2_rmx_ingest_fails_loudly_naming_the_gmd_pass(base, route):
    proj = _project(base, "metadata", bad=True)
    root, env = _init(proj)
    if route == "daemon":
        _start(root, env)
    try:
        r = _rmx(env, "ingest", str(proj))
    finally:
        if route == "daemon":
            _rmx(env, "daemon", "stop", timeout=120)
    out = r.stdout + r.stderr
    errs = [ln for ln in out.splitlines() if ln.startswith("Error:")]
    assert r.returncode != 0, f"`rmx ingest` exited 0 after the GMD pass failed:\n{out}"
    assert any("gmd" in ln.lower() for ln in errs), (
        f"no `Error:` line naming the GMD pass; Error lines: {errs}\n{out}")


def test_s2_guard_a_clean_tree_ingests_quietly(base):
    """The loud path is for a failure only: the same tree without the bad file exits 0."""
    proj = _project(base, "metadata")
    root, env = _init(proj)
    _start(root, env)
    try:
        r = _rmx(env, "ingest", str(proj))
    finally:
        _rmx(env, "daemon", "stop", timeout=120)
    assert r.returncode == 0 and "Error:" not in r.stdout + r.stderr, r.stdout + r.stderr


# ---- M1 ---------------------------------------------------------------------------------


def test_m1_a_file_target_is_refused_naming_sync_while_the_daemon_is_busy(base):
    from refmatrix import discovery
    proj = _project(base, "none")
    root, env = _init(proj)
    _start(root, env)
    pid = discovery.daemon_status(root).get("pid")
    assert pid, "no daemon pid"
    os.kill(pid, signal.SIGSTOP)               # alive, not answering: `busy`
    try:
        st = discovery.daemon_status(root, retries=0)
        assert st.get("busy") and not st.get("up"), f"the daemon is not busy: {st}"
        r = _rmx(env, "ingest", str(proj / "docs" / "d00.md"), timeout=180)
    finally:
        os.kill(pid, signal.SIGCONT)
        _rmx(env, "daemon", "stop", timeout=120)
    out = r.stdout + r.stderr
    errs = [ln for ln in out.splitlines() if ln.startswith("Error:")]
    assert r.returncode != 0, out
    assert len(errs) == 1 and "rmx sync -f" in errs[0], (
        f"a file target under a busy daemon must get the `rmx sync -f` refusal: {errs}\n{out}")
    assert "busy" not in errs[0], f"the busy message won over the file refusal: {errs[0]!r}"
