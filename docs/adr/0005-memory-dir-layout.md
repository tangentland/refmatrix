---
gmd: "0.1"
id: refmatrix/adr-0005-memory-dir-layout
title: "ADR-0005: The curated memory dir is laid out by type and lifecycle; a topic is a derived subject, never a folder"
tags: [adr, memory, memory-dir, layout, save-state, subjects, bridge, memory-index]
---

# ADR-0005: Curated memory dir layout {#root}

**Status:** Proposed · **Date:** 2026-11-09 · **Implementation:** plan-26 tasks 26.1-26.8
(`src/refmatrix/memory_layout.py` first, 26.1); the fleet follows in plan-27

The curated memory dir (`~/.claude/projects/<slug>/memory/`) is organised into folders by
`metadata.type` and by lifecycle. A memory's store identity stays its frontmatter `id`, so a
folder never changes which row a file is. What a memory is ABOUT (its topic) is a derived
ADR-0002 subject reached by a `part-of` edge. A memory can have many topics, so a topic is never
a folder. Every new on-disk behaviour is gated on a per-dir marker, `.memory-layout`, so a
deploy changes no un-organised dir's files.

rel: depends-on -> [[refmatrix/adr-0002-subject-memory-container]]
rel: related-to -> [[refmatrix/adr-0003-canonical-partition-layout]]
rel: part-of -> [[refmatrix/adr-0000-adr-overview]]
rel: derives-from -> [[plan-26-memory-organisation]]
rel: specified-by -> [[task-26.0-adr-memory-dir-layout]]
rel: depends-on -> [[task-19.4-keep-derived-layers-current]]
rel: related-to -> [[task-19.3-subject-tiered-index]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r1-96feccd]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r2-8af766a]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r3-696c3cb]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r4-f89e640]]
rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]
rel: derives-from -> [[bsd-plan26-27-spec-confirm-r6-lite-d396317]]
rel: reinforces -> [[feedback_decay_never_loses_knowledge]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]

## Context {#context}

