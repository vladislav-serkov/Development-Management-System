import { useEffect, useState, type ReactNode } from "react"
import { AlertTriangle, Check, ChevronDown, ChevronRight, Paperclip, RotateCcw, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { useConfirm } from "@/components/ConfirmDialog"
import { useAssistantTurnActions } from "@/hooks/useAssistant"
import { useGenerateBug } from "@/hooks/useBugs"
import { useAssistantStore } from "@/stores/assistantStore"
import { diffLines } from "@/lib/diff"
import { prettyJsonOrRaw } from "@/lib/artifacts"
import { attachmentLabel, isErrorAttachment, type CaseIndex } from "@/lib/assistant"
import { countLabel } from "@/lib/plural"
import { cn } from "@/lib/utils"
import type {
  AssistantAction,
  AssistantChange,
  AssistantSuggestion,
  AssistantTurn,
  TestCaseItem,
  TestStep,
} from "@/types/api"

const FIELD_LABEL: Record<string, string> = {
  name: "Название",
  preconditions: "Предусловия",
  steps: "Шаги",
  expected_result: "Ожидаемый результат",
  priority: "Приоритет",
  curl_command: "Запрос",
  kafka_message: "Kafka",
  sql_setup: "SQL",
  mock_config: "Мок",
}

const STAGE_LABEL: Record<NonNullable<AssistantTurn["stage"]>, string> = {
  waiting: "Ждёт своей очереди",
  thinking: "Думает над ответом",
  acting: "Выполняет действие на стенде",
  verifying: "Проверяет правку на стенде",
  saving: "Сохраняет правки",
}

function fieldText(field: string, value: unknown): string {
  if (value === null || value === undefined) return ""
  if (field === "steps") {
    return (value as TestStep[]).map((s, i) => `${i + 1}. ${s.action}\n   → ${s.expected}`).join("\n")
  }
  if (field === "kafka_message") {
    const message = value as { key: string; value: string }
    return `key: ${message.key}\n${prettyJsonOrRaw(message.value)}`
  }
  if (field === "mock_config") return prettyJsonOrRaw(String(value))
  return String(value)
}

function useElapsed(since: string | undefined): string {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!since) return ""
  const seconds = Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
}

function CaseLink({ caseId, cases, fallback }: { caseId: string | undefined; cases: CaseIndex; fallback: string }) {
  const openCase = useAssistantStore((s) => s.openCase)
  const found = caseId ? cases.get(caseId) : undefined
  if (!caseId || !found) return <span className="text-muted-foreground line-through">{fallback}</span>
  return (
    <button
      onClick={() => openCase(caseId)}
      title={found.name}
      className="rounded px-0.5 font-medium text-blue-700 underline-offset-2 hover:underline dark:text-blue-300"
    >
      #{found.number}
    </button>
  )
}

