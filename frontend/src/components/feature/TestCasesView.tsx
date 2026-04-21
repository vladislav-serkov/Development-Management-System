import { useState } from "react"
import { useFeatureTestCases, usePatchTestCase, useDeleteTestCase, useRunTestCases } from "@/hooks/useTestCases"
import { useGenerateBug } from "@/hooks/useBugs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { Check, ChevronDown, ChevronUp, Copy, Loader2, Play, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { TestCaseItem, TestCaseCategory } from "@/types/api"

const ARTIFACTS = [
  { key: "curl_command", label: "cURL" },
  { key: "kafka_message", label: "MESSAGE" },
  { key: "sql_setup", label: "SQL" },
  { key: "mock_config", label: "MOCKS" },
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

function ReviewChip({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      className={cn(
        "rounded-full border px-3 py-1 text-[0.6875rem] font-medium transition-colors",
        active
          ? "border-foreground/10 bg-foreground text-background"
          : "border-border bg-background text-muted-foreground hover:border-foreground/15 hover:text-foreground"
      )}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function ReviewStat({
  label,
  value,
  tone = "default",
}: {
  label: string
  value: string
  tone?: "default" | "accent" | "danger"
}) {
  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2",
        tone === "accent" && "border-emerald-200/80 bg-emerald-50/70 dark:border-emerald-900/40 dark:bg-emerald-950/10",
        tone === "danger" && "border-red-200/80 bg-red-50/70 dark:border-red-900/40 dark:bg-red-950/10",
        tone === "default" && "border-border bg-background"
      )}
    >
      <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  )
}

function PriorityBadge({ priority }: { priority: TestCaseItem["priority"] }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-[0.12em]",
        priority === "high" && "bg-red-50 text-red-600 ring-1 ring-red-200 dark:bg-red-950/20 dark:text-red-300 dark:ring-red-900/50",
        priority === "medium" && "bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/20 dark:text-amber-300 dark:ring-amber-900/50",
        priority === "low" && "bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700"
      )}
    >
      {PRIORITY_LABEL[priority]}
    </span>
  )
}

