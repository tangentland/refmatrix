---
gmd: "0.1"
id: impl-grep-dropin-family-062-066
title: "The grep drop-in family closed: bug-062, 063, 064, 066 — and two rows whose premises were wrong"
tags: [implementation-summary, grep, bugs, contract]
metadata:
  node_type: summary
  created: 2026-10-06
  bugs: [bug-062, bug-063, bug-064, bug-066]
---

# Closing the `rmx grep` drop-in family {#root}

rel: evidence-for -> [[bug_registry]]
rel: derives-from -> [[project_grep_surface_defect_family]]
rel: related-to -> [[project_grep_output_shape_one_resolver]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]

Four open rows, all on the path every bare `grep` takes through the PreToolUse rewrite, and three of
the four were **control-flow inversions** — `if cmd | grep …` taking the branch it must not. All
four are closed. The registry carries the per-row detail; this records what the rows got wrong and
what the mutation check caught. {#lead}

## Two rows whose premises did not survive measurement {#premises}

**bug-062 said it needed a product decision.** Its analysis: "At the fd level 'the producer emitted
nothing' and 'there is no producer' are indistinguishable: both are a FIFO at EOF", followed by three
options, each breaking a different class of caller. Measured instead: {#bug-062}

| invocation | fd 0 |
|---|---|
| bare command under the Claude Bash tool | CHR (`/dev/null`) |
| `{ true; } \| cmd` | FIFO |

They differ, so there was no trade-off to make. `_is_stdin_piped` had been asking the wrong
QUESTION — whether bytes are PENDING, which conflates an empty pipe with no pipe — and now answers
on the fd's SHAPE. The measurement is itself a test
(`test_a_bare_invocation_and_an_empty_pipeline_differ_at_the_fd`), because the whole fix rests on it:
if a platform ever hands a bare command a FIFO, that test fails first and explains the rest.
{#bug-062-fix}

Two side effects worth recording. The blocking `select()` + FIONREAD probe that the 0.65.1
slow-producer race required is RETIRED — emptiness left the judgement, so there is nothing to wait
out. And two tests in `test_grep_stdin_dialect.py` asserted the OLD contract ("a closed empty pipe is
not piped"); that contract WAS the defect written as a test, so they are rewritten as SUPERSEDED with
the measurement as the reason rather than deleted. {#bug-062-fallout}

**bug-066's recommended fix did not cover the failing case.** The row proposed having "the
`rmxgrep`/`rmxrg` wrappers signal filter-vs-explore explicitly". Reproduced three ways first, which
showed why that would not help: the WRAPPER is already correct (its `[ -p /dev/stdin ]`
short-circuit execs the real tool and exits 1), and the defect only reaches a DIRECT
`cmd | rmx grep PAT`, where no wrapper is involved. {#bug-066-premise}

| path, empty producer | exit | lines |
|---|---|---|
| real grep | 1 | 0 |
| `rmx grep` | **0** | **6** |
| deployed `bin/rmxgrep` | 1 | 0 |

What bug-066 IS, and what was fixed: the generated rewriter resolved `<venv>/bin/rmxgrep` (4,760 B,
whatever pip last installed) before `<tree>/bin/rmxgrep` (5,714 B, the deployed copy), so bug-005's
pipe short-circuit and the removal of the `RMXGREP_MODE=plain` bypass never reached the live path.
`_wrapper()` now checks `<tree>/bin` first. The irony is recorded in the test file: bug-008's durable
fix made this resolve at RUNTIME so a dev-venv install could not bake its own checkout into a
user-global hook — and that fix's resolution ORDER picked the stale copy. {#bug-066-fix}

## The two that were what they said {#clear-cut}

**bug-063** — one line. `-F` was parsed, resolved into `regex=False` above the fork, then DROPPED in
the rg branch, which is regex-by-default. The grep branch always said `E if regex else F`; only the
rg branch had a default instead of reading the decision. Tested in BOTH directions, because "-F means
never match" would pass the inversion case alone. {#bug-063}

**bug-064** — `-l`/`-L` now have their own block BEFORE the empty-output branch, which got both of
their answers wrong: order (fan-out completion order instead of argument order) and exit status
(grep's status reflects whether a line was SELECTED, not whether filenames printed). A directory walk
keeps the tool's own order deliberately — re-sorting a walk would invent an order grep does not
promise either. **A third inversion the row never named**, found by reading the path rather than the
report: `-L alpha a.txt` with every file matching prints NOTHING and grep exits 0, while the old code
fell through and exited 1. The defect ran in both directions and only one was reported. {#bug-064}

## What the gates caught {#gates}

- **`test_the_fallback_renderer_exists_exactly_once` failed my first `-l`/`-L` cut**, because it
  pasted a second copy of the provenance banner. That guard exists because `_grep_run` once carried
  an inlined duplicate of the whole fallback and bug-058 was then fixed in one copy and missed in the
  other. There is now one `_banner()` emitter. The guard did exactly its job, to me.
- **The mutation check: 9 mutants, 5 survivors on the first pass, every one a test that could not
  observe its branch.** A pipe test cannot see regular-file support; a PATH-based fixture resolved
  the wrapper through the PATH branch instead of the sibling branch it was about; no test had a tty.
  Added a `< file` redirect case, an empty-redirect case, a real-pty case, and isolated the fallback
  fixture. All load-bearing after.
- **The last survivor was not a test gap.** Deleting an `isatty()` pre-check changed no behaviour,
  including under a real pty, because a terminal IS a character device and the mode test already
  covers it. The dead branch was removed rather than kept untestable.
- **A control taken through a shell is contaminated here.** Twice this session a "control" ran
  `/usr/bin/grep` inside a Bash tool command and the rewrite hook rewrote it, so the control WAS the
  thing under test. Every control in these tests is a direct `subprocess` exec, no shell.

## Verification {#verification}

| gate | result |
|---|---|
| RED first | `pytest-bug063-064-RED.log` (6 failed), `pytest-bug062-RED.log` (2 failed), `pytest-bug066-RED.log` (2 failed) |
| grep family | 181 passed |
| full suite | **2348 passed, 4 failed** — 3 pre-existing (bug-069), 1 the hook-install drift this deploy clears |
| mutations | 9 of 9 load-bearing after the coverage fixes |
| GMD lint | 0 errors |

Open, deliberately: bug-070 (the precision cost of bug-067's canonical predicate — tightening it
gives back the ingest-side gain, so it needs both numbers and a decision), bug-069 (three
federation/locate failures, logged undiagnosed so the next run does not re-attribute them), bug-065
(save-state writes memory rows `memory recall` cannot see). {#open}
