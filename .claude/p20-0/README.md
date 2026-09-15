# p20-0 — memory-driven action classifier (guardrail compiler)

> **OPTIONAL / ADVANCED.** This is a self-contained, opt-in mechanism. The template
> works fine without it. Enable it only if you want memory-declared guardrails
> compiled into Claude Code's native auto-mode. It degrades gracefully: the
> SessionStart hook no-ops unless both this directory and `rmx` are present.

## What it is

Guardrail **memories** — small GMD files, each carrying a fenced `guardrail:` block
that declares a `tier` and a prose `rule` — are the source of truth. A compiler
reads them (via `rmx`) and merges their rules into Claude Code's native auto-mode
block at the tier each memory declares. The platform's own auto-mode is the
enforcement engine; there is no bespoke classifier.

**Self-hardening loop:** drop a new guardrail memory into `guardrails/`, re-run the
compiler, and the new rule is enforced — zero new code.

## Files

| File | Role |
|------|------|
| `guardrails/*.md` | Committed **seed** guardrail memories (source of truth). Each is GMD with `metadata.type: guardrail` and a fenced ```yaml guardrail:``` block (`tier`, `rule`, `scope`, `match_kind`, `message`). |
| `compile_guardrails.py` | Compiler. Reads the guardrail memories and writes the auto-mode arrays. Idempotent. |
| `golden_cases.jsonl` | Structural corpus. First line is `_meta`; each other line is one case. |
| `validate.py` | Deterministic oracle over the compiled result. Exit 0 = GREEN, exit 1 = RED. |

## Tier -> array map

| Tier | auto-mode array | Meaning |
|------|-----------------|---------|
| `hard_deny` | `autoMode.hard_deny` | Lane-agnostic BLOCK, any actor |
| `soft_deny` | `autoMode.soft_deny` | Unused by the seed set |
| `allow` | `autoMode.allow` | Read-only recon carve-out |
| `advise` | `autoMode.environment` | Nudge only; never a blocking tier |

## Seed guardrails shipped

| Memory | Tier | Rule concept |
|--------|------|--------------|
| `guardrail-externalize-off-machine` | `hard_deny` | Never publish/send project code, design, or schema off-machine (Artifact tool / web services); local files + on-machine rmx only. |
| `guardrail-revert-uncommitted-work` | `hard_deny` | Never revert/discard uncommitted work (git checkout / reset --hard / stash-drop over a dirty tree) without explicit user confirmation. |
| `guardrail-readonly-recon-allow` | `allow` | Read-only recon (grep/rg, rmx, ls, git status, cat) is always allowed. |

## How the compiler works

1. `rmx memory sync-disk guardrails/` — upsert the on-disk seed memories into rmx
   (idempotent), so a lone run is self-contained.
2. `rmx memory list --type guardrail` — deterministic enumeration (NOT `recall`,
   which is semantic / session-dependent).
3. `rmx memory get <name>` — full body per memory; parse the `tier` + `rule`.
4. Merge into `.claude/settings.local.json -> autoMode.{hard_deny,soft_deny,allow,environment}`,
   preserving the `"$defaults"` sentinel first in every managed array.
5. **Idempotent** via the `[auto:p20-0]` marker: each run strips prior
   marker-tagged entries and re-adds the current set — re-running never duplicates.

## Run

```bash
python3 .claude/p20-0/compile_guardrails.py   # compile seed guardrails -> settings.local.json autoMode
python3 .claude/p20-0/validate.py             # structural oracle; exit 0 = GREEN
```

The SessionStart hook in `.claude/settings.json` recompiles each session when this
directory and `rmx` are both present, so committed guardrails stay in effect.

## Validation is STRUCTURAL

`validate.py` asserts, over the compiled JSON only (it spawns nothing):

- **G1** `autoMode` present and an object.
- **G2** `"$defaults"` preserved in every required array.
- **G3** rules are well-formed (non-empty strings).
- **G4** idempotent — no duplicate rules in any array.
- **Per-case** each golden case's rule prose is present at its expected tier and
  does not leak into a forbidden (blocking) tier.

The `reason_contains` tokens in each corpus case must ALL appear (case-insensitive)
inside a single compiled rule string in the expected tier array — this is the
contract the seed prose must satisfy.

## Known limitation — runtime efficacy is NOT verified here

Whether the installed CLI actually *enforces* `autoMode` rules at runtime is out of
scope. Validation is **structural only**. Two facts bound the gap: (1) the
`claude auto-mode` surface cannot be driven as a config/critique inspector — piping
input spawns a live agentic session with tools, disqualifying it as a check; and
(2) `autoMode` rules are inert unless the session runs in `auto` permission-mode.
