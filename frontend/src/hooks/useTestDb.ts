import { useMutation, useQuery } from "@tanstack/react-query"
import { executeSql, fetchTestDbStatus } from "@/api/test-db"

export function useTestDbStatus() {
  return useQuery({
    queryKey: ["test-db", "status"],
    queryFn: fetchTestDbStatus,
    staleTime: Infinity,
  })
}

export function useExecuteSql() {
  return useMutation({
    mutationFn: (sql: string) => executeSql(sql),
  })
}
