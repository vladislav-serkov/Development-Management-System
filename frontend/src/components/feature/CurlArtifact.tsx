import { useMemo, useState } from "react"
import { Check, ChevronDown, ChevronRight, Copy, Globe, Loader2, Play } from "lucide-react"
import { parseCurl, type CurlParam } from "@/lib/curl"
import { useExecuteHttpRequest, useTestStandStatus } from "@/hooks/useTestStand"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { HttpExecuteResponse } from "@/types/api"

// Swagger-like chrome: the card frame and header are tinted by HTTP method
const METHOD_BADGE: Record<string, string> = {
  GET: "bg-sky-600",
  POST: "bg-emerald-600",
  PUT: "bg-amber-600",
  PATCH: "bg-teal-600",
  DELETE: "bg-red-600",
  HEAD: "bg-violet-600",
  OPTIONS: "bg-slate-600",
}

const METHOD_TINT: Record<string, { frame: string; head: string }> = {
  GET: { frame: "border-sky-200/80 dark:border-sky-900/50", head: "bg-sky-50/70 dark:bg-sky-950/20" },
  POST: { frame: "border-emerald-200/80 dark:border-emerald-900/50", head: "bg-emerald-50/70 dark:bg-emerald-950/20" },
  PUT: { frame: "border-amber-200/80 dark:border-amber-900/50", head: "bg-amber-50/70 dark:bg-amber-950/20" },
  PATCH: { frame: "border-teal-200/80 dark:border-teal-900/50", head: "bg-teal-50/70 dark:bg-teal-950/20" },
  DELETE: { frame: "border-red-200/80 dark:border-red-900/50", head: "bg-red-50/70 dark:bg-red-950/20" },
  HEAD: { frame: "border-violet-200/80 dark:border-violet-900/50", head: "bg-violet-50/70 dark:bg-violet-950/20" },
  OPTIONS: { frame: "border-border", head: "bg-muted/30" },
}

function prettyJsonOrRaw(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

function statusTone(status: number): string {
  if (status < 300) return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
  if (status < 400) return "bg-sky-100 text-sky-800 dark:bg-sky-950/40 dark:text-sky-300"
  if (status < 500) return "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
  return "bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300"
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      {children}
    </p>
  )
}

function CodeBlock({ value, subdued = false }: { value: string; subdued?: boolean }) {
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border/60 px-3 py-2.5 text-[0.75rem] font-mono leading-6",
        subdued ? "bg-muted/30 text-muted-foreground" : "bg-muted/40 text-foreground"
      )}
    >
      <code>{value}</code>
    </pre>
  )
}

