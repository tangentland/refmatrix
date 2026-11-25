---
gmd: "0.1"
id: sample-packaged-rule
title: "Sample packaged rule: a schema file changes with its migration"
tags: [instruction-unit, packaged-sample, task-I1.b1]
unit:
  kind: rule
  bind:
    - event: PreToolUse
      tool: Edit
      match:
        file_path: '/schema/[^/]+[.]sql$'
      prefilter: 'schema/'
  priority: 10
  census: [R907]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/schema/core.sql", old_string: "a", new_string: "b"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/src/schema.py", old_string: "a", new_string: "b"}
---

# Sample packaged rule {#root}

PACKAGED-RULE-TEXT: a schema file changes only in the commit that adds its migration.
