import { useState } from "react"
import { AlertTriangle, Check, Loader2, Play, RotateCcw, Square, X } from "lucide-react"
import { useFeatureGaps, useGapActions, useGapContext } from "@/hooks/useGaps"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { cn } from "@/lib/utils"
import type { BusinessPicture, GapContext, GapEvidence, GapItem, GapSource } from "@/types/api"

const STAGES: Record<string, string> = {
  sources: "Собираем исходные спецификации",
  queued: "Ожидаем свободный Codex",
  research: "Изучаем бизнес-процесс и связанные ТЗ",
  analysis: "Проверяем сценарии и движение данных",
  verification: "Перепроверяем замечания по источникам",
  saving: "Сохраняем результаты",
}
const KINDS: Record<string, string> = {
  contradiction: "Противоречие", missing_logic: "Пропущенная логика", business_question: "Вопрос о бизнес-правиле",
}
const STATUSES: Record<string, string> = {
  pending: "К рассмотрению", approved: "Подтверждено", clarified: "Есть уточнение", rejected: "Отклонено", applied: "Ранее применено",
}
const HISTORY_ACTIONS = { ...STATUSES, sources_changed: "Изменились источники" } as Record<string, string>
const FACT_SECTIONS: [keyof Omit<BusinessPicture, "purpose" | "purpose_evidence" | "unknowns">, string][] = [
  ["actors", "Участники"], ["entities_and_states", "Сущности и состояния"],
  ["lifecycle", "Жизненный цикл"], ["business_rules", "Бизнес-правила"],
]

function ErrorText({ error }: { error: Error | null }) {
  return error ? <p role="alert" className="text-sm text-destructive">{error.message}</p> : null
}

function EvidenceList({ evidence, sources }: { evidence: GapEvidence[]; sources: GapSource[] }) {
  return <div className="space-y-2">{evidence.map((entry, i) => {
    const source = sources.find(s => s.id === entry.source_id)
    const url = source?.url && /^https?:\/\//i.test(source.url) ? source.url : null
    return <div key={i} className="rounded-lg border bg-muted/20 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{source?.title}</a>
          : <span>{source?.title ?? entry.source_id}</span>}
        {source?.version != null && <span>версия {source.version}</span>}
        <span>{entry.location}</span>
      </div>
      <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-border pl-3 leading-relaxed">{entry.quote}</blockquote>
    </div>
  })}</div>
}

function ContextEditor({ initial, onSave, pending, error }: {
  initial: GapContext; onSave: (value: GapContext) => void; pending: boolean; error: Error | null
}) {
  const [notes, setNotes] = useState(initial.notes)
  const [urls, setUrls] = useState(initial.source_urls.join("\n"))
  const [saved, setSaved] = useState(false)
  return <div className="mt-4 space-y-3">
    <p className="text-sm text-muted-foreground">Общий контекст для всех фич проекта. Опишите назначение продукта, участников и важные бизнес-правила. Добавьте ссылки на обзор процесса и связанные ТЗ.</p>
    <label className="block space-y-1.5 text-sm">
      <span>Пояснения аналитика</span>
      <Textarea value={notes} onChange={e => { setNotes(e.target.value); setSaved(false) }} rows={5} maxLength={20000}
        placeholder="Зачем существует этот процесс, что считается успехом, какие ограничения важны…" />
    </label>
    <label className="block space-y-1.5 text-sm">
      <span>Источники бизнес-контекста — по одной ссылке Confluence на строку</span>
      <Textarea value={urls} onChange={e => { setUrls(e.target.value); setSaved(false) }} rows={3} placeholder="https://confluence…" />
    </label>
    <div className="flex items-center gap-3">
      <Button size="sm" disabled={pending} onClick={() => {
        onSave({ notes, source_urls: urls.split("\n").map(s => s.trim()).filter(Boolean) }); setSaved(true)
      }}>{pending ? "Сохранение…" : "Сохранить контекст проекта"}</Button>
      {saved && !pending && !error && <span className="text-xs text-muted-foreground">Сохранено</span>}
    </div>
    <ErrorText error={error} />
  </div>
}

