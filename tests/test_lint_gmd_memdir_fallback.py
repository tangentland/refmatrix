"""T0.1' (plan-29 task 29.4 stage 1): bug-155's residual -- the memory dir `scripts/lint-gmd.sh`
scans is chosen by ONE resolver, `scripts/gmd_memdir.py` `resolve_memdir(root, home)`.

WHY. bug-155's second cause (a clone has no memory dir under its own slug) shipped a fix on
2026-11-14 (`44d1a34`) as bash in the script plus a Python copy of it in the repo-scope test.
Both copies look at one directory per checkout, test only that it EXISTS, and follow the origin
one hop. Two cases slip through (task-t0-suite-trust-sweep `#t0-1-residual`):

1. a clone of a clone (live: 8 of the 33 littlebig clones, every review clone cut from an
   author's clone): the origin's slug has no memory dir either, the walk stops, and every
   memory-id ref dangles (1,235 `dangling-doc`,
   workflow/review-output/t0.1/base-ac1.5-case1-script-clone-of-clone.log);
2. an own-slug `memory/` that exists and is EMPTY (Claude Code creates one for any session whose
   cwd is the checkout): the `-d` test takes it, no fallback is tried, and every memory-id ref
   dangles with no line on stderr (1,235 `dangling-doc`, exit 1,
   workflow/review-output/t0.1/base-ac1.5-case2-shipped-script-empty-own-dir.log).

What is pinned here:
- AC-1.5 case 2, through the REAL script with a decoy HOME (the empty own-slug dir);
- AC-1.6, the resolver's cases on fixture checkouts (real `git` repos) and a tmp home: populated,
  empty, absent, origin canonicalisation, non-local, chained, cycle (under a wall deadline), the
  bound of 5, and the two other stops R1.4 names (no origin, not a checkout);
- AC-1.7, statically: the script calls the resolver and keeps no slug or origin logic of its own
  (a second, correct bash copy would pass AC-1.5 and AC-1.6 while the convergence had failed).

AC-1.5 case 2's node needs the resolver to build its decoy, so at T0.1's base it fails on the
missing module; its stated-reason RED is the logged shipped-script run above, and its own RED is
its run under mutation M1.6 after GREEN (ruling L123). Nothing here writes to the real home: the
real `~/.claude` is only read, through `RMX_SANDBOX_REAL_HOME`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_gmd_lint_requires_version import (
    GMD_MEMDIR,
    assert_gate_ran,
    assert_gate_ran_clean,
    dangling_summary,
    gate_note_lines,
    load_gmd_memdir,
    reason_text,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "lint-gmd.sh"

# AC-1.6's cycle case runs in a child under this deadline (R0.4): a broken cycle guard with the
# bound intact fails on the message; a broken guard AND a broken bound fails on the deadline,
# never hangs the suite (ch-bsd r2 M2).
CYCLE_DEADLINE_S = 30


# ---- fixtures: real git checkouts and a tmp home -------------------------------------------

def _slug(path: Path) -> str:
    """The test's OWN statement of the slug rule (`/` and `_` -> `-`), used only as the oracle
    for the resolver's unit cases. The decoy homes built for the real script use the module's
    `slug()` instead, so the script-level tests keep no third copy of the rule."""
    return str(path).replace("/", "-").replace("_", "-")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", "-c", "init.defaultBranch=main", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _checkout(path: Path, origin: "str | None" = None) -> Path:
    """A real git checkout at `path` (canonical), with `origin` set verbatim when given."""
    path.mkdir(parents=True)
    _git("init", "-q", cwd=path)
    if origin is not None:
        _git("remote", "add", "origin", origin, cwd=path)
    return path.resolve()


def _memdir(home: Path, checkout: Path) -> Path:
    return home / ".claude" / "projects" / _slug(checkout) / "memory"


def _populate(home: Path, checkout: Path) -> Path:
    d = _memdir(home, checkout)
    d.mkdir(parents=True)
    (d / "feedback_fixture.md").write_text("---\ngmd: \"0.1\"\nid: feedback_fixture\n---\n")
    return d


def _empty(home: Path, checkout: Path) -> Path:
    d = _memdir(home, checkout)
    d.mkdir(parents=True)
    (d / "not-a-memory.txt").write_text("a non-.md file does not make the dir populated\n")
    return d


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = (tmp_path / "home").resolve()
    (h / ".claude" / "projects").mkdir(parents=True)
    return h


def _resolve(gm, root: Path, home: Path):
    chosen, note = gm.resolve_memdir(root, home)
    return (Path(chosen).resolve() if chosen is not None else None), (note or "")


def _one_line(note: str) -> None:
    assert note and "\n" not in note.strip(), f"the fallback note is not one line: {note!r}"


def _segment(note: str, start: str, end: "str | None") -> str:
    """The part of the note from `start` up to `end` (the next checkout named), so a reason word
    is checked against the checkout it belongs to."""
    assert start in note, f"the note does not name {start}: {note!r}"
    i = note.index(start)
    if end is None:
        return note[i:]
    assert end in note[i + len(start):], f"the note does not name {end} after {start}: {note!r}"
    return note[i:note.index(end, i + len(start))]


# ---- AC-1.6: the resolver's cases -----------------------------------------------------------

def test_a_populated_own_dir_is_chosen_with_no_fallback_line(tmp_path, home):
    gm = load_gmd_memdir()
    root = _checkout(tmp_path / "chk_own", origin=str(tmp_path / "unused"))
    own = _populate(home, root)
    chosen, note = _resolve(gm, root, home)
    assert chosen == own.resolve(), (chosen, note)
    assert not note, f"the own dir was used, so there is no fallback line: {note!r}"


def test_an_empty_own_dir_falls_back_to_the_origin_and_says_empty(tmp_path, home):
    gm = load_gmd_memdir()
    origin = _checkout(tmp_path / "origin_main")
    used = _populate(home, origin)
    root = _checkout(tmp_path / "chk_empty", origin=str(origin))
    _empty(home, root)
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (
        f"an own-slug memory/ holding no *.md is not a memory dir; the origin's must be used: "
        f"chosen={chosen} note={note!r}")
    _one_line(note)
    assert "empty" in reason_text(note), note
    assert str(origin) in note, note


def test_an_absent_own_dir_falls_back_to_the_origin_and_says_absent(tmp_path, home):
    gm = load_gmd_memdir()
    origin = _checkout(tmp_path / "origin_main")
    used = _populate(home, origin)
    root = _checkout(tmp_path / "chk_absent", origin=str(origin))
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (chosen, note)
    _one_line(note)
    assert "absent" in reason_text(note), note
    assert str(origin) in note, note


def test_origin_spellings_canonicalise_to_one_origin_and_slug(tmp_path, home):
    """Relative, trailing `/`, `<path>/.git`, a `.git` suffix and a symlinked path all name the
    same checkout: one canonical origin, one slug, one chosen dir (R1.4; mutation M1.7)."""
    gm = load_gmd_memdir()
    origin = _checkout(tmp_path / "origin_main")
    used = _populate(home, origin).resolve()
    link = tmp_path / "origin_link"
    link.symlink_to(origin, target_is_directory=True)
    spellings = {
        "relative": "../origin_main",
        "trailing-slash": str(origin) + "/",
        "dot-git-component": str(origin) + "/.git",
        "dot-git-suffix": str(origin) + ".git",
        "symlink": str(link),
    }
    got = {}
    for name, url in spellings.items():
        root = _checkout(tmp_path / f"chk_{name.replace('-', '_')}", origin=url)
        got[name] = _resolve(gm, root, home)
    wrong = {k: v for k, v in got.items() if v[0] != used}
    assert not wrong, f"each spelling must resolve to {used}; these did not: {wrong!r}"
    for name, (_c, note) in got.items():
        assert str(origin) in note, f"{name}: the line names the canonical origin {origin}: {note!r}"


@pytest.mark.parametrize("kind", ["scp", "https", "file"])
def test_a_non_local_origin_stops_the_walk_with_no_dir(tmp_path, home, kind):
    """`git@host:repo`, `https://…` and `file://…` are non-local: no fallback, the "no memory dir"
    line, which says memory-id refs will surface as `dangling-doc`. The `file://` URL names a
    checkout whose dir IS populated, so only the non-local rule can refuse it."""
    gm = load_gmd_memdir()
    target = _checkout(tmp_path / "origin_main")
    _populate(home, target)
    url = {"scp": "git@example.invalid:owner/repo.git",
           "https": "https://example.invalid/owner/repo.git",
           "file": f"file://{target}"}[kind]
    root = _checkout(tmp_path / f"chk_{kind}", origin=url)
    chosen, note = _resolve(gm, root, home)
    assert chosen is None, f"a {kind} origin is non-local; no dir may be chosen: {chosen} {note!r}"
    _one_line(note)
    for word in ("non-local origin", "no memory dir", "dangling-doc"):
        assert word in reason_text(note), f"{word!r} missing from the no-dir line: {note!r}"


def test_a_chain_of_clones_is_walked_to_the_first_populated_dir(tmp_path, home):
    """checkout -> clone A -> clone B, only B populated: B's dir, and the line names A as `absent`
    and then B (ch-bsd r1 S1; mutation M1.9 follows one hop and stops at A)."""
    gm = load_gmd_memdir()
    clone_b = _checkout(tmp_path / "clone_b")
    used = _populate(home, clone_b)
    clone_a = _checkout(tmp_path / "clone_a", origin=str(clone_b))
    root = _checkout(tmp_path / "chk_chain", origin=str(clone_a))
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (
        f"the walk must follow local origins hop by hop to clone B: chosen={chosen} "
        f"note={note!r}")
    _one_line(note)
    assert "absent" in reason_text(_segment(note, str(clone_a), str(clone_b))), note
    assert str(clone_b) in note, note


def test_a_chain_names_an_empty_intermediate_dir_as_empty(tmp_path, home):
    gm = load_gmd_memdir()
    clone_b = _checkout(tmp_path / "clone_b")
    used = _populate(home, clone_b)
    clone_a = _checkout(tmp_path / "clone_a", origin=str(clone_b))
    _empty(home, clone_a)
    root = _checkout(tmp_path / "chk_chain", origin=str(clone_a))
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (chosen, note)
    _one_line(note)
    assert "empty" in reason_text(_segment(note, str(clone_a), str(clone_b))), note


def test_a_chain_resolves_under_an_exported_git_dir_of_an_unrelated_repo(tmp_path, home,
                                                                         monkeypatch):
    """ch-bsd T0.1' r1 MEH-1 (L126): the gate can run from inside a git hook, where git exports
    `GIT_DIR` / `GIT_WORK_TREE` for the repo being committed (the bug-212 E1 class). Every
    `git -C <checkout>` the walk makes must still read THAT checkout, not the exported repo:
    the resolver strips git's locating variables. Here they name an unrelated repo whose origin
    is non-local, so a resolver that keeps them reads that origin for every hop and stops on
    `non-local origin` with no dir (mutation M1.12, "drop the scrub")."""
    gm = load_gmd_memdir()
    clone_b = _checkout(tmp_path / "clone_b")
    used = _populate(home, clone_b)
    clone_a = _checkout(tmp_path / "clone_a", origin=str(clone_b))
    root = _checkout(tmp_path / "chk_chain", origin=str(clone_a))
    unrelated = _checkout(tmp_path / "unrelated_repo",
                          origin="git@example.invalid:owner/unrelated.git")
    monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (
        f"with GIT_DIR/GIT_WORK_TREE exported for {unrelated}, the chain {root} -> {clone_a} -> "
        f"{clone_b} must still resolve to clone B's dir: chosen={chosen} note={note!r}")
    _one_line(note)
    assert "absent" in reason_text(_segment(note, str(clone_a), str(clone_b))), note
    assert str(unrelated) not in note, f"the walk read the exported repo: {note!r}"


_CYCLE_CHILD = r'''
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("gmd_memdir", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
chosen, note = mod.resolve_memdir(Path(sys.argv[2]), Path(sys.argv[3]))
print(json.dumps({"chosen": None if chosen is None else str(chosen), "note": note or ""}))
'''


def test_a_cycle_of_origins_returns_no_dir_and_says_cycle(tmp_path, home):
    """clone A's origin is clone B and B's is A; no slug populated. The resolver returns, with no
    dir, and the line says `cycle`. Run in a child under a wall deadline with the bound intact:
    mutation M1.10 (no visited-path guard) ends on `bound of 5` and fails on the message; a
    broken guard plus a broken bound fails on the deadline, never hangs (R0.4)."""
    gm = load_gmd_memdir()
    clone_a = _checkout(tmp_path / "clone_a", origin=str((tmp_path / "clone_b").resolve()))
    clone_b = _checkout(tmp_path / "clone_b", origin=str(clone_a))
    root = _checkout(tmp_path / "chk_cycle", origin=str(clone_a))
    try:
        r = subprocess.run([sys.executable, "-c", _CYCLE_CHILD, str(GMD_MEMDIR), str(root),
                            str(home)], capture_output=True, text=True,
                           timeout=CYCLE_DEADLINE_S)
    except subprocess.TimeoutExpired:
        pytest.fail(f"resolve_memdir did not return within {CYCLE_DEADLINE_S}s on a two-clone "
                    "origin cycle: neither the cycle guard nor the bound stopped the walk")
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["chosen"] is None, got
    _one_line(got["note"])
    assert "cycle" in reason_text(got["note"]), (
        f"the walk must stop on the visited-path guard and say `cycle`: {got['note']!r}")
    assert str(clone_b) in got["note"] and str(clone_a) in got["note"], got["note"]


def _chain(tmp_path: Path, n: int) -> list:
    """o1 <- o2 <- ... : returns [o1, …, on] where o_k's origin is o_{k+1}; on has no origin."""
    paths = [tmp_path / f"hop_{k}" for k in range(1, n + 1)]
    out = [None] * n
    for k in range(n - 1, -1, -1):
        nxt = str(paths[k + 1].resolve()) if k + 1 < n else None
        out[k] = _checkout(paths[k], origin=nxt)
    return out


