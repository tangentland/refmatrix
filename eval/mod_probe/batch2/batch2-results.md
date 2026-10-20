# Plan-24 mod probes, batch 2 (2026-10-20)

Claude Code 2.1.304, `--model haiku`. Every `-p` run used `--setting-sources project
--strict-mcp-config` so the user's own hooks and the refmatrix MCP server stayed out of it, plus
`--debug-file`. Mods and logs are in `batch2/` next to this file: `mods/` holds the mods and
helper servers, and `logs/<cwd>/` holds `probe.log`, `run.out` and `run.err`. Debug logs are
not copied; the excerpts that matter are below or in `debug-excerpt.log`.

One caveat: every run inherited `CLAUDE_CODE_CHILD_SESSION` from the parent session, so
transcript saving was off. The interactive banner says so. No result below depends on
transcripts.

| # | probe | result |
|---|-------|--------|
| 1 | `$.state` + `$.session.id()` across main → subagent | **PASS**: shared |
| 2 | subagent context routes | **PASS**: 4 routes inject into a subagent; `prompt.section` / `prompt.compose` do not fire for it; `skill.prompt` UNKNOWN (never fired) |
| 3 | background agent | **PASS**: callable, hooks see it, all injections land |
| 4 | settings hook sees `$.env.set` | **PASS**: it runs under `-p` and sees `RMX_MOD_PROBE=1` |
| 5 | `$.http.fetch` over a Unix socket | measured: a `HooksError` with errno text and no `code`; the engine aborts a hung fetch at **30 s** |
| 6 | two `--plugin-dir`s with one name | **first wins**; the second is not loaded, with one stderr line |
| 7 | plugin vs MCP server of the same name | `$.tool.register` **throws**; the plugin's `tool.call` hook **shadows** the MCP tool |
| 8 | interactive mode + `/clear` | **PASS** (driven via screen) |

## 1. `$.state` across loops {#p1}

**Method.** Mod `rp` (`mods/rp-runA-snapshot`) declares `PluginState { rp: { mark: string } }`
in `types/index.d.ts`. The main loop calls `mcp__rp__rp_set v=MAIN-WAS-HERE`. A foreground
general-purpose subagent then calls `mcp__rp__rp_get`. Run `logs/cA`.

**Result: PASS.** The subagent reads the main loop's value and gets the same session id.

```
18:50:12.600Z rp_set agentId=MAIN sid=64f3f96f-af32-4ea1-b479-ca5007beb6b8 v=MAIN-WAS-HERE isSet=true ver=1
18:50:19.644Z rp_get agentId=a4c396546e64ce27e sid=64f3f96f-af32-4ea1-b479-ca5007beb6b8 value="MAIN-WAS-HERE" ver=1
```

The background agent in run `cB` shows the same thing (`value="BG-TEST"`, same sid).

## 2. Subagent context routes {#p2}

**Method.** Same run `cA`. Every listed event is logged. Four injection routes are tried, each
with its own code word:

- **agent.spawn** rewrites `prompt` with `MOD-SPAWN: also call rp_ping n=777`.
- **session.append** rewrites the subagent's `door=prompt` row to add `MOD-APPEND ... PELICAN`.
- **prompt.context** appends a block `rpContext` with `MOD-CONTEXT ... HERON`.
- **$.session.append({agentId})** is called from the `rp_get` handler with `MOD-SAPPEND ... OSPREY`.

This last route was tested in run `cB`, after a fix: in `cA` it sat in the catch-all `tool.call`
hook, and a matcher hook that answers without `next` shadows that hook.

**Which hooks fire, and where:**

