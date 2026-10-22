import { useState } from "react"
import { useFeatureTestCases, usePatchTestCase, useDeleteTestCase, useRunTestCases, useAskTestCase, useRequestAutotest } from "@/hooks/useTestCases"
import { useGenerateBug } from "@/hooks/useBugs"
import { useExecuteSql, useTestDbStatus } from "@/hooks/useTestDb"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { StatStrip } from "@/components/ui/stat-strip"
import { FilterSelect, Segmented } from "@/components/ui/segmented"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { CurlArtifact } from "@/components/feature/CurlArtifact"
import { ArtifactHead, CodeBlock, CopyButton, MetaChip, TypeBadge } from "@/components/feature/artifact-ui"
import { ARTIFACT_BADGE } from "@/lib/artifacts"
import { Bot, Check, ChevronDown, ChevronUp, Equal, Loader2, Play, Search, Sparkles, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { countLabel } from "@/lib/plural"
import type { TestCaseItem, TestCaseCategory, SqlExecuteResponse } from "@/types/api"

const ARTIFACTS = [
  { key: "curl_command", label: "Запрос" },
  { key: "kafka_message", label: "Kafka" },
  { key: "sql_setup", label: "SQL" },
  { key: "mock_config", label: "Мок" },
] as const

const CATEGORY_LABEL: Record<TestCaseCategory, string> = {
  validation: "Валидация",
  positive: "Позитивный",
  negative: "Негативный",
  edge_case: "Граничный",
}

const PRIORITY_LABEL = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
} as const

type ReviewFilter = "all" | "pending" | "approved" | "edited"
type SortMode = "default" | "unreviewed" | "with_bug" | "longest"

