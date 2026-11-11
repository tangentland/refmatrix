---
description: Save state — handoff the session (commit, promote STM, memory, report)
---

"Save state" is a handoff directive: make the work ready for context-clear,
exit, or pickup by another instance. Not just a summary. **Save state =
promote** — the working memory graduates to durable memory.

**Project conventions** (use the project's own if its CLAUDE.md names different ones):
- **Status file** — the one the project's CLAUDE.md names; else `handoff.md` if it exists; else
  `workflow/STATUS.md` (the navigable current-state header + save-state chain).
- **Agent brief dir** — `workflow/agents/`.
- **Memory dir** — `~/.claude/projects/<slug>/memory/` (layout: refmatrix ADR-0005).

Do all of this, in this order:

1. **Commit** outstanding intentional work (multiple commits if it spans
   concerns). Tool noise (`.tldr/`, `__pycache__/`, `egg-info/`) stays
   unstaged. Never commit another agent's in-flight files.
2. **Enduring memory FIRST** — write/append any feedback rules, project-state facts, or gotchas
   to the memory dir + update its `MEMORY.md` index (per `~/.claude/MEMORY-RULES.md`). Before
   save-state, because save-state's memory bridge ingests the dir as it is at that moment.
   - **Where a file goes.** A dir with a `.memory-layout` marker is organised: write into the
     type folder named by `metadata.type` — `feedback/`, `project/`, `reference/`, `user/`,
     `guardrail/` (impressions in `impressions/`) — and link it with the folder
     (`- [Title](feedback/feedback_x.md) — hook`). A dir without the marker stays flat: write
     at the top level.
   - Never hand-write into `savestates/` (save-state owns it), never make a folder for a topic
     (a topic is a `rel: part-of` subject), and never move a memory file by hand —
     `rmx memory organise` moves them, behind a backup.
   - The filename stem equals the frontmatter `id`, whatever the folder. Two files claiming one
     `id` are refused by the bridge, and neither is written.
3. **Save-state + promote + bridge** in one:
   ```
   rmx save-state --commit -m "<one-line headline of this session>"
   ```
   This writes the GMD handoff, promotes the condensed STM digest to durable memory, runs the
   memory bridge (`ingest-gmd --as-memory` over the memory dir, so the next instance's
   SessionStart recall sees everything), and commits.
   - `--commit` is `git add -A`. If any agent is still editing this tree, drop `--commit`,
     commit your own files by pathspec (`git commit -- <paths>`), and say in the handoff that
     the agents' edits are in flight.
   - In an organised dir the handoff lands in `savestates/<id>.md`; a top-level copy of the
     same save-state is moved in or removed, and the output says which.
   - A red `memory bridge FAILED` line, a duplicate-id refusal, a skipped-file count or a
     `remove_failed` line is a loose end — fix or report it, never skip it.
3a. **Active goal (MANDATORY if a `/goal` is active)** — a goal does not survive the session on
   its own. Write/refresh the `{#active-goal}` block at the top of the status file's body (after any
   frontmatter and its H1; and
   commit it) with ALL of:
   - the goal text **verbatim**, exactly as the user typed it after `/goal`;
   - what the goal's scope means concretely (the slot/phase list it covers, from the
     discussion — not just the one-liner);
   - the completion criteria (what "done" is checked against);
   - the current position: per branch / slot, what is done, in flight, next;
   - every pending user decision (numbered, with the recommendation);
   - **every agent running at save time**, one row each: name · agent type · target branch · worktree path ·
     base SHA it started from · expected artifact (commit on branch / ledger path / report file) · DB/role
     prefix it uses (if any) · brief file. Write each agent's full brief, plus any amendments sent after
     dispatch, to `<agent brief dir>/<name>.md` so a fresh agent can be re-dispatched from it verbatim;
   - the restore instruction: *"re-issue `/goal <verbatim text>` to resume"*.
   If no goal is active, the block says so (`no active goal`) — never leave a stale one.
   If the project has no status file yet, create it with this block at the top of its body.
4. **Deploy if code landed** — only if this repo ships a tool that runs from a separate live
   install: promote dev → live and restart any affected daemon. Otherwise skip. refmatrix:
   fast-forward the deploy tree to the committed sha (`git -C ~/refmatrix pull --ff-only origin
   master`), then `rmx daemon restart --relaunch`, and verify with `rmx version -v` (no
   `[DEV TREE]`). Never `pip install -e` the dev tree into the deploy venv — that makes `rmx`,
   every daemon and the hub run uncommitted code (2026-09-14).
5. **Report** the resume point: branch + HEAD, what shipped, open loose ends,
   the concrete next action, and whether the push is still pending (the user
   pushes).

$ARGUMENTS
