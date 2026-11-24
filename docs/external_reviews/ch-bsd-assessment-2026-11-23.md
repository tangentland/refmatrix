---
gmd: "0.1"
id: refmatrix/ch-bsd-assessment-2026-11-23
title: "ch-bsd across the fleet: what the ledgers say it is worth, and eight findings to act on after 0.85.0"
tags: [external-review, ch-bsd, review, process, cat-herder]
metadata:
  node_type: external-review
  created: 2026-11-23
  harness: "read-only census of workflow/bullshit/ ledgers and .claude/agents/ch-bsd*.md across every repo on this machine"
  origin_session: dd0578f8-70b4-4c79-9eae-a453aefd8d45
  bus_message: e5f2ccbe0917
  memory: announce-e5f2ccbe0917
  status: hold-until-0.85.0
---

# ch-bsd across the fleet: assessment and findings {#root}

An assessment of the ch-bsd agent (the runtime-integration auditor, or "bullshit detector")
across every project on this machine, written from its own ledgers. The same text went to
`proj:refmatrix:process` as bus message `e5f2ccbe0917` and was accepted into memory as
`announce-e5f2ccbe0917`.

**HOLD.** Act on nothing here until 0.85.0 is released and deployed. This is not freeze-line
work. After that release, react to each finding in [[#findings]] (F1-F8; F8 added 2026-11-24): fix it, admit it as a
[[plan-of-plans#queue]] row, or rule it out with an L-row and a reason. {#hold}

rel: evidence-for -> [[plan-of-plans#queue]]
rel: depends-on -> [[orchestration]]

The subject is the agent definition `.claude/agents/ch-bsd.md` plus its overlay
`.claude/agents/ch-bsd.local.md`. Neither is in the lint scope, so it is cited by path rather than
by `rel:` edge.

## Verdict {#verdict}

ch-bsd is the highest-value reviewer in the stack. Until the lean reset of 2026-11-15
(L164–L167) it was also the most expensive. Its value comes from running things: it probes
throwaway stores, worker clones and database roles. That value does not come from the charter
written in its definition. The cost came from the review loop around it, which the reset has
since bounded. **Keep it, and keep the one-pass rule.** {#verdict-lead}

## What this does NOT claim {#not-claimed}

- **Precision is not measured.** No ledger records how often a BULLSHIT was upheld versus
  overruled, so "high value" rests on sampled findings, not a rate ([[#f5]]).
- **No cost in tokens or wall-clock** was measured per run. Cost is inferred from round counts
  and the L165 line counts.
- **Counts are parsed from `INDEX.md` rows**, using the `(XB/YS/ZM)` pattern and `r<n>` round
  tags. Rows that don't follow the pattern are not counted.

## Evidence {#evidence}

### Where it is used {#usage}

| Project | Runs | CLEAN | BULLSHIT / SKETCHY / MEH | PATTERN files | Active |
|---|---:|---:|---|---:|---|
| refmatrix | 285 | 12 (4%) | 298 / 736 / 1,021 | 8 | 2026-09-14 → today |
| cliquedb | 118 | 43 (36%) | — | 7 | 2026-06-22 → 2026-11-10 |
| viascope | 91 | 14 | own vocabulary (`CLEAR`, `O`) | 1 | 2026-05-12 → 2026-06-22 |
| cliquet | 9 | 2 | — | 0 | 2026-09-09 |
| thiquet | 6 | 1 | — | 0 | 2026-06-30 → 2026-07-09 |
| cat-herder, orderly, prep_prolific, atlftpd, atldb, portal | 0 | — | — | 0 | template files only |

### Convergence before and after the reset (refmatrix) {#convergence}

| Window | Runs | Highest round | Distribution |
|---|---:|---|---|
| 2026-09-14 → 2026-11-14 | 254 | r18 | 228 of all runs were r2 or later; 50 reports on 2026-11-14 alone |
| 2026-11-15 → today | 31 | r3 | 23 × r1, 7 × r2, 1 × r3 |

L165 measured the cost of the old shape on 2026-11-13..15: 731 commits, 40 touching `src/`,
+5.1k `src` lines against +63.6k lines of plans, specs and reviews. Specs were reviewed for
5–9 ch-bsd rounds each. {#l165-cost}

### What the value looks like {#value}

- **Real defects, found by probing.** Examples: the deploy venv imported the dev tree
  (`bsd-0661-e2e-memory-bridge`). A replica-merge fix remapped ids but left `memory_content`
  keyed on the raw id, so one memory took another's body (bug-216 r2). In cliquedb, a
  **live critical** finding: a tenant-owner ACE ran as the `cliquedb` superuser
  (`bsd-tenant-domain-check-as-definer-3316f5e-680075a`).
- **The only role asking what is missing.** L167 recorded that RED and GREEN share the spec's
  blind spots and that mutations cannot see code that was never written.
- **Impressions that transfer.** "Census the resource, not one constructor of it";
  "an exit-code allowlist needs a probe for every code it admits"; "a remedy RED that rebuilds
  the repro in a more convenient place tests a different bug".
- **Judgment moved upstream.** L166 turned the 8 PATTERN files into [[self-audit]] questions,
  so ch-bsd's lessons now shape the work before review.

## Findings {#findings}

### F1. `last_run.log` is stale and still read first {#f1}

`workflow/bullshit/last_run.log` is dated 2026-10-19 and holds 2 lines. The definition says it is
always one line, overwritten on every run. CLAUDE.md `#session-start` step 3 tells every session to
read it first, so sessions orient on audit state five weeks old. **Fix:** make the writer honour
the contract (overlay or definition), or point CLAUDE.md at the tail of `INDEX.md`.

rel: contradicts -> [[claude#session-start]]

### F2. The charter does not match the job {#f2}

The definition says ch-bsd ONLY checks "does this code actually run in production" and leaves
security and test quality to other agents. Its best findings are correctness, concurrency and
security bugs, and the refmatrix overlay adds test-discipline checks. The base text is written
for a web app (resolvers, `useQuery`, E2E assertion waves) and mostly doesn't apply to the Python
and SQL repos that use it. **Proposal:** recharter it as an *adversarial runtime verifier* and move
the frontend and assertion-wave sections into overlays.

### F3. No written stop condition {#f3}

The definition's stance (hostile, "no benefit of the doubt", "a single cheap-fix finding is enough
to block"), plus escalation by repetition count rather than impact, produced unbounded rounds. A
reviewer that says CLEAN 4% of the time carries little signal in its verdict. **Fix:** write L165
into the definition itself. No BULLSHIT means GO, and SKETCHY and MEH go to a fold list and never
trigger a new round.

rel: derives-from -> [[plan-of-plans#rulings]]

### F4. The leaderboard cannot tell authors apart {#f4}

136 `INDEX.md` rows list the author as just "orchestrator". The by-author BS rate, which the
definition calls "the reason ch-bsd exists", therefore says nothing. **Proposal:** replace it with
a tally by [[self-audit]] question, recording which question missed each BULLSHIT. That is the
feedback loop L166 already set up.

### F5. Precision is unmeasured {#f5}

Nobody tracks how often a BULLSHIT is upheld versus overruled by a lead ruling. Without that, the
agent's hostility is a setting nobody has measured. **Fix:** give each BULLSHIT a column or registry
link, either `bug-NNN` fixed or overruled with its L-row, and report the rate.

### F6. Ten definition copies, ten checksums {#f6}

Every `.claude/agents/ch-bsd.md` on the machine differs from every other. The cliquedb copy adds
an rmx-grep block and a raw-git block. refmatrix differs from cat-herder only in the memory-bridge
command. viascope has no agent file and uses its own verdict vocabulary. **Proposal:** one canonical
template (cat-herder, or `src/refmatrix/templates/agents/`), project specifics only in `.local.md`
overlays, one verdict vocabulary everywhere, and a script that reports drift between the copies.

### F7. `IMPRESSIONS.md` is 396 lines against a 50-line cap {#f7}

The `## Former anchors, restored` section is exempt from the cap under the refmatrix overlay, but
every run still reads the whole file. **Proposal:** move the pointer list into its own file so the
run-time read stays near the cap.

### F8. SKETCHY is under-rated, and since L165 the label decides whether a fix is verified {#f8}

Added 2026-11-24 at the user's prompt ("some of the sketchy bsd findings seem like they should be
bullshit"). **Census:** every SKETCHY in the 11 post-reset *code* reviews (2026-11-15 → 11-24;
spec reviews excluded), 25 findings in all, read in full and traced to the lead's ruling in
[[plan-of-plans#rulings]]. {#f8-census}

**Why it matters now.** Under L165 only BULLSHIT earns a confirm round. A SKETCHY is folded and
merged on the author's word, so a finding rated too low now ships its fix without an independent
check. **Why it happens.** The definition sets severity by *category* (unregistered mock, new
deferral or unwired config are all SKETCHY), not by *consequence*. ch-bsd has also argued itself
down in writing: "why sketchy, not bullshit: it is disclosed … and fits the letter" (s1 r1 s-1),
for code its own rule 1 calls dead. {#f8-why}

**Rubric applied.** BULLSHIT when the code at HEAD does one of the following:

1. breaks a real entry point (CLI, MCP tool, hook);
2. silently loses or corrupts state, or skews a measurement the release relies on;
3. traps the user or holds the harness unbounded;
4. leaves a test or guard that cannot fail for the property it claims;
5. is dead by the definition's own rule 1;
6. is a rule-10 cheap fix (for example, test slack added to hide a defect).

**Gate breach** when the code is correct at HEAD but a mutation on the `src` change survives.
CLAUDE.md `#before-commit` already requires every mutation to fail a test. {#f8-rubric}

| Verdict | Count |
|---|---:|
| Should have been BULLSHIT | **13** |
| Gate breach (correct at HEAD, protection missing) | 9 |
| SKETCHY is right | 3 |

**The 13 that should have been BULLSHIT, and whether the fix got an independent confirm:**

| Report | Finding | Rubric | Confirm? |
|---|---|---|---|
| scanorder r1 `ca22b79` | S2: named identifiers cut before ordering; tier 1 was **empty** on the real hook run | 1 | ruling not located |
| scanorder r1 | S3: composite marked "sent" when the byte budget dropped it, then never re-sent | 2 | ruling not located |
| t02 r1 `1121b4e` | S3: stop drain runs outside `_StopDeadline` (bug-051); `conftest.py` adds 30 s slack to absorb it | 3, 6 | **no** (L169: B1, B2 only) |
| t02 r1 | S4: `register_spawn` has no adopter | 5 | **no** (L169) |
| 315 r1 `51bbdfb` | S1: capture flips scan-prompt / recall exit to 1 with a traceback (surrogate prompt, unreadable dir); the scan hook's `2>/dev/null \|\| true` hides it | 1, 2 | **no** (L178; red re-ran probes) |
| 315 r1 | S2: unchanged composite re-sent; skews the `suppressed_unchanged` counts the release measures | 2 | **no** (L178) |
| 315 r1 | S4: bug-268 fixed on one of five readers; focus-graph corruption is sticky; loader kept lenient "so AC-0.16 has a raising input" | 2, 6 | **no** (L178) |
| t04 r1 `5eae7916` | S1: mock-registry guard blind to module-object swaps; a live unregistered swap passes it | 4 | yes (L186, lead added it) |
| s1 r1 `be1c6b6c` | s-1: kept `_migrate_*` moves are dead in effect on DuckDB | 5 | yes, through b-1 (L191) |
| 294a r1 `1bb14a5b` | s-1: the tier tests' own file is classed `devtree`, so it is NOT RUN in any clone or lane | 4 | **no** (L197: b-1 only) |
| cah r1 `cbbe9e3f` | s-1: rollback lockout; every tool call denied, the only way out is deleting the gate file by hand | 3 | yes (L202, lead added it) |
| cah r1 | s-2: compaction held for minutes; the bound test asserts over an EMPTY list | 3, 4 | yes (L202; L204 set 10 s) |
| cah confirm `4784cdd5` | s-3: MCP `rmx_memory_recall(recent, pack)` raises `VerbArgsError` | 1 | **no** (L208: "no BULLSHIT, L165") |

**Gate breaches (9):** t08 r1 S1, S2; t02 r1 S1, S2; t03 r1 S1, S2, S3; 315 r1 S3; t05 r1 s-1
(confirmed at L188). **SKETCHY is right (3):** scanorder S1, t04 S2, 294a s-2 (now bug-305).
{#f8-tables}

**What the census shows.** Of the 13, 4 got an independent confirm, and in 3 of those the lead
added the SKETCHY to the confirm by hand (L186, L202). 7 did not, and for 2 no ruling was found.
The lead is already re-rating case by case. The label carries less signal than the lead's
judgment, and when that judgment isn't applied, as at L208, a broken MCP tool merges on a fold
alone. {#f8-finding}

**Fix:**

1. Put the rubric into the definition, so severity follows consequence and any breach of a
   CLAUDE.md CRITICAL rule is BULLSHIT.
2. ch-bsd may not argue a finding down for being "disclosed" or "fitting the letter".
3. A surviving mutation on a `src` change gets its own label, GATE, and the merge needs either a
   killing test or a ruling.
4. Re-check the 7 unconfirmed fixes once, by probe, after 0.85.0.

**F3 depends on F8:** "no BULLSHIT means GO" is only safe once severity is right. {#f8-fix}

rel: amends -> [[#f3]]
rel: contradicts -> [[claude#before-commit]]

## The consequence package (F8 + F3), drafted for one commit {#package}

**User ruling, 2026-11-24:** the 7 unconfirmed fixes are re-checked after 0.85.0, not before. The
consequence change to the instructions must be in place first, together with the process change
that goes with it. The re-probes run under the new rubric, not the old one. {#package-ruling}

The package is four edits, landed as **one commit** after 0.85.0 deploys. Changing the rubric
without the process, or the process without the rubric, leaves either a label that doesn't decide
anything or a decision keyed to a label that is still wrong. {#package-one-commit}

### P1. `.claude/agents/ch-bsd.md` `#severity-levels`: replace the table {#p1}

```markdown
Severity follows CONSEQUENCE, never category. Rate by what the code at HEAD does.

| Level | The code at HEAD … | Action |
|-------|--------------------|--------|
| **BULLSHIT** | (1) breaks a real entry point (CLI, MCP tool, daemon op, hook); (2) silently loses or corrupts state, or skews a measurement the release relies on; (3) traps the user or holds the harness without a bound; (4) leaves a test or guard that cannot fail for the property it claims; (5) is dead (rule 1); (6) is a cheap fix (rule 10). Any breach of a CLAUDE.md CRITICAL rule is BULLSHIT. | Fold, then a confirm-lite by probe. |
| **GATE** | is correct today, but a mutation on the `src` change survives every test. | Merge needs a killing test, or a lead ruling that names why none is possible. |
| **SKETCHY** | works, but a gap needs written justification (heuristic quality, letter-vs-intent, a missing pin with no live consequence). | Implementer folds; lead reads the diff. |
| **MEH** | has a minor gap. | Noted or folded in the same commit. |

Never rate DOWN because a gap is disclosed, documented, or fits the letter of a spec.
Disclosure is not wiring. When torn between two levels, state the consequence that decides it.
```

The category defaults in rules 3, 7 and 9 ("→ SKETCHY") become *starting points*. A finding is
raised to BULLSHIT whenever its consequence matches a BULLSHIT clause. {#p1-categories}

### P2. `workflow/ORCHESTRATION.md` `#task`, large-change step 5: replace the severity sentence {#p2}

```markdown
BULLSHIT → fold, then one confirm-lite. GATE → a killing test is added (seen failing on the
mutant) or the lead rules, in an L-row, why none is possible; no new round. SKETCHY → the
implementer folds and the lead checks the diff; no new round. MEH → noted or folded in the same
commit. The lead may raise a severity, never lower it, and records the consequence that decided.
```

### P3. `CLAUDE.md` `#task-completion-workflow` step 4 and `#before-commit` {#p3}

- Step 4: "one ch-bsd pass (only BULLSHIT earns a second round)" → "one ch-bsd pass; BULLSHIT
  earns a confirm-lite, GATE needs a killing test or a ruling".
- `#before-commit`: "one ch-bsd pass with no unaddressed BULLSHIT" → "… with no unaddressed
  BULLSHIT or GATE".

### P4. `.claude/agents/ch-bsd.local.md`: re-rate the overlay's test-discipline clause {#p4}

"Each is at least SKETCHY; a test that cannot fail is BULLSHIT" → "Each is at least SKETCHY. A
test or guard that cannot fail for its stated property, a patched guard input, or a waited-out
timeout that hides a defect is BULLSHIT (P1 clause 4 or 6)."

rel: amends -> [[#f8-fix]]
rel: depends-on -> [[orchestration]]

## Recommended order after 0.85.0 {#order}

1. **The consequence package ([[#package]]: P1-P4, F8 with F3) in one commit**, with F1 in the
   same commit or just before it. Nothing below starts until the package is merged.
2. **Re-probe the 7 unconfirmed fixes** from [[#f8-tables]] under the new rubric: one ch-bsd
   confirm-lite that re-runs each finding's own probe against 0.85.0. Prioritise the MCP
   `rmx_memory_recall(recent, pack)` path (cah confirm s-3). Anything still live is rated by P1.
   The 9 GATE rows get a killing test or a ruling.
3. F5 and F4 together, since both add columns to the same ledger.
4. F6, then F2. Consolidate the template first, then recharter it once. P1's table carries over
   into the canonical template unchanged.
5. F7 at the next impressions fold.
