---
gmd: "0.1"
id: agent-brief-iso-bug301
title: "Isolated agent brief: bug-301 — content_terms strips punctuation from tokens"
tags: [agent-brief, isolated, bug-301, terms, bm25]
metadata:
  node_type: brief
  created: 2026-11-24
---

# bug-301: `content_terms` strips punctuation {#root}

You are an isolated small-fix agent (L174/L176) in your own clone: one agent writes the test and
the fix, test seen failing first. Read `CLAUDE.md` `#test-discipline` and bug-301's row in
`workflow/bug_registry.md`.

rel: implements -> [[bug_registry]]

## The bug {#bug}

`src/refmatrix/terms.py::content_terms` splits on whitespace and keeps punctuation:
`'How long is my daily commute to work?'` → `['long','daily','commute','work?']`;
`'is the grep (backstop) ok, really?'` → `['grep','(backstop)','ok,','really?']`. The last word
of every question, and any bracketed or comma-trailed word, never resolves to its concept. Every
`content_rank` caller is affected (`rmx context` natural-language queries, `memory recall --fuse`,
scan). {#bug-body}

## Do {#do}

1. RED: find the existing test file for `content_terms` (`rmx-master context content_terms`, or
   grep `tests/` for it) and extend it (no new file): a parametrized test over the three inputs
   above plus symbol-shaped tokens that MUST survive intact (`fov_wedge`, `refmatrix.store`,
   `src/refmatrix/terms.py`, `bug-301`, `--fuse`, `a.b_c`). Expected: leading/trailing
   punctuation `?!,;:()[]{}"'` stripped, internal `_ . / -` kept, a leading `--` on a flag kept
   or dropped (decide, say why in the docstring). Also one test through `rmx context` on a fixture
   store (the existing context test fixtures) where a query ending in `word?` finds `word`. Seen
   failing at base: keep the E lines.
2. GREEN: strip per token as the test says; drop a token that becomes shorter than the existing
   2-char floor. Docstring names bug-301 and the date.
3. Run the file(s) you edited, `tests/test_context*.py` that exercise natural-language queries,
   and `tests/test_suite_discipline.py tests/test_wallclock_census.py`, with
   `PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee ../bug301.log`.
   Any background wait has a deadline.
4. Mutation: revert your src change only, re-run the new tests: they fail; restore.
5. Update bug-301's row: fix text and status `fixed` (cite your commit in a second commit).

## Report {#report}

In the REPORT.md the prompt names: commit shas, the RED E lines, the GREEN counts, the mutation
result, your `--` decision.
