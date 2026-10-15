"""Task 23.0 R3 and AC-2: a touch of a live path is REFUSED in-process, not recorded.

The record-only `_recording_connect` (conftest, 2026-10-07) named bug-088's offenders and let
every one of them through. R3 replaces it with a `sys.addaudithook` hook over one deny set
built from the REAL paths captured before the redirect: the real `~/.refmatrix/`, this repo's
`.refmatrix/`, every registered store root, and TCP 7777 on 127.0.0.1 / localhost / ::1.

The probes run in a `pytester` inner session in THIS process, so the audit hook the outer
conftest installed (process-global, irremovable) is the thing under test. Each outer test calls
`_require_sandbox()` before writing a single inner probe: at a HEAD without the sandbox it fails
there, and nothing live is opened or connected.

Mutation (AC-2, pre-registered): put back the record-only connect -> the inner probes connect /
open for real and PASS, so `assert_outcomes(failed=...)` fails here. That mutation run touches
the live paths by design; run it only with the hub and global daemon in a state you accept.
"""
from __future__ import annotations

import os
import plistlib
import pwd
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_REPO = Path(__file__).resolve().parents[1]
_TOUCHES = _REPO / "workflow" / "review-output" / "live-socket-touches.log"


def _real_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _require_sandbox() -> Path:
    root = os.environ.get("RMX_SANDBOX_ROOT")
    assert root, (
        "R1: RMX_SANDBOX_ROOT is unset -- no sandbox, no refusal hook; refusing to run an "
        "inner probe that would touch the live machine")
    assert Path(root).is_dir(), root
    return Path(root)


def _touches_size() -> int:
    return _TOUCHES.stat().st_size if _TOUCHES.exists() else 0


def _new_touches(since: int) -> list[str]:
    if not _TOUCHES.exists():
        return []
    with open(_TOUCHES, "rb") as fh:
        fh.seek(since)
        return fh.read().decode(errors="replace").splitlines()


def _run_inner(pytester, body: str):
    pytester.makepyfile(test_inner=body)
    return pytester.runpytest("-p", "no:cacheprovider", "-rf")


def _assert_refused(result, touches: list[str], expect: dict[str, str]) -> None:
    """Every inner test in `expect` FAILED with SandboxViolation and the touches log names
    it together with its target marker."""
    out = result.stdout.str() + result.stderr.str()
    result.assert_outcomes(failed=len(expect))
    failed_lines = [ln for ln in result.outlines if ln.startswith("FAILED")]
    for name, target in expect.items():
        mine = [ln for ln in failed_lines if f"::{name}" in ln]
        assert mine, f"{name} did not fail:\n{out[-3000:]}"
        assert "SandboxViolation" in mine[0], f"{name} failed for another reason: {mine[0]}"
        logged = [t for t in touches if name in t and target in t]
        assert logged, f"touches log has no line naming {name} + {target}: {touches[-20:]}"


# ---- AC-2: the three named probes ------------------------------------------------------


def test_inner_probes_on_live_paths_fail_with_sandbox_violation(pytester):
    """AC-2: connect to the real `~/.refmatrix/rmxd.sock`, open the real
    `~/.refmatrix/query.log` for append, connect to `::1:7777` -- each FAILS with
    SandboxViolation and the touches log names it."""
    _require_sandbox()
    real = str(_real_home())
    before = _touches_size()
    result = _run_inner(pytester, f'''
import os, socket
REAL = {real!r}

def test_connect_real_global_daemon_socket():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(os.path.join(REAL, ".refmatrix", "rmxd.sock"))
    finally:
        s.close()

def test_append_real_global_query_log():
    with open(os.path.join(REAL, ".refmatrix", "query.log"), "a"):
        pass

def test_connect_ipv6_hub_port():
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("::1", 7777))
    finally:
        s.close()
''')
    _assert_refused(result, _new_touches(before), {
        "test_connect_real_global_daemon_socket": "rmxd.sock",
        "test_append_real_global_query_log": "query.log",
        "test_connect_ipv6_hub_port": "7777",
    })


