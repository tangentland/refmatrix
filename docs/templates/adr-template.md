---
gmd: "0.1"
id: adr-template
title: "ADR Template"
tags: [template, adr]
---

# ADR-NNNN: Short Title (one decision per ADR) {#root}

rel: related-to -> [[adr-format]]
rel: related-to -> [[agent-doc-primer#root]]

Status: Proposed
Date: YYYY-MM-DD
Authors: name1, name2
Governs: PrimaryConcept, OtherConcept, ThirdConcept
Cross-references: ADR-NNNN, ADR-MMMM

## Context {#context}

What problem are we deciding? What forces are in play? Keep this to
2-4 paragraphs. Link the prior work that brought this question forward.

## Decision {#decision}

State the decision in one or two sentences, then specify the concrete
shape of the thing being decided. Use fenced code blocks for class /
interface specs so rmx can index them:

```
PrimaryConcept:
    field_one: string
    field_two: list[OtherConcept]
    field_three: int64
    do_thing(arg: OtherConcept) -> ThirdConcept
```

For subclass hierarchies, use one of these forms:

```
PrimaryConcept(BaseConcept):
    extra_field: bool
```

Or tree notation:

```
PrimaryConcept (base)
  +-- ChildA(PrimaryConcept)
  +-- ChildB(PrimaryConcept)
  +-- GrandChild(ChildA, ChildB)
```

## Consequences {#consequences}

What does this commit us to? What are the trade-offs? What follow-up
ADRs or work does this enable or block?

- **Positive:** what gets easier or possible.
- **Negative:** what gets harder or constrained.
- **Neutral:** trade-offs that aren't strictly wins or losses.

## Alternatives considered {#alternatives-considered}

Briefly note the major alternatives and why they were not chosen.
This is the most important section for future readers — *why not*
is often more useful than *why*.

1. **Alternative A** — rejected because ...
2. **Alternative B** — rejected because ...

## References {#references}

Optional. Links to prior discussions, related ADRs, external prior
art. Use `ADR-NNNN` form for ADR refs so they index as `related_to`.

---

# How to use this template {#how-to-use-this-template}

1. Copy to `docs/architecture/adr/NNNN-kebab-title.md` (zero-padded number).
2. Fill in `Status` (Proposed → Accepted when ratified; Superseded
   when retired — rmx zeros linkages on Superseded).
3. List every authoritative concept in `Governs:` as CamelCase tokens.
4. Reference related ADRs as `ADR-NNNN` (exact form) in prose or in
   the `Cross-references:` header line.
5. Put concrete specs in fenced code blocks. Loose prose specs are
   not extracted.
6. Run `rmx ingest .` and verify with:
   ```bash
   rmx neighbors docs/architecture/adr/NNNN-...
   rmx context PrimaryConcept     # should include this ADR
   ```

For full extractor reference: [[adr-format]].
For authoring conventions across all doc forms: [[agent-doc-primer#root]].
