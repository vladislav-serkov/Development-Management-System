import { useMutation, useQuery } from "@tanstack/react-query"
import { fetchTestWireMockStatus, uploadMock } from "@/api/test-wiremock"

export function useTestWireMockStatus() {
  return useQuery({
    queryKey: ["test-wiremock"],
    queryFn: fetchTestWireMockStatus,
    staleTime: Infinity,
  })
}

export function useUploadMock() {
  return useMutation({ mutationFn: uploadMock })
}
