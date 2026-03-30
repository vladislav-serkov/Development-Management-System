import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchGaps, patchGap, deleteGap, runGapsAnalysis, runApplyPreview, fetchApplyPreview, applyConfirm } from "@/api/gaps"
import type { StructuredBusinessLogic } from "@/types/api"

export function useFeatureGaps(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "gaps"],
    queryFn: () => fetchGaps(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
    refetchInterval: (query) => {
      const status = query.state.data?.gaps_status
      return status === "running" ? 2000 : false
    },
  })
}

export function usePatchGap(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ gapIndex, status, analyst_text }: { gapIndex: number; status: string; analyst_text?: string | null }) =>
      patchGap(projectSlug, featureName, gapIndex, { status, analyst_text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "gaps"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useDeleteGap(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (gapIndex: number) => deleteGap(projectSlug, featureName, gapIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "gaps"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useRunGaps(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runGapsAnalysis(projectSlug, featureName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "gaps"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useRunApplyPreview(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runApplyPreview(projectSlug, featureName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "apply-preview"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useApplyPreviewData(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "apply-preview"],
    queryFn: () => fetchApplyPreview(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "running" ? 2000 : false
    },
  })
}

export function useApplyConfirm(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (proposed: StructuredBusinessLogic) => applyConfirm(projectSlug, featureName, proposed),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "gaps"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "apply-preview"] })
    },
  })
}
