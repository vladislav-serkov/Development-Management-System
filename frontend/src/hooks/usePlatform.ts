import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useState } from "react"
import { fetchCodexLimits, fetchSupportContact } from "@/api/platform"

export function useSupportContact() {
  return useQuery({
    queryKey: ["platform", "support"],
    queryFn: fetchSupportContact,
    staleTime: Infinity,
  })
}

const LIMITS_KEY = ["platform", "codex-limits"]

/** Subscription usage; the backend caches it for a minute, so polling is cheap. */
export function useCodexLimits() {
  return useQuery({
    queryKey: LIMITS_KEY,
    queryFn: () => fetchCodexLimits(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

/** Bypasses the backend cache (it still refuses more than one read per 10 s). */
export function useRefreshCodexLimits() {
  const client = useQueryClient()
  const [pending, setPending] = useState(false)
  const refresh = useCallback(async () => {
    setPending(true)
    try {
      client.setQueryData(LIMITS_KEY, await fetchCodexLimits(true))
    } finally {
      setPending(false)
    }
  }, [client])
  return { refresh, pending }
}
