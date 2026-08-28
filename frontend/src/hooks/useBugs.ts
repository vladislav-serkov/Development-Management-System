import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchBugs, generateBug, patchBug, deleteBug, exportBugToJira, syncJiraStatuses } from "@/api/bugs"

export function useFeatureBugs(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "bugs"],
    queryFn: () => fetchBugs(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
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
