import { useState } from "react"
import { useFeatureBugs, usePatchBug, useDeleteBug } from "@/hooks/useBugs"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { AlertTriangle, Bug, Check, Copy, Loader2, Search, ShieldCheck, Wrench } from "lucide-react"
import { cn } from "@/lib/utils"
import type { BugItem, BugSeverity } from "@/types/api"

const SEVERITY_STYLE: Record<BugSeverity, string> = {
  critical: "bg-red-100 text-red-700 ring-1 ring-red-200 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-900/40",
  major: "bg-amber-100 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:ring-amber-900/40",
  minor: "bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700/60",
  trivial: "bg-gray-100 text-gray-500 ring-1 ring-gray-200 dark:bg-gray-800/40 dark:text-gray-400 dark:ring-gray-700/60",
}

const SEVERITY_LABEL: Record<BugSeverity, string> = {
  critical: "Критичные",
  major: "Серьезные",
  minor: "Умеренные",
  trivial: "Незначительные",
}

type BugStatusFilter = "all" | "open" | "fixed" | "verified"
type ParsedKafkaArtifact = {
  topic?: string
  key?: string
  value?: string
}

function RichText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("`") && part.endsWith("`") ? (
          <code key={i} className="px-1 py-px rounded bg-muted text-[0.75rem] font-mono">
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

function stringifyKafkaPart(value: unknown): string | undefined {
  if (value == null) return undefined
  return typeof value === "string" ? value : JSON.stringify(value, null, 2)
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
      const kafka = parseKafkaArtifact(step.kafka_message)
      const kafkaText = kafka
        ? [
          kafka.topic ? `topic: ${kafka.topic}` : null,
          kafka.key ? `key: ${kafka.key}` : null,
          kafka.value ? `value:\n${kafka.value}` : null,
        ].filter(Boolean).join("\n\n")
        : step.kafka_message
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
  const [copiedField, setCopiedField] = useState<string | null>(null)

  const isBusy = patchMut.isPending || deleteMut.isPending
  const isFixed = bug.status === "fixed"
  const isVerified = bug.status === "verified"
  const isDone = isFixed || isVerified
  const statusLabel = isVerified ? "Проверен" : isFixed ? "Исправлен" : "Открыт"
  const statusTone = isVerified ? "verified" : isFixed ? "fixed" : "open"

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
        "overflow-hidden rounded-lg border bg-card transition-all hover:shadow-sm",
        isDone ? "border-border/60" : "border-border",
      )}
    >
      <div className="flex">
        <div className={cn(
          "w-1 shrink-0",
          bug.status === "open" && "bg-transparent",
          bug.status === "fixed" && "bg-amber-500",
          bug.status === "verified" && "bg-emerald-500",
        )} />

        <div className="flex-1 min-w-0">
          <div
            className="cursor-pointer p-4 md:p-5"
            onClick={() => setOpen(!open)}
          >
            <div className="flex items-start gap-3">
              <button
                className={cn(
                  "mt-[0.1875rem] shrink-0 flex h-4 w-4 items-center justify-center rounded-[0.25rem] border transition-colors",
                  isVerified
                    ? "border-emerald-500 bg-emerald-500 text-white"
                    : isFixed
                      ? "border-amber-500 bg-amber-500 text-white"
                      : "border-muted-foreground/25 hover:border-muted-foreground/50",
                )}
                onClick={handleCheckbox}
                disabled={isBusy}
              >
                {isDone && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
              </button>

              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        "text-[0.875rem] font-semibold leading-[1.55] text-foreground",
                        !open && "line-clamp-2",
                        isDone && "text-foreground/80",
                      )}
                    >
                      <RichText text={bug.title} />
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2.5 text-[0.6875rem]">
                      <p className="font-medium text-muted-foreground">{bug.test_case_name}</p>
                      <span className={cn(
                        "rounded-full px-2.5 py-0.5 font-medium",
                        statusTone === "verified" && "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
                        statusTone === "fixed" && "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
                        statusTone === "open" && "bg-muted text-muted-foreground",
                      )}>
                        {statusLabel}
                      </span>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-start gap-2">
                    {bug.severity && (
                      <span className={cn("rounded-full px-2.5 py-1 text-[0.625rem] font-semibold uppercase tracking-wide", SEVERITY_STYLE[bug.severity])}>
                        {bug.severity}
                      </span>
                    )}
                    <button
                      className={cn(
                        "rounded-md p-1 transition-colors",
                        copied ? "text-emerald-500" : "text-muted-foreground/50 hover:text-foreground",
                      )}
                      onClick={handleCopy}
                      title="Скопировать для Jira"
                    >
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {open && (
            <div className="ml-7 space-y-6 px-5 pb-5">
              {/* Сценарий — flat document style like Jira */}
              {bug.steps.length > 0 && (
                <div>
                  <p className="text-[0.875rem] font-bold text-foreground">Сценарий:</p>
                  <ol className="mt-3 list-decimal space-y-4 pl-5">
                    {bug.steps.map((step, si) => (
                      <li key={si} className="text-[0.875rem] leading-[1.7] text-foreground">
                        <RichText text={step.action} />
                        {step.result && (
                          <p className="mt-1 text-[0.8125rem] leading-[1.65] text-foreground/70"><RichText text={step.result} /></p>
                        )}
                        {(step.curl_command || step.sql_query || step.kafka_message) && (
                          <div className="mt-2.5 space-y-2.5">
                            {step.curl_command && (
                              <JiraCodeBlock
                                value={step.curl_command}
                                copied={copiedField === `${si}-curl`}
                                onCopy={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(step.curl_command!)
                                  setCopiedField(`${si}-curl`)
                                  setTimeout(() => setCopiedField(null), 1500)
                                }}
                              />
                            )}
                            {step.sql_query && (
                              <JiraCodeBlock
                                value={step.sql_query}
                                copied={copiedField === `${si}-sql`}
                                onCopy={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(step.sql_query!)
                                  setCopiedField(`${si}-sql`)
                                  setTimeout(() => setCopiedField(null), 1500)
                                }}
                              />
                            )}
                            {step.kafka_message && (() => {
                              const kafka = parseKafkaArtifact(step.kafka_message)
                              if (kafka) {
                                return (
                                  <div className="space-y-2.5">
                                    {kafka.topic && (
                                      <JiraCodeBlock
                                        value={`topic: ${kafka.topic}`}
                                        copied={copiedField === `${si}-message-topic`}
                                        onCopy={(e) => {
                                          e.stopPropagation()
                                          navigator.clipboard.writeText(kafka.topic!)
                                          setCopiedField(`${si}-message-topic`)
                                          setTimeout(() => setCopiedField(null), 1500)
                                        }}
                                      />
                                    )}
                                    {kafka.key && (
                                      <JiraCodeBlock
                                        value={`key: ${kafka.key}`}
                                        copied={copiedField === `${si}-message-key`}
                                        onCopy={(e) => {
                                          e.stopPropagation()
                                          navigator.clipboard.writeText(kafka.key!)
                                          setCopiedField(`${si}-message-key`)
                                          setTimeout(() => setCopiedField(null), 1500)
                                        }}
                                      />
                                    )}
                                    {kafka.value && (
                                      <JiraCodeBlock
                                        value={kafka.value}
                                        copied={copiedField === `${si}-message-value`}
                                        onCopy={(e) => {
                                          e.stopPropagation()
                                          navigator.clipboard.writeText(kafka.value!)
                                          setCopiedField(`${si}-message-value`)
                                          setTimeout(() => setCopiedField(null), 1500)
                                        }}
                                      />
                                    )}
                                  </div>
                                )
                              }

                              return (
                                <JiraCodeBlock
                                  value={formatKafkaArtifact(step.kafka_message)}
                                  copied={copiedField === `${si}-message`}
                                  onCopy={(e) => {
                                    e.stopPropagation()
                                    navigator.clipboard.writeText(formatKafkaArtifact(step.kafka_message!))
                                    setCopiedField(`${si}-message`)
                                    setTimeout(() => setCopiedField(null), 1500)
                                  }}
                                />
                              )
                            })()}
                          </div>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {/* ОР — ожидаемый результат */}
              <div>
                <p className="text-[0.875rem] font-bold text-foreground">ОР — ожидаемый результат:</p>
                <p className="mt-2 text-[0.875rem] leading-[1.7] text-foreground/80"><RichText text={bug.expected_result} /></p>
              </div>

              {/* ФР — фактический результат */}
              <div>
                <p className="text-[0.875rem] font-bold text-foreground">ФР — фактический результат:</p>
                <p className="mt-2 text-[0.875rem] leading-[1.7] text-foreground/80"><RichText text={bug.actual_result} /></p>
              </div>

              {bug.status === "open" && (
                <BugActionRow>
                  <button
                    className="rounded-md bg-amber-500 px-4 py-2 text-[0.75rem] font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-60"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "fixed" }) }}
                    disabled={isBusy}
                  >
                    Исправлен
                  </button>
                  <button
                    className="rounded-md px-3 py-2 text-[0.75rem] text-muted-foreground transition-colors hover:text-red-500"
                    onClick={(e) => { e.stopPropagation(); deleteMut.mutate(index) }}
                    disabled={isBusy}
                  >
                    Удалить
                  </button>
                </BugActionRow>
              )}

              {bug.status === "fixed" && (
                <BugActionRow>
                  <button
                    className="rounded-md bg-emerald-600 px-4 py-2 text-[0.75rem] font-semibold text-white transition-colors hover:bg-emerald-700 disabled:opacity-60"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "verified" }) }}
                    disabled={isBusy}
                  >
                    Проверен
                  </button>
                  <button
                    className="rounded-md border border-border px-3.5 py-2 text-[0.75rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "open" }) }}
                    disabled={isBusy}
                  >
                    Вернуть в работу
                  </button>
                </BugActionRow>
              )}

              {bug.status === "verified" && (
                <BugActionRow>
                  <button
                    className="rounded-md px-3 py-2 text-[0.75rem] text-muted-foreground/70 transition-colors hover:text-foreground"
                    onClick={(e) => { e.stopPropagation(); patchMut.mutate({ bugIndex: index, status: "open" }) }}
                    disabled={isBusy}
                  >
                    Вернуть в ожидание
                  </button>
                </BugActionRow>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function formatKafkaArtifact(raw: string): string {
  const kafka = parseKafkaArtifact(raw)
  if (!kafka) return formatValue(raw)

  return formatParsedKafkaArtifact(kafka)
}

function formatParsedKafkaArtifact(kafka: ParsedKafkaArtifact): string {
  return [
    kafka.topic ? `topic: ${kafka.topic}` : null,
    kafka.key ? `key: ${kafka.key}` : null,
    kafka.value ? `value:\n${kafka.value}` : null,
  ].filter(Boolean).join("\n\n")
}

function parseKafkaArtifact(raw: string): ParsedKafkaArtifact | null {
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === "object") {
      const topic = "topic" in parsed ? stringifyKafkaPart(parsed.topic) : undefined
      const key = "key" in parsed ? stringifyKafkaPart(parsed.key) : undefined
      const value = "value" in parsed
        ? formatValue(typeof parsed.value === "string" ? parsed.value : JSON.stringify(parsed.value, null, 2))
        : undefined

      if (topic || key || value) {
        return { topic, key, value }
      }
    }
  } catch {
    const topicMatch = raw.match(/(?:^|\n)\s*topic:\s*([^\n]+)/i)
    const keyMatch = raw.match(/(?:^|\n)\s*key:\s*([^\n]+)/i)
    const valueMatch = raw.match(/(?:^|\n)\s*value:\s*([\s\S]*)$/i)

    if (topicMatch || keyMatch || valueMatch) {
      return {
        topic: topicMatch?.[1]?.trim(),
        key: keyMatch?.[1]?.trim(),
        value: valueMatch?.[1] ? formatValue(valueMatch[1].trim()) : undefined,
      }
    }

    return null
  }

  return null
}

