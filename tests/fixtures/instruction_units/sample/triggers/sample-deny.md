---
gmd: "0.1"
id: sample-deny
title: "Sample deny: rmfoo --all"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: deny
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'rmfoo +--all'
      unless: '--dry-run'
      prefilter: 'rmfoo'
      who: any
      where: any
  priority: 50
  census: [R900]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "rmfoo --all build/"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "rmfoo --all build/ --dry-run"}
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "ls build/"}
---

# Sample deny {#root}

SAMPLE-DENY-TEXT: `rmfoo --all` removes every build directory, the shared cache included.

Instead: `rmfoo build/` (one directory at a time).
