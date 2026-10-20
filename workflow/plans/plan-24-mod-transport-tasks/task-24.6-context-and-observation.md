---
gmd: "0.1"
id: task-24.6-context-and-observation
title: "Task 24.6: context and observation move into the engine — prompt.compose / prompt.submit replace the primer import, scan-prompt and per-prompt recall; tool.call replaces the focus pre/post hooks and the grep guard and reads each result; the shell hooks stay as a fallback that stands down while the mod is live, and stop hiding their failures"
tags: [task, plan-24, mod, hooks, context, observation, stm, fallback, telemetry]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.6: context and observation move in {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20; the facilities rows assigned to 24.6 in
> [[exploration-claude-code-mod-transport#facilities]] folded in; the stand-down marker, hook loudness and the
> subagent / `-p` probes added per ch-bsd s5; `refmatrix.injected` / `refmatrix.delivered` per the
> user's question of 2026-10-20 on `$.state`).
> Depends on: [[task-24.2a-hook-verbs-explicit-session]] (every verb this task calls),
> [[task-24.5-mod-core]] (handshake, routing, state contract, outbox), [[task-24.0-hook-cost-baseline]]
> (its before window closed before this deploys).
> Feeds: 24.0's after window; 24.8's re-specified held items build on these events.

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.2a-hook-verbs-explicit-session]]
rel: depends-on -> [[task-24.5-mod-core]]
rel: depends-on -> [[task-24.0-hook-cost-baseline]]
rel: implements -> [[plan-24-mod-transport#goals]]
rel: derives-from -> [[bsd-plan24-spec-review-cdcfbc3#s5]]
rel: related-to -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[feedback_install_hooks_no_claude_reaps]]
rel: implements -> [[exploration-claude-code-mod-transport#facilities]]
rel: related-to -> [[feedback_bind_capture_to_mandatory]]

## Why {#why}

The hot hooks are where the integration is thinnest: three `UserPromptSubmit` processes race each
other (the focus `input` hook writes the state that `scan-prompt` and `recall` read, in parallel),
their output is capped at ~10k characters and lands in the transcript, `focus hook --event tool`
re-parses a stdin envelope to learn what the tool did, and every failure ends `2>/dev/null ||
true`. In the engine, the prompt events can be ORDERED, context goes where the model reads it
(G2), a tool call is seen with its result (G3), and a failure is a line (G6). The shell hooks stay:
not every context is known to load a mod, and a broken mod must not leave a session with nothing.
{#why-lead}

## The event map {#event-map}

| engine event (mod) | verbs, in order | shell entry it stands in for |
|---|---|---|
| `classic.SessionStart` (its `e.source`: startup / resume / clear / compact) | `rmx_focus_observe(session-start)`; then in parallel `rmx_memory_recall(trigger=session_start, k=10, scope=both)`, `rmx_primer`, `rmx_memory(action=brief)`, `rmx_curator(status, drain)`, `rmx_sync(flush)`, and on `resume` `rmx_focus(context, top=15)`; then `$.ui.invalidate("prompt.section")` and `$.ui.invalidate("prompt.context")` | SessionStart focus / recall / resume-focus / primer + sync + curator entries |
| `prompt.compose` | append the ids `refmatrix:primer` and `refmatrix:memory` (`scope: "session"`) after every `shared` section | the `@.refmatrix/PRIMER.md` import |
| `prompt.section` on `refmatrix:primer` / `refmatrix:memory` | answer the primer text / the memory brief; cached by the engine until the next invalidate (cache-stable across turns) | — |
| `prompt.context` | append one block: session-start recall + (on resume) the focus context + the curator line; re-read by the engine on compaction and `/clear` | SessionStart's stdout |
| `prompt.submit` | `rmx_focus_observe(input, prompt)` AWAITED first; then in parallel `rmx_scan_prompt(prompt, max_tokens=2000, composite_every=3, timeout=5, skip_block_shas=<injected>)`, `rmx_memory_recall(query=prompt, trigger=prompt, k=5, scope=both, timeout=5)`, `rmx_curator(status, drain)` → `next({ ...e, context: [...] })` | the three UserPromptSubmit entries |
| `tool.call` on Edit / Write / MultiEdit / NotebookEdit / Read / Bash / Grep / Glob (by `String(e.tool)`) | `rmx_focus_observe(tool-pre)`; Bash: `rmx_shell_rewrite` → `next({ ...e, command })`; `const ran = await next(e)`; `rmx_focus_observe(tool, input, result: ran, mentions)`; edits: `rmx_sync(enqueue, files)`; Grep: `rmx_grep_teach` | PreToolUse / PostToolUse focus, enqueue, grep-rewrite-guard, grep-tool-teach |
| `turn.complete` (main loop) | `rmx_focus_observe(say, text)`, `rmx_focus(summarize, promote=True, timeout=5)`, `rmx_sync(flush)`; refresh `refmatrix.focus` | Stop's three entries |
| `turn.complete` (`e.agentId` set) | `rmx_sync(flush)` | SubagentStop |
| `session.append`, door `response`, main loop | OBSERVE: each text block ≥ 40 chars → `rmx_focus_observe(reason, text: first 2,000 chars)`; `next(e)` with `e` unchanged | — (new: reasoning capture) |
| `session.append`, door `tool-result` | `next(e)` unchanged, EXCEPT a text block matching `scrub.ts`'s secret patterns, which is rewritten with the match replaced by `[redacted:<kind>]` | — (new) |
| `session.compact`, main loop, trigger `manual` / `auto` | before `next(e)`: `rmx_focus(summarize, promote=True, timeout=30)`, then `rmx_save_state(message="auto: pre-compact checkpoint", promote=False, sync=False)`; `instructions` and `messages` passed unchanged | PreCompact ×3 |
| `tool.check` on Bash | `policy.ts`: the enforce-test-to-file and enforce-rmx-grep rules → `{ decision: "deny", reason }` or `next(e)` | the project's enforce-test-to-file / enforce-rmx-grep entries (when installed) |
| — (stays shell) | SessionStart `ingest-gmd --as-memory --detach`; the project's adr-gate and p20-0 hooks | — |

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | The input observation is awaited BEFORE scan and recall start | 21.1 R9's order (snapshot, sweep, record) exists because scan and recall read what the input hook writes; in the shell they race, in the engine they need not |
| d2 | Per-prompt context goes in `prompt.submit`'s `context` entries; session-fixed context goes in one `prompt.compose` section with `scope: "session"` | `context` is read beside the prompt and never shown, with no 10k cap (G2); a compose section that does not change across turns keeps the prompt cache |
| d3 | The session section is built at `classic.SessionStart`, which carries `source`; `session.start` fires once per process and not after `/clear` | `/clear`, `/compact` and resume each need a fresh section, and only the classic event says which happened |
| d4 | The primer and the memory brief are two plugin sections (`refmatrix:primer`, `refmatrix:memory`) whose text a `prompt.section` hook answers, cached until `classic.SessionStart` invalidates; CLAUDE.md drops `@.refmatrix/PRIMER.md`; the shell fallback prints the existing `PRIMER.md` on SessionStart instead | `prompt.section` answers are cached by the engine, so the text is cache-stable across turns; one source per context: with both, the model reads the primer twice |
| d4b | Session-start recall, the resume focus and the curator line go in a `prompt.context` block, not the system prompt | they are conversation facts that change per session; the engine re-reads that block on compaction and `/clear`, which is when they must be rebuilt |
| d4c | Core's own sections (`memory` and the rest) are never rewritten: the mod's `prompt.section` hook matches only its own two ids | Claude Code's auto-memory index is the user's file; replacing it is not this task's decision |
| d5 | `refmatrix.injected = { session, shas }` (21.1's `block_sha`s of blocks delivered this session, cap 500) is passed to `rmx_scan_prompt` as `skip_block_shas`; the VERB omits them and emits `unchanged: true` | the composite is not re-sent every turn, and the delivered events stay true because the daemon, not the mod, decides what was delivered |
| d6 | `refmatrix.delivered = { session, items: [{ name, kind, query_id }] }` (cap 2,000), filled from scan / recall answers; `tool.call` finds those names in `ran.text` and sends them as `mentions`; the daemon checks each against `delivered_in_session` (authoritative) and emits `used` with evidence `tool_result` | exact `used` detection from the result the agent actually saw (21.x); `$.state` is the prefilter, the store is the record |
| d7 | STM events go to the daemon on every call, never buffered in `$.state` (a projection only); a failed engine write goes to 24.5's outbox | d7 of 24.5: `$.state` is not a system of record |
| d8 | Stand-down: the mod exports a freshness marker into the engine's environment, `$.env.set("RMX_MOD_LIVE", "<epoch s>")` and `$.env.set("RMX_MOD_EVENTS", "start,prompt,tool,stop,compact,check")`, refreshed by the 15 s tick; every MOVED generated entry starts with a guard that exits 0 when the marker is under 45 s old and lists its event class | one cheap shell test per hook instead of a Python spawn; a mod that dies or unloads stops refreshing and the shell resumes within 45 s; no hook config edit on enable / disable |
| d9 | The marker lists only event classes the probes verified in THIS context (interactive, `-p`, subagent) | a class the mod does not receive in a context must keep its shell hook there |
| d10 | If P-env shows settings hooks do NOT inherit `$.env.set`, the marker is a file `<store>/.refmatrix/mod-live/<session_id>.json` and the guard reads `session_id` from the envelope with `jq` (stdin saved and replayed to the command); the generator emits exactly one of the two mechanisms, the one the probe chose | the types name Bash children, MCP servers and `$.process.run` as inheriting, not settings hooks; one mechanism, picked by evidence |
| d11 | Fallback loudness (G6): every generated rmx entry drops `2>/dev/null` and `|| true`; the hook twins exit 1 with one stderr line on failure (a non-blocking error Claude Code shows), never 2; backgrounded commands append stderr to `<store>/.refmatrix/hooks.stderr.log`, which 24.5's tick counts and the status line shows | the project rule (no silent failures on memory paths) and G6, on the path that stays |
| d12 | `session.compact` replaces the PreCompact entries for promote and save-state, and passes `instructions` / `messages` UNCHANGED; the PreCompact `memory recall --recent` is not called on the mod path | a PreCompact hook's stdout is not model context, so that recall fed nothing the model read; whether compaction should be told what to keep is 19.6 R8's question, re-specified by 24.8 |
| d13 | `session.append` is OBSERVE-ONLY with one exception: a `tool-result` text block matching a fixed secret-pattern list is redacted; every other row is passed as the same object | reasoning capture binds to a mandatory artifact (the assistant's own prose, [[feedback_bind_capture_to_mandatory]]); a second rewrite purpose would make the transcript the mod's to edit |
| d14 | The enforce guards move to `tool.check` as a TS port (`policy.ts`) held to the shell scripts by a shared case table, with a `.catch` that denies only when the command passes the guard's own cheap pre-filter (a test-runner word, or a leading grep) | `tool.check` decides before anything runs and needs no store; a port without a parity table would drift; a blanket fail-closed catch would deny every Bash on a mod bug |

## Requirements {#requirements}

1. **R1 — the session context (d3, d4, d4b, d4c).** `mod/src/context.ts`: on `classic.SessionStart`
   (main loop), run the event map's first row and keep the parts in module memory (not `$.state`:
   they are derived, and the contract holds four keys) keyed by session, rebuilt lazily on the next
   read after a hot reload. `prompt.compose` appends the two section ids after every `shared`
   section (the result type's rule); `prompt.section` matched on exactly `{ name:
   "refmatrix:primer" }` and `{ name: "refmatrix:memory" }` answers their text; `prompt.context`
   appends one block. Each part has a heading line naming its verb; a failed part is replaced by
   one line `[rmx] <part> unavailable: <type>: <message>` and logged (G6). Probe **P-section**
   (with R7's): whether `prompt.section` is raised for a section a plugin added in
   `prompt.compose`; if not, compose carries the text itself and the cache-stability comes from
   answering the same text until the next invalidate. {#r1}
2. **R2 — the prompt (d1, d2, d5).** `prompt.submit` (main loop; a `$.prompt.submit` from 24.5's bus
   wake carries `origin` plugin and gets the same treatment): observe → parallel scan / recall /
   curator → `next({ ...e, context: [...(e.context ?? []), scanText, recallText, curatorText] })`,
   empty parts omitted. Update `refmatrix.injected` with the returned non-`unchanged` block shas
   and `refmatrix.delivered` with returned names (both with `update`, `ifVersion`). The hook's own
   time is small (the `$` calls stop its budget clock); each verb call carries its own `deadline_s`
   (scan 5, recall 5, observe 2). {#r2}
3. **R3 — the tool call (d6).** `tool.call` per the event map; `tool-pre` and the shell rewrite
   are awaited before `next`; the post-observe is awaited after `next` resolves and before the
   hook returns `ran` unchanged (the result is never altered by observation). `mentions` = the
   delivered names found in `ran.text` by whole-identifier match. A failed observe is an outbox
   entry, never a failed tool call. Subagent calls (`e.agentId`) are observed under the main
   session with `agent_id`. {#r3}
4. **R4 — the `used` evidence (Python).** `rmx_focus_observe(tool, mentions=...)` checks each
   mention against `telemetry.delivered_in_session(session)` and emits a `used` event (evidence
   `tool_result`, `ref_query_id` = the delivering call's `query_id`) per verified name, once per
   name per turn. `tool_result` joins the evidence enum; 21.1's schema tests extend. {#r4}
5. **R5 — the stop.** `turn.complete` per the event map; the `say` text is `next(e)`'s resolved
   `text`. Summarize / promote uses `timeout=5` as the Stop hook does. Afterwards
   `refmatrix.focus` is refreshed from `rmx_focus(context, top=5)`. {#r5}
6. **R6 — the stand-down guard (d8-d10).** `hooks.py` gains `MOD_GUARD(event_class)`, prefixed
   to every generated entry the event map moves (and to the user-global grep-rewrite-guard and
   grep-tool-teach scripts that `search_hooks.py` renders). Env form:
   `[ -n "${RMX_MOD_LIVE:-}" ] && [ $(( $(date +%s) - RMX_MOD_LIVE )) -lt 45 ] && case
   ",${RMX_MOD_EVENTS:-}," in *,<class>,*) exit 0;; esac;`. Entries NOT moved carry no guard.
   `install-hooks --check` stays clean after `--apply`; the generator's docstring states the
   contract. {#r6}
7. **R7 — probes, before the GREEN commit, in a scratch project.** {#r7}
   - **P-env:** a settings hook in a session where the mod called `$.env.set` prints the variable
     to a file — present or absent decides d10.
   - **P-print:** under `claude -p --plugin-dir mod`, do `classic.SessionStart`, `prompt.compose`,
     `prompt.submit`, `tool.call` and `turn.complete` fire? Record per event.
   - **P-sub:** in a subagent, do `tool.call` (the types say yes, with `agentId`), `turn.complete`
     (with `agentId`) and `prompt.compose` (the subagent's own system prompt) fire?
   - **P-section:** R1's question (is `prompt.section` raised for a plugin-added section?).
   - The results land in `eval/mod_probe/` and set d9's per-context class list in
     `mod/src/standdown.ts` (a table, cited by the probe files), with a decision row added here.
8. **R8 — loudness (d11).** Every generated rmx command loses `2>/dev/null` / `|| true`; the hook
   twins (`focus hook`, `scan-prompt`, `curator status`, `sync`) return exit 1 + one stderr line on
   failure and exit 0 otherwise (the envelope-without-session case of `focus hook` keeps its
   recorded row AND now exits 1); backgrounded commands append stderr to `hooks.stderr.log` with a
   timestamp and the command name. {#r8}
9. **R9 — CLAUDE.md and the briefing (d4).** This repo's `CLAUDE.md` drops the
   `@.refmatrix/PRIMER.md` line; `hooks.py`'s `CLAUDE_BRIEFING` stops telling projects to add it
   and says the primer arrives from the mod or the SessionStart hook; the SessionStart fallback
   entry prints `.refmatrix/PRIMER.md` (guarded, class `start`). {#r9}
10. **R10 — 24.0's after window.** Once this deploys, the after window of
    [[task-24.0-hook-cost-baseline]] opens: its report reads the residual shell rows plus 24.2 R9's
    `invocation: "mod"` rows (the in-engine wait) and the spawn rows of 24.5 R4. The deploy sha is
    recorded in this task's implementation summary for the report's `--since`. {#r10}

11. **R11 — reasoning capture (d13).** `session.append` hook, matched `{ door: "response" }`,
    main loop only (`agentId` absent): text blocks of ≥ 40 characters are sent as
    `rmx_focus_observe(reason)` (not awaited past 2 s; a failure goes to the outbox) and the hook
    returns `next(e)` with the event it received. {#r11}
12. **R12 — secret scrub (d13).** `mod/src/scrub.ts` holds the pattern list, each named:
    `aws-access-key` (`AKIA[0-9A-Z]{16}`), `private-key` (`-----BEGIN [A-Z ]*PRIVATE KEY-----`
    through its END line), `github-token` (`gh[pousr]_[A-Za-z0-9]{36,}`, `github_pat_\w{22,}`),
    `anthropic-key` (`sk-ant-[A-Za-z0-9_-]{20,}`), `slack-token` (`xox[abpr]-[A-Za-z0-9-]{10,}`).
    Only `tool-result` rows are scanned; a match rewrites that block's text (`[redacted:<name>]`),
    logs one debug line naming the pattern (never the secret) and records a `scrub` STM event.
    A `userConfig` picker `scrub_secrets` (on / off, default on) turns it off. {#r12}
13. **R13 — compaction (d12).** `session.compact` matched on trigger `manual` and `auto`, main
    loop: the two verbs in order, each bounded (30 s, 30 s), then `return next(e)` with the event
    received; a failure is a transcript line and compaction proceeds (never `{ skip }`). The
    PreCompact shell entries take the guard class `compact`. {#r13}
14. **R14 — the guards (d14).** `mod/src/policy.ts` ports the two scripts' rules exactly (the
    test-runner and allow-prefix regexes and the tee / redirect / pipe exemptions of
    enforce-test-to-file; the learn.off checks, the rmx / piped / leading-grep rule and the corpus
    path test of enforce-rmx-grep, reading `CORPUS_PATHS` / `CORPUS_EXTS` from
    `.claude/hooks/hooks.env` via `$.fs.read`). `tool.check` on `{ tool: "Bash" }` registers only
    for a script present in the project (the generator's `want()` rule), answers `{ decision:
    "deny", reason: <the script's message> }` or `next(e)`, with d14's `.catch`. The shell entries
    take the guard class `check`. `tests/fixtures/guard_cases.json` (command, cwd fixture,
    expected allow / deny) is run by pytest against the real scripts (`bash`, the envelope on
    stdin, exit 2 = deny) and by `claude plugin test` against `policy.ts` (rendered into
    `mod/src/generated/guard_cases.ts` by `modgen`). {#r14}

## Acceptance criteria {#acceptance}

1. **AC-1 (R2, d1).** `prompt.submit` test: `rmx_focus_observe(input)` resolves before either
   scan or recall is requested (ordering read off the mocked `http.fetch` log); the next hook sees
   `context` with the scan and recall texts; a scan failure leaves recall's text and one
   transcript line. RED at base. {#ac-1}
2. **AC-2 (d5).** Two prompts in one session: the second scan request carries the first's block
   shas in `skip_block_shas`; Python-side (24.2a AC-3) the omitted block is emitted `unchanged`.
   A new session id resets `injected`. {#ac-2}
3. **AC-3 (R3, R4, d6).** A Read whose result text names a delivered memory sends it in
   `mentions`; the Python test of R4 emits one `used` event with evidence `tool_result` and the
   delivering `query_id`, and none for a name never delivered in that session (a spoofed mention).
   The tool's result reaches the model unchanged. {#ac-3}
4. **AC-4 (R1, d3).** `classic.SessionStart` with `source: "clear"` rebuilds the section (a new
   recall request), and `prompt.compose` returns it after the shared sections; a compose with no
   section built yet builds it once. {#ac-4}
5. **AC-5 (R6, d8).** Rendering the hook block: every moved entry starts with the guard for its
   class, every unmoved one does not; under `bash -c` with `RMX_MOD_LIVE=$(date +%s)` and the class
   listed, a guarded entry exits 0 without running `rmx` (a `PATH` with an `rmx` that records its
   call shows none); with the marker 60 s old it runs. `rmx install-hooks --check` is clean after
   `--apply` on a fixture project. {#ac-5}
6. **AC-6 (R8).** No generated rmx command contains `2>/dev/null` or `|| true` (a walk over the
   render); `focus hook` with an envelope lacking `session_id` exits 1 with one stderr line and
   the recorded row. {#ac-6}
7. **AC-7 (R7).** The four probe files exist, `standdown.ts`'s table cites them, and d9 / d10
   have their evidence rows. {#ac-7}
8. **AC-8 (R9).** `CLAUDE.md` has no `PRIMER.md` import; `CLAUDE_BRIEFING` does not mention it;
   the guarded SessionStart fallback prints the file. {#ac-8}

9. **AC-9 (R11, d13).** A `session.append` of a `response` row returns the identical object and
   one observe request with event `reason`; a subagent's row and a 20-character block send none.
   {#ac-9}
10. **AC-10 (R12, d13).** Over a fixture set of rows of EVERY door (prompt, command, response,
    tool-result, tool-message, delivery, attachment, hook-context, note, compaction, notice), each
    without a secret is returned as the same object (identity, not equality); a tool-result block
    with each named secret is rewritten with that name only; a response row holding a secret is
    NOT rewritten (scrubbing is tool results only); `scrub_secrets: "off"` rewrites nothing. {#ac-10}
11. **AC-11 (R13).** A mocked `session.compact` (`auto`) issues the summarize request then the
    save-state request, then calls `next` with an event deep-equal to the input; `precompute`
    issues neither; a failed save-state still calls `next`. {#ac-11}
12. **AC-12 (R14).** Every row of `guard_cases.json` gives the same verdict from the shell script
    (pytest) and from `policy.ts` (plugin test); a `policy.ts` forced to throw denies a pytest
    command and allows `ls`. {#ac-12}
13. **AC-13 (R1).** `prompt.section` for `memory` (core's) passes through untouched; for
    `refmatrix:primer` answers the primer text; after a `classic.SessionStart` with `source:
    "clear"` the next answer is rebuilt; `prompt.context` appends exactly one block. {#ac-13}

## Test strategy {#test-strategy}

TS: `mod/tests/context.test.ts`, `mod/tests/observe.test.ts`, `mod/tests/standdown.test.ts`,
`mod/tests/append.test.ts`, `mod/tests/compact.test.ts`, `mod/tests/policy.test.ts`
(answering `http.fetch` beneath the plugin with recorded host bodies, as 24.5). Python:
`tests/test_task24_6_hooks_standdown.py` (AC-5, AC-6, AC-8 over `hooks.py` /
`search_hooks.py` renders, plus `bash -c` runs of the guard), `tests/test_task24_6_used_evidence.py`
(R4). The existing hook suites (`test_hooks.py`, `test_hook_wiring.py`, `test_hooks_reproducible.py`,
`test_repo_hooks_in_sync.py`, `test_search_hooks.py`) are updated for the guard and loudness, never
skipped. Re-applying the live hooks follows [[feedback_install_hooks_no_claude_reaps]]: back up
`settings.json`, `--apply`, diff. RED first, logged to `workflow/review-output/task24_6-red.log`.
{#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `mod/src/context.ts`, `mod/src/observe.ts`, `mod/src/standdown.ts`, `mod/src/index.ts` | R1-R3, R5, R6's marker |
| `mod/src/scrub.ts`, `mod/src/compact.ts`, `mod/src/policy.ts` | R11-R14 |
| `tests/fixtures/guard_cases.json`, `src/refmatrix/modgen.py` (renders `guard_cases.ts`), `tests/test_task24_6_guards.py` | R14, AC-12 |
| `mod/tests/context.test.ts`, `observe.test.ts`, `standdown.test.ts` | AC-1..AC-4 |
| `src/refmatrix/hooks.py` | `MOD_GUARD`, guarded entries, loudness, the SessionStart primer print, `CLAUDE_BRIEFING` (R6, R8, R9) |
| `src/refmatrix/search_hooks.py` | the guard in the rendered user-global scripts (R6) |
| `src/refmatrix/cli.py` | hook twins' exit codes (R8) |
| `src/refmatrix/verbs.py`, `src/refmatrix/telemetry.py` | `mentions` → `used` with `tool_result` (R4) |
| `CLAUDE.md` | drop the primer import (R9) |
| `.claude/settings.json` | regenerated by `rmx install-hooks --apply` (never hand-edited) |
| `tests/test_task24_6_hooks_standdown.py`, `tests/test_task24_6_used_evidence.py`, the existing hook suites | AC-5, AC-6, AC-8, R4 |
| `eval/mod_probe/` | R7 |
