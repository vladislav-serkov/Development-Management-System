import type { GapsResponse, GapItem, StructuredBusinessLogic, ApplyPreviewData } from "@/types/api"
import { apiFetch } from "./client"

export async function fetchGaps(projectSlug: string, featureName: string): Promise<GapsResponse> {
  const res = await apiFetch(`/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/`)
  if (!res.ok) throw new Error(`Fetch gaps failed: ${res.status}`)
  return res.json()
}

export async function runGapsAnalysis(projectSlug: string, featureName: string): Promise<{ status: string }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/run`,
    { method: "POST" }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Run failed: ${res.status}`)
  }
  return res.json()
}

export async function deleteGap(projectSlug: string, featureName: string, gapIndex: number): Promise<{ gaps: GapItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/${gapIndex}`,
    { method: "DELETE" }
  )
  if (!res.ok) throw new Error(`Gap delete failed: ${res.status}`)
  return res.json()
}

export async function patchGap(
  projectSlug: string,
  featureName: string,
  gapIndex: number,
  patch: { status: string; analyst_text?: string | null }
): Promise<GapItem[]> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/${gapIndex}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }
  )
  if (!res.ok) throw new Error(`Gap patch failed: ${res.status}`)
  return res.json()
}

export async function runApplyPreview(
  projectSlug: string,
  featureName: string,
): Promise<{ status: string }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/apply-preview`,
    { method: "POST" }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Apply preview failed: ${res.status}`)
  }
  return res.json()
}

export async function fetchApplyPreview(
  projectSlug: string,
  featureName: string,
): Promise<ApplyPreviewData & { status: string }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/apply-preview`,
  )
  if (!res.ok) return { status: null } as unknown as ApplyPreviewData & { status: string }
  return res.json()
}

export async function applyConfirm(
  projectSlug: string,
  featureName: string,
  proposed: StructuredBusinessLogic,
): Promise<{ status: string }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/gaps/apply-confirm`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ proposed }) }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Apply confirm failed: ${res.status}`)
  }
  return res.json()
}
