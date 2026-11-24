---
gmd: "0.1"
id: refmatrix/adr-0007-instruction-architecture
title: "ADR-0007: Every rule is delivered by the event that makes it actionable, from one generated source, with a recorded delivery"
tags: [adr, instructions, hooks, rules, skills, agents, injection, telemetry, templates, plan-32]
---

# ADR-0007: Instruction architecture {#root}

**Status:** Accepted (the user, 2026-11-24, L226) · **Date:** 2026-11-24, amended the same day
([[#amendments]]) ·
**Implementation:** plan-32 step 5 (queue row I1, tasks I1.a to I1.i in
[[plan-32-retriage-2026-11-24#i1-tasks]]); agent composition and distribution with queue row H1
(H1.a to H1.g in [[plan-32-retriage-2026-11-24#h1-tasks]]); the plugin transport with plan-24
(24.6, 24.7)

A rule reaches the model at the **earliest mandatory event at which it can be acted on**, from
**one source file**, **once per context**, and every delivery **writes a row**. Where a
violation can be detected the rule is **enforced** (denied or checked), not recalled. Always-on
text shrinks from 62,087 B to at most 10,000 B of principles and pointers, beside the PRIMER,
which keeps its place ([[#primer]]). The 205
rules of the census each get exactly one of ten delivery contracts ([[#contract]]). An agent
is composed from a stack-neutral core, stack packs and a project overlay, each arriving without
being fetched ([[#composition]]). All of it is generated from package data by the `hooks.py`
family, so the installed files equal the generated ones in every project ([[#generation]]).

rel: part-of -> [[refmatrix/adr-0000-adr-overview]]
rel: derives-from -> [[plan-32-instruction-architecture#principle]]
rel: derives-from -> [[instruction-census-2026-11-24]]
rel: derives-from -> [[plan-of-plans#rulings]]
rel: realizes -> [[design-note-tool-keyed-context-2026-11-15#open]]
rel: implements -> [[constitution#project-4]]
rel: depends-on -> [[task-10.3-plan-10-injection-dedup#r1]]
rel: depends-on -> [[task-compaction-as-handoff]]
rel: amends -> [[task-agent-start-context]]
rel: amends -> [[refmatrix/cat-herder-merge-2026-11-24#shape-upgrade]]
rel: related-to -> [[refmatrix/adr-0005-memory-dir-layout#hooks]]
rel: related-to -> [[plan-24-mod-transport]]
rel: related-to -> [[exploration-claude-code-mod-transport#facilities]]
rel: reinforces -> [[feedback_bind_capture_to_mandatory]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_injection_presentation_rules]]

## Context {#context}

The user's question (2026-11-24, L214): for each rule type, what is the most automatic,
reliable, repeatable and efficient way to put it in context, without relying on the model to
remember to fetch it. What the census measured at `c7550ad5`
([[instruction-census-2026-11-24#totals]]):

- 205 rules. **105** are stated in two or more files. **85** arrive only if a recall surfaces a
  memory or the model reads a doc; 14 of those are not even a title in the index. 28 have any
  hook, auto-mode rule or test guard behind them, several only in part.
- **62,087 B** load in every session. 28,093 B of that (the `MEMORY.md` index and `PRIMER.md`)
  state no rule in full.
- **19 contradictions** between sources, 5 superseded memories still in the index, and 5 stated
  rules whose installed enforcement differs from the text
  ([[instruction-census-2026-11-24#contradictions]]).

What already exists and is reused, not rebuilt: {#context-reuse}

- **Generated hooks** with an installed-equals-generated check (`hooks._claude_hook_block`,
  `render_managed`, `check`; [[constitution#project-4]]).
- **The per-command byte budget**: `hook_budget.HOOK_COMMAND_BUDGET_BYTES` = 9,500 B under the
  measured 10,000-unit cap, with a per-channel table that is checked at import.
- **A per-session "already sent" home and its one reset**, specified but not built:
  `stm/<session>.emitted/` and `stm.last_marker` ([[task-10.3-plan-10-injection-dedup#r2]]),
  which 10.2's held set and 25.3's helix repeat memory already name as theirs.
- **A read gate with a ledger**: C1 writes a pointer at SessionStart, denies every other tool
  call until the handoff is read, never traps, and records each write, pull and stand-down in
  `handoffs/ledger.jsonl` ([[task-compaction-as-handoff]]). It is the first working instance of
  the contract below.
- **`agent_id` / `agent_type` on a subagent's hook envelope** (bug-307, Claude Code 2.1.331).

Claude Code facts this ADR rests on are of three kinds. {#context-facts}

- **Verified** from the docs on 2026-11-24
  ([[plan-32-instruction-architecture#rule-types-mechanism-pre-mod-now-post-mo]], and the
  lead's check of hooks.md, skills.md and plugins/components.md the same day): path-scoped
  rules load their body on Read / Write / Edit in the main session and in subagents, not on
  Glob or Grep, and reload after compaction on the next touch; an agent's `skills:` preloads
  full skill bodies; PreToolUse deny-with-reason; a hook's `allow` **skips the permission
  prompt**; PostToolUse context beside the result; SubagentStart injection; Stop and
  SubagentStop `block`; the 10,000-character cap with a 2,000-character preview above it.
  `InstructionsLoaded` is asynchronous observation only (`file_path`, `memory_type`,
  `load_reason` including `path_glob_match` and `compact`, `trigger_file_path`): good for
  telemetry, unable to gate. A plugin ships skills, commands, agents, hooks, MCP servers,
  output styles and monitors, and **not** path-scoped rules or a `CLAUDE.md`.
- **Documented only in part.** PreToolUse `additionalContext`: every documented example pairs
  it with a `permissionDecision`; whether it is honoured without one is not documented
  ([[#open]] P1). A skill's `paths:`: whether a match loads the skill's body or only changes
  the listing is not documented (P6). Both have a verified fallback ([[#t3-fallbacks]]).
- **Not verified:** the other probes in [[#open]]. No unit that depends on a probe is built
  before the probe is committed.

## Decision {#decision}

### 1. The principle and its order of preference {#principle}

1. **Enforce** when a violation is detectable: deny the call or fail the check, with the rule
   and the right action as the reason. It costs nothing until violated and cannot be forgotten.
2. Else **inject at the trigger**: the path, tool call, agent spawn or session event at which
   the rule becomes actionable.
3. Else (no trigger exists) one **always-on line** in the principles block.
4. **Recall is never the only delivery of a rule.** Recall carries knowledge (T6), not rules.
5. A rule that gains a detector moves up this list and its lower-rank text is deleted.

### 2. The delivery contract per type {#contract}

One row per type. "Unit" is the rule's one source file ([[#generation]]). "Ledger row" is the
`outcome` written to the instruction ledger ([[#telemetry]]). {#contract-lead}

| T | Mechanism (the unit's kind) | Trigger | Once-marker | Ledger row | Size rule |
|---|---|---|---|---|---|
| T1 detectable prohibitions | `deny` or `ask` from the PreToolUse dispatcher; auto-mode rules (the p20-0 compile) only where the violation needs judgment, not a pattern | tool + pattern + who (`main`, `subagent`, `agent:<type>`) + where (project root, clone) | none: it fires on every violation | `denied`, `asked` | reason ≤ 600 B: the rule, then the command to run instead |
| T2 area conventions | `.claude/rules/<id>.md` with `paths:` | native: Read / Write / Edit of a matching file, main session and subagents | native: once per context, reloaded after compaction on the next touch | `loaded` (from `InstructionsLoaded`) | file ≤ 4,000 B |
| T3 procedures with a trigger | a skill, `.claude/skills/<id>/SKILL.md`, reached three ways: (a) by path: its `paths:` if P6 shows the body loads, until then a generated path rule; (b) a dispatcher `gate` or inject of its `#checklist`; (c) an agent's `skills:` preload ([[#t3-fallbacks]]) | (a) file touch, (b) tool + pattern, (c) agent start | (a), (c) native; (b) the delivery ledger entry ([[#once]]) | `injected`, `gated`, `suppressed_once`, `preloaded`, `invoked` | checklist ≤ 2,000 B; the skill body within the 5k-token compaction window |
| T4 completion obligations | a `check`, run by `rmx rules check` at commit, at merge, at Stop and at SubagentStop | `git commit` (two triggers, [[#t4-two-triggers]]); `git merge` and the release commit (an open BULLSHIT or GATE row on shipped code, L216; a touched security surface, [[#security-first]]; an overdue context review, [[#context-review]]); end of turn; end of a build agent | none: it runs every time; a Stop block fires once per stop | `check_failed` per failure, one `check_run` per run | message ≤ 1,000 B: the missing item and the command that supplies it |
| T5 session orientation | SessionStart blocks; C1's pointer and read gate; the review-due line ([[#context-review]]) | `startup`, `resume`, `compact`, `clear` | the event itself | the handoff ledger (exists) | pointer ≤ 1,024 B; `session_start` 9,000 B (exists) |
| T6 prompt-relevant knowledge | UserPromptSubmit scan and recall (exists) | every prompt | the composite's sent marker (exists); names-only dedupe is post-mod (10.2) | `recall-events.jsonl` (exists) | `CHANNEL_BUDGET_BYTES` (exists). Carries no rule once I1.h lands |
| T7 agent roles and per-agent facts | a stack-neutral core + stack packs + the project overlay ([[#composition]]); SubagentStart `additionalContext` for live state | agent spawn; a file touch for a pack's rule half | per `agent_id` (a spawn is a new context) | `spawned` with `agent_type`, bytes and the units carried | block ≤ 9,000 B; the brief-keyed recall is dropped first |
| T8 judgment principles | one line each in the `CLAUDE.md` principles block | launch | native | `loaded` | block ≤ 2,000 B, enforced by a size guard |
| T9 style | one SessionStart or output style | launch | native | none of ours | not ours, and done: the duplicate caveman hooks are gone (L223, [[#user-calls]]) |
| T10 reference facts | a nested `CLAUDE.md` in the directory concerned + an always-on pointer list | native: a file touch under that directory | native | `loaded` | nested file ≤ 3,000 B; pointer list ≤ 1,000 B |

**Corrections to the census's targets**, each for a stated reason: {#contract-corrections}

- **R168** (use the MCP tool for STM notes) is an inject, not a deny. A deny would block the
  only capture path whenever the MCP server is disconnected after a deploy.
- **R006** (live-store surgery needs its own go) is `ask`, not an inject: the user's go is the
  rule ([[#open]] P2).
- **R186** (no `/usr/bin/grep`) is not built before the mod. The redirect it guards is off
  while `learn.off` exists, and plan-16 replaces it with observation
  ([[plan-16-invisible-grep-shim]]).
- **R115** (open Q ids at the end of a reply) and **R159** (third edit of one file) are not in
  the first builds: neither has a detector that will not misfire. They stay prose where they
  are and are re-read once the ledger shows what a Stop check costs.
- **R183** (caveman per prompt) belongs to a plugin the user installed. It was registered
  twice; the lead removed the duplicate settings entries and the plugin's own stay (L223). No
  build.
- **R003** (subagents read-only on a live store) is a refmatrix local unit, not a packaged
  one (Q58 = b). **R007** denies Edit and Write in the deploy tree and leaves `cp` to the
  user's permission rules (Q57 = b, [[#r007-q57]]).

#### One dispatcher per event {#dispatcher}

Each hook event that delivers instructions gets **one** generated command (`rmx rules fire
--event <e>`), emitted by `hooks._claude_hook_block` beside today's entries. It reads the
envelope, matches the compiled table ([[#generation]]), and returns one of: nothing; a deny or
ask with the unit's reason; an inject. It joins `verbs.INTERNAL_CLI` (hook plumbing, L204).
The hand-written scripts under `.claude/hooks/` are a second hook source, which this layer
does not keep: `enforce-test-to-file.sh` becomes a unit in I1.c and is deleted; `adr-gate.sh`
follows as a PostToolUse unit; `enforce-rmx-grep.sh` stays until plan-16 decides it.
{#dispatcher-lead}

- **No call pays for a rule that does not apply.** The generated command starts with a shell
  prefilter built from the table's patterns (the form `hooks._handoff_cmd` already uses), and
  starts Python only on a prefilter hit. Band, measured before the first install with 24.0's
  instrument (a wrapper timestamp around the hook command): the median added wall time of a
  non-matching tool call is at most 10 ms; above that the prefilter is fixed before any unit
  ships. {#dispatcher-cost}
- **A hook never returns `allow`.** plan-32 writes "additionalContext with an allow". The
  docs say an allow skips the permission prompt, so an inject that carried one would grant
  permissions silently. A `context` inject returns `additionalContext` and no
  `permissionDecision`; whether Claude Code honours that is not documented, so `context` mode
  is built only after probe P1, with the fallbacks in [[#t3-fallbacks]]. {#dispatcher-allow}
- **Two inject modes.** `context`: the checklist rides beside the call. `gate`: the call is
  denied once with the checklist as the reason, and the retry passes (the delivery ledger
  holds the unit). `gate` is for procedures whose first step must come before the call:
  release and deploy, live-store surgery, the mutation loop. {#dispatcher-modes}
- **Deny only by JSON at exit 0; every other failure allows.** A missing table, an unreadable
  ledger, a timeout or a missing `rmx` never traps a session (C1's rule, bug-308). The failure
  is counted, and the next SessionStart says `rmx rules: dispatcher failed N times` in one
  line. A session whose `rmx` is absent runs without denies; that is said at its start, not
  hidden. {#dispatcher-failure}

#### T3's two undocumented routes and their fallbacks {#t3-fallbacks}

- **The tool-keyed inject in `context` mode waits on P1.** If Claude Code does not deliver
  context without a decision, each unit takes the fallback its binding names, all three
  verified: a procedure whose first step must precede the call uses `gate` (deny with the
  reason); a reminder that may arrive beside the result uses PostToolUse `additionalContext`
  on the triggering call; an agent's own procedure uses its `skills:` preload. P1's answer
  changes the compiled table and no unit's text.
- **The path-keyed skill waits on P6.** Until a probe shows that a `paths:` match loads the
  body, in subagents too, a file-triggered procedure (the POP row, the bug row, persisting a
  review) is delivered by a generated path-scoped rule with the same `paths:` whose body is
  the skill's `#checklist`. Rules load their body; that is verified. The skill stays the one
  source and the rule is a generated artifact under the parity gate.
- **The first T3 builds wait on neither.** `release-deploy`, `live-surgery` and
  `mutation-loop` are `gate` units; `bsd-pass`, `self-audit` and `dispatch-red-green` are
  preloads.

#### Inject once {#once}

- **Key:** (`session_id`, `agent_id` or `main`, unit id, unit sha). A changed unit is a new
  delivery. A subagent never inherits the lead's entries: its context does not hold what the
  lead was shown (the bug-307 lesson).
- **Home:** `stm/<session>.emitted/instructions.json`, in 10.3's directory, written through
  10.3's helper. No new marker.
- **Reset:** an entry older than `stm.last_marker(root, session).ts` suppresses nothing; an
  unreadable marker counts as "marker now". Compaction drops injected hook context, so it must
  drop the entry. This is why 10.3 moves forward into I1.b
  ([[plan-32-retriage-2026-11-24#r12]]).
- **Direction of error:** when in doubt, deliver again. A repeat costs bytes; a miss costs the
  rule.
- Native mechanisms (T2, T8, T10, skill preloads) keep their own once-per-context behaviour;
  the ledger covers only what the dispatcher injects.

#### Staying under the cap {#cap}

Each dispatcher command has its own channel in `hook_budget.CHANNEL_BUDGET_BYTES`, summed per
command and checked at import against `HOOK_COMMAND_BUDGET_BYTES`. Proposed: `instruction_pre`
6,000 B, `agent_start` 9,000 B, `instruction_stop` 1,000 B. When several units match one call
they are packed by declared priority, most important first, each labelled by kind. A unit that
does not fit is replaced by one pointer line (its id and the file and anchor to Read) and
logged `dropped_bytes`. The harness's preview path is never reached. The 10,000-unit cap and
the 9,500 B budget are read from `hook_budget`; no doc restates them. {#cap-body}

#### T2 needs a backstop {#t2-backstop}

A path-scoped rule does not load when a file is changed through Bash (`sed`, a heredoc), or
found by Glob or Grep. So T2 alone is advice. Every T2 rule whose violation matters names its
backstop in its unit: a T4 check or a repo guard test (`test_suite_discipline.py` for the
`tests/**` rule, `test_verb_parity.py` for the verbs rule). A T2 rule with no backstop is
labelled advisory.

#### T4 has two triggers and one implementation {#t4-two-triggers}

Git hooks are not cloned, and agents commit in `/Volumes/littlebig` clones. So the commit
check is called from two places with the same code: the generated git `pre-commit` /
`commit-msg` hook in the dev tree, and the PreToolUse dispatcher on a `git commit` Bash call,
which reaches every subagent. `rmx install-hooks --check` covers the git hooks too (bug-209).

### 3. Generation and ownership {#generation}

- **One source per rule: a unit.** A unit is one markdown file with a GMD id, so a memory or a
  doc points at it with an edge instead of restating it. The directories mirror what Claude
  Code reads, which is also the plugin layout: {#units}

  | package data, `src/refmatrix/templates/` | installed as | type |
  |---|---|---|
  | `agents/<role>.md`, a stack-neutral core | `.claude/agents/`, with a generated `skills:` list | T7 |
  | `commands/<name>.md` | `.claude/commands/` (two at user level, as today) | T3 |
  | `skills/<id>/SKILL.md` | `.claude/skills/<id>/` | T3 |
  | `skills/<role>-<stack>/SKILL.md`, a pack's role half | `.claude/skills/`, where the stack is detected | T7 |
  | `rules/<id>.md` | `.claude/rules/` | T2 |
  | `rules/stack-<x>.md`, a pack's rule half | `.claude/rules/`, where the stack is detected | T2 |
  | `triggers/<id>.md` | compiled into `.claude/rmx-instructions.json` | T1; T3's tool-keyed injects |
  | `checks/<id>.md` | compiled into the same file | T4 |

- **The template is the single source; a project adds only what is true of it alone.**
  Packaged units (agent cores, stack packs, process skills, neutral rules, triggers, checks)
  ship from `src/refmatrix/templates/`, and their installed copies are generated artifacts:
  never hand-edited, compared by the parity gate (L219). A project's own sources are its
  `.local.md` overlays and the units for procedures and prohibitions that exist only there
  (for refmatrix: the dev `rmx` against a live store, the deploy tree, the lanes, the
  release), under the same directory names in `.claude/`, with the same schema and fixtures.
  `--check` puts every installed file in one of three classes: **generated** (equal to the
  render), **drift** (a template name whose content differs: an error), **local** (a name the
  template does not have: listed, its fixtures run). A local file with a pack-shaped name is
  refused ([[#composition-rules]]). What a second project would use is promoted to the
  template, not copied. {#layers}
- **How this reads L219.** L219 puts project specifics "only in `.local.md` overlays". That
  settles agents. A project's own denies and procedures bind the lead too, so an agent overlay
  cannot hold them; this ADR treats them as the same local layer for the other kinds. Read
  more narrowly, they would move into the template behind a detection key and ship refmatrix's
  development rules to every project (Q61, [[#user-calls]]). Q58 = b already depends on the
  wider reading: a deny that applies to refmatrix only has to be a refmatrix file.
  {#layers-l219}
- **The binding lives in the unit's frontmatter:** the event, the tool, the pattern and the
  field it is matched on (`command`, `file_path`, `subagent_type`), who, where, the action
  (`deny`, `ask`, `inject` with its mode), the priority, and the census rows it carries. A
  trigger that injects a skill's checklist names the skill's anchor; the text is copied into
  the compiled file at install, so the hook reads one file and the skill stays the one source.
  {#binding}
- **Every unit proves it can fire.** Its frontmatter carries at least one `fire` envelope and
  one `pass` near-miss. One parametrized test runs every packaged unit's fixtures through the
  hook command. `rmx install-hooks --check` runs the same fixtures for a project's own units,
  so a consumer with no test suite still has the proof. Before a deny ships, its pattern is
  also replayed read-only over the last 30 days of STM tool events and the hits (counts and
  hashes) are read: each is a real violation or a pattern bug. A path glob that the 29.5 split
  kills fails its `fire` fixture instead of going quiet. {#fixtures}
- **Installed equals generated, for everything.** `render_managed` and `check` extend from the
  hook block to rules, skills, agents, commands, the compiled file and the git hooks. A
  hand-edited copy is drift, shown as a diff. Local changes belong in an overlay or a local
  unit ([[#layers]]). [[constitution#project-4]] should be widened from "hooks" to "every
  instruction artifact" when this ADR is accepted (a constitution amendment, the lead's).
  {#installed-equals-generated}
- **Every other mention is a pointer.** `CLAUDE.md`, the profile, `ORCHESTRATION.md`, agent
  files and overlays name a unit's id and do not restate it. A memory whose rule now lives in
  a unit keeps its file (the incident and the why), gains `rel: encoded-as` to the unit, loses
  its `MEMORY.md` line, and leaves the per-prompt and session-start packs
  ([[#always-on]]). {#pointers}
- **Rules live in repo files, not in the memory partition.** A deny must work in a clone with
  no store, with the daemon down, and at the version of the code that enforces it. A guardrail
  memory is where a lesson is first captured; promotion to a unit is an explicit edit. The
  p20-0 compile stays as the path for prohibitions that need a classifier's judgment (R014 to
  R018), and its efficacy stays unmeasured until someone probes it. {#not-memory}
- **Nothing loses its delivery during the move.** A rule's always-on or agent-file text is
  deleted only in a commit after its unit is installed and its `fire` fixture passes. The
  census is the checklist: at the end of I1.h every one of the 205 rows is claimed by exactly
  one unit, one principles line, or `retired`, by a script that reads the units' `census`
  fields. {#removal-order}

### 4. Agent composition {#composition}

Decided by the user as L219 ([[plan-of-plans#rulings]]): an agent definition is three layers,
so one role serves every stack in the fleet, and each layer arrives without the agent fetching
it. What was measured: ten copies of the security auditor in the fleet with ten checksums and
two overlays; Docker named on 21 lines of 8 of this repo's 13 neutral agent files, while
no fleet repo tracks a container. {#composition-lead}

| Layer | Holds | Source | Delivered by |
|---|---|---|---|
| **Core** | the role's method, its consequence rubric, its outputs. No stack word | `templates/agents/<role>.md` | the agent file at spawn |
| **Stack pack, rule half** | conventions of the stack that bind any role | `templates/rules/stack-<x>.md`, `paths:` by extension and manifest name | the native path rule, on Read / Write / Edit, in the lead and every subagent |
| **Stack pack, role half** | what this role does differently on this stack | `templates/skills/<role>-<x>/SKILL.md` | the agent's `skills:` preload; `rmx init` generates the list from the detected stacks |
| **Overlay** | this project's facts for the role | `.claude/agents/<role>.local.md`, hand-written in the project | preloaded: the generator renders it as the skill `<role>-local`, last in the `skills:` list |

Rules of composition: {#composition-rules}

- **A core holds no stack word.** A guard test reads the packaged cores for a stack-term list
  (Docker, pytest, JWT, npm, Postgres and the rest) and plants a must-fail case. Docker text
  leaves the cores for a `docker` pack, which removes C1 instead of editing around it.
- **No "read your overlay first".** That sentence is a fetch the model must remember; it
  leaves every core. The overlay arrives by preload, like the packs.
- **A cell exists only when it has content.** `<role>-<x>` is written when today's files hold
  stack text for that role (the extraction source) or an audit shows the need. The generator
  lists the cells that exist; it never installs an empty skill.
- **A preload budget.** A pack skill is at most 6,000 B. The generator sums each agent's list
  at render and fails, naming the skills, if it passes the 25k-token window in which preloaded
  bodies survive compaction.
- **Packs are template-only.** Cores, stack rules and role × stack skills live in
  `src/refmatrix/templates/` and nowhere else. A stack no pack covers is added to the
  template, never locally: `--check` refuses a local file named like a pack (`stack-*`,
  `<role>-<stack>`). An installed agent file is the core plus its generated `skills:` list, so
  the parity gate compares it with the render, not with the template's bytes.

#### Stack detection {#stack-detection}

`rmx init` and `rmx install-hooks --apply` choose the packs. The contract: {#stack-detection-lead}

1. **Inputs:** manifests at tracked paths, and a census of tracked files by extension from
   `git ls-files`. Never a directory walk; untracked, ignored and vendored files do not count.
2. **A stack is detected** by its manifest, or by at least 5 tracked files of its extensions
   (a proposed threshold; the smallest stack measured in the fleet has 31). A framework is
   detected only from a manifest's dependencies.
3. **Each pack declares its own detection** (`detect:` in its rule's frontmatter: manifest
   names, extensions, dependency names). Adding a pack adds its detection; there is no second
   table to drift.
4. **The result is recorded** in `.claude/rmx-hooks.json` (`stacks`: each with its count and
   what detected it) and printed. The project may pin `include` or `exclude` there; detection
   never overrides a pin.
5. **`--check` re-runs detection.** A stack detected but not installed, or installed but no
   longer detected, is out of sync, and the line names the command that fixes it.
6. **Nothing is silent.** A group of tracked files with no pack is printed with its count and
   counted. A repo with no tracked files (orderly today) installs cores only and says so.
   Outside a git repo detection reads manifests only, and says so.

#### The first packs {#packs-first}

From L219's fleet census; counts are tracked files. Ordered by repos served, then by risk.
{#packs-first-lead}

| # | Pack | Detected by | Rule `paths:` | First role cells | Reach |
|---|---|---|---|---|---|
| 1 | `python` (pytest folded in: every Python repo here uses it) | `pyproject.toml`, `setup.py`, `requirements*.txt`; `.py` | `**/*.py` | test-engineer, implementer, code-reviewer, security-auditor | every repo with code |
| 2 | `shell` | `.sh`; hook scripts | `**/*.sh` | security-auditor (quoting, PATH, hooks), code-reviewer | every repo |
| 3 | `postgres` | `.sql`; a Postgres driver in a manifest | `**/*.sql` | security-auditor (roles, grants, injection), implementer, test-engineer | atldb 250, cliquedb 264, portal 112, thiquet 31 |
| 4 | `node`, and `node-express` where `express` is a dependency | `package.json` | `**/*.{js,mjs,cjs,jsx,ts,tsx}` | security-auditor (web / API), test-engineer | portal 198 (Express), viascope 396 (frontend) |
| 5 | `docker` | a tracked `Dockerfile*` or compose file | those files | test-engineer, security-auditor: the text extracted from today's cores | no repo today; refmatrix when T0.9 (b) lands |

#### Security, the first instance {#security-first}

- **One canonical `ch-security-auditor` core.** Its checklist is by **surface category**: web
  and API; database roles and SQL; network daemons; device control; local IPC and CLI;
  secrets; supply chain; agent-context injection. Stack detail (JWT, Express middleware,
  Postgres grants, shell quoting) lives in `ch-security-auditor-<stack>` cells.
- **The overlay declares the project's surfaces** and their path globs, in
  `ch-security-auditor.local.md`'s frontmatter. The generator compiles them into two units.
  A trigger on the ch-bsd dispatch lists the surfaces and says to dispatch the auditor in the
  same message when the range touches them ([[#t3-fallbacks]] for its mode). A check at
  `git merge` is the backstop: the range is git's own; if it touches a surface and the ledger
  has no `spawned` row for the auditor since the branch head was committed, the merge is
  gated once with the surfaces named. The retry passes and is logged.
- **ch-bsd gains one clause,** in the `bsd-pass` skill: a security breach with a live
  consequence is BULLSHIT.
- **No declared surfaces, no dispatch units**, and `--check` says `security surfaces: none
  declared` in one line.
- **Retention** is read from the ledger's `spawned` rows per project ([[#roster-bands]]). The
  baseline audits of the other repos are the lead's, on the user's go (L219), and are not
  part of this ADR.

### 5. Distribution {#distribution}

- **Now:** `rmx init` scaffolds; `rmx install-hooks` renders, checks and applies. One engine
  for both; the `rmx template diff|upgrade` the merge review proposes is that engine's check
  and apply under another name, not a second installer. {#dist-now}
- **A project's roster** (which agents, skills and commands it installs) and its detected
  stacks are recorded in `.claude/rmx-hooks.json` with the other flags, so `--check`
  re-renders the same set. The template keeps every agent and every pack; refmatrix trims its
  own install (L214). {#roster}
- **Installed copies are generated artifacts** (L219): cores, pack rules and pack skills are
  written by the installer from `src/refmatrix/templates/`, never by hand, and a hand edit is
  drift. A project changes its behaviour through its overlay, or the template changes for
  everyone. {#dist-generated}
- **H1 is built once** because the template tree is already in plugin layout and
  `--check` is the parity gate. An upgrade shows the diff, backs the file up, and replaces it.
  The backup is part of H1: today `--force` backs up only the two user-level commands
  (`init_agents._install_user_level`) and overwrites a project file without one
  (`_install_pkg_md`). It does **not** build the three-way merge of
  [[refmatrix/cat-herder-merge-2026-11-24#shape-upgrade]]: an edited neutral file is drift by
  rule, and the plugin retires copied agents, skills, commands and hooks anyway. {#h1-once}
- **Post-mod, the plugin carries** skills (process skills and the packs' role half),
  commands and hooks from the same tree ([[exploration-claude-code-mod-transport#distribution]],
  24.7). The copy step stands down per component while the plugin is live, the rule 24.6
  already has for shell hooks. {#dist-post-mod}
- **A plugin cannot carry path-scoped rules or a `CLAUDE.md`** (the docs). So the rule half of
  every stack pack, a project's T2 rules, the nested `CLAUDE.md` files and the pointer list
  stay installed by `rmx init` / `install-hooks` after the mod, under the same parity gate.
  The installer is therefore permanent, not a bridge to the plugin, and H1's check and upgrade
  are not throwaway. A pack then has two carriers, so `--check` reports installed rules whose
  version differs from the live plugin's, on the version-and-schema handshake 24.7 already
  specifies. {#dist-rules-stay}
- **Agent cores and the per-project `skills:` list.** A plugin's agent file is one static file
  for every project, so it cannot hold a list generated from one project's stacks. Post-mod,
  either the agent files stay installed (generated, as now), or the mod registers each agent
  per project with its computed list (`$.agent.register`, read from the recorded stacks). The
  second is a 24.5 / 24.7 design point. Whether a project agent's `skills:` may name a plugin
  skill, and how plugin agents are named, is [[#open]] P10; a binding that matches an agent
  type accepts both the bare and the namespaced name from the start. {#dist-agent-lists}
- **Also installed, always:** a project's local units, its overlays and the generated
  `<role>-local` skills, and the workflow skeleton. {#dist-local}
- **Template version = rmx version.** A unit changes in a release and reaches a project at its
  install window, which stays user-gated. {#dist-version}

### 6. Usage telemetry {#telemetry}

- **One ledger per store,** `<store>/instructions/ledger.jsonl`: one line per delivery,
  appended lock-free like `query.log`. It is a file append, not a store write, so a subagent's
  hook may write it. It is not `recall-events.jsonl`, whose rows are store entities (21.1
  AC-9). Its append, reap and unreadable-line count are the helper `handoffs/ledger.jsonl`
  uses, shared, not copied. {#ledger}
- **Row:** `v`, `ts`, `session`, `agent_id`, `agent_type`, `event`, `tool`, `unit`,
  `unit_sha`, `type`, `outcome`, `bytes`, `cause`. No prompt, command or path text: hashes
  and ids only. Outcomes are the ones in [[#contract]], plus `dropped_bytes` and `error`.
  {#ledger-row}
- **Who writes:** the dispatcher (its own rows); a generated `InstructionsLoaded` entry (every
  `CLAUDE.md`, nested `CLAUDE.md` and rule load; the event is asynchronous and cannot gate, and
  its `load_reason` goes to `cause`, so a reload after compaction is told from a first load);
  the SubagentStart entry (`spawned`); the
  dispatcher on a `Skill` call or a slash command (`invoked`, [[#open]] P8). {#ledger-writers}
- **"Was it used" is derived, not emitted.** At report time: `denied` again for the same unit
  in one session (the reason did not teach); a T1 or T4 failure after that rule's own T2 / T3
  delivery in the same context (`violated_after_delivery`); for a checklist, its commands seen
  in later tool events. The join is 21.5's method ([[task-21.5-tool-used-signal]]): delivered
  rows against STM tool events, never a hook-emitted `used`. {#ledger-used}
- **The raw view** is an `instructions` view in `rmx telemetry --context`: per unit and per
  agent, skill and command, the count, bytes and last use. The review below reads it.
- **Roster bands are inputs to the review, never a removal** (the user, L225). No use in a
  project for 30 days flags an agent, skill or command for that project's roster; no use in
  any fleet store for 90 days flags it for the template. A flag is put to the user with its
  numbers and a recommended action, and the review is not complete until each flagged item
  has the user's decision. Nothing leaves a roster or the template without one. The fleet is
  read from the hub's registry, never by a tree walk. Rows are kept 90 days. {#roster-bands}
- **Later:** `bytes` per delivery is what `session.measure` tuning weighs against real
  headroom after the mod.

#### The context-effectiveness review {#context-review}

The user, L225: "a periodic context effectiveness review should be mandatory". Mandatory
means enforced, not remembered ([[#principle]]). {#context-review-lead}

**One read-only command, `rmx review context`,** produces the report. It is a verb with CLI
and MCP adapters, reads the ledgers and a store snapshot through the readers each ledger
already has, and writes nothing. Its sections are every delivery surface the ledgers measure:
{#context-review-report}

| Section | What it shows | Source |
|---|---|---|
| Injected units | per unit: fired, suppressed, dropped for bytes; denied again in one session; violated after delivery; checklist steps seen afterwards. Units that never fired in the window | the instruction ledger; 21.5's join ([[#ledger-used]]) |
| The roster | each agent, skill and command against the 30-day and 90-day bands, with a recommended action per flagged item | `spawned`, `preloaded`, `invoked` rows; the hub registry for the fleet band |
| The PRIMER | the share of discovery calls only it could have served, and the targets nothing delivered | 31.5's scorer ([[#primer]]) |
| Scan-prompt and recall | per channel and block: delivered against used | `recall-events.jsonl`; 21.1's usage report; 31.5's per-block capture |
| Always-on bytes | each source against its target in [[#always-on]], and what grew since the last review | file sizes; `loaded` rows |

A section whose instrument is not built yet prints `not measured` and the task that builds
it. It is never left out. {#context-review-unmeasured}

**The record is one dated row** in `workflow/context-reviews.md`, a GMD ledger in the repo:
the date, the window, the report's hash and headline numbers, a decision for every flagged
item, and the next due date. The file is in git so that a clone, another machine and the
release commit all see the same answer; the store would not give that. A decision that
changes scope (an agent leaves a roster, a unit is retired, a PRIMER task opens) is an L-row
in the POP first, and the review row cites it. The report prints the row's skeleton with
each flagged item marked undecided; the lead fills it from the user's answers, and a T4
check refuses a commit of a review row that leaves a flagged item undecided. That check is
what makes the roster review strong rather than a listed candidate.
{#context-review-record}

**Enforcement**, decided by the user (Q63 = a, in L225): {#context-review-enforce}

- **Due** 30 days after the newest review row, or before a major release if that is sooner.
- **Overdue, every session says so once:** a SessionStart "review due" block on `startup`
  and `resume` names the command and the days overdue (T5; under 300 B).
- **Overdue, a major release holds:** the release commit needs a review row newer than the
  last major release, as release step 1b needs no open GATE row
  ([[orchestration#release]]). It is a T4 check; an L-row may waive it for one release, and
  the release commit names the waiver.
- **Fleet:** each repo holds its own review, and the hub's nightly tick lists the overdue
  repos from its registry, in `rmx hub status` and the web UI. The hub has no nightly
  scheduler before the mod (plan-17 is post-mod), so the tick is a once-a-day pass inside
  its existing watchdog loop.
- **Bootstrap:** the gate ships in the same release as the command, so the first major
  release after it needs the first review, and none before.

### 7. The always-on budget {#always-on}

Target: **at most 10,000 B** of standing always-on text, from 54,238 B at the census. Two
things are counted apart from it, by the user's rulings: the PRIMER, which keeps its place at
today's 7,849 B until a better one is measured (L224), and the open-findings rows added after
the census (L216). With both, a session loads at most 17,849 B plus the open rows, against
62,087 B at the census. {#always-on-target}

| Source | Today | Target | How |
|---|---|---|---|
| `CLAUDE.md` | 15,989 | ≤ 4,000 | identity; the principles block (≤ 2,000 B, T8, one line per rule); the pointer list (≤ 1,000 B, T10). A size guard test holds it |
| `.claude/PROJECT_PROFILE.md` | 9,599 | 0 | the `@` import is removed. Layout, primitives and glossary go to a nested `src/refmatrix/CLAUDE.md`; commands into the skills; constraints into units; the subagent lookup text into SubagentStart. The file shrinks to identity, stack and pointers for the agents that read it |
| `.refmatrix/PRIMER.md` | 7,849 | 7,849, until a better PRIMER is measured | kept, apart from the target (L224); measured and improved, never cut on a low reading, below |
| `.claude/rules/bug-registry.md` | 867 | 0 | `paths: workflow/bug_registry.md` (its `globs:` key is not read), plus the T4 registry check |
| `MEMORY.md` | 20,244 | ≤ 3,000 | the index rule, below |
| `~/.claude/GMD.md` + `MEMORY-RULES.md` | 6,901 | ≤ 2,250 | the user, L222: `GMD.md` (2,052 B) stays always-on; `MEMORY-RULES.md` (4,849 B) moves to triggered delivery after probe P7, leaving one pointer line |
| `~/.claude/CLAUDE.md`, the ancestor `CLAUDE.md` | 638 | 638 | not ours |
| `workflow/bullshit/OPEN.md` (imported since L216, after the census) | 3,312 | its open rows | not capped: its size is the open debt. Its backfill note is history and moves to the closed ledger, by the file's own rule |

- **The PRIMER keeps its place** (the user, L224: unused content "is a signal to make the
  primer better, not reduce or drop it"). It states no rule and nothing has measured its use,
  so it is measured, read-only, with 31.5's discovery-call scorer: the share of discovery
  calls whose target only the PRIMER could have delivered (a PRIMER name that the same
  prompt's scan and recall did not deliver), and beside it the targets that neither the
  PRIMER nor scan and recall delivered. **No reading cuts or drops it.** A low reading
  (recommended: under 10%, written before the read) opens an improvement task on what the
  PRIMER selects and how it is shaped. The missed targets are its input: they say which names
  it should have held, where today's list ranks by reference count and spends lines on
  `import/json` and test-function names. The task is measured before and after on the same
  scorer, and a new shape is adopted on that reading, not on its byte count. The PRIMER stays
  at today's size until then. After the mod it is a candidate for a cache-stable section in
  the main session. {#primer}
- **`MEMORY.md` states no rule.** A memory superseded by another, or encoded as a unit, has no
  index line; the principles block is the always-on text of a T8 memory, so it has none
  either. What remains is `reference_*` pointers and the fold lines that say how to list the
  rest. The renderer today never folds a feedback memory, because the index line was its only
  delivery; that rule inverts once the unit exists. This lands in `memory_index.py` with
  26.7's render (the layout-1 renderer, so only where the `.memory-layout` marker is present),
  lowers `MAX_INDEX_CHARS` on purpose, and is announced because ADR-0005's shrink guard
  refuses a render that keeps under half its lines
  ([[refmatrix/adr-0005-memory-dir-layout#hooks]]). {#memory-index}
- **Order:** this is the last I1 task. Text leaves always-on only by [[#removal-order]].

### 8. What stays for the mod {#split}

T1 to T7 are native now. The mod is a second **transport** for the same units, not a second
design: {#split-lead}

| Mod facility | What it replaces or adds | Note |
|---|---|---|
| `tool.check`, `tool.call` | the PreToolUse dispatcher's process spawn; the result of a call for T4 | reads the same compiled table |
| `prompt.context` | T5's pointer-and-gate under the hook cap | re-read on compaction and `/clear` |
| `session.measure` | T6 budgets from real headroom (plan-19's frozen parts) | the ledger's `bytes` is its input |
| `session.compact` | the PreCompact entry that writes 10.3's marker | |
| `agent.spawn`, `$.agent.register` | SubagentStart inject; installed agent files, each with its per-project `skills:` list | [[#dist-agent-lists]] |
| `skill.prompt` | T3 checklists with live store facts | **never fired in the 2026-10-20 probe** ([[plan-24-mod-transport#probes-batch2]]): probe before 24.8 counts on it |
| `tool.describe` | the discovery-ladder pointer at the Grep tool itself (21.3) | |
| `turn.complete` | the Stop check | |
| plugin distribution | the copy step for skills, commands and hooks. Never rules or `CLAUDE.md` | 24.7; [[#dist-rules-stay]] |

**T2 and T8 do not move to `prompt.section`.** plan-32's table sends them there, but
`prompt.section` and `prompt.compose` do not fire for a subagent
([[plan-24-mod-transport#probes-batch2]]), and subagents do most of the editing. Path-scoped
rules and `CLAUDE.md` reach both, so they stay the delivery after the mod. {#split-t2}

### 9. The 19 contradictions {#contradictions}

For each: the source that wins, why, and the edit that removes the loser. "User" in the last
column means the choice is not settled by evidence ([[#user-calls]]). Numbers are
[[instruction-census-2026-11-24#contradictions]]'s. {#contradictions-lead}

| # | Wins | Why | Edit that removes the loser | Call |
|---|---|---|---|---|
| C1 Docker | `CLAUDE.md`: no container | a project fact; the Docker text is stack text in neutral files | Docker leaves every core for the `docker` pack ([[#composition-rules]]), installed only where a container file is tracked; `ch-test-engineer.md`'s appended host-venv line moves to its overlay; the lanes are refmatrix's local `lane-verify` skill. T0.9 (b) later installs the pack here | evidence |
| C2 verify lane | `CLAUDE.md` `#test-discipline` rule 9 | newer (L173 to L176); `ORCHESTRATION` `#one-suite` agrees | `ch-test-engineer.local.md`'s `lockf` sentence becomes a pointer to `lane-verify` | evidence |
| C3 ch-bsd on specs | `ORCHESTRATION` `#planning` | L165, the user's "go"; it says it wins | `CLAUDE.md` `#agent-skill-workflow` and `PLANNING_WORKFLOW` `#default-planning-path` lose the spec-round chain and point at `#planning` | evidence |
| C4 when specs are written | just in time | the user, Q55 = a (L221); L165; plan-32, C1 and C2 were all run that way | `CLAUDE.md` `#plans-pre-written`, `PLAN_GOVERNANCE` `#lifecycle-gates` and the POP's `#status-lifecycle` say: `approved` is the plan approved and its next task specced; no production code for a **task** before that task's one-page spec is approved | **user, decided** (Q55 = a) |
| C5 subagents and a live store | `PROJECT_PROFILE` `#corpus`, **in refmatrix only** | the user's ruling, 2026-11-14; its reach is the user's, Q58 = b (L221) | R003's deny is a refmatrix local unit ([[#layers]]), not a packaged one. The packaged `gmd-curator.md` is unchanged, so the nine consumers are unchanged. Here a `gmd-curator.local.md` overlay says the curator returns the ingest and sync commands for the lead to run | evidence; reach: **user, decided** (Q58 = b) |
| C6 agents and registry rows | both, scoped | an agent writes the row under an id the lead allocated (bug-301: the brief names the existing row, the isolated agent committed `93783619`) | `bug-registry.md` gets `paths:` and one sentence: the id comes from the lead. R161 rides SubagentStart | evidence |
| C7 who bumps the version | `ORCHESTRATION` `#release`: the lead, in the release commit | a bumped version on a branch is what R001 guards against | the line leaves `ch-implementer.local.md`; a deny on a version edit from an envelope with `agent_id` | evidence |
| C8 the hub after a deploy | `ORCHESTRATION` `#release` step 3 | measured: the handshake did not restart it in 90 s; used at 0.85.0 and 0.85.1 | `PROJECT_PROFILE` `#commands` points at `release-deploy`; the sentence in `feedback_deploy_tree_is_the_runtime` is corrected. If the hub is meant to restart itself, the 90 s miss is a registry row | evidence |
| C9 SKETCHY and a second round | `ORCHESTRATION` `#task` step 5 | L213, the user's F8 ruling | `feedback_proportionate_process` is amended; the one copy is the `bsd-pass` skill | evidence |
| C10 where Q ids live | `feedback_ldq_enter_pop_first` | the user, 2026-11-15; `workflow/open-questions.md` no longer exists | `feedback_track_questions_by_id` is amended: the POP's counter, across sessions | evidence |
| C11 plan D labels | `feedback_plan_d_labels_are_valid_ids` | a declared supersession | the superseded memory loses its index line; `ORCHESTRATION` `#ledgers` adds "or the plan's own D label" | evidence |
| C12 the channel for reasoning notes | the MCP tool | `feedback_mcp_first_agent_stm`; `CLAUDE.md` `#write-decisions` | `hooks.CLAUDE_BRIEFING` (the source of `.refmatrix/CLAUDE.md`) names the MCP tool first and the Bash form as the no-server fallback; a `src/` edit, in I1.d | evidence |
| C13 masking on memory-path hooks | `CLAUDE.md`: STM capture is a memory path | the user, Q56 = a (L221); STM is promoted to durable memory, so a silent capture failure loses it | the four `rmx focus hook … 2>/dev/null \|\| true` entries become counted failures surfaced once at SessionStart, exit 0: a `hooks.py` change, so it ships in I1.b's install window, not with the doc edits. `feedback_no_silent_failures` loses its carve-out (I1.a, the lead's) | **user, decided** (Q56 = a) |
| C14 suite size | none of the four | all four are stale; 5,536 was measured for the 0.85.0 README | no doc states a count: the `lane-verify` skill gives the collect command; the three other mentions are deleted | evidence |
| C15 report files from subagents | return as text; the lead persists | the harness refuses a subagent's report Write (`reference_subagent_reports_returned_as_text`) | every neutral agent file's "write the full report to `workflow/review-output/`" becomes "return it as text" ([[orchestration#reports]]). An isolated agent is its own session and keeps `REPORT.md` until A1 (b) | evidence |
| C16 docstrings | `CLAUDE.md` `#development-guidelines` | project convention over a neutral default (R094) | `ch-code-reviewer.md` defers to the project's convention; the `src/**` rule carries it | evidence |
| C17 the grep escape | the user's settings: `RMXGREP_MODE=plain` stays in the global settings | the user, Q57 = b (L221): the settings stay and the rule is reworded to match. The value is inert at the shim, which treats anything but `rich` as auto ([[instruction-census-2026-11-24#c17]]) | `feedback_rmxgrep_no_plain_escape` is amended: the global env line is the user's standing setting and is not a violation. R186's pattern loses its `env RMXGREP_MODE=` half. No settings edit | **user, decided** (Q57 = b) |
| C18 hook output budget | 9,500 B | `hook_budget.HOOK_COMMAND_BUDGET_BYTES`; the user, 2026-11-15 | `reference_hook_output_cap_measured`'s 9,000 is corrected; prose points at the constant; [[task-agent-start-context]] R3 reads its channel budget | evidence |
| C19 who mutates, and when | `ORCHESTRATION` `#task` | L164 (3), L165; L200: RED runs them after GREEN | `ch-test-engineer.local.md`'s pre-GREEN mutation sentence becomes a pointer to the `mutation-loop` skill | evidence |

Two general rules fall out, and remove the classes rather than the instances: a superseded
memory never has an index line ([[#memory-index]]); a stated rule and its installed
enforcement are one unit, so they cannot differ ([[#generation]]).
{#contradictions-general}

**R007 follows Q57 = b as well** (L221). The standing `cp … ~/refmatrix/src/…` grants in
`.claude/settings.local.json` stay, so the rule is reworded to match them: the deploy tree is
not edited in place, and a file is copied into it only under a grant the user has given.
R007's deny covers Edit and Write under `~/refmatrix/**` and leaves `cp` to the permission
rules; the "do not cp" line of `feedback_refmatrix_dev_deploy_split` is amended the same way.
One consequence to carry, not to reopen: a granted copy leaves the deploy tree dirty, so
`release-deploy`'s first step reads `git -C ~/refmatrix status --short` and names any file
that differs before the fast-forward. That keeps R011 (deploy only from a committed `master`
sha) true without touching the settings. {#r007-q57}

### Decisions that are the user's {#user-calls}

Decided by the user on 2026-11-24 (L221 to L226, [[plan-of-plans#rulings]]): {#user-calls-decided}

1. **C4** (Q55 = a): `approved` means the plan approved and the next task specced.
2. **C13** (Q56 = a): STM capture is a memory path.
3. **C17 and `permissions.allow`** (Q57 = b): the user's settings stay as they are
   (`RMXGREP_MODE=plain` in the global settings; the `cp … ~/refmatrix/src/…` grants in
   `.claude/settings.local.json`). The rules are reworded to match them, not the other way
   round ([[#contradictions]] C17, [[#r007-q57]]). The first draft recommended the opposite.
4. **The reach of R003's deny** (C5; Q58 = b): refmatrix only. This holds only with a local
   unit layer: under Q61 = b the deny would ship in the template to every project, which
   Q58 = b rules out.

5. **The user's global files** (Q59 part 1 = c, L222): `~/.claude/MEMORY-RULES.md` moves to
   triggered delivery, an inject on a write under a `*/memory/` dir, after probe P7, leaving
   one always-on pointer line; `~/.claude/GMD.md` stays always-on. The file serves every
   project, so its trigger is installed at user level beside the existing PostToolUse memory
   lint, or a project without the rmx dispatcher loses the rules. Its `#index` text changes
   with [[#memory-index]] and goes to the user together with 26.8's AC-8 text, one approval.
6. **T9** (Q59 part 2 = a, L223): done by the lead. Caveman was registered twice; the two
   `~/.claude/settings.json` entries were removed and the plugin's own hooks stay. No build.
7. **The PRIMER** (Q59 part 3, L224): never cut or dropped on a low reading; measured and
   improved ([[#primer]]).

8. **The roster bands** (Q59 part 3, the other half; L225): they are inputs to a mandatory
   periodic review and are put to the user strongly; nothing is removed automatically
   ([[#roster-bands]], [[#context-review]]). Q59 is now fully decided.

9. **The review's cadence and enforcement** (Q63 = a): [[#context-review-enforce]].
10. **The re-triage and acceptance** (Q60 = a, L226): this ADR is Accepted and
    [[plan-32-retriage-2026-11-24]] is the queue. Row 16's plan-24 revision gets no ch-bsd
    round; I1 installs in two user-gated windows.

Still open ([[plan-of-plans#questions]]): {#user-calls-open}

11. **The local layer** (Q61; [[#layers-l219]]): may a project hold its own denies, checks and
    procedure skills beside its overlays (recommended), or does L219 mean overlays only?
12. **The detection threshold** of 5 tracked files ([[#stack-detection]]), and the order of
    the first packs ([[#packs-first]]) (Q62).

## Consequences {#consequences}

- 85 rules stop depending on recall. The price is a dispatcher on every tool call, held to
  the band in [[#dispatcher-cost]].
- A deny has no escape hatch by design. A bad pattern blocks real work until the unit is
  fixed, so the replay in [[#fixtures]] is not optional. A deny never overrides a grant the
  user keeps on purpose: where the settings allow something, the unit is written to match
  (Q57 = b, [[#r007-q57]]).
- Agent files, overlays and `CLAUDE.md` get shorter and stop disagreeing, because they point
  instead of restate. The census's 105 multi-stated rules is the number to re-count.
- New standing surfaces: the instruction ledger, the compiled file, the units' fixtures. Each
  is covered by `--check`.
- The install window carries more than hooks. It stays user-gated, and its diff is readable
  before it is applied.
- An installed agent file differs per project by its generated `skills:` list, so "the same
  file everywhere" (F6's test) becomes "the same render everywhere", checked by `--check`.
- The installer outlives the mod: rules and `CLAUDE.md` cannot ride a plugin.
- The review is a standing claim on the user's time, every 30 days per repo that has one.
  The report is built to make that short: flagged items only, each with a recommendation.
  In a repo with no release, its only pressure is the session block and the hub's list.
- Isolated agents (another macOS user, their own session) get the units their clone's
  `.claude/` carries, and no dev-tree ledger rows. Their denies depend on `rmx` being on
  their PATH; [[#dispatcher-failure]] says so at their SessionStart.

## Alternatives considered {#alternatives}

- **Guardrail memories as the rule store** (the design note's sketch). Rejected: a rule would
  need the store and the daemon to be enforced, would not version with the enforcing code, and
  would not exist in a clone ([[#not-memory]]).
- **Keep hand-written hook scripts beside the generated block.** Rejected: they are not
  package data, so they differ per project (3 of 5 differ between cat-herder and refmatrix),
  and the optional-script wrapper around them is where bug-118 hid (both blocking hooks
  exited 0).
- **Wait for the mod's `tool.check` and `prompt.section`.** Rejected by L214's finding that
  T1 to T7 are native now; and `prompt.section` does not reach subagents ([[#split-t2]]).
- **Inject with `permissionDecision: allow`.** Rejected ([[#dispatcher-allow]]).
- **One agent file per role per stack.** Rejected: roles times stacks files, the ten copies
  and ten checksums again; and a repo with two stacks would need both.
- **Stack text kept in the core behind "if your project uses X".** Rejected: that is the
  Docker text today, loaded in every repo while none tracks a container (C1).
- **One always-on file, better organised.** Rejected: "works; only grows"
  ([[design-note-tool-keyed-context-2026-11-15#kinds]]).

## Open questions and probes {#open}

Each is one throwaway-session probe. Evidence is committed as field names and hashes under
`workflow/measurements/`, as the hook-cap probe was. They are I1.b's R0. {#open-lead}

| # | Probe | Decides |
|---|---|---|
| P1 | is PreToolUse `additionalContext` delivered with no `permissionDecision`, and does the permission flow stay as it was? (not documented) | `context` mode, or the fallbacks of [[#t3-fallbacks]] |
| P2 | is there an `ask` decision, and what does it do in auto mode? | R006 |
| P3 | `InstructionsLoaded` (fields documented): does it fire in a subagent with `agent_id`; for a skill load? | whose context a `loaded` row belongs to |
| P4 | can a hook entry be filtered by a command pattern before any process starts? | the prefilter's form |
| P5 | do PreCompact and SessionStart `compact` fire inside a subagent? | the ledger reset for a long subagent |
| P6 | a skill's `paths:`: is the body loaded, or only the listing changed; and in subagents? (not documented) | T3 by path: the skill's own `paths:`, or the generated rule of [[#t3-fallbacks]] |
| P7 | does a user-level rule's `paths:` match a file outside the project (the memory dir)? | how `MEMORY-RULES.md` is triggered (L222) and R099 to R103: a user-level rule, or the user-level inject |
| P8 | which event sees a skill or slash-command invocation? | the `invoked` row |
| P9 | the SubagentStart envelope: is the task prompt present? | [[task-agent-start-context#r0]] |
| P10 | how are a plugin's agents and skills named, and may a project agent's `skills:` name a plugin skill? (a plugin cannot carry rules: documented) | [[#dist-agent-lists]] |

Not probes: whether the p20-0 auto-mode rules change behaviour at all (unmeasured since they
shipped); what a Stop check costs in false blocks (read from the ledger after SubagentStop's
self-audit check has run for a week). {#open-not-probes}

## Implementation {#implementation}

Tasks, order and sizes are in [[plan-32-retriage-2026-11-24#i1-tasks]] (delivery and the review) and
[[plan-32-retriage-2026-11-24#h1-tasks]] (composition and distribution); each is specced just
in time ([[orchestration#planning]]). Constraints the specs inherit from this ADR:

- I1.b (the substrate) is a large change on a shared path (hook output): RED and GREEN in
  separate hands, mutations, one ch-bsd pass. Units after it are small: a file and its
  fixtures.
- New code goes in new modules; `cli.py` gains only a thin registration, merged before queue
  step 4's sha or after 29.5 ([[plan-of-plans#queue-quiet]]).
- 29.6 re-points the units' path globs after the split; the `fire` fixtures say which broke.
- Tests extend the existing hook test files through the hook command (`CLAUDE.md`
  `#test-discipline` rules 1 and 3).
- Stack detection and the composed render change `rmx init` / `install-hooks`, a shared path:
  a large change. Each pack after it is files and fixtures.
- An agent file is edited once: the contradiction edits that touch agent files (C1, C5, C15,
  C16) ride the core rewrite in H1.b when it is next; otherwise they go with I1.a.
- Accepted on 2026-11-24 (L226): the index rows carry the status; the amendment of
  [[constitution#project-4]] ([[#installed-equals-generated]]) is still owed, by the lead.

## Amendments {#amendments}

**2026-11-24, after the merge at `6ca154f6`** (the lead's doc check and L219): {#amend-1}

- **Doc facts** ([[#context-facts]]): a hook's `allow` skips the permission prompt;
  `additionalContext` without a decision and a skill's `paths:` body load are not documented,
  so both are probe-gated with verified fallbacks ([[#t3-fallbacks]]); `InstructionsLoaded`
  observes and cannot gate; a plugin cannot carry rules or a `CLAUDE.md`
  ([[#dist-rules-stay]]).
- **Agent composition** (L219): [[#composition]], with [[#stack-detection]],
  [[#packs-first]] and [[#security-first]]; the template as the single source of every pack
  ([[#layers]], [[#dist-generated]]); the per-project `skills:` list against a static plugin
  agent file ([[#dist-agent-lists]]).
- **Since the census:** `OPEN.md` is always-on (L216) and is counted apart from the 10,000 B
  target ([[#always-on]]); the merge and release refusal on an open finding is a T4 check
  ([[#contract]]).
- C1's edit is now the `docker` pack. Sections 4 to 8 were renumbered 5 to 9; no anchor
  changed.

**2026-11-24, the user's answers** (L221; Q55 = a, Q56 = a, Q57 = b, Q58 = b): {#amend-2}

- C4 and C13 are decided as recommended. C13's hook entries are a `hooks.py` change and ship
  in I1.b's install window.
- **C17's winner flips** to the user's settings, and R007 is reworded to match the standing
  `cp` grants ([[#r007-q57]]). No settings edit anywhere in I1.
- R003's deny is refmatrix only: a local unit and a `gmd-curator.local.md` overlay; the
  packaged curator is unchanged ([[#contradictions]] C5).
- [[#user-calls]] is split into decided and open; Q61 and Q62 are cited.

**2026-11-24, Q59** (L222, L223, L224): {#amend-3}

- **The PRIMER is never cut or dropped on a low reading** (L224). [[#primer]] keeps the
  measurement and replaces the cut bands with an improvement task, measured before and after.
  Its always-on row is today's size, and the 10,000 B target is restated apart from it
  ([[#always-on-target]]). The first draft recommended dropping or cutting it by band.
- `MEMORY-RULES.md` moves to triggered delivery after P7 and `GMD.md` stays always-on (L222);
  the global-files row is at most 2,250 B, not 500.
- T9 is done: the duplicate caveman hooks were removed by the lead (L223). No build.
- The roster bands are the open half of Q59.

**2026-11-24, the review** (L225; Q63 = a): {#amend-4}

- A **mandatory context-effectiveness review** ([[#context-review]]): one read-only command,
  `rmx review context`, over every measured delivery surface; a dated row in
  `workflow/context-reviews.md` with the user's decisions; enforcement as the user decided
  it (Q63 = a): every 30 days or before a major release, a SessionStart block when overdue,
  a major-release hold, the hub's nightly list.
- [[#roster-bands]]: the bands are the review's inputs, put to the user with a recommended
  action each; never an automatic removal. Q59 is fully decided (L222 to L225).
- Builds: the report and the record are a new task, I1.i; the release hold and the
  undecided-item check join I1.e.

**2026-11-24, accepted** (L226; Q60 = a): {#amend-5}

- Status is Accepted and the re-triage is the queue. Open after acceptance: Q61 (the local
  layer) and Q62 (the detection threshold and pack order); probes P1 to P10 remain I1.b's
  first step. The amendment of [[constitution#project-4]] named in
  [[#installed-equals-generated]] is the lead's.
