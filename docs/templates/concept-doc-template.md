---
gmd: "0.1"
id: concept-doc-template
title: "Concept Doc Template"
tags: [template, concept-doc]
---

# PrimaryConcept — One-Line Tagline {#root}

rel: related-to -> [[agent-doc-primer#root]]

Filename should be `primary-concept.md` (kebab-case of the H1
concept). Place under `docs/.../concepts/` so rmx detects it as a
concept doc.

One paragraph defining PrimaryConcept canonically. This is the
authoritative definition; other docs should reference, not redefine.

## Some narrative section {#some-narrative-section}

H2 sections are prose — not indexed as concepts. Use them to group
related H3s, give context, or provide examples.

### SubConceptA {#subconcepta}

Each H3 with a single CamelCase title becomes a sub-concept. rmx
emits `defines:SubConceptA → this-doc::SubConceptA`. Authoritative
definition of SubConceptA goes in this paragraph.

### SubConceptB {#subconceptb}

A SubConceptB **subclasses** SubConceptA, adding [extra behavior].
The word `subclasses` (or `extends`) in this H3's body, followed by
a CamelCase parent, declares inheritance. rmx emits
`is_a:SubConceptA → this-doc::SubConceptB`.

### SubConceptC {#subconceptc}

A SubConceptC subclasses SubConceptB.

## How to use this template {#how-to-use-this-template}

1. Save as `docs/<area>/concepts/<concept>.md`. The `concepts/`
   directory in the path is what triggers concept-doc extraction.
2. H1 = the doc's primary concept. Filename must match (kebab-case
   of the H1).
3. Use H3 sections for sub-concepts. One CamelCase concept per H3
   title. Multi-word H3s are treated as section headings, not
   concept definitions.
4. Declare inheritance with the words `subclasses` or `extends`
   followed by a CamelCase parent. Other phrasings ("is a kind of",
   "specializes") are not recognized.
5. Reference other concepts by their canonical name — exact case,
   no plural, no qualifiers.
6. Run `rmx ingest .` and verify:
   ```bash
   rmx context PrimaryConcept     # should return this doc
   rmx context SubConceptA        # should return this doc + sub-entity
   rmx neighbors docs/.../concepts/<concept>.md
   ```

For the full agent-authoring primer: [[agent-doc-primer#root]].