function BusinessView({ picture, sources }: { picture: BusinessPicture; sources: GapSource[] }) {
  return <section className="rounded-xl border bg-card p-4 md:p-5 space-y-4">
    <div>
      <h3 className="font-medium">Как агент понял бизнес-процесс</h3>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{picture.purpose}</p>
      <details className="mt-2"><summary className="cursor-pointer text-xs text-muted-foreground">Источники назначения операции</summary>
        <div className="mt-2"><EvidenceList evidence={picture.purpose_evidence} sources={sources} /></div>
      </details>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">{FACT_SECTIONS.map(([key, label]) => <div key={key}>
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</h4>
      {picture[key].length === 0 ? <p className="mt-2 text-sm text-muted-foreground">Не установлено по источникам</p>
        : <ul className="mt-2 space-y-2">{picture[key].map((fact, i) => <li key={i} className="text-sm leading-relaxed">
          <p className="whitespace-pre-wrap">{fact.text}</p>
          <details className="mt-1"><summary className="cursor-pointer text-xs text-muted-foreground">Подтверждение в источниках</summary>
            <div className="mt-2"><EvidenceList evidence={fact.evidence} sources={sources} /></div>
          </details>
        </li>)}</ul>}
    </div>)}</div>
    {picture.unknowns.length > 0 && <div className="rounded-lg bg-amber-500/10 p-3 text-sm">
      <h4 className="font-medium">Что пока неизвестно</h4>
      <ul className="mt-2 list-disc space-y-1 pl-5">{picture.unknowns.map((text, i) => <li key={i}>{text}</li>)}</ul>
    </div>}
    <p className="text-xs text-muted-foreground">Если смысл процесса понят неверно, внесите пояснение в контекст проекта и запустите анализ снова.</p>
  </section>
}

