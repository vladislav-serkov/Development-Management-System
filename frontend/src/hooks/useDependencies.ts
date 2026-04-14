import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchProjectDependencies, enrichDependency, createDependency, patchDependency, deleteDependency } from "@/api/documents"
import { useUIStore } from "@/stores/uiStore"
import type { CreateDependencyRequest, PatchDependencyRequest } from "@/types/api"

export function useProjectDependencies(projectSlug: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "dependencies"],
    queryFn: () => fetchProjectDependencies(projectSlug!),
    enabled: projectSlug !== null,
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
  const startEnriching = useUIStore((s) => s.startEnriching)
  const stopEnriching = useUIStore((s) => s.stopEnriching)
  return useMutation({
    mutationFn: ({ depType, file, depName }: { depType: string; file: File; depName?: string }) =>
      enrichDependency(projectSlug, depType, file, depName),
    onMutate: ({ depType }) => {
      startEnriching(depType)
    },
    onSettled: (_data, _error, { depType }) => {
      stopEnriching(depType)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "dependencies"] })
    },
  })
}