def test_the_walk_stops_at_the_bound_of_five_origins(tmp_path, home):
    """A chain of 6 local origins where only the sixth is populated: no dir, `bound of 5`
    (mutation M1.11 drops or raises the bound, and the sixth is chosen)."""
    gm = load_gmd_memdir()
    hops = _chain(tmp_path, 6)
    _populate(home, hops[5])
    root = _checkout(tmp_path / "chk_bound", origin=str(hops[0]))
    chosen, note = _resolve(gm, root, home)
    assert chosen is None, (
        f"the sixth origin is past the bound of 5; nothing may be chosen: {chosen} {note!r}")
    _one_line(note)
    assert "bound of 5" in reason_text(note), note


def test_the_fifth_origin_is_inside_the_bound(tmp_path, home):
    gm = load_gmd_memdir()
    hops = _chain(tmp_path, 6)
    used = _populate(home, hops[4])
    root = _checkout(tmp_path / "chk_bound", origin=str(hops[0]))
    chosen, note = _resolve(gm, root, home)
    assert chosen == used.resolve(), (
        f"the fifth origin is inside the bound of 5 and must be chosen: {chosen} {note!r}")
    _one_line(note)


def test_a_checkout_with_no_origin_stops_with_no_dir(tmp_path, home):
    gm = load_gmd_memdir()
    root = _checkout(tmp_path / "chk_no_origin")
    chosen, note = _resolve(gm, root, home)
    assert chosen is None, (chosen, note)
    _one_line(note)
    assert "no origin" in reason_text(note) and "dangling-doc" in reason_text(note), note


