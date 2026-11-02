import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cancelGapsAnalysis, fetchGaps, patchGap, runGapsAnalysis } from "@/api/gaps"

export function useFeatureGaps(project: string, feature: string) {
  return useQuery({
    queryKey: ["projects", project, "features", feature, "gaps"],
    queryFn: () => fetchGaps(project, feature),
    refetchInterval: query => query.state.data?.gaps_running ? 2000 : false,
  })
}

export function useGapActions(project: string, feature: string) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["projects", project, "features"] })
    qc.invalidateQueries({ queryKey: ["projects", project, "tasks"] })
  }
  const run = useMutation({ mutationFn: () => runGapsAnalysis(project, feature), onSuccess: refresh })
  const cancel = useMutation({ mutationFn: () => cancelGapsAnalysis(project, feature), onSuccess: refresh })
  const review = useMutation({
    mutationFn: ({ id, status, analyst_text }: { id: string; status: "approved" | "rejected"; analyst_text?: string | null }) =>
      patchGap(project, feature, id, { status, analyst_text }),
    onSuccess: refresh,
  })
  return { run, cancel, review }
}
