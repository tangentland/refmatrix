# spec-t2 report: T2 memory organisation (G4, G6, G15, G19)

## Commits

One commit, `db2aa9b`, on `spec-wave-t2` in `/Volumes/littlebig/refmatrix-spec-t2`, committed by
pathspec.

- It is spec text only.
- All 10 touched files lint with 0 errors one by one (`tools/gmd/lint.py`).
- A full-scope lint (workflow, docs, CLAUDE.md, `.claude`, memory dir) shows no new message for
  these files against master.
- `./scripts/lint-gmd.sh` could not run: the clone has no `.venv-eval`.
- No status changed. plan-26 and plan-27 stay `approved`, and every task stays `pending`.

Files:
- `docs/adr/0005-memory-dir-layout.md`
- `workflow/plans/plan-26-memory-organisation.md`
- `workflow/plans/plan-26-memory-organisation-tasks/task-26.5-memory-organise-verb.md`
- `workflow/plans/plan-26-memory-organisation-tasks/task-26.7-memory-index-by-subject.md`
- `workflow/plans/plan-26-memory-organisation-tasks/task-26.8-refmatrix-live-rollout.md`
- `workflow/plans/plan-26-memory-organisation-tasks/task-26.9-impression-patterns.md`
- `workflow/plans/plan-27-memory-fleet-rollout.md`
- `workflow/plans/plan-27-memory-fleet-rollout-tasks/task-27.1-fleet-inventory.md`
- `workflow/plans/plan-27-memory-fleet-rollout-tasks/task-27.5-cliquedb-at-session-boundary.md`
- `workflow/plans/plan-27-memory-fleet-rollout-tasks/task-27.6-per-store-compile-and-landing.md`

## Per G-row

### G4 / G15: task 26.5 (`#rev-round-6`)

- **Header.** 26.5 now depends on bug-216 being merged, adding the rel `depends-on
  task-bug216-rule-docs-in-graph`. The `#files` list gains the rev-6 files: `handoff.py`,
  `memory_layout.memdir_of`, the `ingest_gmd.py` reroute, `cli.py` output, and
  `tests/test_ingest_gmd_memdir_route.py`. The part-way-failure monkeypatch is registered in
  `test_mock_registry`, and the bug-202 existence log is added.
- **`#pre-bug208` (L9, Ca-5).** bug-208 is a precondition inside 26.5. AC-208 is RED and GREEN
  before AC-4's marker write is recorded GREEN, and the commit order shows it.
  - R-208a (s-1): an atomic write, to a dot-temp file followed by `os.replace`, keeping the file
    mode. It calls the existing bug-199 `_atomic_write_text` shape through one shared helper.
  - R-208b (m-2): the error names a moved legacy file, on the CLI and in the MCP `VerbError`.
  - R-208c (m-1): `created:` comes from the copy the walk keeps (the `if organised` guard is
    dropped at `handoff.py:432`).
  - R-208d (m-3): three killing tests.
  - AC-208 (a)-(d) has four named mutations.
- **`#bug202-restore` (L9, Ca-6, bsd-pop-r1 M4).**
  - R-202a, read-only and first: read each row's `source_path` through the daemon, test that path
    as written and as resolved, then run a scoped search by frontmatter id. The search never
    starts from `/` and skips `_frameworks_and_libraries`. The result is logged.
  - R-202b, if the files are found: a forced re-bridge of that file, checked by comparing the
    anchor set (names and count) against the file. This is a live write, run with the deployed
    `rmx` and announced first.
  - R-202c, if they are not found: the bug-202 restore note closes with the reason, and the rows
    are kept.
  - AC-202 checks the log and the branch taken.
  - Observed today: the rows are live. `rmx context guardrail-coordinator-lane-dispatch` returns
    the body.
