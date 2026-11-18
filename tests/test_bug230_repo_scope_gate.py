"""bug-230 — the repo-scope GMD gate test passed on a gate the sandbox had killed.

Registry: workflow/bug_registry.md row bug-230 (dev master f10b944).

On the dev tree after the bug-216 merge, tests/test_gmd_lint_requires_version.py::
test_the_repo_scope_is_clean_under_the_stricter_gate PASSED while erroring at teardown with
`SandboxViolation in a child process (it exited 86 …): open …/.refmatrix/.refmatrix_ignore`.
Two defects:

(1) The test accepted any exit but 2 as a clean tree, so a gate step that crashed (the parity
    step, killed by the sandbox with exit 86, printing no `: error` line) read as clean — the
    bug-179 "a gate that did not run reads as clean" shape again. Pinned here through the
    shared verdict `assert_gate_ran_clean`, fed a REAL `scripts/lint-gmd.sh` run whose parity
    step exits 86.

(2) bug-216 R3's scope-parity step must read THIS repo's `.refmatrix/.refmatrix_ignore`, and the
    sandbox denies every open under a live `.refmatrix/`. Choice: (2a), a narrow read-only allow
    for exactly `<checkout>/.refmatrix/.refmatrix_ignore`, carried in the deny set as
    `read_allow` (written by `build_deny`, read by `violation`, so the pytest process and every
    child agree). Why (2a) over the decoy copy (2b): a copy has to be READ from the live store
    to be made, which is the same open, made by the test instead of the gate; and a copy makes
    the repo-scope test lint a stand-in config instead of the one the commit gate reads. The
    ignore spec is configuration, not store data: a read-only open of that one file cannot lock
    a catalog, write a row or reach a socket. Everything else stays denied, and the tests below
    pin that: a write-mode open of the file, any `os.*` mutation of it, and a read of a
    `catalog.*.duckdb` beside it.

    The dev-tree shape is rebuilt in a throwaway checkout under a short mkdtemp root that HAS a
    `.refmatrix/.refmatrix_ignore`, with a deny set naming that checkout's `.refmatrix/` (a
    sandbox root of its own, so a refusal there never reaches the session's touches log). This
    clone itself has no `.refmatrix/`, and no test here creates one.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import rmx_sandbox
from tests.test_bug179_anchor_parity import PLANTED_FIXED, _gate_root
from tests.test_gmd_lint_requires_version import assert_gate_ran_clean

REPO = Path(__file__).resolve().parents[1]
IGNORE_REL = Path(".refmatrix") / ".refmatrix_ignore"
R4_SPEC = ".claude\n!.claude/PROJECT_PROFILE.md\nsrc/refmatrix/templates\n"


@pytest.fixture
def gate_roots():
    made: list = []
    repo_had = (REPO / ".refmatrix").exists()
    yield made
    for r in made:
        shutil.rmtree(r, ignore_errors=False)
    assert (REPO / ".refmatrix").exists() == repo_had, (
        "a bug-230 test created or removed this checkout's .refmatrix/")


def _run_gate(root: Path, env: "dict | None" = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in (env or os.environ).items() if k != "PYTHONPATH"}
    return subprocess.run(["bash", str(root / "scripts" / "lint-gmd.sh")], capture_output=True,
                          text=True, cwd=root, env=env, timeout=600)


# ================================================================ (1) a crashed step is not clean


def test_1_a_gate_whose_parity_step_crashed_fails_the_repo_scope_verdict(gate_roots):
    root = _gate_root(lint_src=None, doc=PLANTED_FIXED)
    gate_roots.append(root)
    (root / "scripts" / "check-gmd-parity.py").write_text(
        "import os, sys\nsys.stderr.write('killed like the sandbox kills a child\\n')\n"
        "os._exit(86)\n")
    r = _run_gate(root)
    out = r.stdout + r.stderr
    assert r.returncode == 86, f"precondition: the gate exits 86 when its parity step does:\n{out}"
    # The hole bug-230 is about: the pre-fix verdict (reject exit 2 and `: error` lines only)
    # accepts this run.
    old_verdict = r.returncode != 2 and not [l for l in out.splitlines() if ": error" in l]
    assert old_verdict, "precondition: the old verdict passes a crashed gate"
    with pytest.raises(AssertionError) as ei:
        assert_gate_ran_clean(r)
    assert "86" in str(ei.value), f"the failure must name the exit code: {ei.value}"


# ================================================================ (2a) the narrow read-only allow


@pytest.fixture
def checkout():
    """A throwaway checkout root with `.refmatrix/.refmatrix_ignore` and a catalog file beside
    it, and the deny set the sandbox builds for such a checkout plus the session's own."""
    base = Path(rmx_sandbox.short_root("b230")).resolve()
    (base / ".refmatrix").mkdir()
    (base / IGNORE_REL).write_text(R4_SPEC)
    (base / ".refmatrix" / "catalog.A.duckdb").write_bytes(b"not really a catalog")
    session = rmx_sandbox._STATE["deny"]
    deny = dict(session,
                paths=sorted(set(session["paths"]) | rmx_sandbox._variants(base / ".refmatrix")),
                read_allow=sorted(rmx_sandbox._variants(base / IGNORE_REL)))
    yield {"root": base, "deny": deny}
    shutil.rmtree(base)


def test_2a_a_read_only_open_of_the_ignore_spec_is_allowed(checkout):
    p = str(checkout["root"] / IGNORE_REL)
    for args in ((p, "r", os.O_RDONLY | os.O_CLOEXEC),           # io.open / Path.read_text
                 (p, None, os.O_RDONLY)):                          # os.open
        assert rmx_sandbox.violation("open", args, checkout["deny"]) is None, (
            f"a read-only open of {p} is refused: {args}")