function TestCaseStatusBadge({ status }: { status: TestCaseItem["status"] }) {
  const label = status === "approved" ? "Принято" : status === "edited" ? "С багом" : "Не просмотрено"

  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-1 text-[0.625rem] font-semibold uppercase tracking-[0.12em]",
        status === "approved" && "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-300 dark:ring-emerald-900/50",
        status === "edited" && "bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-950/20 dark:text-red-300 dark:ring-red-900/50",
        status === "pending" && "bg-muted text-muted-foreground ring-1 ring-border"
      )}
    >
      {label}
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
  const [showBugForm, setShowBugForm] = useState(false)
  const [bugComment, setBugComment] = useState("")
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [copiedField, setCopiedField] = useState<string | null>(null)

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
      className={cn(
        "overflow-hidden rounded-2xl border bg-card transition-all",
        isOpen ? "border-foreground/15 shadow-sm ring-1 ring-foreground/6" : "border-border hover:border-foreground/12 hover:shadow-sm"
      )}
    >
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3.5 md:px-5",
          isOpen && "border-b border-border/70 bg-muted/[0.18]"
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
              <p className={cn("text-[0.875rem] font-semibold leading-[1.5] text-foreground", !isOpen && "line-clamp-2")}>
                <RichText text={tc.name} />
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground">
                <span>{tc.steps.length} шагов</span>
                <span>{artifactCount} артефактов</span>
                <span>{CATEGORY_LABEL[tc.category]}</span>
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <PriorityBadge priority={tc.priority} />
              <TestCaseStatusBadge status={tc.status} />
            </div>
          </div>
        </button>

        <div className="hidden items-center gap-2 lg:flex">
          {tc.status === "pending" ? (
            <>
              <Button size="sm" variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800" onClick={handleAccept} disabled={isBusy}>
                Принять
              </Button>
              <Button size="sm" variant="outline" className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800" onClick={() => { setShowBugForm(true); if (!isOpen) onToggle() }} disabled={isBusy}>
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

      {!isOpen ? null : (
        <div className="space-y-4 px-4 py-4 md:px-5">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)]">
            <TestCaseSection title="Предусловия">
              <p className="text-sm leading-[1.65] text-foreground/85">
                <RichText text={tc.preconditions} />
              </p>
            </TestCaseSection>

            <div className="space-y-4">
              <TestCaseSection title="Ожидаемый результат" tone="expected">
                <p className="text-sm leading-[1.65] text-foreground/85">
                  <RichText text={tc.expected_result} />
                </p>
              </TestCaseSection>

              {tc.status === "edited" && tc.analyst_text && (
                <TestCaseSection title="Комментарий аналитика" tone="comment">
                  <p className="text-sm leading-[1.65] text-foreground/85">{tc.analyst_text}</p>
                </TestCaseSection>
              )}
            </div>
          </div>

          <TestCaseSection title="Шаги проверки">
            <div className="space-y-3">
              {tc.steps.map((step, si) => (
                <div key={si} className="rounded-xl border border-border/70 bg-background px-4 py-3">
                  <div className="grid grid-cols-[auto_1fr] gap-x-3">
                    <span className="pt-0.5 text-[0.75rem] font-semibold tabular-nums text-muted-foreground">{si + 1}</span>
                    <div className="space-y-3">
                      <p className="text-sm leading-[1.65] text-foreground">
                        <RichText text={step.action} />
                      </p>
                      <div className="rounded-xl bg-muted/50 px-3 py-2.5">
                        <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Ожидаемый результат шага</p>
                        <p className="mt-1.5 text-sm leading-[1.6] text-foreground/85">
                          <RichText text={step.expected} />
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </TestCaseSection>

          {artifactCount > 0 && (
            <TestCaseSection title="Технические артефакты">
              <div className="flex flex-wrap items-center gap-1.5">
                {ARTIFACTS.filter((artifact) => tc[artifact.key as keyof TestCaseItem]).map((artifact) => (
                  <button
                    key={artifact.key}
                    className={cn(
                      "rounded-full border px-3 py-1 text-[0.6875rem] font-medium transition-colors",
                      activeArtifact === artifact.key
                        ? "border-foreground bg-foreground text-background"
                        : "border-border bg-background text-muted-foreground hover:text-foreground"
                    )}
                    onClick={() => {
                      setActiveArtifact(activeArtifact === artifact.key ? null : artifact.key)
                      setCopiedField(null)
                    }}
                  >
                    {artifact.label}
                  </button>
                ))}
              </div>

              {!activeArtifact && artifactCount === 1 && (
                <div className="mt-3">
                  {ARTIFACTS.filter((artifact) => tc[artifact.key as keyof TestCaseItem]).map((artifact) => {
                    if (!tc[artifact.key as keyof TestCaseItem]) return null

                    if (artifact.key === "kafka_message" && tc.kafka_message) {
                      return (
                        <div key={artifact.key} className="space-y-2.5">
                          <TestCaseInlineArtifact
                            label="Kafka key"
                            value={tc.kafka_message.key}
                            copied={copiedField === "key"}
                            onCopy={() => {
                              navigator.clipboard.writeText(tc.kafka_message!.key)
                              setCopiedField("key")
                              setTimeout(() => setCopiedField(null), 1500)
                            }}
                          />
                          <TestCaseArtifact
                            label="Kafka value"
                            value={formatJsonOrRaw(tc.kafka_message.value)}
                            copied={copiedField === "value"}
                            onCopy={() => {
                              navigator.clipboard.writeText(tc.kafka_message!.value)
                              setCopiedField("value")
                              setTimeout(() => setCopiedField(null), 1500)
                            }}
                          />
                        </div>
                      )
                    }

                    return (
                      <TestCaseArtifact
                        key={artifact.key}
                        label={artifact.label}
                        value={tc[artifact.key as keyof TestCaseItem] as string}
                        copied={copiedField === artifact.key}
                        onCopy={() => {
                          navigator.clipboard.writeText(tc[artifact.key as keyof TestCaseItem] as string)
                          setCopiedField(artifact.key)
                          setTimeout(() => setCopiedField(null), 1500)
                        }}
                      />
                    )
                  })}
                </div>
              )}

              {activeArtifact && tc[activeArtifact as keyof TestCaseItem] && (
                <div className="mt-3">
                  {activeArtifact === "kafka_message" && tc.kafka_message ? (
                    <div className="space-y-2.5">
                      <TestCaseInlineArtifact
                        label="Kafka key"
                        value={tc.kafka_message.key}
                        copied={copiedField === "key"}
                        onCopy={() => {
                          navigator.clipboard.writeText(tc.kafka_message!.key)
                          setCopiedField("key")
                          setTimeout(() => setCopiedField(null), 1500)
                        }}
                      />
                      <TestCaseArtifact
                        label="Kafka value"
                        value={formatJsonOrRaw(tc.kafka_message.value)}
                        copied={copiedField === "value"}
                        onCopy={() => {
                          navigator.clipboard.writeText(tc.kafka_message!.value)
                          setCopiedField("value")
                          setTimeout(() => setCopiedField(null), 1500)
                        }}
                      />
                    </div>
                  ) : (
                    <TestCaseArtifact
                      label={ARTIFACTS.find((artifact) => artifact.key === activeArtifact)?.label ?? "Artifact"}
                      value={tc[activeArtifact as keyof TestCaseItem] as string}
                      copied={copiedField === activeArtifact}
                      onCopy={() => {
                        navigator.clipboard.writeText(tc[activeArtifact as keyof TestCaseItem] as string)
                        setCopiedField(activeArtifact)
                        setTimeout(() => setCopiedField(null), 1500)
                      }}
                    />
                  )}
                </div>
              )}
            </TestCaseSection>
          )}

          {tc.status === "pending" && showBugForm && (
            <div className="rounded-2xl border border-red-200/70 bg-red-50/40 p-4 dark:border-red-900/40 dark:bg-red-950/10">
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

          <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-4">
            {tc.status === "pending" ? (
              <>
                <Button size="sm" variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800" onClick={handleAccept} disabled={isBusy}>
                  Принять
                </Button>
                <Button size="sm" variant="outline" className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800" onClick={() => setShowBugForm(true)} disabled={isBusy}>
                  Создать баг
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={handleReturnToReview} disabled={isBusy}>
                Вернуть в ревью
              </Button>
            )}

            <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-red-600" onClick={() => deleteMut.mutate(index)} disabled={isBusy}>
              Удалить
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
}: {
  title: string
  children: React.ReactNode
  tone?: "default" | "expected" | "comment"
}) {
  return (
    <section
      className={cn(
        "rounded-2xl border p-4",
        tone === "default" && "border-border/70 bg-muted/[0.12]",
        tone === "expected" && "border-emerald-200/80 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/10",
        tone === "comment" && "border-blue-200/80 bg-blue-50/50 dark:border-blue-900/40 dark:bg-blue-950/10"
      )}
    >
      <p className="mb-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</p>
      {children}
    </section>
  )
}

function TestCaseArtifact({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string
  value: string
  copied: boolean
  onCopy: () => void
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
      <div className="border-b border-slate-800 px-3 py-2">
        <span className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</span>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words px-3 py-3 text-[0.75rem] font-mono leading-6 text-slate-100">
        <code>{value}</code>
      </pre>
      <button
        onClick={onCopy}
        className="absolute right-2 top-2 rounded-md bg-slate-700 p-1.5 text-slate-300 transition-opacity hover:bg-slate-600 opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
        title="Копировать"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

function TestCaseInlineArtifact({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string
  value: string
  copied: boolean
  onCopy: () => void
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950 px-3 py-2.5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</p>
          <code className="mt-1 block overflow-x-auto whitespace-pre-wrap break-all text-[0.75rem] font-mono leading-6 text-slate-100">
            {value}
          </code>
        </div>
        <button onClick={onCopy} className="shrink-0 self-start rounded-md bg-slate-700 p-1.5 text-slate-300 transition-colors hover:bg-slate-600" title="Копировать">
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
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

  const grouped = (categoryFilter === "all"
    ? (["validation", "positive", "negative", "edge_case"] as TestCaseCategory[])
    : [categoryFilter]
  )
    .map((category) => ({
      category,
      items: filteredItems.filter(({ tc }) => tc.category === category),
    }))
    .filter((group) => group.items.length > 0)

  function advanceToNextPending(currentIndex: number) {
    const next = filteredItems.find(({ idx, tc }) => idx !== currentIndex && tc.status === "pending")
    setOpenCardKey(next?.idx ?? null)
  }

  return (
    <div className="space-y-5">
      <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-baseline gap-2.5">
              <h2 className="text-lg font-semibold">Ревью тест-кейсов</h2>
              <span className="text-sm text-muted-foreground">
                Просмотрено {reviewedCount}/{displayTcs.length || 0}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Быстрый разбор сценариев: принять, отправить в баг, вернуться к деталям только когда это действительно нужно.
            </p>
          </div>

          {!generationComplete ? (
            <Button size="sm" variant="outline" className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800" onClick={() => runMut.mutate()} disabled={isRunning}>
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
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/10 dark:text-emerald-300">
              <Check className="h-3.5 w-3.5" />
              Сгенерировано
            </span>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ReviewStat label="Сгенерировано" value={String(displayTcs.length)} />
          <ReviewStat label="Принято" value={String(acceptedCount)} tone={acceptedCount > 0 ? "accent" : "default"} />
          <ReviewStat label="С багом" value={String(bugCount)} tone={bugCount > 0 ? "danger" : "default"} />
          <ReviewStat label="Не просмотрено" value={String(Math.max(displayTcs.length - reviewedCount, 0))} />
        </div>
      </div>

      {displayTcs.length > 0 && (
        <div className="sticky top-0 z-10 -mx-4 rounded-2xl border border-border/70 bg-background/95 px-4 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <ReviewChip active={statusFilter === "all"} onClick={() => setStatusFilter("all")}>Все</ReviewChip>
                <ReviewChip active={statusFilter === "pending"} onClick={() => setStatusFilter("pending")}>Не просмотрено</ReviewChip>
                <ReviewChip active={statusFilter === "approved"} onClick={() => setStatusFilter("approved")}>Принято</ReviewChip>
                <ReviewChip active={statusFilter === "edited"} onClick={() => setStatusFilter("edited")}>С багом</ReviewChip>
              </div>

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="relative min-w-[15rem] flex-1">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию, шагам и ожиданиям" className="pl-8 text-sm" />
                </div>

                <select
                  value={sortMode}
                  onChange={(e) => setSortMode(e.target.value as SortMode)}
                  className="h-8 rounded-lg border border-border bg-background px-2.5 text-sm text-foreground outline-none"
                >
                  <option value="default">По умолчанию</option>
                  <option value="unreviewed">Сначала не просмотренные</option>
                  <option value="with_bug">Сначала с багом</option>
                  <option value="longest">Сначала длинные</option>
                </select>

                <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={() => setOpenCardKey(null)}>
                  Свернуть все
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <ReviewChip active={categoryFilter === "all"} onClick={() => setCategoryFilter("all")}>Все категории</ReviewChip>
              {(["validation", "positive", "negative", "edge_case"] as TestCaseCategory[]).map((category) => (
                <ReviewChip key={category} active={categoryFilter === category} onClick={() => setCategoryFilter(category)}>
                  {CATEGORY_LABEL[category]}
                </ReviewChip>
              ))}
            </div>
          </div>
        </div>
      )}

      {displayTcs.length > 0 && (
        <div className="h-1 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-foreground transition-all duration-500" style={{ width: `${(reviewedCount / displayTcs.length) * 100}%` }} />
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

      <div className="space-y-6">
        {grouped.map(({ category, items }) => (
          <section key={category} className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{CATEGORY_LABEL[category]}</p>
                <span className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] text-muted-foreground">{items.length}</span>
              </div>
            </div>

            <div className="space-y-2.5">
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