| event | fires for main | fires for subagent | evidence |
|---|---|---|---|
| `agent.spawn` | n/a | once per spawn, in the parent | `agent.spawn type=general-purpose bg=false fork=false parentAgentId=MAIN prompt="Call mcp__rp__rp_get ..."`; next resolves `{"model":"claude-haiku-5-5","agentId":"a4c396546e64ce27e"}` |
| `agent.offer` | yes, 5 types × every loop step | yes, in the subagent's steps too | 6 batches of 5, one at 18:50:19.724, inside the subagent |
| `skill.prompt` | **never fired** (0 rows in all runs) | no | UNKNOWN: nothing in these runs triggered it |
| `prompt.section` | once per conversation, 24 sections | **no** | all 24 at 18:50:09.329; none after the spawn |
| `prompt.context` | once per conversation | **does not re-fire**, but its blocks reach the subagent | `session.append door=attachment agentId=a4c396546e64ce27e name=context_sections text="...# rpContext\nMOD-CONTEXT: the code word is HERON."` |
| `prompt.compose` | once per main turn | **no** | 1 row in cA; 2 in cB (the second is the main loop's task-notification turn) |
| `turn.start` | yes | **yes, but without an agentId** (the types say a subagent raises none) | `turn.start turnId=d6a4e807-...` right after `agent.spawn`, the same turnId as the subagent's `turn.step` rows |
| `turn.step` | yes | yes, with `agentId` | `turn.step agentId=a4c396546e64ce27e idx=0 msgs=11` |
| `turn.complete` | yes | yes, with `agentId` | `turn.complete agentId=a4c396546e64ce27e reason=answer` |
| `session.append` | every row | every row, with `agentId` | `door=prompt agentId=a4c396546e64ce27e origin={"kind":"coordinator"}`, then attachments, responses and tool-results |

**Can a mod add context to a subagent's prompt? Yes, by four routes, and all four were confirmed
by what the subagent quoted back.**

1. **`agent.spawn` rewriting `prompt`.** The subagent obeyed the injected line: `rp_ping
   agentId=a4c396546e64ce27e n=777`. Its report quotes `MOD-SPAWN: also call mcp__rp__rp_ping
   with n=777.`
2. **`session.append` rewriting `content` on the subagent's `door=prompt` row.** The subagent
   quoted `MOD-APPEND: the code word is PELICAN.`
3. **`$.session.append({ message, agentId })` while the subagent is running.** It is stored as
   `door=note origin={"kind":"plugin","name":"rp"}` with `isMeta:true`. The subagent quoted
   `MOD-SAPPEND: the code word is OSPREY.` (run cB).
4. **`prompt.context` blocks.** The hook fires once per conversation, and the subagent's
   `context_sections` attachment carries the same blocks. The cB subagent quoted `MOD-CONTEXT:
   the code word is HERON.`; the cA subagent saw the row but did not quote it. A
   `prompt.context` block reaches every subagent, but it is not per-subagent: it is computed
   once.

The main loop never sees routes 1–3. In cA it flagged the subagent's `MOD-SPAWN`/`MOD-APPEND`
lines as unexplained. Expect a parent model to treat injected subagent text with suspicion.

## 3. Background agent {#p3}

**Method.** Run `logs/cB`: the Agent tool with `run_in_background: true`. The subagent calls
`rp_get` and `rp_ping n=5`.

**Result: PASS.** `agent.spawn ... bg=true`. The mod serves the subagent's calls, tagged with its
`agentId`, and all four injection routes land (the report quotes HERON, MOD-SPAWN, PELICAN and
OSPREY, and it called `rp_ping n=777`).

```
18:50:58.477Z agent.spawn type=general-purpose bg=true fork=false parentAgentId=MAIN ...
18:51:00.047Z turn.complete agentId=MAIN reason=answer ...      # main turn ends while bg agent runs
18:51:02.419Z session.append door=note agentId=a3e23341b458ceedd ... text="MOD-SAPPEND: the code word is OSPREY."
18:51:02.420Z rp_get agentId=a3e23341b458ceedd sid=753bb504-... value="BG-TEST" ver=1
18:51:04.670Z rp_ping agentId=a3e23341b458ceedd n=5
18:51:07.461Z turn.complete agentId=a3e23341b458ceedd reason=answer
18:51:07.479Z session.append door=queue agentId=MAIN ... text="<task-notification>..."
```

## 4. A settings hook sees `$.env.set` {#p4}

**Method.** In run `cA`, `session.start` calls `$.env.set('RMX_MOD_PROBE','1')`, whose signature
is `(name: string, value: string | undefined) => Promise<void>`. The probe cwd's
`.claude/settings.json` (`logs/cA/settings.json`) has a PreToolUse hook on Bash that appends
`printenv RMX_MOD_PROBE` to a file. The model then runs `printenv RMX_MOD_PROBE`.

**Result: PASS.** The settings hook runs under `-p` (with `--setting-sources project`) and sees
the variable. So does the Bash tool, and `$.env.get` reads it back.

```
settings-hook.out: 11:50:13 RMX_MOD_PROBE=[1]
Bash tool output:  1
probe.log:         session.start interactive=false surface=null sid=64f3f96f-... envget=1
debug:             session.append door=hook-context ... origin={"kind":"hook","event":"PreToolUse"}
```

## 5. `$.http.fetch` over a Unix socket {#p5}

**Method.** Mod `rpnet` has a tool `rp_fetch {case}`. `mods/servers.py` (run with `python3 -I`)
binds the sockets under `/tmp/rp5/`:

- `dead.sock` is bound and then closed, so the file exists with no listener.
- `hang.sock` accepts and never answers, and logs when the client closes.
- `ok.sock` is a `socketserver.UnixStreamServer` with an `http.server` handler.

Case d races the fetch against `$.clock.sleep(4000)`. Case d2 (run `c5b`) awaits the hung fetch
without a race. Logs are in `logs/c5`, `logs/c5b` and `logs/c5/servers.log`. The servers were
stopped afterwards.

**Rejection shape (identical for a–c and the 30 s abort).** The thrown value is an `Error` with
`name: "HooksError"`, **no `code`**, own keys `message, name, stack, line, column` (`line=0,
column=0`), and this message:

`<plugin>: $.http.fetch(<url>) over <socketPath> failed: <ERRNO>: <ERRNO>: Was there a typo in the url or port?`

| case | time | message tail |
|---|---|---|
| a, no such path (`/tmp/rp5/nonexist.sock`) | 1 ms | `failed: ENOENT: ENOENT: Was there a typo in the url or port?` |
| b, socket file with no server (refused) | 1 ms | `failed: ECONNREFUSED: ECONNREFUSED: Was there a typo in the url or port?` |
| c, a 124-byte path | 2 ms | `failed: ENAMETOOLONG: ENAMETOOLONG: Was there a typo in the url or port?` |
| d, server accepts, never answers, raced against a 4 s timer | 4001 ms | `race winner=TIMER`. The losing fetch keeps running and **rejects at 30003 ms**: `aborted: no complete answer within 30000ms`. The server logs `conn #1 closed by client` at that moment |
| d2, the same server, not raced | 30010 ms | the same `aborted: no complete answer within 30000ms` rejection; the tool call simply took 30 s |
| e, a working server | 3 ms | `status=200 ok=true text="hello from unix http path=/probe?case=e"`; the server saw `Host: rmx` |

**The hook budget does not kill a hung fetch.** The budget clock stops while a `$` call is in
flight (the types' `HookBudget`). d2 waited the full 30 s with no budget failure and no `.catch`
call. The engine's own **30 s fetch timeout** is the only bound: it is fixed, not configurable
through `HttpInit`, and `HttpInit` has no `signal`. A raced-away fetch is not cancelled; it keeps
the connection open until that 30 s abort.

A path of exactly 101 or 104 bytes was not tested. 124 bytes is refused with ENAMETOOLONG
before any connect.

## 6. Two copies of one plugin name {#p6}

**Method.** Run `logs/c6`: `--plugin-dir dupa --plugin-dir dupb`. Both manifests say
`"name": "dup"`. Each copy writes `marker-<copy>.txt` and serves `mcp__dup__which`.

**Result: the first `--plugin-dir` wins.** The second copy's hooks module is not loaded, and the
run still succeeds. Only `marker-a.txt` exists, and the tool answers `answered by copy a`.

```
stderr: dup: hooks module not loaded: another plugin of that name loads first (a managed one, or an earlier source)
debug:  hooks module dup@inline not loaded: another plugin of that name loads first ...
debug:  hooks module dup@inline loaded (worker, environment 1, tier user); events: session.start,tool.call
```

A related finding: `$.tool.register` serves plugin tools as an in-process HTTP MCP server named
after the plugin (`1 tool(s) served at 127.0.0.1:<port>/<secret>/dup`). That is why probe 7
collides.

An installed plugin together with a `--plugin-dir` of the same name was not tested.

## 7. Plugin tool vs MCP tool of the same name {#p7}

**Method.** Run `logs/c7`: plugin `pc` registers tool `t`. `--mcp-config` adds a stdio server
named `pc` (`mods/mcp_pc.py`, about 30 lines of JSON-RPC) with tools `t` and `only_mcp`.

**Result:**

- **`$.tool.register` throws.** The message is `pc: $.tool.register: the session already has an
  MCP server named "pc" in its MCP config; registering would replace it`. The throw skips the
  whole `session.start` hook ("what is below it ran in its place"), so code after the register
  never ran: `plugin-started.txt` was never written.
- **The MCP server's tools stay listed** (`mcp__pc__t` and `mcp__pc__only_mcp`).
- **The plugin's `tool.call` hook still shadows the MCP tool.** A call to `mcp__pc__t` returned
  `answered by PLUGIN pc`, and the MCP server never got a `tools/call` for `t`; its log shows
  only `only_mcp`. A tool the plugin does not hook passes through to the server (`answered by
  MCP SERVER pc tool=only_mcp`).

```
debug: [ERROR] pc: session.start hook skipped: threw pc: $.tool.register: the session already has an MCP server named "pc" in its MCP config; registering would replace it
mcp-server.log: recv {"method":"tools/call","params":{"name":"only_mcp",...}}   # no tools/call for "t"
```

## 8. Interactive parity and `/clear` {#p8}

**Method.** `screen -dmS rp8` ran `claude --model haiku --setting-sources project
--strict-mcp-config --plugin-dir rp`. This screen is version 4.00, so `stuff` and `hardcopy`
need `-p 0`, and the first unwindowed `stuff` was lost. The sequence was: a prompt, `/clear`,
`rp_set v=PRECLEAR`, `/clear`, `rp_get`, `/exit`. Log `logs/c8`.

**Result: PASS on every point.**

- `session.start interactive=true surface=terminal sid=0c02acfd-...`
- `/clear` raises `session.end reason=clear e.sessionId=0c02acfd-...`. **No `session.start`
  follows.** **`$.session.id()` changes** (the next tick reads `sid=62d27609-...`).
- **`$.clock.every` timers survive `/clear`**: the ticks run on with no gap (tick 23 before,
  tick 24 after, with the new sid).
- **`$.state` is wiped by `/clear`**: `rp_set v=PRECLEAR ver=1` in sid 62d27609, then `/clear`,
  then `rp_get value=undefined ver=0` in sid 27b4c1b4.
- `prompt.context` fires again for the new conversation, at its first prompt.
  `prompt.section` (24 sections) re-runs at every prompt here (72 rows over 3 prompts), unlike
  `-p`, where it ran once.
- `/exit` raises `session.end reason=prompt_input_exit`.

```
18:54:20.769Z session.end reason=clear e.sessionId=0c02acfd-... $.session.id=0c02acfd-...
18:54:21.929Z tick 24 sid=62d27609-c809-43ad-9d20-189e95bbe12d
18:54:39.639Z rp_set agentId=MAIN sid=62d27609-... v=PRECLEAR isSet=true ver=1
18:54:55.162Z session.end reason=clear e.sessionId=62d27609-...
18:55:01.963Z rp_get agentId=MAIN sid=27b4c1b4-... value=undefined ver=0
18:55:20.194Z session.end reason=prompt_input_exit
```

## Consequences for plan-24 {#consequences}

1. **The 30 s fetch ceiling breaks 24.5 R3 as written.** R3 sets `deadlineS` default 60 and
   `waitMs = deadline + 2 s`, but the engine aborts every `$.http.fetch` at 30 s. Any verb call
   over about 30 s fails with `aborted: no complete answer within 30000ms`, and the race timer
   never wins. `waitMs` (and the daemon-side deadline) must stay under 30 s. A longer verb has
   to become submit-then-poll. 24.3 d8's long-poll at ≤ 25 s fits.
2. **24.4 R3/R4 (the classifier twin) must parse `message`, not `code`.** The errno appears only
   in the message text (ENOENT / ECONNREFUSED / ENAMETOOLONG), and `name` is always
   `HooksError`. The engine's own 30 s abort is a fifth shape, `aborted: no complete answer
   within 30000ms`, and it means busy. A raced-away fetch is not cancelled, so a race does not
   free the connection.
3. **24.5 R11 / d13 (collision with the `refmatrix` MCP server) needs a change.** With `.mcp.json`
   still naming `refmatrix`, `$.tool.register` THROWS. That skips the whole `session.start` hook
   unless the register is wrapped in `try`. More serious: the mod's
   `tool.call {tool: mcp__refmatrix__X}` handlers would silently take over the MCP server's
   calls. R11 must also make those handlers pass `next(e)` whenever the mod did not register the
   tool.
4. **`/clear` (24.5):** `$.state` resets, no `session.start` fires, the session id changes, and
   timers survive. Read `$.session.id()` per call, never cached from `session.start`. Re-seed
   state lazily, or from `session.end reason=clear` plus a timer.
5. **Subagent context (24.6) is no longer blocked.** `agent.spawn`'s prompt rewrite, a
   `session.append` rewrite on `door=prompt` with an `agentId`, and `$.session.append({agentId})`
   all inject into a subagent, foreground or background. `prompt.context` blocks reach every
   subagent but are computed once. `prompt.compose` and `prompt.section` remain main-only.
   `turn.start` fires for a subagent without an `agentId`, so attribute by `turn.step` or
   `turn.complete` instead.
6. **The state and identity design holds.** `$.state` and `$.session.id()` are shared with
   subagents, foreground and background. `$.env.set` reaches the settings hooks and the Bash
   tool, so the fallback hooks can read a session id the mod exports (G1 and 24.2a).
7. **Dev and deploy (24.7):** two `--plugin-dir`s named `refmatrix` load only the first, with a
   stderr line. An installed copy against a `--plugin-dir` copy is untested.
