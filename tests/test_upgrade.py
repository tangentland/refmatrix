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


# ---- plan-1 task 1.1/1.2: runtime identity (which tree does this interpreter run?) ----

def _fake_tree(base: Path, name: str) -> Path:
    """A refmatrix-shaped tree: <base>/<name>/{pyproject.toml,src/refmatrix/__init__.py}."""
    root = base / name
    (root / "src" / "refmatrix").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "refmatrix"\nversion = "0.0.0"\n')
    (root / "src" / "refmatrix" / "__init__.py").write_text('__version__ = "0.0.0"\n')
    return root


def _fake_venv(root: Path, editable_target: Path | None) -> Path:
    """<root>/.venv with a site-packages carrying the path-style editable .pth."""
    sp = root / ".venv" / "lib" / "python3.14" / "site-packages"
    sp.mkdir(parents=True)
    if editable_target is not None:
        (sp / "__editable__.refmatrix-0.0.0.pth").write_text(str(editable_target) + "\n")
    return root / ".venv"


def test_runtime_identity_detects_foreign_editable_target(tmp_path):
    """2026-09-14: ~/refmatrix/.venv's .pth pointed at the DEV checkout, so the
    deploy binary, every daemon and the hub ran uncommitted code and nothing
    said so. The identity is derived from the interpreter prefix + the import
    path — no attribute of the running package can be trusted on its own."""
    deploy = _fake_tree(tmp_path, "deploy")
    dev = _fake_tree(tmp_path, "dev")
    prefix = _fake_venv(deploy, dev / "src")
    ident = up.runtime_identity(prefix=prefix, import_file=dev / "src" / "refmatrix" / "__init__.py")
    assert ident["dev_tree"] is True
    assert ident["code_root"] == dev
    assert ident["venv_tree"] == deploy
    assert ident["editable_target"] == dev / "src"


def test_runtime_identity_clean_when_venv_imports_its_own_tree(tmp_path):
    deploy = _fake_tree(tmp_path, "deploy")
    prefix = _fake_venv(deploy, deploy / "src")
    ident = up.runtime_identity(prefix=prefix, import_file=deploy / "src" / "refmatrix" / "__init__.py")
    assert ident["dev_tree"] is False
    assert ident["code_root"] == deploy == ident["venv_tree"]


def test_runtime_identity_unknown_when_prefix_has_no_tree(tmp_path):
    """A system interpreter (no pyproject above sys.prefix) cannot be a dev-tree
    mismatch; report None rather than a false alarm."""
    dev = _fake_tree(tmp_path, "dev")
    prefix = tmp_path / "sys" / "python"; prefix.mkdir(parents=True)
    ident = up.runtime_identity(prefix=prefix, import_file=dev / "src" / "refmatrix" / "__init__.py")
    assert ident["venv_tree"] is None and ident["dev_tree"] is False


def test_verify_editable_refuses_foreign_target(tmp_path):
    deploy = _fake_tree(tmp_path, "deploy")
    dev = _fake_tree(tmp_path, "dev")
    _fake_venv(deploy, dev / "src")
    with pytest.raises(up.UpgradeError, match="editable target"):
        up.verify_editable(deploy)


def test_verify_editable_accepts_own_tree(tmp_path):
    deploy = _fake_tree(tmp_path, "deploy")
    _fake_venv(deploy, deploy / "src")
    assert up.verify_editable(deploy) == deploy / "src"


def test_upgrade_from_dev_verifies_editable_after_install(tmp_path):
    """The install step is injectable; the VERIFY step is not — an install_fn
    that leaves the venv pointing at the dev tree must fail the upgrade."""
    deploy = tmp_path / "deploy"
    _init_repo(deploy, "0.1.0")
    (deploy / "src" / "refmatrix").mkdir(parents=True)
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(deploy), str(dev)], check=True)
    _git(dev, "config", "user.email", "t@t")
    _git(dev, "config", "user.name", "t")
    _bump(dev, "0.2.0")

    def bad_install(root, *, log=print):
        _fake_venv(root, dev / "src")          # the 2026-09-14 mistake

    with pytest.raises(up.UpgradeError, match="editable target"):
        up.upgrade(root=deploy, from_dev=dev, install_fn=bad_install, restart_fn=lambda r, log=print: True)

    def good_install(root, *, log=print):
        import shutil
        shutil.rmtree(root / ".venv", ignore_errors=True)
        _fake_venv(root, root / "src")

    # The refused run already fast-forwarded the tree (git before pip); a new
    # dev commit is needed for the next upgrade to have anything to install.
    _bump(dev, "0.3.0")
    res = up.upgrade(root=deploy, from_dev=dev, install_fn=good_install, restart_fn=lambda r, log=print: True)
    assert res.installed and res.new_version == "0.3.0"
