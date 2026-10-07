---
gmd: "0.1"
id: plan-16-invisible-grep-shim
title: "Invisible grep shim: the real tool always answers, the graph learns in the background"
tags: [plan, grep, hooks, learning, drop-in]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-06
---

# Plan 16: the grep shim stops answering and only watches {#root}

**Date:** 2026-10-06
**Status:** Drafting. No task specs yet, and no code until the user approves this plan and
[[#decisions]] is settled. Sequenced after `bsd-r1-remedy` merges (plan-15's round 4).

rel: depends-on -> [[plan-15-derive-impact-tracking]]
rel: derives-from -> [[plan-14-grep-learning-measurement]]
rel: derives-from -> [[bsd-r1-remedy-r3-bb5b97f]]
rel: amends -> [[feedback_rmxgrep_no_plain_escape]]
rel: related-to -> [[project_grep_surface_defect_family]]

## Why {#why}

Today every bare `grep`/`rg` an agent runs through the Bash tool is rewritten to `rmxgrep`/`rmxrg`
by the PreToolUse hook, and the agent shell exports `RMXGREP_MODE=rich`. In rich mode the shim
calls `rmx grep`, which answers from the index when no path is named and from its own rendering of
the `rg` floor when one is. So rmx stands in for grep on every agent search. {#today}

Standing in has been the single largest source of defects in this project. Each item below gave a
wrong grep answer to every script and agent on the machine:

- bug-058 to bug-066, bug-073 and bug-074 (the drop-in family);
- ch-bsd r3's four blockers (bug-076 to bug-079);
- the `\b` false negative found on 2026-10-06, where `/usr/bin/grep -c 'self.root\b'` prints 26
  and exits 0 while deployed `rmx grep` prints `0` and exits 1.

Three audit rounds in a row found new drop-in defects in the fixes for the previous ones. {#cost}

The benefit is smaller than the cost. Index answers reach only path-less invocations: plan-14
measured an index share of 18.5% → 31.7%, and that figure is now stale because bug-074 changed
what counts as an index answer. Learning does not need rmx to answer. It needs rmx to SEE the
search, and the shim already does that. {#benefit}

The shim already has an invisible mode. `bin/rmxgrep`'s plain mode, used today only when stdout is
piped and rich mode is off, execs the real tool (byte-exact output, grep's exit codes) and fires a
detached, throttled teach ping. This plan makes that mode the only one, and replaces the ping with a
learner that is faithful to the search. {#already-built}

## Goal {#goal}

1. A rewritten `grep`/`rg` is **byte-identical** to the real tool, on stdout, stderr and the exit
   code, on every invocation. This holds by construction, because the real tool runs; nothing
   renders in its place.
2. Every invocation the shim sees still teaches the graph, from a background re-run in canonical
   `file:line` form, with the same matching rules the caller used.
3. `rmx grep` remains as an explicit command: the index-first exploration read for an agent or a
   human who asks for it by name.

## Design {#design}

**The shim** (`bin/rmxgrep`, `bin/rmxrg`, generated hook config). {#shim}

- Delete the rich branch and `RMXGREP_MODE`. Every path ends in `exec "$REAL" "$@"`.
- The learner launches BEFORE the exec, as a detached child with its own process group and stdio
  closed, so the caller's output and exit code can never wait on it.
- Unchanged: the outside-a-project branch, the pipe-filter branch (a grep reading a pipe teaches
  nothing), the learn toggle, and the per-invocation throttle stamp.
- Remove `RMXGREP_MODE: rich` from `~/.claude/settings.json` env and `agent-bashrc.sh`, through the
  generator, never by hand.

**The learner** — `src/refmatrix/grep_learn.py`, reached through the hidden command `rmx grep-learn`.
It is NOT a verb: `verbs.VERBS` is exactly the MCP tool set, and only hooks call the learner.
It re-runs the SAME tool the caller ran, never rmx's floor, so the regex dialect is the caller's
by construction. Hits go through `learn_queue.enqueue`, a file append, so no socket and no daemon
are needed. Full spec: task 16.1. {#learner}

- **It parses the caller's argv with the same parser `rmx grep` uses.** The current ping STRIPS
  every flag. A `-i` search is re-run case-sensitively, and since bug-077 made the floor grep-case,
  that means it misses the very hits the caller saw. A `-F 'a|b'` is re-run as a regex.
- **It re-runs with the caller's matching rules and canonical output.**
  - Kept: `-i`, `-w`, `-x`, `-F`/`-E`, and every `-e` value.
  - Forced: `-nH`, as the floor does today.
  - Ignored: shaping flags (`-c`, `-l`, `-o`, `-h`, `-A/-B/-C`, `-m`), which change rendering,
    not which lines match.
  - `-v` and `-L` teach nothing, because their hits are non-matches.
- **It resolves paths to absolute against the caller's cwd before learning.** This closes the path
  half of ch-bsd r3 #s-6: learned rows are stored relative today, so verifying them depends on the
  cwd.
- **It is bounded.** At most N hits are taught (start at 500) under a wall-clock cap. Every call
  appends one record to `.refmatrix/grep-learn.log`, and the learner never opens a `Store`.
- **The dedicated Grep tool uses it too.** `grep-tool-teach.sh` (PostToolUse(Grep)) calls the same
  learner, so all three surfaces learn from one implementation.

**The explicit command.** `rmx grep` keeps its index-first read and its `rg` floor. bug-076 to
bug-079 still matter there. Its stderr notes now describe a command someone chose to run, not a
silent stand-in for grep. {#explicit}

## What we give up {#tradeoffs}

1. **Index answers for path-less agent greps.** That is the 18.5–31.7% share above. Agents that
   want the index call `rmx grep`, `rmx context` or the MCP `rmx_search` by name, as the PRIMER
   already tells them. Task 16.4 measures what is actually lost.
2. **The provenance hints** (`# rmx: 'pat' in the index …` on stderr). These were the agent's only
   sign that the index knew something. Not replaced; reconsider if 16.4 shows a loss.
3. **A command rewrite still happens.** `rmxgrep-rewrite.py` parses the command string, and a
   misparse breaks the command whatever mode the shim is in. That risk is unchanged by this plan.
   Fully passive (PostToolUse only, no rewrite) would remove it, but would lose sight of greps
   inside compound commands, and their pre-truncation context. Out of scope; noted as the fallback
   design if the rewriter keeps producing defects.
4. **Shim startup cost** (`sh` plus the learn-toggle reads) on every grep. 16.4 measures it against
   bare grep.

## Tasks {#tasks}

Specs go in `workflow/plans/plan-16-invisible-grep-shim-tasks/` before approval.

| Task | Builds | Acceptance (sketch) |
|---|---|---|
| 16.1 | the `grep_learn` verb + `rmx grep --learn-only` | flag fidelity table RED→GREEN: `-i`/`-w`/`-F`/`-x`/`-e` each teach the lines `/usr/bin/grep -n` reports; `-v`/`-L` teach nothing; learned paths absolute; bounded under a stalled daemon (wall < cap + 1 s) |
| 16.2 | invisible shim: rich branch + `RMXGREP_MODE` removed, learner wired, generator updated | differential vs `/usr/bin/grep` and `rg` over a fixed invocation corpus: stdout, stderr, exit identical 100%; `rmx install-hooks --check` clean; learner never delays exit (shim wall within ε of bare grep while daemon stalled) |
| 16.3 | Grep-tool hook on the learner; docs (PRIMER text, `.refmatrix/CLAUDE.md` briefing, search_hooks header, guard header) | Grep-tool teach uses argv-faithful learner; docs say "grep is observed; ask the index by name" |
| 16.4 | measurement | replay the real grep log (plan-14's corpus) through old ping vs new learner: patterns taught, rows taught, precision of taught rows vs real lines (must be 1.000); shim overhead p50/p95; index-answer share forgone |

## Decisions (user, 2026-10-06) {#decisions}

1. **Yes, this supersedes the 2026-09-06 stance.** The rewrite no longer exists so that grep is
   ANSWERED by the index; grep is observed, and the index is asked by name. The 2026-09-15
   no-bypass rule stands: every grep still teaches, and the learn switch is the only off switch.
   Recorded in memory `feedback_grep_is_observed_not_answered`. {#d-1}
2. **Fold `RMXGREP_TEACH=0` into `learn_switch`.** One off switch, not two. 16.2 deletes the env
   var from the shims. If the env var is still set, the shims learn anyway; the learner's log
   record names it and `rmx learn status` points to `RMX_LEARN=0`. Nothing goes to stderr, because
   byte-identity includes stderr (task 16.2 R3). {#d-2}
3. **Invisible shim, not fully passive.** The rewrite stays, because it sees greps inside compound
   commands along with their exact argv and cwd. Fully passive remains the fallback only if 16.2's
   rewriter differential finds misparses. {#d-3}

**Interim (user, 2026-10-06):** `RMXGREP_MODE=plain` in `~/.claude/settings.json` and
`.claude/settings.local.json`. Any value other than `rich` is auto, and the agent shell is not a
tty, so greps already run the real tool plus today's flag-stripped ping until 16.2 ships. The 63
env-sensitive tests pass under it (`workflow/review-output/rmxgrep-mode-plain.log`). {#interim}

Next gate: task specs written (`plan-16-invisible-grep-shim-tasks/`, 16.1–16.4); `@ch-bsd` spec
review, then `approved`.

## Out of scope {#out-of-scope}

- Fixing `rmx grep`'s own drop-in gaps beyond what r3 already fixed (`\b`/`\<` BRE escapes, the
  missing-path exit code, `-w` verification). Each is logged in `workflow/bug_registry.md` and
  belongs to the explicit command's backlog. The shim no longer exposes them.
- A PATH-level `grep` alias. CORRECTION (task 16.2): scripts the agent runs under bash DO reach the
  shim today, through the `grep()`/`rg()` functions that `BASH_ENV` defines in
  `agent-bashrc.sh`. They become invisible along with everything else. Shells outside the agent are
  untouched.
