## [2026-09-06 12:00] bootstrap | docs/ tree → GMD conversion
converted: [[ARCHITECTURE]] [[SYSTEM]] [[INTEGRATION]] [[PERFORMANCE]] [[adr-format]] [[agent-doc-primer]] [[0001-intuition-lance-integration]] [[intuition-style-hooks]] [[adr-template]] [[concept-doc-template]] [[design-doc-template]]
already-gmd (untouched except link fixes): [[system_design_review]] [[gmd-migration-guide]] [[adr-0000-adr-overview]] [[adr-0002-subject-memory-container]]
anchors-added: 158; rel-edges-added: 23; prose-citations→wikilinks: ~15
fixed: [[refmatrix-daemon-index-drift-recurrence]]→[[project_daemon_index_drift_recurrence]] (0001); stale "(when created)" template ref (agent-doc-primer); adr-0000 grandfather note + index row
lint: 0 errors, 1 pre-existing warn (rel-target-shape docs/); memory-layer wikilinks verified via --scope ~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory
note: lint.py --reconcile misses this repo's memory dir (slug keeps `_` in claude_tools; actual dir dashifies) — use explicit --scope
