---
gmd: "0.1"
id: sample-gate
title: "Sample gate: shipit --prod, in a store tree, delivers the skill's checklist"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: inject
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'shipit +--prod'
      prefilter: 'shipit'
      where: store
      mode: gate
  from: 'sample-skill#checklist'
  priority: 40
  census: [R902]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "shipit --prod"}
        store: present
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "shipit --prod"}
        store: absent
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "shipit --staging"}
        store: present
---

# Sample gate {#root}