def test_an_origin_that_is_not_a_checkout_stops_with_no_dir(tmp_path, home):
    gm = load_gmd_memdir()
    plain = tmp_path / "plain_dir"
    plain.mkdir()
    root = _checkout(tmp_path / "chk_plain", origin=str(plain.resolve()))
    chosen, note = _resolve(gm, root, home)
    assert chosen is None, (chosen, note)
    _one_line(note)
    assert "not a checkout" in reason_text(note) and "dangling-doc" in reason_text(note), note


# ---- AC-1.5 case 2: the empty own-slug dir, through the real script ------------------------

def test_an_empty_own_slug_memory_dir_falls_back_through_the_real_script(tmp_path):
    """The decoy home gets an EMPTY `memory/` under this checkout's own slug, plus a copy of the
    populated dir the resolver names for this checkout (read through `RMX_SANDBOX_REAL_HOME`, as
    the repo-scope test reads it) under that checkout's slug. Then the real
    `./scripts/lint-gmd.sh` runs with that HOME.

    - In a clone (the resolver's dir for it is an origin's): the script must print ONE memory-dir
      line saying `empty`, and its errors and exit must equal the main tree's at this sha, which
      is a clean gate (exit 0) when the main tree's gate is green.
    - In a checkout with no usable origin (the main tree: origin is not a local path): the line
      says `empty`, the walk stops on the non-local origin with the "no memory dir" line, and the
      gate exits 1 on `dangling-doc`. It does not skip (R0.5).

    At T0.1's base the shipped script's `-d` test took the empty dir, printed no line, and exited
    1 on 1,235 memory-id `dangling-doc` errors (base-ac1.5-case2-shipped-script-empty-own-dir.log).
    Mutation M1.6 (any existing own dir counts) must reproduce exactly that here."""
    root = REPO
    gm = load_gmd_memdir()
    real_home = Path(os.environ["RMX_SANDBOX_REAL_HOME"])
    own = gm.slug(root)
    chosen, _note = gm.resolve_memdir(root, real_home)
    chosen = Path(chosen) if chosen is not None else None
    home = tmp_path / "home"
    projects = home / ".claude" / "projects"
    (projects / own / "memory").mkdir(parents=True)          # exists, holds nothing
    main_tree_layout = chosen is not None and chosen.parent.name == own
    if chosen is not None and not main_tree_layout:
        shutil.copytree(chosen, projects / chosen.parent.name / "memory")
    env = dict(os.environ, HOME=str(home))
    assert Path(env["HOME"]).resolve() != real_home.resolve()
    r = subprocess.run(["./scripts/lint-gmd.sh"], cwd=str(root), capture_output=True,
                       text=True, env=env)
    assert_gate_ran(r)
    lines = gate_note_lines(r, root, own)
    assert len(lines) == 1, (
        "an EMPTY own-slug memory/ is not a memory dir: the script must take the fallback and "
        f"say so on one stderr line; memory-dir lines found: {lines!r}\n" + dangling_summary(r))
    line = lines[0]
    assert "empty" in reason_text(line), (
        f"the line must give the own dir's reason, `empty`: {line!r}")
    if main_tree_layout:
        for word in ("non-local origin", "no memory dir", "dangling-doc"):
            assert word in reason_text(line), f"{word!r} missing from the no-dir line: {line!r}"
        dangling = [l for l in (r.stdout + r.stderr).splitlines()
                    if "error: [dangling-doc]" in l]
        assert r.returncode == 1 and dangling, (
            "with no memory dir the memory-id refs must surface as dangling-doc, exit 1: "
            + dangling_summary(r))
        return
    if chosen is not None:
        named = [t for t in re.findall(r"/[^\s;,()'\"]+", line)
                 if gm.slug(Path(t.rstrip(".,;:)"))) == chosen.parent.name
                 or Path(t.rstrip(".,;:)")).parent.name == chosen.parent.name]
        assert named, (f"the line does not name the checkout whose dir was used "
                       f"(slug {chosen.parent.name}): {line!r}")
    assert_gate_ran_clean(r)