function ParamsTable({ params }: { params: CurlParam[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border/70">
      <table className="w-full text-xs">
        <tbody>
          {params.map((p, i) => (
            <tr key={i} className={cn(i > 0 && "border-t border-muted")}>
              <td className="w-[220px] whitespace-nowrap bg-muted/40 px-2.5 py-1.5 align-top font-mono font-medium text-foreground/90">
                {p.name}
              </td>
              <td className="break-all px-2.5 py-1.5 font-mono text-foreground/85">{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Collapsible({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-[0.75rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {label}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  )
}

function ResponsePanel({ result }: { result: HttpExecuteResponse }) {
  return (
    <div className="border-t border-border/70 bg-muted/[0.12] px-4 py-3">
      <SectionLabel>Ответ стенда</SectionLabel>
      {result.error ? (
        <p className="whitespace-pre-wrap break-words text-[0.8125rem] text-destructive">{result.error}</p>
      ) : (
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("rounded-md px-2 py-0.5 text-[0.75rem] font-mono font-semibold", statusTone(result.status_code ?? 0))}>
              {result.status_code} {result.reason}
            </span>
            <span className="text-[0.6875rem] text-muted-foreground">{result.duration_ms} мс</span>
            <code className="min-w-0 flex-1 truncate text-[0.6875rem] font-mono text-muted-foreground" title={result.url}>
              {result.url}
            </code>
          </div>
          {result.headers.length > 0 && (
            <Collapsible label={`Заголовки ответа (${result.headers.length})`}>
              <ParamsTable params={result.headers} />
            </Collapsible>
          )}
          {result.body && <CodeBlock value={prettyJsonOrRaw(result.body)} />}
          {result.body_truncated && <p className="text-[0.625rem] text-muted-foreground">Тело ответа обрезано</p>}
        </div>
      )}
    </div>
  )
}

export function CurlArtifact({
  value,
  copied,
  onCopy,
  projectSlug,
  featureName,
}: {
  value: string
  copied: boolean
  onCopy: () => void
  projectSlug: string
  featureName: string
}) {
  const parsed = useMemo(() => parseCurl(value), [value])
  const { data: stand } = useTestStandStatus(projectSlug, featureName)
  const execMut = useExecuteHttpRequest(projectSlug, featureName)

  const tabs = useMemo(
    () =>
      [
        parsed && parsed.query.length > 0 && { key: "query", label: `Query (${parsed.query.length})` },
        parsed && parsed.headers.length > 0 && { key: "headers", label: `Заголовки (${parsed.headers.length})` },
        parsed?.body && { key: "body", label: "Тело" },
        { key: "curl", label: "curl" },
      ].filter(Boolean) as { key: string; label: string }[],
    [parsed]
  )
  const [tab, setTab] = useState(tabs[0]?.key ?? "curl")

  const targetUrl = parsed && stand?.configured && stand.target_base
    ? stand.target_base + parsed.path
    : parsed?.url ?? null

  function handleExecute() {
    if (!parsed) return
    execMut.mutate({
      method: parsed.method,
      path: parsed.path,
      headers: Object.fromEntries(parsed.headers.map((h) => [h.name, h.value])),
      body: parsed.body,
    })
  }

  // Unparsable command — fall back to a plain code block
  if (!parsed) {
    return (
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="flex items-center justify-between gap-2 border-b border-border/70 bg-muted/[0.18] px-4 py-2.5">
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">cURL</p>
          <Button size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={onCopy} title="Копировать">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
        <div className="px-4 py-3">
          <CodeBlock value={value} />
        </div>
      </div>
    )
  }

  const tint = METHOD_TINT[parsed.method] ?? METHOD_TINT.OPTIONS

  return (
    <div className={cn("overflow-hidden rounded-2xl border bg-card", tint.frame)}>
      <div className={cn("flex items-center gap-2.5 px-4 py-2.5", tint.head)}>
        <span className={cn("shrink-0 rounded-md px-2.5 py-1 text-[0.6875rem] font-mono font-bold uppercase text-white", METHOD_BADGE[parsed.method] ?? "bg-slate-600")}>
          {parsed.method}
        </span>
        <code className="min-w-0 flex-1 truncate text-[0.8125rem] font-mono font-medium text-foreground" title={targetUrl ?? undefined}>
          {targetUrl}
        </code>
        <div className="flex shrink-0 items-center gap-1.5">
          {stand?.configured && (
            <Button
              size="sm"
              variant="outline"
              className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
              onClick={handleExecute}
              disabled={execMut.isPending}
              title={`Выполнить на тестовом стенде: ${targetUrl}`}
            >
              {execMut.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Выполняется
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" />
                  Выполнить
                </>
              )}
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={onCopy} title="Копировать curl">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {stand?.configured && (
        <div className="flex items-center gap-1.5 border-b border-border/60 px-4 py-1.5 text-[0.6875rem] text-muted-foreground">
          <Globe className="h-3 w-3 shrink-0" />
          <span className="truncate">
            стенд: <span className="font-mono">{stand.target_base}</span>
          </span>
        </div>
      )}

      <div className="flex items-center gap-1 px-4 pt-2.5">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "rounded-md px-2.5 py-1 text-[0.75rem] font-medium transition-colors",
              tab === t.key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="px-4 pb-3.5 pt-2.5">
        {tab === "query" && <ParamsTable params={parsed.query} />}
        {tab === "headers" && <ParamsTable params={parsed.headers} />}
        {tab === "body" && parsed.body && <CodeBlock value={prettyJsonOrRaw(parsed.body)} />}
        {tab === "curl" && <CodeBlock value={value} subdued />}
      </div>

      {execMut.error && (
        <div className="border-t border-border/70 px-4 py-2.5">
          <p className="whitespace-pre-wrap break-words text-[0.8125rem] text-destructive">{(execMut.error as Error).message}</p>
        </div>
      )}
      {execMut.data && <ResponsePanel result={execMut.data} />}
    </div>
  )
}
