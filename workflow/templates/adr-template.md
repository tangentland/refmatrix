---
gmd: "0.1"
id: adr-NNNN-kebab-title
title: "ADR-NNNN: <short title — one decision>"
tags: [adr, architecture]
metadata:
  node_type: adr
  status: Proposed        # Proposed → Accepted (ratified) → Superseded (retired)
  date: YYYY-MM-DD
  governs: [PrimaryConcept, OtherConcept]   # CamelCase concepts this ADR authorizes (rmx visibility)
---

# ADR-NNNN: <Short Title> {#root}

One decision per ADR. Emitted by `/ch-crucible` from the feature spec, before `/ch-plan`.
When filled, add a typed edge back to the originating spec, e.g.
`rel: derives-from -> [[NNN-slug-spec]]` (use the spec's real GMD id).

## Context {#context}

What problem are we deciding? What forces are in play (2-4 paragraphs)? Which spec requirement
or `[NEEDS CLARIFICATION]` marker surfaced this decision? Link prior ADRs that bear on it.

## Decision {#decision}

State the decision in one or two sentences, then give the concrete shape. Put class/interface
specs in fenced code blocks so `rmx` indexes them:

```
PrimaryConcept:
    field_one: string
    do_thing(arg: OtherConcept) -> ThirdConcept
```

## Consequences {#consequences}

- **Positive:** what gets easier or possible.
- **Negative:** what gets harder or constrained.
- **Neutral:** trade-offs that aren't strictly wins or losses.

What must `plan.md` honor as a result? What follow-up ADRs does this enable or block?

## Alternatives considered {#alternatives}

The most important section for future readers — *why not* beats *why*.

1. **Alternative A** — rejected because …
2. **Alternative B** — rejected because …

## References {#references}

Related ADRs as `ADR-NNNN` (indexes as related_to). Prior discussions, external prior art.

<!--
How to use:
1. Copy to docs/architecture/adr/NNNN-kebab-title.md (zero-padded); set frontmatter id to match.
2. Fill Status: Proposed → Accepted when ratified; Superseded when retired.
3. List authoritative concepts in metadata.governs as CamelCase tokens.
4. Concrete specs go in fenced code blocks — loose prose specs are not extracted.
5. Validate: python3 tools/gmd/lint.py docs/architecture/adr/NNNN-*.md   (zero errors)
6. If rmx present: rmx ingest . ; rmx context PrimaryConcept  (should include this ADR)
-->
