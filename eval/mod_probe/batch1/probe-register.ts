import type { Register } from 'claude-code'

const LOG = (globalThis as any).PROBE_LOG ?? "/tmp/modprobe/probe.log"  // scratch path redacted; set to any writable file
const lines: string[] = []
async function log($: any, line: string) {
  lines.push(new Date().toISOString() + " " + line)
  await $.fs.write(LOG, lines.join("\n") + "\n")
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: 'probe_ping',
      description: 'Probe tool: returns pong and which agent loop called it.',
      inputSchema: { type: 'object', properties: { n: { type: 'number' } } },
      isDeferred: false,
    })
    await log($, "session.start interactive=" + e.isInteractive)
    return next(e)
  })
  on('tool.call', { tool: 'mcp__probe__probe_ping' }, async ($, e) => {
    await log($, "probe_ping SERVED agentId=" + (e.agentId ?? "MAIN") + " n=" + (e as any).n)
    return { result: "pong agentId=" + (e.agentId ?? "MAIN") }
  })
  on('tool.call', async ($, e, next) => {
    await log($, "tool.call tool=" + e.tool + " agentId=" + (e.agentId ?? "MAIN"))
    return next(e)
  })
  on('prompt.compose', async ($, e, next) => {
    await log($, "prompt.compose model=" + e.model + " hasProbeTool=" + e.tools.includes('mcp__probe__probe_ping') + " ntools=" + e.tools.length)
    return next(e)
  })
}
