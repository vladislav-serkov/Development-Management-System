import type { TestCasesResponse, TestCaseItem } from "@/types/api"
import { apiFetch } from "./client"

export async function fetchTestCases(projectSlug: string, featureName: string): Promise<TestCasesResponse> {
  const res = await apiFetch(`/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/test-cases/`)
  if (!res.ok) throw new Error(`Fetch test cases failed: ${res.status}`)
  return res.json()
}

export async function runTestCases(projectSlug: string, featureName: string): Promise<{ status: string }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/test-cases/run`,
    { method: "POST" }
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Run failed: ${res.status}`)
  }
  return res.json()
}

export async function deleteTestCase(projectSlug: string, featureName: string, tcIndex: number): Promise<{ test_cases: TestCaseItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/test-cases/${tcIndex}`,
    { method: "DELETE" }
  )
  if (!res.ok) throw new Error(`Test case delete failed: ${res.status}`)
  return res.json()
}

export async function patchTestCase(
  projectSlug: string,
  featureName: string,
  tcIndex: number,
  patch: { status: string; analyst_text?: string | null }
): Promise<{ test_cases: TestCaseItem[] }> {
  const res = await apiFetch(
    `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/test-cases/${tcIndex}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }
  )
  if (!res.ok) throw new Error(`Test case patch failed: ${res.status}`)
  return res.json()
}
