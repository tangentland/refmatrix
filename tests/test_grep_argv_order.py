"""ch-bsd r1 #b-2: argument order for named paths, tested as a RULE.

grep's contract for NAMED paths is argument order. `rg`'s fan-out is completion
order, so `rmx grep`'s floor can emit a different order — the audit observed
`rmx grep -n alpha b.txt a.txt` putting a.txt first where grep puts b.txt on
the deployed build.

WHY THIS IS A UNIT TEST AND NOT AN END-TO-END ONE, stated so the next reader
does not mistake it for laziness. I could not reproduce the divergence on
demand: with a direct-exec grep control, two small files come back in argv
order every run, before any fix. Two attempts to force it failed and are worth
recording because both were the shape this ledger keeps catching —

  * a bash probe comparing against `/usr/bin/grep`, which the PreToolUse
    rewrite hook intercepts, so the "control" was `rmx` and the two sides
    agreed for the wrong reason (this file's sibling,
    `test_grep_fixed_and_file_lists.py`, already warns about exactly that);
  * a faked `subprocess.run` handing the renderer reversed output, which did
    not change the rendered order with OR without the fix — so it proved
    nothing, and a mutation deleting the whole sort left it green.

A gate that cannot fail is worse than no gate
(`feedback_clean_corpus_hides_a_dead_gate`), so those went in the bin and the
RULE is pinned here instead: `order_triples_by_argv` is module-level, and these
assertions fail the moment it stops ordering. The end-to-end contract stays
covered by the real-grep differentials in
`test_grep_fixed_and_file_lists.py`, where the `-c` half IS deterministically
reproducible and did fail before the fix.
"""
from __future__ import annotations

from pathlib import Path

from refmatrix.cli import argv_order_index, argv_rank, order_triples_by_argv


def test_named_paths_get_argument_order_then_line_number():
    order, _ = argv_order_index(["a.txt", "b.txt"])
    triples = [("b.txt", 1, "x"), ("a.txt", 2, "y"), ("a.txt", 1, "z")]

    assert [(f, n) for f, n, _ in order_triples_by_argv(triples, order)] == [
        ("a.txt", 1), ("a.txt", 2), ("b.txt", 1)]


def test_the_argv_spelling_is_the_display_form():
    """grep echoes a path exactly as given, so `./a.txt` stays `./a.txt` — the
    resolved absolute path is the KEY, never the thing printed."""
    order, display = argv_order_index(["./a.txt", "b.txt"])
    key = str(Path("./a.txt").resolve())

    assert display[key] == "./a.txt"
    assert order[key] == 0


def test_a_walk_keeps_the_tools_own_order():
    """Argument order applies to NAMED paths only. Re-sorting a directory walk
    would invent an order grep does not promise either — the opposite error,
    and the reason this is a no-op on an empty index."""
    triples = [("z.txt", 9, "x"), ("a.txt", 1, "y")]

    assert order_triples_by_argv(triples, {}) == triples


def test_a_file_not_named_in_argv_sorts_after_the_named_ones():
    order, _ = argv_order_index(["a.txt"])
    triples = [("other.txt", 1, "x"), ("a.txt", 5, "y")]

    assert [f for f, _n, _t in order_triples_by_argv(triples, order)] == [
        "a.txt", "other.txt"]


def test_rank_reads_a_prefixed_line_as_well_as_a_bare_path():
    """The `-l` branch ranks bare paths; the plain branch ranks `file:line:text`
    lines. ONE comparator serves both, which is the point of hoisting it — the
    finding was a rule applied in one of two places."""
    order, _ = argv_order_index(["a.txt", "b.txt"])

    assert argv_rank("a.txt", order) == 0
    assert argv_rank("a.txt:12:some text", order) == 0
    assert argv_rank("b.txt:1:x", order) == 1
    assert argv_rank("nope.txt:1:x", order) == len(order)


def test_a_duplicated_path_keeps_its_first_position():
    """`grep PAT a.txt b.txt a.txt` prints a.txt's matches at a.txt's FIRST
    position; `setdefault` is load-bearing, not incidental."""
    order, _ = argv_order_index(["a.txt", "b.txt", "a.txt"])

    assert order[str(Path("a.txt").resolve())] == 0


def test_an_unresolvable_path_does_not_break_the_ordering():
    """A path that cannot be resolved must not raise through the renderer: the
    floor's whole job is to answer when the index cannot."""
    order, _ = argv_order_index(["a.txt", "\0bad"])
    triples = [("a.txt", 1, "x")]

    assert [f for f, _n, _t in order_triples_by_argv(triples, order)] == ["a.txt"]
    assert argv_rank("\0bad", order) == len(order)
