import { useState } from "react"
import { AlertTriangle, Check, Loader2, Play, Square, X } from "lucide-react"
import { useFeatureGaps, useGapActions } from "@/hooks/useGaps"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import type { GapEvidence, GapItem, GapSource } from "@/types/api"

const STAGES: Record<string, string> = {
  sources: "Собираем спецификации",
  queued: "Ожидаем запуска",
  research: "Изучаем ТЗ и связанные спецификации",
  analysis: "Проверяем сценарии",
  verification: "Перепроверяем обоснованность замечаний",
  saving: "Сохраняем замечания",
}

function ErrorText({ error }: { error: Error | null }) {
  return error ? <p role="alert" className="text-sm text-destructive">{error.message}</p> : null
}

function EvidenceList({ evidence, sources }: { evidence: GapEvidence[]; sources: GapSource[] }) {
  return <div className="space-y-3">{evidence.map((entry, i) => {
    const source = sources.find(s => s.id === entry.source_id)
    const url = source?.url && /^https?:\/\//i.test(source.url) ? source.url : null
    return <div key={i} className="text-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{source?.title}</a>
          : <span>{source?.title ?? "Спецификация"}</span>}
        {source?.version != null && <span>версия {source.version}</span>}
        <span>{entry.location}</span>
      </div>
      <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-border pl-3 leading-relaxed">{entry.quote}</blockquote>
    </div>
  })}</div>
}