The user decided on 2026-11-08 that the memory dir is organised by TYPE (lifecycle) in folders,
never by topic, and that topics come from derived subjects
([[plan-26-memory-organisation#context]]). What the plan measured before deciding
([[plan-26-memory-organisation#measured]]):

- **The refmatrix dir is flat.** 291 top-level `.md` files: 40 save-states plus 250 typed files;
  `impressions/` holds 67. Every save-state reader and writer is top-level only
  (`handoff.py:371-373`, `:491`, `:104`), and `memory_index.collect` globs `*.md` plus
  `impressions/*.md` only.
- **A precedent already exists.** viascope's memdir holds 146 memories in `feedback/` (65),
  `project/` (68), `reference/` (9) and `impressions/` (3). Its `MEMORY.md` has never been wiped
  only because viascope has never run a save-state: on a copy, `memory_index.write` turned 157
  lines / 61 links into 1 line (ch-bsd r1).
- **Store identity is the frontmatter `id`, not the path.** The bridge writes
  `store.add_memory(name=doc.doc_id, ...)` and the memory entity's `path` is NULL. Moving a file
  therefore never changes which row it is, and no code path forgets a moved memory. The risk of
  a move is STALE state (the old `source_path` and per-anchor concept paths survive a move with
  unchanged bytes), not loss.
- **The bridge walks dot-dirs.** `collect_gmd_files` excludes only `MEMORY.md`; a
  `.organise-rollback-1/x.md` inside a memdir was ingested ([[bsd-plan26-27-spec-review-r1-96feccd#s3]]).
- **Regeneration drops hand-written index prose and path-keyed hooks.** Non-entry lines lost on
  regeneration: viascope 62, cliquedb 29, viascope2 12, cliquet 8. Curated hooks are keyed by
  relative path, so a moved file loses its hook.
- **Some memdirs are git-tracked** (viascope by its repo; two refmatrix files and 93 stale
  entries by `~/.claude`) ([[plan-26-memory-organisation#git-tracked]]).
- **Two definitions of "newest" save-state** exist: recall-state by mtime, `memory_index` by
  `created` then mtime.

None of this is a topic problem. It is a layout problem with one identity rule already in place,
and five safety gaps (walk, prose, hooks, store resolution, tracked dirs) that any move exposes.

## Decision {#decision}

### The folder table {#folders}

The memory dir's layout, version 1:

| folder | holds `metadata.type` | kind | created |
|---|---|---|---|
| `feedback/` | `feedback` | type folder | by organise |
| `project/` | `project` | type folder | by organise |
| `reference/` | `reference` | type folder | by organise |
| `user/` | `user` | type folder | on first use |
| `guardrail/` | `guardrail` | type folder | on first use |
| `impressions/` | `impression` | lifecycle collection | already exists (refmatrix, cliquedb, cliquet) |
| `savestates/` | `session/recall-state` | lifecycle collection | new |

Top-level files that are NOT memories: `MEMORY.md` (the flat index; not GMD, per MEMORY-RULES),
`.memory_hooks.json` (the curated-hook sidecar) and `.memory-layout` (the marker,
[[#marker]]).

**Naming rule {#naming}.** A **type folder** is singular because it names exactly one
`metadata.type` value (viascope's precedent). A **lifecycle collection** is plural because it is a
machine-written series of the same kind (`impressions/` already exists in three dirs under that
name). Nothing in the table is a topic, and no topic is ever added to it. A change to this table
is a new layout version and needs an ADR that amends this one.

### Identity {#identity}

A memory's store identity is its frontmatter `id` (which MEMORY-RULES already requires to equal
the filename stem). Its folder is never part of that identity: no row key, link, vector, decay
record or hook key contains the folder. Moving a file between folders changes only the row's
`source_path` (and the per-anchor concept `path`s), which the bridge refreshes in place
([[task-26.2-bridge-move-safety]]). Two files claiming one `id` are a counted, named refusal,
never a silent last-writer-wins.

### Topics are subjects, never folders {#topics}

A **topic** here means what a memory is about. It is realised as an ADR-0002 subject: the memory
is a leaf with a `part-of` edge to a `mtype=subject` node
([[refmatrix/adr-0002-subject-memory-container#data]]). A memory can carry many such edges, which
is exactly why a topic cannot be a folder: a file lives in one folder.

- Subjects come from `rmx memory compile` (derived) or from `focus change-subject` (declared,
  ADR-0002). This ADR adds no new subject mechanism.
- Every compiled subject carries `metadata.compiled_scope`. A compile prunes and marks stale only
  within its own scope, so the memory compile and the impression-pattern compile cannot destroy
  each other (plan-26 B3; [[task-26.6-compile-subject-hygiene]]).
- A compiled subject left with no leaves is marked `metadata.stale = true` with `stale_since`
  ([[task-19.4-keep-derived-layers-current]] R5). It is never deleted by compile; removal goes
  only through plan-22's audited path ([[task-22.1a-provenance-free-classes#r1]]).
- Wording note: this "topic" is not ADR-0002's emergent `focus topics` (mid-grain STM threads).
  ADR-0002 keeps that word for STM; this ADR uses it only for the user's question "what is this
  memory about", and answers it with ADR-0002's own `subject`. No ADR-0002 term is redefined.

### Folder authority {#authority}

Plan Q3 ([[plan-26-memory-organisation#open-questions]]):

- **`savestates/` is authoritative.** A file under `savestates/` (or a legacy top-level file
  whose `id` starts with `savestate_`) is a `session/recall-state` whatever its frontmatter says.
  The bridge stores that mtype and counts each override; `organise --apply` corrects the file's
  `metadata.type` while preserving its mtime and `updated:`
  ([[task-26.4-savestate-mtype-normalisation]]). This is what keeps hand-typed save-states out of
  hook-mode recall.
- **Every other folder is report-only.** A `project`-typed file in `feedback/` is not re-typed.
  `rmx memory organise --check` reports it as a `folder/type mismatch`; the frontmatter type
  stays authoritative for the row.

### One walk {#one-walk}

`src/refmatrix/memory_layout.py` is the single place the folder table lives
([[task-26.1-layout-module-and-index-walk]]). Its `iter_memory_files(memdir)` is the ONLY walk
of a memory dir:

- The bridge (every memory call site of `collect_gmd_files`, including prestage), `memory_index`
  and `handoff` all use it. No caller keeps its own `glob`/`rglob`.
- It yields `.md` files recursively, and never yields `MEMORY.md`, `README.md`, a dotfile, or
  anything under a dot-directory (ch-bsd r1 #s3). A dot-dir inside a memdir is never a memory
  store.
- Save-states are read through `iter_savestates(memdir)` in the same module, with the one
  ordering in [[#newest]].

### Memdir to store resolution {#store-resolution}

The store a memdir belongs to is resolved from its UNRESOLVED path
`~/.claude/projects/<slug>/memory` via the projects slug (`_root_from_projects_slug`), never from
the caller's cwd (plan-26 B2; [[task-26.5-memory-organise-verb]] AC-1).

- The path is never `.resolve()`d: a symlinked memdir (viascope's) resolves outside `projects/`
  and the lookup would fail.
- A path that is not under `~/.claude/projects/<slug>/` is a hard error that names the fix. It
  never silently becomes "no store". This governs every explicit memdir argument: the organise
  verb's (26.5 AC-1) and R-264a's file/subdir resolution for `ingest-gmd --as-memory`. An explicit
  `--as-memory` call keeps its own store behaviour and refusals.
- A well-formed slug that matches no store root is **file-only**: files are organised, the
  bridge is not run, and the output says so.
- **The flagless-walk carve-out (amended 2026-11-13, bug-220, [[#amendments]]).** A walk WITHOUT
  `--as-memory` that reaches a memory dir never hard-errors on it. It resolves the store from the
  memdir's unresolved form with a non-raising variant of the same resolver. A slug that matches no
  root, or a marker dir with no slug form, is file-only there: counted and named, the walk
  continues. The home memdir (the hub's global store) is held, counted and named, until plan-27
  Q4 is answered ([[task-26.5-memory-organise-verb#r-220c]]). {#store-resolution-walk}
- The resolved store's memory lands in that store's own default (ACTIVE) partition, which is
  where ADR-0003 already puts memory ([[refmatrix/adr-0003-canonical-partition-layout#co-reside]]).
  This ADR does not touch the partition layout.

### Hooks are keyed by memory id; index prose is carried {#hooks}

Curated hooks (`.memory_hooks.json`) are keyed by the memory's `id`, not its relative path, so
a move never loses a hook (plan-26 B4). Hand-written `MEMORY.md` prose (any non-blank line that
is not an entry, pointer or fold line) is carried across a regeneration and never dropped. A
content-line shrink guard leaves the index untouched, and says why, when a render would keep
fewer than half its content lines or lose any prose line.

Both guarantees are part of the layout-1 renderer and therefore apply where the marker is
present ([[#marker]]). Readers accept both sidecar key shapes (path and id) in every dir.

### Git-tracked memory dirs {#git-tracked}

When a memdir is tracked by a git repo (the owning repo of its resolved path), every move is a
`git mv` staged in that repo, and the marker is staged with it. Nothing commits on the user's
behalf; the user makes the commit. A move in a tracked dir is never a delete plus an untracked
file. Rollback there is `git restore` / `git mv` back, not an archive overwrite (plan-26 S1).

### Backups and asides live outside the memdir {#asides}

Every backup archive and every file moved aside (a rollback's kept-current conflict copy, a
rolled-back marker) lives under `~/.refmatrix/backups/memory-organise/`, never inside a memdir
(plan-26 S3). Anything left inside a memdir is a live memory to the bridge, and would trip the
duplicate-id refusal.

### Legacy flat dirs stay readable {#legacy}

A flat (pre-ADR) memdir stays readable forever. Every reader falls back to the legacy shape:
`iter_savestates` reads `savestates/*.md` and top-level `savestate_*.md`; recall-state resumes
from either; `load_hooks` reads path-keyed sidecars. There is never a hard cut that makes a flat
dir unreadable.

### The layout marker {#marker}

`<memdir>/.memory-layout` records three things: the layout version (`1`, this ADR), the date the
dir was organised, and the path of the backup archive taken before the moves. Only
`rmx memory organise --apply` writes it; a rollback moves it aside ([[#asides]]). It is a dotfile,
so it is never a memory ([[#one-walk]]). `memory_layout.is_organised(memdir)` is the one test of
it.

**Encoding (pinned 2026-11-09, orchestrator, closing the 26.0 open question so 26.1's reader and
26.5's writer agree):** one JSON object, UTF-8, written atomically (tmp + rename):
`{"layout": 1, "organised": "<ISO-8601 datetime with offset>", "backup": "<absolute path>"}`.
`is_organised` returns True only for a file that parses with `layout == 1`. A marker that
exists but does not parse, or names another layout version, is a hard error naming the file —
never read as "not organised" (a silent fallback would re-enable the old renderer over an
organised dir). Extra keys are ignored, so a later layout can add fields. {#marker-encoding}

**Every NEW on-disk behaviour applies only where the marker is present** (r2 s2):

- save-state writes go into `savestates/`, and a legacy top-level save-state for the same session
  is moved into it ([[task-26.3-savestate-subfolder]]);
- the new `MEMORY.md` renderer (carried prose, the content-line guard, later 19.3's subject
  blocks) and the id-keyed hooks sidecar writer;
- index regeneration on every bridge write, and on every compile apply (19.4 R2 and R3);
- the `source_path`-aware resume gate's refresh writes ([[task-26.2-bridge-move-safety]]).

**A dir without the marker keeps the pre-ADR behaviour exactly**, including the old renderer,
its prose-dropping compaction and its path-keyed sidecar write (r3 s1, m3, m4). The earlier
"guards that only refuse apply everywhere" clause (r2) is withdrawn: with the old renderer every
prose line counts as lost, so such a guard would refuse every index write in viascope, cliquedb,
viascope2 and cliquet while `_ss_update_index` kept appending.

**What reaches every dir regardless of the marker** (plan-26 r4 s1, m3):

- **Readers are dual**: both layouts, both sidecar key shapes. A reader writes no file.
- **The walk is `iter_memory_files`** for the bridge and for `memory_index.collect`. It only
  removes dot-path and `README.md` files (0 found fleet-wide) and only ADDS nested entries. It is
  deliberately ungated: gating `collect` would keep viascope's index wipe.
- **The save-state mtype correction in the store** ([[#authority]]). It writes no file.
- **Classification by location, on walks without `--as-memory` (amended 2026-11-13, bug-220,
  [[#amendments]]).** A GMD file inside a memory dir that such a walk reaches is never ingested as
  a `kind=doc` twin. It is collected and bridged as `kind=memory`, after the walk's own ingest
  returns and outside its writer lock, into the store its memdir resolves to, per
  [[#store-resolution-walk]]. A memory dir here is the `~/.claude/projects/<slug>/memory` shape,
  or the nearest ancestor with a marker, matched on both the as-given and the resolved path
  ([[task-26.5-memory-organise-verb#bug220-route]]). It runs after the ignore predicate, so a
  pruned dot-dir is never reached. It is ungated because it is store-side. The only file write it
  can cause is the memory path's `MEMORY.md` regeneration in an organised dir, which is already
  marker-gated. An explicit `--as-memory` call is unchanged.

**The trade, stated.** An un-organised dir keeps the old prose-dropping compaction until it is
organised behind its own backup (plan-27). In viascope that means prose loss on a save-state,
not a wipe (the ungated `collect` keeps its ~146 entries). The recovery path until then is
26.8's pre-deploy snapshot of every memdir's `MEMORY.md` and sidecar.

### "Newest" save-state {#newest}

There is one ordering of save-states, used by recall-state, recents and the index (r2 s3):

1. frontmatter `updated`, compared by calendar date (with no `updated`, the mtime's local date);
2. when the dates are equal, mtime decides — always, whether or not either value carries a time
   of day. A date-only value is never read as midnight (r3 m2);
3. a remaining tie is broken by file name.

This is one sort key per file, `(date, mtime, name)`, so it is a total order. Amended 2026-11-09
(ch-bsd 26.1 #s-2): the earlier rule let BOTH-timed pairs compare datetimes while mixed pairs
compared mtimes, so three same-day save-states could form a cycle and each could come out
"newest" depending on input order — and 26.3 routes `rmx recall-state` through this. A time of
day in `updated` is therefore informational only; 26.4's rewrite preserves mtime, so mtime is the
honest same-day signal.

`created` is never a key: a session created earlier but saved later must win.

## Consequences {#consequences}

- A file move is safe by construction: identity is the `id`, the bridge refreshes the path, hooks
  follow the `id`, and prose is carried. Moving is still only done by the
  `rmx memory organise` verb, never by hand ([[plan-26-memory-organisation#verb]]).
- Topic organisation scales without a filesystem fight: subjects are many-to-many and re-filed by
  compile; the folder answers only "what kind of memory, and who writes it".
- The deploy is decoupled from the migration. Shipping the code changes no un-organised dir's
  files; each dir changes when, and only when, it is organised behind a backup.
- Two behaviours coexist until plan-27 finishes. Every reader carries the dual-layout cost
  permanently ([[#legacy]]); every new writer carries a marker branch.
- Agents must learn to write into type folders. Until the MEMORY-RULES edit
  ([[#appendix-memory-rules]]) is applied, agents keep writing at the top level, which keeps
  `organise --check` non-zero and can trip the duplicate-id refusal (plan-26 Q8, 26.8 AC-8).

## Alternatives considered {#alternatives}

- **Topic folders.** Rejected by the user (2026-11-08): a memory belongs to several topics, and
  a file has one folder. Topics as folders would also freeze compile's re-filing into file moves.
- **Path as identity.** Rejected: the store already keys memories by `id` with a NULL entity
  path; making the path identity would turn every move into a forget-plus-add and lose decay
  history ([[feedback_decay_never_loses_knowledge]]).
- **Plural type folders (`projects/`, `feedbacks/`).** Rejected: viascope's 146 memories already
  use singular type folders, and the singular name maps 1:1 to the `metadata.type` value.
- **Gate nothing; ship the new behaviour everywhere at deploy.** Rejected (r2 s2): the deploy
  would rewrite fleet dirs that plan-27 has not yet backed up.
- **Refuse-only guards everywhere.** Withdrawn (r3 m4): see [[#marker]].
- **Hand-moves.** Rejected: only the organise verb moves files, with a backup, `git mv` in
  tracked dirs and an id-aware rollback.

## Open questions {#open}

- **Marker encoding.** CLOSED 2026-11-09 by [[#marker-encoding]] (one JSON object, `layout == 1`).
  This entry is kept as a record.
- **Scheduled compile.** Registering the compile on 17.2's nightly tick stays with plan-17/19
  ([[plan-26-memory-organisation#plan-19]]); this ADR does not depend on it.

## Implementation {#implementation}

| task | builds |
|---|---|
| [[task-26.1-layout-module-and-index-walk]] | `memory_layout.py` (table, walk, `iter_savestates`, `is_organised`); index walk; id-keyed hooks; carried prose |
| [[task-26.2-bridge-move-safety]] | move refresh via `source_path`; duplicate-id refusal |
| [[task-26.3-savestate-subfolder]] | `savestates/` writer (marker-gated); dual reader |
| [[task-26.4-savestate-mtype-normalisation]] | `savestates/` folder authority |
| [[task-26.5-memory-organise-verb]] | the only mover; store resolution; backup; `git mv`; marker; rollback; `--check` |
| [[task-26.6-compile-subject-hygiene]] | `compiled_scope`; the stale mark (19.4) |
| [[task-26.7-memory-index-by-subject]] | the subject-grouped index (19.3) |
| [[task-26.8-refmatrix-live-rollout]] | refmatrix organised; the MEMORY-RULES edit applied |

This repo has no `pseudocode/` layer, so 26.1 was built directly from this ADR and its task spec; the waiver is recorded here (ch-bsd 26.1 #m-3, 2026-11-09).

## Appendix A: proposed MEMORY-RULES text {#appendix-memory-rules}

The user-global `~/.claude/MEMORY-RULES.md` governs where every agent writes a memory, so the
folder convention must reach it (ch-bsd r1 #m6). This ADR does NOT edit that file. The user
authorised the edit on 2026-11-09 (plan-26 Q8); it is applied at task 26.8, with the text below,
as a new section placed after `## Required GMD frontmatter {#frontmatter}`:

```markdown
## Where a memory file goes {#placement}

First look for a `.memory-layout` file in the memory dir. It marks the dir as organised.

- **Organised dir (the marker is present).** Write a new memory into its type folder:
  `feedback/`, `project/`, `reference/`, `user/` or `guardrail/`, named by its `metadata.type`
  (create `user/` or `guardrail/` on first use). Impressions go in `impressions/`. Index links in
  `MEMORY.md` include the folder (`- [Title](feedback/feedback_x.md) — hook`).
- **Flat dir (no marker).** Write at the top level, as before, and link it without a folder.
  `rmx memory organise` files it later, behind a backup. Never create a type folder in a flat dir
  by hand.

In every dir: save-states are written by `rmx save-state`, so never hand-write into
`savestates/`. The filename stem still equals the frontmatter `id`. The folder is never part of
the id, and moving a file never changes which memory it is. Never make a folder for a topic: a
topic is a subject (`rel: part-of`), and one memory can belong to many. Never move memory files
by hand: `rmx memory organise` moves them, with a backup. Layout and rules: refmatrix ADR-0005.
```

**Why the marker condition (amended 2026-11-13, L11, [[#amendments]]).** After 26.8, only the
refmatrix dir is organised. Every other dir stays flat until plan-27 backs it up and organises
it ([[#marker]]). An unconditional "write into the type folder" would send agents in other
projects into folders that no backup covers. It would also contradict the deployed `/save-state`
command, which already gates on the marker (`src/refmatrix/templates/commands/save-state.md`,
"Where a file goes"). The user approves this text at 26.8 AC-8.
{#appendix-memory-rules-why}

### A.2: proposed forget-flow step 5 (put to the user at 26.8 AC-8) {#appendix-forget-step}

`MEMORY-RULES.md#forget` ends at "4. Delete the file". The bridge never forgets a memory whose
file was deleted: no path in `ingest_gmd.py` removes a row for a vanished file (read
2026-11-13), and [[plan-26-memory-organisation#measured]] says the same. So a forgotten memory
stays in the store and recall keeps returning it. L12 puts this step to the user in the same
MEMORY-RULES window as the text above. The user may accept it, change it or decline it. A
removal from the store is a deliberate deletion, which
[[feedback_decay_never_loses_knowledge]] allows only on an explicit request such as "forget X".

```markdown
5. Remove it from the store: `rmx memory forget <id>`, run in the project root. The bridge
   never forgets a deleted file, so without this step recall keeps returning the memory.
```

The validation gate is unchanged by this layout. The PostToolUse lint hook
(`~/.claude/hooks/lint-memory-gmd.sh`, wired since 2026-11-09 by refmatrix bug-183) matches
`*/memory/*.md` in a shell `case`, where `*` also matches `/`, so a file in a type folder is
linted exactly like a top-level one. `MEMORY.md` stays excluded.

## Amendments {#amendments}

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[bsd-spec-t2-b5fe2d3]]

- **2026-11-13 (plan-review L11, L12, L37; spec gaps G4 and G19).** The status stays Proposed. {#amend-2026-11-13}
  - Appendix A's MEMORY-RULES text carries the marker condition (L11; `contra-a.md` Ca-4).
  - Appendix A.2 proposes forget-flow step 5 for the user's decision at 26.8 AC-8 (L12; Ca-9).
  - [[#marker]]'s every-dir list gains classification by location (bug-220, L37), scoped to
    walks without `--as-memory`.
  - [[#store-resolution]] gains [[#store-resolution-walk]]. A walk without `--as-memory` that
    reaches a memdir with no resolvable store treats it as file-only and never hard-errors; the
    home memdir is held per plan-27 Q4. This IS a resolution-rule change, for that walk only. The
    hard error still governs every explicit memdir argument. (Corrected in rev 7, answering
    [[bsd-spec-t2-b5fe2d3#s2]]; the first wording of this entry said no resolution rule
    changed.)
  - The marker-encoding open question is marked closed.
  - No folder, identity or gating rule changes. The reroute is ungated because it is store-side,
    and its only possible file write is already marker-gated.

## Lines that change under plan-review Q8 b {#q8-b}

Q8 is open ([[open-questions]]). This ADR holds under Q8 a or c. Under Q8 b (save-states kept
out at ingest), three things change:
- [[#authority]]'s "the bridge stores that mtype and counts each override";
- [[#marker]]'s every-dir "save-state mtype correction in the store".

- [[#marker]]'s classification-by-location bullet: a rerouted save-state is skipped and counted,
  not bridged (rev 7, bsd-spec-t2 m1).

The first two lose their store side, because no save-state row is written. The file-side rewrite
by `organise --apply` stays.
