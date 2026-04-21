import { isDesktop } from "@/lib/platform"

async function tauriInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isDesktop()) {
    throw new Error(`Tauri command "${command}" called in web mode`)
  }
  const { invoke } = await import("@tauri-apps/api/core")
  return invoke<T>(command, args)
}

export function hasApiKey(): Promise<boolean> {
  return tauriInvoke<boolean>("has_api_key")
}

export function saveApiKey(key: string): Promise<void> {
  return tauriInvoke<void>("save_api_key", { key })
}

export function deleteApiKey(): Promise<void> {
  return tauriInvoke<void>("delete_api_key")
}

export function startBackend(): Promise<void> {
  return tauriInvoke<void>("start_backend")
}

export function getBackendPort(): Promise<number | null> {
  return tauriInvoke<number | null>("get_backend_port")
}

export function spawnShell(cols: number, rows: number): Promise<void> {
  return tauriInvoke<void>("spawn_shell", { cols, rows })
}

export function writeToShell(data: string): Promise<void> {
  return tauriInvoke<void>("write_to_shell", { data })
}

export function resizeShell(cols: number, rows: number): Promise<void> {
  return tauriInvoke<void>("resize_shell", { cols, rows })
}

export function killShell(): Promise<void> {
  return tauriInvoke<void>("kill_shell")
}