# ---- AC-1.7: one copy (static) ---------------------------------------------------------------

def _code_lines() -> list:
    """`scripts/lint-gmd.sh` without its full-line comments: the history the comments tell
    (bug-155's `tr '/_'`, `remote.origin.url`) is not code."""
    return [l for l in SCRIPT.read_text().splitlines() if not l.lstrip().startswith("#")]


def test_the_script_calls_the_resolver_under_python3():
    """R1.4 / ch-bsd r1 M1: the script runs `scripts/gmd_memdir.py` under `python3`, as it runs
    the linter, never under `$DEVPY` (the resolver must not inherit bug-253). The path may be
    named inline or through a variable (`X=".../gmd_memdir.py"`, then `python3 "$X"`)."""
    code = _code_lines()
    names = {m.group(1) for l in code
             for m in [re.match(r"\s*(?:local\s+|readonly\s+)?(\w+)=.*gmd_memdir\.py", l)] if m}
    refs = ["gmd_memdir.py"] + [f"${n}" for n in names] + [f"${{{n}}}" for n in names]
    calls = [l for l in code if any(r in l for r in refs)
             and not re.match(r"\s*(?:local\s+|readonly\s+)?\w+=[\"']?[^\s\"']*"
                              r"gmd_memdir\.py[\"']?\s*$", l)]
    assert calls, ("scripts/lint-gmd.sh does not invoke scripts/gmd_memdir.py: the memory dir is "
                   "still chosen by the script's own bash (T0.1' R1.4, AC-1.7)")
    assert [l for l in calls if re.search(r"\bpython3\b", l)], (
        f"the resolver must run under python3: {calls!r}")
    assert not [l for l in calls if "DEVPY" in l], (
        f"the resolver must never run under $DEVPY (bug-253): {calls!r}")


