import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowUp, ChevronDown, MessageSquare, Paperclip, Plus, Sparkles, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { useConfirm } from "@/components/ConfirmDialog"
import {
  useAssistantOverview,
  useAssistantSession,
  useDeleteAssistantSession,
  useSendAssistantMessage,
} from "@/hooks/useAssistant"
import { useFeatureTestCases } from "@/hooks/useTestCases"
import { assistantKey, useAssistantDraft, useAssistantStore } from "@/stores/assistantStore"
import { attachmentLabel, buildCaseIndex, isErrorAttachment } from "@/lib/assistant"
import { countLabel } from "@/lib/plural"
import { cn } from "@/lib/utils"
import type { AssistantAttachment, AssistantOverview, AssistantSessionSummary } from "@/types/api"
import { AssistantTurnView } from "./AssistantTurnView"

/** First-message ideas: the label is shown, the text lands in the input to be finished */
const STARTERS = [
  { label: "Почему SQL не выполнился на стенде", text: "Посмотри, почему SQL не выполнился на стенде в кейсе #" },
  { label: "Замени тестовые данные в кейсе…", text: "Замени тестовые данные в кейсе # на " },
  { label: "Добавь негативные кейсы на шаг…", text: "Добавь негативные кейсы на шаг " },
  { label: "Какие шаги ТЗ не покрыты кейсами", text: "Какие шаги ТЗ не покрыты кейсами?" },
]

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
}

/** What the assistant can do by itself on this feature's stand, in one sentence. */
function standSummary(stand: AssistantOverview["stand"]): string {
  const can = [
    stand.sql && "выполняет SQL в тестовой БД",
    stand.http && "вызывает сервис на стенде",
    stand.wiremock && "загружает моки",
  ].filter(Boolean)
  if (can.length === 0) return "Стенд не подключён: ассистент работает только с текстом кейсов и ТЗ."
  const schemas = stand.write_schemas
  const limit = stand.sql
    ? schemas.length > 0
      ? ` Запись в БД — только в ${schemas.length === 1 ? "схему" : "схемы"} ${schemas.join(", ")}.`
      : " Записывать в БД не может: неизвестно, в какие схемы пишет эта фича."
    : ""
  return `Сам ${can.join(", ")}.${limit}`
}

