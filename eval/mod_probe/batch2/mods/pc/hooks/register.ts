import type { Register } from 'claude-code'
export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({ name: 't', description: 'Probe: says who answers.', inputSchema: { type: 'object', properties: {} }, isDeferred: false })
    await $.fs.write((await $.session.cwd()) + '/plugin-started.txt', 'plugin pc started\n')
    return next(e)
  })
  on('tool.call', { tool: 'mcp__pc__t' }, async () => ({ result: 'answered by PLUGIN pc' }))
}
