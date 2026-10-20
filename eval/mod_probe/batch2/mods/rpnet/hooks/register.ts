import type { Register } from 'claude-code'

const lines: string[] = []
let logPath = ''
let chain: Promise<void> = Promise.resolve()
function log($: any, line: string) {
  lines.push(new Date().toISOString() + ' ' + line)
  chain = chain.then(async () => {
    if (!logPath) logPath = (await $.session.cwd()) + '/probe.log'
    await $.fs.write(logPath, lines.join('\n') + '\n')
  }).catch(() => {})
  return chain
}
const PATHS: Record<string, string> = {
  a: '/tmp/rp5/nonexist.sock',
  b: '/tmp/rp5/dead.sock',
  c: '/tmp/rp5/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.sock',
  d: '/tmp/rp5/hang.sock',
  d2: '/tmp/rp5/hang.sock',
  e: '/tmp/rp5/ok.sock',
}
function shape(err: any): string {
  let props = ''
  try { props = JSON.stringify(err, Object.getOwnPropertyNames(err ?? {})) } catch (x) { props = 'unserializable' }
  return 'typeof=' + typeof err + ' ctor=' + (err?.constructor?.name) + ' name=' + err?.name + ' code=' + err?.code + ' message=' + JSON.stringify(err?.message ?? String(err)) + ' own=' + props
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({ name: 'rp_fetch', description: 'Probe: fetch over a unix socket. case is one of a,b,c,d,d2,e.', inputSchema: { type: 'object', properties: { case: { type: 'string' } }, required: ['case'] }, isDeferred: false })
    await log($, 'session.start')
    return next(e)
  })
  on('tool.call', { tool: 'mcp__rpnet__rp_fetch' }, async ($, e, next) => {
    const c = String((e as any).case)
    const sp = PATHS[c]
    const t0 = Date.now()
    await log($, 'case ' + c + ' start socketPath=' + sp + ' (len ' + sp.length + ')')
    const p = $.http.fetch('http://rmx/probe?case=' + c, { socketPath: sp })
    p.then((r: any) => log($, 'case ' + c + ' LATE-OR-FINAL resolve after ' + (Date.now() - t0) + 'ms status=' + r.status + ' text=' + JSON.stringify(r.text).slice(0, 80)),
           (err: any) => log($, 'case ' + c + ' LATE-OR-FINAL reject after ' + (Date.now() - t0) + 'ms ' + shape(err)))
    let out: string
    if (c === 'd') {
      const winner = await Promise.race([p.then(() => 'FETCH', () => 'FETCH-REJECT'), $.clock.sleep(4000).then(() => 'TIMER')])
      out = 'race winner=' + winner + ' after ' + (Date.now() - t0) + 'ms'
    } else {
      try { const r = await p; out = 'resolved status=' + r.status + ' ok=' + r.ok + ' text=' + JSON.stringify(r.text).slice(0, 80) }
      catch (err: any) { out = 'rejected after ' + (Date.now() - t0) + 'ms ' + shape(err) }
    }
    await log($, 'case ' + c + ' RESULT ' + out)
    return { result: 'case ' + c + ': ' + out }
  }).catch(($, e, next) => { return { result: 'CATCH handler: hook failed kind=' + next.error?.kind + ' ' + JSON.stringify(next.error).slice(0, 300) } })
  on('session.end', async ($, e, next) => { await log($, 'session.end reason=' + e.reason); return next(e) })
}