function GapCard({ gap, sources, project, feature }: {
  gap: GapItem; sources: GapSource[]; project: string; feature: string
}) {
  const { review } = useGapActions(project, feature)
  const [mode, setMode] = useState<"clarified" | "rejected" | null>(null)
  const [text, setText] = useState(gap.analyst_text ?? "")
  const submit = (status: string, analyst_text?: string | null) => review.mutate({ id: gap.id, status, analyst_text }, {
    onSuccess: () => setMode(null),
  })
  return <article className="rounded-xl border bg-card p-4 md:p-5 space-y-4">
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className={gap.severity === "critical" ? "text-red-600 border-red-300" : "text-amber-600 border-amber-300"}>
          {gap.severity === "critical" ? "Критично" : "Существенно"}
        </Badge>
        <span>{gap.kind ? KINDS[gap.kind] : "Замечание из прежнего анализа"}</span>
        <span className="text-muted-foreground">{STATUSES[gap.status]}</span>
        {gap.presence === "not_detected" && <Badge variant="outline">Не найдено при последней проверке</Badge>}
        {gap.presence === "unverified" && <Badge variant="outline">Повторно не проверено</Badge>}
        {gap.needs_review && <Badge variant="outline">Источники изменились — перепроверьте решение</Badge>}
      </div>
      <h3 className="whitespace-pre-wrap text-sm font-medium leading-relaxed">{gap.question}</h3>
      {gap.location && <p className="text-xs text-muted-foreground">{gap.location}</p>}
    </div>
    {(gap.scenario || gap.business_impact) && <div className="grid gap-4 md:grid-cols-2 text-sm">
      <div><h4 className="mb-1 text-xs text-muted-foreground">Проблемный сценарий</h4><p className="whitespace-pre-wrap leading-relaxed">{gap.scenario}</p></div>
      <div><h4 className="mb-1 text-xs text-muted-foreground">Последствие для бизнеса</h4><p className="whitespace-pre-wrap leading-relaxed">{gap.business_impact}</p></div>
    </div>}
    {gap.evidence?.length ? <EvidenceList evidence={gap.evidence} sources={gap.source_snapshots ?? sources} />
      : <p className="text-xs text-muted-foreground">Замечание из прежнего анализа. Цитаты не сохранены — нужна повторная проверка.</p>}
    <div className="text-sm"><h4 className="mb-1 text-xs text-muted-foreground">Что уточнить в ТЗ</h4><p className="whitespace-pre-wrap leading-relaxed">{gap.suggestion}</p></div>
    {gap.analyst_text && <div className="rounded-lg bg-muted/40 p-3 text-sm"><h4 className="mb-1 text-xs text-muted-foreground">Решение аналитика</h4><p className="whitespace-pre-wrap">{gap.analyst_text}</p></div>}
    <div className="flex flex-wrap gap-2 border-t pt-3">
      <Button size="sm" variant="outline" disabled={review.isPending} onClick={() => submit("approved", gap.analyst_text)}><Check className="h-3.5 w-3.5" />Подтвердить</Button>
      <Button size="sm" variant="outline" disabled={review.isPending} onClick={() => { setMode("clarified"); setText(gap.analyst_text ?? "") }}>Дать уточнение</Button>
      <Button size="sm" variant="ghost" disabled={review.isPending} onClick={() => { setMode("rejected"); setText(gap.analyst_text ?? "") }}><X className="h-3.5 w-3.5" />Отклонить</Button>
      {gap.status !== "pending" && <Button size="sm" variant="ghost" disabled={review.isPending} onClick={() => submit("pending", null)}><RotateCcw className="h-3.5 w-3.5" />Вернуть к рассмотрению</Button>}
    </div>
    {mode && <div className="space-y-2">
      <label className="block space-y-2 text-sm"><span>{mode === "rejected" ? "Почему замечание неверно или неактуально" : "Уточнение бизнес-правила или поведения"}</span>
        <Textarea value={text} onChange={e => setText(e.target.value)} rows={3} maxLength={20000} />
      </label>
      <div className="flex gap-2"><Button size="sm" disabled={review.isPending || !text.trim()} onClick={() => submit(mode, text.trim())}>Сохранить решение</Button>
        <Button size="sm" variant="ghost" onClick={() => setMode(null)}>Отмена</Button></div>
    </div>}
    <ErrorText error={review.error} />
    {!!gap.history?.length && <details><summary className="cursor-pointer text-xs text-muted-foreground">История решений ({gap.history.length})</summary>
      <ul className="mt-2 space-y-2 text-xs text-muted-foreground">{gap.history.map((item, i) => <li key={i}>
        {new Date(item.at).toLocaleString("ru-RU")} · {item.actor ?? "Система"} · {HISTORY_ACTIONS[item.action] ?? "Решение обновлено"}
        {item.text && <p className="mt-1 whitespace-pre-wrap">{item.text}</p>}
      </li>)}</ul>
    </details>}
  </article>
}

