---
gmd: "0.1"
id: agent-brief-census-rules
title: "Census brief: every stated rule → its type T1-T10, where it is stated, its trigger event and target mechanism (plan-32 step 3)"
tags: [agent-brief, census, instructions, plan-32]
metadata:
  node_type: brief
  created: 2026-11-24
---

# census-rules: where every rule lives, and where it should {#root}

rel: implements -> [[plan-32-instruction-architecture]]

Read [[plan-32-instruction-architecture]] first: its principle and its T1-T10 table are your
classification key. You produce ONE measurement document; you change nothing else. {#role}

## Where {#where}

Clone `/Volumes/littlebig/refmatrix-census`, branch `census-2026-11-24` at master `c7550ad5`.
Write `workflow/measurements/instruction-census-2026-11-24.md` (GMD: frontmatter `gmd`, `id`,
`title`, `tags`; an anchor on every heading; `rel:` edges for citations; zero errors from
`python3 tools/gmd/lint.py <file>`), commit it in the clone. Read-only everywhere else, including
every live store. Never `find /`.

## Sources to read (all of them) {#sources}

- `~/.claude/CLAUDE.md`, `~/.claude/GMD.md`, `~/.claude/MEMORY-RULES.md`
- `CLAUDE.md`, `.claude/PROJECT_PROFILE.md`, `.claude/rules/*.md`, `.refmatrix/CLAUDE.md`
- `workflow/ORCHESTRATION.md`, `workflow/PLANNING_WORKFLOW.md`, `workflow/SELF_AUDIT.md`,
  `workflow/PLAN_GOVERNANCE.md`
- `.claude/agents/*.md` and `*.local.md` (rules only; not role prose)
- the memory dir `~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/`:
  every `feedback_*.md` and `reference_*.md` (skip `savestate_*`, `impressions/`, `project_*`)
- the installed hooks: `.claude/settings.json` and `~/.claude/settings.json` (which rules are
  already enforced or injected, and how)

## Output {#output}

1. **The table**, one row per distinct rule (merge duplicates into one row): rule (one line),
   type T1-T10, every place it is stated (file#anchor or memory id), the trigger event that makes
   it actionable (tool + pattern, path glob, state transition, or "none"), the target mechanism
   from plan-32's table, and whether something already delivers it that way (which hook/rule).
2. **Totals**: rules per type; rules stated in 2+ places; rules today reachable only by recall
   or model fetch; always-on bytes per source (`wc -c`).
3. **The first build list**: the 10 rules where moving to the target mechanism removes the most
   risk (a rule that was re-derived or broken in recent sessions — the bug registry and the POP
   L-rows name several), each with its mechanism.
4. **Not claimed**: what you did not read or could not classify.

## Report (as text, to the lead) {#report}

The commit sha, the totals, the first build list, and any rule you found contradicted between
two sources (both texts quoted, with locations).
