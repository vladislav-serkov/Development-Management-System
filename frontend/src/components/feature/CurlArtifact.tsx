import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Loader2, Play } from "lucide-react"
import { parseCurl, type CurlParam } from "@/lib/curl"
import { useExecuteHttpRequest, useTestStandStatus } from "@/hooks/useTestStand"
import { Button } from "@/components/ui/button"
import { MethodBadge } from "@/components/sidebar/MethodBadge"
import { cn } from "@/lib/utils"
import { ArtifactHead, CodeBlock, CopyButton, MetaChip, SubTabs } from "./artifact-ui"
import { prettyJsonOrRaw } from "@/lib/artifacts"
import type { HttpExecuteResponse } from "@/types/api"

function statusTone(status: number): string {
  if (status < 300) return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400"
  if (status < 400) return "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300"
  if (status < 500) return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300"
  return "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400"
}

function ParamsTable({ params }: { params: CurlParam[] }) {
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full text-xs">
        <tbody>
          {params.map((p, i) => (
            <tr key={i} className={cn(i > 0 && "border-t")}>
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
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Ответ стенда</span>
        {!result.error && (
          <>
            <span className={cn("rounded-full border px-2 py-px font-mono text-[0.6875rem] font-semibold", statusTone(result.status_code ?? 0))}>
              {result.status_code} {result.reason}
            </span>
            <span className="text-[0.6875rem] text-muted-foreground">{result.duration_ms} мс</span>
            <code className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-muted-foreground" title={result.url}>
              {result.url}
            </code>
          </>
        )}
      </div>
      {result.error ? (
        <p className="whitespace-pre-wrap break-words text-[0.8125rem] text-destructive">{result.error}</p>
      ) : (
        <>
          {result.headers.length > 0 && (
            <Collapsible label={`Заголовки ответа (${result.headers.length})`}>
              <ParamsTable params={result.headers} />
            </Collapsible>
          )}
          {result.body && <CodeBlock value={prettyJsonOrRaw(result.body)} copyValue={result.body} />}
          {result.body_truncated && <p className="text-[0.625rem] text-muted-foreground">Тело ответа обрезано</p>}
        </>
      )}
    </div>
  )
}

export function CurlArtifact({
  value,
  projectSlug,
  featureName,
}: {
  value: string
  projectSlug: string
  featureName: string
}) {
  const parsed = useMemo(() => parseCurl(value), [value])
  const { data: stand } = useTestStandStatus(projectSlug, featureName)
  const execMut = useExecuteHttpRequest(projectSlug, featureName)

  const tabs = useMemo(
    () =>
      [
        parsed?.body && { key: "body", label: "Тело" },
        parsed && parsed.query.length > 0 && { key: "query", label: `Query (${parsed.query.length})` },
        parsed && parsed.headers.length > 0 && { key: "headers", label: `Заголовки (${parsed.headers.length})` },
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
      <div className="space-y-2.5">
        <ArtifactHead badge={<MethodBadge method={null} featureType="rest_endpoint" />} target="curl" />
        <CodeBlock value={value} />
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      <ArtifactHead
        badge={<MethodBadge method={parsed.method} featureType="rest_endpoint" />}
        target={parsed.path}
        chips={
          stand?.configured ? (
            <MetaChip mono title={stand.target_base ?? undefined}>стенд {stand.target_base}</MetaChip>
          ) : undefined
        }
        actions={
          <>
            {stand?.configured && (
              <Button
                size="sm"
                variant="outline"
                className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900/60 dark:text-emerald-400 dark:hover:bg-emerald-950/30 dark:hover:text-emerald-300"
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
                    Выполнить на стенде
                  </>
                )}
              </Button>
            )}
            <CopyButton value={value} label="curl" />
          </>
        }
      />

      <SubTabs tabs={tabs} value={tab} onChange={setTab} />

      {tab === "query" && <ParamsTable params={parsed.query} />}
      {tab === "headers" && <ParamsTable params={parsed.headers} />}
      {tab === "body" && parsed.body && <CodeBlock value={prettyJsonOrRaw(parsed.body)} copyValue={parsed.body} />}
      {tab === "curl" && <CodeBlock value={value} />}

      {execMut.error && (
        <p className="whitespace-pre-wrap break-words text-[0.8125rem] text-destructive">{(execMut.error as Error).message}</p>
      )}
      {execMut.data && <ResponsePanel result={execMut.data} />}
    </div>
  )
}
