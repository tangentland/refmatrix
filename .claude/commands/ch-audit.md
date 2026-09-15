---
name: ch-audit
description: Full security audit of the project or a scoped path via the ch-security-auditor agent
argument-hint: [optional path to scope the audit]
allowed-tools: [Task, Read, Grep, Glob, Bash]
model: inherit
enabled: true
---

# Security Audit

Run a full security audit. Scope: the argument if given, else the whole project (prioritize
auth flows, API surface, data access, secrets handling, and dependency/container config).

## Steps

1. Dispatch `ch-security-auditor` against the scope. It covers: authentication & authorization,
   input validation / injection, secrets management, dependency / supply-chain, transport / TLS,
   access control, container hardening, API protection (rate limiting, endpoint authz), and
   logging/audit.
2. The agent writes its full report to `workflow/review-output/<scope>-security-audit.md` and
   returns a pointer + finding counts by severity.

## Triage {#triage}

- **Critical / High** — must be fixed before deployment. Do not ship with open Critical/High.
- **Medium / Low** — track in `docs/architecture/todo.md`.
- Log findings to `docs/problem_log.md`.

Report a consolidated summary: counts by severity, the report path, and the blocking items.
