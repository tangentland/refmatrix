---
gmd: "0.1"
id: agent-brief-arch-215r1
title: "Brief: arch-215r1 — task 21.5 spec revision r1 (+ 24.6 r6) (ch-architect)"
tags: [agent-brief, dispatch]
---

# Brief: arch-215r1 — task 21.5 spec revision r1 (+ 24.6 r6) (ch-architect) {#root}

Revise the refmatrix task 21.5 spec (a tool-level `used` signal, derived at report time) so it
closes every finding of ch-bsd spec review r1, and amend task 24.6 for the addendum findings.

## Where {#where}

- Clone: `/Volumes/littlebig/refmatrix-plan21-5`, branch `task-21.5-tool-used-signal`, tip
  `d8ae624`. Work and commit ONLY in this clone (by pathspec; never `git add -A`; `.venv-eval`
  is an untracked symlink).
- The clone branched from dev `f7c0d39`, BEFORE 24.6 r5 (`99d96c7`) landed on dev master. First:
  `git fetch origin master` (origin = the dev repo) and merge `origin/master` into the branch
  (`--no-ff`), so you amend 24.6 from r5. Report the merge sha.

## Read first {#read-first}

1. The review: `workflow/bullshit/2026-11-11-1312-task-21.5-spec-r1-15e8f64.md` — DIRTY 18
   (3B/7S/8M) + an addendum vs 24.6 r5 (x-1..x-4: 3S/1M). Every finding needs an explicit
   disposition in the revised spec.
2. The spec: `workflow/plans/plan-21-agent-context-usage-tasks/task-21.5-tool-used-signal.md`
   (`15e8f64`), its plan `workflow/plans/plan-21-agent-context-usage.md`, task 21.1's spec and
   tests (`tests/test_task21_1_agent_usage_report.py`, `tests/test_task21_1_emitters.py`), and
   `src/refmatrix/telemetry.py` (`row_provenance`, ~line 1727).
3. 24.6 (after the merge, r5): `workflow/plans/plan-24-mod-transport-tasks/task-24.6-context-and-observation.md`.
4. 19.0 R2 (the `origin` field) wherever plan-19 lives under `workflow/plans/`.
5. `CLAUDE.md`, `.claude/PROJECT_PROFILE.md`, `workflow/templates/task-spec.md`.

## Lead decisions (made as the user would; record each as a decision row with its rationale) {#lead-decisions-made-as-the-user-would-re}

- **b-3 / Agent + mcp legs:** keep them, marked "live from 24.6 R4" (the mod gives them a real
  producer). 24.6 r6 AC-3 adds an Agent call and an `mcp__refmatrix__` call that reach the ring
  (it tests only a Read today). Until 24.6 ships, 21.5 reports those legs as not-yet-producing,
  counted, never as zero use.
- **Credit unit:** per (tool call, file).
- **R1 ring fields:** record `tool_use_id` plus ONE origin field, named `origin` per 19.0 R2.
  OD-2: the labeller records each pair's origin (main loop or subagent) from the transcript.
- **Headline:** excludes prior-touch; both numbers are printed.
- **OD-4:** the matcher signature is `(tool_name, tool_input, cwd)` plus a ring adapter; a
  memory's path is `memory_content.metadata.source_path` (memories have no `Entity.path`).
- **OD-5:** not confirmed until s-1 (define what a "prompt" is) and s-6 (a below-minimum default
  and a per-stratum minimum) are fixed in the spec.
- **`v: 2` (BULLSHIT):** a schema bump is decided by its classifier: either the spec changes
  `row_provenance` and the two 21.1 tests that pin `{"v": 2}` as malformed (named, with the new
  expectation), or it avoids the bump. Pick the smaller correct change and say why.
- **24.6 r6 for x-1..x-3:** x-3: the mod's observe records RAW `result_mentions` (pre-filtered by
  `$.state` only); 21.5 checks them against delivered events at report time (no observe-time
  backward read, one delivered-set source). x-4: `result_mentions` stays a reserved ring field
  the matcher ignores until a measured `tool_result` leg exists, counted as
  `result_mentions_present`.
- Anything else the review leaves open: decide as the user would, record the decision row and
  rationale in the spec; do not queue questions. A genuinely user-only decision (changes the
  store on disk, the public interface, or the user's stated intent) goes in an "Open for the
  user" section with a recommendation.

## Rules {#rules}

- GMD everywhere: frontmatter, `{#anchor}` on every heading, `rel:` edges for every citation;
  `python3 tools/gmd/lint.py <path>` zero errors on each file you touch.
- Prototype check: the review found three dead legs with a 40-line join over scratch copies. If
  you change the join, re-run a prototype the same way (scratch COPIES of the live events files /
  `stm/*.jsonl` under a mkdtemp root, deleted after; raw prompts never committed or quoted) and
  put only counts in the spec.
- Never run a dev-venv `rmx` against the live store, never open `Store()` on a live
  `.refmatrix/`, never write to `~/.refmatrix`, `~/refmatrix`, the live memory dir or fleet repos.
  Never `rm -rf *`; never search from `/`.
- No production code: this is a spec revision.

## Deliverable {#deliverable}

Commits on the branch: the merge of master, spec 21.5 rev 2 (a revision log entry mapping every
r1 finding and addendum item to its disposition), 24.6 r6. Final message (text): shas, the
finding -> disposition table, and anything left for the user.
