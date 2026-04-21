import { isDesktop } from "@/lib/platform"
import { useDesktopStore } from "@/stores/desktopStore"

const WEB_API_PREFIX = "/api"

export function getApiBase(): string {
  if (!isDesktop()) return WEB_API_PREFIX
  const port = useDesktopStore.getState().apiPort
  if (!port) {
    throw new Error("Backend port is not yet available — request made before backend-ready event")
  }
  return `http://127.0.0.1:${port}`
}

export function apiUrl(path: string): string {
  const base = getApiBase()
  if (path.startsWith("/")) return `${base}${path}`
  return `${base}/${path}`
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init)
}
