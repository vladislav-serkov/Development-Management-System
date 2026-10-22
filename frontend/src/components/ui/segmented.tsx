import { cn } from "@/lib/utils"

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  count?: number
}

/** Single-choice filter: one bordered row of segments with optional counts. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div className={cn("inline-flex overflow-hidden rounded-lg border", className)} role="radiogroup">
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "border-r px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors last:border-r-0",
              active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            {option.label}
            {option.count !== undefined && <span className="ml-1 tabular-nums opacity-60">{option.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

/** Native select styled to sit next to Segmented in a filter bar. */
export function FilterSelect<T extends string>({
  value,
  onChange,
  options,
  className,
  ariaLabel,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
  className?: string
  ariaLabel?: string
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className={cn("h-7 rounded-lg border bg-background px-2 text-xs outline-none focus-visible:border-ring", className)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
