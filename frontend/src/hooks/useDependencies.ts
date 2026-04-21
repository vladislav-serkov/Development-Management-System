import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchProjectDependencies, enrichDependency, createDependency, patchDependency, deleteDependency } from "@/api/documents"
import type { CreateDependencyRequest, PatchDependencyRequest } from "@/types/api"

export function useProjectDependencies(projectSlug: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "dependencies"],
    queryFn: () => fetchProjectDependencies(projectSlug!),
    enabled: projectSlug !== null,
    // Poll while any dependency has enrichment_status === "running"
    refetchInterval: (query) => {
      const hasRunning = query.state.data?.some(d => d.enrichment_status === "running") ?? false
      return hasRunning ? 2000 : false
    },
  })
}

export function useCreateDependency(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: CreateDependencyRequest) => createDependency(projectSlug, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "dependencies"] })
    },
  })
}

export function usePatchDependency(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ depName, depType, patch }: { depName: string; depType: string; patch: PatchDependencyRequest }) =>
      patchDependency(projectSlug, depName, depType, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "dependencies"] })
    },
  })
}

export function useDeleteDependency(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ depName, depType }: { depName: string; depType: string }) =>
      deleteDependency(projectSlug, depName, depType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "dependencies"] })
      qc.invalidateQueries({ queryKey: ["projects"] })
    },
  })
}

export function useEnrichDependency(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ depType, file, depName }: { depType: string; file: File; depName?: string }) =>
      enrichDependency(projectSlug, depType, file, depName),
    onSuccess: () => {
      // Trigger immediate refetch — polling will pick up "running" status
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "dependencies"] })
    },
  })
}
