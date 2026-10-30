import { apiFetch } from "./client"

export interface TestWireMockStatus {
  configured: boolean
  target_url: string | null
}

export interface MockUploadResult {
  mapping_id: string
  target_url: string
  status_code: number
  duration_ms: number
}

export async function fetchTestWireMockStatus(): Promise<TestWireMockStatus> {
  const res = await apiFetch("/test-wiremock/status")
  if (!res.ok) throw new Error(`Не удалось получить настройки WireMock: ${res.status}`)
  return res.json()
}

export async function uploadMock(mockConfig: string): Promise<MockUploadResult> {
  const res = await apiFetch("/test-wiremock/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mock_config: mockConfig }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === "string" ? body.detail : `Не удалось загрузить мок: ${res.status}`)
  }
  return res.json()
}
