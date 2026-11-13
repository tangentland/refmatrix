---
gmd: "0.1"
id: task-10.3-plan-10-injection-dedup
title: "Task 10.3: the compaction marker (19.6 R8a's writer, built ahead of 19.6) — PreCompact and SessionStart compact|clear write it; it is the only reset of 10.2's held set"
tags: [task, plan-10, hooks, stm, compaction, versioned-injection]
metadata:
  node_type: task
  status: pending
  plan: plan-10-injection-dedup
  created: 2026-09-15
  updated: 2026-11-13
---

# Task 10.3: the compaction marker {#root}

> Plan: [[plan-10-injection-dedup]]
> Status: Pending (rewritten 2026-11-13; unchanged in substance by Q13; revision round 6
> 2026-11-13, [[#rev-round-6]]; ch-bsd spec review next)
> Depends on: nothing beyond `master`. It is the ONLY plan-10 task that builds early (L30). It
> follows the revival merge in queue item 4 and lands before 25.1b and 25.3, which read its
> marker. The rest of plan-10 builds after T4.
> **Install: user-gated, for the PreCompact entry only.** R1's NEW PreCompact entry
> (`--event compact-marker`) regenerates the hook config, so it reaches live stores only through
> an `install-hooks` window. It rides 25.1b's user-gated window in queue item 4, batched per C11
> (bsd-spec-t3ab S7; in G31). The `session-start` dispatch on `compact` / `clear` needs no window:
> it rides TODAY's installed SessionStart focus entry, whose matcher already covers both. So once
> 10.3 deploys, markers are written live on SessionStart `compact` / `clear`, and only the
> PreCompact-side marker waits for the window (r2 m4). Every reader handles that safely:
> - 10.2 is not built yet;
> - 25.1b ships in the same window;
> - 25.3 R7's helix reset only sees its reset happen sooner, which is the safe direction.
> Builds: [[task-19.6-phased-context-and-topic-cache]] R8a's writer, as 19.6 names it. Its readers
> are listed in R2.

rel: part-of -> [[plan-10-injection-dedup]]
rel: realizes -> [[task-19.6-phased-context-and-topic-cache]]
rel: implements -> [[exploration-session-phased-context#vi-compaction]]
rel: related-to -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[impression_bsd_guard_cannot_fire]]
rel: depends-on -> [[impression_bsd_tests_bypass_wiring]]

## Why {#why}

10.2's names-only dedupe treats an item as held only if it was delivered in full after the
session's last compaction marker, and the marker is its ONLY reset (10.2 h3). 19.6 R8a defines
"in the window" by the same marker for its own blocks later. One writer, built once. {#why-lead}

Two signals, because neither is trustworthy alone. 25.1's R0 probe (branch
`task-25.1-recall-hook-byte-budget`, `workflow/measurements/hook-output-cap-probe.md`) observed
`/compact` firing PreCompact (`trigger=manual`) and then SessionStart with `source=compact`, and
found PreCompact output reaching the compaction summary: that answers 19.6 R8's first question for
the manual path. rmx already runs a command on each event: PreCompact `rmx focus summarize
--promote`, the recall and the save-state checkpoint; SessionStart `rmx focus hook --event
session-start` (matcher `startup|resume|clear|compact`, `hooks.py:255-258`, 21.1 D4).

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| f1 | Build 19.6 R8a exactly as named: `rmx focus hook --event compact-marker` as its OWN PreCompact entry, and the dispatch inside `--event session-start` on `source=compact`; plus `source=clear` | one marker for plan-10 and 19.6; `/clear` empties the window as compaction does, so nothing may count as held after it (a new session id after `/clear` gives that already; the marker makes it independent of that) |
| f2 | The marker lives at `stm/<session>.emitted/marker.json` (`{schema: 1, ts, source, writer}`), beside 10.2's per-channel held files | 19.6 R8a says the marker is written into the session's last-emitted state; one directory per session, one writer per file, atomic replace, no read-modify-write between the concurrent hooks |
| f3 | The writer is the STM focus hook, not 25.1 R11's `recall-state` entry | `recall-state` is a reader (the handoff); the focus hook already parses the SessionStart envelope's `source` and owns STM session state |
| f4 | `resume` and `startup` write no marker | `startup` starts a new session (no state); `resume` reloads the transcript, so what was emitted is in the window again |
| f5 | A failed marker write exits non-zero with ONE `Error:` line on stderr; the readers treat an UNREADABLE marker file as "marker now" (nothing held) | a missed reset is the unsafe direction, so a read failure resets; a write failure is loud (loud-failure rule, 2026-11-10) |

## Requirements {#requirements}

1. **R1 The writer.** `stm.mark_compaction(root, session, *, source) -> dict` writes
   `stm/<session>.emitted/marker.json` by temp-file + replace (one write path), creating the
   directory. Called by: {#r1}
   - `rmx focus hook --event compact-marker` (a new `--event` choice), generated as its OWN
     PreCompact entry, not chained into the summarize / recall / save-state commands, and present
     whether or not the PreCompact recall entry is generated (25.1 R7 may drop it);
   - `rmx focus hook --event session-start` when the envelope's `source` is `compact` or `clear`
     (today's entry; its matcher already covers both).
2. **R2 The reader.** `stm.last_marker(root, session) -> Marker | None`: None when the file does
   not exist; `Marker(ts=now, source="unreadable")` plus one stderr line when it exists but cannot
   be read or parsed (f5). Every reader calls this function, and nothing opens the file directly.
   The readers are: 10.2's `held_items`; 10.4 R4's curator change-only check; 10.6 R3's composite
   rev; 25.1b R14's spill page (a page older than the marker is gone); 25.3 R7's helix
   once-per-session reset (L16); and, later, 19.6's "in the window". The writer deletes nothing.
   Each reader decides what the marker resets in its own state. {#r2}
3. **R3 Nothing else moves.** The marker is not a ring event and not a focus-graph field: the ring,
   `focus.json`, the topic cache, `pre.json` and the STM turn are untouched by it (19.6 R3's "one
   writer, one home" for the cache stays true). {#r3}
4. **R4 Failure surface.** `mark_compaction` failing → exit non-zero, one `Error: compaction marker
   not written: …` line on stderr, no traceback; in the session-start entry the existing pointer
   write and surfacing run first and still print. {#r4}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox through the GENERATED hook config (`hooks._claude_hook_block(...)`, the entry
under test run with `bash -c`, the envelope on stdin, the sandbox `HOME`). A test that calls
`mark_compaction` directly does not show the hook is wired ([[impression_bsd_tests_bypass_wiring]]);
such tests exist only in addition. {#acceptance-lead}

1. **AC-1 Generated config.** PreCompact holds exactly one entry whose command is `rmx focus hook
   --event compact-marker`, in its own entry, with and without the PreCompact recall entry; the
   SessionStart focus entry is unchanged; `rmx install-hooks --check` is clean after `--apply`.
2. **AC-2 PreCompact writes it.** After the generated PreCompact marker entry runs,
   `stm.last_marker` returns `source="precompact"` with a ts inside the run.
3. **AC-3 SessionStart writes it on compact and clear only.** The generated SessionStart focus
   entry with `{"source": "compact"}` and with `{"source": "clear"}` writes the marker; with
   `resume` and `startup` the file is unchanged (absent, or its old ts).
4. **AC-4 Nothing else moves.** The ring, `focus.json` and the graph `turn` are byte-identical
   before and after AC-2 and AC-3.
5. **AC-5 Read failure resets, write failure is loud.** A marker file holding `{` → `last_marker`
   returns `source="unreadable"` and a stderr line; an unwritable `.emitted` directory → the
   generated entry exits non-zero with one `Error:` line and no `Traceback`.
6. **AC-6 Mutations that must FAIL a test:** the PreCompact marker ENTRY removed from the generator
   (the call site, not the function: AC-1, AC-2); the marker chained into the summarize command
   (AC-1); the session-start dispatch dropped (AC-3 compact); `clear` left out (AC-3 clear);
   `resume` writing a marker (AC-3); the marker written as a ring event (AC-4); an unreadable file
   read as "no marker" (AC-5); a traceback on failure (AC-5).

## Files to modify {#files}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `mark_compaction`, `last_marker`, `Marker`; the `.emitted` directory path helper (10.2 reuses it) |
| `src/refmatrix/cli.py` (`focus hook`) | `--event compact-marker`; the `session-start` dispatch on `compact` / `clear`; R4's error line |
| `src/refmatrix/hooks.py` | the PreCompact `compact-marker` entry, independent of the recall flag |
| `.claude/settings.json`, `.claude/rmx-hooks.json` | regenerated by calling the generator from Python in the task's clone (never `rmx install-hooks` against a live store) |
| `tests/test_task10_3_compaction_marker.py` (new) | AC-1..AC-6 |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-2, AC-3, AC-5 at `master`, recorded.
- No mock of the generator, the focus hook or STM; the generated entries run as bash commands.
- The call-site mutation edits `hooks.py`, not `stm.py`.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation table in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-10.3-plan-10-injection-dedup.md`.
- Committed on branch `task-10.3-plan-10-injection-dedup`; merged `--no-ff` to `master`.
- Installed fleet-wide only in 25.1b's user-gated `install-hooks` window (C11), never by this
  task alone. `rmx install-hooks --check` runs clean in the sandbox after `--apply` (AC-1).

## Revision round 6 (2026-11-13, spec wave, spec-t3b) {#rev-round-6}

Driven by G11 and L15, L16 and L30 ([[plan-review-2026-11-13#lead]]), and by contra-b CB-5 and
CB-6. 10.3 is the only plan-10 task that builds early (queue item 4), because 25.1b (its spill
page "removed at compaction") and 25.3 R7 (the helix reset, L16) read its marker. R2 used to say
that only 10.2 and 19.6 read the file, while 10.4 R4 and 10.6 R3 already read it in rev 5. R2 now
lists every reader, and each reads through `stm.last_marker`. Nothing in the writer changes.

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: motivates -> [[task-25.1b-hook-output-ladder-and-spill]]
rel: motivates -> [[task-25.3-stm-ref-admission-and-helix-repeat#r7]]

**bsd-spec-t3ab r1 folded (2026-11-13, lead ruling S7).** The install is user-gated and rides
25.1b's window in queue item 4, recorded in the header and the DoD. {#rev-round-6-bsd}

rel: derives-from -> [[bsd-spec-t3ab-ff1d453-369e0b5]]

**bsd-spec-t3ab r2 m4 folded (2026-11-13).** The install note is corrected: SessionStart
`compact` / `clear` markers are written live after deploy through today's entry, and only the new
PreCompact entry waits for the window. 25.3 R7 is named among the readers. {#rev-round-6-bsd-r2}
