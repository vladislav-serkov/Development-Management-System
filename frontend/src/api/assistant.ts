import type { AssistantAttachment, AssistantOverview, AssistantSession, AssistantTurn } from "@/types/api"
import { apiFetch } from "./client"

function base(projectSlug: string, featureName: string): string {
  return `/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}/assistant`
}

async function json<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = typeof body?.detail === "string" ? body.detail : null
    throw new Error(detail || `${fallback}: ${res.status}`)
  }
  return res.json()
}

function post(path: string, body?: unknown): Promise<Response> {
  return apiFetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export async function fetchAssistantOverview(projectSlug: string, featureName: string): Promise<AssistantOverview> {
  return json(await apiFetch(base(projectSlug, featureName)), "Не удалось загрузить ассистента")
}

export async function fetchAssistantSession(
  projectSlug: string,
  featureName: string,
  sessionId: string,
): Promise<AssistantSession> {
  return json(
    await apiFetch(`${base(projectSlug, featureName)}/sessions/${sessionId}`),
    "Не удалось загрузить сессию",
  )
}

export async function deleteAssistantSession(projectSlug: string, featureName: string, sessionId: string) {
  return json<{ status: string }>(
    await apiFetch(`${base(projectSlug, featureName)}/sessions/${sessionId}`, { method: "DELETE" }),
    "Не удалось удалить сессию",
  )
}

export async function sendAssistantMessage(
  projectSlug: string,
  featureName: string,
  message: { text: string; attachments: AssistantAttachment[]; session_id: string | null },
): Promise<AssistantTurn> {
  return json(await post(`${base(projectSlug, featureName)}/messages`, message), "Не удалось отправить сообщение")
}

export async function removeQueuedTurn(projectSlug: string, featureName: string, turnId: string) {
  return json<{ status: string }>(
    await apiFetch(`${base(projectSlug, featureName)}/turns/${turnId}`, { method: "DELETE" }),
    "Не удалось убрать сообщение",
  )
}

export async function cancelAssistantTurn(projectSlug: string, featureName: string, turnId: string) {
  return json<{ status: string }>(
    await post(`${base(projectSlug, featureName)}/turns/${turnId}/cancel`),
    "Не удалось остановить ассистента",
  )
}

export async function retryAssistantTurn(
  projectSlug: string,
  featureName: string,
  turnId: string,
): Promise<AssistantTurn> {
  return json(await post(`${base(projectSlug, featureName)}/turns/${turnId}/retry`), "Не удалось повторить")
}

export async function setAssistantChangeState(
  projectSlug: string,
  featureName: string,
  turnId: string,
  changeId: string,
  action: "revert" | "restore",
): Promise<AssistantTurn> {
  return json(
    await post(`${base(projectSlug, featureName)}/turns/${turnId}/changes/${changeId}/${action}`),
    action === "revert" ? "Не удалось отменить правку" : "Не удалось вернуть правку",
  )
}

export async function resolveAssistantSuggestion(
  projectSlug: string,
  featureName: string,
  turnId: string,
  suggestionId: string,
  accept: boolean,
): Promise<AssistantTurn> {
  return json(
    await post(`${base(projectSlug, featureName)}/turns/${turnId}/suggestions/${suggestionId}`, { accept }),
    "Не удалось сохранить решение",
  )
}
