import { useMutation, useQuery } from "@tanstack/react-query"
import { executeHttpRequest, fetchTestStandStatus } from "@/api/test-stand"
import type { HttpExecuteRequest } from "@/types/api"

export function useTestStandStatus(projectSlug: string, featureName: string) {
  return useQuery({
    queryKey: ["test-stand", projectSlug, featureName],
    queryFn: () => fetchTestStandStatus(projectSlug, featureName),
    staleTime: Infinity,
  })
}

export function useExecuteHttpRequest(projectSlug: string, featureName: string) {
  return useMutation({
    mutationFn: (request: HttpExecuteRequest) => executeHttpRequest(projectSlug, featureName, request),
  })
}
