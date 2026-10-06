---
gmd: "0.1"
id: impl-remedy-bsd-r1-1452875
title: "Remediation of ch-bsd r1 (e0b7df6..1452875): 13 findings, 4 of 5 blockers closed and one named unproven"
tags: [implementation-summary, bsd, remediation]
metadata:
  node_type: summary
  audit: bsd-plan14-15-grep-family-1452875
  created: 2026-10-06
---

# Remediation of ch-bsd r1 {#root}

rel: implements -> [[bsd-plan14-15-grep-family-1452875]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]

The audit's verdict was DIRTY, 13 findings (5 BULLSHIT, 5 SKETCHY, 3 MEH), and
every claim the dispatch asked it to attack held up. So this is not a defence
of the range; it is the repair. {#lead}

## The blockers {#blockers}

**#b-3 — a test wrote `src/refmatrix/store.py`.** The rewrite now lands on a
copy via `_DERIVE_SRC_DIR`, the seam 130 lines below whose comment already said
"tests edit real COPIES". Verified by `stat`: byte-identical mtime and size
before and after that file's 22 tests. This one mattered beyond itself — it is
why the "2432 passed" log describes a tree the suite edited 70 s in, and
`handoff.md` now RETRACTS that line as evidence about `1452875`. {#b-3}

**#b-1 — "the remainder is COUNTED" over a 0-or-1 producer.** `_op_embed`
reported `len(pending_embeddings(limit=1))`. New
`Store.pending_embeddings_count` does a COUNT over the same predicate, which is
factored into `_pending_embeddings_where` so the list and the count cannot
drift — this repo's recurring defect is one rule implemented per call path.
Measured on a throwaway store: `len(limit=1)` = 1, count = 9. The fake that hid
it asserted `remaining: 9999`, a value the producer could not emit; two new
tests drive the real store method and the real `_op_embed` with only the MODEL
faked. {#b-1}

**#b-2 — the drop-in fix reached `-l`/`-L` only.** Split in two, and only half
is claimed. {#b-2}

**#b-4 — the skipped-store note.** `doWhere` computed `skipNote` and spent it
only in the zero-hits branch, so the partial fan-out rendered as if every store
answered. One concatenation. The reason is now HTML-escaped as well: bug-069
had just started feeding exception text and filesystem paths into that
template. {#b-4}

**#b-5 — ~20 unregistered doubles.** Six registry rows, including the two that
hid defects and one recording a double DELETED the day it was written. {#b-5}

## #b-2's order half is NOT fixed, and that is the honest answer {#b-2-open}

The `-c` half is real and closed: `grep -c PAT a b c` prints a row per named
file, zeros included, in argv order, and the fix was RED at HEAD with a killed
mutation. {#b-2-closed}

The ORDER half I could not reproduce, and two attempts to prove it failed in
ways this ledger already catalogues: {#b-2-attempts}

1. A bash control against `/usr/bin/grep` — which the PreToolUse rewrite hook
   INTERCEPTS, so both sides were `rmx` and agreed for the wrong reason. The
   sibling test file's own docstring warns about exactly this.
2. A faked `subprocess.run` handing the renderer reversed output. The fake
   fires (instrumented: one `rg -nH -S --no-heading -F` call), but the
   reversal does not change the rendered order with OR without the fix, and a
   mutation deleting the entire sort left all tests green.

The audit saw `rmx` put `a.txt` first where grep put `b.txt`; I see both put
`b.txt` first. Those are consistent with rg's fan-out being NONDETERMINISTIC —
the two observations are two draws, not a contradiction — but I could not force
the losing draw, so I will not claim a fix I cannot demonstrate.

What shipped instead: the rule is now module-level (`argv_order_index`,
`argv_rank`, `order_triples_by_argv`) and pinned by 7 unit tests, including the
three properties that made the original fix wrong in one of two places — one
comparator serves a bare path AND a `file:line:text` line, a directory walk is
left alone, and a duplicated path keeps its first position. A rule that cannot
be reproduced on demand still has to be correct; it no longer rests on a gate
that cannot fail. {#b-2-shipped}

rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

## SKETCHY {#sketchy}

- **#s-1** `derive-UNKNOWN` joins `hub queues`'s human flag list. `derive_error`
  reached `--json` and no reader.
- **#s-2** `retries=0` on the `derive_stamp` call — the one WRITE among the four
  new `daemon.call` sites. `_op_derive_stamp` appends a `derive_history` row,
  so a client-side timeout on a stamp the daemon applied recorded the derive
  twice. Confirmed: 3 stamps, 3 history rows.
- **#s-3** `DERIVE_HISTORY_MAX = 50` is documented as "a release arc" and
  measures ~11 hours. Left as-is deliberately: 50 rows per (partition, pass) is
  the right ORDER for a cap whose job is bounding the table, and the defect is
  the DOCSTRING's claim about what it buys. Noted here rather than retuned,
  because changing the number without measuring what history readers actually
  need would be the same unmeasured move in the other direction.
- **#s-4** the published `multi-word 0/18 → 14/15` reproduces under NO
  definition. Corrected to `0/28 → 24/27 (88.9%)` with the definition stated
  (patterns containing a space, over those that taught something) and both
  halves traceable to the committed JSON; the two other defensible pairings are
  given, and the overstatement — 93% claimed vs 88.9% real, on bug-067's
  central cell — is named. Fixed in the measurement doc, bug-067's registry row
  and the test docstring that cited it.
- **#s-5** plan-15 returns to `in-progress`. It was flipped `completed` before
  this gate ran and #b-3 is task 15.1's own test.

## MEH {#meh}

- **#m-1** the breadth instrument's run instructions named
  `grep_evidence_precision.py`; the file is `grep_evidence_breadth.py` (I
  renamed it mid-session and left the docstring behind). Fixed.
- **#m-2** eight agent-facing commands with no verb. REGISTERED as a deferral
  rather than fixed, with the part that matters recorded: the parity test
  asserts every MCP tool is a verb, so it is structurally blind to a command
  that never became either — adding the verbs without extending the test
  leaves the same blind spot for the next command.
- **#m-3** the toggle reported a typo'd `RMX_LEARN` loudly and swallowed an
  unreadable marker with a bare `pass` — and the fall-through lands on ON, so
  an operator who turned learning off and hit a permission problem got it back
  on with no word. `Decision.marker_error` carries it; `rmx learn` prints it;
  2 tests, one of which asserts the quiet case stays quiet.

## Gates {#gates}

Full suite re-run at the remediation HEAD with the tree state captured before
it started, precisely because #b-3 made the previous log unattributable:
`workflow/review-output/pytest-bsd-r1-remedy-full.log`. GMD lint 0 errors.
Mutations: #b-1 (2 tests on the real producer), #b-2's `-c` (killed), #b-3
(proven by `stat`, not by a test), #b-4 (source-level gate, named as the weak
one it is — this repo runs no JS). {#gates-body}

## What is still open after this pass {#open}

- #b-2's order half, above — unproven either way, pending the auditor's repro.
- #s-3's cap, deliberately unretuned.
- #m-2, deferred with a trigger.
- bug-070's other half: `c.name ILIKE '%pattern%'` still draws 74 rows / 26
  concepts for `ERROR`, which is the pre-bug-067 contract and a separate
  decision.
