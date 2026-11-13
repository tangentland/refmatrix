---
gmd: "0.1"
id: bsd-pattern-handoff-without-sibling-ac
title: "PATTERN: work handed to a sibling task by decision or registry row, with no acceptance criterion in the sibling's spec (4 runs)"
tags: [bsd, pattern, deferral, specs]
metadata:
  node_type: bsd-pattern
  occurrences: 4
  first_seen: 26.1-followup
  last_seen: 1caf3df
---

# PATTERN: hand-off without a sibling AC {#root}

A finding or a known gap is resolved as "26.x handles it", recorded in a decision row, a registry
row, a docstring or a summary flag — and the receiving task's spec never names it. The work then has
an owner on paper and no test anywhere. Fourth sighting at 26.4 r1 (bug-213 and the misfiled-stem
report handed to 26.5); earlier: an implementer's flag with no anchor (26.1 r4), a registry fix
column the follow-up spec dropped (26.1 r3), and a summary handing work to a sibling with no AC
there (26.6 r1). {#shape}

rel: evidence-for -> [[bsd-task-26.4-r1-savestate-mtype-1caf3df#b-1]]

**Rule:** before accepting a deferral to a sibling task, grep the sibling's spec for the item; if it
is absent, add the requirement and an AC there in the same change (as done for 26.5
`#inherit-264-r1`), or do not defer. {#rule}
