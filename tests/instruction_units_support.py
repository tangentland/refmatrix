"""Shared harness for task I1.b1's tests (units, the compiler, the fixture runner, the parity
gate): `tests/test_instruction_units.py`, the parity cases of `tests/test_hooks_reproducible.py`
and `tests/test_repo_hooks_in_sync.py`.

Not a test module (no `test_` prefix). Everything enters through the dev `rmx` as a child
process (`tests/task21_1_support.py`'s `run_rmx`: the clone's `src` first on `PYTHONPATH`, the
sandbox `HOME`, `REFMATRIX_ROOT` = the per-test sandbox store), in the sandbox project that store
sits in (`<sandbox>/r/<n>/`, a short `mkdtemp()`-style root made by the conftest). Nothing here
patches `src/`; the only state built is real files on disk and real `git`.

The unit format these tests pin (task-I1.b1 #d1, ADR-0007 #units #binding #fixtures) is what
the files under `tests/fixtures/instruction_units/` hold: GMD frontmatter plus a `unit:` map
(`kind`, `bind` list, `priority`, `census`, `fixtures`, `from`, and for checks `on` / `run`);
the unit's text is the markdown body after the frontmatter, stripped, or the section a
`from: <skill id>#<anchor>` names. Local units live in the project's `.claude/` under the
directory of their kind: `triggers/` (deny, ask, inject), `checks/`, `rules/`,
`skills/<id>/SKILL.md`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from tests import task21_1_support as h

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
FIX = REPO / "tests" / "fixtures" / "instruction_units"
SAMPLE = FIX / "sample"
PLANTED = FIX / "planted"
PACKAGED_SAMPLE = FIX / "packaged"
TEMPLATES = SRC / "refmatrix" / "templates"
# The packaged layer (task-I1.b1 #d2): units ship under these template directories.
PACKAGED_DIRS = ("triggers", "checks", "rules", "skills", "practices")
COMPILED = Path(".claude") / "rmx-instructions.json"

# The sample units a sandbox project gets as its LOCAL layer. `sample-ask` is not among them:
# `ASK_VERIFIED` is off until probe P2's evidence is committed (task-I1.b0 #verdicts), so an
# `ask` unit is refused at compile (AC-2's `ask-unverified` case); its fixtures still run in
# AC-3. When P2 flips the constant, the commit that flips it adds `sample-ask` here.
LOCAL_SAMPLES = ("sample-deny", "sample-gate", "sample-context", "sample-check",
                 "sample-rule", "sample-skill")

# The install-hooks flags every sandbox apply uses: no user-level writes (agent-env, search
# scripts), no briefing; git hooks only where a test asks for them.
APPLY_ARGS = ("install-hooks", "--no-briefing", "--no-agent-env", "--no-search",
              "--apply", "--force")


def frontmatter(path: Path) -> "tuple[dict, str]":
    """(frontmatter dict, body) of a unit file, read the plain way (`---` fences, YAML)."""
    text = Path(path).read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head) or {}, body


def unit_files(base: Path) -> "list[Path]":
    """Every `.md` under `base` whose frontmatter carries a `unit:` map, sorted."""
    out = []
    for p in sorted(Path(base).rglob("*.md")):
        try:
            fm, _ = frontmatter(p)
        except AssertionError:
            continue
        if isinstance(fm.get("unit"), dict):
            out.append(p)
    return out


def sample_path(uid: str) -> Path:
    hits = [p for p in unit_files(SAMPLE) if frontmatter(p)[0].get("id") == uid]
    assert len(hits) == 1, f"sample unit {uid}: {hits}"
    return hits[0]


def local_target(proj: Path, sample: Path) -> Path:
    """Where a sample unit goes in a project's local layer: the same path under `.claude/`
    as under the sample directory (`triggers/x.md`, `skills/<id>/SKILL.md`, …)."""
    return Path(proj) / ".claude" / sample.relative_to(SAMPLE)


def install_local(proj: Path, ids=LOCAL_SAMPLES) -> "dict[str, Path]":
    """Copy the named sample units into the project's local layer; {id: installed path}."""
    out = {}
    for uid in ids:
        src = sample_path(uid)
        dst = local_target(proj, src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        out[uid] = dst
    return out


def sandbox() -> "tuple[Path, Path]":
    """(store root, project dir) of THIS test's sandbox store (the conftest's per-test
    `REFMATRIX_ROOT`, `<sandbox>/r/<n>/.refmatrix`)."""
    root = Path(os.environ["REFMATRIX_ROOT"])
    return root, root.parent


def rmx(root: Path, *args, timeout: float = 60, **extra) -> subprocess.CompletedProcess:
    """The dev `rmx` against the sandbox store, cwd = its project."""
    return h.run_rmx(list(args), root=root, cwd=root.parent, timeout=timeout, **extra)


def apply(root: Path, *, git: bool = False, **extra) -> subprocess.CompletedProcess:
    args = list(APPLY_ARGS)
    if not git:
        args.insert(1, "--no-git")
    return rmx(root, *args, **extra)


def check(root: Path, **extra) -> subprocess.CompletedProcess:
    return rmx(root, "install-hooks", "--check", **extra)


def out_of(r: subprocess.CompletedProcess) -> str:
    return (r.stdout or "") + (r.stderr or "")


def lines_with(text: str, *needles: str) -> "list[str]":
    """The output lines that carry every needle (a class word and a file name on ONE line)."""
    return [ln for ln in text.splitlines() if all(n in ln for n in needles)]


def compiled_bytes(proj: Path) -> "bytes | None":
    p = Path(proj) / COMPILED
    return p.read_bytes() if p.exists() else None


# ---- a refmatrix that ships a packaged rule -------------------------------------------------
#
# No unit ships in b1 (task-I1.b #c-no-units), yet AC-4's first case edits "a generated rule".
# A generated rule needs a template, so the tests build the real state: a copy of this
# checkout's `refmatrix` package whose `templates/rules/` holds one rule unit, put first on the
# child's PYTHONPATH. The child runs that copy (asserted below), the way a consumer runs a
# release that ships a rule. Nothing in `src/` is patched or redirected.

def build_overlay_site(dest: Path,
                       ships: "tuple[str, ...]" = ("rules/sample-packaged-rule.md",)) -> Path:
    """`dest/refmatrix`: a copy of this checkout's package whose `templates/` also ships each
    file of `ships` (paths under `tests/fixtures/instruction_units/packaged/`; default the one
    packaged rule). Returns `dest` (the PYTHONPATH entry)."""
    pkg = Path(dest) / "refmatrix"
    shutil.copytree(SRC / "refmatrix", pkg,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for rel in ships:
        target = pkg / "templates" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        init = target.parent / "__init__.py"
        if not init.exists():
            init.write_text("")
        shutil.copyfile(PACKAGED_SAMPLE / rel, target)
    pp = overlay_pythonpath(dest)
    r = subprocess.run([sys.executable, "-c", "import refmatrix; print(refmatrix.__file__)"],
                       env=h.clean_env(PYTHONPATH=pp), capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0 and r.stdout.strip().startswith(str(pkg)), (
        f"the overlay package is not what a child imports: {r.stdout!r} {r.stderr!r}")
    return Path(dest)


def overlay_pythonpath(site: Path) -> str:
    """The child PYTHONPATH with `site` in place of this checkout's `src`."""
    rest = [p for p in h.clean_env()["PYTHONPATH"].split(os.pathsep)
            if p and p != str(SRC)]
    return os.pathsep.join([str(site)] + rest)
