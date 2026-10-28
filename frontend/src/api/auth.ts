import { apiFetch } from "./client"

export interface CurrentUser {
  auth_enabled: boolean
  username: string | null
}

/** `null` = login enabled and no valid session. */
export async function fetchMe(): Promise<CurrentUser | null> {
  const res = await apiFetch("/auth/me")
  if (res.status === 401) return null
  if (!res.ok) throw new Error(`Failed to fetch current user: ${res.status}`)
  return res.json()
}

export async function login(username: string, password: string): Promise<CurrentUser> {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Ошибка входа: ${res.status}`)
  }
  return res.json()
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" })
}
