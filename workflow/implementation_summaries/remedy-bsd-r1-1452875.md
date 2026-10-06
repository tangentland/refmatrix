---
gmd: "0.1"
id: impl-remedy-bsd-r1-1452875
title: "Remediation of ch-bsd r1 (e0b7df6..1452875): 13 findings, all 5 blockers closed"
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

## #b-2's order half: real, and now gated — my "unproven" was wrong {#b-2-closed-too}

The `-c` half was always closed: a row per named file, zeros included, in argv
order, RED at HEAD with a killed mutation. {#b-2-c}

I initially reported the ORDER half as unreproducible and nearly deleted the
fix as unproven code. **That was wrong, for two measured reasons, both of which
the audit supplied on request.** {#b-2-correction}

1. **The defect is nondeterministic — rg's parallel fan-out — so gate power
   depends on file count.** Measured over 40 runs per size, how often the
   UNFIXED build holds argv order by luck: 2 files **18/40**, 3 files 1/40,
   4+ files **0/40**. My probe used TWO files, so it had a ~45% chance of
   agreeing with grep at HEAD. One clean run was never a disproof.
2. **My control was not a control.** The rewrite hook replaces even an
   absolute-path `/usr/bin/grep` and survives a `;` separator, and this
   machine's settings carry `RMXGREP_MODE=rich` (bug-066's open config half) —
   under which both sides of that probe are `rmx` and agree by construction.
   The `# rmx grep fallback via rg` banner on stderr is the discriminator, and
   my transcript had it on the control's own output. I spotted that and still
   drew the wrong conclusion from it.

And **my fake never fired** because `_grep_rg_fallback` does a function-local
`import subprocess` — cli.py has 11 local imports and none at module level, so
patching a `cli.subprocess` attribute silently patches nothing.

The gate now in place needs no fake: `tests/test_grep_argv_order_e2e.py`, SIX
files of 400 matching lines, named in reverse alphabetical order (so an
alphabetical sort cannot pass it), every exec `shell=False` with a list argv,
and the control asserts the fallback banner is ABSENT. Measured here:
**unfixed build fails 10/10, fixed build passes 5/5.** A fourth test asserts
rg itself still scrambles at this size — if that ever stops, the gate has lost
its power and says so rather than passing quietly. The rule also stays unit
tested (`test_grep_argv_order.py`) because one comparator serves both the `-l`
branch and the line-prefixed branch, which is the shape the original fix got
wrong. {#b-2-gate}

One trap worth recording: seeding the zero counts in argv order ALREADY fixes
`-c`'s order, because dicts preserve insertion order. So a green `-c` test is
not evidence the `triples` sort works — reading it as such is how the sort
would have been deleted with every test still green. {#b-2-trap}

rel: reinforces -> [[feedback_never_explain_away_a_failing_guard]]

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
- **#m-2** eight commands with no verb. **Resolved by user decision** (2026-10-06,
  "I'm okay with internal harness/testing cli only commands"): `rmx derive
  log|diff|status` and `rmx learn on|off|status` are operator/test-harness
  surfaces, not agent capabilities, so the verb rule does not bind them. The
  registry row records that as ACCEPTED, not deferred. One piece survives the
  decision and is recorded separately, because it is not about these eight: the
  parity test cannot distinguish "CLI-only by decision" from "agent-facing and
  missing its verb", so the decision needs ENCODING (an internal-only allowlist
  the gate reads) or the next agent-facing command inherits the same blind
  spot.
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

- #s-3's cap, deliberately unretuned.
- #m-2, deferred with a trigger.
- bug-070's other half: `c.name ILIKE '%pattern%'` still draws 74 rows / 26
  concepts for `ERROR`, which is the pre-bug-067 contract and a separate
  decision.