function GapCard({ gap, sources, project, feature }: {
  gap: GapItem; sources: GapSource[]; project: string; feature: string
}) {
  const { review } = useGapActions(project, feature)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState("")
  const submit = (status: "approved" | "rejected", analyst_text?: string | null) =>
    review.mutate({ id: gap.id, status, analyst_text }, { onSuccess: () => setRejecting(false) })
  return <article className="rounded-xl border bg-card p-4 md:p-5">
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {gap.severity === "critical" && <Badge variant="outline" className="border-red-300 text-red-600">Критично</Badge>}
      {gap.needs_review ? <Badge variant="outline">Требуется повторное рассмотрение</Badge>
        : gap.status === "approved" ? <Badge variant="secondary">Принято</Badge>
        : gap.status === "rejected" ? <Badge variant="secondary">Отклонено</Badge> : null}
      {gap.presence === "not_detected" && <span className="text-muted-foreground">Не найдено при последней проверке</span>}
      {gap.presence === "unverified" && <span className="text-muted-foreground">Повторно не проверено</span>}
      {gap.location && <span className="text-muted-foreground">{gap.location}</span>}
    </div>
    <h3 className="mt-2 whitespace-pre-wrap text-sm font-medium leading-relaxed">{gap.question}</h3>
    {gap.scenario && <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{gap.scenario}</p>}
    {gap.business_impact && <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{gap.business_impact}</p>}
    <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed"><span className="font-medium">Что уточнить: </span>{gap.suggestion}</p>
    {gap.needs_review && gap.reconsideration_reason && <p className="mt-3 text-sm leading-relaxed"><span className="font-medium">Новое основание: </span>{gap.reconsideration_reason}</p>}
    {gap.analyst_text && <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground"><span className="font-medium">Комментарий: </span>{gap.analyst_text}</p>}
    {gap.status === "approved" && !gap.needs_review && <p className="mt-2 text-xs text-muted-foreground">Принято к учёту. ТЗ в Confluence обновляется отдельно.</p>}
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
      <details className="min-w-0 basis-full sm:basis-auto sm:flex-1">
        <summary className="w-fit cursor-pointer text-xs text-muted-foreground">Источники и обоснование</summary>
        <div className="mt-3">{gap.evidence?.length
          ? <EvidenceList evidence={gap.evidence} sources={gap.source_snapshots ?? sources} />
          : <p className="text-xs text-muted-foreground">Цитаты прежнего анализа не сохранены. Запустите повторную проверку.</p>}
        </div>
      </details>
      <div className="flex shrink-0 gap-1">
        <Button size="sm" variant="ghost" disabled={review.isPending || (gap.status === "approved" && !gap.needs_review)}
          onClick={() => submit("approved", gap.status === "rejected" ? null : gap.analyst_text)}><Check className="h-3.5 w-3.5" />Принять</Button>
        <Button size="sm" variant="ghost" disabled={review.isPending || (gap.status === "rejected" && !gap.needs_review)}
          onClick={() => { setRejecting(true); setReason(gap.status === "rejected" ? gap.analyst_text ?? "" : "") }}><X className="h-3.5 w-3.5" />Отклонить</Button>
      </div>
    </div>
    {rejecting && <div className="mt-3 space-y-2 rounded-lg bg-muted/30 p-3">
      <label className="block space-y-2 text-sm"><span>Причина отклонения <span className="text-muted-foreground">(необязательно)</span></span>
        <Textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} maxLength={20000}
          placeholder="Пояснение поможет при следующих проверках" />
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
  const analysis = data?.analysis
  const running = run.isPending || !!data?.gaps_running
  const gaps = data?.gaps ?? []
  const groups = {
    pending: gaps.filter(g => (g.presence ?? "current") === "current" && (g.needs_review || !["approved", "rejected"].includes(g.status))),
    approved: gaps.filter(g => (g.presence ?? "current") === "current" && g.status === "approved" && !g.needs_review),
    rejected: gaps.filter(g => (g.presence ?? "current") === "current" && g.status === "rejected" && !g.needs_review),
    history: gaps.filter(g => g.presence === "not_detected" || g.presence === "unverified"),
  }
  const visible = groups[filter]
  const finishedAt = analysis?.finished_at ?? data?.gaps_run_at
  const checked = !!finishedAt
  return <div className="space-y-4">
    <section className="rounded-xl border bg-card p-4 md:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-medium">GAP-анализ</h2>
          <p className="mt-1 text-sm text-muted-foreground">Замечания к ТЗ выбранной фичи</p>
        </div>
        <div className="flex items-center gap-2">
          <Button disabled={running || !data?.configured} size="sm" onClick={() => run.mutate()}>
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running ? "Анализ выполняется" : checked ? "Повторить анализ" : "Запустить анализ"}
          </Button>
          {data?.gaps_running && <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}><Square className="h-3.5 w-3.5" />Остановить</Button>}
        </div>
      </div>
      {finishedAt && <p className="mt-3 text-xs text-muted-foreground">{running ? "Предыдущая проверка" : "Последняя проверка"}: {new Date(finishedAt).toLocaleString("ru-RU")}</p>}
      {running && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{STAGES[data?.job?.stage ?? "sources"] ?? "Анализ выполняется"}<AnimatedDots /></p>}
      {data?.configured === false && <p className="mt-3 text-sm text-amber-600">Анализ временно недоступен. Обратитесь к администратору.</p>}
      {data?.job?.stage === "cancelled" && !running && <p className="mt-3 text-sm text-muted-foreground">Анализ остановлен. Предыдущие результаты сохранены.</p>}
      {data?.job?.error && !running && <p role="alert" className="mt-3 text-sm text-destructive">{data.job.error}</p>}
      <div className="mt-3 space-y-2"><ErrorText error={query.error} /><ErrorText error={run.error} /><ErrorText error={cancel.error} /></div>
    </section>

    {data?.stale && <p className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-500/5 p-3 text-sm"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />Исходные материалы изменились. Запустите анализ повторно.</p>}
    {analysis?.coverage === "partial" && <div className="rounded-lg border border-amber-300 bg-amber-500/5 p-3 text-sm">
      <p className="font-medium">{running ? "Предыдущая проверка неполная" : "Проверка неполная"}</p>
      <p className="mt-1 text-muted-foreground">Часть материалов не удалось проверить. Замечания относятся только к проверенной части.</p>
      {analysis.limitations.length > 0 && <details className="mt-2"><summary className="w-fit cursor-pointer text-xs">Что помешало проверке</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{analysis.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul>
      </details>}
    </div>}

    <section className="space-y-3" aria-label="Замечания к ТЗ">
      {(checked || gaps.length > 0) && <div className="flex flex-wrap gap-1" aria-label="Фильтр замечаний">{([
        ["pending", "К рассмотрению"], ["approved", "Принятые"], ["rejected", "Отклонённые"], ["history", "Предыдущие"],
      ] as const).filter(([value]) => value !== "history" || groups.history.length > 0).map(([value, label]) =>
        <Button key={value} size="sm" variant={filter === value ? "secondary" : "ghost"} aria-pressed={filter === value}
          onClick={() => setFilter(value)}>{label} · {groups[value].length}</Button>)}
      </div>}
      {query.isLoading && <p className="text-sm text-muted-foreground">Загрузка результатов…</p>}
      {!query.isLoading && !query.error && visible.length === 0 && <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
        {running ? "Проверяем спецификации. Замечания появятся после завершения анализа."
          : !checked ? "Запустите анализ, чтобы проверить ТЗ выбранной фичи."
          : filter !== "pending" ? "В этой группе замечаний нет."
          : analysis?.coverage === "partial" ? "В проверенной части обоснованных замечаний не найдено. Проверка неполная."
          : groups.approved.length + groups.rejected.length > 0 ? "Все замечания рассмотрены. Принятые и отклонённые доступны через фильтры."
          : "Обоснованных замечаний не найдено."}
      </div>}
      {visible.map(gap => <GapCard key={gap.id} gap={gap} sources={analysis?.sources ?? []} project={projectSlug} feature={featureName} />)}
    </section>
  </div>
}
