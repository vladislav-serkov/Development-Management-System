import type { GapItem, GapsResponse } from "@/types/api"
import { apiFetch } from "./client"

function base(project: string, feature: string) {
  return `/projects/${encodeURIComponent(project)}/features/${encodeURIComponent(feature.replaceAll("/", "__"))}/gaps`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === "string" ? body.detail : `Ошибка запроса: ${response.status}`)
  }
  return response.json()
}

export function fetchGaps(project: string, feature: string) {
  return request<GapsResponse>(`${base(project, feature)}/`)
}

export function runGapsAnalysis(project: string, feature: string) {
  return request<{ status: string }>(`${base(project, feature)}/run`, { method: "POST" })
}

export function cancelGapsAnalysis(project: string, feature: string) {
  return request<{ status: string }>(`${base(project, feature)}/cancel`, { method: "POST" })
}

export function patchGap(project: string, feature: string, id: string, patch: { status: "approved" | "rejected"; analyst_text?: string | null }) {
  return request<{ gaps: GapItem[] }>(`${base(project, feature)}/items/${encodeURIComponent(id)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
  })
}