- **`#bug220-route` (L37, X1).**
  - R-220a: one resolver, `memory_layout.memdir_of(path)`. It returns the nearest ancestor with a
    marker (a malformed marker is a hard error), else the `~/.claude/projects/<slug>/memory`
    shape, else None. R-264a is this function plus its refusal on None.
  - R-220b: with `as_memory=False`, memdir files are ingested through the memory path (it routes
    them and never refuses them). This covers kind, partition, the 26.4 save-state rule and the
    `iter_memory_files` exclusions. The existing purge of a `kind=doc` twin (`ingest_gmd.py:1376`)
    removes old twins.
  - R-220c: the result carries a `rerouted_to_memory` count with names, and the count is printed.
  - R-220d: the reroute runs after bug-216's `should_ignore`, and the X1 pins stay green.
  - R-220e: the store question is open item T2-O1.
  - The reroute is not marker-gated: it writes no file, and the ADR is amended to say so.
  - AC-220 has cases (a)-(f): a memdir target, file and subdir targets, a marker-on dir outside
    the projects path, a mixed root, twin cleanup, and a re-run of the X1 pins. It has four
    mutations.
- **`#q8-b`.** These lines change under Q8 b:
  - AC-5's forced save-state re-bridge and its `forced` stat; the replacement is G22's work,
    through plan-22's audited path;
  - R-264b's sticky-row repair;
  - AC-6's save-state recall bullet;
  - R-220b for save-states.

  The file-side type rewrites stay.

### G6: task 26.7 (`#rev-round-3`, `#ac-e`)

- **Header.** 26.7 depends on 25.1 rev 7 being merged (D-Q2), with the rel `depends-on
  task-25.1#r4`. It records that the 26.6 R3 residual comes next (L1).
- **AC-E: 25.1's curated-hook lookup survives the regroup.** The fixture copies an organised
  memdir with at least five hooked memories: a member of one subject, a member of two subjects,
  a folded memory, a memory on its type line, and a memory that 26.5 moved.
  - (a) `load_hooks` returns byte-identical hooks before and after the 19.3 render. No hook is
    replaced by subject-line text, a fold line, or a `…` cut.
  - (b) Two renders leave the sidecar byte-identical, and `index --check` reads in sync.
  - (c) The real `rmx memory recall --pack` prints the curated hooks: 25.1 AC-9's id-keyed case,
    re-run.
  - (d) The marker-off twin passes the path-keyed case.
  - Three mutations.
- **`#q8-b`.** Nothing changes under Q8 b: the index is file-side.

### G19: tasks 26.8 and 26.9, plan-26, plan-27 and its tasks, ADR-0005

- **26.8 (`#rev-round-6`).**
  - The header says "26.0-26.7 merged" includes the 26.6 R3 residual. New rels depend on ADR-0005
    `#appendix-memory-rules` and `#appendix-forget-step`.
  - AC-8, L11: apply the amended Appendix A, which carries the marker condition. The applied
    section must byte-equal the ADR block, and the diff is recorded. If the user edits the text,
    the edit is written back into the ADR in this task's commit.
  - AC-8, L12: forget step 5 is shown to the user in the same window. First, re-check at the
    deployed sha that the bridge never forgets a deleted file. The step is applied only if the
    user accepts, and the answer is recorded verbatim.
  - `#counts-reread`. Read 2026-11-13: 306 top-level files (44 save-states and 262 typed:
    72 feedback, 175 project, 15 reference) and 80 impressions. `~/.claude` still tracks 2 files
    and now carries 231 unstaged deletions, 93 of them under the old cliquedb dir. The new rules:
    - AC-3: re-survey before the preview, and the preview must equal that survey exactly;
    - AC-2: `moved` equals the preview's move count, exact; `moved_legacy` (19 on 2026-11-09) is
      re-probed at AC-0, and a re-probe other than 19 gets a bug row before AC-4;
    - AC-4: re-read the dirt count at the step;
    - AC-6: re-list the 20 pre-0.34 subject rows at the step.
  - `#q8-b`: the AC-0 and AC-2 save-state terms lose their store side, and AC-5's save-state
    recall becomes `recall-state` only.
