---
gmd: "0.1"
id: task-19.0-stm-cluster-hygiene
title: "Task 19.0: STM topic clusters are built from the session's real threads, not from script bodies, subagents, hand-backs, typos or another session's ring"
tags: [task, stm, focus, topics, hygiene, plan-19, bug-100, bug-103, bug-104]
metadata:
  node_type: task
  status: pending
  created: 2026-10-14
  updated: 2026-10-15
---

# Task 19.0: STM cluster hygiene {#root}

> Plan: [plan-19-adaptive-memory-budget](../plan-19-adaptive-memory-budget.md)
> Status: Pending (revision after the 2026-10-14 decision log)
> Depends on: 23.0 (the test sandbox, d1a/d1b), and bug-109 MERGED TO `master` (d9s; round-4
> #s-1): R5 EXTENDS bug-109's session pointer and resolver as existing code and never rebuilds
> them; the dependency is the merge, not a sha on the bug-109 branch (it landed: `0c7d0e0`,
> 0.78.0, bug-109 r1-r4; round 6 re-read R0, R5 and R7 against it). Scheduled no later than
> Wave 2 (d5e); in the Wave 1 order it runs once 23.0 is in
> ([[plan-review-2026-10-14#t8-wave1]]). Hard prerequisite of 19.6.

rel: part-of -> [[plan-19-adaptive-memory-budget]]
rel: derives-from -> [[plan-review-2026-10-14#t5-stm-hygiene]]
rel: amends -> [[plan-review-2026-10-14#t8-amendments-body]]
rel: implements -> [[exploration-session-phased-context#prereq-stm-hygiene]]
rel: depends-on -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[feedback_causal_story_before_evidence]]
rel: specified-by -> [[bsd-decision-log-review-a192ba2#s-10]]
rel: specified-by -> [[bsd-decision-log-review-a192ba2#m-1]]
rel: derives-from -> [[plan-review-2026-10-14#t8]]
rel: depends-on -> [[bug_registry]]

## Why {#why}

Phase detection and the topic cache (19.6) key on STM topic clusters. In session db80475a
(2026-10-14) those clusters were led by junk, read off the frozen ring (502 events: 416 tool,
27 input, 22 say, 21 git, 16 reason):

- **Script bodies (bug-104).** 68 tool events carried heredoc / `-c` scripts. The refs come from
  `cli._tool_event_fields` (`cli.py:1909`; lines re-read at HEAD `3d3c798` in round 6): for a Bash
  call with no `file_path`, it runs `stm._PATH_RE.findall(cmd)` over the WHOLE command, heredoc
  body included (`cli.py:1926-1930`;
  `_PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}`, `stm.py:53`, which matches `re.searc`, `r.get`,
  `collections.Count`), and the hook stores them on the event. So truncated locals and stdlib
  calls became concepts: `r.get` 32, `re.searc` 21, `collections.Count` 18, `glob.glob` 16,
  `json.loads` 13, `s.repla` 10, `m.group` 10. `_extract_refs` (`stm.py:1105`) is NOT the cause:
  it runs only when a caller passes no refs (re-review #b-4). `Stm.rebuild_focus`
  (`stm.py:712-745`) replays each event's STORED `refs`, filtered only by `is_junk_ref`
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
- **Another session's ring (bug-100).** `latest_session` (`stm.py:392`) resolves "the session" as
  the newest ring by mtime. Its direct callers, found by a scan of `src/` at HEAD `3d3c798`
  (round-4 #b-2): scan-prompt's STM enrichment (`scan.py:537`), the scan-prompt STM composite
  (`composite.py:103`, called with no session at `scan.py:888-894`), the helix stale gate
  (`helix.py:96`), `promote_focus_edges` (`promote.py:161`), and the tail of bug-109's verb
  resolver `resolve_session_source` (`verbs.py:566`). That tail is reached in turn by every
  `prefer_latest=True` CLI command through `cli._resolve_stm_session` (`cli.py:1072`), 15 call
  sites, five of which write (round-6 #b-2; R5's table). So with two sessions on one project one
  session's prompt can be seeded with the other's focus, and a write can land in the other's
  ring. The topic cache is session-scoped, so 19.6 cannot ship on it. bug-109 (d9s) fixes the MCP
  write path's SOURCE (a per-Claude-process pointer) but keeps the newest ring as its last
  fallback and leaves every other caller above as it is.

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
     whether `CLAUDE_PID` is set, equals the Claude process's pid and is a real ancestor; the
     status `stm.owner_lookup()` returns (`found`, `none`, `failed`; `stm.py:236-279`, the
     function the resolver calls at `verbs.py:545`); and, for `found`, which of its three
     branches produced the owner: `$CLAUDE_PID` found in the kernel ancestor chain, the nearest
     ancestor recognised by executable path (`_is_claude`) or by `ps` argv[0], or the `ps`-only
     chain used when the kernel chain has fewer than 2 entries (`_ps_comm_chain`). `CLAUDE_CODE_SESSION_ID` is recorded for the record only: no
     resolver reads it ([[task-21.1-context-usage-telemetry#req-session]]).
   - **Id on disk at PostToolUse time.** For ≥ 10 subagent calls, whether the `tool_use` block
     with `id == tool_use_id` is already in the subagent transcript when the parent's
     PostToolUse hook runs (the round-3 review saw it there DURING the call). Rung 2 relies on it.
   - **UserPromptSubmit envelope and the snapshot interval** (round-4 #m-1). Every field of the
     UserPromptSubmit envelope (is there a per-prompt unique id?), and, over ≥ 50 real prompts,
     the interval the match actually compares: the input hook's snapshot `wall` minus each
     parallel reader's entry `t0`, keyed by `prompt_sha` (the writer's `wall` is stamped after
     its imports, envelope parse and bug-109's pointer write, so the entry-to-entry skew
     under-measures it). This sets `stm.PRE_PROMPT_SKEW_S` (R7), or retires it if a per-prompt
     id exists.
1. **R1 Script bodies are not focus** (bug-104; re-review #b-4). ONE function,
   `stm.command_refs(cmd: str) -> list[str]`, extracts a Bash command's refs from the command
   line and the paths it names, never from a heredoc body (`<<EOF … EOF`, `<<'EOF'`, `<<-EOF`) or
   an inline script argument (`python3 -c`, `bash -c`, `node -e`, `perl -e`). Dotted refs whose
   head is a stdlib module (`re`, `json`, `glob`, `collections`, `os`, `sys`, `pathlib`, …) or a
   local of ≤ 2 chars (`r.`, `s.`, `m.`) are dropped. The token gate reuses
   `scan._PROMPT_STOPWORDS` ([[feedback_reuse_shared_stoplist]]); the stdlib heads and short-local
   rule live in ONE separate, documented code-noise set next to it, not a second stoplist.
   - **Hook path (the cause).** `cli._tool_event_fields` calls `stm.command_refs(cmd)` in place
     of `_PATH_RE.findall(cmd)` (`cli.py:1926-1930`), for both the PreToolUse park and the
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
     `tool_use_id`; `cli._tool_call_key` (`cli.py:1896-1906`) already prefers it, and every key in
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
     PreToolUse PARK time `t_pre` (the `t` that `Stm.inflight_begin`, `stm.py:574-586`, records and
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
   - **Swept calls** (round-6 #s-1). `Stm.inflight_sweep` (`stm.py:596-618`) records every call
     parked longer than 90 s as a `tool` event with `abandoned: true` and the refs it was parked
     with, into the ring AND the graph, at the parent's next prompt. A background subagent's
     calls park in the PARENT's sidecar (their PreToolUse envelope carries the parent's
     `session_id`), so a subagent call that runs past 90 s, hangs or is denied would enter the
     parent's focus through the sweep: bug-103 by a second door. So:
     - the park record (`Stm.inflight_begin`, `stm.py:574-586`, called from the `tool-pre` branch
       of `cli.focus_hook`) also stores the envelope's `tool_use_id` (already the key when present,
       `cli._tool_call_key`), its `transcript_path`, `tool_name` and rung 2b's input digest;
     - the sweep runs THIS ladder on each swept call with `t_pre` = the park's `t`: rung 1 when
       the stored fields carry R0's subagent marker, rung 2 by id (the subagent transcript holds
       the `tool_use` block from issue time; R0 records that it does), rung 2b only for an `h:`
       key, rung 3 as above. An `agent:<id>` swept event stays in the ring with its origin and is
       not ingested into the parent's graph; an `unattributed` one may be a member, never a label;
     - each swept call's search obeys the cost bound below, per call AND per sweep, and its
       counts join the hook's origin counts in `rmx focus topics`;
     - a park record written before this change (no stored fields) is swept as `unattributed`,
       counted.
   - **A long call is no longer recorded twice** (round-6 #s-1; predates this plan). A call still
     RUNNING at the sweep is recorded `abandoned`, and recorded AGAIN when its PostToolUse
     arrives: `inflight_end` (`stm.py:588-594`) finds nothing, and the PostToolUse branch
     (`cli.py:2013` onward) records regardless, so its refs are ingested twice. The sweep keeps
     the swept keys in their OWN file, `<key>.swept.json` beside `<key>.inflight.json`
     (`stm.py:468`), a dict `{tool key: {t, origin}}` bounded like the sidecar (`INFLIGHT_BUDGET`
     = 64, `stm.py:45`; past it the oldest half by `t` is dropped, counted). The in-flight sidecar
     stays a dict of park records only (round-7 #m-2: a list stored under a key of that dict
     would raise `AttributeError` in `inflight_sweep`'s `v.get("t")`, `stm.py:604-605`, and
     `inflight_begin`'s eviction, `:579-580`, on every later turn). A PostToolUse whose key is in
     `<key>.swept.json` records its event ring-only, with `late: true` and the swept record's
     `origin`, and does NOT ingest its refs into the graph; the key is then removed from that
     file. A failed read or write of `<key>.swept.json` is one stderr line and a `sweep-failed`
     row (21.1 R9 D8), never a silent skip. The ring keeps both lines for provenance.
   - **Cost bound, in bytes read (counted by the reader, not timed).** The lower bound is
     `t_lo = t_pre − 5 s`
     (the park time; with no park, `event ts − 120 s`, counted `no_park`). Rungs 2 and 2b open only
     the `agent-*.jsonl` files whose mtime is ≥ `t_lo` (a transcript that issued the call was
     written at or after issue time, so its mtime cannot be older). Each is read from the end in
     64 KB blocks, back to the first entry older than `t_lo`, stopping early when the id is found,
     with a hard cap of 1 MB per event across all files. Hitting the cap ends the search as rung 3
     (`unattributed`) and is counted. It never reads a whole transcript and never reads the
     parent's transcript. **Per sweep** (round-7 #m-1): one `inflight_sweep` reads at most
     `SWEEP_READ_CAP = 4 MB` across all its swept calls (the sidecar can hold up to
     `INFLIGHT_BUDGET` = 64 parks, so the per-event cap alone allowed 64 MB in one
     UserPromptSubmit). Once the total is reached, every remaining swept call is recorded
     `origin: unattributed` without opening a file, counted `sweep_cap`. So one input hook reads
     ≤ 4 MB of transcripts and one PostToolUse hook ≤ 1 MB; neither opens a daemon or hub socket
     (AC-6f).
   - **Counted.** The focus hook keeps per-session counts of events by origin and rung (and of
     cap hits and `sweep_cap`). `rmx focus topics` (`cli.py:1234`, no required argument) prints
     them as a footer, also when it prints "no topics yet" (round-7 #m-4 (b): the round-6 surface
     `rmx focus show` takes a required `LINE`, `cli.py:1210`; there is no `focus status`
     command), so attribution failures are visible, not silent.
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
5. **R5 The session comes from one resolver; the newest ring only for labelled reads** (bug-100;
   round-3 #b-1; round-4 #b-2, #s-1, #m-2; round-6 #b-1, #b-2; d9s).
   - **Existing code** (bug-109 as MERGED: r1-r4, merged at `0c7d0e0`, 0.78.0; round-6 #b-1).
     Read at HEAD `3d3c798` (`src/` = `master` `c7129e6`); the full list, with lines, is
     [[task-21.1-context-usage-telemetry#req-session]] "Existing code this task extends". In
     short: `stm._proc_info` reads the kernel (libproc / `/proc`, `stm.py:127-165`);
     `stm.owner_lookup()` (`:236-279`) returns `(pid, found | none | failed)`, recognising Claude
     by executable path (`_is_claude`, `:190`) with `ps` only as an argv[0] fallback
     (`_ps_comm_chain`, `:205`); `stm.write_pid_pointer` / `read_pid_pointer` (`:346`, `:378`)
     keep `<root>/stm/by-pid/<pid>.json` = `{session, pid, pid_start, t}`;
     `stm.record_pointer_error` (`:294`) appends to `<root>/stm/by-pid/_errors.jsonl`, bounded at
     `_ERRORS_MAX_BYTES` = 256 KiB by an in-place halving (`:291`, `:308-310`), with reasons
     `no-owner`, `owner-lookup-failed`, `write-failed`, `ps-failed`, `pointer-unresolved`;
     `stm.read_pointer_errors` (`:318`); `handoff.session_pointer_anomalies` (`handoff.py:508`),
     called by `compose_recall_state` (`:569`), already reports those rows in `rmx recall-state`;
     `verbs._LONG_LIVED` and `verbs.resolve_session_source(root, session) -> (session, source)`
     (`verbs.py:524-569`, owner from `owner_lookup()` at `:545`). Its tests live in
     `tests/test_mcp_session_pointer.py`, which this task EXTENDS.
   - **The resolver** is bug-109's `verbs.resolve_session_source`, EXTENDED as specified ONCE in
     [[task-21.1-context-usage-telemetry#req-session]] (21.1 R9, deltas D1-D8): bug-109's order;
     a `SessionResolution` NamedTuple; `envelope=`; a REQUIRED `purpose` ∈ `write`, `read`,
     `event`; the user-level pointer location; the SessionStart writer; recorded stale and
     unreadable pointers; the EXISTING recall-state reader following the log to its new location
     (D6); `by-pid/` cleanup. Whichever of 19.0 and 21.1 merges first builds the deltas; the other
     imports them. `CLAUDE_CODE_SESSION_ID` is read by no path.
   - **`cli._resolve_stm_session(explicit, *, purpose)` and `cli._stm(session=None, *, purpose)`**
     (round-6 #b-2; today `cli.py:1062-1078` and `:1081-1083`, with `prefer_latest`). `purpose`
     is a REQUIRED keyword of both, with no default; `prefer_latest` and the `prefer_latest=False`
     branch (`$RMX_SESSION` → `default`, `:1073-1078`) are removed. `_resolve_stm_session` calls
     `resolve_session_source(_root(), explicit, purpose=purpose)` and returns its session, raising
     `SessionUnresolved` for a `write`. Neither helper picks a purpose: each of its callers states
     its own, per the table.
   - **Every caller, by purpose.** The list comes from a scan of `src/` for calls of
     `latest_session`, `resolve_session_source`, `resolve_session`, `_resolve_stm_session` and
     `_stm`, to every level (round-6 #b-2: round 5's scan stopped at the helper, which fans out to
     15 call sites), not from memory; AC-6e keeps it closed. Lines are HEAD `3d3c798`.

     | caller | purpose | when nothing resolves |
     |---|---|---|
     | scan-prompt STM enrichment, `scan.py:535-537` | `event` (session from the envelope) | skipped; one stderr line and an `enrichment-unresolved` row (21.1 D8) |
     | scan-prompt STM composite, `composite.build_topic_composite` (`composite.py:63`, its `latest_session` default at `:103`), called at `scan.py:888-894` | `event`; on this prompt-time call scan-prompt passes `session=` and `graph=pre_prompt_state(…).graph` (R7), so the composite never reads the live `focus_graph()` | no composite; the skip is recorded like the enrichment's |
     | the composite's `except Exception: comp = ""` (`scan.py:893-894`) | — | becomes one stderr line plus a `composite-failed` row (21.1 D8), never a silent `""` |
     | helix stale gate, `helix._current_session` (`helix.py:84-98`) | `event`; scan-prompt passes the session it resolved | the gate excludes no session's touches and annotates nothing that turn, counted; its docstring's false claim "the hook exports RMX_SESSION" is corrected |
     | `promote.promote_focus_edges` (`promote.py:140`, default at `:161`) and the daemon op `promote_edges` | `session` becomes a REQUIRED argument: the op refuses a call without one instead of taking the newest ring | the CLI decides (next row) |
     | `rmx focus promote-edges` (`cli.focus_promote_edges`, resolves in the CLI at `cli.py:1497`) | `--apply`: `write`; `--dry-run`: `read` | `--apply`: `SessionUnresolved`, exit 2, nothing promoted |
     | `rmx focus summarize` (`cli.py:1297`) | `--promote`: `write` (it writes the `session/digest` memory); without: `read` | `--promote`: `SessionUnresolved`, exit 2, no digest written (under `--envelope-stdin`, exit 1: next row) |
     | the generated Stop entry `rmx focus summarize --promote --timeout 5` (`hooks.py:202`) and PreCompact entry `… --timeout 30` (`hooks.py:334`) | `write`, session from the hook's stdin envelope: both entries gain `--envelope-stdin`, which reads the envelope JSON on stdin and passes it as `envelope=` (the field `focus hook` reads at `cli.py:1967`), so the session is the one the hook already holds | no envelope `session_id` and no pointer: no digest written; one stderr line; EXIT 1, not 2, under `--envelope-stdin`, because exit 2 from a Stop hook is the harness's "block the stop" signal and would feed the line back to the model as an instruction. Because a non-blocking hook error reaches the user only as a notice, the durable channel is the resolver's `pointer-unresolved` row (D8-scoped to the root and the owner pid), which recall-state and the SessionStart surfacing report; AC-6c pins the stderr line AND the row (round-7 #s-4) |
     | `rmx focus detour` (`cli.py:1589`) and `rmx focus return` (`:1614`): write focus marks | `write` | `SessionUnresolved`, exit 2, no mark written or consumed |
     | `rmx focus clear-subject` (`cli.py:1724`): writes subject state | `write` | `SessionUnresolved`, exit 2, subject state unchanged |
     | `rmx focus rebuild` with no `--all` / `--session` (`cli.py:1556`) | without `--dry-run`: `write` (rewrites `focus.json`); with `--dry-run`: `read` | write: `SessionUnresolved`, exit 2, no graph rewritten |
     | `rmx focus record` (`cli.py:1091-1094`) and `rmx focus clear` (`:1624-1628`), both `_stm()` with no purpose today, so `RMX_SESSION` → `default` (bug-109 r1 #m-3) | `write` | `SessionUnresolved`, exit 2; `focus clear` no longer clears the `default` ring while claiming "this session" |
     | `rmx focus tail` (`:1103`), `context` (`:1121`, then `_stm(sess)` at `:1122` with the session it resolved), `export` (`:1191`), `show` (`:1218`), `topics` (`:1245`), `detours` (`:1599`), `subject` (`:1687`), `size` (`:1735`), and `rmx recall-state` (`:13260`) | `read` | the newest ring, labelled `session: <id> (newest ring; not resolved)` |
     | write verbs `save_state` (`verbs.py:892`), `focus_note` (`:958`), `change_subject` (`:972`), and `task` push / pop / swap (`:1029`; the one call serves every action, so it passes `purpose="read" if action in ("list", "current") else "write"`) (CLI and MCP) | `write` | `verbs.SessionUnresolved` naming the sources tried; CLI exit 2 with that line; MCP tool error; nothing written to `default`, to the newest ring or anywhere else |
     | read verbs `focus` (`verbs.py:934`), `recall_state` (`:1068`), both through the str wrapper `resolve_session` today, and `task` list / current (`:1029`) | `read` | the newest ring, labelled |
     | the focus hook (`cli.py:1963-1967`: `json.load(sys.stdin)` with `except Exception: return`, then `d.get("session_id") or stm_mod.session_id()`) | explicit envelope session, read through 21.1 R9 D9's ONE envelope reader `stm.read_hook_envelope(…, require_session=True)` (round-8 #nm-4) | a falsy envelope `session_id` (missing, `None` or `""`): the hook writes no ring, prints one stderr line AND records one `envelope-no-session` row (D8-scoped: `root`, `owner` from `owner_lookup()`); an unparseable or non-object envelope records `envelope-unreadable` the same way, instead of today's silent `return`. The generated focus entries end `2>/dev/null \|\| true` (`hooks.py:131-147`), where stderr is not a channel (bug-109's own docstring, `stm.py:295-296`), so the ROW is the durable channel, surfaced by 21.1 D6; the suffix is not changed here (bug-118 converges the generator's hook-command wrapper in ONE renderer; any change to this suffix goes through it) |
     | `stm.Stm.__init__` (`stm.py:447`: `self.session = session or session_id()`), the tail no table row above shows (round-7 #m-4 (d)): a `None` session becomes `$RMX_SESSION`, else `default`, so an `event` / `read` caller that passed its `None` on would silently read or write the `default` ring | — (not a resolver caller) | the fallback is removed: `session` is a required `str`, and a FALSY session (`None` or `""`, round-8 #nm-4) raises `ValueError`. Every caller that can hold `None` from the `event` tail (scan-prompt's enrichment, `scan.py:540`; the composite, `composite.py:106`) skips BEFORE constructing, as its row says. `hub._op_focus`'s `args.get("session") or "default"` (`hub.py:565`) is a UI read naming an explicit ring and keeps its literal. AC-6e's third check lists every `Stm(` call |

     The `read` tail is the ONE allowed `latest_session` call in `src/` (round-4 #m-2): it
     exists so a plain terminal keeps its convenience, labelled. bug-109's str wrapper
     `verbs.resolve_session` (`verbs.py:572-575`) is removed and its callers pass `purpose`.
   - **bug-109's deferred items, owned here** (its auditor's r1 #m-1..#m-4; d9s):
     - `composite.py:103` and `helix.py:96` read the newest ring: the table above;
     - `focus record` / `focus clear` bypass the resolver: the table above;
     - no SessionStart pointer write: 21.1 R9 D4, generated by `hooks.py`;
     - the hook and the server resolve their store root differently (`cli._root()` from the
       hook's cwd, `mcp._resolve_root(args)` from the server's spawn cwd): 21.1 R9 D3 moves the
       pointer to the user-level `by-pid/` directory, read by every root;
     - `stm/by-pid/` cleanup: 21.1 R9 D7;
     - the error log's surfacing: bug-109 r2 ALREADY surfaces it in `rmx recall-state`
       (`handoff.session_pointer_anomalies`). What is owned here is keeping that surface working
       when D3 / D8 move the file, SCOPED to the reader's root and, on SessionStart, to its owner
       (21.1 R9 D6 extends `session_pointer_anomalies`; round-7 #s-2; 21.1 AC-4b (v), (vii),
       (viii)), migrating bug-109's per-root file once with no legacy read left behind (round-7
       #s-3; 21.1 AC-4b (ii), (vi)), plus the two new surfaces (`rmx focus topics`' footer, the
       SessionStart writer's stdout).
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

   **Replay clock** (round-7 #m-3). The fixture keeps its recorded 2026-10-14 timestamps; the
   TEST rebases them, never the cost bound. Before a replay it copies the fixture into its tmp
   projects dir and shifts every transcript entry's `timestamp` and every envelope's time by
   `Δ = replay start − the first envelope's recorded time`, then sets each transcript file's
   mtime (`os.utime`) to its last rebased entry. So a park made at replay time `t` sees the
   matching `tool_use` entry inside `[t_lo, t]` exactly as it was live, and R2's `t_lo` and
   mtime filters run unchanged. A test that widens or drops `t_lo`, or skips the mtime filter,
   to pass is the cheap fix this ladder forbids, and AC-4d's mutation catches it.

7. **R7 The pre-prompt snapshot, the input hook's FIRST state access** (round-3 #b-2; round-4
   #b-1, #m-1). The input branch of `cli.focus_hook` (`cli.py:1974-2004` at HEAD `3d3c798`: pointer
   write `:1979-1993`, sweep `:1998-2001`, input record `:2003-2004`) today runs `inflight_sweep()`
   (`stm.py:596-618`), which `record`s every call parked > 90 s as an `abandoned` tool
   event into the ring AND the graph, BEFORE the ambient check and before `record("input")`. The
   new order, specified ONCE in [[task-21.1-context-usage-telemetry#req-session]] (21.1 R9, "The
   pre-prompt state"):
   1. bug-109's pointer write (existing);
   2. `Stm.snapshot_pre_prompt(prompt)` for every non-empty prompt, ambient included: writes
      `<session>.pre.json` (prompt sha256, sub-second `wall`, the graph's `turn`, the ring's
      parent-origin event count, the focus graph, 19.6's topic cache) by tmp + `os.replace`;
   3. `inflight_sweep()`, which gives each swept call an `origin` by R2's ladder (R2 "Swept
      calls"); its `except Exception: pass` (`cli.py:2000-2001`) becomes one stderr line and a
      `sweep-failed` row (21.1 R9 D8);
   4. if not ambient, `record("input", …)`; the event gains `prompt_sha` and a sub-second `t`.
   `Stm.record` does not call the snapshot. Readers call `stm.pre_prompt_state(root, session,
   prompt, *, t0) -> stm.PrePromptState`; same first-to-merge ownership as R5.
   `stm.PRE_PROMPT_SKEW_S` comes from R0's `wall − t0` measurement. This task's own prompt-time
   readers, scan-prompt's STM enrichment AND its composite (R5), read through it. Known limit,
   stated in 21.1 R9: `focus.json` has no lock.

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
   `envelopes.jsonl` through the hook (rebased onto the replay clock, R6; this holds for AC-4,
   AC-4e and AC-4g), then `rmx focus topics`:
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
    within the cap ends as a counted cap hit, `unattributed`. **Per sweep** (round-7 #m-1): six
    calls parked 120 s back, each with a `tool_use_id` found in no transcript and each search
    able to hit its 1 MB cap (six 5 MB transcripts with mtime ≥ `t_lo`), are swept by one
    `--event input`: the reader's byte count for that hook is ≤ 4 MB, files are opened for at
    most four of the calls, every one of the six is `unattributed`, and `rmx focus topics`'
    footer shows `sweep_cap=2`.
4e. **Long calls** (re-review #b-3). A subagent Bash call whose `tool_use` entry is timestamped
    10 s before its PostToolUse envelope (and a second one 45 s before, the measured maximum),
    with the transcript otherwise idle, is attributed `agent:<id>` by rung 2. In the no-id leg,
    the same 10 s call is matched by rung 2b against the PARK time and attributed too.
4f. **Structured match only** (round-3 #m-4). A subagent transcript whose ONLY occurrence of
    the envelope's `tool_use_id` is inside a `tool_result` block's text (another agent quoting
    it), and a second transcript holding the real `tool_use` block, attributes the event to the
    second agent. With the second transcript absent, the event is not attributed to the first
    (rung 3: `parent` after a completed search).
4g. **Swept subagent call** (round-6 #s-1). Through the hook: a PreToolUse envelope from the
    subagent fixture (its `tool_use_id` present in the subagent transcript, refs on the command
    line) is parked by `--event tool-pre`, the sidecar's `t` is set 120 s back by the test, and
    the parent's `--event input` then sweeps it (the transcript rebased so its `tool_use` entry
    sits after the park's `t_lo`, R6). The ring holds the swept event with
    `abandoned: true` and `origin: agent:<id>`; none of its refs is a member or label of any parent
    composite; `rmx focus topics` shows the `background:` line. Non-vacuous control: a PARENT call
    parked and swept the same way is `origin: parent` and its refs ARE members. RED at post-109
    `master`: the subagent call's refs are members of the parent's top composite.
4h. **Late completion recorded once in the graph** (round-6 #s-1). A parent call parked 120 s
    back is swept, then its PostToolUse arrives. The ring holds two lines for it (`abandoned`,
    then `late: true`), and each of its refs' node weights in `focus.json` after the PostToolUse
    equals the weight right after the sweep. Then (round-7 #m-2) a SECOND call is parked 120 s
    back and the next `--event input` sweeps it: the ring gains its `abandoned` event,
    `<key>.inflight.json` no longer holds it, `<key>.swept.json` holds its key, and no
    `sweep-failed` row is written. RED at post-109 `master`: the weights rise (the second
    ingest).
5. **Hand-back ambient.** An `<agent-message …>` input event is dropped from the focus graph and
   kept in the ring.
6. **Envelope session.** Two rings in one tmp STM dir; the envelope names the OLDER-mtime ring;
   scan-prompt's enrichment, its STM COMPOSITE (the composite block in the same stdout) and the
   helix gate's excluded session all read the envelope's ring, through the generated scan-prompt
   hook command (round-4 #b-2). The STM dir also holds a `default` ring whose events carry terms
   found in neither other ring (round-7 #m-4 (d)): with no envelope, no pointer and no
   `RMX_SESSION`, enrichment and composite are skipped, no `default`-ring term appears anywhere in
   the payload, and the skip is recorded (`enrichment-unresolved`); with the composite
   forced to raise, the payload carries no composite and `_errors.jsonl` gains a
   `composite-failed` row. RED at post-bug-109 `master` for this leg: the failing assertion is
   the composite block's topics, which name the NEWER ring's terms. **Envelope legs** (round-8 #nm-4), through the GENERATED
   `focus hook --event input` command (run as generated, suffix included, so the production
   path is the one tested): an envelope with a prompt and no `session_id`, and separately one
   with `"session_id": ""`, each add exactly one `envelope-no-session` row with `root` = the
   sandbox root and `owner` = the test pid (`CLAUDE_PID` set as in AC-6c), write no ring and no
   `pre.json` (STM dir listing compared), and the row appears in `rmx recall-state`'s STM-hook
   clause; stdin `not json` adds one `envelope-unreadable` row and writes nothing (the STM hooks
   call 21.1 D9's reader with `prose_ok=False`). RED at post-bug-109 `master` for the envelope
   legs: the failing assertion is the row count (the hook writes the `default` ring, or returns
   silently on bad JSON).
   6b. **Session switch under one long-lived MCP server** (round-3 #b-1; re-baselined on
   post-bug-109 `master`, round-4 #s-1). 21.1 AC-1b's harness, extending
   `tests/test_mcp_session_pointer.py`: `rmx mcp` started with `CLAUDE_CODE_SESSION_ID=A`; the
   generated SessionStart hook fed `{session_id: A, source: startup}`, then
   `{session_id: B, source: clear}`, with the test process as the Claude owner and NO input-hook
   run after the clear. On the same server: `rmx_focus_note`, `rmx_task push` and
   `rmx_save_state` write to B's ring / checkpoint (A's ring line count unchanged), and
   `rmx_focus` reads B. A third envelope `{session_id: A, source: resume}` switches them back.
   RED at post-109 `master`, failing assertion: A's ring line count (no SessionStart writer, so
   the server still resolves A's pointer). The input-hook switch bug-109 already passes is kept
   as a GREEN regression leg and is not counted as RED.
   6c. **Unresolved writes fail loudly** (round-3 #b-1; round-4 #b-2; round-7 #s-4). Every child
   in this AC runs with `CLAUDE_PID` = the test process's pid, as 21.1 AC-4 does, so
   `owner_lookup()` returns `(test pid, "found")` and the resolver's row does not depend on the
   runner (a plain terminal records nothing). With no pointer and no `RMX_SESSION`: `rmx focus note x`, `rmx focus record --terse x`, `rmx focus clear` and
   `rmx focus promote-edges --apply --yes` each exit 2 naming the sources tried; MCP
   `rmx_focus_note` and `rmx_save_state` return a tool error; the daemon op `promote_edges`
   called with no `session` refuses; no ring and no durable edge changes (ring line counts and
   mtimes compared, the `co-occurs` edge count compared); `rmx focus tail` prints the newest ring
   with `(newest ring; not resolved)`. RED at post-109 `master`, failing assertions: the newest
   ring's line count (bug-109 writes the note there) and the `default` ring (`focus record` /
   `focus clear` write or clear it).
   **The other CLI writes** (round-6 #b-2), same setup, two rings on disk: `rmx focus summarize
   --promote`, `rmx focus detour x`, `rmx focus return`, `rmx focus clear-subject` and `rmx focus
   rebuild` (no `--all`, `--session` or `--dry-run`) each exit 2 naming the sources tried; no
   `session/digest` memory is written (the sandbox store's `focus_summary_*` memory count is
   compared), no focus mark, subject file or `focus.json` changes (mtimes and bytes compared).
   **The hook entries:** the generated Stop and PreCompact summarize commands carry
   `--envelope-stdin`; fed `{session_id: <the OLDER ring's id>}` they promote
   `focus_summary_<that id's slug>` and not the newer ring's; fed an envelope with no
   `session_id`, they exit 1 (not 2), write no digest, print exactly ONE stderr line naming the
   sources tried, and add exactly one `pointer-unresolved` row with `owner` = the test pid and
   `root` = the sandbox root, which then appears in `handoff.compose_recall_state`'s anomalies
   under the session-pointer clause (21.1 R9 D6). The same three assertions (one stderr line,
   one row, visible in `compose_recall_state`) hold for the CLI write leg `rmx focus note x`
   above. RED at post-109 `master`, failing
   assertions: the generated commands lack `--envelope-stdin` (asserted on the config first);
   `focus summarize --promote` writes `focus_summary_<newest ring's slug>`; `focus detour x` adds a
   mark to the newest ring.
   6d. **Snapshot before every mutation** (round-3 #b-2; round-4 #b-1). The seeded store holds an
   in-flight sidecar with one call parked 120 s ago whose refs join the active topic.
   `rmx focus hook --event input` fed an envelope whose prompt adds new terms: afterwards
   `<session>.pre.json` holds the prompt's sha256, and the graph `turn`, the ring's event count
   and a graph equal to the `focus.json` copied BEFORE the call (the swept call is in neither);
   the ring then holds the swept `abandoned` event followed by the input event, which carries
   `prompt_sha` and a float `t`. An AMBIENT prompt (`<agent-message …>`) with the same parked call
   writes `pre.json` too (pre-sweep values) and records no input event. With a 19.0 R2 `origin:
   agent:<id>` event in the seeded ring, `pre.json`'s event count excludes it. 21.1 AC-8b covers
   the readers.
   6e. **No `latest_session` caller outside the allow-list** (round-4 #b-2, #m-2). A test parses
   every module under `src/refmatrix/` (AST, not text) and lists every call whose function is
   named `latest_session` (a `Name` or an `Attribute`); the list must equal exactly one site,
   the `read` tail inside `verbs.resolve_session_source`. A second AST check (round-6 #b-2) lists
   every call of `resolve_session_source`, `_resolve_stm_session` and `_stm`. Each must carry a
   `purpose=` keyword whose value is a string constant (`"write"`, `"read"`, `"event"`) or a
   conditional expression whose two branches are such constants (`focus summarize`,
   `promote-edges`, `rebuild`, the `task` verb). Exactly two calls are allow-listed to pass the
   bare name `purpose` through: `_resolve_stm_session`'s call of `resolve_session_source`, and
   `_stm`'s call of `_resolve_stm_session`. Any other value fails, and so does a `purpose`
   parameter with a default on either helper. The set of enclosing functions found must equal
   R5's table, so a new caller fails until it is given a row. A THIRD check (round-7 #m-4 (d))
   lists every `Stm(` call (a `Name` or an `Attribute`; 13 at HEAD `77ac38f`: `cli.py:1083`,
   `:1563`, `:1968`; `composite.py:106`; `hub.py:565`; `promote.py:167`; `scan.py:540`;
   `verbs.py:893`, `:934`, `:959`, `:973`, `:1030`, `:1068`). Each must pass a session argument
   (positional or `session=`), and the set of enclosing functions must equal a list kept in the
   test beside R5's table, so a new constructor call fails until someone states where its
   session comes from; a separate unit case asserts `Stm(root, None)` and `Stm(root, "")` each raise `ValueError` (round-8 #nm-4). RED
   at post-109 `master`:
   `composite.py`, `helix.py`, `promote.py` and `scan.py` are listed by the first check, and the
   second finds 19 `_stm` / `_resolve_stm_session` calls with no `purpose=` (18 in commands, plus
   `_stm`'s own call at `cli.py:1083`); the unit case fails (`Stm(root, None)` builds the
   `default` ring's `Stm`). The third check's list is a guard, GREEN at `master`.
   6f. **The STM hooks open no daemon or hub socket** (round-7 #m-1; round-8 #nm-3). The commands
   run are exactly the generated command strings whose argv contains `focus hook --event <e>` for
   `e` ∈ `session-start` (once 21.1 R9 D4's entry exists), `input` (with a parked call to sweep and
   a prompt), `tool-pre`, `tool` and `say` (the Stop entry, `hooks.py:153`, fed an envelope
   whose `transcript_path` is a tmp transcript holding one assistant message AND whose
   `session_id` is a test session id (the STM hooks read the envelope with
   `require_session=True`, D9, so a `say` envelope without one records `envelope-no-session`
   and never reaches `s.record`; round-10 #m10-5), so the
   `s.record("say", …)` branch at `cli.py:2005-2011` runs; round-9 #m9-7), taken from
   `hooks.py`'s generated block; the other commands
   of those events (`rmx scan-prompt`, `rmx memory recall`, `rmx sync --flush-queue`,
   `rmx curator status`) dial the daemon legitimately and are NOT run here. Each command is run
   with its trailing `2>/dev/null || true` removed: the test asserts the generated string ends
   with exactly that suffix and strips it (no regex guess), because under `|| true` "exited 0"
   is always true and the suffix hides the stderr this AC reads. Two detectors (no mock of
   `src/`; 23.0's audit hook still refuses every live target):
   - **the connect log, 23.0's interface** (round-9 #s9-3). Python imports ONE `sitecustomize`,
     so this AC adds none: 23.0 R4's `tests/sandbox_site/sitecustomize.py`
     ([[task-23.0-test-sandbox#r4]]) appends the target of every `AF_UNIX` `socket.connect` to
     the file named by `$RMX_SANDBOX_CONNECT_LOG` when that variable is set (23.0 is extended
     to provide this in its R4 / AC-3 amendment, [[task-23.0-test-sandbox#rev-amend-r10]], which
     also fixes that a refused dial is logged BEFORE the deny check; this AC consumes it as a
     23.0 interface and is blocked until that amendment lands).
     Each command runs with `RMX_SANDBOX_CONNECT_LOG=<tmp>/connects.log`; after the runs the
     file is empty. This sees EVERY unix socket, including ones no listener anticipates.
     **Two control legs, same environment except the log path, run first:** each control runs
     with `RMX_SANDBOX_CONNECT_LOG=<tmp>/control.log`, never `<tmp>/connects.log`, so the
     controls' lines cannot make the hook assertion fail (round-10 #m10-5): (1) a child
     `python -c` that connects to a test-owned listener in the tmp dir writes exactly ONE line
     naming that path to `control.log` (the detector can fail); (2) a child that dials a
     deny-set path (the real `~/.refmatrix/hub.sock` path string) still exits 86 (23.0's
     `CHILD_EXIT`) and its target is ALSO in `control.log` (logged before the deny check), so the
     refusal is still loaded beside the logger. If either control fails, the AC fails before
     the hook commands run;
   - **listeners** (`socket.socket(AF_UNIX)`, bound and listening) at every path a daemon or hub
     client in the sandbox would dial: `daemon.socket_path(<sandbox root>)` (`daemon.py:527`),
     `daemon.socket_path(hub.global_store_root())` (the GLOBAL store's daemon, `hub.py:100`; a
     sandbox path, so 23.0's hook allows it), `hub.hub_sock_path()` (`hub.py:88`) and
     `modelsrv.model_sock_path()` (`modelsrv.py:45`, `$RMX_MODEL_SOCK` set to a sandbox path); a
     non-blocking `accept()` on each returns nothing.
   Each un-suffixed command exits 0 with EMPTY stderr. (`say` reads its transcript and calls no
   daemon today, so it is a regression leg like `input`.) Mutations: an input hook that calls
   `daemon.call(root, "ping")` (the project listener accepts and the log has a line), and one that
   calls `daemon.call(hub.global_store_root(), "ping")` (only the global listener and the log see
   it; at round 7 this mutant passed). This is a regression guard for `input`, `tool-pre` and
   `tool` (no daemon call today, round-7 #hook-daemon-cost) and is not counted as RED; its
   `session-start` leg runs once 21.1 R9 D4's entry exists. bug-115/116 (0.78.2) bound what such
   a call would cost; this AC keeps it from being made.
7. **Mutations that must FAIL a test:**
   - extract refs from the heredoc body again in `stm.command_refs` (AC-1 and AC-1b);
   - `_tool_event_fields` back on `_PATH_RE.findall(cmd)` (AC-1b);
   - `rebuild_focus` replaying stored refs instead of re-extracting (AC-1: the fixture's stored
     refs hold the junk);
   - drop the stdlib-head rule (AC-1c);
   - remove `<agent-message` from `is_ambient_text`;
   - fold tokens of length 4;
   - restore the `latest_session` fallback on the scan enrichment path (AC-6, AC-6e);
   - the composite restored to `session or latest_session(root)` (AC-6: the composite names the
     newer ring; AC-6e lists `composite.py`);
   - the composite reading the live `focus_graph()` instead of `pre_prompt_state(…).graph` on
     the prompt-time call (21.1 AC-8b's scan-prompt leg; 19.6 AC-3c);
   - the composite's `except Exception: comp = ""` restored (AC-6: no `composite-failed` row);
   - `helix._current_session` restored to `latest_session` (AC-6, AC-6e);
   - `promote_focus_edges` defaulting to `latest_session` again, or `promote-edges --apply`
     resolving with `purpose="read"` (AC-6c: an edge is written; AC-6e);
   - `focus record` / `focus clear` back on `_stm()` without the resolver (AC-6c);
   - `_resolve_stm_session` passing a hard-coded `purpose="read"` instead of its caller's (AC-6e
     accepts the literal; AC-6c fails: `focus summarize --promote` writes a digest named after the
     newest ring);
   - `focus summarize` resolving with `purpose="read"` on `--promote` (AC-6c: the digest is
     written);
   - the Stop / PreCompact summarize entries without `--envelope-stdin` (AC-6c: the generated
     config, and the older-ring envelope promotes the newer ring);
   - `--envelope-stdin`'s unresolved exit left at 2 (AC-6c: the hook leg's exit code);
   - `focus detour` / `return` / `clear-subject` / `rebuild` resolving with `read` (AC-6c: a mark
     or file changes);
   - a `purpose` default restored on `_resolve_stm_session` or `_stm` (AC-6e);
   - the sweep recording a swept call without running the origin ladder (AC-4g: the subagent's
     refs become members);
   - the park record without `tool_use_id` / `transcript_path` (AC-4g: the swept call ends
     `unattributed`, a member);
   - a late PostToolUse ingested into the graph again (AC-4h: the weights rise);
   - the MCP server reading `CLAUDE_CODE_SESSION_ID`, or resolving once at spawn (AC-6b);
   - a write verb with no resolved session writing to `default` or the newest ring (AC-6c);
   - `snapshot_pre_prompt` called after the append or the ingest (AC-6d);
   - `snapshot_pre_prompt` called inside `record("input")` after the sweep, or skipped for
     ambient prompts (AC-6d: `pre.json` holds the post-sweep count);
   - an unterminated heredoc or quote treated as ending at the cut (AC-1d: `foo_baz.py` admitted);
   - rung 2 matching the id as text anywhere in a line (AC-4f: the quoting agent wins);
   - route subagent events into the parent's focus graph;
   - drop the rung-2 id match (AC-4);
   - rung 2 matching on a ±2 s window around the PostToolUse time instead of the id (AC-4e);
   - rung 2b measured from the PostToolUse time instead of the park time (AC-4e, no-id leg);
   - match on `tool_name` alone without the input digest (AC-4b, no-id leg);
   - rung 3 judging "running" by mtime (AC-4e: the idle transcript would read as not running);
   - read whole transcripts, or ignore the mtime filter (AC-4d);
   - the AC-4 literal rendered from a constant `general-purpose` instead of the meta file;
   - (round 7) the resolver recording its miss only for `purpose="event"` / `"read"` (AC-6c: no
     `pointer-unresolved` row for the Stop hook leg or `focus note`);
   - `--envelope-stdin` exiting 1 with no stderr line and no row (AC-6c's hook leg);
   - the `swept` keys stored inside `<key>.inflight.json` (AC-4h's second park: `sweep-failed`
     and the second call never swept);
   - no per-sweep total, only the 1 MB per-event cap (AC-4d's per-sweep leg reads 6 MB,
     `sweep_cap` absent);
   - `t_lo` widened or dropped, or the mtime filter skipped (AC-4d: more than one file opened,
     more than 1 MB read);
   - `Stm.__init__` keeping `session or session_id()` (AC-6e's unit case; AC-6: the seeded
     `default` ring's terms reach the payload if a caller passes its `None` on);
   - a `Stm(` call added without a session argument or outside the listed functions (AC-6e's
     third check);
   - an STM hook calling the daemon or hub (AC-6f: a listener accepts a connection);
   - (round 8) an STM hook calling the GLOBAL store's daemon (AC-6f: the global listener accepts
     and the connect log has a line);
   - AC-6f run with the `2>/dev/null || true` suffix kept, or entries chosen by event instead of
     by `focus hook --event` argv (a review check on the test: the suffix assertion and the argv
     filter are asserted on the command list the test builds);
   - the focus hook writing the `default` ring, or returning silently, on an envelope with a falsy
     `session_id` or unparseable stdin (AC-6's envelope legs: no row);
   - `Stm.__init__` accepting `""` (AC-6e's unit case);
   - the origin counts printed by `focus show` instead of `focus topics` (AC-4d's `sweep_cap`
     footer is read from `rmx focus topics`).

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/stm.py` | `command_refs` (R1; the ONE extractor for Bash commands); `rebuild_focus` re-extracts from `detail`; code-noise set; `is_ambient_text`; typo label rule; `origin` / `tool_use_id` ring fields; subagent key per R0 |
| `src/refmatrix/scan.py` | enrichment AND composite session from the envelope through the resolver (`purpose="event"`), the composite's graph from `pre_prompt_state`, the composite's `except` recorded (R5); the code-noise set beside `_PROMPT_STOPWORDS` |
| `src/refmatrix/composite.py` | `build_topic_composite` takes `session=` and `graph=`; no `latest_session` default (R5) |
| `src/refmatrix/helix.py` | `_current_session` through the resolver (`purpose="event"`), docstring corrected (R5) |
| `src/refmatrix/promote.py`, `daemon.py` (`promote_edges` op) | `session` required; the op refuses a call without one (R5) |
| `src/refmatrix/verbs.py` | EXTEND bug-109's `resolve_session_source` per 21.1 R9 D1-D2 (`purpose`, `SessionResolution`, `SessionUnresolved`); remove the str wrapper `resolve_session`; the read verbs' `(newest ring; not resolved)` label |
| `src/refmatrix/stm.py` (session, snapshot) | EXTEND bug-109's pointer code per 21.1 R9 D3-D8; NEW `snapshot_pre_prompt`, `pre_prompt_state`, `PRE_PROMPT_SKEW_S` (R5, R7; specified in 21.1 R9; built here or by 21.1, whichever merges first) |
| `src/refmatrix/hooks.py` | the generated SessionStart entry `rmx focus hook --event session-start` (`startup\|resume\|clear\|compact`, stderr kept; 21.1 R9 D4); the Stop (`:202`) and PreCompact (`:334`) summarize entries gain `--envelope-stdin` (R5; round-6 #b-2). The MCP server's per-call resolution is bug-109's, existing |
| `src/refmatrix/handoff.py` (`session_pointer_anomalies`, `:508-529`) | EXTENDED, not paralleled (round-6 #b-1): follows the error log to `stm.pointer_dir()`, reads only its own root's rows, prints the session-pointer, STM-hook and truncation clauses apart, and reads no legacy file (21.1 R9 D6; round-7 #s-2, #s-3) |
| `src/refmatrix/cli.py` (`_tool_event_fields` `:1909`, `focus_hook` `:1949` (envelope through `stm.read_hook_envelope`, 21.1 D9; round-8 #nm-4), `_resolve_stm_session` `:1062`, `_stm` `:1081`, and every command in R5's table) | `_tool_event_fields` calls `stm.command_refs` (the bug-104 cause, `:1926-1930`; round-7 #m-4 (c)); pass the envelope's session and `tool_use_id`; run R2's ladder with the park time from `inflight_end`; the input branch's order (R7); `--event session-start`; rebuild drops hand-backs; origin counts (with `sweep_cap`) and the pointer-error clauses as `focus topics`' footer, also with no topics (round-7 #m-4 (b)); `_resolve_stm_session` / `_stm` with a required `purpose`, each caller stating its own; `focus summarize --envelope-stdin` (exit 1 when unresolved under it); `focus record` / `clear` / `promote-edges` / `summarize` / `detour` / `return` / `clear-subject` / `rebuild` and the read commands through the resolver per R5's table; the `tool-pre` park stores `tool_use_id`, `transcript_path`, `tool_name` and the input digest, and a PostToolUse whose key is in `<key>.swept.json` records ring-only with `late: true` (R2); the Stop / PreCompact `--envelope-stdin` miss prints one stderr line (R5) |
| `tests/test_mcp_session_pointer.py` | EXTENDED (bug-109's file, no parallel file): AC-6b, AC-6c |
| `src/refmatrix/stm.py` (subagent attribution) | R2's rungs 2, 2b, 3: transcript tail reader, id lookup, input digest, open-call check, meta label, `background:` rendering; `inflight_begin` stores the ladder's fields, `inflight_sweep` runs the ladder per swept call under `SWEEP_READ_CAP` and keeps the bounded `<key>.swept.json` file (R2 "Swept calls"; round-7 #m-1, #m-2); `Stm.__init__` without the `session_id()` fallback (R5; round-7 #m-4 (d)) |
| `tests/fixtures/stm/ring-db80475a-redacted.jsonl`, `tests/fixtures/stm/subagent-db80475a/`, their build script | R6 |

## Test strategy {#test-strategy}

- **Sandbox:** every test runs under task 23.0's sandbox (tmp `HOME`, tmp global root and
  registry, injected store roots, the conftest guard that fails a test touching `~/.refmatrix` or
  a registered live store). Replays use `--root <tmp>`; no daemon is needed. Each test file
  asserts 0 live connects through 23.0's guard.
- **RED first**, against post-bug-109 `master` (round-4 #s-1): AC-3, AC-1b, AC-1d, AC-4f, AC-4g,
  AC-4h, AC-6, AC-6b, AC-6c, AC-6d and AC-6e are run and their FAILING ASSERTIONS recorded by name before
  GREEN. A test that fails only because `--event session-start` is not a click choice, or
  `purpose=` not a keyword, is RED for the wrong reason
  ([[feedback_red_test_must_fail_at_head]]); each such AC asserts on observable state first
  (a ring line count, the generated config, the composite's topics, the AST list).
- **AC-6f** (round-7 #m-1) is a regression guard (no STM hook calls the daemon at post-109
  `master`) and is not counted as RED; it keeps the hooks this task grows file-only.
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

## Revision round 5 (2026-10-14) {#rev-round-5}

Answers [[bsd-plan19-21-spec-rereview-r4-878647c]] (every id; plus the round-3 ids it marks
partial) and d9s of [[plan-review-2026-10-14#t11-approvals]]. Code facts re-read at write time:
HEAD `39dffbb` (`src/` identical to `master` `a434f51`): `cli.py:1946-1981`, `:1964`, `:1976-1981`;
`scan.py:535-537`, `:889-894`; `composite.py:100-106`; `helix.py:84-98`; `promote.py:158-161`;
`verbs.py:526-530`; `mcp.py:49-67`. bug-109 at `320dc82` in `/Volumes/littlebig/refmatrix-bug109`
(READ ONLY): `git grep "latest_session("` over `src/` (`composite.py:103`, `helix.py:96`,
`promote.py:161`, `scan.py:537`, `verbs.py:558`), `cli.py:1062-1078`, `:1091-1094`,
`:1490-1496`, `:1624-1627`, `:1973-2002`, `verbs.py:521-566`, its implementation summary
(`#open`) and its ch-bsd r1 report (#m-1..#m-5).

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r4-878647c]]

| finding / decision | answered at |
|---|---|
| round-4 #b-1 (snapshot after the input hook's sweep; ambient prompts sweep) | R7 (the input hook's order: pointer → snapshot → sweep → record; ambient prompts snapshot; sweep failure recorded); AC-6d (parked call, ambient leg, subagent-origin leg); mutation. Specified once in 21.1 R9 ([[task-21.1-context-usage-telemetry#rev-round-5]]) |
| round-4 #b-2 (composite, helix, promote never routed) | [[#why]] (the scanned caller list); R5 caller table (composite with `session=` + `graph=`, its `except` recorded; helix; promote required session + `--apply` as `write`); AC-6 (composite + helix legs through the generated hook), AC-6c (promote leg), AC-6e (AST allow-list); mutations; [[#files-to-modify]] |
| round-4 #s-1 (bug-109 owns the pointer; RED for the wrong reason; tests twice) | header (bug-109 merged to `master`); R5 "Existing code" + the resolver EXTENDED per 21.1 R9 D1-D8; AC-6b, AC-6c, AC-6e re-baselined with the failing assertion named; [[#test-strategy]]; [[#files-to-modify]] (`tests/test_mcp_session_pointer.py` extended). bug-109's registry row exists (open) |
| round-4 #m-1 (`S` interval; background appends; lock) | R0 (`wall − t0`); R7 (parent-origin count; lock limit); AC-6d subagent leg |
| round-4 #m-2 (the read fallback is a `latest_session` consult) | R5 (the `read` tail named as the ONE allowed use); AC-6e |
| d9s: bug-109's deferred items listed in R5 | R5 "bug-109's deferred items, owned here" (composite/helix newest ring; `focus record` / `focus clear`; SessionStart writer; hook vs server store root; `by-pid/` cleanup; `_errors.jsonl` surfacing) |
| round-3 #b-1 (partial via d9s) | as round-4 #s-1 |
| round-3 #b-2 (partial) | as round-4 #b-1 |

## Revision round 6 (2026-10-15) {#rev-round-6}

Answers [[bsd-plan19-21-spec-rereview-r6-0e77da3]] (the 19.0 side of #b-1, #b-2, #s-1, #m-1).
No round-6 decision-log row names plan 19 ([[plan-review-2026-10-14#t12-approvals]], d9ao-d9ar,
covers plans 16/17/22/23). Code facts read at write time at HEAD `3d3c798` (`src/` identical to
`master` `c7129e6`, bug-109 r1-r4 merged at `0c7d0e0`), plus an AST scan of `src/refmatrix/` for
calls of `latest_session`, `resolve_session_source`, `resolve_session`, `_resolve_stm_session` and
`_stm` (32 calls): `stm.py:45`, `:127-165`, `:190`, `:205`, `:236-279`, `:291-343`, `:346`,
`:378`, `:392`, `:574-586`, `:588-594`, `:596-618`, `:712-745`, `:1105`; `cli.py:1062-1083`,
`:1091-1094`, `:1103`-`:1735` (R5's rows), `:1896-1906`, `:1909`, `:1926-1930`, `:1949`, `:1967`,
`:1974-2004`, `:2013`, `:13260`; `hooks.py:202`, `:334`; `verbs.py:524-575`, `:892`, `:934`,
`:958`, `:972`, `:1029`, `:1068`; `handoff.py:508-529`, `:569`; `scan.py:537`, `:888-894`;
`composite.py:63`, `:103`; `helix.py:84-98`; `promote.py:140`, `:161`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r6-0e77da3]]

| finding / decision | answered at |
|---|---|
| round-6 #b-1 (bug-109 read at r1, not as merged; recall-state's pointer report silenced by D3/D8) | header (merge landed); R0 (probe names `owner_lookup()`'s statuses and branches); R5 "Existing code" rewritten from `master` (`_proc_info`, `owner_lookup`, `owner-lookup-failed`, `read_pointer_errors`, `handoff.session_pointer_anomalies`, `_ERRORS_MAX_BYTES` halving); R5 "bug-109's deferred items" ("nothing surfaces" removed: the item is keeping recall-state's reader working after the move); [[#files-to-modify]] (`handoff.py` added). The deltas themselves (D6 `t` watermark, counted halving, legacy read; D7 `_proc_start`) and their ACs are 21.1's: [[task-21.1-context-usage-telemetry#rev-round-6]] |
| round-6 #b-2 (`_resolve_stm_session`'s 15 `prefer_latest=True` callers, five of them writes incl. the Stop hook's per-turn promote, had no purpose; AC-6e pushed toward `purpose="read"` in the helper) | [[#why]] (second-level callers); R5 (`_resolve_stm_session` / `_stm` take a REQUIRED `purpose`; one table row per caller: summarize `--promote` / not, the Stop and PreCompact entries with `--envelope-stdin` and exit 1, detour, return, clear-subject, rebuild, the nine read commands, the `task` verb by action); AC-6c (the other CLI writes; the hook entries); AC-6e (second check covers the helpers; two pass-through calls allow-listed; caller set equals the table); mutations (hard-coded `purpose="read"` in the helper, and five more); [[#files-to-modify]] (`cli.py`, `hooks.py`) |
| round-6 #s-1 (swept calls carry no origin; long calls recorded twice) | R2 "Swept calls" (the park stores the ladder's fields; the sweep runs the ladder) and "A long call is no longer recorded twice" (`swept` list, `late: true`, ring-only); R7 step 3; AC-4g, AC-4h; [[#test-strategy]]; mutations; [[#files-to-modify]] |
| round-6 #m-1 (citations stale since the merge) | [[#why]], R0, R1, R2, R5, R7 re-read at `3d3c798` (`cli.py:1974-2004`, sweep `:1998-2001`, record `:2003-2004`; `owner_lookup()` at `verbs.py:545`, not `owner_claude_pid()`). bug-109's registry row is `fixed` (the round-5 row above said open) |
| round-6 #m-2, #s-2, #s-3 | not 19.0 items: [[plan-19-adaptive-memory-budget#rev-round-6]], [[task-19.6-phased-context-and-topic-cache#rev-round-6]], [[task-19.3-subject-tiered-index#rev-round-6]], [[task-19.4-keep-derived-layers-current#rev-round-6]] |

## Revision round 7 (2026-10-15) {#rev-round-7}

Answers [[bsd-plan19-21-spec-rereview-r7-331b414]] (the 19.0 side of #s-2, #s-3, #s-4, #m-1,
#m-2, #m-3, #m-4). The user took the one-shot migration for #s-3
([[plan-review-2026-10-14#t12-approvals]], round-7 item 2); the deltas it changes are specified
once in 21.1 R9. Code facts read at write time at HEAD `77ac38f` (its `src/` equals the review's
`331b414`): `stm.py:45`, `:447`, `:468`, `:558-618` (eviction `:579-580`, sweep iterator
`:604-605`); `cli.py:1083`, `:1209-1210`, `:1234-1276`, `:1926-1930`, `:1974-2004`;
`scan.py:540`; `composite.py:106`; `hub.py:88`, `:565`; `daemon.py:522`; `modelsrv.py:44`;
`handoff.py:508-529`; an AST scan of `src/refmatrix/` for `Stm(` calls (13). The user's note on
#m-1: bug-115/116 ship as 0.78.2 (ping on the dispatcher, heartbeat on cli completions, expired
reads dropped, `daemon.call` sends `deadline_s` and no longer re-sends after a send); the "0
daemon connects from the STM hooks" AC still stands.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]

| finding / decision | answered at |
|---|---|
| round-7 #s-2 (19.0 side: the user-level log is unscoped) | R5 "bug-109's deferred items" (the surfacing kept SCOPED to root and owner); [[#files-to-modify]] (`handoff.py`). The scope itself and its ACs: [[task-21.1-context-usage-telemetry#rev-round-7]] (D6-D8, AC-4b (vii), (viii)) |
| round-7 #s-3 (19.0 side: the "for one release" legacy read in the Files row) | [[#files-to-modify]] (`handoff.py`: no legacy file); R5 deferred items (one-shot migration). Specified in 21.1 R9 D3 / D6, AC-4b (ii), (vi) |
| round-7 #s-4 (a `write` miss is never pinned to its row; AC-6c depends on the runner) | R5 table (the Stop / PreCompact row: the row is the durable channel, pinned); AC-6c (`CLAUDE_PID` = the test pid; the hook leg and `focus note` each assert one stderr line, one `pointer-unresolved` row with `owner` and `root`, and the row in `compose_recall_state`); mutations (records only for `event` / `read`; `--envelope-stdin` silent exit 1) |
| round-7 #m-1 (no aggregate bound on the sweep; "no daemon calls" asserted nowhere) | R2 cost bound (in bytes, counted; `SWEEP_READ_CAP = 4 MB` per sweep, the rest `unattributed`, `sweep_cap` counted; "latency budget" withdrawn); AC-4d per-sweep leg; AC-6f (listeners at every daemon / hub path; the generated `session-start`, `input`, `tool-pre`, `tool` entries; 0 accepts); [[#test-strategy]]; mutations |
| round-7 #m-2 (the `swept` list breaks both sidecar iterators) | R2 (`<key>.swept.json`, its own bounded dict; the sidecar holds park records only; read/write failure recorded); AC-4h (a second park and sweep after the late completion); mutation; [[#files-to-modify]] |
| round-7 #m-3 (fixture timestamps below any live `t_lo`) | R6 "Replay clock" (the test rebases entry times and file mtimes; the bound is never widened); AC-4, AC-4e, AC-4g (rebased); mutation (`t_lo` widened or the mtime filter skipped fails AC-4d) |
| round-7 #m-4 (b) (`focus show` takes a required `LINE`) | R2 "Counted" (`rmx focus topics`' footer, also with no topics); R2 "Swept calls"; [[#files-to-modify]] (`cli.py`); mutation |
| round-7 #m-4 (c) (stale `cli.py:1923-1927`) | [[#files-to-modify]] (`cli.py` row: `:1926-1930`) |
| round-7 #m-4 (d) (`Stm.__init__` is an unlisted resolver tail) | R5 table (`Stm.__init__` row: the `session_id()` fallback removed, `Stm(root, None)` raises; `hub._op_focus` keeps its explicit literal); AC-6 (a seeded `default` ring whose terms must not appear); AC-6e third check (13 `Stm(` calls listed, set equality; unit case); mutations; [[#files-to-modify]] (`stm.py`) |
| round-7 #m-4 (a) | not a 19.0 item: 21.1 AC-4b (iii-b) |
| round-7 #s-1; d9ax, d9ay | not 19.0 items: [[task-19.6-phased-context-and-topic-cache#rev-round-7]], [[task-19.2-memory-usage-record#rev-round-7]] |

## Revision round 8 (2026-10-15) {#rev-round-8}

Answers [[bsd-plan19-21-spec-rereview-r8-23ad703]] (the 19.0 side of #nm-3, #nm-4, #nm-7, and
#ns-2 as it bears on R5's Stop row). No user decision was needed. Code facts read at write time at
HEAD `23ad703`: `cli.py:1062`, `:1081`, `:1909`, `:1949`, `:1963-1967`, `:1974-2004`;
`hooks.py:131-147` (the focus entries' `2>/dev/null || true`), `:209-297`; `stm.py:294-307`;
`daemon.py:527` (`socket_path`); `hub.py:88`, `:100`; `modelsrv.py:45`; bug-118's registry row
(open: the generator's presence guard swallows exit codes; one renderer planned). Older revision
tables keep the lines of their own HEAD.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: related-to -> [[task-23.0-test-sandbox]]

| finding / decision | answered at |
|---|---|
| round-8 #nm-3 (AC-6f misses the global store's daemon socket, names entries by event, asserts a vacuous exit 0; stale cite) | AC-6f (only the `focus hook --event <e>` command strings; suffix asserted and stripped; a test-only `sitecustomize` connect logger for every `AF_UNIX` connect; a listener at `daemon.socket_path(hub.global_store_root())`; "exit 0 with empty stderr" on the un-suffixed command; `daemon.py:527`, `modelsrv.py:45`); mutations (global-daemon ping; suffix kept or entries by event) |
| round-8 #nm-4 (a focus envelope with no `session_id` "prints one stderr line" that the generated command discards; `Stm(root, "")` uncovered) | R5 table, focus-hook row (`envelope-no-session` / `envelope-unreadable` rows through 21.1 D9's ONE reader; the row is the durable channel; the suffix left to bug-118's renderer); `Stm.__init__` row (falsy session raises); AC-6 envelope legs; AC-6e unit case (`""`); mutations; [[#files-to-modify]] (`cli.py` `focus_hook`). The reader itself: [[task-21.1-context-usage-telemetry#rev-round-8]] (D9) |
| round-8 #ns-2 (R5's Stop row named SessionStart surfacing as the durable channel, which reached only the same process) | holds as written now that 21.1 D6 surfaces a dead owner's rows as `ended_sessions` in its root ([[task-21.1-context-usage-telemetry#rev-round-8]]) |
| round-8 #nm-7 (`daemon.py:522`) | AC-6f (`:527`) |
| user rule: converge repeated shapes | the focus hook's envelope parse joins 21.1 D9's one reader (AST check 21.1 AC-4b (xii)(c)); the generated-suffix question joins bug-118's one renderer rather than a second wrapper |

## Revision round 9 (2026-10-15) {#rev-round-9}

Answers [[bsd-plan19-21-spec-diffcheck-r9-ebccb20#s9-3]] and the 19.0 part of
[[bsd-plan19-21-spec-diffcheck-r9-ebccb20#m9-7]]. Edit-level; no decision. Code facts read at
HEAD (`hooks.py:153` the Stop `--event say` entry; `cli.py:2005-2011` its branch).

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]
rel: depends-on -> [[task-23.0-test-sandbox#r4]]

| finding | answered at |
|---|---|
| r9 #s9-3 (a second test-only `sitecustomize` cannot coexist with 23.0 R4's: one of the two is silently absent) | AC-6f: no second `sitecustomize`; the connect log is 23.0 R4's ONE sandbox hook, enabled by `$RMX_SANDBOX_CONNECT_LOG` (cited as a 23.0 interface; 23.0 is extended to provide it); two control legs run first (a connect to a test listener logs exactly one line; a deny-set dial still exits 86) |
| r9 #m9-7 (two RED sentences spliced in AC-6; no `--event say` in AC-6f) | AC-6: the composite RED sits under the envelope-session leg, the row-count RED under the envelope legs; AC-6f runs the Stop entry's `focus hook --event say` with a tmp transcript |
| r9 #s9-4 (19.0 side) | AC-6's `not json` leg names 21.1 D9's `prose_ok=False` for the STM hooks |

## Revision round 10 (2026-10-15) {#rev-round-10}

Answers the 19.0 part of [[bsd-plan19-21-spec-diffcheck-r10-f6400aa#m10-5]] and records the
provider for [[bsd-plan19-21-spec-diffcheck-r10-f6400aa#s10-3]]. Edit-level; no decision.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]]
rel: depends-on -> [[task-23.0-test-sandbox#rev-amend-r10]]

| finding | answered at |
|---|---|
| r10 #m10-5 (the connect-log controls and the hook runs shared one log file; the `say` envelope carried no `session_id`) | AC-6f: the controls write `<tmp>/control.log`, the hook runs `<tmp>/connects.log`; the deny-set control also asserts its target is logged; the `say` envelope carries a test `session_id` (D9's `require_session=True`) |
| r10 #s10-3 (`$RMX_SANDBOX_CONNECT_LOG` has no provider) | AC-6f now cites 23.0's amendment ([[task-23.0-test-sandbox#rev-amend-r10]]): the log is written for every `AF_UNIX` connect BEFORE the deny check, and 86 is `CHILD_EXIT`; AC-6f stays blocked until that amendment lands |
