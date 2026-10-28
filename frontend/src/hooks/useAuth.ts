import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchMe, login, logout } from "@/api/auth"

export const ME_KEY = ["auth", "me"]

// Everything except the current-user query: AuthGate stays subscribed to that one
const notMe = { predicate: (q: { queryKey: readonly unknown[] }) => q.queryKey[0] !== ME_KEY[0] }

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: fetchMe,
    staleTime: Infinity,
    retry: false,
  })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) => login(username, password),
    onSuccess: (user) => {
      // Drop anything cached while signed out, then render the app as this user
      qc.removeQueries(notMe)
      qc.setQueryData(ME_KEY, user)
    },
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      qc.setQueryData(ME_KEY, null)
      qc.removeQueries(notMe)
    },
  })
}