# ---- R3: the rest of the deny set --------------------------------------------------------


def test_inner_probes_on_the_rest_of_the_deny_set_fail(pytester):
    """R3: a READ of the real `facts.log`, any path under this repo's own `.refmatrix/`
    (whether or not it exists), a connect to 127.0.0.1:7777 and localhost:7777, and an
    `os.*` mutation inside the real `~/.refmatrix/` are all refused."""
    _require_sandbox()
    real = str(_real_home())
    repo_store = str(_REPO / ".refmatrix")
    before = _touches_size()
    result = _run_inner(pytester, f'''
import os, socket, uuid
REAL = {real!r}
REPO_STORE = {repo_store!r}

def _tcp(host):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((host, 7777))
    finally:
        s.close()

def test_read_real_global_facts_log():
    with open(os.path.join(REAL, ".refmatrix", "facts.log"), "r"):
        pass

def test_read_repo_store_query_log():
    with open(os.path.join(REPO_STORE, "query.log"), "r"):
        pass

def test_connect_loopback_hub_port():
    _tcp("127.0.0.1")

def test_connect_localhost_hub_port():
    _tcp("localhost")

def test_rename_inside_real_global_home():
    # Names that do not exist: without the hook this is a FileNotFoundError, never a
    # change to the live directory.
    a = os.path.join(REAL, ".refmatrix", "sbx-" + uuid.uuid4().hex)
    os.rename(a, a + "-b")
''')
    _assert_refused(result, _new_touches(before), {
        "test_read_real_global_facts_log": "facts.log",
        "test_read_repo_store_query_log": ".refmatrix",
        "test_connect_loopback_hub_port": "7777",
        "test_connect_localhost_hub_port": "7777",
        "test_rename_inside_real_global_home": ".refmatrix",
    })


def _registered_daemon_roots() -> list[Path]:
    """Roots from the REAL `com.refmatrix.daemon.*` plists (the LaunchAgents dir is not in
    the deny set; the roots it names are). bug-088's recorder omitted viascope's."""
    agents = _real_home() / "Library" / "LaunchAgents"
    out: list[Path] = []
    for plist in sorted(agents.glob("com.refmatrix.daemon.*.plist")):
        data = plistlib.loads(plist.read_bytes())
        r = (data.get("EnvironmentVariables") or {}).get("REFMATRIX_ROOT")
        if r:
            out.append(Path(r))
    return out


def test_inner_probes_on_registered_store_roots_fail(pytester):
    """R3: every root in the real registered daemon list is denied, including the stores the
    record-only guard never knew about. A host with no registered daemon (a tier-2 VM) has
    nothing to deny here; the repo-store and global-home probes above still run there."""
    _require_sandbox()
    roots = [r for r in _registered_daemon_roots()
             if r.resolve() != (_REPO / ".refmatrix").resolve()
             and r.resolve() != (_real_home() / ".refmatrix").resolve()]
    if not roots:
        # Nothing registered beyond the repo + global stores: no extra root to deny.
        return
    names = {}
    lines = ["import os"]
    for i, r in enumerate(roots):
        name = f"test_read_registered_root_{i}"
        names[name] = str(r)
        lines += [f"def {name}():",
                  f"    with open(os.path.join({str(r)!r}, 'query.log'), 'r'):",
                  "        pass", ""]
    before = _touches_size()
    result = _run_inner(pytester, "\n".join(lines))
    _assert_refused(result, _new_touches(before), names)


def test_record_only_connect_is_gone():
    """R3: 'The record-only `_recording_connect` is replaced by it.'"""
    src = (_REPO / "tests" / "conftest.py").read_text()
    assert "_recording_connect" not in src, "the record-only connect is still installed"
