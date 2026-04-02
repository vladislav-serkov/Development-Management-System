import { useState } from "react"
import { useFeatureTestCases, usePatchTestCase, useDeleteTestCase, useRunTestCases } from "@/hooks/useTestCases"
import { useGenerateBug } from "@/hooks/useBugs"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { Check, Play, Loader2, Copy } from "lucide-react"
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

function formatJsonOrRaw(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

function RichText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") ? (
          <code key={i} className="px-1 py-px rounded bg-muted text-[12px] font-mono">
            {part.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}

function TestCaseCard({
  tc,
  index,
  projectSlug,
  featureName,
  onBugCreated,
}: {
  tc: TestCaseItem
  index: number
  projectSlug: string
  featureName: string
  onBugCreated?: () => void
}) {
  const patchMut = usePatchTestCase(projectSlug, featureName)
  const deleteMut = useDeleteTestCase(projectSlug, featureName)
  const generateBugMut = useGenerateBug(projectSlug, featureName)
  const [open, setOpen] = useState(false)
  const [showBugForm, setShowBugForm] = useState(false)
  const [bugComment, setBugComment] = useState("")
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [copiedField, setCopiedField] = useState<string | null>(null)

  const isBusy = patchMut.isPending || deleteMut.isPending || generateBugMut.isPending
  const resolved = tc.status === "approved" || tc.status === "edited"

  return (
    <div
      className={cn(
        "rounded-lg border bg-card overflow-hidden transition-all hover:shadow-sm",
        resolved ? "border-border/60" : "border-border",
      )}
    >
      <div className="flex">
        {/* Status stripe */}
        <div className={cn(
          "w-1 shrink-0",
          tc.status === "approved" && "bg-emerald-500",
          tc.status === "edited" && "bg-red-500",
          tc.status === "pending" && "bg-transparent",
        )} />

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div
            className="flex items-start gap-3 p-4 cursor-pointer"
            onClick={() => setOpen(!open)}
          >
            {/* Checkbox */}
            <button
              className={cn(
                "mt-[3px] shrink-0 w-4 h-4 rounded-[4px] border flex items-center justify-center transition-colors",
                resolved
                  ? "bg-emerald-500 border-emerald-500 text-white"
                  : "border-muted-foreground/25 hover:border-muted-foreground/50",
              )}
              onClick={(e) => {
                e.stopPropagation()
                if (!resolved) patchMut.mutate({ tcIndex: index, status: "approved" })
                else patchMut.mutate({ tcIndex: index, status: "pending", analyst_text: null })
              }}
              disabled={isBusy}
            >
              {resolved && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
            </button>

            {/* Name */}
            <div className="flex-1 min-w-0">
              <p className={cn(
                "text-[13px] leading-[1.65]",
                !open && "line-clamp-2",
                resolved && "text-muted-foreground",
              )}>
                <RichText text={tc.name} />
              </p>
            </div>

            {/* Status label */}
            {tc.status === "edited" && (
              <span className="shrink-0 text-[11px] text-red-600 dark:text-red-400 font-medium">баг</span>
            )}
            {tc.status === "approved" && (
              <span className="shrink-0 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">принято</span>
            )}
          </div>

          {/* Expanded */}
          {open && (
            <div className="px-4 pb-4 space-y-3 ml-7">
              {/* Preconditions */}
              <div className="rounded-md bg-muted/50 p-3.5">
                <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-1.5">
                  Предусловия
                </p>
                <p className="text-[13px] leading-[1.65] text-foreground/80">
                  <RichText text={tc.preconditions} />
                </p>
              </div>

              {/* Steps */}
              {tc.steps.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-2 px-1">
                    Шаги
                  </p>
                  <div className="space-y-2">
                    {tc.steps.map((step, si) => (
                      <div key={si} className="grid grid-cols-[auto_1fr] gap-x-2.5 text-[13px]">
                        <span className="text-muted-foreground/50 font-medium tabular-nums pt-px">{si + 1}.</span>
                        <div className="space-y-0.5">
                          <p className="leading-[1.65]"><RichText text={step.action} /></p>
                          <p className="text-muted-foreground leading-[1.65]">→ <RichText text={step.expected} /></p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expected result */}
              <div className="rounded-md bg-emerald-50/60 dark:bg-emerald-950/15 border border-emerald-100/80 dark:border-emerald-900/30 p-3.5">
                <p className="text-[11px] font-medium text-emerald-700/60 dark:text-emerald-400/60 uppercase tracking-wider mb-1.5">
                  Ожидаемый результат
                </p>
                <p className="text-[13px] leading-[1.65] text-foreground/80">
                  <RichText text={tc.expected_result} />
                </p>
              </div>

              {/* Artifacts */}
              {(() => {
                const available = ARTIFACTS.filter(a => tc[a.key as keyof TestCaseItem])
                if (available.length === 0) return null
                return (
                  <div>
                    <div className="flex items-center gap-1.5">
                      {available.map(a => (
                        <button
                          key={a.key}
                          onClick={(e) => { e.stopPropagation(); setActiveArtifact(activeArtifact === a.key ? null : a.key); setCopiedField(null) }}
                          className={cn(
                            "px-2.5 py-1 text-[11px] font-medium rounded-md border transition-colors",
                            activeArtifact === a.key
                              ? "bg-foreground text-background border-foreground"
                              : "bg-card text-muted-foreground border-border hover:bg-muted"
                          )}
                        >
                          {a.label}
                        </button>
                      ))}
                    </div>
                    {activeArtifact && tc[activeArtifact as keyof TestCaseItem] && (
                      <div className="mt-1.5">
                        {activeArtifact === "kafka_message" && tc.kafka_message ? (
                          <div className="space-y-1.5">
                            {/* Key block */}
                            <div className="relative group/key">
                              <div className="p-3.5 rounded-md bg-slate-900 text-slate-100 text-xs font-mono dark:bg-slate-950">
                                <span className="text-slate-400">key: </span>{tc.kafka_message.key}
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(tc.kafka_message!.key)
                                  setCopiedField("key")
                                  setTimeout(() => setCopiedField(null), 1500)
                                }}
                                className="absolute top-2 right-2 p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 opacity-100 sm:opacity-0 sm:group-hover/key:opacity-100 transition-opacity"
                                title="Копировать key"
                              >
                                {copiedField === "key" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                              </button>
                            </div>
                            {/* Value block */}
                            <div className="relative group/value">
                              <pre className="p-3.5 rounded-md bg-slate-900 text-slate-100 text-xs font-mono overflow-x-auto whitespace-pre-wrap dark:bg-slate-950">
                                <code>{formatJsonOrRaw(tc.kafka_message.value)}</code>
                              </pre>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(tc.kafka_message!.value)
                                  setCopiedField("value")
                                  setTimeout(() => setCopiedField(null), 1500)
                                }}
                                className="absolute top-2 right-2 p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 opacity-100 sm:opacity-0 sm:group-hover/value:opacity-100 transition-opacity"
                                title="Копировать value"
                              >
                                {copiedField === "value" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="relative group">
                            <pre className="p-3.5 rounded-md bg-slate-900 text-slate-100 text-xs font-mono overflow-x-auto whitespace-pre-wrap dark:bg-slate-950">
                              {tc[activeArtifact as keyof TestCaseItem] as string}
                            </pre>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(tc[activeArtifact as keyof TestCaseItem] as string)
                                setCopiedField(activeArtifact)
                                setTimeout(() => setCopiedField(null), 1500)
                              }}
                              className="absolute top-2 right-2 p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity"
                              title="Копировать"
                            >
                              {copiedField === activeArtifact ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })()}

              {/* Analyst comment */}
              {tc.status === "edited" && tc.analyst_text && (
                <div className="rounded-md bg-blue-50/60 dark:bg-blue-950/20 border border-blue-100/80 dark:border-blue-900/30 p-3.5">
                  <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-1.5">
                    Комментарий
                  </p>
                  <p className="text-[13px] leading-[1.65] text-foreground/80">{tc.analyst_text}</p>
                </div>
              )}

              {/* Actions */}
              {tc.status === "pending" && !showBugForm && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-emerald-500 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ tcIndex: index, status: "approved" }) }}
                    disabled={isBusy}
                  >
                    Принять
                  </button>
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-red-500 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors flex items-center gap-1.5"
                    onClick={(e) => { e.stopPropagation(); setShowBugForm(true) }}
                    disabled={isBusy}
                  >
                    {generateBugMut.isPending ? (
                      <><Loader2 className="h-3 w-3 animate-spin" />Генерация<AnimatedDots /></>
                    ) : (
                      "Баг"
                    )}
                  </button>
                  <button
                    className="text-[12px] px-3 py-1.5 rounded-md text-muted-foreground hover:text-red-500 transition-colors"
                    onClick={(e) => { e.stopPropagation(); deleteMut.mutate(index) }}
                    disabled={isBusy}
                  >
                    Удалить
                  </button>
                </div>
              )}

              {tc.status === "pending" && showBugForm && (
                <div className="space-y-2.5 pt-1" onClick={e => e.stopPropagation()}>
                  <Textarea
                    placeholder="Комментарий к багу (необязательно)..."
                    value={bugComment}
                    onChange={(e) => setBugComment(e.target.value)}
                    className="text-[13px] min-h-[56px]"
                    disabled={generateBugMut.isPending}
                  />
                  {generateBugMut.error && (
                    <p className="text-[12px] text-destructive">{(generateBugMut.error as Error).message}</p>
                  )}
                  <div className="flex items-center gap-2">
                    <button
                      className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-border text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
                      onClick={() => {
                        generateBugMut.mutate(
                          { tcIndex: index, analystText: bugComment || null },
                          {
                            onSuccess: () => {
                              patchMut.mutate({ tcIndex: index, status: "edited", analyst_text: bugComment || null })
                              setShowBugForm(false)
                              setBugComment("")
                              onBugCreated?.()
                            },
                          }
                        )
                      }}
                      disabled={generateBugMut.isPending}
                    >
                      {generateBugMut.isPending ? (
                        <><Loader2 className="h-3 w-3 animate-spin" />Генерация<AnimatedDots /></>
                      ) : (
                        "Создать баг-репорт"
                      )}
                    </button>
                    <button
                      className="text-[12px] px-3 py-1.5 rounded-md text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => { setShowBugForm(false); setBugComment("") }}
                      disabled={generateBugMut.isPending}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              )}

              {resolved && (
                <button
                  className="text-[12px] text-muted-foreground/60 hover:text-foreground transition-colors pt-1"
                  onClick={(e) => { e.stopPropagation(); patchMut.mutate({ tcIndex: index, status: "pending", analyst_text: null }) }}
                  disabled={isBusy}
                >
                  Вернуть в ожидание
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function TestCasesView({
  projectSlug,
  featureName,
  onBugCreated,
}: {
  projectSlug: string
  featureName: string
  onBugCreated?: () => void
}) {
  const { data: tcData, isLoading } = useFeatureTestCases(projectSlug, featureName)
  const runMut = useRunTestCases(projectSlug, featureName)

  const displayTcs = tcData?.test_cases ?? []
  const isRunning = runMut.isPending || tcData?.test_cases_status === "running"
  const alreadyDone = tcData?.test_cases_status === "done"

  const resolvedCount = displayTcs.filter(tc => tc.status !== "pending").length

  const categories: TestCaseCategory[] = ["validation", "positive", "negative", "edge_case"]
  const grouped = categories
    .map(cat => ({
      category: cat,
      items: displayTcs
        .map((tc, idx) => ({ tc, idx }))
        .filter(({ tc }) => tc.category === cat),
    }))
    .filter(g => g.items.length > 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-base font-medium">Тест-кейсы</h2>
          {displayTcs.length > 0 && (
            <span className="text-[13px] text-muted-foreground tabular-nums">
              {resolvedCount} из {displayTcs.length}
            </span>
          )}
        </div>
        {!alreadyDone ? (
          <button
            className={cn(
              "text-[12px] font-medium px-3.5 py-1.5 rounded-md transition-colors",
              isRunning
                ? "text-muted-foreground"
                : "border border-emerald-500 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30",
            )}
            onClick={() => runMut.mutate()}
            disabled={isRunning}
          >
            {isRunning ? (
              <span className="flex items-center gap-1.5"><Loader2 className="h-3 w-3 animate-spin" />Генерация<AnimatedDots /></span>
            ) : (
              <span className="flex items-center gap-1.5"><Play className="h-3 w-3" />Сгенерировать</span>
            )}
          </button>
        ) : displayTcs.length > 0 ? (
          <span className="text-[12px] text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
            <Check className="h-3.5 w-3.5" />Завершён
          </span>
        ) : null}
      </div>

      {/* Progress */}
      {displayTcs.length > 0 && (
        <div className="h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-500"
            style={{ width: `${(resolvedCount / displayTcs.length) * 100}%` }}
          />
        </div>
      )}

      {/* Error */}
      {runMut.error && (
        <p className="text-[13px] text-destructive">{(runMut.error as Error).message}</p>
      )}

      {/* Loading */}
      {(isLoading || isRunning) && displayTcs.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isRunning && displayTcs.length === 0 && (
        <p className="text-[13px] text-muted-foreground text-center py-16">
          Нет данных
        </p>
      )}

      {/* Groups */}
      <div className="space-y-6">
        {grouped.map(({ category, items }) => (
          <div key={category}>
            <p className="text-[11px] font-medium text-muted-foreground/60 uppercase tracking-wider mb-2.5 px-1">
              {CATEGORY_LABEL[category]} <span className="text-muted-foreground/40 ml-1">{items.length}</span>
            </p>
            <div className="space-y-2">
              {items.map(({ tc, idx }) => (
                <TestCaseCard
                  key={`${tc.category}-${idx}`}
                  tc={tc}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                  onBugCreated={onBugCreated}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