@pytest.mark.parametrize("args", [
    ("w", os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
    ("a", os.O_WRONLY | os.O_CREAT | os.O_APPEND),
    ("r+", os.O_RDWR),
    (None, os.O_RDWR),
    (None, os.O_WRONLY),
    ("r", None),                                                   # flags unknown: refused
    # bsd-216 bug-230 r1 #m2: flags that modify a file opened O_RDONLY — O_CREAT creates an
    # absent spec, O_TRUNC can empty it (BSD-derived kernels truncate) — each pinned alone.
    (None, os.O_RDONLY | os.O_CREAT),
    (None, os.O_RDONLY | os.O_TRUNC),
    (None, os.O_RDONLY | os.O_EXCL),
], ids=["w", "a", "r+", "os-rdwr", "os-wronly", "no-flags", "rdonly-creat", "rdonly-trunc",
        "rdonly-excl"])
def test_2a_guard_a_write_open_of_the_ignore_spec_is_still_a_violation(checkout, args):
    p = str(checkout["root"] / IGNORE_REL)
    assert rmx_sandbox.violation("open", (p, *args), checkout["deny"]) is not None, (
        f"a non-read open of the ignore spec must stay denied: {args}")


@pytest.mark.parametrize("event", ["os.remove", "os.rename", "os.chmod", "os.truncate",
                                   "os.utime", "shutil.copyfile"])
def test_2a_guard_any_other_touch_of_the_ignore_spec_is_still_a_violation(checkout, event):
    p = str(checkout["root"] / IGNORE_REL)
    args = (p, "/tmp/elsewhere") if event in ("os.rename", "shutil.copyfile") else (p,)
    assert rmx_sandbox.violation(event, args, checkout["deny"]) is not None, event


@pytest.mark.parametrize("name", ["catalog.A.duckdb", "catalog.read.duckdb", "rmxd.sock",
                                  ".refmatrix_ignore.bak", "facts.log"])
def test_2a_guard_a_read_of_any_other_file_under_the_store_is_still_a_violation(checkout,
                                                                                 name):
    p = str(checkout["root"] / ".refmatrix" / name)
    assert rmx_sandbox.violation("open", (p, "r", os.O_RDONLY), checkout["deny"]) is not None


def test_2a_guard_a_symlinked_spec_allows_no_read_of_its_target(checkout):
    """bsd-216 bug-230 r1 #m1: `_variants` adds the realpath, so a spec that is a symlink to
    `catalog.A.duckdb` put the CATALOG into `read_allow`. With the spec linked to the catalog,
    neither a direct read of the catalog nor a read through the link is allowed."""
    root = checkout["root"]
    spec, catalog = root / IGNORE_REL, root / ".refmatrix" / "catalog.A.duckdb"
    spec.unlink()
    spec.symlink_to(catalog)
    deny = dict(checkout["deny"], read_allow=rmx_sandbox.read_allow(root))
    for p in (catalog, spec):
        assert rmx_sandbox.violation("open", (str(p), "rb", os.O_RDONLY), deny) is not None, (
            f"a read of {p} is allowed with the spec symlinked to the catalog "
            f"(read_allow={deny['read_allow']})")


def test_2a_the_session_deny_set_allows_exactly_this_checkouts_ignore_spec():
    """`build_deny` writes the allow for the repo the sandbox was entered for — this checkout —
    and for nothing else, so every child reads the same rule from `deny.json`."""
    deny = rmx_sandbox._STATE["deny"]
    want = sorted(rmx_sandbox._variants(REPO / IGNORE_REL))
    assert sorted(deny.get("read_allow") or []) == want, (
        f"session read_allow {deny.get('read_allow')} != {want}")
    on_disk = json.loads((Path(os.environ["RMX_SANDBOX_ROOT"]) / rmx_sandbox.DENY_FILE)
                         .read_text())
    assert sorted(on_disk.get("read_allow") or []) == want, "deny.json lacks the allow"


def test_2a_the_dev_tree_shape_runs_the_scope_parity_step_under_the_sandbox(gate_roots):
    """The bug-230 repro: lint-gmd.sh on a checkout that HAS `.refmatrix/.refmatrix_ignore`,
    under a deny set naming that checkout's store (its own sandbox root). The parity step reads
    the spec; the gate must run to exit 0. Pre-fix the child is killed with exit 86."""
    root = _gate_root(lint_src=None, doc=PLANTED_FIXED)
    gate_roots.append(root)
    (root / ".refmatrix").mkdir()
    (root / IGNORE_REL).write_text(R4_SPEC)
    sb = Path(rmx_sandbox.short_root("b230s")).resolve()
    gate_roots.append(sb)
    session = rmx_sandbox._STATE["deny"]
    deny = dict(session,
                paths=sorted(set(session["paths"]) | rmx_sandbox._variants(root / ".refmatrix")),
                read_allow=sorted(rmx_sandbox._variants(root / IGNORE_REL)),
                touches=str(sb / "touches.log"))
    (sb / rmx_sandbox.DENY_FILE).write_text(json.dumps(deny, indent=1))
    env = dict(os.environ, RMX_SANDBOX_ROOT=str(sb))
    r = _run_gate(root, env)
    out = r.stdout + r.stderr
    touches = (sb / "touches.log").read_text() if (sb / "touches.log").exists() else ""
    assert r.returncode == 0, (
        f"lint-gmd.sh exited {r.returncode} on a checkout with .refmatrix/.refmatrix_ignore "
        f"under the sandbox:\n{out[-2000:]}\ntouches: {touches[-800:]}")
    assert touches == "", f"the gate touched the store beyond the allow: {touches}"
