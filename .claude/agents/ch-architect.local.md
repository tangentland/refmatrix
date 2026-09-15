# ch-architect — refmatrix overlay

## This project's architecture

- **Core primitives:** entity / concept / linkage bitmaps; partition; Store (DuckDB + Lance +
  pyroaring); daemon (single writer, ops registry, fast-exit); hub (watchdog, shared model
  workers, global memory, bus); STM focus → durable memory; verbs (agent capability layer);
  generated hooks. Defined in `.claude/PROJECT_PROFILE.md` §primitives.
- **Design tenets doc:** `docs/SYSTEM.md` + `docs/ARCHITECTURE.md`; charter memory
  `project_refmatrix_mission_charter` ("conceptual memory is the product; symbolic retrieval is
  table stakes").
- **ADR conventions:** `docs/adr/NNNN-slug.md`, GMD, status weighting per `docs/adr-format.md`;
  `docs/adr/0000-adr-overview.md` is the index. New ADRs also get a row in `docs/INDEX.md`.
- **Known constraints:** one writer per store (the daemon); CLI reads on the snapshot; writes via
  `_store(write)`; every agent-facing capability is a verb; hook config is generated; memory
  paths never fail silently; the benchmark path is the production path.

## Where architectural truth lives

- ADRs: `docs/adr/` · System/architecture: `docs/SYSTEM.md`, `docs/ARCHITECTURE.md`,
  `docs/INTEGRATION.md`, `docs/PERFORMANCE.md` · Negative results: `PERFORMANCE.md` + memories
  `project_retrieval_negatives_*`.

## Review emphasis

Write-path safety under the single-writer model (daemon vs in-process fallbacks), supervisor
interactions (launchd + hub watchdog: never SIGKILL a busy daemon), and "two ways to do X"
(second bridge, second hook source, second runtime) — collapse to one.
