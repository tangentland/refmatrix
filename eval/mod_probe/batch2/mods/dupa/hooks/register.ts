import type { Register } from 'claude-code'
export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.fs.write((await $.session.cwd()) + '/marker-a.txt', 'copy a loaded ' + new Date().toISOString() + '\n')
    await $.tool.register({ name: 'which', description: 'Probe: says which copy answers.', inputSchema: { type: 'object', properties: {} }, isDeferred: false })
    return next(e)
  })
  on('tool.call', { tool: 'mcp__dup__which' }, async () => ({ result: 'answered by copy a' }))
}
