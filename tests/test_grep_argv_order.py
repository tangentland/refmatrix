"""ch-bsd r1 #b-2 / r2 #b-1 #b-2: argument order for named paths, as a RULE.

grep processes argv left to right. For a directory argument under `-r` it walks
that directory in its OWN order, GROUPED by file. `rg`'s fan-out is completion
order — nondeterministic, measured at 0/40 argv-order holds with 4+ files — so
the renderer has to impose argument order without inventing one for a walk.

Two corrections are baked into these assertions, both from fixes that were
WORSE than the build they replaced:

  * **r2 #b-1 — rank only, stable.** The first cut sorted on `(rank, line)`
    and no-opped only on an EMPTY order. But `rmx grep -rn PAT .` names the
    directory, so the order held one entry, every walked file tied, and the
    tiebreak became the LINE NUMBER — a walk came back interleaved where grep
    and 0.76.0 both group. A stable sort on the rank alone keeps the tool's
    order within an argument and argument order across arguments.
  * **r2 #b-2 — no `Path.resolve()`.** Resolving looked like the obvious
    identity and was wrong three ways: a symlink and its target collapsed into
    one `-c` row with the SUMMED count, a directory seeded a fabricated `.:0`,
    and a missing argument seeded `nosuch.txt:0` where grep errors and exits 2.
    grep echoes a path exactly as given, so the SPELLING is the identity.

The end-to-end contract lives in `test_grep_argv_order_e2e.py` (6 files, real
exec, measured to fail the unfixed build 10/10) and in the real-grep
differentials in `test_grep_fixed_and_file_lists.py`. These are the rule.
"""
from __future__ import annotations

import os

from refmatrix.cli import (argv_count_rows, argv_order_index, argv_rank,
                           order_triples_by_argv)


def test_named_paths_get_argument_order_and_nothing_else(tmp_path, monkeypatch):
    """Rank only — NOT `(rank, line)`. The line tiebreak is what interleaved a
    walk (r2 #b-1)."""
    for n in ("a.txt", "b.txt"):
        (tmp_path / n).write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["a.txt", "b.txt"])

    triples = [("b.txt", 1, "x"), ("a.txt", 9, "y"), ("a.txt", 2, "z")]
    out = order_triples_by_argv(triples, argv)

    # a.txt's rows come first, and KEEP the tool's own order among themselves
    # (9 before 2) — the renderer must not re-sort lines it was handed.
    assert [(f, n) for f, n, _ in out] == [
        ("a.txt", 9), ("a.txt", 2), ("b.txt", 1)]


def test_a_walk_under_a_named_directory_keeps_the_tools_grouping(tmp_path,
                                                                 monkeypatch):
    """THE r2 #b-1 case at the rule level: a named directory fills the argv
    list, so the no-op-on-empty carve-out does not save us."""
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["."])

    # What rg hands back: grouped, in its own order.
    triples = [("./f2.txt", 1, "a"), ("./f2.txt", 3, "a"),
               ("./f0.txt", 1, "a"), ("./f0.txt", 3, "a")]
    out = order_triples_by_argv(triples, argv)

    assert [(f, n) for f, n, _ in out] == [
        ("./f2.txt", 1), ("./f2.txt", 3),
        ("./f0.txt", 1), ("./f0.txt", 3)], out


def test_a_named_file_outranks_a_directory_that_came_later(tmp_path,
                                                           monkeypatch):
    (tmp_path / "b.txt").write_text("alpha\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.txt").write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["b.txt", "sub"])

    out = order_triples_by_argv(
        [(os.path.join("sub", "deep.txt"), 1, "x"), ("b.txt", 1, "y")], argv)

    assert [f for f, _n, _t in out] == ["b.txt", os.path.join("sub", "deep.txt")]


def test_the_longest_matching_directory_wins(tmp_path, monkeypatch):
    """`rmx grep -rn PAT outer outer/inner` — a file under the deeper argument
    belongs to that argument, not to the one that merely contains it."""
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["outer", os.path.join("outer", "inner")])

    deep = os.path.join("outer", "inner", "f.txt")
    assert argv_rank(deep, argv) == 1
    assert argv_rank(os.path.join("outer", "other.txt"), argv) == 0


def test_a_file_not_named_in_argv_sorts_after_the_named_ones(tmp_path,
                                                             monkeypatch):
    (tmp_path / "a.txt").write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["a.txt"])

    out = order_triples_by_argv([("other.txt", 1, "x"), ("a.txt", 5, "y")],
                                argv)
    assert [f for f, _n, _t in out] == ["a.txt", "other.txt"]


def test_no_paths_is_a_no_op(tmp_path):
    """stdin, or a bare pattern: nothing was named, so there is no argument
    order to impose."""
    argv, _ = argv_order_index([])
    triples = [("z.txt", 9, "x"), ("a.txt", 1, "y")]
    assert order_triples_by_argv(triples, argv) == triples


def test_a_duplicated_path_keeps_its_first_position(tmp_path, monkeypatch):
    """`grep PAT a.txt b.txt a.txt` prints a.txt's matches at a.txt's FIRST
    slot."""
    for n in ("a.txt", "b.txt"):
        (tmp_path / n).write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["a.txt", "b.txt", "a.txt"])

    assert argv_rank("a.txt", argv) == 0


# ---- the `-c` row set: FILES only (r2 #b-2) -------------------------------

def test_count_rows_are_named_files_only(tmp_path, monkeypatch):
    """A directory gets no `.:0` and a missing argument gets no
    `nosuch.txt:0` — a count row claims rmx read a file."""
    (tmp_path / "a.txt").write_text("alpha\n")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["a.txt", "sub", "nosuch.txt"])

    assert argv_count_rows(argv) == ["a.txt"]


def test_count_rows_keep_argv_order_and_the_argv_spelling(tmp_path,
                                                          monkeypatch):
    """The SPELLING, not a resolved path: `./a.txt` stays `./a.txt`, which is
    what grep echoes — and resolving is what collapsed a symlink into its
    target."""
    (tmp_path / "a.txt").write_text("alpha\n")
    (tmp_path / "b.txt").write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["b.txt", "./a.txt"])

    assert argv_count_rows(argv) == ["b.txt", "./a.txt"]


def test_a_symlink_and_its_target_are_two_distinct_rows(tmp_path, monkeypatch):
    """r2 #b-2's wrong NUMBER, at the rule level."""
    (tmp_path / "a.txt").write_text("alpha\n")
    os.symlink(tmp_path / "a.txt", tmp_path / "alias.txt")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["alias.txt", "a.txt"])

    assert argv_count_rows(argv) == ["alias.txt", "a.txt"]
    assert argv_rank("alias.txt", argv) == 0
    assert argv_rank("a.txt", argv) == 1


def test_an_unresolvable_path_does_not_break_the_ordering(tmp_path,
                                                          monkeypatch):
    """The floor's whole job is to answer when the index cannot; a weird path
    must not raise through the renderer."""
    (tmp_path / "a.txt").write_text("alpha\n")
    monkeypatch.chdir(tmp_path)
    argv, _ = argv_order_index(["a.txt", "\0bad"])

    out = order_triples_by_argv([("a.txt", 1, "x")], argv)
    assert [f for f, _n, _t in out] == ["a.txt"]
    assert argv_count_rows(argv) == ["a.txt"]