/** Assistant text: `code` spans and #N references that open the case. */
function ReplyText({ text, turn, cases }: { text: string; turn: AssistantTurn; cases: CaseIndex }) {
  const parts = text.split(/(`[^`\n]+`|#\d{1,4}\b)/)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return (
            <code key={i} className="rounded bg-muted px-1 py-px font-mono text-[0.75rem]">
              {part.slice(1, -1)}
            </code>
          )
        }
        if (/^#\d{1,4}$/.test(part)) {
          return <CaseLink key={i} caseId={turn.numbering?.[part.slice(1)]} cases={cases} fallback={part} />
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

function WriteBadge() {
  return (
    <span
      title="Действие изменило данные на стенде"
      className="shrink-0 rounded border border-amber-300 px-1 text-[0.625rem] font-medium leading-4 text-amber-800 dark:border-amber-800 dark:text-amber-300"
    >
      запись
    </span>
  )
}

function ActionRow({ action }: { action: AssistantAction }) {
  const [open, setOpen] = useState(false)
  return (
    <li>
      <button
        className="flex w-full items-start gap-2 px-3 py-1.5 text-left hover:bg-muted/40"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="mt-0.5 shrink-0">
          {action.status === "ok" ? (
            <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
          ) : action.status === "blocked" ? (
            <X className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5 text-[0.8125rem] leading-5">
            <span className="[overflow-wrap:anywhere]">{action.title}</span>
            {action.write && action.status === "ok" && <WriteBadge />}
          </span>
          {action.summary && (
            <span
              className={cn(
                "block text-[0.75rem] leading-5 [overflow-wrap:anywhere]",
                action.status === "ok" ? "text-muted-foreground" : "text-destructive",
                action.status === "blocked" && "text-amber-800 dark:text-amber-300",
              )}
            >
              {action.status === "blocked" ? "Не выполнено: " : ""}
              {action.summary}
            </span>
          )}
        </span>
        {open ? (
          <ChevronDown className="mt-1 h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-1 h-3 w-3 shrink-0 text-muted-foreground" />
        )}
      </button>
      {open && action.detail && (
        <pre className="mx-3 mb-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted px-2.5 py-2 font-mono text-[0.6875rem] leading-5">
          {action.detail}
        </pre>
      )}
    </li>
  )
}

function Journal({ actions, defaultOpen }: { actions: AssistantAction[]; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  if (actions.length === 0) return null
  const writes = actions.filter((a) => a.write && a.status === "ok").length
  return (
    <div className="overflow-hidden rounded-xl border">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[0.75rem]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="font-semibold">Что сделал на стенде</span>
        <span className="text-muted-foreground">
          {countLabel(actions.length, ["действие", "действия", "действий"])}
          {writes > 0 ? ` · ${countLabel(writes, ["запись", "записи", "записей"])}` : ""}
        </span>
        {open ? (
          <ChevronDown className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>
      {open && (
        <ol className="border-t py-1">
          {actions.map((action) => (
            <ActionRow key={action.id} action={action} />
          ))}
        </ol>
      )}
    </div>
  )
}

function FieldDiff({ field, before, after }: { field: string; before: unknown; after: unknown }) {
  if (field === "priority") {
    return (
      <p className="px-3 py-1 font-mono text-[0.75rem] text-muted-foreground">
        {String(before ?? "—")} → <span className="text-foreground">{String(after ?? "—")}</span>
      </p>
    )
  }
  const lines = diffLines(fieldText(field, before), fieldText(field, after))
  return (
    <div className="max-h-72 overflow-auto py-1 font-mono text-[0.75rem] leading-5">
      {lines.map((line, i) =>
        line.type === "skip" ? (
          <div key={i} className="px-3 text-muted-foreground/70">
            ⋯
          </div>
        ) : (
          <div
            key={i}
            className={cn(
              "whitespace-pre-wrap break-words px-3",
              line.type === "add" && "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300",
              line.type === "del" && "bg-red-50 text-red-800 line-through decoration-red-300 dark:bg-red-950/30 dark:text-red-300",
              line.type === "same" && "text-muted-foreground",
            )}
          >
            {line.type === "add" ? "+ " : line.type === "del" ? "− " : "  "}
            {line.text || " "}
          </div>
        ),
      )}
    </div>
  )
}

function ChangeCard({
  change,
  turn,
  cases,
  projectSlug,
  featureName,
}: {
  change: AssistantChange
  turn: AssistantTurn
  cases: CaseIndex
  projectSlug: string
  featureName: string
}) {
  const { setChangeState } = useAssistantTurnActions(projectSlug, featureName)
  const openCase = useAssistantStore((s) => s.openCase)
  const found = cases.get(change.case_id)
  const title = change.kind === "add" ? "Новый кейс" : "Правка кейса"
  const fields = (change.fields ?? []).map((f) => FIELD_LABEL[f] ?? f).join(", ")
  const toggle = (action: "revert" | "restore") =>
    setChangeState.mutate({ turnId: turn.id, changeId: change.id, action })

  if (change.state === "reverted") {
    return (
      <div className="flex items-center gap-2 rounded-xl border px-3 py-2 text-[0.8125rem] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate" title={change.case_name}>
          {title} {found ? `#${found.number}` : `«${change.case_name}»`}
          {fields ? ` · ${fields}` : ""}
        </span>
        <span>отменена</span>
        <button
          className="font-medium text-foreground underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => toggle("restore")}
          disabled={setChangeState.isPending}
        >
          Вернуть
        </button>
        {setChangeState.error && <span className="text-destructive">{setChangeState.error.message}</span>}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border">
      <div className="flex items-center gap-2 border-b px-3 py-2 text-[0.75rem]">
        <button
          className="min-w-0 truncate font-semibold hover:underline disabled:no-underline"
          onClick={() => openCase(change.case_id)}
          disabled={!found}
          title={change.case_name}
        >
          {title} {found ? `#${found.number}` : `«${change.case_name}»`}
        </button>
        {fields && <span className="shrink-0 text-muted-foreground">{fields}</span>}
      </div>
      {change.summary && <p className="px-3 pt-2 text-[0.8125rem] leading-5 [overflow-wrap:anywhere]">{change.summary}</p>}
      {change.kind === "add" ? (
        <p className="px-3 py-2 text-[0.8125rem] leading-5 text-muted-foreground [overflow-wrap:anywhere]">{change.case_name}</p>
      ) : (
        (change.fields ?? []).map((field) => (
          <div key={field}>
            {(change.fields ?? []).length > 1 && (
              <p className="px-3 pt-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {FIELD_LABEL[field] ?? field}
              </p>
            )}
            <FieldDiff field={field} before={change.before?.[field]} after={change.after?.[field]} />
          </div>
        ))
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t px-3 py-2 text-[0.8125rem]">
        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <span className="min-w-0 flex-1 text-emerald-700 dark:text-emerald-400">
          {change.kind === "add"
            ? "Добавлен в список"
            : change.stand_check?.status === "ok"
              ? "Сохранено после успешного запуска на стенде"
              : change.stand_check?.status === "skipped"
                ? "Сохранено без проверки: тестовая БД не подключена"
                : "Сохранено в кейсе"}
        </span>
        <button
          className="font-medium underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => toggle("revert")}
          disabled={setChangeState.isPending}
        >
          {change.kind === "add" ? "Убрать кейс" : "Отменить правку"}
        </button>
        {setChangeState.error && <p className="w-full text-[0.75rem] text-destructive">{setChangeState.error.message}</p>}
      </div>
    </div>
  )
}

function SuggestionCard({
  suggestion,
  turn,
  cases,
  testCases,
  projectSlug,
  featureName,
}: {
  suggestion: AssistantSuggestion
  turn: AssistantTurn
  cases: CaseIndex
  testCases: TestCaseItem[]
  projectSlug: string
  featureName: string
}) {
  const confirm = useConfirm()
  const { resolveSuggestion } = useAssistantTurnActions(projectSlug, featureName)
  const generateBug = useGenerateBug(projectSlug, featureName)
  const found = cases.get(suggestion.case_id)
  const busy = resolveSuggestion.isPending || generateBug.isPending
  const resolve = (accept: boolean) =>
    resolveSuggestion.mutate({ turnId: turn.id, suggestionId: suggestion.id, accept })

  async function accept() {
    if (suggestion.kind === "delete") {
      const ok = await confirm({
        title: `Удалить кейс${found ? ` #${found.number}` : ""}?`,
        description: `«${suggestion.case_name}» будет удалён из списка. Это действие нельзя отменить.`,
        confirmText: "Удалить",
        destructive: true,
      })
      if (ok) resolve(true)
      return
    }
    const tcIndex = testCases.findIndex((tc) => tc.id === suggestion.case_id)
    if (tcIndex < 0) return
    generateBug.mutate({ tcIndex, analystText: suggestion.text }, { onSuccess: () => resolve(true) })
  }

  const isBug = suggestion.kind === "bug"
  const done = suggestion.state !== "open"
  return (
    <div
      className={cn(
        "space-y-2 rounded-xl px-3 py-2.5 text-[0.8125rem] leading-5",
        isBug ? "bg-amber-50 text-amber-900 dark:bg-amber-950/20 dark:text-amber-200" : "border",
      )}
    >
      <p className="[overflow-wrap:anywhere]">
        <span className="font-semibold">
          {isBug ? "Похоже на баг сервиса" : "Предлагаю удалить"} ·{" "}
          <CaseLink caseId={suggestion.case_id} cases={cases} fallback={`«${suggestion.case_name}»`} />
        </span>
        <br />
        {suggestion.text}
      </p>
      {done ? (
        <p className="text-[0.75rem] opacity-70">
          {suggestion.state === "dismissed" ? "Отклонено" : isBug ? "Баг-репорт создаётся" : "Кейс удалён"}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant={isBug ? "outline" : "destructive"} onClick={accept} disabled={busy || !found}>
            {isBug ? "Создать баг" : `Удалить${found ? ` #${found.number}` : ""}`}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => resolve(false)} disabled={busy}>
            {isBug ? "Не баг" : "Оставить"}
          </Button>
        </div>
      )}
      {(resolveSuggestion.error || generateBug.error) && (
        <p className="text-[0.75rem] text-destructive">{(resolveSuggestion.error ?? generateBug.error)?.message}</p>
      )}
    </div>
  )
}

function UserMessage({ turn, cases, children }: { turn: AssistantTurn; cases: CaseIndex; children?: ReactNode }) {
  const queued = turn.status === "queued"
  return (
    <div className="flex max-w-[88%] flex-col items-end gap-1 self-end">
      <div
        className={cn(
          "flex flex-col gap-1.5 rounded-xl px-3 py-2",
          queued ? "border border-dashed border-ring" : "bg-muted",
        )}
      >
        {turn.attachments.map((attachment, i) => {
          const isError = isErrorAttachment(attachment)
          const quote = attachment.error ?? (attachment.kind === "http_result" ? attachment.body : null)
          return (
            <div key={i} className="flex flex-col gap-1">
              <span
                className={cn(
                  "inline-flex max-w-full items-center gap-1 self-start rounded-md px-2 py-0.5 text-[0.75rem] leading-4",
                  isError ? "bg-destructive/10 text-destructive" : "bg-background text-muted-foreground",
                )}
              >
                <Paperclip className="h-3 w-3 shrink-0" />
                <span className="truncate">{attachmentLabel(attachment, cases)}</span>
              </span>
              {quote && (
                <div className="max-h-24 overflow-hidden rounded-md bg-background px-2 py-1.5 font-mono text-[0.6875rem] leading-[1.125rem] [overflow-wrap:anywhere]">
                  {quote.slice(0, 400)}
                </div>
              )}
            </div>
          )
        })}
        <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{turn.text}</span>
      </div>
      {children}
    </div>
  )
}

export function AssistantTurnView({
  turn,
  cases,
  testCases,
  queuePosition,
  projectSlug,
  featureName,
}: {
  turn: AssistantTurn
  cases: CaseIndex
  testCases: TestCaseItem[]
  /** 1 = next to be answered; only for queued messages */
  queuePosition: number | null
  projectSlug: string
  featureName: string
}) {
  const { cancel, retry, removeQueued } = useAssistantTurnActions(projectSlug, featureName)
  const elapsed = useElapsed(turn.status === "running" ? turn.started_at : undefined)

  if (turn.status === "queued") {
    return (
      <UserMessage turn={turn} cases={cases}>
        <div className="flex items-center gap-2 text-[0.6875rem] text-muted-foreground">
          <span>в очереди{queuePosition === 1 ? " · следующее" : ""}</span>
          <button
            className="font-medium underline-offset-2 hover:underline disabled:opacity-50"
            onClick={() => removeQueued.mutate(turn.id)}
            disabled={removeQueued.isPending}
          >
            Убрать
          </button>
        </div>
      </UserMessage>
    )
  }

  const retryButton = (
    <Button size="sm" variant="outline" className="self-start" onClick={() => retry.mutate(turn.id)} disabled={retry.isPending}>
      <RotateCcw />
      Повторить
    </Button>
  )

  return (
    <>
      <UserMessage turn={turn} cases={cases} />

      {turn.status === "running" && (
        <div className="flex flex-col gap-2 rounded-xl border p-3">
          <div className="flex items-center gap-2">
            <span className="flex-1 font-medium">
              Ассистент работает
              <AnimatedDots />
            </span>
            <span className="text-[0.75rem] tabular-nums text-muted-foreground">{elapsed}</span>
            <Button size="xs" variant="ghost" onClick={() => cancel.mutate(turn.id)} disabled={cancel.isPending}>
              Отменить
            </Button>
          </div>
          <ol className="flex flex-col gap-1 text-[0.8125rem]">
            {turn.actions.map((action) => (
              <li key={action.id} className="flex items-start gap-2 text-muted-foreground">
                {action.status === "ok" ? (
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
                )}
                <span className="min-w-0 [overflow-wrap:anywhere]">{action.title}</span>
              </li>
            ))}
            <li className="flex items-start gap-2">
              <span className="inline-block w-3.5 shrink-0 text-center">·</span>
              <span className="min-w-0 [overflow-wrap:anywhere]">
                {turn.current || STAGE_LABEL[turn.stage ?? "thinking"]}
              </span>
            </li>
          </ol>
          {cancel.error && <p className="text-[0.75rem] text-destructive">{cancel.error.message}</p>}
        </div>
      )}

      {turn.status === "done" && (
        <div className="flex flex-col gap-2.5">
          <Journal actions={turn.actions} defaultOpen={turn.actions.length <= 6} />
          {turn.cause && (
            <div className="rounded-xl bg-muted/50 px-3 py-2">
              <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Причина</p>
              <p className="mt-1 leading-[1.55] [overflow-wrap:anywhere]">
                <ReplyText text={turn.cause} turn={turn} cases={cases} />
              </p>
            </div>
          )}
          <p className="whitespace-pre-wrap leading-[1.55] [overflow-wrap:anywhere]">
            <ReplyText text={turn.reply ?? ""} turn={turn} cases={cases} />
          </p>
          {(turn.failures ?? []).map((failure) => {
            const found = cases.get(failure.case_id)
            return (
              <div key={failure.case_id} className="overflow-hidden rounded-xl border">
                <div className="flex items-center gap-2 border-b px-3 py-2 text-[0.75rem]">
                  <span className="min-w-0 truncate font-semibold" title={failure.case_name}>
                    Кейс {found ? `#${found.number}` : `«${failure.case_name}»`}
                  </span>
                  <span className="shrink-0 text-muted-foreground">
                    {FIELD_LABEL[failure.field] ?? failure.field} · {countLabel(failure.attempts, ["попытка", "попытки", "попыток"])}
                  </span>
                </div>
                <div className="flex items-start gap-2 bg-amber-50 px-3 py-2 text-[0.8125rem] leading-5 text-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span className="[overflow-wrap:anywhere]">Не получилось исправить: {failure.error}. Кейс не изменён.</span>
                </div>
              </div>
            )
          })}
          {(turn.changes ?? []).map((change) => (
            <ChangeCard key={change.id} change={change} turn={turn} cases={cases} projectSlug={projectSlug} featureName={featureName} />
          ))}
          {(turn.suggestions ?? []).map((suggestion) => (
            <SuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              turn={turn}
              cases={cases}
              testCases={testCases}
              projectSlug={projectSlug}
              featureName={featureName}
            />
          ))}
        </div>
      )}

      {(turn.status === "error" || turn.status === "cancelled") && (
        <div className="flex flex-col gap-2.5">
          <Journal actions={turn.actions} defaultOpen />
          <div
            className={cn(
              "flex flex-col gap-2 rounded-xl px-3 py-2.5",
              turn.status === "error" ? "bg-destructive/10" : "bg-muted/50",
            )}
          >
            <p className={cn("text-[0.8125rem] leading-5 [overflow-wrap:anywhere]", turn.status === "error" && "text-destructive")}>
              {turn.status === "cancelled" ? "Остановлено. Правки в кейсы не внесены." : (turn.error ?? "Ассистент не ответил")}
            </p>
            {retryButton}
            {retry.error && <p className="text-[0.75rem] text-destructive">{retry.error.message}</p>}
          </div>
        </div>
      )}
    </>
  )
}
