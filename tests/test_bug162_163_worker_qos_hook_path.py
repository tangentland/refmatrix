"""bug-162 / bug-163 — two field defects from cliquedb's 2026-11-08 report.

bug-162: the hub LaunchAgent ran at `ProcessType=Background`, and the shared
model workers it spawns inherit that QoS (efficiency cores, throttled CPU).
Measured on the same 10 x 2160-char pool with ms-marco-MiniLM-L-12-v2:
0.23 s at normal QoS, 2.7-3.5 s under `taskpolicy -b`, 3.6 s on the live
shared worker — so every scan-prompt rerank blew its 4.9 s budget.

bug-163: every generated Claude hook called a bare `rmx`, so a session whose
launcher ran `bash -l` without `~/bin` on PATH (Herdr, 2026-11-08) failed
EVERY rmx hook with `/bin/sh: rmx: command not found` (exit 127): the Stop
summary visibly, the rest behind `|| true`.
"""
from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path

from refmatrix import hooks, launchctl


def _fake_rmx(tmp_path: Path) -> str:
    p = tmp_path / "bin" / "rmx"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return str(p)


def test_hub_plist_does_not_run_its_model_workers_at_background_qos(tmp_path):
    plist = plistlib.loads(
        launchctl.render_hub_plist(rmx=_fake_rmx(tmp_path), allow_dev=True))
    # The hub's children serve interactive hook budgets; Background QoS made
    # the cross-encoder ~15x slower.
    assert plist.get("ProcessType") == "Standard"


def _all_commands(block: dict) -> list[str]:
    out = []
    for groups in block.get("hooks", {}).values():
        for g in groups:
            for h in g.get("hooks", []):
                if h.get("type") == "command":
                    out.append(h["command"])
    return out


def test_every_generated_rmx_hook_runs_without_rmx_on_the_callers_path(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".refmatrix").mkdir(parents=True)
    block = hooks._claude_hook_block(proj / ".refmatrix", project_root=proj)
    cmds = [c for c in _all_commands(block) if hooks.RMX_HOOK_MARKER in c]
    assert cmds, "generator produced no rmx hooks"

    home = tmp_path / "home"
    marker = tmp_path / "ran"
    fake = home / "bin" / "rmx"
    fake.parent.mkdir(parents=True)
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{marker}"\nexit 0\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    # The thin PATH a `bash -l` launcher handed the 2026-11-08 session.
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    failures = []
    for c in cmds:
        r = subprocess.run(["/bin/sh", "-c", c], env=env, input="{}",
                           capture_output=True, text=True, timeout=30, cwd=proj)
        if "command not found" in r.stderr or r.returncode == 127:
            failures.append((c, r.returncode, r.stderr.strip()))
    assert not failures, failures
    assert marker.exists() and marker.read_text().strip(), "no hook reached rmx"
