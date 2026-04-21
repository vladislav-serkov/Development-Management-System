import type { ReactNode } from "react"
import { Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DependencyStatus, FeatureStatus } from "@/types/api"

export function SidebarMetric({ label, value, helper }: { label: string; value: number; helper: string }) {
  return (
    <div className="rounded-xl border bg-background px-3 py-2">
      <p className="text-[0.6875rem] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      <p className="text-[0.6875rem] text-muted-foreground">{helper}</p>
    </div>
  )
}

const featureStatusLabels: Record<FeatureStatus, string> = {
  done: "Готово",
  extracting: "Извлечение",
}

export function FeatureStatusDot({ status }: { status: FeatureStatus }) {
  const colors: Record<FeatureStatus, string> = {
    done: "bg-green-500",
    extracting: "bg-amber-400",
  }

  return (
    <span
      className={cn("mt-1 inline-block h-2 w-2 shrink-0 rounded-full", colors[status] ?? "bg-muted-foreground/40")}
      aria-label={featureStatusLabels[status] ?? status}
      title={featureStatusLabels[status] ?? status}
    />
  )
}

const depStatusLabels: Record<DependencyStatus, string> = {
  enriched: "Обогащено",
  stub: "Заглушка",
  error: "Ошибка",
  running: "Обогащение",
}

export function DepStatusDot({ status }: { status: DependencyStatus }) {
  const colors: Record<DependencyStatus, string> = {
    enriched: "bg-green-500",
    stub: "bg-muted-foreground/40",
    error: "bg-destructive",
    running: "bg-amber-400",
  }

  return (
    <span
      className={cn("inline-block h-2 w-2 shrink-0 rounded-full", colors[status] ?? "bg-muted-foreground/40")}
      aria-label={depStatusLabels[status] ?? status}
      title={depStatusLabels[status] ?? status}
    />
  )
}

export function FeatureTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors",
        active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
      )}
    >
      {children}
    </button>
  )
}

export function SidebarTrashButton({ onDelete }: { onDelete: () => void }) {
  return (
    <button
      className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
      title="Удалить"
      onClick={(e) => {
        e.stopPropagation()
        onDelete()
      }}
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  )
}

export function getFeatureSidebarMeta(featureName: string) {
  // Support both "." and "/" as separators
  const separator = featureName.includes("/") ? "/" : "."
  const [context, ...rest] = featureName.split(separator)

  if (rest.length === 0) {
    return { primary: featureName, secondary: null as string | null }
  }

  return {
    primary: rest.join(separator),
    secondary: context,
  }
}
