const WEB_API_PREFIX = "/api"

export function getApiBase(): string {
  return WEB_API_PREFIX
}

export function apiUrl(path: string): string {
  const base = getApiBase()
  if (path.startsWith("/")) return `${base}${path}`
  return `${base}/${path}`
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init)
}
