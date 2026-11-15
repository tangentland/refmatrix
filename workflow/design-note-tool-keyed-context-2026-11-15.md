---
gmd: "0.1"
id: design-note-tool-keyed-context-2026-11-15
title: "Design note for the mod: three kinds of context, and rules injected at the tool call"
tags: [design, mod, context, injection, guardrail]
metadata:
  node_type: design-note
  created: 2026-11-15
---

# Three kinds of context; rules at the tool call {#root}

The user, 2026-11-15: "the bigger question is how to feed the right context so you know what you
need to know without having to discover the things you don't", then (Q27 = b) "I really like the
tool specific context injection. That seems like the right kind of optimization." Input to
plan-24 (the mod transition), not pre-mod work ([[plan-of-plans#freeze]]).

rel: motivates -> [[plan-24-mod-transport]]
rel: related-to -> [[plan-31-pre-mod-loose-ends#t5]]
rel: related-to -> [[feedback_injection_presentation_rules]]

## What the lead needed, by kind {#kinds}

| kind | example (session 070141d0) | how it arrived | verdict |
|---|---|---|---|
| orientation | handoff, save-state, agent briefs | read once at session start | works |
| standing rules | never run a bumped dev `rmx` live; watch long agent runs | CLAUDE.md + MEMORY.md one-liners, always loaded | works; only grows |
| **action-bound rules** | 29.1's status grammar when editing `bug_registry.md`; D19's reasons when touching `store.py`; ADR-0004's grid | **missing**: ungrammatical statuses written until review; D23 asked before the count | the gap |
| decision facts | learned-row counts; what a line of code does | pulled: queries, `rmx context`, reads | works when pull is good |

Prompt-keyword push (STM composite, content matches) mostly missed: on the prompt that started
this note, STM "Topic 1" was the prompt's own tokens (`buigger, question, feed, …`) linked to
`ui/server.py::context`. {#kinds-evidence}

## The design {#design}

1. **Rules bind to an action, and are injected when the action happens.** A rule is keyed on a
   path glob, a command shape, or an agent type, and injected before the tool runs (PreToolUse
   today; the mod's tool-call hook after the transition). Examples: editing
   `workflow/bug_registry.md` → 29.1's status grammar; a live-store `rmx` write → the backup and
   announcement rule; dispatching an agent → the brief checklist ([[orchestration#roles-briefs]]);
   editing `src/refmatrix/store*.py` → bug-107 and the derive-hash note.
2. **The rules are small and curated**, stored as `guardrail` memories (the type exists) with a
   binding field, deduplicated per session (a rule already shown is not repeated).
3. **Prompt push shrinks to what earns its bytes** (plan-31 31.5's bands); facts are pulled, and
   pull quality is plan-30's and 30.6's job.
4. **Orientation stays as is.**

## Open for plan-24 {#open}

The binding syntax; where the rule store lives (memory partition vs repo file); how a rule is
proven to fire (a must-fire fixture per rule, so a dead binding is caught); the per-session dedupe
key. {#open-body}
