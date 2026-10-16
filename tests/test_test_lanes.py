"""Task 23.0 R7/R8: the script-level contracts of the tier-1 and tier-2 lanes.

Most of R7/R8 is operator work (creating `rmxtest`, sudoers, installing Tart, building the
`rmx-golden` image) and AC-7/AC-8 are lane runs on that setup; none of it can run inside the
suite. What CAN be pinned here is the scripts' own refusals:

- both lane scripts exist, are executable, and refuse to run without a `<sha>`;
- `scripts/test-lane-vm.sh` refuses a third macOS VM (Apple's licence: at most two at once)
  BEFORE it clones one. `tart` is replaced by a recording fake on PATH (external binary; see
  workflow/test_mock_registry.md) that reports two running VMs.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_USER_LANE = _REPO / "scripts" / "test-lane-user.sh"
_VM_LANE = _REPO / "scripts" / "test-lane-vm.sh"


def _head_sha() -> str:
    return subprocess.run(["git", "-C", str(_REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.parametrize("script", [_USER_LANE, _VM_LANE], ids=["user-lane", "vm-lane"])
def test_lane_script_exists_and_refuses_without_a_sha(script, tmp_path):
    """R7/R8: `scripts/test-lane-user.sh <sha>` / `scripts/test-lane-vm.sh <sha>`."""
    assert script.is_file(), f"{script} does not exist"
    assert os.access(script, os.X_OK), f"{script} is not executable"
    r = subprocess.run([str(script)], capture_output=True, text=True, cwd=str(tmp_path),
                       timeout=60)
    assert r.returncode != 0, f"{script.name} ran with no sha: {r.stdout[-1000:]!r}"
    assert "sha" in (r.stderr + r.stdout).lower(), r.stderr[-1000:]


def _fake_tart(bindir: Path, record: Path) -> None:
    """A `tart` that records argv and lists two RUNNING macOS VMs (table or --format json)."""
    vms = [{"Source": "local", "Name": "rmx-run-aaaaaaa", "Disk": 50, "Size": 20,
            "State": "running", "OS": "darwin"},
           {"Source": "local", "Name": "other-vm", "Disk": 50, "Size": 20,
            "State": "running", "OS": "darwin"},
           {"Source": "local", "Name": "rmx-golden", "Disk": 50, "Size": 20,
            "State": "stopped", "OS": "darwin"}]
    table = ("Source Name             Disk Size State\n"
             "local  rmx-run-aaaaaaa  50   20   running\n"
             "local  other-vm         50   20   running\n"
             "local  rmx-golden       50   20   stopped\n")
    script = bindir / "tart"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {str(record)!r}\n"
        "case \"$1\" in\n"
        "  list)\n"
        "    case \"$*\" in\n"
        f"      *json*) printf '%s\\n' {json.dumps(json.dumps(vms))} ;;\n"
        f"      *) printf {json.dumps(table)} ;;\n"
        "    esac ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def test_vm_lane_refuses_a_third_vm_before_cloning(tmp_path):
    """R8 Limits: 'the script refuses a third'. With two VMs running, no `tart clone` and no
    `tart run` is issued, and the refusal says why."""
    assert _VM_LANE.is_file(), f"{_VM_LANE} does not exist"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    record = tmp_path / "tart.argv"
    record.touch()
    _fake_tart(bindir, record)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    r = subprocess.run([str(_VM_LANE), _head_sha()], capture_output=True, text=True,
                       cwd=str(_REPO), env=env, timeout=120)
    calls = record.read_text().splitlines()
    assert r.returncode != 0, f"started a third VM: {r.stdout[-1000:]!r}"
    assert any(c.startswith("list") for c in calls), f"never asked tart what runs: {calls}"
    assert not any(c.startswith(("clone", "run")) for c in calls), calls
    msg = (r.stderr + r.stdout).lower()
    assert "two" in msg or "2" in msg, r.stderr[-1000:]
