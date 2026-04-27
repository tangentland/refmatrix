# refmatrix

A roaring-bitmap-backed reference matrix for **documents, code, and concepts**.
A hyper-tldr index that lets you ask set-algebra questions about a codebase
that `grep` can't answer.

```bash
rmx query "defines:auth AND NOT mentions:auth"
# code that implements `auth` but is documented nowhere
```

## What it is

Every entity in your project — a doc, a source file, a function, a concept —
gets a stable integer column id. Every concept gets a row. **Linkage types**
(`defines`, `calls`, `mentions`, `imports`, `is_a`, `related_to`, plus any
custom one you add) live as fields. Each `(linkage_type, concept_id)` cell is
a roaring bitmap of the entity column ids that satisfy that relation.

The conceptual model mirrors [Pilosa](https://github.com/FeatureBaseDB/featurebase)
(index → field → row → column), but storage is in-process via
[pyroaring](https://github.com/Ezibenroc/PyRoaringBitMap) plus a SQLite catalog.
No server, no HTTP, single-binary CLI.

## Install

```bash
git clone <this repo> && cd refmatrix
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[watch,dev]'
rmx --version
```

To call `rmx` outside the venv, drop a shim into a directory on your `$PATH`:

```bash
cat > ~/bin/rmx <<'EOF'
#!/usr/bin/env bash
exec env -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 \
  /path/to/refmatrix/.venv/bin/rmx "$@"
EOF
chmod +x ~/bin/rmx
```

(The env-clearing matters if you have a global `PYTHONPATH` — without it your
user-site packages can shadow the venv's.)

## Five-minute tour

```bash
mkdir demo && cd demo
git init -q                              # so post-commit hook has somewhere to live
rmx init                                 # creates .refmatrix/ in cwd

# ---- manual entities + concepts ----
rmx add-concept parser -d "anything that turns text into structure"
rmx add-concept tokenizer
rmx add-entity --kind code src/foo.py --tldr "@core/foo: dispatch + parse"
rmx add-entity --kind code src/lex.py --tldr "tokenizer impl"
rmx add-entity --kind doc README.md      --tldr "high-level overview"

# ---- linking ----
rmx link parser src/foo.py --type defines
rmx link parser README.md  --type mentions
rmx link parser src/lex.py --type related_to
rmx link tokenizer src/lex.py --type defines

# ---- query ----
rmx query "defines:parser"
rmx query "defines:parser OR mentions:parser"
rmx query "defines:parser AND NOT mentions:parser"   # implementation gap
rmx query "parser"                                   # bare term: any linkage
rmx neighbors parser --depth 2
rmx co-occur parser --type defines
rmx stats
```

Output of `rmx query "defines:parser OR mentions:parser"`:

```
┏━━━━┳━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ id ┃ kind ┃ name       ┃ path         ┃
┡━━━━╇━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 3  │ doc  │ README.md  │ ./README.md  │
│ 4  │ code │ src/foo.py │ ./src/foo.py │
└────┴──────┴────────────┴──────────────┘
cardinality=2
```

## Auto-ingest from a real codebase

`rmx tldr-warm` shells out to [llm-tldr](https://github.com/parcadei/llm-tldr)
to build a call graph, then ingests it:

```bash
rmx tldr-warm . --semantic        # warm + ingest call graph + Python imports + docstrings
rmx stats                         # see what was extracted
rmx list-entities --kind concept  # one row per function name + docstring keyword
```

Without llm-tldr installed, you still get file-level entities:

```bash
rmx ingest . --source tree --semantic   # files + Python ast (imports + docstrings)
```

## The query surface

### DSL (infix set algebra)

```bash
rmx query "mentions:parser AND defines:parser"
rmx query "calls:foo OR (mentions:bar AND NOT imports:legacy)"
rmx query "parser"                                     # bare: union over all linkages
rmx query "defines:auth AND NOT mentions:auth" --ids-only
```

Operators: `AND` / `&&`, `OR` / `||`, `NOT` / `!`, parentheses for grouping.
A term is `linkage:concept` (or just `concept` to mean "any linkage to that concept").

### PQL (Pilosa-style functions)

```bash
rmx query --pql "Row(defines, parser)"
rmx query --pql "Intersect(Row(calls, foo), Row(mentions, bar))"
rmx query --pql "Union(Row(defines, parser), Row(related_to, parser))"
rmx query --pql "Difference(Row(calls, x), Row(defines, x))"   # ghost callers
rmx query --pql "TopN(Row(defines, parser), 5)"
rmx query --pql "Count(Row(defines, parser))"
```

Functions: `Row`, `Intersect` / `And`, `Union` / `Or`, `Difference` / `Diff`,
`Xor`, `TopN`, `Neighbors`, `Count`.

### Higher-level helpers

```bash
rmx neighbors parser --depth 2 --limit 50
rmx co-occur parser --type mentions
rmx top parser --type mentions -k 10                   # weighted top-N
rmx context parser                                     # token-budgeted bundle
rmx context parser --format json                       # LLM-ready
rmx context parser -l defines -l calls --max-tokens 800
rmx context --since main                               # branch-scoped: every concept
                                                       # touched by files changed
                                                       # since `main`
rmx query "defines:auth" --explain                     # show file:line evidence for
                                                       # every result's memberships
```

Output of `rmx context parser`:

```
=== context for `parser` ===
anchor: parser  [concept]

DEFINED BY (defines):
  src/foo.py  [code]
    @core/foo: dispatch + parse

CALLED BY (called_by):
  src/bar.py  [code]
    caller of parser

CALLS (calls):
  src/lex.py  [code]
    tokenizer impl

MENTIONED IN (mentions):
  README.md  [doc]
    high-level overview of the parser pipeline

[~55 tokens, 4 neighbors]
```

### Saved queries

```bash
rmx save-query doc-gap "defines:auth AND NOT mentions:auth"
rmx run doc-gap
rmx list-queries
```

## Power examples

These are the queries that justify the bitmap layer — single-shot answers to
questions that are awkward with `grep`.

```bash
# 1. Documentation gap: code implements `auth` but no doc mentions it.
rmx query "defines:auth AND NOT mentions:auth"

# 2. Ghost API: anything called somewhere but never defined.
rmx query "calls:parse AND NOT defines:parse"

# 3. Cross-cutting code: modules tied to two subsystems.
rmx query "(defines:auth OR calls:auth) AND (defines:billing OR calls:billing)"

# 4. Refactor blast radius: 2-hop transitive closure of a symbol.
rmx neighbors parse --depth 2

# 5. The killer single-shot bundle for an LLM.
rmx context parse --format json --max-tokens 1500
```

The reason these compose is that every linkage lives in the same algebra.
Add `rmx add-linkage-type implements` and `implements:foo AND tested_by:foo`
becomes a one-liner immediately.

## Concept namespacing

Auto-generated concepts are stored under namespaces so they don't collide
with the ones you add by hand:

| Namespace | Source | Example |
|---|---|---|
| `keyword/` | docstring keywords (semantic ingest) | `keyword/tokenizer` |
| `import/` | Python `import` statements | `import/json`, `import/tree_sitter` |
| (none) | function-name concepts (from `tldr-warm`) and your own `add-concept` | `parse`, `register_graph_object` |

Query a namespaced concept with the slash in the term:

```bash
rmx query "imports:import/json"
rmx query "mentions:keyword/parser"
```

Bare-token user concepts (`parser`) and namespaced auto concepts
(`keyword/parser`) are independent. The DSL already accepts `/` inside concept
refs, so no quoting is needed.

## Primer & prompt-aware context

Two LLM-orientation features that use the index proactively:

```bash
# Static — emit a density-ranked top-N symbol map for `@`-include in CLAUDE.md.
rmx primer --top 150 --max-tokens 2000 --out .refmatrix/PRIMER.md

# Dynamic — read a prompt, find concepts mentioned in it, emit context bundles.
echo '{"prompt": "fix register_graph_object handler"}' | rmx scan-prompt
```

`primer` filters to identifier-shaped names (snake_case, dotted.path,
camelCase, or any namespaced `<ns>/<name>`) and skips the `keyword/`
namespace by default. `scan-prompt` does suffix matching, so a prompt
mentioning bare `tree_sitter` matches the indexed `import/tree_sitter`.

The Claude Code hooks installed by `rmx install-hooks --apply` wire
`primer` to `SessionStart` and `scan-prompt` to `UserPromptSubmit`
automatically.

## Maintenance

```bash
rmx stats                                  # cardinalities per linkage
rmx stats --stale                          # tracked files where on-disk mtime
                                           # > last_synced (drift detector)
rmx queue                                  # pending paths waiting to flush
cat .refmatrix/sync.log                    # append-only log of every sync run

rmx vacuum                                 # drop empty-bitmap concepts and
                                           # missing-file tracked rows

rmx prune-noise                            # MARK concepts in `keyword/` with
                                           # df<2 or df/total>0.25 as noise
                                           # (non-destructive — queries hide them
                                           # by default; --full reveals them)
rmx prune-noise --max-df-ratio 0.10        # tighter — marks "get", "name", etc.
rmx prune-noise -n keyword -n import       # also mark obscure imports
rmx prune-noise --drop                     # actually DELETE marked concepts
                                           # (irrecoverable — use with care)

# query both views:
rmx query "mentions:foo"                   # cleaned graph (default)
rmx query "mentions:foo" --full            # raw — find/grep parity
```

## Custom linkage types

```bash
rmx add-linkage-type implements --description "code implements concept"
rmx add-linkage-type tested_by  --description "concept covered by entity (test)"
rmx link parser src/foo.py --type implements
rmx query "implements:parser AND NOT tested_by:parser"
```

## Incremental sync

`rmx sync` is the freshness primitive that hooks call into:

```bash
rmx sync -f path/to/changed.py            # one or more specific files
rmx sync --since HEAD~1                   # everything changed since a git ref
rmx sync --flush-queue                    # drain .refmatrix/dirty.queue
rmx sync --invalidate path/to/gone.py     # force-purge regardless of existence
rmx sync --enqueue-only -f path/...       # cheap append for fast hooks
rmx queue                                 # see what's pending
```

Every sync purges-then-re-adds each touched path, so stale per-function
entities and semantic linkages don't leak across edits.

## Hooks: keep the index fresh

```bash
rmx install-hooks                         # dry-run — prints the plan
rmx install-hooks --apply                 # actually write
rmx install-hooks --apply --force         # overwrite existing hook files
rmx install-hooks --no-briefing           # skip .refmatrix/CLAUDE.md
```

What gets written:

| Target | Purpose |
|---|---|
| `.git/hooks/post-commit` | `rmx sync --since HEAD~1` after each commit |
| `.git/hooks/post-merge` | sync since `ORIG_HEAD` |
| `.git/hooks/post-checkout` | sync the diff on branch switch |
| `.git/hooks/post-rewrite` | sync after rebase/amend |
| `.claude/settings.local.json` | `PostToolUse` enqueue · `Stop`/`SubagentStop` flush · `SessionStart` flush + regen `PRIMER.md` · `UserPromptSubmit` runs `rmx scan-prompt` |
| `.refmatrix/CLAUDE.md` | briefing so Claude knows rmx exists and how to use it |
| `.refmatrix/PRIMER.md` | density-ranked symbol map, refreshed on `SessionStart` (suggested `@`-include) |

After installing, add these lines to your project's `CLAUDE.md` (or create one):

```
@.refmatrix/CLAUDE.md
@.refmatrix/PRIMER.md
```

Now every Claude session in this project loads the briefing and a refreshed
top-symbols map automatically. Symbols you mention in a prompt also get
context bundles injected on the fly via the `UserPromptSubmit` hook.

## Watch mode (editor-driven freshness)

For flows outside Claude or git — e.g. another tool rewriting code — there's
a watcher daemon:

```bash
pip install 'refmatrix[watch]'
rmx watch . --semantic --debounce 500     # blocks until Ctrl-C
```

Coalesces fs events for `--debounce` ms, then batch-syncs. Ignores `.git`,
`.venv`, `node_modules`, `__pycache__`, `.tldr`, `.refmatrix`, etc.

## Storage layout

```
.refmatrix/
├── catalog.db                # SQLite: entities, concepts, linkage_types, entity_links, tracked_files, saved_queries
├── bitmaps/
│   ├── defines/<concept_id>.rb        # roaring bitmap, one file per concept row per linkage
│   ├── calls/<concept_id>.rb
│   └── …
├── queries/                  # saved query bodies (also in catalog)
├── dirty.queue               # populated by hooks, drained by `rmx sync --flush-queue`
└── CLAUDE.md                 # briefing for Claude (written by install-hooks)
```

The forward index (`entity_links`) tracks every `(entity, linkage, concept)`
membership in SQL so deletes are O(links) instead of needing a scan over
every bitmap.

## Concept model

| Term | What it is |
|---|---|
| **Entity** | A column. `kind ∈ {doc, code, concept}`. Concepts are themselves entities, so concepts can link to concepts. |
| **Concept** | A row label. Identified by name, gets a stable id. |
| **Linkage type** | A named relation; the field axis. Directed by default; `--undirected` for symmetric ones like `related_to`. |
| **Bitmap** | A roaring set of entity ids. Persisted as `<linkage>/<concept_id>.rb`. |
| **Weight** | Optional float on `(entity, linkage, concept)` — used by `rmx top` and the weighted ranking inside `rmx context`. |

## Architecture

```
   ┌──────────────────────────────────────────────────────────────┐
   │  CLI  (click + rich)                                         │
   │   init  add-* link sync ingest tldr-warm install-hooks       │
   │   query (DSL+PQL) neighbors co-occur top context             │
   └────────────────────────┬─────────────────────────────────────┘
                            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  Query engine  (refmatrix.query, refmatrix.context)          │
   │   DSL parser  •  PQL evaluator  •  graph walks  •  topN      │
   └────────────────────────┬─────────────────────────────────────┘
                            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  Store  (refmatrix.store)                                    │
   │   SQLite catalog  +  on-disk roaring bitmaps                 │
   │   forward index for O(links) deletes                         │
   └──────────────────────────────────────────────────────────────┘
              ▲                            ▲
              │                            │
   ┌──────────┴──────────┐        ┌────────┴────────┐
   │  ingest             │        │  sync           │
   │  • tldr cache       │        │  files / since  │
   │  • file tree        │        │  / queue / inv. │
   │  • ast (Py)         │        └─────────────────┘
   └─────────────────────┘                 ▲
                                           │
                                ┌──────────┴──────────┐
                                │ hooks: git + Claude │
                                │ + watchdog watcher  │
                                └─────────────────────┘
```

## Relationship to llm-tldr

refmatrix consumes [llm-tldr](https://github.com/parcadei/llm-tldr) output —
tldr is the extractor, refmatrix is the indexer/query layer. They compose;
neither is bundled inside the other.

Source priority (auto):
1. `.tldr/cache/semantic/metadata.json` — per-unit semantic dump with
   `signature`, `unit_type` (function/class/method/...), per-unit
   `calls`/`called_by`, `dependencies`, CFG/DFG summaries. Yields a
   `kind/<unit_type>` namespace queryable as `is_a:kind/class`.
2. `.tldr/cache/call_graph.json` — leaner: just `(from_file, from_func) →
   (to_file, to_func)` edges.
3. `tree` — last-resort directory walk; per-file entities only.

Force a source explicitly: `rmx ingest . --source metadata|tldr|tree`.
Run `rmx tldr-warm <path>` to extract + ingest in one shot.

## Development

```bash
source .venv/bin/activate
env -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 pytest tests/ -q
```

37 tests, ~3 seconds.

## License

MIT.
