import type { SqlExecuteResponse, TestDbStatus } from "@/types/api"
import { apiFetch } from "./client"

export async function fetchTestDbStatus(): Promise<TestDbStatus> {
  const res = await apiFetch("/test-db/status")
  if (!res.ok) throw new Error(`Fetch test DB status failed: ${res.status}`)
  return res.json()
}

export async function executeSql(sql: string): Promise<SqlExecuteResponse> {
  const res = await apiFetch("/test-db/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `SQL execute failed: ${res.status}`)
  }
  return res.json()
}
