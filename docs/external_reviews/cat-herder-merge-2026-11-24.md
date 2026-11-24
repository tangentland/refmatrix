---
gmd: "0.1"
id: refmatrix/cat-herder-merge-2026-11-24
title: "Should cat-herder merge into refmatrix? Yes, as project-neutral templates inside rmx init"
tags: [external-review, cat-herder, template, process, ch-bsd]
metadata:
  node_type: external-review
  created: 2026-11-24
  harness: "read-only comparison of ~/github/atollogy/bdep/cat-herder against ~/claude_tools/refmatrix (cmp/diff of .claude/ agents, commands, hooks; workflow/ listing; git log counts; rmx call census)"
  origin_session: dd0578f8-70b4-4c79-9eae-a453aefd8d45
  status: hold-until-0.85.0
---

# Should cat-herder merge into refmatrix? {#root}

The question, from the user on 2026-11-24: cat-herder and refmatrix seem to overlap more and
more; does it make sense to merge them? This review answers it from the two repos as they stand.

**HOLD.** This is not 0.85.0 work. Nothing here starts until 0.85.0 is released and deployed, and
until the ch-bsd consequence package has landed (see [[#order]]). {#hold}

rel: depends-on -> [[refmatrix/ch-bsd-assessment-2026-11-23#package]]

## Verdict {#verdict}

**Yes. Merge cat-herder into refmatrix, as project-neutral package data under
`src/refmatrix/templates/` installed by `rmx init`, not by mixing it into refmatrix's own
`.claude/`.** The merge has in fact already begun: `rmx init` ships 9 of cat-herder's files today
(see [[#ev-two-scaffolders]]). The real problem is not that there are two repos. It is that there
is no path for changes to flow between them, and now two installers write the same files. A
merge fixes that only if refmatrix's own copy becomes an *instance* of the template, checked by a
parity gate, and consumers get an upgrade command. {#verdict-lead}

rel: amends -> [[refmatrix/ch-bsd-assessment-2026-11-23#f6]]

## What this does NOT claim {#not-claimed}

- It does not settle ownership. cat-herder lives under `atollogy/`, refmatrix under
  `tangentland/`. If that is a work-versus-personal split, the user decides, and it could rule
  out a merge on its own (see [[#ownership]]).
- It did not read every diff line. Drift direction was checked on `ch-bsd.md`,
  `general-purpose.md` and `enforce-rmx-grep.sh`; the other 11 differing agent files were sized
  only.
- It did not check whether the 9 consumer projects have edited their copies on purpose.

## Evidence {#evidence}

### cat-herder has stopped moving {#ev-activity}

| Repo | Commits | Since 2026-10-01 | Last commit |
|------|--------:|-----------------:|-------------|
| cat-herder | 25 | 3 | 2026-11-08 |
| refmatrix | 2,700 | — | 2026-11-24 |

### refmatrix is already the real source {#ev-upstream}

Template work is exercised, and therefore improved, where the process runs (285 ch-bsd runs in
refmatrix). None of the following has reached cat-herder:

- `ch-bsd.md` in refmatrix carries the rmx MCP tools in `tools:` and `effort: high`.
- `enforce-rmx-grep.sh` in refmatrix honours `learn.off`, the fix for the bug-115 cli-pool
  saturation. cat-herder's copy still redirects every corpus grep back to the daemon.
- `workflow/ORCHESTRATION.md`, `workflow/SELF_AUDIT.md` and `workflow/measurements/` exist only
  in refmatrix.

Of the template files compared: all 14 agent files differ; 13 of 21 commands are byte-identical;
3 of 5 hooks differ. `save-state.md` and `recall-state.md` exist only in cat-herder (refmatrix
uses the global skills instead).

### The two are already coupled {#ev-coupling}

31 cat-herder files call `rmx` (top verbs: `context` 30, `memory` 22, `grep` 18, `focus` 16).
Its `CLAUDE.md` names rmx as the primary memory layer, and `install.sh` installs rmx from git.
`--skip-rmx` exists, but a project scaffolded with it is missing much of its workflow. Hook
flags (`learn.off`) and MCP tool names are rmx's interface, so the template already versions
with rmx in practice, just without saying so.

### Two scaffolders already write the same files {#ev-two-scaffolders}

`src/refmatrix/templates/` ships `gmd-curator.md` and 8 session commands (`save-state`,
`recall-state`, `commit-state`, `detour`, `return`, `stash`, `stash-list`, `stash-pop`);
`rmx init` installs them (`src/refmatrix/init_agents.py`). cat-herder's `install.sh` ships its
own copies of the same 9 files, and **all 9 differ** from refmatrix's packaged versions. A
project scaffolded by `install.sh` and then `rmx init`-ed gets whichever ran first, since both
skip existing files.

refmatrix has already met this drift once and fixed it in-house: on 2026-11-10 the
`/save-state` / `/recall-state` pair moved to user level (`~/.claude/commands/`) because
per-project copies drifted and one rewrite had lost the memory-dir rules
(`init_agents.py` docstring). `rmx init --force` already backs up a differing copy before
replacing it. The upgrade machinery cat-herder lacks is half-built here.

### No upgrade path {#ev-no-upgrade}

`install.sh` only adds missing files ("re-running is safe, but it is not an upgrade"). The 9
consumer projects that carry the template (atldb, atlftpd, cliquedb, cliquet, orderly, portal,
prep_prolific, thiquet, plus refmatrix itself) are frozen at whatever version they first got.
That is the mechanism behind F6's 10 copies with 10 checksums.

rel: evidence-for -> [[refmatrix/ch-bsd-assessment-2026-11-23#f6]]

### refmatrix is not a clean source either {#ev-not-clean}

refmatrix's copies carry project specifics in committed files, which the template's own rule
forbids (specifics belong in `.local.md` overlays). Example: `general-purpose.md` hardcodes
`.venv-eval/bin/python` and has dropped the `#project-profile` overlay section that keeps agent
files project-neutral. Making refmatrix's `.claude/` the template as-is would hand refmatrix's
specifics to every project.

## Proposed shape {#shape}

1. **`src/refmatrix/templates/` grows to hold the whole template**: project-neutral `ch-*`
   agents, commands, hooks, the workflow skeleton and `tune-project.py`. It must live inside the
   package, because a `pipx`/`uv tool` install ships only package data; a top-level `template/`
   would never reach a consumer. First reconcile the 9 files both installers ship
   ([[#ev-two-scaffolders]]). `rmx init` absorbs `install.sh`'s scaffold and tune steps;
   `install.sh` shrinks to "install rmx, run `rmx init`". cat-herder's git history can be imported
   with a subtree merge so it is not lost. {#shape-dir}
2. **refmatrix's own `.claude/` becomes one instance of the template.** Its specifics move into
   `.local.md` overlays. A parity check (next to `lint-gmd.sh` parity) fails if a committed agent,
   command or hook file differs from `src/refmatrix/templates/` apart from the frontmatter `id`. This fixes F6
   at the source rather than by sweep. {#shape-parity}
3. **`rmx template diff|upgrade`** lets consumers pull template changes deliberately, with a
   three-way view against their local edits. It builds on `rmx init --force`, which already
   backs up a differing copy before replacing it. This is the upgrade path `install.sh` never
   had. {#shape-upgrade}
4. **Template version = rmx version.** A template change ships in an rmx release, so hook flags
   and MCP tool names never drift from the rmx that serves them. `install.sh` installs the
   matching rmx. {#shape-version}

## Reasons to hesitate {#hesitate}

- **Ownership.** `atollogy/` versus `tangentland/`. If the split is deliberate, keep two repos
   and build only [[#shape-upgrade]] and [[#shape-parity]] against cat-herder as upstream. That
   recovers most of the value without a merge. {#ownership}
- **Release overhead.** A template edit would go through refmatrix's release gate. Arguably
   correct: a template change reaches 10 projects.
- **Scope creep in refmatrix.** refmatrix is a bitmap index and daemon; a Docker-only
   `CLAUDE.md` skeleton and SDD commands are a different concern. They are package data, not
   code, and `templates/` already exists as their home, so the cost is wheel size and review
   surface, not architecture.

## Recommended order {#order}

1. 0.85.0 releases and deploys.
2. The ch-bsd consequence package lands (P1–P4 + F1, one commit), so the new severity text is
   written once.
3. Ownership ruling from the user: merge, or keep two repos with sync.
4. Reconcile the 9 doubly-shipped files, then grow `src/refmatrix/templates/` + the parity gate
   ([[#shape-dir]], [[#shape-parity]]); move refmatrix's specifics into overlays.
5. `rmx template diff|upgrade` ([[#shape-upgrade]]); roll the package and the bug-115 hook fix
   out to the 9 consumers through it.
6. Archive the standalone cat-herder repo with a pointer README.

rel: depends-on -> [[refmatrix/ch-bsd-assessment-2026-11-23#order]]
