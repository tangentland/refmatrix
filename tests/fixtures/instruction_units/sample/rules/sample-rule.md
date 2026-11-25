---
gmd: "0.1"
id: sample-rule
title: "Sample rule: ADR files"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: rule
  bind:
    - event: PreToolUse
      tool: Edit
      match:
        file_path: '/docs/adr/[^/]+[.]md$'
      prefilter: 'docs/adr/'
  priority: 10
  census: [R905]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/docs/adr/0001-x.md", old_string: "a", new_string: "b"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/docs/guide.md", old_string: "a", new_string: "b"}
---

# Sample rule {#root}

SAMPLE-RULE-TEXT: an accepted ADR is amended by a new section with a dated anchor, never
rewritten in place.
