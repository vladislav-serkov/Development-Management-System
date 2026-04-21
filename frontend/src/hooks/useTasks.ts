import { useQuery } from "@tanstack/react-query"
import { fetchProjectTasks, type TaskFilters } from "@/api/tasks"

export function useProjectTasks(projectSlug: string | null, filters: TaskFilters = {}) {
  return useQuery({
    queryKey: ["projects", projectSlug, "tasks", filters],
    queryFn: () => fetchProjectTasks(projectSlug!, filters),
    enabled: projectSlug !== null,
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? []
      return tasks.some((t) => t.status === "running") ? 2000 : 5000
    },
  })
}
