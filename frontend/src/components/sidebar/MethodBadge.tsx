import { cn } from "@/lib/utils"

export function MethodBadge({ method, featureType, large }: { method: string | null; featureType: string; large?: boolean }) {
  const resolved =
    method ??
    (featureType === "kafka_consumer"
      ? "CONSUMER"
      : featureType === "rest_endpoint"
        ? "API"
        : featureType === "scheduled_task"
          ? "SCHED"
          : null)
  if (!resolved) return null

  const colorMap: Record<string, string> = {
    GET: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    POST: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    PUT: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    DELETE: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    PATCH: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    CONSUMER: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    SCHEDULED: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",
    SCHED: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",
    API: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400",
  }

  return (
    <span className={cn("shrink-0 rounded px-1.5 py-0.5 font-mono font-semibold", large ? "text-xs" : "text-[0.625rem]", colorMap[resolved] ?? colorMap.API)}>
      {resolved}
    </span>
  )
}
