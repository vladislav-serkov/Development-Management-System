import { useState } from "react"
import { Check, Loader2, Play, Square, X } from "lucide-react"
import { useFeatureGaps, useGapActions } from "@/hooks/useGaps"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import type { GapItem } from "@/types/api"

function ErrorText({ error }: { error: Error | null }) {
  return error ? <p role="alert" className="text-sm text-destructive">{error.message}</p> : null
}

function GapRemark({ gap, project, feature }: { gap: GapItem; project: string; feature: string }) {
  const { review } = useGapActions(project, feature)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState("")
  const submit = (status: "approved" | "rejected", analyst_text?: string | null) =>
    review.mutate({ id: gap.id, status, analyst_text }, { onSuccess: () => setRejecting(false) })
  const sources = gap.source_snapshots ?? []
  const evidence = gap.evidence ?? []
  return <article className="space-y-3 p-4">
    <p className="whitespace-pre-wrap text-sm leading-relaxed">{gap.text}</p>
    {gap.analyst_text && <p className="whitespace-pre-wrap text-xs text-muted-foreground">Причина отклонения: {gap.analyst_text}</p>}
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {evidence.map((entry, i) => {
          const source = sources.find(s => s.id === entry.source_id)
          const url = source?.url && /^https?:\/\//i.test(source.url) ? source.url : null
          const label = entry.location || source?.title || "Источник"
          const title = [source?.title, entry.location, entry.quote].filter(Boolean).join("\n")
          return url ? <a key={i} href={url} title={title} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{label}</a>
            : <span key={i} title={title}>{label}</span>
        })}
        {evidence.length === 0 && <span>Источник прежнего замечания не сохранён</span>}
        {gap.needs_review ? <span>Есть новые основания</span>
          : gap.presence === "not_detected" ? <span>Не найдено при последней проверке</span>
          : gap.presence === "unverified" ? <span>Повторно не проверено</span>
          : gap.status === "approved" ? <span>Принято</span>
          : gap.status === "rejected" ? <span>Отклонено</span> : null}
      </div>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" disabled={review.isPending || (gap.status === "approved" && !gap.needs_review)}
          onClick={() => submit("approved")}><Check className="h-3.5 w-3.5" />Принять</Button>
        <Button size="sm" variant="ghost" disabled={review.isPending || (gap.status === "rejected" && !gap.needs_review)}
          onClick={() => { setRejecting(true); setReason(gap.status === "rejected" ? gap.analyst_text ?? "" : "") }}><X className="h-3.5 w-3.5" />Отклонить</Button>
      </div>
    </div>
    {rejecting && <div className="space-y-2">
      <label className="block space-y-2 text-sm"><span>Причина отклонения (необязательно)</span>
        <Textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} maxLength={20000} />
      </label>
      <div className="flex gap-2">
        <Button size="sm" disabled={review.isPending} onClick={() => submit("rejected", reason.trim() || null)}>Отклонить замечание</Button>
        <Button size="sm" variant="ghost" disabled={review.isPending} onClick={() => setRejecting(false)}>Отмена</Button>
      </div>
    </div>}
    <ErrorText error={review.error} />
  </article>
}

export function GapsView({ projectSlug, featureName }: { projectSlug: string; featureName: string }) {
  const query = useFeatureGaps(projectSlug, featureName)
  const { run, cancel } = useGapActions(projectSlug, featureName)
  const [filter, setFilter] = useState<"pending" | "approved" | "rejected" | "history">("pending")
  const data = query.data
  const running = run.isPending || !!data?.gaps_running
  const gaps = data?.gaps ?? []
  const groups = {
    pending: gaps.filter(g => (g.presence ?? "current") === "current" && (g.needs_review || !["approved", "rejected", "applied"].includes(g.status))),
    approved: gaps.filter(g => (g.presence ?? "current") === "current" && ["approved", "applied"].includes(g.status) && !g.needs_review),
    rejected: gaps.filter(g => (g.presence ?? "current") === "current" && g.status === "rejected" && !g.needs_review),
    history: gaps.filter(g => g.presence === "not_detected" || g.presence === "unverified"),
  }
  const finishedAt = data?.analysis?.finished_at ?? data?.gaps_run_at
  const partial = data?.analysis?.coverage === "partial"
  return <section className="space-y-4" aria-label="GAP-анализ">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-base font-medium">Замечания к ТЗ</h2>
        {finishedAt && <p className="mt-1 text-xs text-muted-foreground">{running ? "Предыдущая проверка" : "Последняя проверка"}: {new Date(finishedAt).toLocaleString("ru-RU")}</p>}
      </div>
      <div className="flex items-center gap-2">
        <Button disabled={running || !data?.configured} size="sm" onClick={() => run.mutate()}>
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          {running ? "Проверяем ТЗ…" : finishedAt ? "Повторить анализ" : "Запустить анализ"}
        </Button>
        {data?.gaps_running && <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate()}><Square className="h-3.5 w-3.5" />Остановить</Button>}
      </div>
    </div>
    {data?.configured === false && <p className="text-sm text-muted-foreground">Анализ временно недоступен.</p>}
    {data?.stale && <p className="text-sm text-muted-foreground">ТЗ или исходные материалы изменились. Запустите анализ повторно.</p>}
    {partial && <p role="status" className="text-sm text-muted-foreground">Не удалось проверить часть ТЗ.</p>}
    {data?.job?.stage === "cancelled" && !running && <p className="text-sm text-muted-foreground">Анализ остановлен. Предыдущие замечания сохранены.</p>}
    {data?.job?.error && !running && <p role="alert" className="text-sm text-destructive">{data.job.error}</p>}
    <ErrorText error={query.error} /><ErrorText error={run.error} /><ErrorText error={cancel.error} />

    {(groups.approved.length > 0 || groups.rejected.length > 0 || groups.history.length > 0) &&
      <select aria-label="Показать замечания" className="rounded-md border bg-background px-2 py-1.5 text-xs"
        value={filter} onChange={e => setFilter(e.target.value as typeof filter)}>
        <option value="pending">К рассмотрению · {groups.pending.length}</option>
        <option value="approved">Принятые · {groups.approved.length}</option>
        <option value="rejected">Отклонённые · {groups.rejected.length}</option>
        {groups.history.length > 0 && <option value="history">Предыдущие · {groups.history.length}</option>}
      </select>}
    {query.isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
    {!query.isLoading && !query.error && groups[filter].length === 0 && <p className="py-6 text-sm text-muted-foreground">
      {running ? "Замечания появятся после завершения анализа."
        : !finishedAt ? "Запустите анализ, чтобы проверить ТЗ."
        : filter !== "pending" ? "В этой группе замечаний нет."
        : groups.approved.length + groups.rejected.length > 0 ? "Все замечания рассмотрены."
        : partial ? "В проверенной части замечаний нет."
        : "Обоснованных замечаний не найдено."}
    </p>}
    {groups[filter].length > 0 && <div className="divide-y rounded-lg border" aria-label="Список замечаний">
      {groups[filter].map(gap => <GapRemark key={gap.id} gap={gap} project={projectSlug} feature={featureName} />)}
    </div>}
  </section>
}
