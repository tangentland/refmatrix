---
gmd: "0.1"
id: impl-task-bug195-cut-hook-repair
title: "bug-195 GREEN: the backed-up, dry-run-default repair of bug-193's cut hook values"
tags: [implementation-summary, bug-195, bug-193, memory, hooks, repair, plan-26]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# bug-195 GREEN: repairing the cut hook values bug-193 left in sidecars {#root}

rel: implements -> [[task-bug195-cut-hook-repair]]
rel: derives-from -> [[bsd-task-26.1-r3-followup-c9a035e#s-2]]

RED `12ac9b2` (11 failing), GREEN `ccb9398`. Only `src/refmatrix/memory_index.py` changed. No
tests were written in this step.

## What was built {#built}

- **`repair_cut_hooks(memdir, *, apply=False, restores=None, out=None) -> int`**: the R1-R5
  command. It runs as a dry-run unless `apply` is set, and returns the exit code. {#repair}
- **`classify_cut_hooks(memdir, data) -> list[(key, class)]`**: sorts every `…`-ended value into
  `derived`, `bare`, `curated-lost` or `gone`. Path keys (`*.md`, including `impressions/x.md`)
  resolve against the memdir. Any other key is looked up as a memory id. The id lookup walks the
  dir once with `memory_layout.iter_memory_files` and only runs when an id key is present. An id
  with no memory, a path with no file, or a bare `…` with no file is `gone` and is left alone.
  {#classify}
- **One sidecar reader and one writer.** `_load_sidecar` is the strict parse and raises
  `SidecarError`. `_read_sidecar` (the render path) still prints a warning and carries on when
  that parse fails. `_dump_sidecar` is the single serialisation. `_store_sidecar` writes the file
  atomically (`mkstemp` in the memdir, fsync, `os.replace`, temp file removed on failure).
  `save_hooks` now writes through it too, so the bytes it writes are unchanged but the write is
  atomic. {#one-impl}
- **Backups** go to `taxonomy.user_home()/backups/memory-hooks/<slug>-<YYYYmmddTHHMMSS-ns>/`.
  The slug is the project dir's name for a `.../<project>/memory` dir. The dir is created with
  `exist_ok=False`, and the backup is read back and compared byte-for-byte before anything is
  written. If the backup fails, the command exits non-zero and leaves the sidecar untouched.
  {#backup}
- **`main()` rejects unknown flags.** HEAD dropped any `--` arg it did not know and then rendered
  the index. Now an unknown flag, `--apply` or `--restore` without `--repair-cut-hooks`, or a
  missing value exits 2 with a usage message. The existing `<memdir> [--check]` behaviour is
  unchanged. {#main}

## Decisions RED did not pin {#decisions}

- **`--restore` needs an existing key**, so a typo fails instead of adding a stray value. With no
  sidecar at all, a restore is refused. {#d-restore}
- **A bare `…` whose file is gone counts as `gone`, not `bare`**, because R2 says a gone key is
  never touched. {#d-bare-gone}
- **Id keys are resolved in every dir, not only organised ones.** `load_hooks` already reads id
  keys in every dir (task 26.1 AC-4), so doing the same here keeps the two consistent. {#d-ids}
- **An unreadable memory file stops the whole run** with a message naming the key. This also
  applies to any file read while building the id lookup, because an id key could point at that
  file. {#d-unreadable}

## Verification {#verification}

- RED file: 11/11 (`workflow/review-output/bug195-green.log`; again after the mutations in
  `bug195-green-post-mutation.log`).
- Family `tests/test_memory*.py tests/test_save_state*.py tests/test_verb_parity.py`: 505/505
  (`bug195-green-family.log`).

| Mutation | Change | Result |
|---|---|---|
| derived never dropped | `_REPAIR_DROPS = {"bare"}` | killed, 5 failed (`mut1.log`) |
| bare kept | `_REPAIR_DROPS = {"derived"}` | killed, 1 failed (`mut2.log`) |
| backup skipped | backup mkdir/write/read-back replaced by `pass` | killed, 3 failed (`mut3.log`) |
| curated dropped | `_REPAIR_DROPS` plus `curated-lost` | killed, 1 failed (`mut4.log`) |

After each mutation I ran `git checkout -- src` and cleared `__pycache__` as a separate command,
then checked that `git status --short src` was empty and grepped for the restored line.

## Not done here {#not-done}

The live run on the refmatrix memdir and the `workflow/bug_registry.md` row are left to the
orchestrator. The command has not been run against any real memory dir. {#live-run}

## Remedy r1: the sidecar keeps its file mode {#remedy-r1}

rel: derives-from -> [[bsd-bug195-r1-cut-hook-repair-39777c6#m-1]]

ch-bsd r1 m-1 found that the atomic write changed the sidecar's permissions. `mkstemp` creates the
temp file as 0600 and `os.replace` keeps that mode, so after `ccb9398` every save-state left
`.memory_hooks.json` owner-only, where `write_text` had left 0644. RED `6f667e4` added 12 tests,
6 of them failing on file mode. GREEN is `cace22e`.

- **`_sidecar_mode(side) -> int`** returns the existing file's permission bits. When there is no
  sidecar yet it returns `0o666 & ~umask`, the mode `write_text` would have created. Python before
  3.15 cannot read the umask without setting it, so the function sets it and restores it
  straight away. {#r1-mode}
- **`_store_sidecar`** calls `os.fchmod` on the temp file with that mode before the fsync and the
  rename. `save_hooks` and the repair both write through it, so both are fixed. {#r1-store}

Verification: repair file 23/23 (`bug195-green-r1.log`, and again after the mutation in
`bug195-green-r1-post-mutation.log`). Family run 517/517 (`bug195-green-r1-family.log`).

| Mutation | Result |
|---|---|
| `os.fchmod` removed | killed, 6 failed: every mode test (`bug195-green-r1-mut-fchmod.log`) |

After the mutation I ran `git checkout -- src` and cleared `__pycache__` as a separate command,
then checked that `git status --short src` was empty and grepped for the fchmod line. {#r1-verify}
