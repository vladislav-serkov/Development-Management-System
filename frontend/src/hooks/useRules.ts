import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchGlobalRules, saveGlobalRules, fetchProjectRules, saveProjectRules, type RulesData } from "@/api/rules"

export function useGlobalRules() {
  return useQuery({
    queryKey: ["rules", "global"],
    queryFn: fetchGlobalRules,
  })
}

export function useSaveGlobalRules() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: saveGlobalRules,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules", "global"] }),
  })
}

export function useProjectRules(projectSlug: string | null) {
  return useQuery({
    queryKey: ["rules", "projects", projectSlug],
    queryFn: () => fetchProjectRules(projectSlug!),
    enabled: projectSlug !== null,
  })
}

export function useSaveProjectRules(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rules: RulesData) => saveProjectRules(projectSlug, rules),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules", "projects", projectSlug] }),
  })
}
