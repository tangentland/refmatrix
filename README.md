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

rmx ships two eval harnesses. The number that matters comes from the **honest
production harness** (`eval/production/`): it materializes the BEIR corpus as
real files, runs the production `rmx ingest --semantic` path, and ranks
through the same `content_rank` that `rmx context` calls — no bespoke index,
no benchmark-only tokenizer.

### CSN Python, production path (43 827 docs · 14 918 queries)

| Metric        | rmx (symbolic, CPU) | CodeRankEmbed (dense, GPU) |
|---------------|:-------------------:|:--------------------------:|
| MRR@10        | **0.961**           | 0.959                      |
| Recall@1      | **0.944**           | 0.934                      |
| Recall@10     | 0.984               | 0.993                      |
| nDCG@10       | 0.967               | 0.967                      |

The historical bespoke harness scores 0.972 — a true number about code users
never ran; refmatrix defends the production 0.961 instead. On the bespoke
harness the symbolic win repeats across languages: JS **0.939 vs 0.916**,
TS **0.365 vs 0.358** (real-world corpus with fork dupes; low absolute,
still ahead).

Latency: rmx ≈ 3–4 min ingest + seconds to retrieve, CPU only. CodeRankEmbed
≈ 100 min corpus encode (GPU/MPS). And every rmx score traces to `file:line`
evidence. Full methodology, the proactive-retrieval (MemAware) benchmark, and
the measured-negatives table live in [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

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

A user-level **global store** (`~/.refmatrix`) holds cross-project behavior
memories. It is memory-only by construction: every ingest route — daemon ops
and direct CLI alike — structurally refuses filesystem code/doc paths there
(`ingest-gmd --as-memory` is the one sanctioned write shape).

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

`scan-prompt` ranks its bundles with salience-seeded **personalized PageRank**
over the concept graph (measured against a degree-walk alternative — PPR wins
5x; see PERFORMANCE.md's negatives table).

## Drop-in learning grep

`bin/rmxgrep` and `bin/rmxrg` are byte-exact grep/rg drop-ins (`alias
grep=rmxgrep`): outside an rmx project they exec the real tool untouched;
inside one, every search teaches the graph — index-first with annotated hits
in rich mode, real-tool bytes plus a throttled background teach ping in plain
mode. `rmx grep` honors bare grep flags, greps a pipe when stdin is piped
(explicit path args win, per grep's contract), and **fails loud (exit 2)**
on anything it can't honor byte-exactly — the wrappers fall back to the real
tool, so the worst case is plain grep behavior, never a silently wrong answer.


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

1361 tests.

## License

MIT.
