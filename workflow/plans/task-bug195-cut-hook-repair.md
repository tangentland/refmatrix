---
gmd: "0.1"
id: task-bug195-cut-hook-repair
title: "Task bug-195: a one-shot, backed-up repair of hook values cut by bug-193"
tags: [task, bug-195, bug-193, memory, hooks, repair, plan-26]
metadata:
  node_type: task
  status: approved
  updated: 2026-11-10
---

# Task bug-195: repair the cut hook values bug-193 left in sidecars {#root}

rel: derives-from -> [[bsd-task-26.1-r3-followup-c9a035e#s-2]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk#followup-r3]]

bug-193 (precedence fixed in `25af9ca`) saved the renderer's `prefix…` cut back into
`.memory_hooks.json` as if it were the hook. The fixed precedence stops new damage but never heals
old values: on the live refmatrix sidecar 66 values end in `…` (39 on index lines, 27 on folded
entries), 1 of them a bare `…`. 37 are cuts of the memory's own first prose; ~29 are curated text
with no source left. Runs after the 26.1 follow-up merge, before the release that ships 26.1.

## Requirements {#requirements}

1. **R1: one committed command, dry-run by default.** `python -m refmatrix.memory_index
   --repair-cut-hooks <memdir>` (the module entry `memory_index` already has) classifies every
   sidecar value ending in `…`, prints each by key and class, and changes nothing. `--apply` writes.
   No new verb: this is a one-shot maintenance repair, not an agent capability. {#r1}
2. **R2: three classes.** (a) *derived*: the cut's prefix starts the memory file's `_first_prose`
   — the key is dropped, so the full derived hook returns; (b) *bare*: the value is exactly `…` —
   dropped; (c) *curated-lost*: anything else — kept unchanged and listed by name for the user to
   rewrite. A key whose file is gone is reported, never touched. Counts per class are printed.
   {#r2}
3. **R3: backed up first.** `--apply` copies the sidecar to
   `~/.refmatrix/backups/memory-hooks/<memdir-slug>-<timestamp>/.memory_hooks.json` before writing,
   prints the path, and refuses (exit non-zero, nothing written) if the backup fails. The write is
   atomic (temp + rename). {#r3}
4. **R4: idempotent and loud.** A second `--apply` changes nothing and says so. Every failure
   (unreadable sidecar, unparseable JSON, unreadable memory file) is printed and exits non-zero;
   nothing is skipped silently. {#r4}
5. **R5: optional git-recoverable restore.** `--restore <key>=<text>` (repeatable) sets a curated
   value explicitly, so the one value `~/.claude` git recovers (`project_session_0623_arc.md`)
   is restored by the operator, not guessed by the tool. {#r5}

## Acceptance criteria {#acceptance}

- **AC-1:** on a tmp memdir with one value of each class plus a gone-file key, dry-run prints all
  four by key with the right class and counts, and the sidecar bytes are unchanged.
- **AC-2:** `--apply` on the same dir: derived and bare keys are gone, curated-lost and gone-file
  keys are byte-identical, the backup file equals the old sidecar, the printed path exists.
- **AC-3:** a second `--apply` writes nothing (mtime unchanged) and prints "nothing to repair".
- **AC-4:** after apply, `memory_index.write` renders the derived memory's full first-prose hook.
- **AC-5:** a backup that cannot be written (read-only backup root) → non-zero exit, sidecar
  unchanged.
- **AC-6:** `--restore k=text` sets exactly that value (and is backed up like any apply).
- **Mutations:** derived class never dropped; bare kept; backup skipped; curated dropped — each
  killed.
- **Live run (operator, announced and backed up):** dry-run on the live refmatrix memdir reports
  66 = 37 derived + 1 bare + ~28 curated-lost (the class split is measured, not asserted); apply;
  `--check` in sync; the curated-lost list goes to the user.

## Files {#files}

`src/refmatrix/memory_index.py` (repair function + entry flag), `tests/test_memory_hook_repair.py`
(new), `workflow/bug_registry.md`.
