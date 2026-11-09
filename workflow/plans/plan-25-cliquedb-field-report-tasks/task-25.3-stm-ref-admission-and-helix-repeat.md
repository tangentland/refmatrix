---
gmd: "0.1"
id: task-25.3-stm-ref-admission-and-helix-repeat
title: "Task 25.3: one ref-admission predicate at both STM extraction sites, the rebuild and the composite render; helix says a stale line once per session, never annotates a hub neighbour, and logs every suppression so the phase-2 instrument keeps its reading (bug-166; builds task 19.0 R1)"
tags: [task, plan-25, bug-166, stm, focus, composite, helix, token-gate, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-09
---

# Task 25.3: STM ref admission and the helix repeat {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08; revision rounds 1-2 2026-11-09, [[#rev-round-1]],
> [[#rev-round-2]])
> Bug: bug-166 (cliquedb priority 4), both halves: junk topic members AND the stale helix line
> "whatever the topic".
> Depends on: [[task-25.2-thin-prompt-gate]] merged for the helix half (its ACs need prompts that
> pass the gate). The STM half (R1-R5) has no dependency and may be built first in its own clone.
> Task 3.7 merged.
> Builds: [[task-19.0-stm-cluster-hygiene]] R1 (`stm.command_refs` and the code-noise set), with
> the extensions in [[#beyond-19-0]].

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.2-thin-prompt-gate]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: realizes -> [[task-19.0-stm-cluster-hygiene#requirements]]
rel: amends -> [[task-19.0-stm-cluster-hygiene]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r1-2f4a1df]]
rel: derives-from -> [[bsd-plan25-spec-r2-5b8ed15]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[project_helix_phase2_decision_criterion]]
rel: related-to -> [[project_helix_log_confounded]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]

## Why {#why}

### (a) Shell fragments become topic members {#why-refs}

cliquedb's composite listed `S/as.sh`, `s.repla`, `s.count`, `cliquedb.pk`, `pk8a.kitem` as topic
members. Refs enter the focus graph at two extraction sites and survive at a third (read at
`fbee6c9`):

- **Tool path.** `cli._tool_event_fields` (`cli.py:1992-2031`) runs `stm._PATH_RE.findall(cmd)`
  over the WHOLE Bash command when the tool input names no `file_path` (`cli.py:2012`).
  `_PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}` (`stm.py:55`) has no right boundary, so `s.replace(`
  matches as `s.repla`, `re.search(` as `re.searc`, `docs/notes.md5sum` as `docs/notes.md`;
  `sed -i 's/as.sh/x/'` yields `s/as.sh`. Heredoc and `-c` bodies are not excluded (19.0's bug-104
  finding: 58 of 416 tool events in one ring).
- **Prose path.** `Stm.record` calls `_extract_refs(terse)` (`stm.py:1180`, defined `:2006`) when
  the caller passes no refs (input, say and reason events). It runs `_PATH_RE` plus `_IDENT_RE`
  (`stm.py:54`) filtered by `_STOP`. `_PATH_RE`'s only users are `stm.py:2008` and `cli.py:2012`.
- **Replay and render.** `Stm.rebuild_focus` (`stm.py:1430`) replays STORED refs filtered only by
  `is_junk_ref` (`stm.py:92`), and the composite applies the same gate at render.

`_extract_refs` has one more caller: `stm.pre_prompt_state`'s `overlap` field (`stm.py:1815`),
which 21.1 writes on its telemetry rows. Changing extraction moves that instrument ([[#r3]]).

### (b) The same helix line on every prompt, whatever the topic {#why-helix}

`helix.annotate` (`helix.py:307-345`) emits `[helix] last worked <date> (<n>d ago …)` whenever a
retrieved name's newest touch outside the current session is older than the window (3 days).
Two causes, both measured on cliquedb's `helix.log` ([[bsd-plan25-spec-r1-2f4a1df#probes]],
counts only):

- **No memory of having said it.** 230 rendered rows over 132 distinct (concept, touch) keys.
  refmatrix: 1,834 rows over 704 keys, top key 134 rows.
- **A hub neighbour.** One NEIGHBOR-role key is 59 of cliquedb's 230 rows; neighbor-role rows are
  170 of 230. The neighbor sweep (`context._helix_neighbor_sweep`, `context.py:1008-1035`)
  annotates graph neighbours of whatever was retrieved, and a document linked to almost
  everything is a neighbour of almost every prompt. Dedupe makes that line rarer; only a hub rule
  makes it stop being irrelevant ([[bsd-plan25-spec-r1-2f4a1df#s7]]).

The current session is guessed: `helix._current_session` reads `$RMX_SESSION` (not exported by
`HOOK_ENV`) and falls back to the newest ring (bug-100). helix.log is also an INSTRUMENT: the
pre-registered phase-2 criterion ([[project_helix_phase2_decision_criterion]], not yet applied)
counts `rendered: true` rows per session (≥ 2 / < 0.5 thresholds) and a ≥ 25% neighbor share.
Per-touch dedupe alone would cut cliquedb's rendered rows by up to 43% and refmatrix's by 62% and
shift the role share: the [[project_helix_log_confounded]] shape, decided by a spec rather than
pre-registered. So every suppression is logged and the criterion reads rendered + suppressed
([[#r8]]).

## Beyond 19.0 R1 {#beyond-19-0}

| 19.0 R1 says | here, additionally | why |
|---|---|---|
| `command_refs(cmd)` for the tool path | `command_refs(cmd, *, root=None, cwd=None)`; with `root=None` it is SHAPE-ONLY (no existence checks), which is what 19.0's rebuild re-extraction must call | replay must not check existence ([[#r5]]) |
| heredoc + `-c` / `-e` bodies are body | plus sed / perl substitution expressions and text inside quoted shell strings | `s/as.sh` |
| stdlib heads, ≤ 2-char locals dropped | plus a right boundary on `_PATH_RE` (no match ending inside a word or before `(`) | `s.repla`, `re.searc`, `docs/notes.md` out of `docs/notes.md5sum` are truncations by the regex itself |
| (none) | a PATH-SHAPED candidate (from `_PATH_RE`, with or without `/`) is admitted only if it exists under the project root or the event's cwd, when the root is known | `S/as.sh`, `cliquedb.pk`; keeps `pyproject.toml`, `query.log` |
| (none) | the prose path uses the same predicate | junk need not come from a Bash command |
| rebuild re-extracts from `detail` | not here: rebuild and render FILTER stored refs shape-only; re-extraction stays 19.0's, calling `command_refs(detail)` with `root=None` | the filter fixes the visible composite now |

## Requirements {#requirements}

### STM ref admission {#req-stm}

1. **R1 One predicate, two tiers.** In `stm.py`:
   - **Head, defined:** for a ref containing no `/`, its head is the leading identifier, the
     characters before its first `.` (`s.count` → `s`, `json.loads` → `json`, `refmatrix.stm` →
     `refmatrix`). A ref containing `/` has no head and is never subject to the head rules (its
     admission is the existence check). So `S/as.sh` cannot be dropped by a head rule, whichever
     segment an implementer looks at.
   - `is_code_noise(ref) -> bool`: SHAPE rules, no I/O: a slashless dotted ref whose head is ≤ 2
     chars; a slashless dotted ref whose head is in `CODE_NOISE_HEADS` (stdlib modules, 19.0 R1's set, documented
     next to `_STOP`, applied in addition to the shared stoplist); a sed / perl substitution shape
     (`^[sy]([/|#,:]).+\1`); an ALL-CAPS token of ≤ 5 chars that is a heredoc delimiter in the
     same text (`<<-?['"]?TOKEN`).
   - `admit_ref(ref, *, kind, root=None, cwd=None) -> bool`, `kind ∈ {"path", "ident"}`:
     `not is_junk_ref(ref) and not is_code_noise(ref)`, and for `kind="path"` with a known `root`,
     the path exists relative to `cwd`, to the project root (`root.parent`), or absolutely under
     the project root. At most 12 `stat` calls per event. Identifier candidates (`_IDENT_RE`:
     `refmatrix.stm`, `scan.scan_prompt`, `cliquedb.pk` in prose) take no existence check. {#r1}
2. **R2 The tool path** (19.0 R1). `stm.command_refs(cmd, *, root=None, cwd=None) -> list[str]`
   extracts path candidates from the command line only: not from a heredoc body (`<<EOF … EOF`,
   `<<'EOF'`, `<<-EOF`; unterminated → to end of string), not from an inline script argument
   (`python3 -c`, `bash -c`, `node -e`, `perl -e` / `-pe`; unterminated quote → to end of string),
   not from inside a quoted string EXCEPT a quoted token that `admit_ref` accepts as an existing
   path. Every candidate passes `admit_ref(kind="path")`. `cli._tool_event_fields` calls it in
   place of `_PATH_RE.findall(cmd)` for both the PreToolUse park and the PostToolUse record. {#r2}
3. **R3 The prose path.** `_extract_refs(text, *, root=None, cwd=None)` passes path candidates
   through `admit_ref(kind="path")` and identifier candidates through `admit_ref(kind="ident")`.
   `Stm.record` passes its store root. **Instrument shift, named:** `pre_prompt_state`'s `overlap`
   (`stm.py:1815`, a 21.1 telemetry field) uses the same function; its value can fall on prompts
   that quoted junk. The fixture's `overlap` is recorded before and after, and the 21.1 field
   description gains a dated note. {#r3}
4. **R4 The regex boundary.** `_PATH_RE` becomes `[\w./-]+\.[A-Za-z]{1,5}(?![\w(])`. Its users
   are `stm.py:2008` (`_extract_refs`) and `cli.py:2012` (replaced by `command_refs`); none other
   at `fbee6c9`, re-checked at RED time. {#r4}
5. **R5 Replay and render.** `Stm.rebuild_focus` and the composite's render-time gate drop refs
   for which `is_junk_ref(r) or is_code_noise(r)` holds, counting them in the existing
   `dropped_refs` stat. No existence check on replay (a ref that existed when recorded is
   history). {#r5}

### Helix: relevant, said once, counted {#req-helix}

6. **R6 An explicit session.** `helix.annotate(..., session: str | None = None)` and
   `helix.flush(root, rows, *, session=None)`. scan-prompt passes the session it already resolves
   for its telemetry row (`telemetry.resolve_event_session(root, envelope)`, `cli.py:9424`), so
   there is one resolution per call. With `session=None` (no envelope session; manual
   `rmx context`) there is no sidecar and no repeat suppression, and the row carries
   `cur_session: null`; the newest-ring fallback is never used for suppression. {#r6}
7. **R7 The repeat memory.** A per-session sidecar `.refmatrix/stm/<session>.helix.json` (the
   existing `<session>.<kind>.json` pattern; not `*.jsonl`, so `_ring_files` and `stm.py:1059`
   never read it as a ring) holds the keys already RENDERED this session: key = (normalised
   concept, touch ring_stem, touch line_no). A key is marked at `flush` only (a note built for a
   bundle that does not render never suppresses the next one). Written atomically (tmp + rename).
   A NEWER stale touch of the same concept is a new key and renders. A sidecar read or write
   failure lets the note render and is recorded ON THE ROW (`sidecar_error: "<ExcType>"`) and in
   the scan-prompt `query.log` row, because the hook's stderr is discarded
   (`hooks.py:249`, `2>/dev/null || true`). {#r7}
8. **R8 Hub neighbours are not annotated.** In `_helix_neighbor_sweep`, a neighbour whose link
   degree (count of `entity_links` rows naming it, the measure `scan._concept_signal` uses for
   concepts, extended to the neighbour's entity id) is above the p99 of that count is not
   annotated. **Population: all linked entities of every kind in the store's catalog** (not docs
   only, not per partition), computed once per store stamp and cached in `helix_index.json` beside
   the touch index. Anchor-role notes are unaffected. Measured on a copy of cliquedb's read
   catalog ([[bsd-plan25-spec-r2-5b8ed15#probes]]): 21,918 linked entities, p99 = 280, p99.9 = 736,
   220 entities above p99; the hub `docs/adr32-35_chat_history.md` has 2,331 links, so p99 catches
   it. The constant's comment records the threshold, the population size and the count above it,
   and the implementation summary re-records them for refmatrix and cliquedb at GREEN. {#r8}
9. **R9 Every suppression is a row; the criterion reads rendered + suppressed.** A suppressed note
   (repeat or hub) is not returned; its row goes through the same deferred sink and `flush` writes
   it as `{..., "rendered": false, "suppressed": "session-repeat" | "hub-neighbor"}`, only when the
   bundle it belonged to rendered. **A suppressed note counts toward `_HELIX_NEIGHBOR_NOTES` (5)
   and `_HELIX_NEIGHBOR_SCAN` (20)** (`context.py:91-92`) exactly as a rendered note does, so the
   sweep stops where HEAD stopped and never renders a sixth stale neighbour HEAD capped out. Every
   row gains `cur_session`. A `rendered: true` row keeps its
   meaning. So, over any window, `rendered` + `suppressed` = what HEAD would have logged for the
   same prompts. **The phase-2 criterion reads `rendered + suppressed`** until a new
   pre-registered criterion supersedes [[project_helix_phase2_decision_criterion]]; `rendered`
   alone is reported beside it. When this task merges, a memory that AMENDS the criterion memory
   records that reading (written at merge, not now). {#r9}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on a fixture project (files `src/pkg/stm_like.py`, `docs/notes.md`,
`pyproject.toml`, and the 25.1 fixture store), through the GENERATED hook commands from
`hooks._claude_hook_block(...)` with `bash -c` and a synthetic envelope on stdin. Refs are read
from the ring file the hook wrote, never from a helper. {#acceptance-lead}

1. **AC-1 Tool path.** The generated PostToolUse `focus hook --event tool` command, fed a Bash
   envelope whose command is `sed -i 's/as.sh/x/' docs/notes.md && python3 -c "s.replace(a,b);
   s.count(x); import re; re.search(p, t); print(cliquedb.pk, pk8a.kitem)" && cat <<'EOF' >
   /dev/null\nx.pk = 1\nEOF`, stores refs that include `docs/notes.md` and none of `s/as.sh`,
   `s.repla`, `s.count`, `re.searc`, `cliquedb.pk`, `pk8a.kitem`, `x.pk`, `EOF` (RED: at HEAD the
   stored refs include at least `s/as.sh`, `s.repla`, `s.count`).
2. **AC-1b Boundary witness.** The same command, fed `md5 docs/notes.md5sum` (unquoted, on the
   command line, the fixture has no `docs/notes.md5sum`), stores NO ref. At HEAD the old regex
   yields `docs/notes.md`, an existing path that every other rule keeps: only the R4 boundary
   drops it, so the boundary mutation fails here and nowhere else.
3. **AC-2 Prose path and the existence witness.** The generated `focus hook --event input` command
   with the prompt `"x.pk = 1 fails after s.count(x); see S/as.sh, pyproject.toml,
   src/pkg/stm_like.py and memory_recall, then cat <<EOF"` records refs including
   `src/pkg/stm_like.py`, `pyproject.toml` and `memory_recall`, and none of `x.pk`, `s.count`,
   `S/as.sh`, `EOF` (RED at HEAD). `S/as.sh` is path-shaped, contains `/` (so no head rule applies,
   R1) and is unquoted: only the existence check drops it, so it is the existence-check witness. Recorded,
   not gated: `cliquedb.pk` in PROSE is an identifier candidate and is kept; cliquedb's instances
   came from command text, which AC-1 covers.
4. **AC-3 Existing rings.** A synthetic ring written in HEAD's format with the AC-1 junk in its
   stored refs: the composite rendered by the generated scan-prompt command (composite on, a
   prompt that passes 25.2's gate) lists none of the junk, and `rmx focus rebuild` reports them in
   `dropped_refs` (RED at HEAD).
5. **AC-4 Not over-filtered.** Kept: `src/pkg/stm_like.py`, `docs/notes.md`, `pyproject.toml`, a
   quoted existing path `'docs/notes.md'` (tool path); `refmatrix.stm`, `scan.scan_prompt`,
   `stm_like.py` (prose, identifier candidates). Dropped: `s.module` (≤ 2-char head), `json.loads`
   (stdlib head), a path inside a heredoc body even when it exists. A table over `admit_ref` /
   `command_refs`, plus the five load-bearing rows through the AC-1 command.
6. **AC-5 `overlap` shift recorded.** On the fixture's pre-prompt state with a prompt that quotes
   junk, `pre_prompt_state`'s `overlap` is recorded at HEAD and after (a measurement, not a gate).
7. **AC-6 Helix once.** Two prompts in one session, both passing the gate and both retrieving a
   fixture concept whose only touch is a 10-day-old ring of another session (anchor role): at HEAD
   the generated scan-prompt command prints the `[helix]` line both times (RED); after, the first
   prints it and the second does not.
8. **AC-7 Per session, per touch.** A third prompt from a NEW session prints it again; a newer
   stale touch of the same concept prints it again in the original session; a different stale
   concept prints in the original session.
9. **AC-8 Built-not-rendered.** A bundle that builds a helix note and is dropped before render
   (the existing anchor-less drop) does not mark the key: the next rendering prompt prints it.
10. **AC-9 Hub neighbour.** The fixture holds a hub document linked to every concept (degree above
    p99) with a 10-day-old touch. Three prompts on three unrelated topics: at HEAD each prints a
    neighbor-role `[helix]` line for the hub (RED); after, none does, and helix.log has three
    `suppressed: "hub-neighbor"` rows. A non-hub stale neighbour of one prompt still renders.
11. **AC-10 Instrument continuity.** The fixture gives one prompt SEVEN stale neighbours, the
    hub among them. After AC-6 and AC-9, for each concept, `rendered: true` + `suppressed` rows
    equal HEAD's `rendered: true` count for the same prompts, and the per-prompt neighbour-role
    total stays ≤ 5 (no sixth neighbour rendered because one was suppressed); every row carries
    `cur_session`.
12. **AC-11 Session from the envelope.** With two sessions' rings present and the OTHER session's
    ring newer, the sidecar written is `<envelope session>.helix.json`. With no envelope session,
    no sidecar is written, nothing is suppressed as a repeat, and rows carry `cur_session: null`.
13. **AC-12 Sidecar failure is on the row.** With the sidecar path made unwritable (a directory of
    that name), the note renders and the helix.log row and the scan-prompt `query.log` row carry
    `sidecar_error`.
14. **AC-13 Mutations that must FAIL a test:** remove the `_PATH_RE` boundary (AC-1b only); drop
    the existence check (AC-2 `S/as.sh`); extract from heredoc bodies (AC-4); keep
    `_PATH_RE.findall` at `_tool_event_fields` (AC-1); skip the render-time filter (AC-3); mark the
    helix key at annotate instead of flush (AC-8); drop a suppressed row (AC-10); key by concept
    only (AC-7 newer touch); disable the hub rule (AC-9); fall back to the newest ring for the
    sidecar (AC-11); print the sidecar error to stderr only (AC-12); suppressed notes not counted
    toward the neighbour cap (AC-10: a sixth neighbour renders); the head rule applied to a slashed
    ref (AC-2: `S/as.sh` dropped without the existence check).

## Measurement {#measurement}

- Junk refs per 100 tool events: a synthetic 200-event ring shaped like 19.0's bug-104 replay
  (committed), HEAD vs GREEN; after deploy, on cliquedb's current ring read-only (counts only).
- Helix rows per 10 prompts in one session on the fixture, by role and by outcome (rendered,
  session-repeat, hub-neighbor), HEAD vs GREEN; after deploy, cliquedb's helix.log counts by key
  and role against the 230 / 132 / 59 baseline. Bytes saved per prompt appended to
  `workflow/measurements/plan-25-hook-bytes.md`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `_PATH_RE` boundary; `CODE_NOISE_HEADS`; `is_code_noise`, `admit_ref`, `command_refs`; `_extract_refs` filter; `rebuild_focus` filter |
| `src/refmatrix/composite.py` | render-time gate adds `is_code_noise` |
| `src/refmatrix/cli.py` (`_tool_event_fields`, `:2012`; `scan_prompt_cmd`, `:9424`) | `stm.command_refs(cmd, root=, cwd=)`; pass the resolved session to scan |
| `src/refmatrix/helix.py` | `session` params; sidecar repeat memory; suppressed rows; `cur_session`; `sidecar_error`; p99 degree in the index |
| `src/refmatrix/context.py` (`:218-222`, `_helix_neighbor_sweep` `:1008-1035`, `_helix_flush` `:1547`) | session through annotate / flush; hub rule in the neighbor sweep |
| `src/refmatrix/scan.py` | pass the session to `build_context` / helix |
| `src/refmatrix/telemetry.py` | `sidecar_error` on the scan-prompt row; dated note on `overlap` |
| `tests/test_task25_3_stm_refs_helix.py` (new) | AC-1..AC-13 |
| `workflow/bug_registry.md` | bug-166 → fixed at merge (both halves) |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-1b, AC-2, AC-3, AC-6, AC-9 at HEAD (after 25.2 merges for the helix ACs).
- No mock of `stm`, `helix`, `context` or the hook generator. Ring files and old touches are
  written with the timestamps the test needs; no clock patching inside the function under test.
- `stat`-cost check: AC-1's command run 50 times; p95 wall of the focus hook recorded before and
  after (a measurement, not a gate).

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| h1 | Repeat window | once per session per stale touch; a newer touch re-renders |
| h2 | Which count the phase-2 criterion reads | `rendered + suppressed` (= HEAD's reading) until a new pre-registered criterion supersedes it; `rendered` reported beside it ([[#r9]]) |
| h3 | The hub neighbour | fixed here (R8, AC-9), not parked; threshold p99, re-set from the measured cliquedb key if p99 misses it |
| h4 | Existence check | for every path-shaped candidate when the root is known, with or without `/`; identifiers never |

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan25-spec-r1-2f4a1df]] and the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| S5 boundary mutation unkillable; wrong existence witness | AC-1b adds `docs/notes.md5sum` on the command line (only the boundary drops `docs/notes.md`); `S/as.sh` in prose named as the existence-check witness; AC-13 rewritten | AC-1b, AC-2, AC-13 |
| S6 h2 changes the criterion's reading | the criterion reads `rendered + suppressed` until superseded; amend-memory to write at merge | [[#why-helix]], [[#r9]], h2 |
| S7 cause parked behind a bug row | hub-neighbour rule built here (R8): degree above the store's p99 is not annotated, logged `hub-neighbor`; AC-9; measured against cliquedb's 59-row key | [[#why-helix]], [[#r8]], AC-9, h3 |
| M4 wrong `_PATH_RE` users; unnamed instrument | users are `stm.py:2008` and `cli.py:2012`; `pre_prompt_state` `overlap` (`stm.py:1815`) named as an instrument shift and measured | [[#why-refs]], [[#r3]], [[#r4]], AC-5 |
| M5 "loud" on a discarded stderr | sidecar failure recorded on the helix.log and `query.log` rows | [[#r7]], AC-12 |
| M6 resolver purpose unstated | reuse the session `scan_prompt_cmd` resolves with `telemetry.resolve_event_session`; None → no sidecar, no suppression, `cur_session: null` | [[#r6]], AC-11 |
| M7 extension allow-list drops working files | allow-list removed; existence check applies to every path-shaped candidate (`pyproject.toml` kept, `cliquedb.pk` dropped) | [[#beyond-19-0]], [[#r1]], AC-2, AC-4 |
| M9 (19.0 half) | `command_refs(..., root=None)` is shape-only, the form 19.0's rebuild re-extraction calls; revision row added to 19.0 | [[#beyond-19-0]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan25-spec-r2-5b8ed15]] with the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| M5 rendered + suppressed ≠ HEAD under the neighbour cap | suppressed notes count toward `_HELIX_NEIGHBOR_NOTES` and `_HELIX_NEIGHBOR_SCAN`; AC-10's fixture has seven stale neighbours; mutation added | [[#r9]], AC-10, AC-13 |
| M6 p99 population unstated | all linked entities of every kind in the store's catalog; cliquedb measurement (21,918 / p99 280 / 220 above / hub 2,331) recorded; counts re-recorded at GREEN in every case | [[#r8]] |
| M7 "head" undefined | head = the leading identifier before the first `.`, for slashless refs only; slashed refs are never subject to head rules, so `S/as.sh` stays the existence witness | [[#r1]], AC-2, AC-13 |