def test_the_script_holds_no_slug_derivation():
    """AC-1.7 (ch-bsd r1 M2; mutation M1.8): no `tr '/_'`, no other rewrite of a path into a
    slug, and no `~/.claude/projects/<slug>` path built in bash."""
    code = "\n".join(_code_lines())
    found = []
    for pat, what in [
        (r"\btr\s+(-\w+\s+)?['\"]?[^'\"\s]*[/_]", "a `tr` over `/` or `_`"),
        (r"\$\{[^}]*//[^}]*\}", "a `${var//pat/rep}` rewrite"),
        (r"\bsed\b[^\n]*['\"]?[sy]([^\w\s])\\?/", "a `sed` rewrite of `/`"),
        (r"\.claude/projects", "a `.claude/projects/<slug>` path built in bash"),
    ]:
        for m in re.finditer(pat, code):
            found.append(f"{what}: {code[max(0, m.start() - 20):m.end() + 20]!r}")
    assert not found, ("scripts/lint-gmd.sh still derives a slug itself; the resolver is the "
                       "one copy (T0.1' R1.4, AC-1.7):\n" + "\n".join(found))


def test_the_script_reads_no_origin():
    """AC-1.7: no `remote.origin.url`, no `remote get-url`: the origin walk is the resolver's."""
    code = "\n".join(_code_lines())
    found = [w for w in ("remote.origin.url", "remote get-url", "config --get remote")
             if w in code]
    assert not found, ("scripts/lint-gmd.sh still reads the origin itself; the resolver is the "
                       f"one copy (T0.1' R1.4, AC-1.7): {found!r}")