export function GapsView({ projectSlug, featureName }: { projectSlug: string; featureName: string }) {
  const query = useFeatureGaps(projectSlug, featureName)
  const context = useGapContext(projectSlug)
  const { run, cancel } = useGapActions(projectSlug, featureName)
  const [filter, setFilter] = useState<"active" | "rejected" | "history" | "all">("active")
  const data = query.data
  const analysis = data?.analysis
  const running = run.isPending || !!data?.gaps_running
  const gaps = data?.gaps ?? []
  const current = gaps.filter(g => (g.presence ?? "current") === "current" && (g.status !== "rejected" || g.needs_review))
  const previousCount = gaps.filter(g => g.presence === "not_detected" || g.presence === "unverified").length
  const rejectedCount = gaps.filter(g => g.status === "rejected").length
  const visible = gaps.filter(g => filter === "all" || (filter === "active" ? current.includes(g)
    : filter === "rejected" ? g.status === "rejected" : g.presence === "not_detected" || g.presence === "unverified"))
  return <div className="space-y-5">
    <section className="rounded-xl border bg-card p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h2 className="text-base font-medium">Gap-анализ</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">Проверка бизнес-сценариев, пропущенной логики и согласованности параметров по исходным спецификациям.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button disabled={running || !data?.configured} size="sm" onClick={() => run.mutate()}>
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running ? "Анализ выполняется" : analysis || data?.gaps_run_at ? "Повторить анализ" : "Запустить анализ"}
          </Button>
          {data?.gaps_running && <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}><Square className="h-3.5 w-3.5" />Остановить</Button>}
        </div>
      </div>
      {running && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{STAGES[data?.job?.stage ?? "sources"] ?? "Анализ выполняется"}<AnimatedDots /></p>}
      {data?.configured === false && <p className="mt-3 text-sm text-amber-600">Codex отключён на сервере. Для анализа требуется включённый Codex с входом через ChatGPT.</p>}
      {data?.job?.stage === "cancelled" && !running && <p className="mt-3 text-sm text-muted-foreground">Анализ остановлен. Предыдущие результаты сохранены.</p>}
      {data?.job?.error && !running && <p role="alert" className="mt-3 text-sm text-destructive">{data.job.error}</p>}
      <div className="mt-3 space-y-2"><ErrorText error={query.error} /><ErrorText error={run.error} /><ErrorText error={cancel.error} /></div>
    </section>

    <details className="rounded-xl border bg-card p-4 md:p-5">
      <summary className="cursor-pointer text-sm font-medium">Бизнес-контекст проекта</summary>
      {context.data && <ContextEditor key={JSON.stringify(context.data)} initial={context.data} pending={context.save.isPending}
        error={context.save.error} onSave={value => context.save.mutate(value)} />}
      <ErrorText error={context.error} />
    </details>

    {data?.stale && <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-500/5 p-3 text-sm"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />ТЗ, зависимости или бизнес-контекст изменились. Результат требует повторной проверки.</div>}
    {analysis && <>
      <div className={cn("rounded-xl border p-4 text-sm", analysis.coverage === "partial" ? "border-amber-300 bg-amber-500/5" : "bg-muted/20")}>
        <p className="font-medium">{running ? "Предыдущий результат · " : ""}{analysis.coverage === "partial" ? "Проверка неполная" : "Проверка завершена"} · {new Date(analysis.finished_at).toLocaleString("ru-RU")}</p>
        <p className="mt-1 text-muted-foreground">Источников проверено: {analysis.checked_source_ids.length} · Сценариев: {analysis.checked_scenarios.length} · Актуальных замечаний: {current.length}</p>
        {analysis.limitations.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5">{analysis.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul>}
        <details className="mt-3"><summary className="cursor-pointer">Покрытие и версии источников</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">{analysis.checked_scenarios.map((text, i) => <li key={i}>{text}</li>)}</ul>
          <ul className="mt-3 space-y-1 text-xs text-muted-foreground">{analysis.sources.map(source => <li key={source.id}>
            {source.title}{source.version != null ? ` · версия ${source.version}` : ""} · {analysis.checked_source_ids.includes(source.id) ? "Проверен" : "Загружен, проверка не подтверждена"}
          </li>)}</ul>
        </details>
      </div>
      <BusinessView picture={analysis.business_picture} sources={analysis.sources} />
    </>}

    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-medium">Замечания</h3>
        <div className="flex flex-wrap gap-1">{([
          ["active", `Актуальные (${current.length})`], ["rejected", `Отклонённые (${rejectedCount})`],
          ["history", `Предыдущие (${previousCount})`], ["all", `Все (${gaps.length})`],
        ] as const).map(([value, label]) => <Button key={value} size="sm" variant={filter === value ? "secondary" : "ghost"} onClick={() => setFilter(value)}>{label}</Button>)}</div>
      </div>
      {query.isLoading && <p className="text-sm text-muted-foreground">Загрузка результатов…</p>}
      {!query.isLoading && visible.length === 0 && <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
        {!analysis && !data?.gaps_run_at ? "Добавьте бизнес-контекст и запустите проверку исходных спецификаций."
          : filter !== "active" ? "В этой группе замечаний нет."
          : analysis?.coverage === "partial" ? "В проверенной части замечаний нет. Для полного вывода нужны недостающие материалы."
          : "Актуальных замечаний нет. Список проверенных сценариев доступен в покрытии анализа."}
      </div>}
      {visible.map(gap => <GapCard key={gap.id} gap={gap} sources={analysis?.sources ?? []} project={projectSlug} feature={featureName} />)}
    </section>
  </div>
}
