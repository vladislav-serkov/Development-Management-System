import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchTestCases, patchTestCase, deleteTestCase, runTestCases } from "@/api/test-cases"

export function useFeatureTestCases(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "test-cases"],
    queryFn: () => fetchTestCases(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
    refetchInterval: (query) => {
      return query.state.data?.test_cases_running ? 2000 : false
    },
  })
}

export function usePatchTestCase(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ tcIndex, status, analyst_text }: { tcIndex: number; status: string; analyst_text?: string | null }) =>
      patchTestCase(projectSlug, featureName, tcIndex, { status, analyst_text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useDeleteTestCase(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tcIndex: number) => deleteTestCase(projectSlug, featureName, tcIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useRunTestCases(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runTestCases(projectSlug, featureName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}
