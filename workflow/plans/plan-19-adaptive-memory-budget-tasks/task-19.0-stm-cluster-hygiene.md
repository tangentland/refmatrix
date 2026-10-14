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

- **Script bodies (bug-104).** 68 tool events carried heredoc / `-c` scripts. The refs come from
  `cli._tool_event_fields` (`cli.py:1906`): for a Bash call with no `file_path`, it runs
  `stm._PATH_RE.findall(cmd)` over the WHOLE command, heredoc body included (`cli.py:1923-1927`;
  `_PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}`, `stm.py:53`, which matches `re.searc`, `r.get`,
  `collections.Count`), and the hook stores them on the event. So truncated locals and stdlib
  calls became concepts: `r.get` 32, `re.searc` 21, `collections.Count` 18, `glob.glob` 16,
  `json.loads` 13, `s.repla` 10, `m.group` 10. `_extract_refs` (`stm.py:840`) is NOT the cause:
  it runs only when a caller passes no refs (re-review #b-4). `Stm.rebuild_focus`
  (`stm.py:447-480`) replays each event's STORED `refs`, filtered only by `is_junk_ref`
  (`stm.py:90`, which gates ids, hex, uuids and deep paths only), so a replay of the ring never
  re-runs extraction. Read off the frozen ring at `3357c44`: all 416 tool events carry `detail`
  (the verbatim command, cut at `DETAIL_MAX` = 600 chars, `stm.py:43`); 58 of them carry one of
  the junk refs above in their stored `refs`.
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
   from it. The same probe also records (round-3 #b-1, #b-2, #m-4):
   - **Hook environment.** In a PostToolUse, a UserPromptSubmit and a SessionStart hook process:
     whether `CLAUDE_PID` is set and equals the Claude process's pid, and whether
     `CLAUDE_CODE_SESSION_ID` is set and equals the envelope's `session_id` AFTER a `/clear`
     (the long-lived `rmx mcp` keeps its spawn-time value, [[task-21.1-context-usage-telemetry#req-session]];
     a hook may or may not). This decides which branch of R5's pointer writer finds the Claude
     pid (`$CLAUDE_PID` or the ancestor walk).
   - **Id on disk at PostToolUse time.** For ≥ 10 subagent calls, whether the `tool_use` block
     with `id == tool_use_id` is already in the subagent transcript when the parent's
     PostToolUse hook runs (the round-3 review saw it there DURING the call). Rung 2 relies on it.
   - **UserPromptSubmit envelope and hook skew.** Every field of the UserPromptSubmit envelope
     (is there a per-prompt unique id?), and, over ≥ 50 real prompts, the start-time skew between
     the parallel UserPromptSubmit hooks of one prompt (each logs `time.time()` at entry). This
     sets `stm.PRE_PROMPT_SKEW_S` (R7), or retires it if a per-prompt id exists.
1. **R1 Script bodies are not focus** (bug-104; re-review #b-4). ONE function,
   `stm.command_refs(cmd: str) -> list[str]`, extracts a Bash command's refs from the command
   line and the paths it names, never from a heredoc body (`<<EOF … EOF`, `<<'EOF'`, `<<-EOF`) or
   an inline script argument (`python3 -c`, `bash -c`, `node -e`, `perl -e`). Dotted refs whose
   head is a stdlib module (`re`, `json`, `glob`, `collections`, `os`, `sys`, `pathlib`, …) or a
   local of ≤ 2 chars (`r.`, `s.`, `m.`) are dropped. The token gate reuses
   `scan._PROMPT_STOPWORDS` ([[feedback_reuse_shared_stoplist]]); the stdlib heads and short-local
   rule live in ONE separate, documented code-noise set next to it, not a second stoplist.
   - **Hook path (the cause).** `cli._tool_event_fields` calls `stm.command_refs(cmd)` in place
     of `_PATH_RE.findall(cmd)` (`cli.py:1923-1927`), for both the PreToolUse park and the
     PostToolUse record. This is what stops new junk (AC-1b).
   - **Rebuild path (past rings).** `Stm.rebuild_focus` RE-EXTRACTS: for a `tool` event whose
     `detail` is a command string (not a JSON object), its refs are recomputed as
     `stm.command_refs(detail)`; for every other event it keeps the stored refs. Both pass through
     `is_junk_ref` and the code-noise set. Since `detail` is cut at 600 chars and the command line
     precedes its heredoc body, the cut drops body text or trailing paths. So AC-1's replay
     exercises R1's extraction, not only a drop list; the code-noise set is tested on its own by
     AC-1c.
   - **Unterminated scripts** (round-3 #m-2). The cut can leave a heredoc with no closing
     delimiter, or a `-c '…` / `-e "…` argument with no closing quote. Rule: an unterminated
     heredoc runs from its `<<` marker to the END of the string, and an unterminated quoted
     script argument runs from its opening quote to the end of the string; both are body, never
     command line. So a cut can only remove refs (under-extraction, the safe direction), never
     turn body text into command-line refs (AC-1d).
2. **R2 Subagent tool events are not the parent's focus** (bug-103; d8h; re-review #b-3). Every
   PostToolUse event is given an `origin` by this ladder, first rung that resolves wins. The
   event stores `origin` and the envelope's `tool_use_id` (new ring fields; old events without
   `origin` read as `parent`).
   - **Rung 1, the envelope.** If R0 shows the envelope identifies the subagent (an `agent_id`,
     or a `transcript_path` under `<session-id>/subagents/agent-<agentId>.jsonl`), the event's
     origin is `agent:<agentId>`.
   - **Rung 2, the exact key: `tool_use_id`.** The PostToolUse (and PreToolUse) envelope carries
     `tool_use_id`; `cli._tool_call_key` (`cli.py:1893-1903`) already prefers it, and every key in
     the live `*.inflight.json` sidecars is a `toolu_…` id. Each subagent writes its own
     transcript `<projects dir>/<slug>/<session-id>/subagents/agent-<agentId>.jsonl`, whose
     assistant entries hold `tool_use` content blocks with `id` = that same `toolu_…` value and
     an `agentId` field, plus `agent-<agentId>.meta.json` (`agentType`, `description`,
     `toolUseId`, `spawnDepth`, `requestShape`, `requestNonInteractive`). Verified read-only on
     session db80475a's 20 subagent pairs at `3357c44`. The directory comes from the envelope's
     parent `transcript_path` (`<projects dir>/<slug>/<session-id>.jsonl`), else from
     `$HOME/.claude/projects/<slug>`. The event is `agent:<agentId>` when a `tool_use` block with
     `id == tool_use_id` is found in exactly one subagent transcript (its line's `agentId` must
     equal the file's; a mismatch is counted and falls to rung 3). **The match is structured**
     (round-3 #m-4): a line counts only when it parses as JSON and one of its
     `message.content[]` blocks has `type == "tool_use"` and `id == tool_use_id`. The cost bound's
     backward block scan may use a byte search for the id to FIND candidate lines, but a byte hit
     is only a candidate: the round-3 probe found in-flight ids quoted inside another subagent's
     `tool_result` text, which must never match. No time window is involved:
     a call that ran 45 s is matched like one that ran 0.1 s. Its label is
     `<agentType>: <description>` from the meta file; a missing or unreadable meta file leaves
     the label `agent:<agentId>` and is counted.
   - **Rung 2b, digest + window, only when the envelope has NO `tool_use_id`** (the `h:` fallback
     key of `_tool_call_key`). A match is exactly ONE `tool_use` entry across the session's
     subagent transcripts with equal `tool_name`, equal input digest (sha256 of the tool input as
     canonical JSON: sorted keys, no whitespace), and an entry timestamp within ± `W = 2 s` of the
     PreToolUse PARK time `t_pre` (the `t` that `Stm.inflight_begin`, `stm.py:309`, records and
     `inflight_end` returns), never of the PostToolUse time: the transcript entry is written when
     the call is ISSUED, the PostToolUse event after it finishes. With no parked record, rung 2b
     does not run (counted `no_park`) and the event goes to rung 3.
   - **Rung 3, parent or unattributed.**
     - With a `tool_use_id`: if the bounded search below COMPLETED (every candidate file read back
       to its lower bound, no cap hit) and found no block with that id, the call was not issued by
       any subagent: `origin: parent`. If the search hit the cap, `origin: unattributed`.
     - Without a `tool_use_id` (rung 2b found no single match): `origin: unattributed` when any
       subagent of the session is RUNNING, else `parent`. A subagent is running when its meta file
       exists and the tail of its transcript holds a `tool_use` block with no later
       `tool_result` for that id (an open call), never judged by mtime.
     - An `unattributed` event stays in the ring and may be a member, but is never a cluster
       label.

   The rest of R2:
   - **Effect.** Events with origin `agent:<id>` stay in the parent's ring for provenance, keyed
     `agent:<id>`, and are excluded from the parent's focus graph and composites.
     `rmx focus topics` renders each agent active in the window as ONE line,
     `background: <label>`, never as members of the parent's topics.
   - **Cost bound (inside the hook's latency budget).** The lower bound is `t_lo = t_pre − 5 s`
     (the park time; with no park, `event ts − 120 s`, counted `no_park`). Rungs 2 and 2b open only
     the `agent-*.jsonl` files whose mtime is ≥ `t_lo` (a transcript that issued the call was
     written at or after issue time, so its mtime cannot be older). Each is read from the end in
     64 KB blocks, back to the first entry older than `t_lo`, stopping early when the id is found,
     with a hard cap of 1 MB per event across all files. Hitting the cap ends the search as rung 3
     (`unattributed`) and is counted. It never reads a whole transcript and never reads the
     parent's transcript.
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
5. **R5 The session comes from one resolver, never the newest ring** (bug-100; round-3 #b-1).
   Every resolver of "this session" used by STM (scan-prompt's enrichment at `scan.py:535-537`,
   the verb resolver `verbs.resolve_session` at `verbs.py:519-530` and its CLI twin
   `cli._resolve_stm_session` at `cli.py:1060-1078`, the focus hook at `cli.py:1964`) calls
   `stm.resolve_session(root, *, envelope=None, long_lived=False) -> stm.SessionResolution`,
   specified ONCE in [[task-21.1-context-usage-telemetry#req-session]] (21.1 R9): per-call
   processes go envelope → `CLAUDE_CODE_SESSION_ID` → the pid pointer for `$CLAUDE_PID` →
   `RMX_SESSION`; the long-lived `rmx mcp` goes pid pointer for `os.getppid()` → `RMX_SESSION`,
   re-resolved per tool call, never reading its spawn-time `CLAUDE_CODE_SESSION_ID` (live: pid
   59378 holds `b38025a7…` while serving `db80475a…`). The pid pointer
   (`<root>/stm/by-pid/<pid>.json`) is written by the generated SessionStart hook
   `rmx focus hook --event session-start` (`startup|resume|clear|compact`) and refreshed by the
   input hook. Whichever of 19.0 and 21.1 merges first builds it; the other imports it.
   `latest_session` is not consulted on any of these paths. When nothing resolves:
   - **Enrichment** (scan-prompt): skipped, one stderr line naming the skip, counted.
   - **Write verbs** (`save_state`, `focus_note`, `change_subject`, `task` push/pop/swap, on CLI
     and MCP): raise `verbs.SessionUnresolved` naming the sources tried. The CLI exits 2 with that
     line; the MCP tool returns it as a tool error. Nothing is written to `default`, to the
     newest ring, or anywhere else: no dropped write and no misrouted one.
   - **Read verbs** (`focus`, `task list` / `current`, `recall_state`, CLI `focus tail` /
     `context` / `size`): read the newest ring and say so in their output
     (`session: <id> (newest ring; not resolved)`). A read cannot misattribute a write, and a plain
     terminal keeps its convenience, labelled.
   - An explicit `--session` (CLI) or `session` argument (verb) always wins over the resolver.
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
   shape the match needs, and every `tool_use` block keeps its `id`. The raw transcripts stay
   local; only their sha256s are committed, in the fixture's README. Beside them,
   `envelopes.jsonl`: the PreToolUse / PostToolUse envelope pairs of the replay, in recorded
   order, REBUILT by the committed build script from the transcripts' `tool_use` blocks
   (`tool_name`, `tool_input`, `tool_use_id` = the block's `id`, `session_id` = the PARENT's id,
   `transcript_path` = the parent's), interleaved with the parent's own calls. The ring at HEAD
   stores no `tool_use_id`, so subagent separation is tested THROUGH THE HOOK on these envelopes,
   not by replaying stored events. The subagent's calls carry refs on the COMMAND LINE (for
   example the `sed -n … src/refmatrix/daemon.py` target), so R1 alone cannot clear them and AC-4
   isolates R2. The fixture's subagent is the decision-log review, whose meta reads
   `agentType: "ch-bsd"`, `description: "BSD review of decision log"` (re-review #evidence).

7. **R7 The pre-prompt snapshot** (round-3 #b-2). `Stm.record(kind="input")` first calls
   `Stm.snapshot_pre_prompt(prompt)`, which writes `<session>.pre.json` (prompt sha256,
   sub-second `wall`, the graph's `turn` and the ring's event count before this prompt, the
   focus graph, 19.6's topic cache) by tmp + `os.replace`, and only then appends the event (which
   gains `prompt_sha` and a sub-second `t`) and ingests. Readers call
   `stm.pre_prompt_state(root, session, prompt, *, t0) -> stm.PrePromptState`. Both are specified
   ONCE in [[task-21.1-context-usage-telemetry#req-session]] (21.1 R9, "The pre-prompt state");
   same first-to-merge ownership as R5. `stm.PRE_PROMPT_SKEW_S` comes from R0's skew measurement.
   This task's own prompt-time reader, scan-prompt's STM enrichment, reads through it.

## Acceptance criteria {#acceptance}

AC-1, AC-2 and AC-3 replay the redacted ring fixture with `rmx focus rebuild --dry-run --root
<tmp>` (a pure file op, no daemon) into `topic_composites(graph, k=5)`; that rebuild RE-EXTRACTS
tool refs per R1. AC-1b and AC-4..AC-4e drive the HOOK (`rmx focus hook --event tool-pre` /
`--event tool`, the production write path) with envelopes on stdin. A "label" is a composite's
head member as `rmx focus topics` renders it.

1. **No junk, replay** (frozen list, written before GREEN). None of `r.get`, `re.searc`,
   `collections.Count`, `glob.glob`, `json.loads`, `s.repla`, `m.group`, `re.findi` is a label or
   a member of any top-5 composite. Neither `aggre` nor `llok` is a label.
   1b. **No junk, hook path** (re-review #b-4). `rmx focus hook --event tool` fed a recorded
   PostToolUse(Bash) envelope whose command is `python3 - <<'EOF'` + a body using `re.search`,
   `r.get` and `collections.Counter` + `EOF`, run against `src/refmatrix/daemon.py` named on the
   command line, stores an event whose `refs` contain `src/refmatrix/daemon.py` and none of the
   body's tokens. The same for `python3 -c '<body>'`. RED at HEAD (the stored refs hold
   `re.searc`, `r.get`, `collections.Count`).
   1c. **Code-noise set alone.** `stm.command_refs("cat r.get m.group json.loads foo_bar.py")`
   returns `["foo_bar.py"]`: the stdlib-head and short-local rule applies to command-line tokens
   too, independent of the heredoc rule.
   1d. **Unterminated scripts** (round-3 #m-2). `stm.command_refs` on
   `"sed -n 1,5p src/refmatrix/daemon.py; python3 - <<'EOF'\nimport collections\nx = foo_baz.py"`
   (no closing `EOF`) and on `"python3 -c 'import re; open(\"foo_baz.py\")"` (no closing quote)
   returns `["src/refmatrix/daemon.py"]` and `[]`: `foo_baz.py` sits in the unterminated body and
   is never a ref. The same through `rebuild_focus` on a 600-char-cut `detail`.
2. **The real threads lead** (frozen list, written before GREEN). Each of the thread terms
   `plan-review-2026-10-14`, `plan-19`, `plan-21`, `plan-23` is a substring of at least one top-5
   label.
3. **RED at HEAD.** The same replay at HEAD fails AC-1 (at least one listed junk ref is a label or
   member). The failing run's output is captured to `workflow/review-output/` before any `src/`
   change, per [[feedback_red_test_must_fail_at_head]].
4. **Subagent separation, by id** (d8h; re-review #b-3). Feeding the subagent fixture's
   `envelopes.jsonl` through the hook, then `rmx focus topics`:
   - none of the subagent's refs (its command-line refs) is a member or label of any parent
     topic composite;
   - the ring holds those events with `origin: agent:<id>` and their `tool_use_id`;
   - `rmx focus topics` shows exactly one line
     `background: ch-bsd: BSD review of decision log` (the fixture meta's `agentType` and
     `description`).

   Pre-check before GREEN, recorded: with R1 built and R2 disabled, this AC fails.
4b. **No over-attribution.** A parent call with the same `tool_name` and the same input as a
    subagent call, issued within 1 s of it but with its own `tool_use_id`, stays
    `origin: parent`. In the no-id leg (rung 2b), an event matching two agents is
    `unattributed`, a member at most, never a label.
4c. **Rung 1.** If R0 found an agent id in the envelope, an envelope fixture carrying it
    attributes the event without opening any transcript (zero files opened). If R0 found none,
    this AC is recorded as not applicable, with the probe's field list.
4d. **Cost bound.** In a subagents dir with 10 transcripts of 5 MB each, 9 of them with mtimes
    older than `t_lo`, attributing one event opens exactly 1 file and reads ≤ 1 MB (counted by the
    reader, not timed). A transcript over 1 MB with no matching id and no entry older than `t_lo`
    within the cap ends as a counted cap hit, `unattributed`.
4e. **Long calls** (re-review #b-3). A subagent Bash call whose `tool_use` entry is timestamped
    10 s before its PostToolUse envelope (and a second one 45 s before, the measured maximum),
    with the transcript otherwise idle, is attributed `agent:<id>` by rung 2. In the no-id leg,
    the same 10 s call is matched by rung 2b against the PARK time and attributed too.
4f. **Structured match only** (round-3 #m-4). A subagent transcript whose ONLY occurrence of
    the envelope's `tool_use_id` is inside a `tool_result` block's text (another agent quoting
    it), and a second transcript holding the real `tool_use` block, attributes the event to the
    second agent. With the second transcript absent, the event is not attributed to the first
    (rung 3: `parent` after a completed search).
5. **Hand-back ambient.** An `<agent-message …>` input event is dropped from the focus graph and
   kept in the ring.
6. **Envelope session.** Two rings in one tmp STM dir; the envelope names the OLDER-mtime ring;
   scan-prompt's enrichment and the verb resolver read the envelope's ring. With no envelope,
   `CLAUDE_CODE_SESSION_ID`, pid pointer or `RMX_SESSION`, enrichment is skipped and the skip is
   printed.
   6b. **Session switch under one long-lived MCP server** (round-3 #b-1). 21.1 AC-1b's harness
   (`rmx mcp` started with `CLAUDE_CODE_SESSION_ID=A`; the generated SessionStart hook fed
   `{session_id: A, source: startup}`, then `{session_id: B, source: clear}`, with `CLAUDE_PID` =
   the test's pid). After the switch, on the same server: `rmx_focus_note`, `rmx_task push` and
   `rmx_save_state` write to B's ring / checkpoint (A's ring line count unchanged), and
   `rmx_focus` reads B. A third envelope `{session_id: A, source: resume}` switches them back.
   6c. **Unresolved writes fail loudly** (round-3 #b-1). With no pointer, no `RMX_SESSION`, and
   (CLI leg) no `CLAUDE_CODE_SESSION_ID`: `rmx focus note x` exits 2 naming the sources tried;
   MCP `rmx_focus_note` and `rmx_save_state` return a tool error; no ring in the STM dir changes
   (line counts and mtimes compared); `rmx focus tail` prints the newest ring with
   `(newest ring; not resolved)`.
   6d. **Snapshot before mutation** (round-3 #b-2). `rmx focus hook --event input` fed an
   envelope whose prompt adds new terms: afterwards `<session>.pre.json` holds the prompt's
   sha256, the graph `turn` and ring event count from BEFORE the call, and a graph equal to the
   `focus.json` copied before the call; the ring's last event carries `prompt_sha` and a float
   `t`. 21.1 AC-8b covers the readers.
7. **Mutations that must FAIL a test:**
   - extract refs from the heredoc body again in `stm.command_refs` (AC-1 and AC-1b);
   - `_tool_event_fields` back on `_PATH_RE.findall(cmd)` (AC-1b);
   - `rebuild_focus` replaying stored refs instead of re-extracting (AC-1: the fixture's stored
     refs hold the junk);
   - drop the stdlib-head rule (AC-1c);
   - remove `<agent-message` from `is_ambient_text`;
   - fold tokens of length 4;
   - restore the `latest_session` fallback on the scan enrichment path;
   - the MCP server reading `CLAUDE_CODE_SESSION_ID`, or resolving once at spawn (AC-6b);
   - a write verb with no resolved session writing to `default` or the newest ring (AC-6c);
   - `snapshot_pre_prompt` called after the append or the ingest (AC-6d);
   - an unterminated heredoc or quote treated as ending at the cut (AC-1d: `foo_baz.py` admitted);
   - rung 2 matching the id as text anywhere in a line (AC-4f: the quoting agent wins);
   - route subagent events into the parent's focus graph;
   - drop the rung-2 id match (AC-4);
   - rung 2 matching on a ±2 s window around the PostToolUse time instead of the id (AC-4e);
   - rung 2b measured from the PostToolUse time instead of the park time (AC-4e, no-id leg);
   - match on `tool_name` alone without the input digest (AC-4b, no-id leg);
   - rung 3 judging "running" by mtime (AC-4e: the idle transcript would read as not running);
   - read whole transcripts, or ignore the mtime filter (AC-4d);
   - the AC-4 literal rendered from a constant `general-purpose` instead of the meta file.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `command_refs` (R1; the ONE extractor for Bash commands); `rebuild_focus` re-extracts from `detail`; code-noise set; `is_ambient_text`; typo label rule; `origin` / `tool_use_id` ring fields; subagent key per R0 |
| `src/refmatrix/scan.py` | enrichment session from the envelope (R5); the code-noise set beside `_PROMPT_STOPWORDS` |
| `src/refmatrix/verbs.py` | `resolve_session` delegates to `stm.resolve_session` (R5); `SessionUnresolved` on write verbs; the read verbs' `(newest ring; not resolved)` label |
| `src/refmatrix/stm.py` (session, snapshot) | `resolve_session` / `SessionResolution`, the pid pointer; `snapshot_pre_prompt`, `pre_prompt_state`, `PRE_PROMPT_SKEW_S` (R5, R7; specified in 21.1 R9; built here or by 21.1, whichever merges first) |
| `src/refmatrix/hooks.py`, `src/refmatrix/mcp.py` | the generated SessionStart entry `rmx focus hook --event session-start` (`startup\|resume\|clear\|compact`, stderr kept); the MCP server's per-call resolution (21.1 R1) |
| `src/refmatrix/cli.py` (`_tool_event_fields` `:1906`, `focus_hook` `:1946`, `focus_rebuild`, `focus show`) | `_tool_event_fields` calls `stm.command_refs` (the bug-104 cause, `:1923-1927`); pass the envelope's session and `tool_use_id`; run R2's ladder with the park time from `inflight_end`; rebuild drops hand-backs; origin counts |
| `src/refmatrix/stm.py` (subagent attribution) | R2's rungs 2, 2b, 3: transcript tail reader, id lookup, input digest, open-call check, meta label, `background:` rendering |
| `tests/fixtures/stm/ring-db80475a-redacted.jsonl`, `tests/fixtures/stm/subagent-db80475a/`, their build script | R6 |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under task 23.0's sandbox (tmp `HOME`, tmp global root and
  registry, injected store roots, the conftest guard that fails a test touching `~/.refmatrix` or
  a registered live store). Replays use `--root <tmp>`; no daemon is needed. Each test file
  asserts 0 live connects through 23.0's guard.
- **RED first:** AC-3, AC-1b, AC-1d, AC-4f, AC-6b, AC-6c and AC-6d are run and their failures
  recorded before GREEN.
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

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan19-21-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9-fixes]] ("19.0
matches subagent events by `tool_use_id` (not a time window) and filters refs at
`cli._tool_event_fields`"). Code facts read at `3357c44`: `cli.py:1893-1903`, `:1906`,
`:1923-1927`, `:1946`; `stm.py:43`, `:53`, `:309`, `:447-480`, `:840`; the subagent transcript and
meta shape on session db80475a.

| finding / decision | answered at |
|---|---|
| re-review #b-3 (±2 s window misses 41% of calls; rung 3 re-admits them; exact key ignored; AC-4 literal) | R2 rung 2 (`tool_use_id`), rung 2b (park time), rung 3 (completed-search / open-call rules); cost bound (`t_lo` from the park time); AC-4 (`background: ch-bsd: …`), AC-4b, AC-4d, AC-4e; mutations |
| re-review #b-4 (wrong mechanism named; replay cannot fail on the hook defect) | [[#why]] (cause = `cli._tool_event_fields`); R1 (`stm.command_refs`, hook path + rebuild re-extraction stated); AC-1, AC-1b, AC-1c; mutations; [[#files-to-modify]] |
| d8h (ladder) | R2, now with the exact key ahead of the fuzzy rung (#t9-fixes) |

## Revision round 3 (2026-10-14) {#rev-round-3}

Answers [[bsd-plan19-21-spec-rereview-r3-6091648]]. Code facts re-read at `636b210` (read-only):
`verbs.py:519-530` (the resolver: `RMX_SESSION` → `latest_session`), `cli.py:1060-1078`,
`:1964`; `stm.py:123-140`, `:246-282` (append then ingest, `ts` to the second), `:405-445`
(`focus.json` written by tmp + `replace`; `turn` incremented per input); `hooks.py:145-147`,
`:209-213`, `:270-290`; the live `rmx mcp` (pid 59378, ppid 59363 = `CLAUDE_PID`).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r3-6091648]]

| finding / decision | answered at |
|---|---|
| round-3 #b-1 (19.0 R5 promotes a variable frozen in the MCP server; write verbs on no session) | R5 (one resolver, `stm.resolve_session`, specified in 21.1 R9; pid pointer + SessionStart writer; per-verb outcome when unresolved: write verbs raise, reads label the newest ring); R0 (hook env: `CLAUDE_PID`, current session id); AC-6, AC-6b (A→B under one server), AC-6c; mutations; [[#files-to-modify]] |
| round-3 #b-2 (phase inputs read a graph the input hook already changed; second-truncated `ts`) | R7 (`snapshot_pre_prompt` before the append and ingest; `pre_prompt_state`; specified in 21.1 R9); R0 (UserPromptSubmit fields; hook skew sets `PRE_PROMPT_SKEW_S`); AC-6d; mutation. Readers: 21.1 AC-8b, 19.6 AC-3c |
| round-3 #m-2 (the 600-char cut and an unterminated heredoc / quote) | R1 "Unterminated scripts"; AC-1d; mutation |
| round-3 #m-4 (rung 2 structured match; two more R0 facts) | R2 rung 2 (structured `tool_use` block match; byte hits are only candidates); R0 (id on disk at PostToolUse time; hook env); AC-4f; mutation |
