---
gmd: "0.1"
id: task-25.3-stm-ref-admission-and-helix-repeat
title: "Task 25.3: one ref-admission predicate at both STM extraction sites, the rebuild and the composite render; helix says a stale line once per session and counts what it suppressed (bug-166; builds task 19.0 R1)"
tags: [task, plan-25, bug-166, stm, focus, composite, helix, token-gate, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-08
---

# Task 25.3: STM ref admission and the helix repeat {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08)
> Bug: bug-166 (cliquedb priority 4)
> Depends on: [[task-25.2-thin-prompt-gate]] merged for the helix half (its ACs need prompts that
> pass the gate; a bare ack no longer reaches helix). The STM half (R1-R5) has no dependency and
> may be built first in its own clone. Task 3.7 merged.
> Builds: [[task-19.0-stm-cluster-hygiene]] R1 (`stm.command_refs` and the code-noise set), with
> the extensions in [[#beyond-19-0]].

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-25.2-thin-prompt-gate]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: realizes -> [[task-19.0-stm-cluster-hygiene#requirements]]
rel: amends -> [[task-19.0-stm-cluster-hygiene]]
rel: derives-from -> [[bug_registry#registry]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[project_helix_phase2_decision_criterion]]
rel: related-to -> [[project_helix_log_confounded]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]

## Why {#why}

### (a) Shell fragments become topic members {#why-refs}

cliquedb's composite listed `S/as.sh`, `s.repla`, `s.count`, `cliquedb.pk`, `pk8a.kitem` as topic
members. Three admission sites put refs into the focus graph, and the cause is visible at each
(read at `fbee6c9`):

- **Tool path.** `cli._tool_event_fields` (`cli.py:1992-2031`) runs `stm._PATH_RE.findall(cmd)`
  over the WHOLE Bash command when the tool input names no `file_path` (`cli.py:2012`).
  `_PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}` (`stm.py:55`) has no right boundary, so `s.replace(`
  matches as `s.repla`, `re.search(` as `re.searc`, `collections.Counter` as `collections.Count`;
  `sed -i 's/as.sh/x/'` yields `s/as.sh`; `x.pk = 1` yields `x.pk`. Heredoc and `-c` bodies are
  not excluded (19.0's bug-104 finding: 58 of 416 tool events in one ring).
- **Prose path.** `Stm.record` calls `_extract_refs(terse)` (`stm.py:1180`, defined `:2006`) when
  the caller passes no refs: input, say and reason events. It runs the same `_PATH_RE` plus
  `_IDENT_RE` (`stm.py:54`), filtered by `_STOP`, so a prompt or answer quoting code
  (`cliquedb.pk`, `pk8a.kitem`, a heredoc `EOF`) admits the same junk.
- **Replay and render.** `Stm.rebuild_focus` (`stm.py:1430`) replays STORED refs filtered only by
  `is_junk_ref` (`stm.py:92`: id prefixes, hex, uuids, deep absolute paths), and the composite
  applies the same gate at render. Neither sees these shapes, so existing rings keep the junk.

### (b) The same helix line on every prompt {#why-helix}

`helix.annotate` (`helix.py:307-345`) emits `[helix] last worked <date> (<n>d ago …)` whenever a
retrieved concept's newest touch outside the current session is older than the window (3 days).
Nothing remembers that this session was already told, so a concept that keeps being retrieved
(cliquedb: `docs/adr32-35_chat_history.md: last worked 2026-06-30 (131d ago)`) is re-annotated on
nearly every prompt, whatever the topic. The current session itself is guessed:
`helix._current_session` reads `$RMX_SESSION` (not exported by `HOOK_ENV`) and falls back to the
newest ring (`stm.latest_session`, bug-100's hazard). {#why-helix-lead}

helix.log is an instrument: the pre-registered phase-2 criterion
([[project_helix_phase2_decision_criterion]]) counts `rendered: true` rows per working session. A
dedupe that silently drops rows would change the instrument's reading without saying so, which is
the confound shape [[project_helix_log_confounded]] already recorded once.

## Beyond 19.0 R1 {#beyond-19-0}

| 19.0 R1 says | here, additionally | why |
|---|---|---|
| `command_refs` for the tool path | the prose path uses the same admission predicate | cliquedb's `cliquedb.pk` / `pk8a.kitem` / `EOF` need not come from a Bash command |
| heredoc + `-c` / `-e` bodies are body | plus sed / perl substitution expressions and text inside quoted shell strings | `s/as.sh` |
| stdlib heads, ≤ 2-char locals dropped | plus a right boundary on `_PATH_RE` (no match that ends inside a word or before `(`) | `s.repla`, `re.searc` are TRUNCATIONS by the regex itself |
| (none) | a slash ref is admitted only if it resolves to an existing path under the project root or the event's cwd; a PATH-SHAPED ref without a slash only if its extension is a known source / doc extension | `S/as.sh`, `cliquedb.pk`, `pk8a.kitem` |
| rebuild re-extracts from `detail` | not here: rebuild and render FILTER stored refs with the shape rules; re-extraction stays 19.0's | the filter fixes the visible composite now; re-extraction belongs with 19.0's fixture (R6) |

## Requirements {#requirements}

### STM ref admission {#req-stm}

1. **R1 One predicate, two tiers.** In `stm.py`:
   - `is_code_noise(ref, *, kind="ident") -> bool`: SHAPE rules, no I/O: a dotted ref whose head is ≤ 2 chars; a
     dotted ref whose head is in `CODE_NOISE_HEADS` (stdlib modules, 19.0 R1's set, documented
     next to `_STOP`, applied in addition to the shared stoplist); a sed / perl substitution shape
     (`^[sy]([/|#,:]).+\1`); an ALL-CAPS token of ≤ 5 chars that is a heredoc delimiter in the
     same text (`<<-?['"]?TOKEN`). For PATH-SHAPED candidates only (those produced by `_PATH_RE`),
     also: a ref without `/` whose final extension is not in `ingest.CODE_EXTS | ingest.DOC_EXTS`
     (the set `watch.SUPPORTED_EXTS` already unions). Identifier candidates (`_IDENT_RE`:
     `refmatrix.stm`, `scan.scan_prompt`) are not subject to the extension rule; the candidate's
     origin is passed as `kind="path" | "ident"`.
   - `admit_ref(ref, *, root, cwd=None) -> bool`: `not is_junk_ref(ref) and not is_code_noise(ref)`
     and, for a ref containing `/`, the path exists relative to `cwd`, to the project root
     (`root.parent`), or absolutely under the project root. At most 12 `stat` calls per event.
     {#r1}
2. **R2 The tool path** (19.0 R1). `stm.command_refs(cmd, *, root, cwd) -> list[str]`: extracts
   candidates from the command line only: not from a heredoc body (`<<EOF … EOF`, `<<'EOF'`,
   `<<-EOF`; unterminated → to end of string), not from an inline script argument (`python3 -c`,
   `bash -c`, `node -e`, `perl -e` / `-pe`; unterminated quote → to end of string), not from inside
   a quoted string EXCEPT a quoted token that `admit_ref` accepts as an existing path; every
   candidate passes `admit_ref`. `cli._tool_event_fields` calls it in place of
   `_PATH_RE.findall(cmd)` for both the PreToolUse park and the PostToolUse record. {#r2}
3. **R3 The prose path.** `_extract_refs(text, *, root=None, cwd=None)` filters its candidates
   through `admit_ref` when `root` is known (the `Stm` instance's store root) and through
   `is_junk_ref or is_code_noise` otherwise. {#r3}
4. **R4 The regex boundary.** `_PATH_RE` gains a right boundary so a match cannot end inside a
   word or immediately before `(`: `[\w./-]+\.[A-Za-z]{1,5}(?![\w(])`. Its other users
   (`_ref_kind`, the helix `_candidates`) are checked at RED time and listed in the summary. {#r4}
5. **R5 Replay and render.** `Stm.rebuild_focus` and the composite's render-time gate drop refs
   for which `is_junk_ref(r) or is_code_noise(r)` holds, counting them in the existing
   `dropped_refs` stat. No existence check on replay (a ref that existed when recorded is
   history). {#r5}

### Helix: said once per session {#req-helix}

6. **R6 An explicit session.** `helix.annotate(..., session: str | None = None)` and
   `helix.flush(root, rows, *, session=None)`. scan-prompt passes the session its envelope names,
   resolved through `verbs.resolve_session_source` (the one resolver; the 24.2a R2 shape);
   `_current_session` remains only for callers with no session (manual `rmx context`). {#r6}
7. **R7 The repeat memory.** A per-session sidecar `.refmatrix/stm/<session>.helix.json` (the
   existing `<session>.<kind>.json` pattern beside `.focus.json`, `.inflight.json`, `.pre.json`;
   not a `*.jsonl`, so `_ring_files` never reads it as a ring) holds the keys already RENDERED this
   session: key = `(normalised concept, touch ring_stem, touch line_no)`, i.e. the same stale
   touch. A key is marked at `flush` time only (a note built for a bundle that does not render
   never suppresses the next one). Written atomically (tmp + rename); a read or write failure
   prints one line on stderr and the note renders (fail open, loud). A NEWER stale touch of the
   same concept is a new key and renders. {#r7}
8. **R8 Counted, never silent, instrument intact.** A suppressed note is not returned; its row
   goes through the same deferred sink and `flush` writes it as `{..., "rendered": false,
   "suppressed": "session-repeat"}` only when the bundle it belonged to rendered. Every row (rendered or
   suppressed) gains `cur_session`. A `rendered: true` row keeps its exact meaning (an annotation
   that reached an output surface), so `rendered` + `suppressed` over a window equals what HEAD
   would have logged for the same prompts. {#r8}
9. **R9 Attribution, measured before GREEN.** From cliquedb's `helix.log` (read-only; counts per
   concept and role only, no text copied), record which role (`anchor` / `neighbor`) carried the
   repeated line and how many prompts it hit. If it is the neighbor sweep (`context.py:1008-1035`)
   annotating a high-degree hub, log a follow-up bug row; the hub question is not fixed here. {#r9}

## Acceptance criteria {#acceptance}

Run in 23.0's sandbox on a fixture project (files `src/pkg/stm_like.py`, `docs/notes.md`, and the
25.1 fixture store), through the GENERATED hook commands from `hooks._claude_hook_block(...)` run
with `bash -c` and a synthetic envelope on stdin. {#acceptance-lead}

1. **AC-1 Tool path.** The generated PostToolUse `focus hook --event tool` command, fed a Bash
   envelope whose command is `sed -i 's/as.sh/x/' docs/notes.md && python3 -c "s.replace(a,b);
   s.count(x); import re; re.search(p, t); print(cliquedb.pk, pk8a.kitem)" && cat <<'EOF' >
   /dev/null\nx.pk = 1\nEOF`, stores refs that include `docs/notes.md` and none of `s/as.sh`,
   `s.repla`, `s.count`, `re.searc`, `cliquedb.pk`, `pk8a.kitem`, `x.pk`, `EOF` (RED: at HEAD the
   stored refs include at least `s/as.sh`, `s.repla`, `s.count`). Read from the ring file the hook
   wrote, not from a helper.
2. **AC-2 Prose path.** The generated `focus hook --event input` command with the prompt
   `"x.pk = 1 fails after s.count(x); see S/as.sh, src/pkg/stm_like.py and memory_recall, then
   cat <<EOF"` records refs including `src/pkg/stm_like.py` and `memory_recall` and none of
   `x.pk`, `s.count`, `S/as.sh` (absent path), `EOF` (RED at HEAD). Recorded, not gated: a bare
   identifier like `cliquedb.pk` in PROSE is identifier-shaped and is kept; cliquedb's instances
   came from command text, which AC-1 covers.
3. **AC-3 Existing rings.** A synthetic ring written in HEAD's format with the AC-1 junk in its
   stored refs: the composite rendered by the generated scan-prompt command (composite on, a
   prompt that passes 25.2's gate) lists none of the junk as members, and `rmx focus rebuild`
   reports them in `dropped_refs` (RED at HEAD: the composite lists them).
4. **AC-4 Not over-filtered.** Kept: `src/pkg/stm_like.py`, `docs/notes.md`, `stm_like.py`
   (known extension), `refmatrix.stm` and `scan.scan_prompt` (identifier candidates), a quoted
   existing path `'docs/notes.md'`. Dropped: `s.module` (≤ 2-char head), `json.loads` (stdlib
   head), a path inside a heredoc body even when it exists (19.0 R1: body is body). A table test over `admit_ref` /
   `command_refs`, plus the same table through the AC-1 command for the five load-bearing rows.
5. **AC-5 Helix once.** Two prompts in the same session, both passing the gate and both retrieving
   a fixture concept whose only touch is a 10-day-old ring of another session: at HEAD the
   generated scan-prompt command prints the `[helix]` line both times (RED); after, the first
   prints it and the second does not.
6. **AC-6 Per session, per touch.** A third prompt from a NEW session prints it again; a new stale
   touch of the same concept (a second old ring, newer than the first) prints it again in the
   original session; a different stale concept prints in the original session.
7. **AC-7 Built-not-rendered.** A bundle that builds a helix note and is dropped before render
   (the existing anchor-less drop) does not mark the key: the next rendering prompt prints the line.
8. **AC-8 Instrument.** After AC-5, `helix.log` holds 1 `rendered: true` row and 1 `rendered:
   false, suppressed: "session-repeat"` row for the concept, both carrying `cur_session`; their
   sum equals HEAD's `rendered: true` count for the same two prompts (2).
9. **AC-9 Session from the envelope.** With two sessions' rings present and the OTHER session's
   ring newer, the repeat memory written is `<envelope session>.helix.json` (RED-able: at HEAD no
   sidecar exists; the mutation `session=None` writes the newest ring's sidecar and fails).
10. **AC-10 Mutations that must FAIL a test:** remove the `_PATH_RE` boundary (AC-1 `s.repla`);
    drop the existence check (AC-1 `s/as.sh`, AC-2 `cliquedb.pk`); extract from heredoc bodies
    (AC-4); keep `_PATH_RE.findall` at `_tool_event_fields` (AC-1); skip the render-time filter
    (AC-3); mark the helix key at annotate instead of flush (AC-7); drop the suppressed row
    (AC-8); key by concept only (AC-6 newer touch).

## Measurement {#measurement}

- Junk refs per 100 tool events: on a synthetic ring of 200 events shaped like 19.0's bug-104
  replay (committed, synthetic), HEAD vs GREEN; and, after deploy, on cliquedb's current ring
  read-only (counts only).
- Helix lines per 10 prompts in one session on the fixture: HEAD vs GREEN; bytes saved per prompt
  appended to `workflow/measurements/plan-25-hook-bytes.md`.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `_PATH_RE` boundary; `CODE_NOISE_HEADS`; `is_code_noise`, `admit_ref`, `command_refs`; `_extract_refs` filter; `rebuild_focus` filter |
| `src/refmatrix/composite.py` | render-time gate adds `is_code_noise` |
| `src/refmatrix/cli.py` (`_tool_event_fields`, `:2012`) | `stm.command_refs(cmd, root=, cwd=)` |
| `src/refmatrix/helix.py` | `session` params; sidecar repeat memory; suppressed rows; `cur_session` |
| `src/refmatrix/context.py` (`:218-222`, `:1008-1035`, `_helix_flush` `:1547`) | pass the session through to annotate / flush |
| `src/refmatrix/scan.py` | pass the envelope's resolved session to `build_context` / helix |
| `tests/test_task25_3_stm_refs_helix.py` (new) | AC-1..AC-10 |
| `workflow/bug_registry.md` | bug-166 → fixed at merge |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-2, AC-3, AC-5 at HEAD (after 25.2 merges for the helix ACs); recorded.
- No mock of `stm`, `helix`, `context` or the hook generator. Ring files and old touches are
  written as files with the timestamps the test needs (no clock patching inside the function under
  test; `helix.annotate`'s existing `now=` is not used by the hook path, so the fixture dates the
  ring instead).
- `stat`-cost check: AC-1's command run 50 times; p95 wall of the focus hook recorded before and
  after (a measurement, not a gate).

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| h1 | Repeat window: once per session, or once per N prompts | once per session per stale touch (R7); a long session that needs the reminder again gets it from a newer touch |
| h2 | Which count the phase-2 criterion reads after this lands | `rendered: true` (distinct readings), with `suppressed` reported beside it as the pre-dedupe bound; the decision memory that applies the criterion records both |
| h3 | Topic-relevance gating of neighbor-role notes | not here; R9 measures whether the repeat is a hub neighbor and files it |
| h4 | Existence check for slash refs on the prose path | yes when the root is known; a planned-but-absent path is the safe loss (under-admission) |
