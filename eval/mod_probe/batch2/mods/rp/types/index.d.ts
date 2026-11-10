export type RpMark = string

declare module 'claude-code' {
  interface PluginState {
    rp: { mark: string }
  }
}
