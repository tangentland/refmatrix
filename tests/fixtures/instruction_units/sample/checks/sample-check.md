---
gmd: "0.1"
id: sample-check
title: "Sample check (stateful): a commit while src/ has unstaged changes"
tags: [instruction-unit, sample, task-I1.b1]
unit:
  kind: check
  on: commit
  run: 'git diff --quiet -- src/'
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'git +commit'
      prefilter: 'git commit'
      when:
        git-dirty:
          repo: .
          paths: [src/]
  priority: 20
  census: [R904]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "git commit -m wip"}
        repo:
          files: {README.md: "readme\n", src/app.py: "x = 1\n"}
          commits: 1
          dirty: [src/app.py]
          branch: main
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "git commit -m wip"}
        repo:
          files: {README.md: "readme\n", src/app.py: "x = 1\n"}
          commits: 1
          dirty: []
          branch: main
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "git status"}
        repo:
          files: {README.md: "readme\n", src/app.py: "x = 1\n"}
          commits: 1
          dirty: [src/app.py]
          branch: main
---

# Sample check {#root}

SAMPLE-CHECK-TEXT: src/ has unstaged changes that this commit leaves out.
Run `git add src/` or `git stash -- src/` first.
