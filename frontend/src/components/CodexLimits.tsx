import { Gauge, RefreshCw } from "lucide-react"
import { useCodexLimits, useRefreshCodexLimits } from "@/hooks/usePlatform"
import { cn } from "@/lib/utils"
import type { CodexLimitBucket, CodexLimitWindow } from "@/types/api"

const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  go: "Go",
  plus: "Plus",
  pro: "Pro",
  prolite: "Pro Lite",
  promax: "Pro Max",
  team: "Team",
  business: "Business",
  enterprise: "Enterprise",
}

function windowLabel(minutes: number | null, kind: CodexLimitWindow["kind"]): string {
  if (minutes === null) return kind === "primary" ? "Короткое окно" : "Длинное окно"
  if (minutes === 10080) return "Неделя"
  if (minutes === 1440) return "Сутки"
  if (minutes % 1440 === 0) return `${minutes / 1440} дн`
  if (minutes % 60 === 0) return `${minutes / 60} ч`
  return `${minutes} мин`
}

function resetLabel(iso: string | null): string | null {
  if (!iso) return null
  const at = new Date(iso)
  const now = new Date()
  const time = at.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
  if (at.toDateString() === now.toDateString()) return `сброс в ${time}`
  const date = at.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
  return `сброс ${date}, ${time}`
}

function tone(percent: number) {
  if (percent >= 90) return { bar: "bg-red-500", text: "text-red-600 dark:text-red-400" }
  if (percent >= 70) return { bar: "bg-amber-500", text: "text-amber-600 dark:text-amber-400" }
  return { bar: "bg-emerald-500", text: "text-foreground" }
}

function WindowRow({ window }: { window: CodexLimitWindow }) {
  const t = tone(window.used_percent)
  const reset = resetLabel(window.resets_at)
  return (
    <div className="space-y-1">
      <div className="flex items-baseline gap-2 text-[0.75rem]">
        <span className="font-medium">{windowLabel(window.window_minutes, window.kind)}</span>
        <span className={cn("tabular-nums font-semibold", t.text)}>{window.used_percent}%</span>
        {reset && <span className="ml-auto truncate text-[0.6875rem] text-muted-foreground">{reset}</span>}
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={window.used_percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={cn("h-full rounded-full transition-[width]", t.bar)} style={{ width: `${window.used_percent}%` }} />
      </div>
    </div>
  )
}

function Bucket({ bucket, titled }: { bucket: CodexLimitBucket; titled: boolean }) {
  return (
    <div className="space-y-1.5">
      {titled && (
        <p className="text-[0.6875rem] font-medium text-muted-foreground">{bucket.name ?? bucket.id ?? "Лимит"}</p>
      )}
      {bucket.windows.map((w) => (
        <WindowRow key={w.kind} window={w} />
      ))}
    </div>
  )
}

/** Usage of the ChatGPT subscription behind every Codex workflow of the platform. */
export function CodexLimits({ className }: { className?: string }) {
  const { data, isLoading } = useCodexLimits()
  const { refresh, pending } = useRefreshCodexLimits()
  const limits = data?.limits ?? []
  const reached = limits.some((b) => b.reached) || data?.usage_allowed === false
  const plan = data?.plan ? (PLAN_LABELS[data.plan] ?? data.plan) : null

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-1.5">
        <Gauge className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[0.75rem] font-semibold">Лимиты Codex</span>
        {plan && <span className="rounded-full border px-1.5 text-[0.625rem] text-muted-foreground">{plan}</span>}
        <button
          type="button"
          className="ml-auto rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          onClick={() => void refresh()}
          disabled={pending}
          title={data?.fetched_at ? `Обновлено ${new Date(data.fetched_at).toLocaleTimeString("ru-RU")}` : "Обновить"}
          aria-label="Обновить лимиты Codex"
        >
          <RefreshCw className={cn("h-3 w-3", pending && "animate-spin")} />
        </button>
      </div>

      {isLoading && <div className="h-10 animate-pulse rounded-md bg-muted" />}
      {data && !data.available && (
        <p className="text-[0.75rem] text-muted-foreground">{data.error ?? "Лимиты недоступны"}</p>
      )}
      {data?.available && (
        <>
          {limits.length === 0 && <p className="text-[0.75rem] text-muted-foreground">Ограничений нет</p>}
          {limits.map((bucket, i) => (
            <Bucket key={bucket.id ?? i} bucket={bucket} titled={limits.length > 1} />
          ))}
          {reached && (
            <p className="text-[0.75rem] font-medium text-red-600 dark:text-red-400">
              Лимит исчерпан — задачи Codex не запустятся до сброса
            </p>
          )}
          {(data.reset_credits ?? 0) > 0 && (
            <p className="text-[0.6875rem] text-muted-foreground">
              Доступно бесплатных сбросов лимита: {data.reset_credits}
            </p>
          )}
        </>
      )}
    </div>
  )
}
