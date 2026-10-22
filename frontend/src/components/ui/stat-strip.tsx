import { cn } from "@/lib/utils"

export type StatTone = "default" | "success" | "danger" | "warning"

export interface StatItem {
  value: string | number
  label: string
  tone?: StatTone
  title?: string
}

const toneClasses: Record<StatTone, string> = {
  default: "",
  success: "text-emerald-700 dark:text-emerald-400",
  danger: "text-red-700 dark:text-red-400",
  warning: "text-amber-700 dark:text-amber-400",
}

/** One compact row of numbers — the single way the app shows counters. */
export function StatStrip({ items, className }: { items: StatItem[]; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-5 gap-y-1", className)}>
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline gap-1.5" title={item.title}>
          <span className={cn("text-lg font-semibold leading-6 tabular-nums", toneClasses[item.tone ?? "default"])}>
            {item.value}
          </span>
          <span className="text-xs text-muted-foreground">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
