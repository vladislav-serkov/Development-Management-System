import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchTestCases, patchTestCase, deleteTestCase, runTestCases, requestScript } from "@/api/test-cases"

export function useFeatureTestCases(projectSlug: string | null, featureName: string | null) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features", featureName, "test-cases"],
    queryFn: () => fetchTestCases(projectSlug!, featureName!),
    enabled: !!projectSlug && !!featureName,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.test_cases_running) return 2000
      const scriptActive = data?.test_cases.some(
        (tc) => tc.script_status === "queued" || tc.script_status === "running"
      )
      return scriptActive ? 5000 : false
    },
  })
}

export function useRequestScript(projectSlug: string, featureName: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tcIndex: number) => requestScript(projectSlug, featureName, tcIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features", featureName, "test-cases"] })
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
