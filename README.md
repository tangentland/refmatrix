# refmatrix

**Concept-graph content indexing + memory for Claude Code.** A roaring-bitmap
reference matrix over **documents, code, concepts, and memory** — a hyper-tldr
index that answers set-algebra questions about a codebase that `grep` can't,
and doubles as the durable memory layer for an agent.

```bash
rmx query "defines:auth AND NOT mentions:auth"   # code that implements auth, documented nowhere
rmx context parse --format json                   # one LLM-ready bundle: body + graph + file:line
rmx memory recall "why did rotation get dropped"  # dense recall over curated memories
```

## Benchmarks — symbolic retrieval beats dense embeddings

rmx ships a reproducible eval harness (`eval/`) against `cornstack/CodeRankEmbed`
on CodeSearchNet (BEIR layout). The tuned **symbolic** stack — BM25 + docstring/code
linkage split + coverage^α + linkage-coupled co-mention, **no embeddings, no GPU,
no reranker** — wins on every headline metric, with the biggest edge in
**top-rank recall**:

### CSN Python (43 827 docs · 14 918 queries)

| Metric        | rmx (symbolic) | CodeRankEmbed (dense) | Δ        |
|---------------|:--------------:|:---------------------:|:--------:|
| **Recall@1**  | **0.971**      | 0.934                 | **+0.037** |
| **Recall@10** | **0.997**      | 0.993                 | +0.004   |
| MRR@10        | **0.982**      | 0.959                 | +0.024   |
| nDCG@10       | **0.986**      | 0.967                 | +0.018   |

### CSN JavaScript (margin *larger* than Python)

| Metric        | rmx       | CodeRankEmbed | Δ        |
|---------------|:---------:|:-------------:|:--------:|
| **Recall@1**  | **0.920** | 0.895         | **+0.025** |
| **Recall@10** | **0.970** | 0.951         | +0.019   |
| MRR@10        | **0.939** | 0.916         | +0.023   |

### CSN TypeScript (real-world corpus w/ fork dupes — low absolute, still ahead)

| Metric        | rmx       | CodeRankEmbed | Δ        |
|---------------|:---------:|:-------------:|:--------:|
| **Recall@1**  | **0.244** | 0.241         | +0.004   |
| **Recall@10** | **0.660** | 0.644         | +0.016   |
| MRR@10        | **0.365** | 0.358         | +0.007   |

