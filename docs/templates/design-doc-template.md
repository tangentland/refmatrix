---
gmd: "0.1"
id: design-doc-template
title: "Design Doc Template"
tags: [template, design-doc]
---

# Design Doc Title {#root}

rel: related-to -> [[agent-doc-primer#root]]

**Created:** YYYY-MM-DD
**Authors:** name1, name2
**Status:** Draft | Proposed | Adopted | Superseded
**Source:** docs/architecture/principles.md
**Referenced by:** CLAUDE.md, MEMORY.md
**Companion:** docs/architecture/bedrock.md
**Implements:** ADR-NNNN
**Supersedes:** docs/design/old-version.md

One-paragraph summary of what this design doc covers and what
decisions or proposals it makes. Keep it scannable — readers should
know within ten seconds whether this doc is relevant to them.

## Context {#context}

What is the problem? What constraints are in play? What prior work
brought us here?

## Proposal {#proposal}

What is being proposed? Use prose freely — design docs are less
structured than ADRs.

For concrete artifacts (types, interfaces, schemas), use fenced
code blocks so rmx can index them. These extract as `defines`
linkages at weight 0.5 (lower than ADRs since this isn't a binding
decision):

```
ProposedType:
    field_one: string
    field_two: list[OtherType]
    do_thing(arg: OtherType) -> Result
```

## Implementation sketch {#implementation-sketch}

If applicable, outline how the proposal would be implemented. This
section is prose; it's not extracted semantically.

## Open questions {#open-questions}

- Question 1
- Question 2
- Question 3

## How to use this template {#how-to-use-this-template}

1. Save as `docs/design/<topic>.md`. Location is conventional; the
   bold-labeled metadata in the header is what carries indexing
   signal.
2. Use **bold-labeled** metadata lines in the first 50 non-blank
   lines, before the first `## ` heading. rmx recognizes these
   labels (others are ignored):
   - `**Source:**` — what this design is based on
   - `**Referenced by:**` — what depends on this
   - `**Companion:**` — peer doc
   - `**Implements:** ADR-NNNN` — ADR being implemented
   - `**Supersedes:** path.md` — doc this replaces
   - `**Replaces:**`, `**Depends on:**`, `**Extends:**`, `**See also:**`
3. Values can be comma-separated. Use project-relative paths or
   `ADR-NNNN` form. rmx resolves paths to existing entities; refs
   to non-existent targets are silently skipped.
4. Reference ADRs as literal `ADR-NNNN` in prose for additional
   `related_to` linkages.
5. Run `rmx ingest .` and verify:
   ```bash
   rmx neighbors docs/design/<topic>.md      # should show metadata refs
   ```

For the full agent-authoring primer: [[agent-doc-primer#root]].
