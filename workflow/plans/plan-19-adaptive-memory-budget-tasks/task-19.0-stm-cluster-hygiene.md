---
gmd: "0.1"
id: task-19.0-stm-cluster-hygiene
title: "Task 19.0: STM topic clusters are built from the session's real threads, not from script bodies, subagents, hand-backs, typos or another session's ring"
tags: [task, stm, focus, topics, hygiene, plan-19, bug-100, bug-103, bug-104]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
---

# Task 19.0: STM cluster hygiene {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (the test sandbox, d1a/d1b) only. Scheduled no later than Wave 2 (d5e); in the
> Wave 1 order it runs once 23.0 is in ([[plan-review-2026-10-14#t8-wave1]]). Hard prerequisite of
> 19.6.

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: derives-from -> [[plan-review-2026-10-14#t5-stm-hygiene]]
rel: amends -> [[plan-review-2026-10-14#t8-amendments-body]]
rel: implements -> [[exploration-session-phased-context#prereq-stm-hygiene]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[feedback_causal_story_before_evidence]]
rel: specified-by -> [[bsd-decision-log-review-a192ba2#s-10]]
rel: specified-by -> [[bsd-decision-log-review-a192ba2#m-1]]
rel: derives-from -> [[plan-review-2026-10-14#t8]]

## Why {#why}

Phase detection and the topic cache (19.6) key on STM topic clusters. In session db80475a
(2026-10-14) those clusters were led by junk, read off the frozen ring (502 events: 416 tool,
27 input, 22 say, 21 git, 16 reason):

- **Script bodies (bug-104).** 68 tool events carried heredoc / `-c` scripts. `_extract_refs`
  (`stm.py:840`) reads the whole tool `detail`, so truncated locals and stdlib calls became
  concepts: `r.get` 32, `re.searc` 21, `collections.Count` 18, `glob.glob` 16, `json.loads` 13,
  `s.repla` 10, `m.group` 10. `is_junk_ref` (`stm.py:90`) gates ids, hex, uuids and deep paths
  only.
- **Subagent events (bug-103).** The background decision-log review's `sed`/`python3` calls landed
  in the parent's ring under the parent's session id; the composite's lead topic became
  `glob.glob, m.group, re.findi, re.searc`.
- **Hand-backs.** `is_ambient_text` (`stm.py:106`) drops `<channel`, `<task-notification`,
  `[SYSTEM NOTIFICATION`, but not `<agent-message` hand-back envelopes.
- **Typos.** Unmatched prompt tokens (`aggre`, `llok`) became cluster labels.
- **Another session's ring (bug-100).** `latest_session` (`stm.py:127`) resolves "the session" as
  the newest ring by mtime; scan-prompt's STM enrichment (`scan.py:535-537`) and the verb resolver
  (`verbs.py:528`) use it, so with two sessions on one project one session's prompt can be seeded
  with the other's focus. The topic cache is session-scoped, so 19.6 cannot ship on it.

{#why-body}

## Requirements {#requirements}

0. **R0 Probe the real envelope first** (decision-log review #s-10; d5e amendment; d8h).
   Before R2 is built, run one background subagent in a scratch project with the installed
   PostToolUse `focus hook` and record, in the implementation summary and this spec's revision
   table, every field of the subagent's PostToolUse envelope: does it carry an `agent_id`, a
   `transcript_path` distinct from the parent's, or any other subagent marker. The result decides
   whether R2's rung 1 is live; rungs 2 and 3 are built either way. The probe is a measurement,
   not a story ([[feedback_causal_story_before_evidence]]); bug-103's causal line is re-stated
   from it.
1. **R1 Script bodies are not focus** (bug-104). For a `tool` event, refs are extracted from the
   command line and the paths it names, never from a heredoc body (`<<EOF … EOF`, `<<'EOF'`) or
   an inline script argument (`python3 -c`, `bash -c`, `node -e`, `perl -e`). Dotted refs whose
   head is a stdlib module (`re`, `json`, `glob`, `collections`, `os`, `sys`, `pathlib`, …) or a
   local of ≤ 2 chars (`r.`, `s.`, `m.`) are dropped. The token gate reuses
   `scan._PROMPT_STOPWORDS` ([[feedback_reuse_shared_stoplist]]); the stdlib heads and short-local
   rule live in ONE separate, documented code-noise set next to it, not a second stoplist.
2. **R2 Subagent tool events are not the parent's focus** (bug-103; d8h). Every PostToolUse
   event is given an `origin` by this ladder, first rung that resolves wins:
   - **Rung 1, the envelope.** If R0 shows the envelope identifies the subagent (an `agent_id`,
     or a `transcript_path` under `<session-id>/subagents/agent-<agentId>.jsonl`), the event's
     origin is `agent:<agentId>`.
   - **Rung 2, the subagent transcripts.** Otherwise the hook looks in
     `<projects dir>/<project-slug>/<session-id>/subagents/`, where each subagent writes its own
     full transcript `agent-<agentId>.jsonl` (every tool call, with its input and a timestamp)
     and an `agent-<agentId>.meta.json` (`agentType`, `description`, `toolUseId`, `spawnDepth`,
     `requestShape`). The directory comes from the envelope's parent `transcript_path`
     (`<projects dir>/<slug>/<session-id>.jsonl`), else from `$HOME/.claude/projects/<slug>`.
     The event is attributed to agent X when exactly ONE `tool_use` entry, across that session's
     subagent transcripts, matches on all three of:
     - `tool_name`;
     - the input digest: sha256 of the tool input as canonical JSON (sorted keys, no
       whitespace);
     - timestamp within ± `W = 2 s` of the event.

     Its origin is then `agent:<agentId>`, and its label is `<agentType>: <description>` from
     the meta file. A missing or unreadable meta file leaves the label as `agent:<agentId>` and
     is counted. Two or more matching agents is not a match (rung 3).
   - **Rung 3, unattributed.** If no rung resolves while some subagent transcript of the session
     was written within the window, the event's origin is `unattributed`. It stays in the ring
     and may be a member, but is never a cluster label. If no subagent transcript was written
     within the window, the event is the parent's (`origin: parent`).

   The rest of R2:
   - **Effect.** Events with origin `agent:<id>` stay in the parent's ring for provenance, keyed
     `agent:<id>`, and are excluded from the parent's focus graph and composites.
     `rmx focus topics` renders each agent active in the window as ONE line,
     `background: <label>`, never as members of the parent's topics.
   - **Cost bound (inside the hook's latency budget).** Rung 2 opens only the
     `agent-*.jsonl` files whose mtime is ≥ event ts − W. It reads each from the end in 64 KB
     blocks, back to the first entry older than event ts − W, with a hard cap of 1 MB per event
     across all files. Hitting the cap ends the search as rung 3 and is counted. It never reads
     a whole transcript and never reads the parent's transcript.
   - **Counted.** The focus hook keeps per-session counts of events by origin and rung (and of
     cap hits). `rmx focus show` prints them (there is no `focus status` command), so
     attribution failures are visible, not silent.
   - **The TUI's subagent status lines are not persisted and are not a signal.**
3. **R3 Hand-back envelopes are ambient.** `is_ambient_text` also returns True for
   `<agent-message` and the subagent hand-back envelope prefix, beside `<channel`,
   `<task-notification` and `[SYSTEM NOTIFICATION`. `rmx focus rebuild` drops them by default as
   it drops the others.
4. **R4 Typos never label a cluster** (d5e item 4, amended by #m-1).
   - A prompt token with no corpus match, of length ≥ 5, that is not identifier-shaped
     (no `_`, `.`, digit, or internal capital), folds to a known term within edit distance 2
     (`aggre` → `agree`).
   - Tokens of length ≤ 4 (`llok`, `ann`, `lru`, `pql`, `cwd`) and identifier-shaped tokens never
     fold.
   - A fold is a LABEL choice only: the member keeps its raw form.
   - An unmatched, non-code-shaped token may be a member but is never a cluster label (the label
     is the first member that is not such a token).
   - Before GREEN, the fold rate is measured on the redacted fixture (R6) and recorded: folds
     fired / tokens eligible, and every fold pair listed.
5. **R5 The session comes from the envelope, never the newest ring** (bug-100). Every resolver of
   "this session" used by STM (scan-prompt's enrichment at `scan.py:535-537`, the verb resolver at
   `verbs.py:528`, the focus hook) takes the hook envelope's `session_id`, then
   `CLAUDE_CODE_SESSION_ID`, then `RMX_SESSION`. `latest_session` is not consulted on those paths;
   when none of the three is present the enrichment is skipped and counted (a stderr line naming
   the skip), never guessed.
6. **R6 A redacted, committed fixture** (d8f). The raw ring
   `workflow/review-output/stm-export-db80475a-20261014.jsonl` (gitignored; sha256
   `517fd359b1b1ff617e9bc3267365f08da65580fd9be0204ad4d2fc8723beecd1`, 502 lines) stays local.
   Committed instead: `tests/fixtures/stm/ring-db80475a-redacted.jsonl`, holding only
   - the junk-bearing events (heredoc tool events, subagent events, hand-back inputs, the `aggre`
     and `llok` prompts), with prompt text and paths scrubbed to placeholders that keep the
     junk-bearing token and its shape;
   - a synthetic thread set: events whose refs carry the thread terms of AC-2.

   The raw ring's hash is recorded in the fixture's header comment and here; the fixture is
   built by a committed script from the raw ring, so a reviewer holding the raw ring can rebuild
   it byte-identically.

   **Subagent fixture** (d8h). It lives at `tests/fixtures/stm/subagent-db80475a/`, laid out like
   the projects dir: `<session-id>.jsonl` (the parent), `<session-id>/subagents/agent-<id>.jsonl`
   and `agent-<id>.meta.json` (one subagent, the decision-log review). Both are REDACTED copies:
   prompt text and paths are scrubbed, while tool names, inputs, digests and timestamps keep the
   shape the match needs. The raw transcripts stay local; only their sha256s are committed, in
   the fixture's README. The matching ring events are part of the ring fixture above. The
   subagent's events in the fixture carry its refs on the COMMAND LINE (for example the
   `sed -n … src/refmatrix/daemon.py` target), as well as the frozen `glob.glob` / `m.group` /
   `re.findi` set, so that R1 alone cannot clear them and AC-4 isolates R2.

## Acceptance criteria {#acceptance}

Every AC runs on the redacted fixture, replayed with `rmx focus rebuild --dry-run --root <tmp>`
(a pure file op, no daemon) into `topic_composites(graph, k=5)`. A "label" is a composite's head
member as `rmx focus topics` renders it.

1. **No junk** (frozen list, written before GREEN). None of `r.get`, `re.searc`,
   `collections.Count`, `glob.glob`, `json.loads`, `s.repla`, `m.group`, `re.findi` is a label or
   a member of any top-5 composite. Neither `aggre` nor `llok` is a label.
2. **The real threads lead** (frozen list, written before GREEN). Each of the thread terms
   `plan-review-2026-10-14`, `plan-19`, `plan-21`, `plan-23` is a substring of at least one top-5
   label.
3. **RED at HEAD.** The same replay at HEAD fails AC-1 (at least one listed junk ref is a label or
   member). The failing run's output is captured to `workflow/review-output/` before any `src/`
   change, per [[feedback_red_test_must_fail_at_head]].
4. **Subagent separation** (d8h). Replaying the subagent fixture:
   - none of the subagent's refs (its command-line refs and `glob.glob`, `m.group`, `re.findi`)
     is a member or label of any parent topic composite;
   - the ring still holds those events, keyed `agent:<id>`;
   - `rmx focus topics` shows one `background: general-purpose: <description>` line.

   Pre-check before GREEN, recorded: with R1 built and R2 disabled, this AC fails.
4b. **No over-attribution.** A parent event with the same `tool_name` as a subagent call inside
    the window but a different input stays `origin: parent`. An event matching two agents is
    `unattributed`, a member at most, never a label.
4c. **Rung 1.** If R0 found an agent id in the envelope, an envelope fixture carrying it
    attributes the event without opening any transcript (zero files opened). If R0 found none,
    this AC is recorded as not applicable, with the probe's field list.
4d. **Cost bound.** In a subagents dir with 10 transcripts of 5 MB each, 9 of them with stale
    mtimes, attributing one event opens exactly 1 file and reads ≤ 1 MB (counted by the reader,
    not timed). A transcript with no entry inside the window and over 1 MB ends as a counted
    cap hit, as rung 3.
5. **Hand-back ambient.** An `<agent-message …>` input event is dropped from the focus graph and
   kept in the ring.
6. **Envelope session.** Two rings in one tmp STM dir; the envelope names the OLDER-mtime ring;
   scan-prompt's enrichment and the verb resolver read the envelope's ring. With no envelope,
   `CLAUDE_CODE_SESSION_ID` or `RMX_SESSION`, enrichment is skipped and the skip is printed.
7. **Mutations that must FAIL a test:**
   - extract refs from the heredoc body again;
   - drop the stdlib-head rule;
   - remove `<agent-message` from `is_ambient_text`;
   - fold tokens of length 4;
   - restore the `latest_session` fallback on the scan enrichment path;
   - route subagent events into the parent's focus graph;
   - drop the rung-2 transcript match (AC-4);
   - match on `tool_name` alone without the input digest (AC-4b);
   - read whole transcripts, or ignore the mtime filter (AC-4d).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `_extract_refs` command-line-only for tool events; code-noise set; `is_ambient_text`; typo label rule; subagent key per R0 |
| `src/refmatrix/scan.py` | enrichment session from the envelope (R5); the code-noise set beside `_PROMPT_STOPWORDS` |
| `src/refmatrix/verbs.py` | session resolver (R5) |
| `src/refmatrix/cli.py` (`focus_hook`, `focus_rebuild`, `focus show`) | pass the envelope's session; run R2's ladder; rebuild drops hand-backs; origin counts |
| `src/refmatrix/stm.py` (subagent attribution) | R2's rungs 2–3: transcript tail reader, input digest, meta label, `background:` rendering |
| `tests/fixtures/stm/ring-db80475a-redacted.jsonl`, `tests/fixtures/stm/subagent-db80475a/`, their build script | R6 |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under task 23.0's sandbox (tmp `HOME`, tmp global root and
  registry, injected store roots, the conftest guard that fails a test touching `~/.refmatrix` or
  a registered live store). Replays use `--root <tmp>`; no daemon is needed. Each test file
  asserts 0 live connects through 23.0's guard.
- **RED first:** AC-3 is run and its failure recorded before GREEN.
- **R0** is a manual probe in a scratch project, recorded in the implementation summary; it is not
  a pytest.
- No mocks of `stm`; fixture rings only.

## Out of scope {#out-of-scope}

Phasing, the topic cache and versioned injection (19.6). Re-scoring past rings in live stores: a
`rmx focus rebuild --all` on the live store is a separate, announced operation after deploy.

## Revision (2026-10-14 decision log) {#rev-2026-10-14}

| finding / decision | answered at |
|---|---|
| d5e (task created; no later than Wave 2; prerequisite of 19.6) | [[#root]], [[#requirements]] |
| #t5-stm-hygiene item 1 / bug-104 | R1 |
| #t5-stm-hygiene item 2 / bug-103 | R0, R2, AC-4 |
| d8h (subagent differentiation ladder: envelope → transcript match → unattributed; `agent:<id>`; `background:` line; cost bound; redacted parent + subagent fixture; mutations) | R0, R2, R6 (subagent fixture), AC-4, AC-4b, AC-4c, AC-4d, mutations |
| #t5-stm-hygiene item 3 | R3, AC-5 |
| #t5-stm-hygiene item 4; decision-log #m-1; d5e amendment (len ≤ 4, identifier-shaped) | R4 |
| d5e amendment: owns bug-100 | R5, AC-6 |
| d5e amendment: probe the envelope first | R0 |
| d5e amendment: objective acceptance; decision-log #s-10 (judged AC, gitignored fixture) | AC-1, AC-2, R6 |
| d8f (raw ring local, redacted committed fixture) | R6 |
| RED at HEAD | AC-3 |
| d1a/d1b (23.0 sandbox) | [[#test-strategy]] |
| #t8-wave1 (19.0 needs only 23.0) | header |
