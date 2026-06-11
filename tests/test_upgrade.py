"""`rmx upgrade` core logic — git fast-forward (self-update + --from-dev promote),
--check dry-run, version reporting, and ff-only safety. Side effects (pip,
daemon) are injected as no-ops so the tests exercise only the git/version flow.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from refmatrix import upgrade as up


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _init_repo(root: Path, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "master"], check=True)
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", f"v{version}")


def _bump(root: Path, version: str) -> None:
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", f"v{version}")


def _noop_install(root, *, log=print):
    pass


def test_read_version_and_package_root(tmp_path):
    assert up._read_version('foo\nversion = "1.2.3"\nbar') == "1.2.3"
    assert up._read_version("no version here") is None
    (tmp_path / "pyproject.toml").write_text('version = "9.9.9"\n')
    sub = tmp_path / "src" / "refmatrix"
    sub.mkdir(parents=True)
    assert up.package_root(sub / "__init__.py") == tmp_path


def test_from_dev_promote_fast_forwards_and_installs(tmp_path):
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    # dev = clone of deploy, one version ahead (ff-able).
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _git(dev, "config", "user.email", "t@t")
    _git(dev, "config", "user.name", "t")
    _bump(dev, "0.2.0")

    calls = {"installed": False, "restarted": False}
    def inst(root, *, log=print): calls["installed"] = True
    def rest(root, *, log=print): calls["restarted"] = True; return True

    res = up.upgrade(root=deploy, from_dev=dev, install_fn=inst, restart_fn=rest)
    assert res.changed
    assert res.old_version == "0.1.0" and res.new_version == "0.2.0"
    assert calls == {"installed": True, "restarted": True}
    assert up._read_version((deploy / "pyproject.toml").read_text()) == "0.2.0"
    assert res.source.startswith("dev:")


def test_check_is_readonly(tmp_path):
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _git(dev, "config", "user.email", "t@t")
    _git(dev, "config", "user.name", "t")
    _bump(dev, "0.3.0")
    head_before = _git(deploy, "rev-parse", "HEAD")

    installed = {"n": 0}
    res = up.upgrade(root=deploy, from_dev=dev, check=True,
                     install_fn=lambda *a, **k: installed.__setitem__("n", 1))
    assert res.checked and res.changed
    assert res.old_version == "0.1.0" and res.new_version == "0.3.0"
    # nothing mutated: HEAD unmoved, working pyproject unchanged, no install.
    assert _git(deploy, "rev-parse", "HEAD") == head_before
    assert up._read_version((deploy / "pyproject.toml").read_text()) == "0.1.0"
    assert installed["n"] == 0


def test_already_up_to_date_is_noop(tmp_path):
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)

    res = up.upgrade(root=deploy, from_dev=dev, install_fn=_noop_install,
                     restart=False)
    assert not res.changed
    assert not res.installed


def test_non_fast_forward_refuses(tmp_path):
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _git(dev, "config", "user.email", "t@t")
    _git(dev, "config", "user.name", "t")
    _bump(dev, "0.2.0")
    # deploy makes its OWN divergent commit -> not a fast-forward.
    _git(deploy, "config", "user.email", "t@t")
    _git(deploy, "config", "user.name", "t")
    _bump(deploy, "0.1.1")

    with pytest.raises(up.UpgradeError):
        up.upgrade(root=deploy, from_dev=dev, install_fn=_noop_install,
                   restart=False)
