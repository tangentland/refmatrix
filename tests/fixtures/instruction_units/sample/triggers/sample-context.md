---
gmd: "0.1"
id: sample-context
title: "Sample context inject with a declared fallback: a migration edit"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: inject
  bind:
    - event: PreToolUse
      tool: Edit
      match:
        file_path: 'migrations/[^/]+[.]sql$'
      prefilter: 'migrations/'
      mode: context
      fallback: post
  priority: 30
  census: [R903]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/migrations/0007_add.sql", old_string: "a", new_string: "b"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/migrations/README.md", old_string: "a", new_string: "b"}
---

# Sample context inject {#root}

SAMPLE-CONTEXT-TEXT: a migration is append-only; add a new file, never edit a shipped one.
