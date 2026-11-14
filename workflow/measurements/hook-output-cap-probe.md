---
gmd: "0.1"
id: hook-output-cap-probe
title: "R0 probe: Claude Code hook-output delivery cap (UserPromptSubmit, SessionStart, PreCompact)"
tags: [measurement, hooks, budget, plan-25, task-25.1, r0]
metadata:
  node_type: measurement
  measured: 2026-11-11
  claude_code_probe_version: "2.1.322"
  claude_code_interactive_versions: ["2.1.293", "2.1.319"]
  probe_dir: "/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/7efc36ce-3694-46b6-b30c-31160ae25396/scratchpad/r0-probe"
---

# R0 probe: hook-output delivery cap {#root}

rel: evidence-for -> [[task-25.1-recall-hook-byte-budget#r0]]
rel: evidence-for -> [[reference_hook_output_10k_cap]]

**Headline.** Claude Code checks each hook's output separately, not each event's total. A hook
whose whitespace-trimmed output is longer than **10,000 UTF-16 code units** (JavaScript
`string.length`) is not delivered whole. Exactly 10,000 is delivered whole. 10,001 is not.

- On **UserPromptSubmit** and **SessionStart**, an over-cap output is replaced by a
  `<persisted-output>` block. The block holds a header and a preview of at most 2,000 UTF-16
  units, cut back to the last newline.
- On **PreCompact**, an over-cap output is instead **truncated to its first 10,000 units**, and a
  one-line "output cut" notice is added.

The cap counts neither UTF-8 bytes nor code points. Both R0 events land in **outcome (A)**,
per-hook. {#headline}

## Method {#method}

- **Scratch project only.** Everything ran in
  `/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/7efc36ce-3694-46b6-b30c-31160ae25396/scratchpad/r0-probe/`,
  a `git init`-ed directory.
  - `run_cell.py` rewrites that directory's `.claude/settings.json` for each cell. It gives
    each probe hook its own matcher group, which is the shape rmx generates. SessionStart groups
    use the matcher `startup|resume|clear|compact`.
  - No refmatrix or fleet repo was touched, and nothing under `~/.claude/` was edited. Claude
    Code wrote its own session transcripts under
    `~/.claude/projects/-private-tmp-claude-501--Users-tholley-claude-tools-refmatrix-7efc36ce-...-scratchpad-r0-probe/`.
    {#scratch}
- **Isolation.** Every run used
  `claude -p '<question>' --model haiku --setting-sources project --tools '' --output-format json --strict-mcp-config --effort low --max-budget-usd 0.50 --session-id <uuid>`.
  - The parent session's environment was stripped first: `CLAUDECODE`,
    `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_MESSAGING_*`, `CLAUDE_EFFORT` and the related
    variables.
  - `--setting-sources project` kept out the user's global hooks and the hooks of
    `enabledPlugins`. No probe transcript has any non-probe hook record, so no caveman or tldr
    hook ran and no global hook added noise.
  - `--tools ''` stopped the model from opening the persisted file, so it could only report what
    was in its context.
  - `--bare` was not used, because it skips settings hooks. {#isolation}
- **Payload.** `payload.py <label> <N> <kind> <tag>` prints exactly N code points.
  - The first line is `R0-START-<label>-<tag>` and the last line is `R0-END-<label>-<tag>`,
    with no trailing newline. The tag is 8 random hex characters per cell.
  - The filler is 79-character lines of `a-z` (ascii), of U+4E2D (3 UTF-8 bytes, 1 UTF-16
    unit), or of U+1F600 (4 UTF-8 bytes, 2 UTF-16 units).
  - Options: append a trailing `"\n"` (`+nl`), or wrap the payload as
    `hookSpecificOutput.additionalContext` JSON (`+json`).
  - Each emission is logged to `logs/emitted.jsonl` with its code points, UTF-16 units, UTF-8
    bytes and sha256. That log is the ground truth for sizes. {#payload}
- **Evidence, strongest first.** {#evidence-order}
  1. **The API request.** Each transcript's `api-request-blob` records hold the request messages
     exactly as they were sent to the model. For each hook the analyser checks three things:
     whether the START marker is present, whether the END marker is present, and whether the
     START marker sits inside a `<persisted-output>` block.
  2. **The hook attachment record.** This is the `hook_success` record: its `stdout` is the raw
     output, and its `content` is what was delivered. Content that starts with
     `<persisted-output>` means the output was previewed.
  3. **The model's answer.** Haiku was asked for the R0-START and R0-END lines it could see, and
     for any "saved to" path.
     - Its END-marker answers matched the API request on **52 of 52** hook rows.
     - It left out a START line that the request did carry on 14 rows. That is the model failing
       to recall, not a delivery failure, so model answers only corroborate.
- **PreCompact.** `precompact.py` runs three invocations on one session id:
  1. a trivial prompt;
  2. `/compact` with `--resume`, which works in `-p` mode and fires PreCompact with
     `trigger=manual`, then SessionStart with `source=compact`;
  3. the marker question, again with `--resume`.

  The p02 run also adds a hook whose stdout tells the *summariser* to copy a token into the
  summary. {#precompact-method}
- **Budget spent.** 19 sessions, 23 `claude -p` invocations, $0.068 in total. {#budget}

## Versions {#versions}

- The headless probe ran on Claude Code **2.1.322** (`claude --version`).
- The interactive cross-check below used transcripts written by **2.1.319** (the lead session)
  and **2.1.293**. {#versions-list}

## Per-cell results {#cells}

All sizes are taken from `logs/emitted.jsonl`. "u16" is UTF-16 code units. The "result" column
is the API-request verdict; the transcript records agree on every row. "Preview body" is the
part of a `<persisted-output>` block that comes after `Preview (first 2KB):`. {#cells-key}

| cell | event | hooks × size (kind) | per hook u16 / UTF-8 B | event total u16 / B | result per hook | preview body u16 / B | model saw END |
|---|---|---|---|---|---|---|---|
| c01 | UserPromptSubmit | 1 × 9,000 (ascii) | 9,000 / 9,000 | 9,000 / 9,000 | whole | | yes |
| c01 | SessionStart | 1 × 9,000 (ascii) | 9,000 / 9,000 | 9,000 / 9,000 | whole | | yes |
| c02 | UserPromptSubmit | 1 × 10,000 (ascii) | 10,000 / 10,000 | 10,000 / 10,000 | whole | | yes |
| c02 | SessionStart | 1 × 10,000 (ascii) | 10,000 / 10,000 | 10,000 / 10,000 | whole | | yes |
| c03 | UserPromptSubmit | 1 × 11,000 (ascii) | 11,000 / 11,000 | 11,000 / 11,000 | PREVIEWED | 1,948 / 1,948 | no |
| c03 | SessionStart | 1 × 11,000 (ascii) | 11,000 / 11,000 | 11,000 / 11,000 | PREVIEWED | 1,947 / 1,947 | no |
| c04 | UserPromptSubmit | 1 × 9,000 (3-byte) | 9,000 / 26,670 | 9,000 / 26,670 | whole | | yes |
| c04 | SessionStart | 1 × 9,000 (3-byte) | 9,000 / 26,674 | 9,000 / 26,674 | whole | | yes |
| c05 | UserPromptSubmit | 1 × 10,000 (3-byte) | 10,000 / 29,640 | 10,000 / 29,640 | whole | | yes |
| c05 | SessionStart | 1 × 10,000 (3-byte) | 10,000 / 29,644 | 10,000 / 29,644 | whole | | yes |
| c06 | UserPromptSubmit | 1 × 11,000 (3-byte) | 11,000 / 32,616 | 11,000 / 32,616 | PREVIEWED | 1,948 / 5,740 | no |
| c06 | SessionStart | 1 × 11,000 (3-byte) | 11,000 / 32,620 | 11,000 / 32,620 | PREVIEWED | 1,947 / 5,739 | no |
| c07 | UserPromptSubmit | 1 × 10,001 (ascii) | 10,001 / 10,001 | 10,001 / 10,001 | PREVIEWED | 1,948 / 1,948 | no |
| c07 | SessionStart | 1 × 10,001 (ascii) | 10,001 / 10,001 | 10,001 / 10,001 | PREVIEWED | 1,947 / 1,947 | no |
| c08 | UserPromptSubmit | 1 × 6,000 code points (4-byte emoji) | 11,872 / 23,616 | 11,872 / 23,616 | PREVIEWED | 1,935 / 3,831 | no |
| c08 | SessionStart | 1 × 6,000 code points (4-byte emoji) | 11,874 / 23,622 | 11,874 / 23,622 | PREVIEWED | 1,934 / 3,830 | no |
| c09 | UserPromptSubmit | 1 × 10,000 (ascii) + trailing `\n` | raw 10,001 / 10,001 | 10,001 / 10,001 | whole (recorded `content` 10,000, so trimmed) | | yes |
| c09 | SessionStart | 1 × 10,000 (ascii) + trailing `\n` | raw 10,001 / 10,001 | 10,001 / 10,001 | whole (recorded `content` 10,000, so trimmed) | | yes |
| c10 | UserPromptSubmit | 2 × 6,000 (ascii) | 6,000 / 6,000 each | 12,000 / 12,000 | both whole | | yes ×2 |
| c11 | SessionStart | 2 × 6,000 (ascii) | 6,000 / 6,000 each | 12,000 / 12,000 | both whole | | yes ×2 |
| c12 | UserPromptSubmit | 4 × 3,000 (ascii) | 3,000 / 3,000 each | 12,000 / 12,000 | all 4 whole | | yes ×4 |
| c13 | SessionStart | 4 × 3,000 (ascii) | 3,000 / 3,000 each | 12,000 / 12,000 | all 4 whole | | yes ×4 |
| c14 | UserPromptSubmit | 4 × 9,500 (ascii) | 9,500 / 9,500 each | 38,000 / 38,000 | all 4 whole | | yes ×4 |
| c15 | SessionStart | 4 × 9,500 (ascii) | 9,500 / 9,500 each | 38,000 / 38,000 | all 4 whole | | yes ×4 |
| c16 | UserPromptSubmit | 11,000 + 9,000 (ascii) | 11,000; 9,000 | 20,000 / 20,000 | 11k PREVIEWED; 9k whole | 1,949 / 1,949 | no; yes |
| c16 | SessionStart | 11,000 + 9,000 (ascii) | 11,000; 9,000 | 20,000 / 20,000 | 11k PREVIEWED; 9k whole | 1,948 / 1,948 | no; yes |
| c17 | UserPromptSubmit | JSON `additionalContext` 10,000 + 11,000 | 10,000; 11,000 | 21,000 / 21,000 | 10k whole; 11k PREVIEWED | 1,948 / 1,948 | yes; no |
| c17 | SessionStart | JSON `additionalContext` 10,000 + 11,000 | 10,000; 11,000 | 21,000 / 21,000 | 10k whole; 11k PREVIEWED | 1,947 / 1,947 | yes; no |
| p01 | PreCompact | 500 + 11,000 (ascii) | 500; 11,000 | 11,500 / 11,500 | 500 whole; 11k CUT to its first 10,000 + notice | (no preview) | yes; no |
| p01 | SessionStart (`compact`) | 1 × 300 (ascii) | 300 / 300 | 300 / 300 | whole | | yes |
| p02 | PreCompact | 10,000 (3-byte) + 6,000 code points (emoji) | 10,000 / 29,656; 11,874 / 23,622 | 21,874 / 53,278 | 3-byte whole; emoji CUT to 9,999 u16 (5,044 code points) + notice | (no preview) | yes; no |
| p02 | PreCompact (summariser token) | `echo` line asking for `R0-SUMMARY-<tag>` | ~130 | | the token appears in the `isCompactSummary` record | | |
| p02 | SessionStart (`compact`) | 1 × 300 (ascii) | 300 / 300 | 300 / 300 | whole | | yes |

{#cells-table}

The full per-hook rows, including the transcript and API verdicts side by side, are in
`r0-probe/logs/report.md`. The raw evidence is in `r0-probe/runs/<cell>.json`, which records the
argv, transcript path, hook records, API verdict, model reply and the other hook records.
{#cells-raw}

## Conclusions per event {#conclusions}

| event | cap (whole when ≤) | unit | per-hook or per-event | over-cap behaviour | what the model gets when over cap | outcome |
|---|---|---|---|---|---|---|
| UserPromptSubmit | 10,000 | UTF-16 code units of trimmed stdout | **per hook** (4 × 9,500 = 38,000 all whole) | replaced by `<persisted-output>` | header with `Output too large (X KB)` and the file path, then a preview of at most 2,000 u16 cut back to a newline; about 2.3 k u16 in all | **(A)** |
| SessionStart | 10,000 | UTF-16 code units of trimmed stdout | **per hook** (4 × 9,500 = 38,000 all whole) | replaced by `<persisted-output>` | same as UserPromptSubmit | **(A)** |
| PreCompact | 10,000 | UTF-16 code units | **per hook** (500 whole beside 11,000 cut) | **truncated**: the first 10,000 u16 are kept, then `[PreCompact hook [<cmd>] output cut: N characters is over the 10000-character limit]` | it reaches the agent; see the PreCompact section below | n/a (not an R0 outcome event) |

{#conclusions-table}

### Cap value and unit {#unit}

- **10,000 vs 10,001.** ASCII 10,000 was delivered whole and 10,001 was previewed, on both
  events (c02, c07). {#unit-boundary}
- **Not bytes.** 10,000 three-byte characters (29,640 B) were delivered whole (c05). A byte cap
  of 10,000 would have previewed c04 and c05. {#unit-not-bytes}
- **Not code points.** 6,000 emoji code points (11,872 UTF-16 units) were previewed (c08). The
  harness's own header gives the same answer: `Output too large (11.6KB)` is 11,872 / 1,024, and
  the lead's transcript shows `(9.9KB)` for 10,093 chars, which is 10,217 B. So the size it
  prints is UTF-16 length / 1,024, not bytes. On PreCompact the cut notice says
  "11874 characters", which is the UTF-16 count. {#unit-utf16}
- **Trimmed before the check.** 10,000 characters plus a trailing newline (raw 10,001) were
  delivered whole, and the recorded `content` was 10,000 (c09). Only a trailing newline was
  tested. {#unit-trim}
- **JSON output is capped the same way.** `hookSpecificOutput.additionalContext` follows the same
  10,000-unit rule, per hook, with the same preview (c17). {#unit-json}
- **R1's byte unit is safe.** UTF-8 bytes are never fewer than UTF-16 units (1–3 B per
  single-unit character, 4 B per surrogate pair). So a budget of B UTF-8 bytes guarantees at most
  B UTF-16 units, and R1's choice to budget in UTF-8 bytes is safe against this cap.
  {#unit-r1-safe}

### Per-hook, not per-event {#per-hook}

- **Probe.** On both events, two hooks of 6,000 (12,000 in all), four of 3,000 (12,000) and four
  of 9,500 (38,000) were all delivered whole. When an 11,000 hook and a 9,000 hook shared one
  event, only the 11,000 one was previewed (c16). {#per-hook-probe}
- **Interactive, 2.1.293 and 2.1.319.** These come from the read-only cross-check below:
  - On 39 UserPromptSubmit prompts, the whole-delivered hooks summed to more than 10,000; the
    largest sum was **19,916**.
  - On 199 prompts, one hook was previewed while another hook over 1,000 was delivered whole.
  - On one SessionStart, the whole-delivered hooks summed to **13,428**.
  - On two SessionStarts, one hook was previewed while another over 1,000 was delivered whole.
  {#per-hook-interactive}
- **No higher limit seen.** No event-level cap showed up anywhere up to 38,000 units per event,
  or 20,000 + 18,000 across both events in one first turn (c16). {#per-hook-no-aggregate}

### Preview size {#preview}

- **Size and cut point.** The preview body is the first **≤ 2,000 UTF-16 units**, cut back to the
  last newline. With 80-unit lines it came to 1,947–1,949 units; with 159-unit emoji lines,
  1,934–1,935.
- **It is not 2 KB.** The "2KB" label is in UTF-16 units, not bytes: the 3-byte-character preview
  is 1,948 units = **5,740 B**.
- **Whole block.** The block the model sees, including the header and the saved-file path, came to
  2,314–2,317 units in the probe and 1,315–2,287 units in the lead's transcript. The path length
  varies.
- **Start survives, end is lost.** A previewed hook keeps its START marker and always loses its END
  marker. {#preview-facts}

### PreCompact {#precompact}

- **It reaches the agent in two ways** (p01, p02; manual `/compact` only). {#precompact-paths}
  1. **The summariser gets it.** A PreCompact hook told the summariser to include
     `R0-SUMMARY-<tag>`, and that token appears verbatim in the compact-summary record
     (`isCompactSummary: true`). In p01 the summary itself describes the PreCompact filler and the
     10,000-character cut notice. So PreCompact stdout goes into the compaction model's input. The
     transcript keeps no API record of the summariser's request, so this path is shown by the copied
     token, not by a request record.
  2. **The next agent turn gets it as a message.** After a manual `/compact`, a user message
     `<local-command-stdout>Compacted ...` carries each hook's output as
     `PreCompact [<cmd>] completed successfully: <stdout>`. That message is in the next turn's
     `api-request-blob`: the 500-unit hook arrived whole, and the 10,000 units kept from the
     11,000-unit hook arrived too. The post-compact model reported the PC-small START and END and
     the PC-big START.
- **Over the cap it is truncated, not previewed.** Each hook keeps its first 10,000 UTF-16 units
  (p01: 10,000; p02 emoji: 9,999, because the cut fell inside a surrogate pair). No
  `<persisted-output>` file is written. {#precompact-cut}
- **It is per hook.** The 500-unit hook was kept whole beside the cut 11,000-unit one, 10,500
  units in all. {#precompact-per-hook}
- **SessionStart after compaction.** SessionStart with `source=compact` fires after compaction.
  Its 300-unit probe was delivered whole. {#precompact-ss}

## Non-rmx reserve per event (read-only) {#reserve}

Source: `~/.claude/settings.json` hooks plus `enabledPlugins`, read on 2026-11-11. No caveman
script was executed, because `caveman-activate.js` writes `~/.claude/.caveman-active`.
`r0-probe/reserve.py` rebuilds both scripts' output strings from their source and the state they
read:

- the flag file, which holds `full`;
- no caveman `config.json` and no `CAVEMAN_DEFAULT_MODE`, so the mode is `full`;
- `statusLine` **is** set in `settings.json`, so no statusline nudge is printed;
- the standalone install has no `~/.claude/skills/caveman/SKILL.md`, but the plugin has its own.

The rebuilt outputs were then checked byte for byte against the lead transcript's hook records,
and they match. {#reserve-source}

| event | producer | model-visible size | notes |
|---|---|---|---|
| UserPromptSubmit | `~/.claude/hooks/caveman-mode-tracker.js` (standalone settings entry) | 121 chars / 121 B of `additionalContext` (203 B of JSON on the wire) when a caveman mode is active; nothing otherwise | the `/caveman-stats` branch blocks the prompt; it is not a per-turn producer |
| UserPromptSubmit | the **same script again**, from the enabled `caveman@caveman` plugin (`.../plugins/cache/caveman/caveman/ef6050c5e184/hooks/`, identical to the standalone copy per `diff`) | 0–121 B | the lead transcript has **one** 121-char entry on each of 46 prompts. Whether the second copy is de-duplicated or simply not delivered was NOT measured: running it was out of bounds |
| SessionStart | `~/.claude/hooks/caveman-activate.js` (standalone) | **1,213 chars / 1,215 B** (fallback ruleset, no nudge) | matches the lead transcript record exactly |
| SessionStart | the `caveman@caveman` plugin's `caveman-activate.js` | **2,014 chars / 2,024 B** (the plugin's `skills/caveman/SKILL.md`, filtered to `full`) | **R0's spec text did not list this producer**; matches the lead transcript exactly |
| SessionStart | `tldr daemon start` (startup or resume, inside a git repo) | 0 B | its stdout and stderr go to `/dev/null` |
| PreCompact | none outside rmx | 0 B | |

{#reserve-table}

**Rounded reserve, by R0's rule of rounding up to 512 B.** {#reserve-rounded}

- **UserPromptSubmit: 512 B.** The measured worst case is 242 B, if both tracker copies were
  delivered; 121 B were observed.
- **SessionStart: 3,584 B.** The measured total is 3,239 B. This is more than the provisional
  1,536 B in R1: the plugin copy adds 2,024 B, and the nudge it allowed for never fires.

Under outcome (A) the reserve does not enter any budget formula: each hook command is capped on
its own, so non-rmx hooks cannot use up rmx's room. It is recorded here because R0 asks for it, and
for use if a later Claude Code version moves to a per-event cap. {#reserve-binding}

A note outside global scope: refmatrix's own project settings run
`.claude/p20-0/compile_guardrails.py` on SessionStart. It is non-rmx, but it printed 0 B of stdout
in 14 days: all 4 recorded runs were non-blocking errors that wrote only stderr. {#reserve-project}

## Transcript evidence {#transcript-evidence}

- **Handed over by the lead (2026-11-11, session `7efc36ce`, 2.1.319).** UserPromptSubmit is
  per-hook. Two prompts delivered whole hooks that summed to 14,340 and 10,161 chars. On 15
  prompts, one hook was previewed while another over 1 kB was delivered whole. The cap lay between
  9,412 chars (the largest delivered whole) and 10,093 (the smallest previewed). The probe narrows
  that to exactly 10,000 units. {#lead-evidence}
- **Cross-check, read-only (`r0-probe/validate_transcripts.py 14`).** {#cross-check}
  - **Scope:** 119 transcripts from the last 14 days in the refmatrix project directory,
    including subagent transcripts, with 971 `hook_success` records that had non-empty stdout
    (versions 2.1.319 and 2.1.293).
  - **Rule tested:** a hook is previewed exactly when the UTF-16 length of its trimmed stdout is
    over 10,000.
  - **Result: 0 mismatches.** UserPromptSubmit had 243 previewed and 361 whole; SessionStart had
    2 previewed and 31 whole, including `SessionStart:clear` records.
  - **Nearest to the boundary:** the largest output delivered whole was 9,989 (SessionStart), and
    the smallest previewed was 10,013 (UserPromptSubmit).

## R0 outcome per event {#outcomes}

- **UserPromptSubmit → (A) per-hook cap.** The cap is 10,000 UTF-16 units, so each generated hook
  command's budget is `0.9 × 10,000` = **9,000 B**. That applies separately to `scan_cmd`,
  `focus_input_cmd` and the recall command. Inside `scan_cmd`, `scan_prompt` + `curator_status`
  together must stay within 9,000 B. {#outcome-ups}
- **SessionStart → (A) per-hook cap.** The cap is again 10,000 UTF-16 units, so each command's
  budget is **9,000 B**. That applies separately to `sess_cmd` (curator status), the recall
  command (`session_start`), `ingest-gmd --detach` and, on resume, `focus context`
  (`focus_context`). {#outcome-ss}
- **Neither event lands in (B) or (C).** `EVENT_BUDGET`, `EVENT_SPLIT` and the residual test do
  not bind on either event. {#outcome-not-bc}
- **PreCompact (channel `precompact`).** It is also per hook at 10,000 units, but over-cap output
  is cut rather than previewed, so the head is kept. `0.9 × cap` = 9,000 B applies the same way.
  {#outcome-precompact}
- **The provisional R1 values already fit.** Every value is at or under 9,000 B per command:
  `prompt_recall` 4,000; `scan_cmd` 5,000; `focus_input` 256; `session_start` 9,000;
  `focus_context` 1,500; `precompact` 9,000. This is an observation, not a choice of values.
  {#outcome-r1-fit}

## Unmeasured {#unmeasured}

1. **Auto-compaction.** Only manual `/compact` was triggered (`trigger=manual`). With
   `trigger=auto`, neither the `<local-command-stdout>` path nor the summariser path was observed.
   The summariser path probably applies to both triggers; that is an inference. {#um-autocompact}
2. **What the summariser received.** No API record of the compaction request is kept, so its
   PreCompact input is known only through the token it copied. How much of an over-cap hook the
   summariser saw is not measured directly. {#um-summariser-size}
3. **Preview of output with no newline in its first 2,000 units.** The "cut back to the last
   newline" rule was inferred from line-structured payloads only. {#um-preview-no-newline}
4. **Leading whitespace.** Only trimming of a trailing newline was tested. {#um-leading-ws}
5. **Headless boundary cells on SessionStart `resume` and `clear`.** The probe ran `startup`
   (all cells) and `compact` (300 units only). `clear` is covered only by the interactive
   cross-check, which has 0 mismatches but no record between 9,989 and 10,013. {#um-ss-sources}
6. **Interactive boundary cells.** The exact 10,000 / 10,001 boundary was measured headless on
   2.1.322. Interactive 2.1.293 and 2.1.319 are consistent but were not probed at the boundary
   itself. {#um-interactive}
7. **A higher event-level limit above 38,000 units per event,** and a session-wide limit above the
   20,000 + 18,000 delivered in c16's first turn. Neither was looked for. {#um-aggregate}
8. **Whether both caveman UserPromptSubmit tracker copies are delivered.** One entry was observed
   per prompt. The mechanism, de-duplication or non-delivery, is unknown, because the hooks were
   deliberately not run. {#um-caveman-dup}
9. **Hook stdout on a non-zero exit, or on stderr.** Not probed. {#um-nonzero}
10. **Version drift.** The constant has been verified on 2.1.293, 2.1.319 and 2.1.322 only.
    {#um-version}

## Reproduce {#reproduce}

```bash
D=/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/7efc36ce-3694-46b6-b30c-31160ae25396/scratchpad/r0-probe
cd $D
python3 run_cell.py c02-a10000 UserPromptSubmit:UPS-a10000:10000:ascii SessionStart:SS-a10000:10000:ascii
python3 run_cell.py c07-a10001 UserPromptSubmit:UPS-a10001:10001:ascii SessionStart:SS-a10001:10001:ascii
python3 precompact.py p02-precompact-unit PC-cjk:10000:cjk PC-emoji:6000:emoji --instr
python3 report.py            # per-hook table from runs/*.json
python3 reserve.py           # non-rmx reserve (read-only)
python3 validate_transcripts.py 14   # interactive cross-check (read-only)
```

{#reproduce-cmds}
