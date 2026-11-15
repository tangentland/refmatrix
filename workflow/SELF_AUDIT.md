---
gmd: "0.1"
id: self-audit
title: "Self-audit: the ch-bsd questions the author answers before saying done"
tags: [workflow, governance, review, ch-bsd, testing]
metadata:
  node_type: governance
  created: 2026-11-15
---

# Self-audit {#root}

ch-bsd's findings (about 300 BULLSHIT, 730 SKETCHY and 990 MEH across 298 reports) keep returning
to eight shapes. Each is a gap between what the author claims and what the code does. The author
can check every one of them before reporting. **Every build agent answers these questions in its
summary, with evidence: a command and its output, a grep list, a test name.** "N/A" needs a
reason. An unanswered question blocks the merge. The architect answers the same questions as
risks in the spec (one line each). Adopted 2026-11-15 (L166). {#lead}

rel: depends-on -> [[orchestration]]
rel: derives-from -> [[bsd-pattern-tests-prove-existence-not-wiring]]
rel: derives-from -> [[bsd-pattern-partial-bound]]
rel: derives-from -> [[bsd-pattern-busy-is-not-absent]]
rel: derives-from -> [[bsd-pattern-guard-cannot-fire]]
rel: derives-from -> [[bsd-pattern-sibling-render-path]]
rel: derives-from -> [[bsd-pattern-control-point-claim-without-census]]
rel: derives-from -> [[bsd-pattern-prereg-check-unrun-census]]
rel: derives-from -> [[bsd-pattern-handoff-without-sibling-ac]]

## The questions {#questions}

1. **Ran it for real.** Run the changed command or path once, the way a user or hook runs it
   (the `rmx` entry point, on a throwaway store or a read-only copy of a real catalog), and paste
   the output. Green tests are not a working command. {#q-real}
2. **The test reaches the wiring.** Name the test that goes through the entry point users call
   (CLI, verb, daemon op, hook), not only the helper. If the test patches the function under
   test or the input a guard reads, it proves nothing about production. {#q-wiring}
3. **Census of callers and siblings.** Grep every caller of what you changed, every other output
   of the same data (CLI and MCP, text and JSON, the other branch), and every construction of a
   resource you guard. List them. If the commit message names a general cause, the fix covers
   the whole list or says which items it leaves and why. {#q-census}
4. **The whole path is bounded.** For a timeout or budget: list every call on the path (each
   RPC, retry, leg, hook) and its bound. `daemon.call` defaults to `retries=2`, so the worst
   case is 3 × the timeout. State the worst case. {#q-bound}
5. **Busy is not absent.** What does the change do when the daemon or worker is busy, slow,
   or down? Try at least busy and down. A failed short ping does not mean the daemon is gone.
   {#q-busy}
6. **The guard can fire.** For each new guard or branch: name the real state that makes it
   fire, and show the caller can reach that state. The test hands it that state without
   patching the value the guard reads. {#q-guard}
7. **Failures are loud.** Force the failure once and paste what the console shows (exit code
   and stderr; a log line alone is not loud). No `except: pass`, `|| true` or `2>/dev/null` on a
   memory path. {#q-loud}
8. **Nothing handed off on paper.** Anything deferred ("task X handles it") has an AC in X's
   spec or a registry row, linked. A stated rule or count ("the rule is green on our code") was
   run, and the run is cited. {#q-handoff}

## Summary form {#form}

```
## Self-audit
1 real:     <command> → <output excerpt>
2 wiring:   <test node> enters via <entry point>
3 census:   <grep> → N sites; covered: …; left: … (why)
4 bound:    <calls on the path, each bound>; worst case <s>
5 busy:     busy → …; down → …
6 guard:    <guard> fires on <state>; reached by <caller>; test <node>
7 loud:     forced <failure> → exit <n>, stderr "<…>"
8 handoff:  <none> | <item> → <spec#ac / bug-NNN>
```

## The loop back {#loop}

ch-bsd still reviews large changes once (see [[orchestration#task]]). For every BULLSHIT it
names the question above that should have caught it. If none would have, the lead adds a
question here, or a lint when the shape is mechanical (POP row P1 (c)). A shape that keeps
returning despite its question becomes a lint. {#loop-body}
