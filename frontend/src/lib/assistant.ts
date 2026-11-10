import type { AssistantAttachment, TestCaseItem } from "@/types/api"

/** Current position and name of every case, by stable id. */
export type CaseIndex = Map<string, { number: number; name: string }>

export function buildCaseIndex(cases: TestCaseItem[]): CaseIndex {
  return new Map(cases.map((tc, index) => [tc.id, { number: index + 1, name: tc.name }]))
}

export function attachmentLabel(attachment: AssistantAttachment, cases: CaseIndex): string {
  const found = cases.get(attachment.case_id)
  const ref = found ? `кейс #${found.number}` : "удалённый кейс"
  if (attachment.kind === "sql_error") return `Ошибка SQL · ${ref}`
  if (attachment.kind === "mock_error") return `Ошибка мока · ${ref}`
  if (attachment.kind === "http_result") {
    return `${attachment.status_code ? `HTTP ${attachment.status_code}` : "Ошибка запроса"} · ${ref}`
  }
  return found ? `Кейс #${found.number}` : "Удалённый кейс"
}

/** An attachment that reports a failure (shown in the danger tint). */
export function isErrorAttachment(attachment: AssistantAttachment): boolean {
  if (attachment.kind === "case") return false
  if (attachment.kind !== "http_result") return true
  return !!attachment.error || (attachment.status_code ?? 0) >= 400
}