function SessionList({
  sessions,
  currentId,
  onPick,
  onNew,
  onDelete,
}: {
  sessions: AssistantSessionSummary[]
  currentId: string | null
  onPick: (id: string) => void
  onNew: () => void
  onDelete: (session: AssistantSessionSummary) => void
}) {
  return (
    <div className="absolute inset-x-3 top-[3.25rem] z-20 max-h-[70%] overflow-y-auto rounded-xl border bg-popover p-1 shadow-lg">
      <button
        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm font-medium hover:bg-muted"
        onClick={onNew}
      >
        <Plus className="h-4 w-4" />
        Новая сессия
      </button>
      {sessions.length > 0 && (
        <p className="px-2.5 pb-1 pt-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Сессии по этой фиче
        </p>
      )}
      {sessions.map((session) => (
        <div
          key={session.id}
          className={cn("group flex items-center gap-1 rounded-lg hover:bg-muted", session.id === currentId && "bg-muted")}
        >
          <button className="min-w-0 flex-1 px-2.5 py-2 text-left" onClick={() => onPick(session.id)}>
            <span className="block truncate text-sm">{session.title}</span>
            <span className="block truncate text-[0.6875rem] text-muted-foreground">
              {session.author ? `${session.author} · ` : ""}
              {formatWhen(session.updated_at)} · {countLabel(session.turn_count, ["сообщение", "сообщения", "сообщений"])}
              {session.state === "running" && (
                <>
                  {" · работает"}
                  <AnimatedDots />
                </>
              )}
              {session.state === "queued" && " · в очереди"}
            </span>
          </button>
          {session.state !== "running" && (
            <Button
              size="icon-xs"
              variant="ghost"
              className="mr-1.5 text-muted-foreground opacity-0 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
              aria-label={`Удалить сессию «${session.title}»`}
              onClick={() => onDelete(session)}
            >
              <Trash2 />
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}

export function AssistantPanel({
  projectSlug,
  featureName,
  featureTitle,
}: {
  projectSlug: string
  featureName: string
  featureTitle: string
}) {
  const key = assistantKey(projectSlug, featureName)
  const confirm = useConfirm()
  const setOpen = useAssistantStore((s) => s.setOpen)
  const chooseSession = useAssistantStore((s) => s.chooseSession)
  const chosen = useAssistantStore((s) => s.sessions[key])
  const setText = useAssistantStore((s) => s.setText)
  const detach = useAssistantStore((s) => s.detach)
  const clearDraft = useAssistantStore((s) => s.clearDraft)
  const outbox = useAssistantStore((s) => s.outbox)
  const takeOutbox = useAssistantStore((s) => s.takeOutbox)
  const draft = useAssistantDraft(key)

  const { data: overview, error: overviewError } = useAssistantOverview(projectSlug, featureName, true)
  const { data: tcData } = useFeatureTestCases(projectSlug, featureName)
  const testCases = useMemo(() => tcData?.test_cases ?? [], [tcData])
  const cases = useMemo(() => buildCaseIndex(testCases), [testCases])

  const sessions = overview?.sessions ?? []
  // Nothing chosen yet → continue the most recent conversation
  const sessionId = chosen === undefined ? (sessions[0]?.id ?? null) : chosen
  const { data: session, error: sessionError } = useAssistantSession(projectSlug, featureName, sessionId)
  const send = useSendAssistantMessage(projectSlug, featureName)
  const deleteSession = useDeleteAssistantSession(projectSlug, featureName)
  const [showSessions, setShowSessions] = useState(false)

  const turns = session?.turns ?? []
  const queuedIds = turns.filter((t) => t.status === "queued").map((t) => t.id)
  const busy = sessions.some((s) => s.state !== "idle") || turns.some((t) => t.status === "running" || t.status === "queued")
  const title = sessionId ? (session?.title ?? sessions.find((s) => s.id === sessionId)?.title ?? "Сессия") : "Новая сессия"

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const last = turns[turns.length - 1]
  const scrollSignal = `${sessionId}:${turns.length}:${last?.status}:${last?.actions.length}`

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [scrollSignal])

  useEffect(() => {
    inputRef.current?.focus()
  }, [sessionId, draft.attachments.length])

  function submit(text: string, attachments: AssistantAttachment[], onSent?: () => void) {
    send.mutate(
      { text, attachments, session_id: sessionId },
      {
        onSuccess: (turn) => {
          chooseSession(key, turn.session_id)
          onSent?.()
        },
      },
    )
  }

  // A message queued from a case card ("Исправить с ассистентом") is sent as soon as
  // the panel knows which session is current
  const sessionsLoaded = overview !== undefined
  useEffect(() => {
    if (!outbox || outbox.key !== key || !sessionsLoaded) return
    takeOutbox()
    submit(outbox.text, outbox.attachments)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reacts to the outbox only
  }, [outbox, key, sessionsLoaded])

  function handleSend() {
    const text = draft.text.trim()
    if (!text || send.isPending) return
    submit(text, draft.attachments, () => clearDraft(key))
  }

  async function handleDelete(target: AssistantSessionSummary) {
    const ok = await confirm({
      title: "Удалить сессию?",
      description: `«${target.title}» и её журнал действий будут удалены. Правки в кейсах останутся.`,
      confirmText: "Удалить",
      destructive: true,
    })
    if (!ok) return
    deleteSession.mutate(target.id, {
      onSuccess: () => {
        if (target.id === sessionId) chooseSession(key, null)
      },
    })
  }

  return (
    <aside
      aria-label="Ассистент"
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[400px] flex-col border-l bg-background text-sm shadow-xl xl:relative xl:inset-auto xl:z-auto xl:w-[400px] xl:shrink-0 xl:shadow-none"
    >
      <div className="flex items-center gap-1.5 border-b px-3 py-2.5">
        <Sparkles className="ml-1 h-4 w-4 shrink-0" />
        <span className="font-semibold">Ассистент</span>
        <Button
          size="xs"
          variant="ghost"
          className="min-w-0 flex-1 justify-start text-muted-foreground"
          aria-expanded={showSessions}
          aria-label="Сессии"
          onClick={() => setShowSessions((v) => !v)}
        >
          <span className="min-w-0 truncate">{title}</span>
          <ChevronDown />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          className="text-muted-foreground"
          aria-label="Новая сессия"
          title="Новая сессия — с чистым контекстом"
          onClick={() => {
            chooseSession(key, null)
            setShowSessions(false)
          }}
        >
          <Plus />
        </Button>
        <Button size="icon-sm" variant="ghost" className="text-muted-foreground" aria-label="Закрыть панель" onClick={() => setOpen(false)}>
          <X />
        </Button>
      </div>

      {showSessions && (
        <SessionList
          sessions={sessions}
          currentId={sessionId}
          onPick={(id) => {
            chooseSession(key, id)
            setShowSessions(false)
          }}
          onNew={() => {
            chooseSession(key, null)
            setShowSessions(false)
          }}
          onDelete={handleDelete}
        />
      )}

      <div ref={threadRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4" onClick={() => setShowSessions(false)}>
        <div className="mt-auto flex flex-col gap-4">
          {overviewError && <p className="text-[0.8125rem] text-destructive">{overviewError.message}</p>}
          {sessionId && sessionError && (
            <p className="text-[0.8125rem] text-destructive">{sessionError.message}</p>
          )}

          {turns.length === 0 && !(sessionId && !session && !sessionError) && (
            <>
              <div className="flex flex-col gap-1.5">
                <h2 className="text-base font-semibold leading-snug [overflow-wrap:anywhere]">Тест-кейсы {featureTitle}</h2>
                <p className="leading-[1.55] text-muted-foreground">
                  Попросите разобрать ошибку SQL или запроса, заменить тестовые данные, добавить кейс. Ассистент видит ТЗ
                  {testCases.length > 0 ? ` и ${countLabel(testCases.length, ["кейс", "кейса", "кейсов"])}` : ""}.{" "}
                  {overview ? standSummary(overview.stand) : ""}
                </p>
              </div>
              <div className="flex flex-col gap-1.5">
                {STARTERS.map((starter) => (
                  <button
                    key={starter.label}
                    className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-left hover:bg-muted"
                    onClick={() => {
                      setText(key, starter.text)
                      inputRef.current?.focus()
                    }}
                  >
                    <span className="flex-1">{starter.label}</span>
                    <ArrowUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
              <div className="flex items-start gap-2 rounded-lg bg-muted px-3 py-2.5 text-[0.8125rem] leading-5">
                <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Чтобы обсудить конкретный кейс, нажмите «Обсудить» на его карточке — кейс прикрепится к сообщению.</span>
              </div>
            </>
          )}

          {turns.map((turn) => (
            <AssistantTurnView
              key={turn.id}
              turn={turn}
              cases={cases}
              testCases={testCases}
              queuePosition={turn.status === "queued" ? queuedIds.indexOf(turn.id) + 1 : null}
              projectSlug={projectSlug}
              featureName={featureName}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t px-4 pb-4 pt-3">
        {overview && !overview.enabled && (
          <p className="text-[0.75rem] text-amber-800 dark:text-amber-300">
            Codex отключён на сервере — ассистент не сможет ответить.
          </p>
        )}
        {draft.attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {draft.attachments.map((attachment, i) => (
              <span
                key={`${attachment.kind}-${attachment.case_id}`}
                className={cn(
                  "inline-flex max-w-full items-center gap-1 rounded-md py-0.5 pl-2 pr-1 text-[0.75rem] leading-4",
                  isErrorAttachment(attachment) ? "bg-destructive/10 text-destructive" : "bg-muted text-foreground",
                )}
              >
                <Paperclip className="h-3 w-3 shrink-0" />
                <span className="truncate" title={cases.get(attachment.case_id)?.name}>
                  {attachmentLabel(attachment, cases)}
                </span>
                <button
                  className="rounded p-0.5 opacity-70 hover:opacity-100"
                  aria-label="Открепить"
                  onClick={() => detach(key, i)}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-input px-2.5 py-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <textarea
            ref={inputRef}
            aria-label="Сообщение ассистенту"
            rows={2}
            value={draft.text}
            onChange={(e) => setText(key, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="Что разобрать, поправить или добавить"
            className="max-h-40 min-h-10 min-w-0 flex-1 resize-none bg-transparent text-sm leading-5 outline-none [field-sizing:content] placeholder:text-muted-foreground"
          />
          <Button
            size="icon-sm"
            aria-label={busy ? "Поставить в очередь" : "Отправить"}
            onClick={handleSend}
            disabled={!draft.text.trim() || send.isPending}
          >
            <ArrowUp />
          </Button>
        </div>
        {send.error && <p className="text-[0.75rem] text-destructive">{send.error.message}</p>}
        {deleteSession.error && <p className="text-[0.75rem] text-destructive">{deleteSession.error.message}</p>}
        <p className="text-[0.6875rem] text-muted-foreground">
          {busy
            ? "Ассистент занят: новое сообщение встанет в очередь."
            : "Ответ занимает 1–2 минуты. Страницу можно закрыть — он сохранится."}
        </p>
      </div>
    </aside>
  )
}
