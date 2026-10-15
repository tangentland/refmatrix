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
     - each swept call's search obeys the cost bound above, and its counts join the hook's origin
       counts in `rmx focus show`;
     - a park record written before this change (no stored fields) is swept as `unattributed`,
       counted.
   - **A long call is no longer recorded twice** (round-6 #s-1; predates this plan). A call still
     RUNNING at the sweep is recorded `abandoned`, and recorded AGAIN when its PostToolUse
     arrives: `inflight_end` (`stm.py:588-594`) finds nothing, and the PostToolUse branch
     (`cli.py:2013` onward) records regardless, so its refs are ingested twice. The sweep keeps
     the swept keys in a `swept` list in the sidecar (bounded like the sidecar, `INFLIGHT_BUDGET`
     = 64, `stm.py:45`); a PostToolUse whose key is in that list records its event ring-only, with
     `late: true` and the swept record's `origin`, and does NOT ingest its refs into the graph.
     The ring keeps both lines for provenance.
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
     | the generated Stop entry `rmx focus summarize --promote --timeout 5` (`hooks.py:202`) and PreCompact entry `… --timeout 30` (`hooks.py:334`) | `write`, session from the hook's stdin envelope: both entries gain `--envelope-stdin`, which reads the envelope JSON on stdin and passes it as `envelope=` (the field `focus hook` reads at `cli.py:1967`), so the session is the one the hook already holds | no envelope `session_id` and no pointer: no digest written; one stderr line; EXIT 1, not 2, under `--envelope-stdin`, because exit 2 from a Stop hook is the harness's "block the stop" signal and would feed the line back to the model as an instruction; the resolver's own row records the miss |
     | `rmx focus detour` (`cli.py:1589`) and `rmx focus return` (`:1614`): write focus marks | `write` | `SessionUnresolved`, exit 2, no mark written or consumed |
     | `rmx focus clear-subject` (`cli.py:1724`): writes subject state | `write` | `SessionUnresolved`, exit 2, subject state unchanged |
     | `rmx focus rebuild` with no `--all` / `--session` (`cli.py:1556`) | without `--dry-run`: `write` (rewrites `focus.json`); with `--dry-run`: `read` | write: `SessionUnresolved`, exit 2, no graph rewritten |
     | `rmx focus record` (`cli.py:1091-1094`) and `rmx focus clear` (`:1624-1628`), both `_stm()` with no purpose today, so `RMX_SESSION` → `default` (bug-109 r1 #m-3) | `write` | `SessionUnresolved`, exit 2; `focus clear` no longer clears the `default` ring while claiming "this session" |
     | `rmx focus tail` (`:1103`), `context` (`:1121`, then `_stm(sess)` at `:1122` with the session it resolved), `export` (`:1191`), `show` (`:1218`), `topics` (`:1245`), `detours` (`:1599`), `subject` (`:1687`), `size` (`:1735`), and `rmx recall-state` (`:13260`) | `read` | the newest ring, labelled `session: <id> (newest ring; not resolved)` |
     | write verbs `save_state` (`verbs.py:892`), `focus_note` (`:958`), `change_subject` (`:972`), and `task` push / pop / swap (`:1029`; the one call serves every action, so it passes `purpose="read" if action in ("list", "current") else "write"`) (CLI and MCP) | `write` | `verbs.SessionUnresolved` naming the sources tried; CLI exit 2 with that line; MCP tool error; nothing written to `default`, to the newest ring or anywhere else |
     | read verbs `focus` (`verbs.py:934`), `recall_state` (`:1068`), both through the str wrapper `resolve_session` today, and `task` list / current (`:1029`) | `read` | the newest ring, labelled |
     | the focus hook (`cli.py:1967`: `d.get("session_id") or stm_mod.session_id()`) | explicit envelope session | no envelope `session_id`: the hook records nothing and prints one stderr line, instead of writing to `default` |

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
       when D3 / D8 move the file (21.1 R9 D6 extends `session_pointer_anomalies`, AC-4b (v),
       (vi)), plus the two new surfaces (`rmx focus show`, the SessionStart writer's stdout).
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
4g. **Swept subagent call** (round-6 #s-1). Through the hook: a PreToolUse envelope from the
    subagent fixture (its `tool_use_id` present in the subagent transcript, refs on the command
    line) is parked by `--event tool-pre`, the sidecar's `t` is set 120 s back by the test, and
    the parent's `--event input` then sweeps it. The ring holds the swept event with
    `abandoned: true` and `origin: agent:<id>`; none of its refs is a member or label of any parent
    composite; `rmx focus topics` shows the `background:` line. Non-vacuous control: a PARENT call
    parked and swept the same way is `origin: parent` and its refs ARE members. RED at post-109
    `master`: the subagent call's refs are members of the parent's top composite.
4h. **Late completion recorded once in the graph** (round-6 #s-1). A parent call parked 120 s
    back is swept, then its PostToolUse arrives. The ring holds two lines for it (`abandoned`,
    then `late: true`), and each of its refs' node weights in `focus.json` after the PostToolUse
    equals the weight right after the sweep. RED at post-109 `master`: the weights rise (the
    second ingest).
5. **Hand-back ambient.** An `<agent-message …>` input event is dropped from the focus graph and
   kept in the ring.
6. **Envelope session.** Two rings in one tmp STM dir; the envelope names the OLDER-mtime ring;
   scan-prompt's enrichment, its STM COMPOSITE (the composite block in the same stdout) and the
   helix gate's excluded session all read the envelope's ring, through the generated scan-prompt
   hook command (round-4 #b-2). With no envelope, no pointer and no `RMX_SESSION`, enrichment and
   composite are skipped and the skip is recorded (`enrichment-unresolved`); with the composite
   forced to raise, the payload carries no composite and `_errors.jsonl` gains a
   `composite-failed` row. RED at post-bug-109 `master`: the failing assertion is the composite
   block's topics, which name the NEWER ring's terms.
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
   6c. **Unresolved writes fail loudly** (round-3 #b-1; round-4 #b-2). With no pointer and no
   `RMX_SESSION`: `rmx focus note x`, `rmx focus record --terse x`, `rmx focus clear` and
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
   `session_id`, they exit 1 (not 2) and write no digest. RED at post-109 `master`, failing
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
   R5's table, so a new caller fails until it is given a row. RED at post-109 `master`:
   `composite.py`, `helix.py`, `promote.py` and `scan.py` are listed by the first check, and the
   second finds 19 `_stm` / `_resolve_stm_session` calls with no `purpose=` (18 in commands, plus
   `_stm`'s own call at `cli.py:1083`).
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
   - the AC-4 literal rendered from a constant `general-purpose` instead of the meta file.

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
| `src/refmatrix/handoff.py` (`session_pointer_anomalies`, `:508-529`) | EXTENDED, not paralleled (round-6 #b-1): follows the error log to `stm.pointer_dir()` and reads the legacy `<root>/stm/by-pid/_errors.jsonl` for one release (21.1 R9 D6) |
| `src/refmatrix/cli.py` (`_tool_event_fields` `:1909`, `focus_hook` `:1949`, `_resolve_stm_session` `:1062`, `_stm` `:1081`, and every command in R5's table) | `_tool_event_fields` calls `stm.command_refs` (the bug-104 cause, `:1923-1927`); pass the envelope's session and `tool_use_id`; run R2's ladder with the park time from `inflight_end`; the input branch's order (R7); `--event session-start`; rebuild drops hand-backs; origin counts and the pointer-error line in `focus show`; `_resolve_stm_session` / `_stm` with a required `purpose`, each caller stating its own; `focus summarize --envelope-stdin` (exit 1 when unresolved under it); `focus record` / `clear` / `promote-edges` / `summarize` / `detour` / `return` / `clear-subject` / `rebuild` and the read commands through the resolver per R5's table; the `tool-pre` park stores `tool_use_id`, `transcript_path`, `tool_name` and the input digest, and a PostToolUse whose key was swept records ring-only with `late: true` (R2) |
| `tests/test_mcp_session_pointer.py` | EXTENDED (bug-109's file, no parallel file): AC-6b, AC-6c |
| `src/refmatrix/stm.py` (subagent attribution) | R2's rungs 2, 2b, 3: transcript tail reader, id lookup, input digest, open-call check, meta label, `background:` rendering; `inflight_begin` stores the ladder's fields, `inflight_sweep` runs the ladder per swept call and keeps the bounded `swept` key list (R2 "Swept calls") |
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
