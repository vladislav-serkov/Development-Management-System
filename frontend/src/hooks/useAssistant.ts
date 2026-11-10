import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import {
  cancelAssistantTurn,
  deleteAssistantSession,
  fetchAssistantOverview,
  fetchAssistantSession,
  removeQueuedTurn,
  resolveAssistantSuggestion,
  retryAssistantTurn,
  sendAssistantMessage,
  setAssistantChangeState,
} from "@/api/assistant"
import type { AssistantAttachment, AssistantSession } from "@/types/api"

const assistantKey = (projectSlug: string | null, featureName: string | null) =>
  ["projects", projectSlug, "features", featureName, "assistant"] as const

function isActive(session: AssistantSession | undefined): boolean {
  return !!session?.turns.some((turn) => turn.status === "queued" || turn.status === "running")
}

/** The assistant edits cases in the background — refresh everything that shows them. */
function invalidateCases(qc: QueryClient, projectSlug: string, featureName: string) {
  qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
  qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"], exact: true })
}

export function useAssistantOverview(projectSlug: string, featureName: string, enabled: boolean) {
  return useQuery({
    queryKey: assistantKey(projectSlug, featureName),
    queryFn: () => fetchAssistantOverview(projectSlug, featureName),
    enabled,
    // Other testers' sessions on the same feature show up without a reload
    refetchInterval: (query) => (query.state.data?.sessions.some((s) => s.state !== "idle") ? 3000 : 15000),
  })
}

export function useAssistantSession(projectSlug: string, featureName: string, sessionId: string | null) {
  const qc = useQueryClient()
  const key = [...assistantKey(projectSlug, featureName), "sessions", sessionId]
  return useQuery({
    queryKey: key,
    queryFn: async () => {
      const data = await fetchAssistantSession(projectSlug, featureName, sessionId!)
      const previous = qc.getQueryData<AssistantSession>(key)
      const finished = (session: AssistantSession | undefined) =>
        session?.turns.filter((turn) => turn.status === "done").length ?? 0
      // An answer arrived: it may have changed cases and the session title
      if (previous && finished(data) > finished(previous)) {
        invalidateCases(qc, projectSlug, featureName)
        qc.invalidateQueries({ queryKey: assistantKey(projectSlug, featureName), exact: true })
      }
      return data
    },
    enabled: !!sessionId,
    // Answers take a minute or two; the loader must survive navigation, so it follows the server
    refetchInterval: (query) => (isActive(query.state.data) ? 2000 : false),
  })
}

export function useSendAssistantMessage(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (message: { text: string; attachments: AssistantAttachment[]; session_id: string | null }) =>
      sendAssistantMessage(projectSlug, featureName, message),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assistantKey(projectSlug, featureName) })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "tasks"] })
    },
  })
}

/** Cancel / retry / take back a message, undo a change, answer a suggestion. */
export function useAssistantTurnActions(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: assistantKey(projectSlug, featureName) })
  const refreshWithCases = () => {
    refresh()
    invalidateCases(qc, projectSlug, featureName)
  }

  const cancel = useMutation({
    mutationFn: (turnId: string) => cancelAssistantTurn(projectSlug, featureName, turnId),
    onSettled: refresh,
  })
  const retry = useMutation({
    mutationFn: (turnId: string) => retryAssistantTurn(projectSlug, featureName, turnId),
    onSettled: refresh,
  })
  const removeQueued = useMutation({
    mutationFn: (turnId: string) => removeQueuedTurn(projectSlug, featureName, turnId),
    onSettled: refresh,
  })
  const setChangeState = useMutation({
    mutationFn: (args: { turnId: string; changeId: string; action: "revert" | "restore" }) =>
      setAssistantChangeState(projectSlug, featureName, args.turnId, args.changeId, args.action),
    onSettled: refreshWithCases,
  })
  const resolveSuggestion = useMutation({
    mutationFn: (args: { turnId: string; suggestionId: string; accept: boolean }) =>
      resolveAssistantSuggestion(projectSlug, featureName, args.turnId, args.suggestionId, args.accept),
    onSettled: refreshWithCases,
  })
  return { cancel, retry, removeQueued, setChangeState, resolveSuggestion }
}

export function useDeleteAssistantSession(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => deleteAssistantSession(projectSlug, featureName, sessionId),
    onSettled: () => qc.invalidateQueries({ queryKey: assistantKey(projectSlug, featureName) }),
  })
}