- **26.9 (`#rev-round-4`).** The header says it runs in parallel with plan-27 after 26.8 (L10).
  The two share no `src/` file and touch different memdirs. The `#why-state` counts are re-read
  (`IMPRESSIONS.md` 307 lines / 56 KB; 80 impressions), and AC-3 already pre-measures at run
  time. Q8 b changes nothing.
- **plan-26 (`#rev-round-6`, appended at the end).**
  - `#overlap-25-1-waiver`: the D-Q2 waiver of plan-26:358, tied to 26.7 AC-E. 25.1b is not
    waived.
  - `#overlap-r3-residual` (L1).
  - `#overlap-26-9-plan-27` (L10).
  - The Sequencing line now cites the 2026-11-13 queue.
  - `#user-gates` (L45):
    - 26.5: announcing the bug-202 restore, only if the files are found;
    - 26.8: the stop when `refresh_pending` is over 50, the `--apply` go-ahead, the `~/.claude`
      commit, the AC-8 MEMORY-RULES text plus the forget-step decision, and any live rollback;
    - 26.9: per-document approval and its live AC-5.
- **plan-27 (`#rev-round-6`).**
  - The header says 26.9 is not a dependency (L10). New rels derive from L-rows and D-Q5.
  - `#survey-refresh` (L13): the table is the 2026-11-08 survey and is refreshed at 27.1 AC-0.
  - `#facts-hooks-0820`: the facts bullet has been stale since 0.82.0. viascope, cliquedb and
    cliquet settings carry the `ingest-gmd` bridge (read 2026-11-13). bdep/thiquet and atlftpd
    were missed by the hub-driven re-install.
  - `#non-goals` amended, and Q3 gains `#q3-rehost` (L13 + D-Q5). Plan-27 still only reports
    hook drift. Regeneration rides the user-gated `install-hooks` window that finds fleet repos
    by their hook marker (opened by queue item 1, later windows batched), and drifted repos go
    on its list.
  - `#user-gates`: tracked-repo commits (27.0, 27.2, 27.2a, 27.4); the 27.2a approval; the 27.2
    Q1 diff and the archive go; the 27.3 acknowledgement; 27.4 stops on a failure or refusal and
    waits for live-session acknowledgements; the 27.5 cliquedb acknowledgement; 27.6 is
    report-only.
  - `#q8-b`.
- **27.1 (`#ac-0`, `#rev-round-6`).** Refresh `#survey` and `#facts` before AC-1. The hook
  column is measured two ways: settings files plus the post-commit marker over `~/github`,
  `~/claude_tools` and `~/enduris`, skipping `_frameworks_and_libraries`, not via the hub alone.
  A repo found only by its marker is added. The work is logged and read-only.
- **27.6 (`#rev-round-4`).** AC-3's recommended action points at the `install-hooks` window, not
  plan-24.
- **27.5 (`#q8-b`).** Under Q8 b, AC-3's recall of `savestate_7c4e19d2a8f3` becomes
  `recall-state` plus a check that the file's type was rewritten.
- **ADR-0005.**
  - Appendix A (L11): the text carries the marker condition, in the same wording as the shipped
    `/save-state` command. In an organised dir: write into the type folder and link with the
    folder. In a flat dir: write at the top level, link without a folder, and never create a type
    folder by hand. `#appendix-memory-rules-why` explains the reason.
  - New `### A.2` `#appendix-forget-step` (L12): the proposed step 5, `rmx memory forget <id>`.
    It says the bridge never forgets a deleted file (no such path in `ingest_gmd.py`, read
    2026-11-13), and it notes the decay-rule tension.
  - `#marker`'s every-dir list gains classification by location (bug-220).
  - The `#open` "Marker encoding" question is marked closed (by `#marker-encoding`).
  - New `#amendments` and `#q8-b` sections. The status stays Proposed.

## Open items (recommendation first)

