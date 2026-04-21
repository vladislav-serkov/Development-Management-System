import type { TaskKind, TaskListResponse, TaskStatus } from "@/types/api"
import { apiFetch } from "./client"

export interface TaskFilters {
  status?: TaskStatus
  kind?: TaskKind
  target_id?: string
}

export async function fetchProjectTasks(
  projectSlug: string,
  filters: TaskFilters = {},
): Promise<TaskListResponse> {
  const params = new URLSearchParams()
  if (filters.status) params.append("status", filters.status)
  if (filters.kind) params.append("kind", filters.kind)
  if (filters.target_id) params.append("target_id", filters.target_id)

  const qs = params.toString()
  const url = `/projects/${encodeURIComponent(projectSlug)}/tasks${qs ? `?${qs}` : ""}`
  const res = await apiFetch(url)
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`)
  return res.json()
}
