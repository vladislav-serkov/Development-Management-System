import type { HttpExecuteRequest, HttpExecuteResponse, TestStandStatus } from "@/types/api"
import { apiFetch } from "./client"

// Feature names may contain "/" (e.g. "GET /v1/balance") — the API addresses
// them by their path-safe form, same as the test-cases client.
function featurePath(projectSlug: string, featureName: string): string {
  return `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}`
}

export async function fetchTestStandStatus(
  projectSlug: string,
  featureName: string
): Promise<TestStandStatus> {
  const res = await apiFetch(`${featurePath(projectSlug, featureName)}/test-stand`)
  if (!res.ok) throw new Error(`Fetch test stand status failed: ${res.status}`)
  return res.json()
}

export async function executeHttpRequest(
  projectSlug: string,
  featureName: string,
  request: HttpExecuteRequest
): Promise<HttpExecuteResponse> {
  const res = await apiFetch(
    `${featurePath(projectSlug, featureName)}/test-stand/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof body.detail === "string" ? body.detail : `HTTP execute failed: ${res.status}`
    throw new Error(detail)
  }
  return res.json()
}
