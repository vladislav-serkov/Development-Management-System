import type { BugsResponse, BugItem } from "@/types/api"
import { apiFetch } from "./client"

export async function fetchBugs(projectSlug: string, featureName: string): Promise<BugsResponse> {
  const res = await apiFetch(`/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/bugs/`)
  if (!res.ok) throw new Error(`Fetch bugs failed: ${res.status}`)
  return res.json()
}

export async function generateBug(
  projectSlug: string,
  featureName: string,
  tcIndex: number,
  analystText?: string | null,
): Promise<{ bugs: BugItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/bugs/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tc_index: tcIndex, analyst_text: analystText ?? null }),
    }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Generate bug failed: ${res.status}`)
  }
  return res.json()
}

export async function patchBug(
  projectSlug: string,
  featureName: string,
  bugIndex: number,
  patch: { status: string; analyst_text?: string | null },
): Promise<{ bugs: BugItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/bugs/${bugIndex}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }
  )
  if (!res.ok) throw new Error(`Bug patch failed: ${res.status}`)
  return res.json()
}

export async function deleteBug(
  projectSlug: string,
  featureName: string,
  bugIndex: number,
): Promise<{ bugs: BugItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/bugs/${bugIndex}`,
    { method: "DELETE" }
  )
  if (!res.ok) throw new Error(`Bug delete failed: ${res.status}`)
  return res.json()
}
