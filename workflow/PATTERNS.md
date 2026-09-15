---
gmd: "0.1"
id: PATTERNS
title: "Code Patterns"
tags: [reference]
metadata:
  node_type: doc
---

# Code Patterns {#root}

Common patterns used throughout the codebase. Copy-paste these to avoid re-reading source files.

## Ground Rules {#ground-rules}

1. **No mocks in production code** — all `src/` code must be fully concrete. No stubs, no
   `NotImplementedError`, no placeholder logic. If it can't be real, it doesn't exist yet.
2. **Mocks only in tests** — `tests/` may mock external services (databases, APIs, hardware).
3. **Tech stack** — see `TECH_STACK_DECISIONS.md` for approved libraries and rationale.

## Testing Patterns {#testing-patterns}

### Tmp store {#tmp-store}
```python
import tempfile
from pathlib import Path
from refmatrix.store import Store

def test_something():
    root = Path(tempfile.mkdtemp(prefix="rmx-"))   # SHORT path: unix socket sun_path limit
    s = Store(root / ".refmatrix"); s.init()
    ...
```

### Real-path bridge test (no mocking the SUT) {#real-path-test}
```python
def test_bridge_ingests_a_memory_file(tmp_store, tmp_path):
    (tmp_path / "m.md").write_text('---\ngmd: "0.1"\nid: m\ntitle: "m"\ntags: [x]\n---\n# m {#root}\nbody\n')
    report = _sync_memory_dir(tmp_path)          # the function under test, unpatched
    assert tmp_store.get_memory("m") is not None  # observed through the store, not a stub
```

### Hook block equality {#hook-equality}
```python
from refmatrix.hooks import _claude_hook_block
block = _claude_hook_block(refmatrix_root, ...)
assert installed["hooks"] == block["hooks"]    # `rmx install-hooks --check` does this at runtime
```

## Code Patterns {#code-patterns}

### Daemon op {#daemon-op}
```python
def _op_thing(d: Daemon, args: dict) -> dict:
    """WHY this exists + the incident date."""
    with d._store_lock, d._st().with_partition(args.get("partition") or d.store._partition_name):
        return {"rows": ...}
OPS["thing"] = _op_thing          # unregistered ops never run
```

### Verb + adapters {#verb-adapters}
```python
@verb("rmx_thing", "one-line description")
def thing(root: Path, *, arg: str) -> dict: ...
# mcp.py: TOOLS entry generated from the verb; cli.py: click command calling verbs.thing
```
