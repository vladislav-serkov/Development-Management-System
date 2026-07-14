const WEB_API_PREFIX = "/api"

function apiUrl(path: string): string {
  return path.startsWith("/") ? `${WEB_API_PREFIX}${path}` : `${WEB_API_PREFIX}/${path}`
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init)
}
