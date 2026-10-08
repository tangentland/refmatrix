---
gmd: "0.1"
id: bsd-pattern-sibling-render-path
title: "PATTERN: the diagnosis is general, the patch is local — a correct fix that reaches one of two outputs"
severity: BULLSHIT
tags: [bsd, pattern, sibling-condition, renderer, drop-in]
---

# PATTERN: the fix reaches one of its two outputs {#root}

Seven sightings across eight audits, three of them in a single range
(`e0b7df6..1452875`). Filed because the per-finding remedies keep working and the
shape keeps returning in the next commit.

## The shape {#shape}

1. A defect is found on one surface and diagnosed correctly — **and the diagnosis
   names a general cause**: "the tool emits fan-out order", "`_replica_bundle`
   swallows its own failures", "`global_call` defaults to `retries=2`".
2. The patch is applied where the symptom was *observed*: inside one `if` branch,
   on one flag pair, at one call site.
3. The commit message states the general cause, so a reader believes the general
   fix shipped. It did not.
4. Tests pin the patched branch. The sibling branch has no test, because nobody
   wrote a test for a branch they believed was covered by the fix.

The giveaway is textual: **a commit body whose root-cause paragraph is broader
than its diff.** When the paragraph says "the tool" and the diff touches one
flag, the other flags still have the bug.

## Sightings {#sightings}

| date | finding | general cause stated | where the patch landed | sibling left |
|---|---|---|---|---|
| 2026-09-14 | plan-4 r2 | SIGTERM grace before signal | one shutdown path | `stop_daemon` forty lines down |
| 2026-09-15 | plan-4 r4 | plists must refuse a dev tree | `render_plist` (8 daemon plists) | `render_hub_plist`, two lines below, same commit |
| 2026-09-15 | plan-3 r6 | a bound in the verb binds the MCP tool only | `memory get` | `list` / `search` twins (180.2 s each) |
| 2026-09-16 | plans 7-10 r4 | the caller omits a kwarg the renderer needs | `names=` passed | `stats=` on the same call |
| 2026-10-06 | **#b-2** | *"the tool emits fan-out/completion order"* | the `-l`/`-L` block only | plain multi-file render **and** `-c` (plus `-c` dropping zero-count files) |
| 2026-10-06 | **#b-4** | *"a store that could not be searched is SAID"* | the zero-hits branch | the partial-results branch — the common fan-out case |
| 2026-10-06 | **#s-2** | `daemon.call` retries re-send the request | the three new READ calls | the one new WRITE call (`derive_stamp`), the only non-idempotent one |

rel: catalogs -> [[bsd-plan14-15-grep-family-1452875#b-2]]
rel: catalogs -> [[bsd-plan14-15-grep-family-1452875#b-4]]
rel: catalogs -> [[bsd-plan14-15-grep-family-1452875#s-2]]

## Why the per-finding remedy has not stopped it {#why}

Every prior round closed its own sighting as quoted, and several closed it with a
mutation-proven test. What never happens is the step between the diagnosis and
the patch: **enumerating the other places the stated cause reaches.** The r5
verdict asked for a "twin inventory" and the r6 remedy routed two functions and
took no inventory — the same omission one level up.

The 2026-10-06 trio makes the cost legible. All three fixes are right. All three
are one line, one branch, or one kwarg short of complete, and in two of the three
the incomplete half is the *more common* path: a fan-out where one store is down
while others answer, and a `grep -c` over several files.

## The rule to apply {#rule}

Before committing a fix whose root cause is stated in general terms, write the
inventory into the commit body:

1. Quote your own cause sentence. Underline its subject — "the tool", "this
   function", "`global_call`'s default".
2. `grep` for every place that subject appears, and list them with a verdict each
   (patched / not reached / deliberately different, with the reason).
3. If the inventory has more than one row and the diff has one, the diff is not
   the fix — it is one of its rows.
4. For a RENDERER specifically: count the `innerHTML =` / `console.print` /
   `click.echo` assignments in the function and check the payload appears in
   every one. #b-4 is a value computed once and consumed in one of two branches,
   which is visible by reading the function and invisible by reading the diff.
5. For a RETRY or TIMEOUT argument: the rule is per-call-site and the sites are
   not symmetric. Reads and writes want different answers; sort the sites by
   idempotency before copying the argument around.

## Load-bearing detail {#detail}

The three 2026-10-06 sightings each had a test that passed. #b-2's tests pin
`-l`/`-L` against real-grep controls by direct exec — a genuinely good test, for
the branch that was fixed. The missing test is for `-c` and the plain render,
and nobody writes a test for the case they believe the fix covered. So the
inventory has to happen at authoring time: no later gate can produce it, because
every later gate reads the same diff that hid it.

rel: derives-from -> [[impression_bsd_quoted_line_sibling]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]
