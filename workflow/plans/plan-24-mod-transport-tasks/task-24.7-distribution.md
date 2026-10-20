---
gmd: "0.1"
id: task-24.7-distribution
title: "Task 24.7: distribution — a marketplace file in the public repo, the deploy tree's mod loaded through CLAUDE_CODE_PLUGIN_DIRS, the marketplace copy standing down when the deploy copy loads, one version for rmx and the mod, and the deploy steps rewritten"
tags: [task, plan-24, mod, distribution, marketplace, deploy, release]
metadata:
  node_type: task
  status: pending
  created: 2026-10-20
  updated: 2026-10-20
---

# Task 24.7: distribution {#root}

> Plan: [plan-24-mod-transport](../plan-24-mod-transport.md)
> Status: Pending (spec written 2026-10-20).
> Depends on: [[task-24.5-mod-core]] (the loadable mod), [[task-24.6-context-and-observation]]
> (the deploy must carry the event map and the stand-down marker together).
> Feeds: 24.8.

rel: part-of -> [[plan-24-mod-transport]]
rel: depends-on -> [[task-24.5-mod-core]]
rel: depends-on -> [[task-24.6-context-and-observation]]
rel: implements -> [[exploration-claude-code-mod-transport#distribution]]
rel: related-to -> [[reference_github_remote]]
rel: related-to -> [[feedback_deploy_tree_is_the_runtime]]
rel: related-to -> [[feedback_push_from_dev_not_deploy]]

## Why {#why}

D5: "distribution should allow for both". A person installs a tagged release from the public repo
with one line; this workstation runs the exact build its daemons run, from the deploy tree. If
both load, every hook and tool is registered twice. And a deploy today ends with "`/mcp`
reconnect to load new tools"; a mod loaded from a watched folder reloads itself, so the deploy
section changes. {#why-lead}

## Decisions {#decisions}

| # | decision | reason |
|---|----------|--------|
| d1 | `.claude-plugin/marketplace.json` at the REPO ROOT, one entry `{ "name": "refmatrix", "source": "./mod" }`, marketplace name `tangentland` | the reference's form (a relative `source`); the mod stays in `mod/` beside the Python it is generated from |
| d2 | The install line is `/plugin install refmatrix --marketplace tangentland/refmatrix` | the reference's install step, `<mod>` = plugin.json `name` |
| d3 | The workstation loads the deploy copy through `CLAUDE_CODE_PLUGIN_DIRS=~/refmatrix/mod` in `~/.claude/settings.json`'s `env` block, written by a verb, backed up and diffed | the reference: that variable is read from the process env or the USER settings' env (never a project's), loaded exactly as `--plugin-dir`, and watched in an interactive session — every session gets the deploy build with no flag |
| d4 | Double load: each copy hooks `plugin.register` for `{ name: "refmatrix" }`; an `@inline` judge REFUSES a non-inline candidate; a non-inline judge ADMITS an `@inline` candidate and stands itself down (every hook passes `next(e)`, no tools, one transcript line) | `provenance` tells the copies apart, and covering both admission orders means the deploy copy wins whichever loads first (D5) |
| d5 | One version: `mod/.claude-plugin/plugin.json` `version` == `pyproject.toml` `version`, asserted by a test; `modgen --write` sets it | the handshake compares the mod's version with the daemon's; two numbers for one release would be a skew report on every session |
| d6 | A release is a commit on `master` with the bumped version, tagged `v<version>` (annotated); the user pushes `main` and the tag (`git -C <dev> push origin master:main --follow-tags`) | the user pushes (CLAUDE.md); a marketplace install reads the repo's default branch, so `main` at the tag IS the released mod |
| d7 | Pinning the marketplace entry to a tag (a source form with a ref) is used only if `claude plugin validate .` accepts such a form at implementation; otherwise d6's default-branch rule stands and is said in the README | the types and reference show only the relative-path source; an unconfirmed field is not shipped |
| d8 | Each mod request carries `X-Rmx-Mod-Version` and `X-Rmx-Mod-Provenance`; the daemon logs them in 24.2 R9's row; `rmx mod status` reads the newest rows per session | the CLI cannot read `$.store` or the engine; the rows are the existing, durable place where "which mod build is serving this session" can be seen |
| d9 | The operator surface is a verb, `rmx_mod(action: status \| enable \| disable)` (model surface, `writes` = enable / disable), CLI `rmx mod status / enable / disable` | every capability is a verb first; `LEGACY_UNPAIRED` is shrink-only, so a new operator command cannot land there |

## Requirements {#requirements}

1. **R1 — the marketplace file (d1, d7).** `{ "name": "tangentland", "owner": { "name": "Todd
   Holley" }, "plugins": [{ "name": "refmatrix", "source": "./mod" }] }`. `claude plugin validate
   .` (the repo root) reads it, the manifest and the hooks module in one run, exit 0. {#r1}
2. **R2 — the install path.** README's install section gains the line of d2 in a code block and
   what follows it (`y` to add the marketplace, then a scope), and states that the mod needs a
   local `rmx` install (it spawns the project's `rmx` on absent, D4) and a running hub for
   global / bus features. {#r2}
3. **R3 — `rmx_mod` (d9).** `status`: the env block's `CLAUDE_CODE_PLUGIN_DIRS` value, whether it
   names `<deploy_root()>/mod`, the deploy tree's `plugin.json` version, and per recent session
   the newest `X-Rmx-Mod-Version` / provenance seen (d8). `enable`: back up
   `~/.claude/settings.json` to `settings.json.bak.<ts>`, add `<deploy_root()>/mod` to the
   variable (path-list separator, existing entries kept), write atomically, print the diff.
   `disable`: the inverse. The only path it ever writes is `<deploy_root()>/mod`, never the tree
   the command runs from (a dev tree's mod would serve uncommitted code to every session, the
   2026-09-14 defect one level up); a `deploy_root()` of None (no deploy tree) refuses with the
   reason. {#r3}
4. **R4 — the stand-down (d4).** `mod/src/standdown.ts` (shared with 24.6's marker module):
   the `plugin.register` hook per d4, a module-level `standingDown` flag every hook checks first,
   and at `session.start` one `$.ui.log` naming both roots. A probe, **P-double**, in a scratch
   project with the marketplace copy installed AND `--plugin-dir` given: both admission orders
   (install scope user vs project changes load order; recorded which order each produces), the
   stand-down line, one registration per tool, and whether `$.state` owned by the name `refmatrix`
   is shared by the two copies; results to `eval/mod_probe/double_load.json` and a decision row
   here. {#r4}
5. **R5 — one version (d5).** `modgen` writes `version` into `plugin.json` from
   `refmatrix.__version__`; `modgen --check` fails on a mismatch. {#r5}
6. **R6 — the deploy section.** CLAUDE.md `#development-commands` and `.claude/PROJECT_PROFILE.md`
   `#commands` Deploy become: commit on `master` → `git -C ~/refmatrix pull --ff-only origin
   master` → `rmx daemon restart --relaunch` (verifies pid + version) → the hub self-restarts on
   version mismatch → the mod reloads itself (the watched `CLAUDE_CODE_PLUGIN_DIRS` folder changed
   under the ff; a session mid-turn reloads when the turn ends) → `rmx mod status` shows the new
   `X-Rmx-Mod-Version` on the next request. `#mcp-servers` says the MCP server is for non-Claude-Code
   clients after 24.8. A release adds d6's tag and push. {#r6}
7. **R7 — `claude -p` and the desktop host.** README and the deploy section state: `claude -p`
   loads `CLAUDE_CODE_PLUGIN_DIRS` fresh each run (the reference) with what P-print (24.5 R12,
   24.6 R7) measured about which events fire there; a long-lived headless host watches only with
   `CLAUDE_CODE_PLUGIN_DIR_WATCH=1`. {#r7}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1, R5).** `claude plugin validate .` exits 0 (run by `tests/test_task24_4_mod_gates.py`,
   extended); the version test fails on a `plugin.json` edited to another version. RED at base.
   {#ac-1}
2. **AC-2 (R3).** Against a fixture `HOME` (`mkdtemp`), `rmx mod enable` writes the variable,
   keeps an existing entry, leaves a `.bak`, and prints the diff; `disable` restores the previous
   value; run from a dev-tree interpreter it still writes `<deploy_root()>/mod`; with
   `RMX_DEPLOY_ROOT` naming a directory without `pyproject.toml` it refuses. Never run against the real
   `~/.claude/settings.json` in tests. {#ac-2}
3. **AC-3 (R4, d4).** `mod/tests/standdown.test.ts`: an inline judge refuses a
   `refmatrix@tangentland` candidate; a `refmatrix@tangentland` judge admits an inline candidate
   and then answers every hook with `next(e)` and registers nothing; the P-double file exists.
   {#ac-3}
4. **AC-4 (d8).** A 24.2 request with the two headers leaves them in its `cli.log` row; `rmx mod
   status --json` reports them for that session. {#ac-4}
5. **AC-5 (R6).** `./scripts/lint-gmd.sh` is clean on the edited CLAUDE.md / PROJECT_PROFILE.md;
   the deploy section names `rmx mod status` and no longer says `/mcp` reconnect for Claude Code.
   {#ac-5}

## Test strategy {#test-strategy}

`tests/test_task24_7_distribution.py` (AC-1's version check, AC-2, AC-4) under a fixture `HOME`;
`mod/tests/standdown.test.ts` (AC-3); the probe in a scratch project. No test reads or writes the
real user settings: the verb takes the settings path from `Path.home()`, and the tests set `HOME`.
RED first, logged to `workflow/review-output/task24_7-red.log`. {#test-strategy-body}

## Files to modify {#files}

| file | change |
|---|---|
| `.claude-plugin/marketplace.json` | new (R1) |
| `mod/.claude-plugin/plugin.json`, `src/refmatrix/modgen.py` | version from `__version__` (R5) |
| `mod/src/standdown.ts`, `mod/src/index.ts`, `mod/tests/standdown.test.ts` | d4 (R4) |
| `mod/src/generated/client.ts` (via `modgen`) | the two headers (d8) |
| `src/refmatrix/verbs.py`, `src/refmatrix/cli.py` | `rmx_mod`, `rmx mod …` (R3) |
| `src/refmatrix/httpsock.py`, `src/refmatrix/telemetry.py` | log the headers (d8) |
| `README.md`, `CLAUDE.md`, `.claude/PROJECT_PROFILE.md` | R2, R6, R7 |
| `tests/test_task24_7_distribution.py`, `tests/test_task24_4_mod_gates.py` | AC-1..AC-4 |
| `eval/mod_probe/double_load.json` | R4 |
