---
gmd: "0.1"
id: planted-pass-fires
title: "Planted: a pass envelope that fires"
tags: [instruction-unit, planted, task-I1.b1]
unit:
  kind: deny
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'rmfoo +--all'
      unless: '--dry-run'
      prefilter: 'rmfoo'
  priority: 50
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
          tool_input: {command: "rmfoo   --all build/"}
---

# Planted: a pass envelope that fires {#root}

Planted: pass[1] is not a near miss: it matches and carries no unless.

Instead: `rmfoo build/`.