Latency: rmx ≈ 3–4 min ingest + ~70–100s retrieve (8-worker, CPU). CodeRankEmbed
≈ 100 min corpus encode (GPU/MPS) + ~1 min retrieve. rmx wins on accuracy,
latency, *and* explainability — every score traces to `file:line` evidence. Full
methodology + the tuning ablation in [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

## What it is

Every entity in your project — a doc, a source file, a function, a concept, a
**memory** — gets a stable integer column id. Every concept gets a row. **Linkage
types** (`defines`, `calls`, `mentions`, `imports`, `is_a`, `related-to`, plus
any custom verb) are the field axis. Each `(linkage_type, concept_id)` cell is a
roaring bitmap of the entity column ids that satisfy that relation.

The model mirrors [Pilosa](https://github.com/FeatureBaseDB/featurebase)
(index → field → row → column). Storage is a single **DuckDB** catalog plus
in-process [pyroaring](https://github.com/Ezibenroc/PyRoaringBitMap) bitmaps;
dense vectors (for memory/code recall) live in **Lance**. An optional per-store
**daemon** owns the writer so editor + watcher + CLI never contend on the lock.
No external server, no HTTP — a single-binary CLI.

## Install

```bash
git clone https://github.com/tangentland/refmatrix && cd refmatrix
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[watch,dense,dev]'      # dense = Lance + sentence-transformers (memory recall)
rmx --version
```

To call `rmx` outside the venv, drop a shim into a `$PATH` dir:

```bash
cat > ~/bin/rmx <<'EOF'
#!/usr/bin/env bash
exec env -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 \
  /path/to/refmatrix/.venv/bin/rmx "$@"
EOF
chmod +x ~/bin/rmx
```

## Five-minute tour

```bash
mkdir demo && cd demo && git init -q
rmx init                                  # creates .refmatrix/ (DuckDB catalog)
rmx ingest . --semantic                   # files + Python AST (imports + docstrings) + markdown/GMD

rmx query "defines:parser"
rmx query "defines:parser AND NOT mentions:parser"   # implementation gap
rmx neighbors parser --depth 2
rmx context parser                                   # token-budgeted bundle (body + graph)
rmx stats
```

With [llm-tldr](https://github.com/parcadei/llm-tldr) installed you get a full
call graph too:

```bash
rmx tldr-warm . --semantic        # warm tldr cache + ingest call graph + Python semantics
```

## The query surface

### DSL (infix set algebra)

```bash
rmx query "mentions:parser AND defines:parser"
rmx query "calls:foo OR (mentions:bar AND NOT imports:legacy)"
rmx query "parser"                                     # bare: union over all linkages
rmx query "defines:auth AND NOT mentions:auth" --ids-only
```

Operators: `AND` / `&&`, `OR` / `||`, `NOT` / `!`, parentheses. A term is
`linkage:concept` (or bare `concept` for "any linkage").

### PQL (Pilosa-style functions)

```bash
rmx query --pql "Intersect(Row(calls, foo), Row(mentions, bar))"
rmx query --pql "Difference(Row(calls, x), Row(defines, x))"   # ghost callers
rmx query --pql "TopN(Row(defines, parser), 5)"
```

Functions: `Row`, `Intersect`/`And`, `Union`/`Or`, `Difference`/`Diff`, `Xor`,
`TopN`, `Neighbors`, `Count`.

### Higher-level helpers

```bash
rmx neighbors parser --depth 2 --limit 50
rmx co-occur parser --type mentions
rmx top parser --type mentions -k 10                   # weighted top-N
rmx context parser                                     # token-budgeted bundle (body + graph)
rmx context parser --format json                       # LLM-ready
rmx context --since main                               # branch-scoped: concepts touched since main
rmx concept timeline parser                            # when a concept was introduced / worked on
rmx query "defines:auth" --explain                     # file:line evidence per membership
rmx describe src/parser.py                             # EVERY stored fact about one entity
rmx describe parser --format json                      # same dump, machine-readable
```

`rmx context <name>` resolves a concept **or** a same-named memory: it returns
the memory body inline AND the graph neighborhood in one bundle, with KWIC
snippets centered on the matched term.

## Memory, sessions & dense recall

refmatrix is also the agent memory layer. Curated `.md` memories and Claude Code
session transcripts are first-class entities, kept out of the code graph's
ranking but reachable through their own recall surfaces.

```bash
# Curated memories (kind=memory + body sidecar + rel: graph)
rmx memory sync-disk ~/.claude/projects/<proj>/memory   # ingest curated .md memories
rmx embed --kinds memory                                # dense vectors (Lance)
rmx memory recall "why was the writer rotation dropped" # hybrid dense + symbolic recall
rmx memory get <slug>                                   # body + frontmatter
rmx memory dedup                                        # fold any concept↔memory duplicate nodes

# Past Claude Code sessions, compressed to GMD cards
rmx session ingest                                      # index this project's session JSONLs
rmx session recall "slot rotation"                      # KWIC search over session cards
```

Sessions and curated memories live in their own partitions so dense English
prose never drowns out code/specs in the concept graph's BM25 ranking.

## `rmx reingest` — one command to make a store correct

Runs every ingest pass over every source in canonical order, then embeds —
each pass gated/incremental:

```bash
rmx reingest                  # code+docs → memory → sessions → embed, in order
rmx reingest --no-sessions --no-embed
```

This is the "rebuild this store consistently" command; it picks the right pass
per source so the read surfaces (`context`, `scan-prompt`, `recall`) see one
coherent graph.

## Primer & prompt-aware context (LLM hooks)

```bash
rmx primer --top 150 --out .refmatrix/PRIMER.md         # static: density-ranked symbol map
echo '{"prompt":"fix register_graph_object handler"}' | rmx scan-prompt   # dynamic: prompt → bundles
```

`rmx install-hooks --apply` wires `primer` to `SessionStart` and `scan-prompt`
to `UserPromptSubmit`, so every Claude session loads a fresh symbol map and gets
context bundles injected for symbols it mentions. `build_context` is shared by
`context`, `scan-prompt`, and `memory recall`, so a fix to one improves all.

## Concept namespacing

Auto-generated concepts are namespaced so they don't collide with hand-added
ones:

| Namespace | Source | Example |
|---|---|---|
| `keyword/` | docstring keywords (semantic ingest) | `keyword/tokenizer` |
| `import/` | Python `import` statements | `import/json`, `import/tree_sitter` |
| (none) | function-name concepts + your own `add-concept` | `parse`, `register_graph_object` |

Query a namespaced concept with the slash in the term: `rmx query "imports:import/json"`.

## Custom linkage types

```bash
rmx add-linkage-type implements --description "code implements concept"
rmx link parser src/foo.py --type implements
rmx query "implements:parser AND NOT tested_by:parser"
```

GMD ingest auto-creates linkage types from any `rel: <verb> -> [[target]]` line,
so authored docs can introduce verbs without code changes.

## Keeping the index fresh

```bash
rmx install-hooks --apply        # git post-commit/merge/checkout + Claude Code hooks
rmx sync -f path/to/changed.py   # the freshness primitive hooks call
rmx watch . --semantic           # watchdog daemon for editor-driven flows
rmx daemon start                 # per-store socket server: single writer, hot bitmaps
```

| Target | Purpose |
|---|---|
| `.git/hooks/post-commit` | `rmx sync --since HEAD~1` after each commit |
| `.git/hooks/post-merge` / `post-checkout` / `post-rewrite` | sync the relevant diff |
| `.claude/settings.local.json` | `PostToolUse` enqueue · `Stop` flush · `SessionStart` primer · `UserPromptSubmit` scan-prompt |
| `.refmatrix/CLAUDE.md` · `PRIMER.md` | briefing + density-ranked symbol map |

## Storage layout

```
.refmatrix/
├── catalog.A.duckdb / catalog.B.duckdb   # DuckDB catalog (one slot is the pinned writer)
├── active                                # marker: which slot is the writer
├── catalog.read.duckdb                   # snapshot-tier: lock-free read copy, refreshed after writes
├── read_only.duckdb                      # symlink → the current reader (snapshot)
├── vectors/<partition>/<kind>.lance      # dense vectors for memory/code recall
├── facts.log                             # append-only mutation log (replayable: rmx rebuild --from-log)
├── rmxd.sock / rmxd.pid                  # daemon socket + lock
├── dirty.queue                           # hook-populated, drained by sync --flush-queue
└── CLAUDE.md / PRIMER.md                 # agent briefing + symbol map
```

Entities, concepts, linkage types, the `entity_links` forward index, bitmap
fragments (BLOBs), and the `memory_content` sidecar all live in the DuckDB
catalog. The forward index makes deletes O(links) instead of a full bitmap scan.

## Concept model

| Term | What it is |
|---|---|
| **Entity** | A column. `kind ∈ {doc, code, concept, memory}`. Concepts are entities too, so concepts link to concepts. |
| **Concept** | A row label, stable id by name. |
| **Linkage type** | A named relation (the field axis). Directed by default; symmetric ones like `related-to` excepted. |
| **Bitmap** | A roaring set of entity ids, packed `(concept_id << 32) | entity_id`. |
| **Weight** | Optional float on `(entity, linkage, concept)` — drives `rmx top` + weighted ranking in `context`. |
| **Partition** | A logical namespace in one shared catalog (per-project code, memory, sessions). |

## Architecture

```
   ┌─────────────────────────────────────────────────────────────┐
   │  CLI (click + rich): query · context · memory · session ·    │
   │  ingest · reingest · embed · sync · daemon · install-hooks   │
   └───────────────────────────┬─────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  Daemon (per-store unix socket) — owns the writer, serves     │
   │  reads from the snapshot, hosts the embedder + fs watcher     │
   └───────────────────────────┬─────────────────────────────────┘
        ┌──────────────┬────────┴────────┬──────────────┐
        ▼              ▼                 ▼              ▼
   ┌─────────┐   ┌──────────┐    ┌────────────┐  ┌───────────┐
   │ ingest  │   │  query   │    │  Store      │  │  embed    │
   │ /reingest│  │ /context │    │ DuckDB +    │  │  (Lance   │
   │ /gmd    │   │ /scan    │    │ roaring +   │  │  dense)   │
   │         │   │ /recall  │    │ memory side │  │           │
   └─────────┘   └──────────┘    └────────────┘  └───────────┘
```

**Reads** come from the snapshot-tier copy (`catalog.read.duckdb`), never the
write-locked slot — so a query never blocks on an ingest. The writer stays
**pinned** to one catalog slot for the daemon's life (writer rotation was
retired in 0.7.7); the snapshot is regenerated shortly after each write. Deeper
detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/SYSTEM.md`](docs/SYSTEM.md).

## Relationship to llm-tldr

refmatrix consumes [llm-tldr](https://github.com/parcadei/llm-tldr) output — tldr
is the per-function extractor, rmx is the cross-entity index + query engine +
agent memory surface. They compose; neither bundles the other.

Source priority (auto): `.tldr/cache/semantic/metadata.json` (richest) →
`.tldr/cache/call_graph.json` → `tree` walk (file-level only). Force with
`rmx ingest . --source metadata|tldr|tree`.

## Development

```bash
source .venv/bin/activate
env -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 pytest tests/ -q
```

502 tests, ~90 seconds.

## License

MIT.
