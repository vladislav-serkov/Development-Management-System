declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown
  }
}

export function isDesktop(): boolean {
  return typeof window !== "undefined" && window.__TAURI_INTERNALS__ !== undefined
}

export function isWeb(): boolean {
  return !isDesktop()
}
