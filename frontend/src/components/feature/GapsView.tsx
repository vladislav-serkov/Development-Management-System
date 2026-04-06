import { useState } from "react"
import { useFeatureGaps, usePatchGap, useDeleteGap, useRunGaps, useRunApplyPreview, useApplyPreviewData, useApplyConfirm } from "@/hooks/useGaps"
import { Textarea } from "@/components/ui/textarea"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { Check, Play, Loader2, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { GapItem, GapType, GapSeverity, StructuredBusinessLogic, LogicStep, MessageField, ParameterField, UsedDependency } from "@/types/api"

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
  major: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
}

function formatGapType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
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

function GapCard({
  gap,
  index,
  projectSlug,
  featureName,
}: {
  gap: GapItem
  index: number
  projectSlug: string
  featureName: string
}) {
  const patchGap = usePatchGap(projectSlug, featureName)
  const deleteGapMut = useDeleteGap(projectSlug, featureName)
  const [open, setOpen] = useState(false)
  const [showClarify, setShowClarify] = useState(false)
  const [clarifyText, setClarifyText] = useState(gap.analyst_text ?? "")
  const [clarifyError, setClarifyError] = useState(false)

  const isBusy = patchGap.isPending || deleteGapMut.isPending
  const resolved = gap.status === "approved" || gap.status === "clarified"
  const applied = gap.status === "applied"

  return (
    <div
      className={cn(
        "rounded-lg border bg-card overflow-hidden transition-all hover:shadow-sm",
        (resolved || applied) ? "border-border/60" : "border-border",
      )}
    >
      {/* Left accent + content */}
      <div className="flex">
        {/* Status stripe */}
        <div className={cn(
          "w-1 shrink-0",
          gap.status === "approved" && "bg-emerald-500",
          gap.status === "clarified" && "bg-blue-500",
          gap.status === "applied" && "bg-violet-500",
          gap.status === "pending" && "bg-transparent",
        )} />

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div
            className="flex items-start gap-3 p-4 cursor-pointer"
            onClick={() => setOpen(!open)}
          >
            {/* Checkbox — only interactive for actionable gaps or already resolved */}
            <button
              className={cn(
                "mt-[3px] shrink-0 w-4 h-4 rounded-[4px] border flex items-center justify-center transition-colors",
                resolved
                  ? "bg-emerald-500 border-emerald-500 text-white"
                  : applied
                    ? "bg-violet-500 border-violet-500 text-white"
                    : gap.actionable
                      ? "border-muted-foreground/25 hover:border-muted-foreground/50"
                      : "border-muted-foreground/15 cursor-default",
              )}
              onClick={(e) => {
                e.stopPropagation()
                if (resolved) patchGap.mutate({ gapIndex: index, status: "pending", analyst_text: null })
                else if (gap.actionable && !applied) patchGap.mutate({ gapIndex: index, status: "approved" })
              }}
              disabled={isBusy || applied || (!resolved && !gap.actionable)}
            >
              {(resolved || applied) && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
            </button>

            {/* Question */}
            <div className="flex-1 min-w-0">
              <p className={cn(
                "text-[13px] leading-[1.65]",
                !open && "line-clamp-2",
                (resolved || applied) && "text-muted-foreground",
              )}>
                <RichText text={gap.question} />
              </p>
            </div>

            {/* Severity + Status */}
            <div className="shrink-0 flex items-center gap-2">
              {gap.severity && (
                <span className={cn("text-[10px] font-medium px-1.5 py-0.5 rounded", SEVERITY_STYLE[gap.severity])}>
                  {gap.severity}
                </span>
              )}
              {gap.status === "clarified" && (
                <span className="text-[11px] text-blue-600 dark:text-blue-400 font-medium">уточнено</span>
              )}
              {gap.status === "approved" && (
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">принято</span>
              )}
              {gap.status === "applied" && (
                <span className="text-[11px] text-violet-600 dark:text-violet-400 font-medium">применено</span>
              )}
            </div>
          </div>

          {/* Expanded */}
          {open && (
            <div className="px-4 pb-4 space-y-3 ml-7">
              {/* Recommendation */}
              <div className="rounded-md bg-muted/50 p-3.5">
                <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-1.5">
                  Рекомендация
                </p>
                <p className="text-[13px] leading-[1.65] text-foreground/80">
                  <RichText text={gap.suggestion} />
                </p>
              </div>

              {/* Analyst note */}
              {gap.status === "clarified" && gap.analyst_text && (
                <div className="rounded-md bg-blue-50/60 dark:bg-blue-950/20 border border-blue-100/80 dark:border-blue-900/30 p-3.5">
                  <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-1.5">
                    Комментарий
                  </p>
                  <p className="text-[13px] leading-[1.65] text-foreground/80">{gap.analyst_text}</p>
                </div>
              )}

              {/* Actions */}
              {gap.status === "pending" && !showClarify && (
                <div className="flex items-center gap-2 pt-1">
                  {gap.actionable && (
                    <button
                      className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-emerald-500 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
                      onClick={(e) => { e.stopPropagation(); patchGap.mutate({ gapIndex: index, status: "approved" }) }}
                      disabled={isBusy}
                    >
                      Принять
                    </button>
                  )}
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-blue-500 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
                    onClick={(e) => { e.stopPropagation(); setShowClarify(true) }}
                    disabled={isBusy}
                  >
                    Уточнить
                  </button>
                  <button
                    className="text-[12px] px-3 py-1.5 rounded-md text-muted-foreground hover:text-red-500 transition-colors"
                    onClick={(e) => { e.stopPropagation(); deleteGapMut.mutate(index) }}
                    disabled={isBusy}
                  >
                    Удалить
                  </button>
                </div>
              )}

              {gap.status === "pending" && showClarify && (
                <div className="space-y-2.5 pt-1" onClick={e => e.stopPropagation()}>
                  <div className="space-y-1">
                    <Textarea
                      placeholder="Комментарий..."
                      value={clarifyText}
                      onChange={(e) => { setClarifyText(e.target.value); if (e.target.value.trim()) setClarifyError(false) }}
                      className={cn("text-[13px] min-h-[56px]", clarifyError && "border-red-500 focus-visible:ring-red-500")}
                    />
                    {clarifyError && (
                      <p className="text-[12px] text-red-500">Введите комментарий</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="text-[12px] font-medium px-3.5 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors"
                      onClick={() => {
                        if (!clarifyText.trim()) { setClarifyError(true); return }
                        patchGap.mutate({ gapIndex: index, status: "clarified", analyst_text: clarifyText || null }); setShowClarify(false)
                      }}
                      disabled={isBusy}
                    >
                      Сохранить
                    </button>
                    <button
                      className="text-[12px] px-3 py-1.5 rounded-md text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => { setShowClarify(false); setClarifyText(gap.analyst_text ?? ""); setClarifyError(false) }}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              )}

              {resolved && (
                <button
                  className="text-[12px] text-muted-foreground/60 hover:text-foreground transition-colors pt-1"
                  onClick={(e) => { e.stopPropagation(); patchGap.mutate({ gapIndex: index, status: "pending", analyst_text: null }) }}
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

// --- Structural diff ---

type DiffStatus = "same" | "added" | "removed" | "modified"

const DIFF_BG: Record<DiffStatus, string> = {
  same: "",
  added: "bg-emerald-50 dark:bg-emerald-950/20",
  removed: "bg-red-50 dark:bg-red-950/20 line-through opacity-60",
  modified: "bg-amber-50 dark:bg-amber-950/20",
}

function DiffRow({ status, children }: { status: DiffStatus; children: React.ReactNode }) {
  if (status === "same") return <>{children}</>
  return (
    <div className={cn("rounded-sm -mx-1 px-1", DIFF_BG[status])}>
      {children}
    </div>
  )
}

function diffByKey<T>(oldArr: T[], newArr: T[], key: (item: T) => string): { item: T; status: DiffStatus }[] {
  const oldMap = new Map(oldArr.map(item => [key(item), item]))
  const newMap = new Map(newArr.map(item => [key(item), item]))
  const result: { item: T; status: DiffStatus }[] = []

  // Removed items (in old, not in new)
  for (const [k, item] of oldMap) {
    if (!newMap.has(k)) result.push({ item, status: "removed" })
  }

  // Same, modified, or added (iterate new to preserve new order)
  for (const [k, newItem] of newMap) {
    const oldItem = oldMap.get(k)
    if (!oldItem) {
      result.push({ item: newItem, status: "added" })
    } else if (JSON.stringify(oldItem) === JSON.stringify(newItem)) {
      result.push({ item: newItem, status: "same" })
    } else {
      result.push({ item: newItem, status: "modified" })
    }
  }

  return result
}

function DiffMappingTable({ fields }: { fields: MessageField[] }) {
  if (!fields?.length) return null
  return (
    <div className="mt-2 ml-8 border rounded-md overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-muted/50">
          <tr>
            <th className="text-left px-2 py-1 font-medium">Element</th>
            <th className="text-left px-2 py-1 font-medium">Type</th>
            <th className="text-left px-2 py-1 font-medium">Req</th>
            <th className="text-left px-2 py-1 font-medium">Description</th>
            <th className="text-left px-2 py-1 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => (
            <DiffMappingRow key={i} field={f} depth={0} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DiffMappingRow({ field, depth }: { field: MessageField; depth: number }) {
  return (
    <>
      <tr className="border-t border-muted">
        <td className="px-2 py-1 font-mono" style={{ paddingLeft: `${0.5 + depth * 1}rem` }}>
          {field.element}{field.is_collection && <span className="text-muted-foreground">[]</span>}
        </td>
        <td className="px-2 py-1 text-muted-foreground">{field.field_type ?? "-"}</td>
        <td className="px-2 py-1">{field.required ? "Yes" : "No"}</td>
        <td className="px-2 py-1 text-muted-foreground">{field.description ?? "-"}</td>
        <td className="px-2 py-1 text-muted-foreground">{field.source ?? "-"}</td>
      </tr>
      {field.children?.map((child, i) => (
        <DiffMappingRow key={i} field={child} depth={depth + 1} />
      ))}
    </>
  )
}

function DiffStepNode({ step, status }: { step: LogicStep; status: DiffStatus }) {
  return (
    <DiffRow status={status}>
      <div>
        <div className="flex items-start gap-2 py-1">
          <span className="font-mono text-muted-foreground shrink-0 text-sm min-w-[2.5rem]">
            {step.number}
          </span>
          <span className="text-sm">{step.text}</span>
        </div>
        {step.message_mapping && step.message_mapping.length > 0 && (
          <DiffMappingTable fields={step.message_mapping} />
        )}
        {step.children?.length > 0 && (
          <div className="ml-6 border-l-2 border-muted pl-4 mt-1 space-y-1">
            {step.children.map((child, i) => (
              <DiffStepNode key={i} step={child} status={status} />
            ))}
          </div>
        )}
      </div>
    </DiffRow>
  )
}

function DiffLogicSteps({ oldSteps, newSteps }: { oldSteps: LogicStep[]; newSteps: LogicStep[] }) {
  const flattenAll = (steps: LogicStep[]): LogicStep[] => {
    const result: LogicStep[] = []
    for (const s of steps) {
      result.push(s)
      if (s.children?.length) result.push(...flattenAll(s.children))
    }
    return result
  }

  // Diff top-level steps by number, then recurse
  const diffed = diffByKey(oldSteps, newSteps, s => s.number)

  return (
    <div className="space-y-1">
      {diffed.map(({ item: step, status }, i) => {
        // For modified steps, diff children recursively
        if (status === "modified") {
          const oldStep = oldSteps.find(s => s.number === step.number)
          const textChanged = oldStep && oldStep.text !== step.text
          const mappingChanged = JSON.stringify(oldStep?.message_mapping) !== JSON.stringify(step.message_mapping)

          return (
            <div key={i}>
              <DiffRow status={textChanged || mappingChanged ? "modified" : "same"}>
                <div className="flex items-start gap-2 py-1">
                  <span className="font-mono text-muted-foreground shrink-0 text-sm min-w-[2.5rem]">
                    {step.number}
                  </span>
                  <span className="text-sm">{step.text}</span>
                </div>
                {step.message_mapping && step.message_mapping.length > 0 && (
                  <DiffMappingTable fields={step.message_mapping} />
                )}
              </DiffRow>
              {step.children?.length > 0 && (
                <div className="ml-6 border-l-2 border-muted pl-4 mt-1 space-y-1">
                  <DiffLogicSteps
                    oldSteps={oldStep?.children ?? []}
                    newSteps={step.children}
                  />
                </div>
              )}
            </div>
          )
        }

        return <DiffStepNode key={i} step={step} status={status} />
      })}
    </div>
  )
}

function DiffParams({ oldParams, newParams }: { oldParams: ParameterField[]; newParams: ParameterField[] }) {
  const diffed = diffByKey(oldParams, newParams, p => p.name)
  return (
    <div className="rounded-md border overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-muted/50">
          <tr>
            <th className="text-left px-2 py-1 font-medium">Имя</th>
            <th className="text-left px-2 py-1 font-medium">Тип</th>
            <th className="text-left px-2 py-1 font-medium">Обяз.</th>
            <th className="text-left px-2 py-1 font-medium">Описание</th>
            <th className="text-left px-2 py-1 font-medium">Валидация</th>
          </tr>
        </thead>
        <tbody>
          {diffed.map(({ item: p, status }, i) => (
            <tr key={i} className={cn("border-t border-muted", DIFF_BG[status])}>
              <td className="px-2 py-1 font-mono">{p.name}</td>
              <td className="px-2 py-1 text-muted-foreground">{p.field_type}</td>
              <td className="px-2 py-1">{p.required ? "Yes" : "No"}</td>
              <td className="px-2 py-1 text-muted-foreground">{p.description}</td>
              <td className="px-2 py-1 text-muted-foreground text-xs">{p.validation_rules?.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DiffRules({ oldRules, newRules }: { oldRules: string[]; newRules: string[] }) {
  const diffed = diffByKey(
    oldRules.map((r, i) => ({ id: r, text: r, idx: i })),
    newRules.map((r, i) => ({ id: r, text: r, idx: i })),
    r => r.text,
  )
  return (
    <ul className="list-disc pl-4 space-y-1">
      {diffed.map(({ item, status }, i) => (
        <li key={i} className={cn("text-sm rounded-sm", DIFF_BG[status])}>
          {item.text}
        </li>
      ))}
    </ul>
  )
}

function DiffDeps({ oldDeps, newDeps }: { oldDeps: UsedDependency[]; newDeps: UsedDependency[] }) {
  const depKey = (d: UsedDependency) => `${d.type}:${d.name}`
  const diffed = diffByKey(oldDeps, newDeps, depKey)
  return (
    <div className="space-y-1">
      {diffed.map(({ item: d, status }, i) => (
        <DiffRow key={i} status={status}>
          <div className="flex items-center gap-2 text-sm py-0.5">
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
              {d.type}
            </span>
            <span className="font-mono text-sm">
              {d.type === "external_api" && d.method
                ? `${d.method} ${d.name}`
                : d.name}
            </span>
            <span className="text-muted-foreground">— {d.description}</span>
          </div>
        </DiffRow>
      ))}
    </div>
  )
}

function DiffPreviewModal({
  original,
  proposed,
  onAccept,
  onReject,
  isAccepting,
}: {
  original: StructuredBusinessLogic
  proposed: StructuredBusinessLogic
  onAccept: () => void
  onReject: () => void
  isAccepting: boolean
}) {
  const sections: { title: string; content: React.ReactNode }[] = []

  if (original.input_parameters?.length || proposed.input_parameters?.length) {
    sections.push({
      title: "Входные параметры",
      content: <DiffParams oldParams={original.input_parameters ?? []} newParams={proposed.input_parameters ?? []} />,
    })
  }
  {
    const successOld = original.success_response ?? original.output_parameters ?? []
    const successNew = proposed.success_response ?? proposed.output_parameters ?? []
    if (successOld.length || successNew.length) {
      sections.push({
        title: "Успешный ответ",
        content: <DiffParams oldParams={successOld} newParams={successNew} />,
      })
    }
  }
  if (original.logic_steps?.length || proposed.logic_steps?.length) {
    sections.push({
      title: "Шаги логики",
      content: <DiffLogicSteps oldSteps={original.logic_steps ?? []} newSteps={proposed.logic_steps ?? []} />,
    })
  }
  if (original.business_rules?.length || proposed.business_rules?.length) {
    sections.push({
      title: "Бизнес-правила",
      content: <DiffRules oldRules={original.business_rules ?? []} newRules={proposed.business_rules ?? []} />,
    })
  }
  if (original.used_dependencies?.length || proposed.used_dependencies?.length) {
    sections.push({
      title: "Зависимости",
      content: <DiffDeps oldDeps={original.used_dependencies ?? []} newDeps={proposed.used_dependencies ?? []} />,
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={onReject}
    >
      <div
        className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-4xl flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
          <div>
            <h2 className="text-sm font-semibold">Изменения в логике</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Предпросмотр на основе утверждённых gaps
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-100 dark:bg-emerald-950/40 border border-emerald-300" /> добавлено</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-100 dark:bg-amber-950/40 border border-amber-300" /> изменено</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-100 dark:bg-red-950/40 border border-red-300" /> удалено</span>
            </div>
            <button
              className="text-muted-foreground hover:text-foreground transition-colors text-lg leading-none px-1"
              onClick={onReject}
            >
              ×
            </button>
          </div>
        </div>

        {/* Diff body */}
        <div className="flex-1 overflow-y-auto min-h-0 p-5 space-y-6">
          {sections.map(({ title, content }, i) => (
            <div key={i}>
              <h3 className="text-sm font-medium mb-3">{title}</h3>
              {content}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-border">
          <button
            className="text-[12px] px-3.5 py-1.5 rounded-md text-muted-foreground hover:text-foreground border border-border transition-colors"
            onClick={onReject}
            disabled={isAccepting}
          >
            Отклонить
          </button>
          <button
            className="text-[12px] font-medium px-4 py-1.5 rounded-md bg-violet-600 text-white hover:bg-violet-700 transition-colors flex items-center gap-1.5"
            onClick={onAccept}
            disabled={isAccepting}
          >
            {isAccepting ? (
              <><Loader2 className="h-3 w-3 animate-spin" />Сохранение...</>
            ) : (
              <>Принять изменения</>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export function GapsView({ projectSlug, featureName }: { projectSlug: string; featureName: string }) {
  const { data: gapsData, isLoading } = useFeatureGaps(projectSlug, featureName)
  const runGaps = useRunGaps(projectSlug, featureName)
  const runApplyMut = useRunApplyPreview(projectSlug, featureName)
  const { data: applyData } = useApplyPreviewData(projectSlug, featureName)
  const applyConfirmMut = useApplyConfirm(projectSlug, featureName)

  const displayGaps = gapsData?.gaps ?? []
  const isRunning = runGaps.isPending || gapsData?.gaps_status === "running"
  const alreadyDone = gapsData?.gaps_status === "done"
  const isOverloaded = gapsData?.gaps_status === "overloaded"

  const applyRunning = runApplyMut.isPending || applyData?.status === "running"
  const applyReady = applyData?.status === "done" && applyData.original && applyData.proposed

  const resolvedCount = displayGaps.filter(g => g.status !== "pending").length

  const hasActionableGaps = displayGaps.some(g => g.status === "approved" || g.status === "clarified")

  const grouped = (() => {
    const order: string[] = []
    const map = new Map<string, { gap: GapItem; idx: number }[]>()
    displayGaps.forEach((gap, idx) => {
      if (!map.has(gap.gap_type)) {
        order.push(gap.gap_type)
        map.set(gap.gap_type, [])
      }
      map.get(gap.gap_type)!.push({ gap, idx })
    })
    return order.map(type => ({ type, items: map.get(type)! }))
  })()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-base font-medium">Gaps</h2>
          {displayGaps.length > 0 && (
            <span className="text-[13px] text-muted-foreground tabular-nums">
              {resolvedCount} из {displayGaps.length}
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
            onClick={() => runGaps.mutate()}
            disabled={isRunning}
          >
            {isRunning ? (
              <span className="flex items-center gap-1.5"><Loader2 className="h-3 w-3 animate-spin" />Анализ<AnimatedDots /></span>
            ) : (
              <span className="flex items-center gap-1.5"><Play className="h-3 w-3" />Запустить</span>
            )}
          </button>
        ) : displayGaps.length > 0 ? (
          <span className="text-[12px] text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
            <Check className="h-3.5 w-3.5" />Завершён
          </span>
        ) : null}
      </div>

      {/* Progress */}
      {displayGaps.length > 0 && (
        <div className="h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-500"
            style={{ width: `${(resolvedCount / displayGaps.length) * 100}%` }}
          />
        </div>
      )}

      {/* Error */}
      {isOverloaded && (
        <p className="text-[13px] text-amber-600 dark:text-amber-400">Claude API перегружен. Попробуйте через 5 минут.</p>
      )}
      {runGaps.error && (
        <p className="text-[13px] text-destructive">{(runGaps.error as Error).message}</p>
      )}
      {runApplyMut.error && (
        <p className="text-[13px] text-destructive">{(runApplyMut.error as Error).message}</p>
      )}

      {/* Loading */}
      {(isLoading || isRunning) && displayGaps.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isRunning && displayGaps.length === 0 && (
        <p className="text-[13px] text-muted-foreground text-center py-16">
          Нет данных
        </p>
      )}

      {/* Groups */}
      <div className="space-y-6">
        {grouped.map(({ type, items }) => (
          <div key={type}>
            <p className="text-[11px] font-medium text-muted-foreground/60 uppercase tracking-wider mb-2.5 px-1">
              {formatGapType(type)} <span className="text-muted-foreground/40 ml-1">{items.length}</span>
            </p>
            <div className="space-y-2">
              {items.map(({ gap, idx }) => (
                <GapCard
                  key={`${gap.gap_type}-${idx}`}
                  gap={gap}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Apply to Logic button */}
      {alreadyDone && hasActionableGaps && (
        <div className="pt-2 flex justify-start">
          <button
            className="text-[13px] font-medium px-5 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-60"
            onClick={() => runApplyMut.mutate()}
            disabled={applyRunning}
          >
            {applyRunning ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" />Генерация<AnimatedDots /></>
            ) : (
              "Применить к логике"
            )}
          </button>
        </div>
      )}

      {/* Apply preview error */}
      {runApplyMut.error && (
        <p className="text-[13px] text-destructive">{(runApplyMut.error as Error).message}</p>
      )}
      {applyData?.status === "error" && (
        <p className="text-[13px] text-destructive">{applyData.error ?? "Apply preview failed"}</p>
      )}

      {/* Diff Preview Modal */}
      {applyReady && (
        <DiffPreviewModal
          original={applyData!.original}
          proposed={applyData!.proposed}
          onAccept={() => applyConfirmMut.mutate(applyData!.proposed)}
          onReject={() => {/* modal stays until user navigates or confirms */}}
          isAccepting={applyConfirmMut.isPending}
        />
      )}
    </div>
  )
}
