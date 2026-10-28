const WEB_API_PREFIX = "/api"

/** Fired when the API rejects a request for lack of a session; AuthGate shows the login screen. */
export const UNAUTHORIZED_EVENT = "auth:unauthorized"

function apiUrl(path: string): string {
  return path.startsWith("/") ? `${WEB_API_PREFIX}${path}` : `${WEB_API_PREFIX}/${path}`
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(apiUrl(path), init)
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }
  return res
}
