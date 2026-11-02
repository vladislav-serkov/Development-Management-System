import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cancelGapsAnalysis, fetchGapContext, fetchGaps, patchGap, runGapsAnalysis, saveGapContext } from "@/api/gaps"
import type { GapContext } from "@/types/api"

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
    mutationFn: ({ id, status, analyst_text }: { id: string; status: string; analyst_text?: string | null }) =>
      patchGap(project, feature, id, { status, analyst_text }),
    onSuccess: refresh,
  })
  return { run, cancel, review }
}

export function useGapContext(project: string) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ["projects", project, "gap-context"], queryFn: () => fetchGapContext(project),
  })
  const save = useMutation({
    mutationFn: (context: GapContext) => saveGapContext(project, context),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", project, "gap-context"] })
      qc.invalidateQueries({ queryKey: ["projects", project, "features"] })
    },
  })
  return { ...query, save }
}
