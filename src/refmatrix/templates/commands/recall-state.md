---
description: Recall state — orient on the prior session before doing anything
---

"Recall state" is a resume directive: load the prior session's handoff and
orient before taking any other action. The mirror of "save state." Do every
step, then WAIT for direction — the orient pass is the whole job.

**Project conventions** (use the project's own if its CLAUDE.md names different ones):
- **Status file** — `workflow/STATUS.md`. **Agent brief dir** — `workflow/agents/`.
- **Trunk** — `origin/main` unless the repo's default branch differs.
- **Memory dir** — `~/.claude/projects/<slug>/memory/` (layout: refmatrix ADR-0005).

1. **Latest handoff** — read the status file's current-state header, then pull the prior
   session's save-state handoff — the newest save-state (`savestates/`, legacy top-level) in
   the project memory dir — plus the promoted STM digest and recent memories:
   ```
   rmx recall-state         # handoff + git + daemon + anomalies, one shot
   rmx memory recall --session-start --k 10 --scope both
   rmx focus context        # the prior session's threads, if STM survived
   ```
   - "Newest" is one order: frontmatter `updated` by calendar date, then mtime, then file name;
     `created:` never decides. Resume from the handoff `rmx recall-state` names — never pick a
     save-state file by eye.
   - If `--session-start` comes back empty or stale while memory files exist on disk, the
     bridge lagged: run `rmx ingest-gmd --as-memory ~/.claude/projects/<slug>/memory` and
     retry. A duplicate-id refusal or a skipped-file count in its output is an anomaly to report.
2. **Git state** — branch, `git log --oneline -5`, `git status --short` (raw git), and
   how far ahead of the trunk (`git rev-list --count <trunk>..HEAD`).
3. **Daemon/hub state** — `rmx daemon status` (+ `rmx hub status` if used);
   compare the running version against the latest shipped.
3a. **Active goal** — read the `{#active-goal}` block at the top of the status file. If it
   records an active goal, report it first: the verbatim goal text, its position, the pending user
   decisions, and the exact restore command (`/goal <verbatim text>`) for the user to re-issue —
   the agent cannot re-arm a goal itself.
3b. **Running agents from the last session** — for EACH agent row in `#active-goal` (read-only checks; never
   reset, revert or delete an agent's work):
   - **Alive?** `ListAgents` — is it still addressable? If so, it is live: leave it alone and wait for its report.
   - **Committed?** `git log --oneline <base SHA>..<branch>` — any commits since it started? Read their subjects.
   - **In flight?** if the worktree path still exists, `git -C <worktree> status --porcelain` and
     `git -C <worktree> log --oneline -3` — uncommitted work is evidence, not garbage.
   - **Artifact?** does the expected ledger/report file exist (`ls -l <path>`)?
   - **Leftovers?** if the row records a DB/role prefix: DBs or roles under it (e.g. Postgres `pg_database` /
     `pg_roles` LIKE `<prefix>%`) — report only.
   - **Classify** each: DONE (artifact landed) · PARTIAL (commits or dirty worktree, no final artifact) ·
     NOT-STARTED (nothing moved) · LIVE.
   - **Pick-up plan** (propose; do not dispatch until the user says go): DONE → read the artifact and continue
     the pipeline. PARTIAL → a fresh agent of the same type, briefed from `<agent brief dir>/<name>.md` plus
     "resume from <branch>@<tip>; the worktree at <path> holds uncommitted work: inspect it first, then commit
     or redo it". NOT-STARTED → re-dispatch from the brief file unchanged. LIVE → wait.
4. **Report the resume point**: branch + HEAD + version, what was last
   accomplished, open loose ends, the concrete next action, and any anomalies
   (dirty tree, unpushed commits, daemon on stale version, leftover worktrees, memory-bridge
   refusals or skips).
5. **Wait** for direction. Do not start the next action automatically.

$ARGUMENTS
