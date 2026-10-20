import type { Register } from 'claude-code'

const lines: string[] = []
let logPath = ''
let chain: Promise<void> = Promise.resolve()
const mark = { plugin: 'rp', key: 'mark' } as const

function log($: any, line: string) {
  lines.push(new Date().toISOString() + ' ' + line)
  chain = chain.then(async () => {
    if (!logPath) logPath = (await $.session.cwd()) + '/probe.log'
    await $.fs.write(logPath, lines.join('\n') + '\n')
  }).catch(() => {})
  return chain
}
const aid = (e: any) => (e.agentId ?? 'MAIN')
const appended = new Set<string>()

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({ name: 'rp_set', description: 'Probe: store a value in mod state.', inputSchema: { type: 'object', properties: { v: { type: 'string' } }, required: ['v'] }, isDeferred: false })
    await $.tool.register({ name: 'rp_get', description: 'Probe: read the value in mod state.', inputSchema: { type: 'object', properties: {} }, isDeferred: false })
    await $.tool.register({ name: 'rp_ping', description: 'Probe: ping.', inputSchema: { type: 'object', properties: { n: { type: 'number' } } }, isDeferred: false })
    await $.env.set('RMX_MOD_PROBE', '1')
    const back = await $.env.get('RMX_MOD_PROBE')
    await log($, 'session.start interactive=' + e.isInteractive + ' surface=' + e.surface + ' sid=' + (await $.session.id()) + ' envget=' + back)
    let k = 0
    $.clock.every(3000, () => { k++; $.session.id().then((s: string) => log($, 'tick ' + k + ' sid=' + s)) })
    return next(e)
  })
  on('session.end', async ($, e, next) => {
    await log($, 'session.end reason=' + e.reason + ' e.sessionId=' + e.sessionId + ' $.session.id=' + (await $.session.id()))
    return next(e)
  })
  on('tool.call', { tool: 'mcp__rp__rp_set' }, async ($, e) => {
    const r = await $.state.set(mark, String((e as any).v))
    await log($, 'rp_set agentId=' + aid(e) + ' sid=' + (await $.session.id()) + ' v=' + (e as any).v + ' isSet=' + r.isSet + ' ver=' + r.version)
    return { result: 'set ok version=' + r.version }
  })
  on('tool.call', { tool: 'mcp__rp__rp_get' }, async ($, e) => {
    const r = await $.state.get(mark)
    const sid = await $.session.id()
    await log($, 'rp_get agentId=' + aid(e) + ' sid=' + sid + ' value=' + JSON.stringify(r.value) + ' ver=' + r.version)
    return { result: 'value=' + JSON.stringify(r.value) + ' version=' + r.version + ' sid=' + sid }
  })
  on('tool.call', { tool: 'mcp__rp__rp_ping' }, async ($, e) => {
    await log($, 'rp_ping agentId=' + aid(e) + ' n=' + (e as any).n)
    return { result: 'pong n=' + (e as any).n }
  })
  on('tool.call', async ($, e, next) => {
    await log($, 'tool.call tool=' + e.tool + ' agentId=' + aid(e))
    if (e.agentId && !appended.has(e.agentId)) {
      appended.add(e.agentId)
      try {
        const r = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: 'MOD-SAPPEND: the code word is OSPREY.' }] }, agentId: e.agentId })
        await log($, 'session.append-call to agentId=' + e.agentId + ' result=' + JSON.stringify(r).slice(0, 200))
      } catch (err: any) { await log($, 'session.append-call REJECTED ' + String(err && err.message || err)) }
    }
    return next(e)
  })
  on('agent.offer', async ($, e, next) => { await log($, 'agent.offer agent=' + e.agent + ' source=' + e.source); return next(e) })
  on('agent.spawn', async ($, e, next) => {
    await log($, 'agent.spawn type=' + e.subagentType + ' bg=' + e.background + ' fork=' + e.fork + ' parentAgentId=' + (e.parentAgentId ?? 'MAIN') + ' prompt=' + JSON.stringify(e.prompt).slice(0, 300))
    const r = await next({ ...e, prompt: e.prompt + '\n\nMOD-SPAWN: also call mcp__rp__rp_ping with n=777.' })
    await log($, 'agent.spawn next resolved ' + JSON.stringify(r).slice(0, 200))
    return r
  })
  on('skill.prompt', async ($, e, next) => { await log($, 'skill.prompt skill=' + e.skill + ' len=' + e.text.length); return next(e) })
  on('prompt.section', async ($, e, next) => { await log($, 'prompt.section name=' + e.name + ' len=' + (e.text ?? '').length); return next(e) })
  on('prompt.context', async ($, e, next) => {
    await log($, 'prompt.context blocks=' + JSON.stringify(e.blocks.map((b: any) => b.name)))
    return next({ ...e, blocks: [...e.blocks, { name: 'rpContext', text: 'MOD-CONTEXT: the code word is HERON.' }] })
  })
  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    await log($, 'prompt.compose model=' + e.model + ' sections=' + r.sections.map((s: any) => s.id).join(','))
    return r
  })
  on('turn.start', async ($, e, next) => { await log($, 'turn.start turnId=' + e.turnId + ' text=' + JSON.stringify(e.text).slice(0, 60)); return next(e) })
  on('turn.step', async function* ($, e, next) {
    await log($, 'turn.step agentId=' + aid(e) + ' idx=' + e.index + ' msgs=' + e.messageCount + ' turnId=' + e.turnId)
    return yield* next(e)
  })
  on('turn.complete', async ($, e, next) => { await log($, 'turn.complete agentId=' + aid(e) + ' reason=' + e.reason + ' answer=' + JSON.stringify(e.answer).slice(0, 120)); return next(e) })
  on('session.append', async ($, e, next) => {
    const m: any = e.message
    const txt = (m.content ?? []).filter((b: any) => b.type === 'text').map((b: any) => b.text).join(' ')
    await log($, 'session.append door=' + e.door + ' agentId=' + aid(e) + ' type=' + m.type + ' name=' + (m.name ?? '') + ' role=' + (m.role ?? '') + ' origin=' + JSON.stringify(e.origin).slice(0, 80) + ' text=' + JSON.stringify(txt).slice(0, 100))
    if (e.agentId && e.door === 'prompt' && m.role === 'user') {
      await log($, 'session.append REWRITE subagent prompt row agentId=' + e.agentId)
      return next({ ...e, message: { ...m, content: [...m.content, { type: 'text', text: 'MOD-APPEND: the code word is PELICAN.' }] } })
    }
    return next(e)
  })
}
