---
gmd: "0.1"
id: sample-packaged-deny
title: "Sample packaged deny (s-3: a local unit at its path is refused)"
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
  census: [R908]
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

# Sample packaged deny {#root}

PACKAGED-DENY-TEXT: `rmfoo --all` removes every build directory, the shared cache included.

Instead: `rmfoo build/` (one directory at a time).
