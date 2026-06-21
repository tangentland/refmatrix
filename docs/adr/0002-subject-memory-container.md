---
gmd: "0.1"
id: adr-0002-subject-memory-container
title: "ADR-0002: Subject — a memory-scoped working/durable container for threads of work"
tags: [adr, memory, stm, subject]
---

# ADR-0002: Subject — memory-scoped container for threads of work {#root}

**Status:** Proposed · **Date:** 2026-06-20 · **Implementation:** spec (memory layer + stm.py + cli)

`subject` is a first-class organizing node that is a **named STM partition while
active** and a **durable LTM container/index when promoted**. It names a thread of
work ("explore external functionality") and ties every artifact produced under that
thread together across sessions.

rel: depends-on -> [[project_memory_mtype_taxonomy]]
rel: depends-on -> [[feedback_operational_content_not_in_graph]]
rel: realizes -> [[project_refmatrix_mission_charter]]
rel: related-to -> [[feedback_prefer_existing_infra]]
rel: related-to -> [[feedback_save_state_includes_promote]]
rel: related-to -> [[project_hub_ui_control_plane]]
rel: part-of -> [[adr-0000-adr-overview]]

## Context {#context}

The STM/focus stack has stashes, detours, and marks — all *within* a single Claude
session. Nothing names the broader **thread of work** that spans sessions: the
multi-day effort that produces a dozen digests and handoffs over five sessions.
Today those are findable only by recency or full-text; no node says "these all
belong to one pursuit." A thread of work needs a durable handle. {#why}

## Decision {#decision}

Introduce `subject` — one node, two faces:

- **ACTIVE (STM face) {#face-stm}.** A named STM partition. While a subject is
  current, focus events, emergent topics, detours, and marks accrue to *its* ring
  rather than the bare session ring. `change-subject` switches the active partition.
- **DURABLE (LTM face) {#face-ltm}.** A memory entity (`mtype=subject`) that
  **indexes** the artifacts promoted under it. On promote / save-state, the session's
  `session/digest` and `session/recall-state` memories
  ([[project_memory_mtype_taxonomy]]) link to the subject via `part-of`. The subject
  becomes the cross-session table-of-contents over that thread.

```
subject "explore external functionality"      mtype=subject   (durable LTM node)
  ├─ ACTIVE  → named STM partition: focus events · topics · detours · marks
  └─ DURABLE → index of promoted artifacts:
        session/digest        ──part-of──▶ subject
        session/recall-state  ──part-of──▶ subject
        decision / note       ──part-of──▶ subject
```

Subject is the *index*; topics are the *threads* within a work-burst; the mtype'd
session artifacts are the *leaves*. {#layering}

### Memory-scoped, not a concept node {#memory-scoped}

A subject organizes operational/session content.
[[feedback_operational_content_not_in_graph]] mandates that operational artifacts stay
OUT of the code/docs concept graph — they co-mention everything, go stale, drown
structure. So a subject lives in the **memory layer**, indexes its leaves through
**memory linkages**, and is invisible to `context` / `query` / `neighbors` over the
code graph.

### Data model {#data}

Reuse existing infra — no new tables ([[feedback_prefer_existing_infra]]):

- **Subject node** = memory entity. `mtype=subject`, `name` = slugged id
  (`subject_explore_external_functionality`), `content` = label + optional charter
  line, `metadata.label` = display name.
- **Containment** = existing linkage machinery. Verb `part-of` (directed: leaf →
  subject). The index is `WHERE link.type='part-of' AND link.dst=<subject>`.
- **Active-subject pointer** = a per-session value in STM state, NOT a new dotfile.
  Default unset → bare session ring (back-compat).

### STM integration {#stm}

`stm.py` already partitions by session. Extend the key `session → (session, subject)`:
`change-subject` writes the active pointer + ensures a `(session, subject)` ring;
`focus context/topics/tail/detour/mark` read/write the active ring; unset = today's
behaviour. Durable continuity rides the LTM face even when a later session's STM ring
is fresh.

### Commands {#cli}

- `rmx focus change-subject "<label>"` — set/create active subject; upsert its LTM
  node (`--new` forces fresh).
- `rmx focus subject` — current subject (label, id, leaf count, age).
- `rmx focus subjects` — list durable subjects, newest-active first.
- `rmx focus clear-subject` — revert to bare session ring.
- `rmx memory recall --subject "<label|id>"` — recall scoped to a subject's index
  (walks `part-of`); composes with `--exclude-mtype` / `--since`.

### Promote bridge {#promote}

`save-state` + `focus summarize --promote` already mint `session/digest` (save-state
also the `session/recall-state` handoff). When a subject is active, each minted
artifact gets a `part-of -> <subject>` edge. `change-subject` upserts the subject node
eagerly. No active subject → no edge; behaviour unchanged.

## Consequences {#consequences}

- Cross-session "everything on X" becomes one index walk; recall-state can report the
  active subject + its recent leaves.
- The mtype'd session artifacts gain an organizing parent without new schema.
- One more piece of per-session STM state (the active-subject pointer) to thread
  through stm.py and the focus read surfaces.
- Findability improves: subjects are durable, listed, and crosslinked to their leaves
  — the thread stops being recency-only.

## Alternatives considered {#alternatives}

- **Concept-graph node** — rejected: violates [[feedback_operational_content_not_in_graph]];
  subjects would pollute every code-concept neighborhood.
- **A new table / dotfile for subjects** — rejected: `mtype=subject` + `part-of`
  linkage reuse existing infra ([[feedback_prefer_existing_infra]]).
- **Topic as the umbrella** — rejected: collides with the existing emergent
  `focus topics` (mid-grain threads); see the naming discussion that picked
  `subject ⊃ topic`.

## Open questions {#open}

- **Project vs user-global scope.** Project-local first; promote to the hub global
  store when a pursuit crosses repos.
- **Nesting.** `part-of` already supports subject⊇subject if sub-pursuits are wanted;
  defer.
- **Auto-subject inference** from the dominant `focus topics` cluster — future nicety.

## Implementation surface {#impl}

1. `stm.py` — key `(session, subject)` + active pointer + ring resolution.
2. `cli.py` — `focus change-subject / subject / subjects / clear-subject`; thread the
   active subject into `focus context/topics/tail`.
3. memory store — register `part-of`; subject-node upsert; `recall --subject`.
4. promote path — `save_state` + `focus_summarize` add `part-of -> subject`.
5. `recall-state` / `save-state` reporting — surface the active subject.
