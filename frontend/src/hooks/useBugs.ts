import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchBugs, generateBug, patchBug, deleteBug, exportBugToJira, syncJiraStatuses, fixBug } from "@/api/bugs"

export function useFeatureBugs(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "bugs"],
    queryFn: () => fetchBugs(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
    // A fix run takes minutes — keep polling while Claude Code works on any bug
    refetchInterval: (query) => {
      const bugs = query.state.data?.bugs ?? []
      return bugs.some((b) => b.fix_status === "queued" || b.fix_status === "running") ? 5000 : false
    },
  })
}

export function useGenerateBug(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ tcIndex, analystText }: { tcIndex: number; analystText?: string | null }) =>
      generateBug(projectSlug, featureName, tcIndex, analystText),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function usePatchBug(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      bugIndex,
      status,
      analyst_text,
    }: {
      bugIndex: number
      status: string
      analyst_text?: string | null
    }) => patchBug(projectSlug, featureName, bugIndex, { status, analyst_text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
    },
  })
}

export function useExportBugToJira(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ bugIndex, featureTicket }: { bugIndex: number; featureTicket?: string | null }) =>
      exportBugToJira(projectSlug, featureName, bugIndex, featureTicket),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
    },
  })
}

export function useSyncJiraStatuses(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => syncJiraStatuses(projectSlug, featureName),
    onSuccess: (data) => {
      if (data.synced) {
        qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
      }
    },
  })
}

export function useFixBug(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (bugIndex: number) => fixBug(projectSlug, featureName, bugIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
    },
  })
}

export function useDeleteBug(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (bugIndex: number) => deleteBug(projectSlug, featureName, bugIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "bugs"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}