- **T2-O1: bug-220 when the memdir belongs to a different store (26.5 R-220e).**
  - (b) **Recommended.** Route through the memdir's own store's daemon via
    `_sync_memory_dir(memdir, root=)`, per ADR-0005 `#store-resolution`. After bug-216's prune,
    only explicit CLI targets reach memdirs, so this costs only a resolver call and a cross-store
    write from the CLI.
  - (a) Write into the calling store, as `--as-memory` does today. The spec text holds to this
    until the lead rules, and names any file whose memdir resolves elsewhere.
  - (c) Refuse that subset loudly. This conflicts with the user's "route, never refuse".
- **T2-O2: how to force a re-bridge of one file for bug-202 (R-202b).** This only matters if
  R-202a finds the files, and M4 suggests it will not.
  - (a) **Recommended.** `organise --apply --force-rebridge <id>`, extending AC-5's existing force
    input.
  - (b) A new `ingest-gmd --as-memory --force` flag on the bridge.
- **T2-O3: bug-208 scope.** R-208b (m-2) and R-208c (m-1) come from findings the bug-208 row
  lists in its symptom but not in its fix column.
  - **Recommended:** keep them; they touch the same function and the fixes are prescribed.
  - The alternative is to strike them to a backlog row.
- **T2-O4: reading of L37's "same marker gate".**
  - **Recommended:** the reroute reuses the marker reader inside `memdir_of`, and is itself
    ungated. It is store-side and writes no file, and the bug-220 row detects a memdir by marker
    OR the projects path. The ADR every-dir list is amended to match.
  - The alternative, gating on the marker, would keep minting `kind=doc` twins in flat
    `~/.claude/projects` memdirs until plan-27 organises them.
- **T2-O5: forget step 5 and the decay rule.** `rmx memory forget` is a deletion, and
  `feedback_decay_never_loses_knowledge` allows removal only through an audited path. L12 puts the
  step to the user regardless.
  - **Recommended:** keep it as a user decision at AC-8; A.2 states the tension.
  - The alternative is to route it through plan-22's audited path, which does not exist yet for
    single memories.

## Contradictions the plan review missed

1. **A fourth copy of the order D-Q2 waives.** plan-26:358 says "26.7 (19.3) closes before 25.1
   starts". D-Q2 and G3 list only plan-25 `#ordering`, task-25.1 `:22-24`/`:34` and POP row 25.
   Fixed in plan-26 (`#overlap-25-1-waiver`).
2. **Two more references to plan-24 left with no host.** Once D-Q5 superseded plan-24's D1,
   plan-27 `#non-goals` ("plan-24's mod replaces the shell hooks anyway") and 27.6 AC-3
   ("regeneration rides plan-24") pointed nowhere. L13 re-hosted only Q3. Both are fixed.
3. **ADR-0005 contradicted itself.** `#open` still listed "Marker encoding" as open, while the
   same ADR's `#marker-encoding` settled it on 2026-11-09. Fixed.
4. **The "93 deletions" figure is stale.** 26.5, 26.8, plan-27 and 27.1 say `~/.claude` carries
   93 unstaged deletions. The real count is now 231, of which 93 are under the cliquedb dir.
   The never-`commit -a` rule still holds. 26.8 re-reads the count at run time; the other
   mentions stay as historical context.
5. **bug-202's rows are live but their files are missing.** The rows still exist in refmatrix's
   store; the files have not been found. Read each row's `source_path` (26.5 R-202a) before G27
   touches the bug-202 row. The anchor loss was measured on refmatrix's snapshot, so the files
   may have been bridged from outside refmatrix's memdir.
6. **The repo lint gate cannot run in spec clones.** `scripts/lint-gmd.sh` hard-requires
   `.venv-eval`, so it cannot run in the littlebig clones. Per-file `tools/gmd/lint.py` was used
   instead.
7. **Plan text still frames hooks as "stale" from the hub-only view.** The 0.82.0 re-install was
   driven by `rmx hub status`, so bdep/thiquet and atlftpd still run silent pre-26.2 hook bodies.
   Queue item 1's `install-hooks` window must find repos by marker, as G31 implies. The plan
   review never names this for plan-27; it is now in plan-27 `#facts-hooks-0820` and 27.1 AC-0.
