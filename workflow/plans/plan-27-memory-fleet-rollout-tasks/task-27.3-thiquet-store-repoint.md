---
gmd: "0.1"
id: task-27.3-thiquet-store-repoint
title: "Task 27.3: supervise the real thiquet store (bdep/thiquet), retire the empty ~/enduris/thiquet one"
tags: [task, plan-27, thiquet, supervision, launchd, hub, repoint, retire]
metadata:
  node_type: task
  status: pending
  plan: plan-27-memory-fleet-rollout
---

# Task 27.3: thiquet supervision repoint {#root}

> Plan: [[plan-27-memory-fleet-rollout]]
> Status: Pending
> Depends on: [[task-27.1-fleet-inventory]]

rel: part-of -> [[plan-27-memory-fleet-rollout]]
rel: reinforces -> [[feedback_launchd_install_force_leaves_it_unloaded]]
rel: reinforces -> [[feedback_hub_restart_via_launchctl]]

## Requirements {#requirements}

User (2026-11-08): "bdep-thiquet is correct." `~/github/atollogy/bdep/thiquet` is the real repo
(origin `git@github.com:tangentland/thiquet.git`, last commit `234a972` on 2026-11-08). It has
its own `.refmatrix/`, which is NOT supervised. `~/enduris/thiquet` is not a git repo. It holds
`.obsidian/`, `CLAUDE.md` (215 B, a primer include) and `.refmatrix/` (25 MB). That store IS
supervised (`com.refmatrix.daemon.thiquet-369d4c5eeb65`, plist WorkingDirectory
`~/enduris/thiquet`), and an earlier check found it empty. The memdir `-bdep-thiquet` (34
memories, 13 save-states) is correct and stays.

1. **AC-1: inventory what points at `~/enduris/thiquet`.**
   - the launchd plist and label;
   - the `rmx hub status` entry and `~/.refmatrix/registry.json` (it did not list thiquet on
     2026-11-08; record what the hub learns from);
   - any hook or settings file in either tree;
   - any `source_path` under it in any store (a global-store daemon read);
   - session-indexer labels.
   Record each with its action.
2. **AC-2: bdep/thiquet's store state, announced and backed up first.** Before supervising,
   `tar` bdep/thiquet's `.refmatrix/` with its daemon stopped. Then:
   - run `rmx derive` / `rmx daemon status` in that root, plus entity and memory counts;
   - if the derive is stale or the store is empty, `rmx reingest --force` through its own daemon
     after supervision, and record the before and after counts.
3. **AC-3: supervise bdep/thiquet.** Run `rmx daemon launchctl install` in
   `~/github/atollogy/bdep/thiquet`. Then `launchctl print gui/$UID/<label>` must show it loaded
   and running (install `--force` can leave it unloaded, so verify, never assume). `rmx hub
   status` must list `/Users/tholley/github/atollogy/bdep/thiquet/.refmatrix` at the deployed
   version.
4. **AC-4: unsupervise and retire `~/enduris/thiquet`'s store.**
   - Run `rmx daemon launchctl uninstall` in `~/enduris/thiquet`, and verify the label is gone
     from `launchctl list`.
   - Back up its `.refmatrix/` to `~/.refmatrix/backups/thiquet-enduris-<ts>.tar.gz`.
   - Leave a tombstone `README.md` naming bdep/thiquet.
   - Do NOT delete the directory or its `.obsidian/`/`CLAUDE.md` (plan Q5).
   - `rmx hub status` no longer lists it.
5. **AC-5: memory reaches the right store.** In bdep/thiquet, after 27.4 organises its memdir:
   `rmx memory recall "<phrase unique to a thiquet memory>"` returns it, and `rmx recall-state`
   resumes from the newest of its 13 save-states.

## Files to Create / Modify {#files}

- Use only the `launchctl`/hub commands, and touch store data only through daemon ops.
- Create `workflow/implementation_summaries/task-27.3-thiquet-store-repoint.md`.

## Test Strategy {#test-strategy}

Live verification. Every step is announced to the user and backed up first. Restart the hub, if
needed, with `rmx hub stop` plus ONE `launchctl kickstart`.
