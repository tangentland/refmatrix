---
gmd: "0.1"
id: bsd-pattern-prereg-check-unrun-census
title: "PATTERN: a static bypass rule pre-registered against a census nobody ran. Three consecutive plan-18 rounds; the rule was red on its own correct code each time"
tags: [bsd, pattern, ast, static-rule, census, pre-registration, plan-18]
---

# PATTERN: a pre-registered check stated against a census that was never run {#root}

**Filed:** 2026-10-15, at the 3rd consecutive sighting (plan-18 r1 → r2 → r3). It was confirmed
closed at r4 by a census run of the rule exactly as written.

rel: derives-from -> [[bsd-plan18-r1-spec-review-b84fd8d#s-1]]
rel: derives-from -> [[bsd-plan18-r2-spec-diffcheck-cb7bf5b#n-b2]]
rel: derives-from -> [[bsd-plan18-r3-spec-diffcheck-1318b30#n3-b2]]
rel: derives-from -> [[bsd-plan18-r4-closing-diffcheck-c4ef0a8]]
rel: related-to -> [[bsd-plan23-17-spec-rereview-r8-23ad703]]

## Shape {#shape}

A spec writes an AST/static rule (for example "a CHECKPOINT appears only at these sites") and,
next to it, a sentence asserting the census: "the rule is green on our own correct code". Nobody
ran the rule over the source tree to produce that sentence; it was reasoned. Each round, the
reasoned census was wrong in a new way, so the AC was red at GREEN on correct code. A red AC
on correct code is the same failure as an unpassable test. The pressure at build time is then
to weaken the rule until it passes, which removes the guard the rule was written to be.

## Sites {#sites}

| Round | Rule as written | What the run found |
|---|---|---|
| plan-18 r1 S-1 | walk `daemon.py` only; literal at named sites | the census missed three daemon-reached CHECKPOINTs; the hold could be moved to `catalog_maint.py` to bypass it |
| plan-18 r2 N-B2 | walk every module; constant match | red at 18.2 GREEN; could not see `store.py`'s site |
| plan-18 r3 N3-B2 | any string constant, case-INsensitive | flagged six op-name and message strings, two at module level where no function-name exemption can reach |
| plan-18 r4 (closed) | two legs (case-sensitive constant; case-insensitive execute-family argument) | `census3.py` run on the rule exactly as written: 10 constants, 9 functions, no extra hits; its mutations fail |

A sibling of this pattern is plan-23/17 r8: "no handler takes the lock" checked handler bodies
only, while the CLI ops reached the lock through helpers.

## Rule {#rule}

- **The census sentence is evidence.** Any spec that registers a static rule together with a
  census claim ("green on correct code", "exactly N sites") must name the script that produced
  the claim, and the commit it ran at. Without both, the claim is SKETCHY on first sight and
  BULLSHIT if the rule is the AC's kill.
- **The run uses the rule's exact wording.** It includes case sensitivity, which f-string parts
  count, docstring handling, and whether module-level code is covered. A paraphrase of the rule
  is not a run of it.
- **Every registered mutation is planted and seen red.** It is not enough to reason about it.
- **The reviewer's own replacement text gets the same check.** At r4 the reviewer's r3 text
  added an AC clause (a "0-byte foreign WAL" log line) that no requirement produces
  (r4 N4-S1).

rel: contradicts -> [[project-profile#constraints]]
