import { useEffect, useRef, useState } from "react"
import { useFeatureBugs, usePatchBug, useDeleteBug, useExportBugToJira, useFixBug, useSyncJiraStatuses } from "@/hooks/useBugs"
import { Input } from "@/components/ui/input"
import { StatStrip } from "@/components/ui/stat-strip"
import { FilterSelect, Segmented } from "@/components/ui/segmented"
import { Bot, Check, Copy, ExternalLink, Loader2, Search, Send } from "lucide-react"
import { cn } from "@/lib/utils"
import type { BugItem, BugSeverity } from "@/types/api"

const SEVERITY_STYLE: Record<BugSeverity, string> = {
  critical: "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400",
  major: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-400",
  minor: "border-border text-muted-foreground",
  trivial: "border-border text-muted-foreground",
}


const STATUS_STYLE = {
  open: "border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400",
  fixed: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-400",
  verified: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-400",
} as const

/** "https://…/merge_requests/304" → " !304" */
function mrNumber(url: string) {
  const m = url.match(/merge_requests\/(\d+)/) ?? url.match(/pull\/(\d+)/)
  return m ? ` !${m[1]}` : ""
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
  jiraConfigured,
}: {
  bug: BugItem
  index: number
  projectSlug: string
  featureName: string
  jiraConfigured: boolean
}) {
  const patchMut = usePatchBug(projectSlug, featureName)
  const deleteMut = useDeleteBug(projectSlug, featureName)
  const exportMut = useExportBugToJira(projectSlug, featureName)
  const fixMut = useFixBug(projectSlug, featureName)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [jiraFormOpen, setJiraFormOpen] = useState(false)
  const [featureTicket, setFeatureTicket] = useState("")

  const isBusy = patchMut.isPending || deleteMut.isPending || exportMut.isPending || fixMut.isPending
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
    <div className={cn("overflow-hidden rounded-xl border bg-card transition-all hover:border-foreground/15", isDone && "opacity-90")}>
      <div className="flex">
        <div className="flex-1 min-w-0">
          <div className="cursor-pointer px-4 py-3" onClick={() => setOpen(!open)}>
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
                title={isVerified ? "Вернуть в открытые" : isFixed ? "Отметить проверенным" : "Отметить исправленным"}
              >
                {isDone && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
              </button>

              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <p className={cn("text-[0.875rem] font-semibold leading-[1.5] text-foreground", !open && "line-clamp-2", isDone && "text-foreground/80")}>
                      <RichText text={bug.title} />
                    </p>
                    <p className="mt-0.5 text-[0.75rem] text-muted-foreground">из кейса «{bug.test_case_name}»</p>
                  </div>
                  {bug.severity && (
                    <span className={cn("shrink-0 rounded-full border px-2 py-px text-[0.6875rem] font-medium", SEVERITY_STYLE[bug.severity])}>
                      {bug.severity}
                    </span>
                  )}
                  <button
                    className={cn("shrink-0 rounded-md p-1 transition-colors", copied ? "text-emerald-500" : "text-muted-foreground/60 hover:text-foreground")}
                    onClick={handleCopy}
                    title="Скопировать для Jira"
                  >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 text-[0.6875rem]">
                  <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-px font-medium", STATUS_STYLE[statusTone])}>
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    {statusLabel.toLowerCase()}
                  </span>
                  {bug.jira_key ? (
                    <a
                      href={bug.jira_url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-px font-medium text-blue-700 transition-colors hover:bg-blue-100 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-400"
                      title={bug.jira_status ? `Статус в Jira: ${bug.jira_status}` : "Открыть в Jira"}
                    >
                      {bug.jira_key}
                      {bug.jira_status && <span className="font-normal opacity-80">· {bug.jira_status}</span>}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : jiraConfigured && (
                    <button
                      className="inline-flex items-center gap-1 rounded-full border px-2 py-px font-medium text-muted-foreground transition-colors hover:border-blue-300 hover:text-blue-700 disabled:opacity-60 dark:hover:text-blue-400"
                      onClick={(e) => { e.stopPropagation(); setJiraFormOpen(!jiraFormOpen) }}
                      disabled={isBusy}
                      title="Создать задачу в Jira"
                    >
                      {exportMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                      Создать в Jira
                    </button>
                  )}
                  {bug.fix_status === "queued" && (
                    <span className="inline-flex items-center gap-1 rounded-full border px-2 py-px text-muted-foreground">
                      <Bot className="h-3 w-3" /> фикс в очереди
                    </span>
                  )}
                  {bug.fix_status === "running" && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 px-2 py-px text-blue-700 dark:border-blue-900/50 dark:text-blue-400">
                      <Loader2 className="h-3 w-3 animate-spin" /> Claude Code чинит…
                    </span>
                  )}
                  {bug.fix_status === "fix_proposed" && (
                    bug.fix_mr_url ? (
                      <a
                        href={bug.fix_mr_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-px font-medium text-emerald-700 transition-colors hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-400"
                      >
                        <Bot className="h-3 w-3" /> фикс предложен · MR{mrNumber(bug.fix_mr_url)} <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-px font-medium text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-400">
                        <Bot className="h-3 w-3" /> фикс предложен
                      </span>
                    )
                  )}
                  {bug.fix_status === "failed" && (
                    <>
                      <span className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2 py-px font-medium text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400" title={bug.fix_error ?? undefined}>
                        <Bot className="h-3 w-3" /> фикс не удался
                      </span>
                      <button
                        className="rounded-full border px-2 py-px font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60"
                        onClick={(e) => { e.stopPropagation(); fixMut.mutate(index) }}
                        disabled={isBusy}
                      >
                        {fixMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Повторить"}
                      </button>
                    </>
                  )}
                </div>

                {bug.fix_status === "fix_proposed" && bug.fix_summary && (
                  <p className={cn("max-w-4xl text-[0.75rem] leading-[1.55] text-muted-foreground", !open && "line-clamp-2")}>{bug.fix_summary}</p>
                )}
                {bug.fix_status === "failed" && bug.fix_error && (
                  <p className={cn("max-w-4xl text-[0.75rem] leading-[1.55] text-red-700 dark:text-red-400", !open && "line-clamp-2")}>{bug.fix_error}</p>
                )}
                {exportMut.error && <p className="text-[0.75rem] text-destructive">{(exportMut.error as Error).message}</p>}
                {fixMut.error && <p className="text-[0.75rem] text-destructive">{(fixMut.error as Error).message}</p>}
              </div>
            </div>
          </div>

          {jiraFormOpen && !bug.jira_key && (
            <div className="mx-5 mb-4 ml-12 rounded-lg border border-blue-200/70 bg-blue-50/40 p-3.5 dark:border-blue-900/40 dark:bg-blue-950/10">
              <p className="text-[0.75rem] font-medium text-foreground/80">Создать задачу в Jira</p>
              <Input
                value={featureTicket}
                onChange={(e) => setFeatureTicket(e.target.value)}
                placeholder="Feature Link — тикет фичи, напр. MTSPAY-14684 (необязательно)"
                className="mt-2 bg-background text-sm"
                disabled={exportMut.isPending}
                onClick={(e) => e.stopPropagation()}
              />
              <div className="mt-2.5 flex items-center gap-2">
                <button
                  className="flex items-center gap-1.5 rounded-md bg-blue-600 px-3.5 py-1.5 text-[0.75rem] font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-60"
                  onClick={(e) => {
                    e.stopPropagation()
                    exportMut.mutate(
                      { bugIndex: index, featureTicket: featureTicket.trim() || null },
                      { onSuccess: () => { setJiraFormOpen(false); setFeatureTicket("") } },
                    )
                  }}
                  disabled={isBusy}
                >
                  {exportMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                  Создать
                </button>
                <button
                  className="rounded-md px-2.5 py-1.5 text-[0.75rem] text-muted-foreground transition-colors hover:text-foreground"
                  onClick={(e) => { e.stopPropagation(); setJiraFormOpen(false); setFeatureTicket("") }}
                  disabled={exportMut.isPending}
                >
                  Отмена
                </button>
              </div>
            </div>
          )}

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
  const syncJiraMut = useSyncJiraStatuses(projectSlug, featureName)
  const [statusFilter, setStatusFilter] = useState<BugStatusFilter>("all")
  const [severityFilter, setSeverityFilter] = useState<BugSeverity | "all">("all")
  const [query, setQuery] = useState("")

  const bugs = bugsData?.bugs ?? []
  const jiraConfigured = bugsData?.jira_configured ?? false

  // Refresh Jira statuses once per opened feature — silently, stale data stays on error
  const syncedFor = useRef<string | null>(null)
  const hasExported = bugs.some((bug) => bug.jira_key)
  const syncKey = `${projectSlug}/${featureName}`
  useEffect(() => {
    if (!jiraConfigured || !hasExported || syncedFor.current === syncKey) return
    syncedFor.current = syncKey
    syncJiraMut.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jiraConfigured, hasExported, syncKey])
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
    <div className="space-y-4">
      <section className="space-y-3 rounded-xl border bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <h2 className="text-base font-semibold">Баг-репорты</h2>
          <StatStrip
            className="flex-1"
            items={[
              { value: openCount, label: "открыто", tone: openCount > 0 ? "danger" : "default" },
              { value: fixedCount, label: "исправлено", tone: fixedCount > 0 ? "warning" : "default" },
              { value: verifiedCount, label: "проверено", tone: verifiedCount > 0 ? "success" : "default" },
              { value: criticalCount, label: "критичных", tone: criticalCount > 0 ? "danger" : "default" },
            ]}
          />
        </div>
        {bugs.length > 0 && (
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${(resolvedCount / bugs.length) * 100}%` }} />
          </div>
        )}
      </section>

      {bugs.length > 0 && (
        <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-2 rounded-lg bg-background/95 px-1 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <Segmented<BugStatusFilter>
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: "all", label: "Все", count: bugs.length },
              { value: "open", label: "Открытые", count: openCount },
              { value: "fixed", label: "Исправленные", count: fixedCount },
              { value: "verified", label: "Проверенные", count: verifiedCount },
            ]}
          />
          <FilterSelect<BugSeverity | "all">
            ariaLabel="Уровень"
            value={severityFilter}
            onChange={setSeverityFilter}
            options={[
              { value: "all", label: "Все уровни" },
              ...(["critical", "major", "minor", "trivial"] as BugSeverity[]).map((severity) => ({ value: severity, label: SEVERITY_LABEL[severity] })),
            ]}
          />
          <div className="relative ml-auto min-w-[15rem]">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название, кейс или результат" className="h-7 pl-8 text-xs" />
          </div>
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
      <div className="space-y-5">
        {grouped.map(({ severity, items }) => (
          <div key={severity}>
            <div className="mb-2 flex items-center gap-2 px-1">
              <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {SEVERITY_LABEL[severity]}
              </p>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] text-muted-foreground">{items.length}</span>
            </div>
            <div className="space-y-1.5">
              {items.map(({ bug, idx }) => (
                <BugCard
                  key={`${bug.severity}-${idx}`}
                  bug={bug}
                  index={idx}
                  projectSlug={projectSlug}
                  featureName={featureName}
                  jiraConfigured={jiraConfigured}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