function JiraCodeBlock({
  value,
  copied,
  onCopy,
}: {
  value: string
  copied: boolean
  onCopy: (e: React.MouseEvent) => void
}) {
  return (
    <div className="group relative overflow-hidden rounded-md bg-[#f0f4f8] dark:bg-slate-900/70">
      <pre className="max-h-[26rem] overflow-auto whitespace-pre-wrap break-words px-4 py-3 text-[0.75rem] font-mono leading-6 text-slate-900 dark:text-slate-100">
        <code>{value}</code>
      </pre>
      <button
        onClick={onCopy}
        className="absolute right-2 top-2 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700 opacity-0 group-hover:opacity-100 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        title="Копировать"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

function BugActionRow({ children }: { children: React.ReactNode }) {
  return <div className="flex items-center gap-2 border-t border-border/70 pt-3">{children}</div>
}

export function BugsView({ projectSlug, featureName }: { projectSlug: string; featureName: string }) {
  const { data: bugsData, isLoading } = useFeatureBugs(projectSlug, featureName)
  const [statusFilter, setStatusFilter] = useState<BugStatusFilter>("all")
  const [severityFilter, setSeverityFilter] = useState<BugSeverity | "all">("all")
  const [query, setQuery] = useState("")

  const bugs = bugsData?.bugs ?? []
  const resolvedCount = bugs.filter(b => b.status === "fixed" || b.status === "verified").length
  const openCount = bugs.filter((bug) => bug.status === "open").length
  const fixedCount = bugs.filter((bug) => bug.status === "fixed").length
  const verifiedCount = bugs.filter((bug) => bug.status === "verified").length
  const criticalCount = bugs.filter((bug) => bug.severity === "critical").length

  const filteredBugs = bugs
    .map((bug, idx) => ({ bug, idx }))
    .filter(({ bug }) => {
      if (statusFilter !== "all" && bug.status !== statusFilter) return false
      if (severityFilter !== "all" && bug.severity !== severityFilter) return false
      if (!query.trim()) return true

      const haystack = [
        bug.title,
        bug.test_case_name,
        bug.expected_result,
        bug.actual_result,
        bug.analyst_text ?? "",
        ...bug.steps.flatMap((step) => [step.action, step.result]),
      ].join(" ").toLowerCase()

      return haystack.includes(query.trim().toLowerCase())
    })
    .sort((a, b) => {
      const severityRank: Record<BugSeverity, number> = { critical: 0, major: 1, minor: 2, trivial: 3 }
      const statusRank: Record<BugItem["status"], number> = { open: 0, fixed: 1, verified: 2 }
      return severityRank[a.bug.severity] - severityRank[b.bug.severity] || statusRank[a.bug.status] - statusRank[b.bug.status] || a.idx - b.idx
    })

  const severities = severityFilter === "all" ? (["critical", "major", "minor", "trivial"] as BugSeverity[]) : [severityFilter]
  const grouped = severities
    .map(severity => ({
      severity,
      items: filteredBugs.filter(({ bug }) => bug.severity === severity),
    }))
    .filter(g => g.items.length > 0)

  return (
    <div className="space-y-5">
      <div className="space-y-4">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <h2 className="text-base font-medium">Баг-репорты</h2>
          {bugs.length > 0 && (
            <span className="text-[0.8125rem] text-muted-foreground tabular-nums">
              Открыто {openCount} / Закрыто {resolvedCount} / Всего {bugs.length}
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Баги появляются после ревью тест-кейсов. Здесь важны приоритет, статус исправления и воспроизводимость.
        </p>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <BugMiniStat icon={<Bug className="h-4 w-4" />} label="Открыто" value={String(openCount)} />
          <BugMiniStat icon={<Wrench className="h-4 w-4" />} label="Исправлено" value={String(fixedCount)} tone={fixedCount > 0 ? "warning" : "default"} />
          <BugMiniStat icon={<ShieldCheck className="h-4 w-4" />} label="Проверено" value={String(verifiedCount)} tone={verifiedCount > 0 ? "success" : "default"} />
          <BugMiniStat icon={<AlertTriangle className="h-4 w-4" />} label="Критично" value={String(criticalCount)} tone={criticalCount > 0 ? "danger" : "default"} />
        </div>
      </div>

      {bugs.length > 0 && (
        <div className="sticky top-0 z-10 -mx-4 rounded-2xl border border-border/70 bg-background/95 px-4 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <BugFilterChip active={statusFilter === "all"} onClick={() => setStatusFilter("all")}>Все</BugFilterChip>
              <BugFilterChip active={statusFilter === "open"} onClick={() => setStatusFilter("open")}>Открытые</BugFilterChip>
              <BugFilterChip active={statusFilter === "fixed"} onClick={() => setStatusFilter("fixed")}>Исправленные</BugFilterChip>
              <BugFilterChip active={statusFilter === "verified"} onClick={() => setStatusFilter("verified")}>Проверенные</BugFilterChip>
            </div>

            <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <BugFilterChip active={severityFilter === "all"} onClick={() => setSeverityFilter("all")}>Все уровни</BugFilterChip>
                {(["critical", "major", "minor", "trivial"] as BugSeverity[]).map((severity) => (
                  <BugFilterChip key={severity} active={severityFilter === severity} onClick={() => setSeverityFilter(severity)}>
                    {SEVERITY_LABEL[severity]}
                  </BugFilterChip>
                ))}
              </div>

              <div className="relative min-w-[15rem]">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию, кейсу и результату" className="pl-8 text-sm" />
              </div>
            </div>
          </div>
        </div>
      )}

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
        <div className="rounded-xl border border-dashed px-4 py-12 text-center">
          <p className="text-sm font-medium">Баг-репорты еще не появились</p>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">
            Они создаются из вкладки тест-кейсов, когда сценарий требует отдельного баг-репорта.
          </p>
        </div>
      )}

      {bugs.length > 0 && filteredBugs.length === 0 && (
        <div className="rounded-xl border border-dashed px-4 py-12 text-center">
          <p className="text-sm font-medium">Ничего не найдено</p>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">Сбросьте фильтры или расширьте поисковый запрос.</p>
        </div>
      )}

      {/* Groups */}
      <div className="space-y-6">
        {grouped.map(({ severity, items }) => (
          <div key={severity}>
            <div className="mb-2.5 flex items-center gap-2 px-1">
              <p className="text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground/60">
                {SEVERITY_LABEL[severity]}
              </p>
              <span className="text-[0.6875rem] text-muted-foreground/40">{items.length}</span>
            </div>
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

function BugFilterChip({
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

function BugMiniStat({
  icon,
  label,
  value,
  tone = "default",
}: {
  icon: React.ReactNode
  label: string
  value: string
  tone?: "default" | "warning" | "success" | "danger"
}) {
  const toneClasses = {
    default: "border-border bg-background",
    warning: "border-amber-200/70 bg-amber-50/70 dark:border-amber-900/40 dark:bg-amber-950/10",
    success: "border-emerald-200/70 bg-emerald-50/70 dark:border-emerald-900/40 dark:bg-emerald-950/10",
    danger: "border-red-200/70 bg-red-50/70 dark:border-red-900/40 dark:bg-red-950/10",
  }

  return (
    <Card className={cn("shadow-none", toneClasses[tone])}>
      <CardContent className="flex items-start justify-between gap-3 py-3.5">
        <div>
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
          <p className="mt-2 text-xl font-semibold">{value}</p>
        </div>
        <div className="rounded-lg bg-muted p-2 text-muted-foreground">
          {icon}
        </div>
      </CardContent>
    </Card>
  )
}
