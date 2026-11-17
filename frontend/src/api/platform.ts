import type { CodexLimits, SupportContact } from "@/types/api"
import { apiFetch } from "./client"

export async function fetchSupportContact(): Promise<SupportContact> {
  const res = await apiFetch("/platform/support")
  if (!res.ok) throw new Error(`Fetch support contact failed: ${res.status}`)
  return res.json()
}

export async function fetchCodexLimits(refresh = false): Promise<CodexLimits> {
  const res = await apiFetch(`/platform/codex-limits${refresh ? "?refresh=true" : ""}`)
  if (!res.ok) throw new Error(`Fetch Codex limits failed: ${res.status}`)
  return res.json()
}
