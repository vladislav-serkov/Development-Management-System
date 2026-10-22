import { Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DependencyStatus } from "@/types/api"

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
