---
gmd: "0.1"
id: guardrail-revert-uncommitted-work
title: "Guardrail — never revert an agent's uncommitted work (hard_deny)"
tags: [guardrail, hard-deny, git-safety]
metadata:
  node_type: memory
  type: guardrail
  originSessionId: 00000000-0000-0000-0000-000000000000
  created: 2026-07-06
  updated: 2026-07-06
---

# Never revert an agent's uncommitted work {#root}

Lane-agnostic destruction danger: resetting or reverting an agent's un-landed working-tree changes
destroys work that exists nowhere else. This is `hard_deny` for every actor unless the user
explicitly confirms.

Guardrail (compiler-read structured block):

```yaml
guardrail:
  tier: hard_deny
  rule: "Never reset, checkout, restore, or stash-drop an agent's uncommitted working-tree changes without explicit user confirmation: those uncommitted deltas are un-landed work and exist nowhere else."
  scope:
    role: any
  match_kind: prose
  message: "Blocked: reverting uncommitted work. A dispatched agent's uncommitted working-tree deltas are un-landed; do not git checkout/reset --hard/stash-drop them over a dirty tree without explicit user confirmation."
```

**Why:** a dispatched agent's uncommitted deltas are its only copy; a `git reset --hard` /
`checkout` / `restore` / `stash drop` over a dirty tree silently discards them with no one the wiser.
The loss is unrecoverable, so it bars every actor absent explicit user confirmation.

**How to apply:** never run a destructive git command against a working tree that holds uncommitted
changes without confirming with the user first; commit or stash-preserve first, and let the owning
agent land its own work.
