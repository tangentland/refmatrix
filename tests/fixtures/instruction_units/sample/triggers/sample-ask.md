---
gmd: "0.1"
id: sample-ask
title: "Sample ask: dropdb"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: ask
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'dropdb +[a-z]'
      prefilter: 'dropdb'
  priority: 60
  census: [R901]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "dropdb scratch"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "createdb scratch"}
---

# Sample ask {#root}

SAMPLE-ASK-TEXT: dropping a database needs the user's go.

Instead: `pg_dump scratch > scratch.sql` first, then ask.
