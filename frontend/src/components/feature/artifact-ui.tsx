import { useState, type ReactNode } from "react"
import { Check, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function TypeBadge({ label, className }: { label: string; className: string }) {
  return (
    <span className={cn("shrink-0 rounded px-1.5 py-0.5 font-mono text-[0.625rem] font-semibold leading-[0.875rem]", className)}>
      {label}
    </span>
  )
}

/** Small outline chip for artifact context (stand, database, key, response code). */
export function MetaChip({ children, mono, title }: { children: ReactNode; mono?: boolean; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex max-w-full items-center truncate rounded-full border px-2 py-px text-[0.6875rem] text-muted-foreground",
        mono && "font-mono",
      )}
    >
      {children}
    </span>
  )
}

/** One header row for every artifact: type badge · target · chips · actions. */
export function ArtifactHead({
  badge,
  target,
  chips,
  actions,
}: {
  badge: ReactNode
  target?: ReactNode
  chips?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {badge}
      {target && <code className="min-w-0 truncate font-mono text-[0.8125rem] text-foreground">{target}</code>}
      {chips}
      {actions && <div className="ml-auto flex shrink-0 items-center gap-1.5">{actions}</div>}
    </div>
  )
}

export function CopyButton({ value, label, className }: { value: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      size={label ? "xs" : "icon-xs"}
      variant="outline"
      className={cn("bg-background text-muted-foreground hover:text-foreground", className)}
      title="Копировать"
      onClick={(e) => {
        e.stopPropagation()
        navigator.clipboard.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? <Check className="text-emerald-600" /> : <Copy />}
      {label}
    </Button>
  )
}

/** The single code surface of the app (same as bug reports): light slate panel, copy in the corner. */
export function CodeBlock({ value, copyValue, className }: { value: string; copyValue?: string | null; className?: string }) {
  return (
    <div className={cn("group relative overflow-hidden rounded-lg bg-[#f0f4f8] dark:bg-slate-900/70", className)}>
      {copyValue !== null && (
        <CopyButton value={copyValue ?? value} className="absolute right-2 top-2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100" />
      )}
      <pre className="max-h-[26rem] overflow-auto whitespace-pre-wrap break-words px-3.5 py-3 font-mono text-[0.75rem] leading-6 text-slate-900 dark:text-slate-100">
        <code>{value}</code>
      </pre>
    </div>
  )
}

/** Text-button sub tabs inside an artifact (Тело / Заголовки / curl). */
export function SubTabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { key: T; label: string }[]
  value: T
  onChange: (key: T) => void
}) {
  if (tabs.length < 2) return null
  return (
    <div className="flex flex-wrap items-center gap-0.5">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            "rounded-md px-2 py-0.5 text-[0.75rem] font-medium transition-colors",
            value === t.key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
