import { useState } from "react"
import { useFeatureBugs, usePatchBug, useDeleteBug } from "@/hooks/useBugs"
import { Check, Copy, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { BugItem, BugSeverity } from "@/types/api"

const SEVERITY_STYLE: Record<BugSeverity, string> = {
  critical: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
  major: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  minor: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  trivial: "bg-gray-100 text-gray-500 dark:bg-gray-800/40 dark:text-gray-400",
}

const SEVERITY_LABEL: Record<BugSeverity, string> = {
  critical: "Critical",
  major: "Major",
  minor: "Minor",
  trivial: "Trivial",
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

/** Simple regex-based XML pretty-printer. Returns as-is if not XML. */
function formatXml(xml: string): string {
  if (!xml.includes("<")) return xml
  const PADDING = "  "
  let indent = 0
  const lines: string[] = []
  // Split on tag boundaries
  const tokens = xml.replace(/>\s*</g, "><").split(/(?<=>)(?=<)|(?<=[^>])(?=<)/)
  for (const token of tokens) {
    const trimmed = token.trim()
    if (!trimmed) continue
    if (trimmed.startsWith("</")) {
      // Closing tag — decrease indent before
      indent = Math.max(0, indent - 1)
      lines.push(PADDING.repeat(indent) + trimmed)
    } else if (trimmed.startsWith("<") && !trimmed.startsWith("<?") && !trimmed.endsWith("/>") && !trimmed.includes("</")) {
      // Opening tag
      lines.push(PADDING.repeat(indent) + trimmed)
      indent++
    } else {
      // Self-closing, processing instruction, or text node
      lines.push(PADDING.repeat(indent) + trimmed)
    }
  }
  return lines.join("\n")
}

/** Format a raw string value: pretty-print JSON, indent XML, or return as-is. */
function formatValue(raw: string): string {
  const trimmed = raw.trim()
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch { /* not JSON */ }
  }
  if (trimmed.includes("<") && trimmed.includes(">")) {
    return formatXml(trimmed)
  }
  return raw
}

/** Format bug report as Jira wiki markup plain text. */
function formatBugForJira(bug: BugItem): string {
  const lines: string[] = []

  lines.push(`*${bug.severity}* | ${bug.test_case_name}`)
  lines.push("")
  lines.push(bug.title)
  lines.push("")
  lines.push("*Шаги воспроизведения:*")

  bug.steps.forEach((step, i) => {
    lines.push(`${i + 1}. ${step.action}`)
    lines.push(`   Результат: ${step.result}`)
    if (step.curl_command) {
      lines.push(`   {code:bash}`)
      lines.push(`   ${step.curl_command}`)
      lines.push(`   {code}`)
    }
    if (step.sql_query) {
      lines.push(`   {code:sql}`)
      lines.push(`   ${step.sql_query}`)
      lines.push(`   {code}`)
    }
    if (step.kafka_message) {
      let kafkaText = step.kafka_message
      try {
        const parsed = JSON.parse(step.kafka_message)
        if (parsed && typeof parsed === "object" && "key" in parsed && "value" in parsed) {
          const valStr = typeof parsed.value === "string" ? parsed.value : JSON.stringify(parsed.value, null, 2)
          kafkaText = `key: ${parsed.key}\nvalue: ${formatValue(valStr)}`
        }
      } catch { /* use raw */ }
      lines.push(`   {code}`)
      lines.push(`   ${kafkaText}`)
      lines.push(`   {code}`)
    }
  })

  lines.push("")
  lines.push("*Ожидаемый результат:*")
  lines.push(bug.expected_result)
  lines.push("")
  lines.push("*Фактический результат:*")
  lines.push(bug.actual_result)

  return lines.join("\n")
}

function BugCard({
  bug,
  index,
  projectSlug,
  featureName,
}: {
  bug: BugItem
  index: number
  projectSlug: string
  featureName: string
}) {
  const patchMut = usePatchBug(projectSlug, featureName)
  const deleteMut = useDeleteBug(projectSlug, featureName)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const isBusy = patchMut.isPending || deleteMut.isPending
  const isFixed = bug.status === "fixed"
  const isVerified = bug.status === "verified"
  const isDone = isFixed || isVerified

  function handleCheckbox(e: React.MouseEvent) {
    e.stopPropagation()
    if (isVerified) {
      patchMut.mutate({ bugIndex: index, status: "open" })
    } else if (isFixed) {
      patchMut.mutate({ bugIndex: index, status: "verified" })
    } else {
      patchMut.mutate({ bugIndex: index, status: "fixed" })
    }
  }

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    navigator.clipboard.writeText(formatBugForJira(bug)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div
      className={cn(
        "rounded-lg border bg-card overflow-hidden transition-all hover:shadow-sm",
        isDone ? "border-border/60" : "border-border",
      )}
    >
      <div className="flex">
        {/* Status stripe */}
        <div className={cn(
          "w-1 shrink-0",
          bug.status === "open" && "bg-transparent",
          bug.status === "fixed" && "bg-amber-500",
          bug.status === "verified" && "bg-emerald-500",
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
                isVerified
                  ? "bg-emerald-500 border-emerald-500 text-white"
                  : isFixed
                    ? "bg-amber-500 border-amber-500 text-white"
                    : "border-muted-foreground/25 hover:border-muted-foreground/50",
              )}
              onClick={handleCheckbox}
              disabled={isBusy}
            >
              {isDone && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
            </button>

            {/* Title */}
            <div className="flex-1 min-w-0">
              <p className={cn(
                "text-[13px] leading-[1.65]",
                !open && "line-clamp-2",
                isDone && "text-muted-foreground",
              )}>
                <RichText text={bug.title} />
              </p>
              <p className="text-[11px] text-muted-foreground/60 mt-0.5">{bug.test_case_name}</p>
            </div>

            {/* Severity + Status + Copy */}
            <div className="shrink-0 flex items-center gap-2">
              {bug.severity && (
                <span className={cn("text-[10px] font-medium px-1.5 py-0.5 rounded", SEVERITY_STYLE[bug.severity])}>
                  {bug.severity}
                </span>
              )}
              {bug.status === "fixed" && (
                <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">исправлен</span>
              )}
              {bug.status === "verified" && (
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">проверен</span>
              )}
              {open && (
                <button
                  className={cn(
                    "transition-colors",
                    copied ? "text-emerald-500" : "text-muted-foreground/50 hover:text-foreground",
                  )}
                  onClick={handleCopy}
                  title="Copy for Jira"
                >
                  {copied
                    ? <Check className="h-4 w-4" />
                    : <Copy className="h-4 w-4" />
                  }
                </button>
              )}
            </div>
          </div>

          {/* Expanded */}
          {open && (
            <div className="px-4 pb-4 space-y-3 ml-7">
              {/* Steps */}
              {bug.steps.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider mb-2 px-1">
                    Шаги воспроизведения
                  </p>
                  <div className="space-y-3">
                    {bug.steps.map((step, si) => (
                      <div key={si} className="grid grid-cols-[auto_1fr] gap-x-2.5 text-[13px]">
                        <span className="text-muted-foreground/50 font-medium tabular-nums pt-px">{si + 1}.</span>
                        <div className="space-y-1">
                          <p className="leading-[1.65]"><RichText text={step.action} /></p>
                          <p className="text-muted-foreground leading-[1.65]">Факт: <RichText text={step.result} /></p>
                          {step.curl_command && (
                            <div>
                              <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">curl</span>
                              <pre className="mt-0.5 text-[12px] bg-muted/60 rounded px-2.5 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-foreground/70">
                                <code>{step.curl_command}</code>
                              </pre>
                            </div>
                          )}
                          {step.sql_query && (
                            <div>
                              <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">SQL</span>
                              <pre className="mt-0.5 text-[12px] bg-muted/60 rounded px-2.5 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-foreground/70">
                                <code>{step.sql_query}</code>
                              </pre>
                            </div>
                          )}
                          {step.kafka_message && (
                            <div>
                              <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">Kafka</span>
                              {(() => {
                                try {
                                  const parsed = JSON.parse(step.kafka_message)
                                  if (parsed && typeof parsed === "object" && "key" in parsed && "value" in parsed) {
                                    const valStr = typeof parsed.value === "string"
                                      ? formatValue(parsed.value)
                                      : JSON.stringify(parsed.value, null, 2)
                                    return (
                                      <div className="mt-0.5 space-y-1">
                                        <div className="text-[12px] bg-muted/60 rounded px-2.5 py-1.5 font-mono text-foreground/70">
                                          <span className="text-muted-foreground/50">key:</span> {typeof parsed.key === "string" ? parsed.key : JSON.stringify(parsed.key)}
                                        </div>
                                        <pre className="text-[12px] bg-muted/60 rounded px-2.5 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-foreground/70">
                                          <code>{valStr}</code>
                                        </pre>
                                      </div>
                                    )
                                  }
                                } catch { /* not JSON, fall through */ }
                                return (
                                  <pre className="mt-0.5 text-[12px] bg-muted/60 rounded px-2.5 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-foreground/70">
                                    <code>{formatValue(step.kafka_message)}</code>
                                  </pre>
                                )
                              })()}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expected result */}
              <div>
                <p className="text-[13px] font-semibold mb-1">Ожидаемый результат</p>
                <p className="text-[13px] leading-[1.65] text-foreground/80"><RichText text={bug.expected_result} /></p>
              </div>

              {/* Actual result */}
              <div>
                <p className="text-[13px] font-semibold mb-1">Фактический результат</p>
                <p className="text-[13px] leading-[1.65] text-foreground/80"><RichText text={bug.actual_result} /></p>
              </div>

              {/* Actions */}
              {bug.status === "open" && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-amber-500 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/30 transition-colors"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "fixed" }) }}
                    disabled={isBusy}
                  >
                    Исправлен
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

              {bug.status === "fixed" && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-emerald-500 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "verified" }) }}
                    disabled={isBusy}
                  >
                    Проверен
                  </button>
                  <button
                    className="text-[12px] font-medium px-3.5 py-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground transition-colors"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "open" }) }}
                    disabled={isBusy}
                  >
                    Вернуть
                  </button>
                </div>
              )}

              {bug.status === "verified" && (
                <button
                  className="text-[12px] text-muted-foreground/60 hover:text-foreground transition-colors pt-1"
                  onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "open" }) }}
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

export function BugsView({ projectSlug, featureName }: { projectSlug: string; featureName: string }) {
  const { data: bugsData, isLoading } = useFeatureBugs(projectSlug, featureName)

  const bugs = bugsData?.bugs ?? []
  const resolvedCount = bugs.filter(b => b.status === "fixed" || b.status === "verified").length

  const severities: BugSeverity[] = ["critical", "major", "minor", "trivial"]
  const grouped = severities
    .map(severity => ({
      severity,
      items: bugs
        .map((bug, idx) => ({ bug, idx }))
        .filter(({ bug }) => bug.severity === severity),
    }))
    .filter(g => g.items.length > 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-base font-medium">Баг-репорты</h2>
          {bugs.length > 0 && (
            <span className="text-[13px] text-muted-foreground tabular-nums">
              {resolvedCount} из {bugs.length}
            </span>
          )}
        </div>
      </div>

      {/* Progress */}
      {bugs.length > 0 && (
        <div className="h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-500"
            style={{ width: `${(resolvedCount / bugs.length) * 100}%` }}
          />
        </div>
      )}

      {/* Loading */}
      {isLoading && bugs.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty */}
      {!isLoading && bugs.length === 0 && (
        <p className="text-[13px] text-muted-foreground text-center py-16">
          Нет баг-репортов
        </p>
      )}

      {/* Groups */}
      <div className="space-y-6">
        {grouped.map(({ severity, items }) => (
          <div key={severity}>
            <p className="text-[11px] font-medium text-muted-foreground/60 uppercase tracking-wider mb-2.5 px-1">
              {SEVERITY_LABEL[severity]} <span className="text-muted-foreground/40 ml-1">{items.length}</span>
            </p>
            <div className="space-y-2">
              {items.map(({ bug, idx }) => (
                <BugCard
                  key={`${bug.severity}-${idx}`}
                  bug={bug}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
