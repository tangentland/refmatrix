---
gmd: "0.1"
id: test_mock_registry
title: "Test Mock Registry — mock governance"
tags: [process, testing, governance]
metadata:
  node_type: registry
---

# Test Mock Registry {#root}

Mock governance for `refmatrix`. Every mock in `tests/` is classified here. Production
code (`src/`) contains **no mocks** — see CLAUDE.md "No Mocks in Production Code".

## Classification {#classification}

| Classification | Meaning | Allowed? |
|----------------|---------|----------|
| `external` | External library, platform API, third-party service | Permanent |
| `internal-active` | Internal subsystem with existing implementation | **Must graduate** |
| `internal-pending` | Internal subsystem not yet built | Temporary |

## Registry {#registry}

| Mock | Target | Classification | Test File(s) | Graduation Plan |
|------|--------|----------------|--------------|-----------------|
| `cli._sync_memory_dir` (lambda) | the memory bridge itself | internal-active | tests/test_save_state.py | plan 3: replace with a real tmp-store ingest test |
| `monkeypatch.setattr` sites (184, unregistered) | various | internal-active | tests/ | plan 6 sweep: register or graduate |

## Graduation Log {#graduation-log}

| Date | Mock | From → To | Notes |
|------|------|-----------|-------|
| — | — | — | — |