function formatJsonOrRaw(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

function getArtifactCount(tc: TestCaseItem) {
  return ARTIFACTS.filter((artifact) => tc[artifact.key as keyof TestCaseItem]).length
}

function RichText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") ? (
          <code key={i} className="rounded bg-muted px-1 py-px text-[0.75rem] font-mono">
            {part.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}

function sortItems(items: Array<{ tc: TestCaseItem; idx: number }>, sortMode: SortMode) {
  const sorted = [...items]

  sorted.sort((a, b) => {
    if (sortMode === "default") return a.idx - b.idx
    if (sortMode === "longest") {
      return b.tc.steps.length - a.tc.steps.length || a.idx - b.idx
    }
    if (sortMode === "with_bug") {
      const aValue = a.tc.status === "edited" ? 1 : 0
      const bValue = b.tc.status === "edited" ? 1 : 0
      return bValue - aValue || a.idx - b.idx
    }

    const score = (tc: TestCaseItem) => {
      if (tc.status === "pending") return 0
      if (tc.status === "edited") return 1
      return 2
    }

    return score(a.tc) - score(b.tc) || a.idx - b.idx
  })

  return sorted
}

function PriorityBadge({ priority }: { priority: TestCaseItem["priority"] }) {
  const Icon = priority === "high" ? ChevronUp : priority === "low" ? ChevronDown : Equal
  return (
    <span
      title={`Приоритет: ${PRIORITY_LABEL[priority]}`}
      className="inline-flex h-5 w-5 shrink-0 items-center justify-center"
    >
      <Icon
        strokeWidth={2.75}
        className={cn(
          "h-4 w-4",
          priority === "high" && "text-red-500",
          priority === "medium" && "text-amber-500",
          priority === "low" && "text-blue-500"
        )}
      />
    </span>
  )
}

function TestCaseStatusBadge({ status }: { status: TestCaseItem["status"] }) {
  if (status === "pending") return null

  return (
    <span
      className={cn(
        "text-[0.6875rem] font-medium",
        status === "approved" && "text-emerald-600 dark:text-emerald-400",
        status === "edited" && "text-red-600 dark:text-red-400"
      )}
    >
      {status === "approved" ? "Принято" : "С багом"}
    </span>
  )
}

function TestCaseCard({
  tc,
  index,
  projectSlug,
  featureName,
  isOpen,
  onToggle,
  onResolved,
}: {
  tc: TestCaseItem
  index: number
  projectSlug: string
  featureName: string
  isOpen: boolean
  onToggle: () => void
  onResolved: (currentIndex: number) => void
}) {
  const patchMut = usePatchTestCase(projectSlug, featureName)
  const deleteMut = useDeleteTestCase(projectSlug, featureName)
  const generateBugMut = useGenerateBug(projectSlug, featureName)
  const autotestMut = useRequestAutotest(projectSlug, featureName)
  const [showBugForm, setShowBugForm] = useState(false)
  const [bugComment, setBugComment] = useState("")

  const isBusy = patchMut.isPending || deleteMut.isPending || generateBugMut.isPending
  const artifactCount = getArtifactCount(tc)

  function handleAccept() {
    patchMut.mutate(
      { tcIndex: index, status: "approved" },
      {
        onSuccess: () => {
          setShowBugForm(false)
          setBugComment("")
          onResolved(index)
        },
      }
    )
  }

  function handleReturnToReview() {
    patchMut.mutate({ tcIndex: index, status: "pending", analyst_text: null })
  }

  function handleCreateBug() {
    generateBugMut.mutate(
      { tcIndex: index, analystText: bugComment || null },
      {
        onSuccess: () => {
          patchMut.mutate(
            { tcIndex: index, status: "edited", analyst_text: bugComment || null },
            {
              onSuccess: () => {
                setShowBugForm(false)
                setBugComment("")
                onResolved(index)
              },
            }
          )
        },
      }
    )
  }

  return (
    <article
      id={`tc-card-${index}`}
      className={cn(
        "overflow-hidden rounded-xl border bg-card transition-all",
        isOpen ? "border-foreground/20 shadow-sm" : "hover:border-foreground/15"
      )}
    >
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-2.5",
          isOpen && "border-b bg-muted/20"
        )}
      >
        <button
          className={cn(
            "mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-[0.25rem] border transition-colors",
            tc.status === "approved" && "border-emerald-500 bg-emerald-500 text-white",
            tc.status === "edited" && "border-red-500 bg-red-500 text-white",
            tc.status === "pending" && "border-muted-foreground/25 hover:border-muted-foreground/50"
          )}
          onClick={(e) => {
            e.stopPropagation()
            if (tc.status === "pending") {
              handleAccept()
              return
            }

            handleReturnToReview()
          }}
          disabled={isBusy}
        >
          {tc.status !== "pending" && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
        </button>

        <button className="min-w-0 flex-1 text-left" onClick={onToggle}>
          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <p className={cn("text-[0.875rem] font-medium leading-[1.5] text-foreground", isOpen ? "font-semibold" : "line-clamp-1")}>
                <RichText text={tc.name} />
              </p>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground">
                <span>{countLabel(tc.steps.length, ["шаг", "шага", "шагов"])}</span>
                <span>{countLabel(artifactCount, ["артефакт", "артефакта", "артефактов"])}</span>
                {tc.origin === "ask" && <span>{CATEGORY_LABEL[tc.category]}</span>}
                {tc.covers && (
                  <span
                    className="max-w-[340px] truncate font-mono text-[0.625rem]"
                    title={tc.covers}
                  >
                    {tc.covers}
                  </span>
                )}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {tc.origin === "ask" && (
                <span title="Сгенерировано по запросу" className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
                  <Sparkles className="h-3.5 w-3.5 text-violet-500/80" />
                </span>
              )}
              <PriorityBadge priority={tc.priority} />
              <TestCaseStatusBadge status={tc.status} />
            </div>
          </div>
        </button>

        <div className="hidden items-center gap-2 lg:flex">
          {tc.status === "pending" ? (
            <>
              <Button size="sm" variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900/60 dark:text-emerald-400 dark:hover:bg-emerald-950/30 dark:hover:text-emerald-300" onClick={handleAccept} disabled={isBusy}>
                Принять
              </Button>
              <Button size="sm" variant="destructive" onClick={() => { setShowBugForm(true); if (!isOpen) onToggle() }} disabled={isBusy}>
                Баг
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={handleReturnToReview} disabled={isBusy}>
              Вернуть
            </Button>
          )}

          <Button size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={onToggle} aria-label={isOpen ? "Свернуть карточку" : "Раскрыть карточку"}>
            {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {tc.autotest_status && (
        <div className="flex flex-wrap items-center gap-2.5 border-t border-border/50 bg-muted/[0.12] px-4 py-2 text-[0.75rem] md:px-5">
          {tc.autotest_status === "queued" && (
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Bot className="h-3.5 w-3.5" /> Автотест: в очереди
            </span>
          )}
          {tc.autotest_status === "running" && (
            <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Claude Code пишет автотест…
            </span>
          )}
          {tc.autotest_status === "generated" && (
            <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
              <Bot className="h-3.5 w-3.5" />
              Автотест готов
              {tc.autotest_mr_url && (
                <a
                  href={tc.autotest_mr_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="font-medium underline underline-offset-2 hover:text-emerald-700 dark:hover:text-emerald-300"
                >
                  MR
                </a>
              )}
              {tc.autotest_summary && <span className="text-foreground/60">— {tc.autotest_summary}</span>}
            </span>
          )}
          {tc.autotest_status === "failed" && (
            <>
              <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                <Bot className="h-3.5 w-3.5" />
                Автотест не создан{tc.autotest_error ? `: ${tc.autotest_error}` : ""}
              </span>
              <button
                className="rounded-md border border-border px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60"
                onClick={(e) => { e.stopPropagation(); autotestMut.mutate(index) }}
                disabled={isBusy || autotestMut.isPending}
              >
                {autotestMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Повторить"}
              </button>
            </>
          )}
          {autotestMut.error && (
            <span className="text-destructive">{(autotestMut.error as Error).message}</span>
          )}
        </div>
      )}

      {!isOpen ? null : (
        <div className="space-y-3 px-4 py-4 md:pl-11">
          {tc.covers && (
            <p className="text-[0.75rem] text-muted-foreground">
              <span className="font-semibold uppercase tracking-wide text-[0.625rem]">Покрывает в ТЗ:</span>{" "}
              <span className="font-mono">{tc.covers}</span>
            </p>
          )}
          <div className="grid gap-3 xl:grid-cols-2">
            <TestCaseSection title="Предусловия">
              <p className="text-sm leading-[1.65] text-foreground/85 [overflow-wrap:anywhere]">
                <RichText text={tc.preconditions} />
              </p>
            </TestCaseSection>

            <div className="space-y-3">
              <TestCaseSection title="Ожидаемый результат" tone="expected">
                <p className="text-sm leading-[1.65] text-foreground/85 [overflow-wrap:anywhere]">
                  <RichText text={tc.expected_result} />
                </p>
              </TestCaseSection>

              {tc.status === "edited" && tc.analyst_text && (
                <TestCaseSection title="Комментарий аналитика" tone="comment">
                  <p className="text-sm leading-[1.65] text-foreground/85 [overflow-wrap:anywhere]">{tc.analyst_text}</p>
                </TestCaseSection>
              )}
            </div>
          </div>

          <TestCaseSection title="Шаги проверки">
            <ol className="space-y-2.5">
              {tc.steps.map((step, si) => (
                <li key={si} className="grid grid-cols-[1.25rem_1fr] gap-x-2">
                  <span className="pt-0.5 text-[0.75rem] font-semibold tabular-nums text-muted-foreground">{si + 1}</span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm leading-[1.6] text-foreground [overflow-wrap:anywhere]">
                      <RichText text={step.action} />
                    </p>
                    <p className="text-[0.8125rem] leading-[1.55] text-muted-foreground [overflow-wrap:anywhere]">
                      <span className="font-medium text-emerald-700 dark:text-emerald-400">→ </span>
                      <RichText text={step.expected} />
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </TestCaseSection>

          <ArtifactsSection tc={tc} projectSlug={projectSlug} featureName={featureName} />

          {tc.status === "pending" && showBugForm && (
            <div className="rounded-xl border border-red-200/70 bg-red-50/40 p-3 dark:border-red-900/40 dark:bg-red-950/10">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-foreground">Создать баг по этому кейсу</p>
                  <p className="mt-1 text-[0.8125rem] text-muted-foreground">Сценарий останется в списке, а вы сможете продолжить ревью без переключения вкладки.</p>
                </div>
                <Button size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={() => { setShowBugForm(false); setBugComment("") }}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Textarea
                placeholder="Краткий комментарий аналитика или контекст для баг-репорта"
                value={bugComment}
                onChange={(e) => setBugComment(e.target.value)}
                className="mt-3 min-h-[5.25rem] text-sm"
                disabled={generateBugMut.isPending}
              />
              {generateBugMut.error && (
                <p className="mt-2 text-[0.75rem] text-destructive">{(generateBugMut.error as Error).message}</p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="destructive" onClick={handleCreateBug} disabled={generateBugMut.isPending}>
                  {generateBugMut.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Создание<AnimatedDots />
                    </>
                  ) : (
                      "Создать баг-репорт"
                  )}
                </Button>
                <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={() => { setShowBugForm(false); setBugComment("") }} disabled={generateBugMut.isPending}>
                  Отмена
                </Button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t pt-3">
            {tc.status === "pending" ? (
              <>
                <Button size="sm" variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900/60 dark:text-emerald-400 dark:hover:bg-emerald-950/30 dark:hover:text-emerald-300" onClick={handleAccept} disabled={isBusy}>
                  Принять
                </Button>
                <Button size="sm" variant="destructive" onClick={() => setShowBugForm(true)} disabled={isBusy}>
                  Создать баг
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={handleReturnToReview} disabled={isBusy}>
                Вернуть в ревью
              </Button>
            )}

            <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground hover:text-red-600" onClick={() => deleteMut.mutate(index)} disabled={isBusy}>
              Удалить кейс
            </Button>
          </div>
        </div>
      )}
    </article>
  )
}

function TestCaseSection({
  title,
  children,
  tone = "default",
  surface = false,
}: {
  title: string
  children: React.ReactNode
  tone?: "default" | "expected" | "comment"
  /** white card instead of the muted tint — for blocks that hold code */
  surface?: boolean
}) {
  return (
    <section
      className={cn(
        "rounded-xl border p-3.5",
        tone === "default" && (surface ? "bg-card" : "bg-muted/20"),
        tone === "expected" && "border-emerald-200/80 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/10",
        tone === "comment" && "border-blue-200/80 bg-blue-50/50 dark:border-blue-900/40 dark:bg-blue-950/10"
      )}
    >
      <p className="mb-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</p>
      {children}
    </section>
  )
}

function SqlRunResults({ result }: { result: SqlExecuteResponse }) {
  return (
    <div className="overflow-hidden rounded-lg border">
      {result.results.map((res, i) => (
        <div key={i} className="border-b px-3 py-2 last:border-b-0">
          <div className="flex items-center gap-2">
            <span className="text-[0.6875rem] font-semibold tabular-nums text-muted-foreground">{i + 1}</span>
            <code className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-muted-foreground" title={res.statement}>
              {res.statement.replace(/\s+/g, " ")}
            </code>
            <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-px font-mono text-[0.625rem] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400">
              {res.status}
            </span>
          </div>
          {res.columns && res.columns.length > 0 && res.rows && (
            <div className="mt-2 overflow-x-auto rounded-md border">
              <table className="w-full font-mono text-[0.6875rem]">
                <thead>
                  <tr className="border-b bg-muted/40">
                    {res.columns.map((col) => (
                      <th key={col} className="whitespace-nowrap px-2 py-1.5 text-left font-semibold text-muted-foreground">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {res.rows.map((row, ri) => (
                    <tr key={ri} className="border-b last:border-b-0">
                      {row.map((cell, ci) => (
                        <td key={ci} className="whitespace-nowrap px-2 py-1">
                          {cell === null ? <span className="italic text-muted-foreground">null</span> : String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {res.truncated && <p className="mt-1 text-[0.625rem] text-muted-foreground">Показаны первые строки — результат обрезан</p>}
        </div>
      ))}
      {result.error && (
        <div className="px-3 py-2">
          <p className="text-[0.6875rem] font-semibold text-destructive">
            Ошибка{result.failed_statement !== null ? ` в выражении ${result.failed_statement + 1}` : ""} — изменения отменены
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words font-mono text-[0.6875rem] text-destructive/90">{result.error}</p>
        </div>
      )}
      {!result.error && (
        <p className="px-3 py-2 text-[0.625rem] text-muted-foreground">Выполнено за {result.duration_ms} мс, изменения применены</p>
      )}
    </div>
  )
}

function countSqlStatements(sql: string) {
  return sql.split(";").filter((s) => s.trim()).length
}

function SqlArtifact({ value }: { value: string }) {
  const { data: dbStatus } = useTestDbStatus()
  const execMut = useExecuteSql()
  const statements = countSqlStatements(value)

  return (
    <div className="space-y-2.5">
      <ArtifactHead
        badge={<TypeBadge label="SQL" className={ARTIFACT_BADGE.SQL} />}
        target={dbStatus?.configured ? dbStatus.database : undefined}
        chips={<MetaChip>{countLabel(statements, ["запрос", "запроса", "запросов"])}</MetaChip>}
        actions={
          dbStatus?.configured ? (
            <Button
              size="sm"
              variant="outline"
              className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900/60 dark:text-emerald-400 dark:hover:bg-emerald-950/30 dark:hover:text-emerald-300"
              onClick={() => execMut.mutate(value)}
              disabled={execMut.isPending}
              title={`Выполнить на тестовой БД ${dbStatus.host ?? ""}/${dbStatus.database ?? ""}`}
            >
              {execMut.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Выполняется
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" />
                  Выполнить в тестовой БД
                </>
              )}
            </Button>
          ) : undefined
        }
      />
      <CodeBlock value={value} />
      {execMut.error && (
        <p className="whitespace-pre-wrap break-words text-[0.75rem] text-destructive">{(execMut.error as Error).message}</p>
      )}
      {execMut.data && <SqlRunResults result={execMut.data} />}
    </div>
  )
}

function KafkaArtifact({ message }: { message: { key: string; value: string } }) {
  return (
    <div className="space-y-2.5">
      <ArtifactHead
        badge={<TypeBadge label="KAFKA" className={ARTIFACT_BADGE.KAFKA} />}
        target="сообщение"
        chips={message.key ? <MetaChip mono title={message.key}>key {message.key}</MetaChip> : undefined}
        actions={message.key ? <CopyButton value={message.key} label="key" /> : undefined}
      />
      <CodeBlock value={formatJsonOrRaw(message.value)} copyValue={message.value} />
    </div>
  )
}

/** WireMock stub: show what is mocked (method + path → status) above the formatted JSON. */
function MockArtifact({ value }: { value: string }) {
  let method: string | null = null
  let path: string | null = null
  let status: number | null = null
  try {
    const parsed = JSON.parse(value)
    method = typeof parsed?.request?.method === "string" ? parsed.request.method : null
    const req = parsed?.request ?? {}
    path = req.urlPath ?? req.url ?? req.urlPattern ?? req.urlPathPattern ?? null
    status = typeof parsed?.response?.status === "number" ? parsed.response.status : null
  } catch {
    // not JSON — show as is
  }

  return (
    <div className="space-y-2.5">
      <ArtifactHead
        badge={<TypeBadge label="MOCK" className={ARTIFACT_BADGE.MOCK} />}
        target={path ? `${method ? `${method} ` : ""}${path}` : "мок внешней системы"}
        chips={status !== null ? <MetaChip>ответ {status}</MetaChip> : undefined}
      />
      <CodeBlock value={formatJsonOrRaw(value)} copyValue={value} />
    </div>
  )
}

function ArtifactsSection({ tc, projectSlug, featureName }: { tc: TestCaseItem; projectSlug: string; featureName: string }) {
  const available = ARTIFACTS.filter((artifact) => tc[artifact.key as keyof TestCaseItem])
  const [active, setActive] = useState<string>(available[0]?.key ?? "")
  if (available.length === 0) return null
  const current = available.some((a) => a.key === active) ? active : available[0].key

  return (
    <TestCaseSection title="Технические артефакты" surface>
      {available.length > 1 && (
        <div className="mb-3 inline-flex h-7 items-center gap-0.5 rounded-lg bg-muted p-[3px]">
          {available.map((artifact) => (
            <button
              key={artifact.key}
              onClick={() => setActive(artifact.key)}
              className={cn(
                "h-full rounded-md px-2.5 text-[0.75rem] font-medium transition-colors",
                current === artifact.key ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {artifact.label}
            </button>
          ))}
        </div>
      )}

      {current === "curl_command" && tc.curl_command && (
        <CurlArtifact value={tc.curl_command} projectSlug={projectSlug} featureName={featureName} />
      )}
      {current === "kafka_message" && tc.kafka_message && <KafkaArtifact message={tc.kafka_message} />}
      {current === "sql_setup" && tc.sql_setup && <SqlArtifact value={tc.sql_setup} />}
      {current === "mock_config" && tc.mock_config && <MockArtifact value={tc.mock_config} />}
    </TestCaseSection>
  )
}

export function TestCasesView({
  projectSlug,
  featureName,
}: {
  projectSlug: string
  featureName: string
}) {
  const { data: tcData, isLoading } = useFeatureTestCases(projectSlug, featureName)
  const runMut = useRunTestCases(projectSlug, featureName)
  const askMut = useAskTestCase(projectSlug, featureName)
  const [askText, setAskText] = useState("")
  const [dismissedAskAt, setDismissedAskAt] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<ReviewFilter>("all")
  const [categoryFilter, setCategoryFilter] = useState<TestCaseCategory | "all">("all")
  const [sortMode, setSortMode] = useState<SortMode>("default")
  const [query, setQuery] = useState("")
  const [openCardKey, setOpenCardKey] = useState<number | null>(null)

  const displayTcs = tcData?.test_cases ?? []
  const isRunning = runMut.isPending || Boolean(tcData?.test_cases_running)
  const generationComplete = !isRunning && Boolean(tcData?.test_cases_run_at)
  const reviewedCount = displayTcs.filter((tc) => tc.status !== "pending").length
  const acceptedCount = displayTcs.filter((tc) => tc.status === "approved").length
  const bugCount = displayTcs.filter((tc) => tc.status === "edited").length

  const filteredItems = sortItems(
    displayTcs
      .map((tc, idx) => ({ tc, idx }))
      .filter(({ tc }) => {
        if (statusFilter !== "all" && tc.status !== statusFilter) return false
        if (categoryFilter !== "all" && tc.category !== categoryFilter) return false
        if (!query.trim()) return true

        const haystack = [
          tc.name,
          tc.preconditions,
          tc.expected_result,
          tc.analyst_text ?? "",
          ...tc.steps.flatMap((step) => [step.action, step.expected]),
        ].join(" ").toLowerCase()

        return haystack.includes(query.trim().toLowerCase())
      }),
    sortMode
  )

  // Cases generated on a tester's ask live in their own section on top, newest first
  const askedItems = filteredItems
    .filter(({ tc }) => tc.origin === "ask")
    .sort((a, b) => b.idx - a.idx)
  const systemItems = filteredItems.filter(({ tc }) => tc.origin !== "ask")

  const grouped = (categoryFilter === "all"
    ? (["validation", "positive", "negative", "edge_case"] as TestCaseCategory[])
    : [categoryFilter]
  )
    .map((category) => ({
      category,
      items: systemItems.filter(({ tc }) => tc.category === category),
    }))
    .filter((group) => group.items.length > 0)

  function advanceToNextPending(currentIndex: number) {
    const next = filteredItems.find(({ idx, tc }) => idx !== currentIndex && tc.status === "pending")
    setOpenCardKey(next?.idx ?? null)
  }

  function openCaseByName(name: string) {
    const idx = displayTcs.findIndex((tc) => tc.name === name)
    if (idx < 0) return
    // Drop filters so the target card is guaranteed to be rendered
    setStatusFilter("all")
    setCategoryFilter("all")
    setQuery("")
    setOpenCardKey(idx)
    requestAnimationFrame(() => {
      document.getElementById(`tc-card-${idx}`)?.scrollIntoView({ behavior: "smooth", block: "center" })
    })
  }

  function handleAsk() {
    const text = askText.trim()
    if (text.length < 3 || isRunning || askMut.isPending) return
    askMut.mutate(text, {
      onSuccess: () => {
        setAskText("")
        setDismissedAskAt(null)
      },
    })
  }

  const pendingCount = displayTcs.length - reviewedCount
  const categoryCounts = (["validation", "positive", "negative", "edge_case"] as TestCaseCategory[]).map((category) => ({
    category,
    count: displayTcs.filter((tc) => tc.category === category).length,
  }))

  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-xl border bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <h2 className="text-base font-semibold">Ревью тест-кейсов</h2>
          <StatStrip
            className="flex-1"
            items={[
              { value: `${reviewedCount} / ${displayTcs.length}`, label: "просмотрено" },
              { value: acceptedCount, label: "принято", tone: acceptedCount > 0 ? "success" : "default" },
              { value: bugCount, label: "с багом", tone: bugCount > 0 ? "danger" : "default" },
            ]}
          />
          {!generationComplete ? (
            <Button size="sm" onClick={() => runMut.mutate()} disabled={isRunning}>
              {isRunning ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Генерация<AnimatedDots />
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" />
                  Сгенерировать
                </>
              )}
            </Button>
          ) : (
            <Badge variant="outline" className="border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-400">
              <Check className="h-3 w-3" />
              сгенерировано
            </Badge>
          )}
        </div>

        {displayTcs.length > 0 && (
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${(reviewedCount / displayTcs.length) * 100}%` }} />
          </div>
        )}

        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
          onSubmit={(e) => {
            e.preventDefault()
            handleAsk()
          }}
        >
          <div className="relative flex-1">
            <Sparkles className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={askText}
              onChange={(e) => setAskText(e.target.value)}
              placeholder="Нужен кейс на пункт ТЗ — например: «негативные сценарии для шага проверки тарифа»"
              className="pl-8 text-sm"
              disabled={askMut.isPending}
            />
          </div>
          <Button size="sm" variant="outline" type="submit" disabled={isRunning || askMut.isPending || askText.trim().length < 3}>
            {askMut.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Отправка<AnimatedDots />
              </>
            ) : (
              "Попросить кейс"
            )}
          </Button>
        </form>
      </section>

      {askMut.error && (
        <p className="text-[0.8125rem] text-destructive">{(askMut.error as Error).message}</p>
      )}

      {isRunning && displayTcs.length > 0 && (
        <p className="flex items-center gap-2 text-[0.8125rem] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Генерация выполняется — новые кейсы появятся в списке<AnimatedDots />
        </p>
      )}

      {tcData?.last_ask_message && tcData.last_ask_at !== dismissedAskAt && !isRunning && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-blue-200/80 bg-blue-50/50 px-3 py-2 dark:border-blue-900/40 dark:bg-blue-950/10">
          <div className="min-w-0">
            <p className="text-[0.8125rem] leading-[1.6] text-foreground/85">
              <span className="font-semibold">Ответ на запрос кейса:</span> {tcData.last_ask_message}
            </p>
            {(() => {
              const refs = (tcData.last_ask_covered_by ?? []).filter((name) =>
                displayTcs.some((tc) => tc.name === name)
              )
              if (refs.length === 0) return null
              return (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {refs.map((name) => (
                    <button
                      key={name}
                      onClick={() => openCaseByName(name)}
                      className="max-w-full truncate rounded-md border border-blue-200/80 bg-background px-2 py-1 text-left text-[0.75rem] text-blue-700 transition-colors hover:border-blue-300 hover:bg-blue-100/50 dark:border-blue-900/50 dark:text-blue-300 dark:hover:bg-blue-950/30"
                      title={name}
                    >
                      {name}
                    </button>
                  ))}
                </div>
              )
            })()}
          </div>
          <button
            className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => setDismissedAskAt(tcData.last_ask_at)}
            aria-label="Скрыть сообщение"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {displayTcs.length > 0 && (
        <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-2 rounded-lg bg-background/95 px-1 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <Segmented<ReviewFilter>
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: "all", label: "Все", count: displayTcs.length },
              { value: "pending", label: "Не просмотрено", count: pendingCount },
              { value: "approved", label: "Принято", count: acceptedCount },
              { value: "edited", label: "С багом", count: bugCount },
            ]}
          />
          <FilterSelect<TestCaseCategory | "all">
            ariaLabel="Категория"
            value={categoryFilter}
            onChange={setCategoryFilter}
            options={[
              { value: "all", label: "Все категории" },
              ...categoryCounts.map(({ category, count }) => ({ value: category, label: `${CATEGORY_LABEL[category]} · ${count}` })),
            ]}
          />
          <FilterSelect<SortMode>
            ariaLabel="Сортировка"
            value={sortMode}
            onChange={setSortMode}
            options={[
              { value: "default", label: "По умолчанию" },
              { value: "unreviewed", label: "Сначала не просмотренные" },
              { value: "with_bug", label: "Сначала с багом" },
              { value: "longest", label: "Сначала длинные" },
            ]}
          />
          <div className="relative ml-auto min-w-[15rem]">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название, шаг или ожидание" className="h-7 pl-8 text-xs" />
          </div>
          <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={() => setOpenCardKey(null)}>
            Свернуть все
          </Button>
        </div>
      )}

      {runMut.error && (
        <p className="text-[0.8125rem] text-destructive">{(runMut.error as Error).message}</p>
      )}

      {(isLoading || isRunning) && displayTcs.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!isLoading && !isRunning && displayTcs.length === 0 && (
        <div className="rounded-2xl border border-dashed px-4 py-14 text-center">
          <p className="text-sm font-medium">Тест-кейсы еще не сгенерированы</p>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">
            Сначала сгенерируйте сценарии, затем здесь появится рабочая зона для быстрого ревью.
          </p>
        </div>
      )}

      {displayTcs.length > 0 && filteredItems.length === 0 && (
        <div className="rounded-2xl border border-dashed px-4 py-12 text-center">
          <p className="text-sm font-medium">Ничего не найдено</p>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">Попробуйте сбросить фильтры или изменить поисковый запрос.</p>
        </div>
      )}

      <div className="space-y-5">
        {askedItems.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Сгенерировано по запросу
              </p>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] text-muted-foreground">
                {askedItems.length}
              </span>
            </div>

            <div className="space-y-1.5">
              {askedItems.map(({ tc, idx }) => (
                <TestCaseCard
                  key={idx}
                  tc={tc}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                  isOpen={openCardKey === idx}
                  onToggle={() => setOpenCardKey((current) => (current === idx ? null : idx))}
                  onResolved={advanceToNextPending}
                />
              ))}
            </div>
          </section>
        )}

        {grouped.map(({ category, items }) => (
          <section key={category} className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{CATEGORY_LABEL[category]}</p>
                <span className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] text-muted-foreground">{items.length}</span>
              </div>
            </div>

            <div className="space-y-1.5">
              {items.map(({ tc, idx }) => (
                <TestCaseCard
                  key={idx}
                  tc={tc}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                  isOpen={openCardKey === idx}
                  onToggle={() => setOpenCardKey((current) => (current === idx ? null : idx))}
                  onResolved={advanceToNextPending}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
