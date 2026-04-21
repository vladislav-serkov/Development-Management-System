import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AlertCircle, CheckCircle2, FileText, GitBranch, Loader2, Network, Sparkles, TestTube, ArrowRight } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { useProjectTasks } from "@/hooks/useTasks"
import { useProject, useProjectFeatures, useUploadDocument } from "@/hooks/useDocuments"
import { useProjectDependencies } from "@/hooks/useDependencies"
import { useUIStore } from "@/stores/uiStore"
import { ProjectSidebar } from "@/components/sidebar"
import { featurePath } from "@/lib/routes"
import type { TaskKind, TaskRecord, TaskStatus } from "@/types/api"

const KIND_LABELS: Record<TaskKind, string> = {
  extraction: "Извлечение",
  gaps: "Пробелы",
  apply_gaps: "Применение правок",
  test_cases: "Тест-кейсы",
  enrichment: "Обогащение",
}

const KIND_ICONS: Record<TaskKind, typeof FileText> = {
  extraction: FileText,
  gaps: Sparkles,
  apply_gaps: GitBranch,
  test_cases: TestTube,
  enrichment: Network,
}

const STATUS_LABELS: Record<TaskStatus, string> = {
  running: "Выполняется",
  done: "Готово",
  error: "Ошибка",
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "—"
  if (ms < 1000) return `${ms} мс`
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)} с`
  const min = Math.floor(sec / 60)
  const remSec = Math.round(sec % 60)
  return `${min} мин ${remSec} с`
}

function formatTime(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function StatusBadge({ status }: { status: TaskStatus }) {
  if (status === "running") {
    return (
      <Badge variant="outline" className="gap-1 border-amber-400 text-amber-600 dark:text-amber-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        {STATUS_LABELS[status]}
      </Badge>
    )
  }
  if (status === "done") {
    return (
      <Badge variant="outline" className="gap-1 border-emerald-500 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        {STATUS_LABELS[status]}
      </Badge>
    )
  }
  return (
    <Badge variant="destructive" className="gap-1">
      <AlertCircle className="h-3 w-3" />
      {STATUS_LABELS[status]}
    </Badge>
  )
}

function KindChip({ kind }: { kind: TaskKind }) {
  const Icon = KIND_ICONS[kind]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <Icon className="h-3.5 w-3.5" />
      {KIND_LABELS[kind]}
    </span>
  )
}

function TaskTargetLink({ task, projectSlug }: { task: TaskRecord; projectSlug: string }) {
  const navigate = useNavigate()
  if (task.target_type === "feature") {
    return (
      <button
        className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
        onClick={() => navigate(featurePath(projectSlug, task.target_id))}
      >
        {task.target_id}
        <ArrowRight className="h-3 w-3" />
      </button>
    )
  }
  if (task.target_type === "dependency" && !task.target_id.startsWith("bulk:")) {
    // We don't know dep_type from target_id alone; default to link-less display.
    return <span className="font-mono text-xs">{task.target_id}</span>
  }
  if (task.target_type === "document") {
    return <span className="font-mono text-xs">{task.target_id}</span>
  }
  return <span className="font-mono text-xs">{task.target_id}</span>
}

type KindFilter = TaskKind | "all"
type StatusFilter = TaskStatus | "all"

export default function BackgroundTasksPage() {
  const { projectSlug: projectSlugParam } = useParams<{ projectSlug: string }>()
  const projectSlug = projectSlugParam ?? null
  const sidebarWidth = useUIStore((s) => s.sidebarWidth)
  const setSidebarWidth = useUIStore((s) => s.setSidebarWidth)
  const isDragging = useRef(false)

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isDragging.current) return
      setSidebarWidth(e.clientX)
    }
    function onMouseUp() {
      isDragging.current = false
    }
    document.addEventListener("mousemove", onMouseMove)
    document.addEventListener("mouseup", onMouseUp)
    return () => {
      document.removeEventListener("mousemove", onMouseMove)
      document.removeEventListener("mouseup", onMouseUp)
    }
  }, [setSidebarWidth])

  const { data: project } = useProject(projectSlug)
  const { data: allFeatures } = useProjectFeatures(projectSlug, project?.status)
  const features = allFeatures?.filter((f) => f.status === "done")
  const { data: dependencies } = useProjectDependencies(projectSlug)
  const uploadMutation = useUploadDocument(projectSlug ?? "")

  const [kindFilter, setKindFilter] = useState<KindFilter>("all")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const { data, isLoading, error } = useProjectTasks(projectSlug)

  const tasks = data?.tasks ?? []

  const filtered = useMemo(() => {
    return tasks.filter((t) => {
      if (kindFilter !== "all" && t.kind !== kindFilter) return false
      if (statusFilter !== "all" && t.status !== statusFilter) return false
      return true
    })
  }, [tasks, kindFilter, statusFilter])

  const counts = useMemo(() => {
    const running = tasks.filter((t) => t.status === "running").length
    const done = tasks.filter((t) => t.status === "done").length
    const errored = tasks.filter((t) => t.status === "error").length
    return { running, done, errored, total: tasks.length }
  }, [tasks])

  if (!projectSlug || !project) {
    return null
  }

  return (
    <div className="flex h-screen bg-background">
      <ProjectSidebar
        project={project}
        projectSlug={projectSlug}
        features={features}
        dependencies={dependencies}
        selectedFeatureName={null}
        selectedDep={null}
        onUpload={(file) => uploadMutation.mutate(file)}
        isUploading={uploadMutation.isPending}
        sidebarWidth={sidebarWidth}
        onStartDrag={() => {
          isDragging.current = true
        }}
      />

      <main className="flex-1 min-h-0 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl space-y-6">
          <div>
            <h1 className="text-2xl font-semibold">Фоновые задачи</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Журнал запусков пайплайнов извлечения, анализа пробелов, генерации тест-кейсов и обогащения зависимостей.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <SummaryCard label="Всего" value={counts.total} />
            <SummaryCard label="Выполняется" value={counts.running} tone="amber" />
            <SummaryCard label="Успешно" value={counts.done} tone="emerald" />
            <SummaryCard label="Ошибок" value={counts.errored} tone="red" />
          </div>

          <Card>
            <CardContent className="flex flex-wrap items-center gap-2 py-3">
              <FilterGroup
                label="Статус"
                value={statusFilter}
                options={[
                  { value: "all", label: "Все" },
                  { value: "running", label: "Выполняется" },
                  { value: "done", label: "Готово" },
                  { value: "error", label: "Ошибка" },
                ]}
                onChange={(v) => setStatusFilter(v as StatusFilter)}
              />
              <span className="h-5 w-px bg-border" />
              <FilterGroup
                label="Тип"
                value={kindFilter}
                options={[
                  { value: "all", label: "Все" },
                  { value: "extraction", label: "Извлечение" },
                  { value: "gaps", label: "Пробелы" },
                  { value: "apply_gaps", label: "Применение" },
                  { value: "test_cases", label: "Тест-кейсы" },
                  { value: "enrichment", label: "Обогащение" },
                ]}
                onChange={(v) => setKindFilter(v as KindFilter)}
              />
            </CardContent>
          </Card>

          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {error && (
            <p className="text-sm text-destructive">Ошибка загрузки: {(error as Error).message}</p>
          )}
          {!isLoading && !error && filtered.length === 0 && (
            <div className="rounded-xl border border-dashed px-4 py-12 text-center">
              <p className="text-sm font-medium">Задач не найдено</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Либо в проекте ещё не запускались пайплайны, либо фильтры не нашли совпадений.
              </p>
            </div>
          )}

          <div className="space-y-2">
            {filtered.map((task) => (
              <Card key={task.id} className="border-border/70 shadow-none">
                <CardContent className="flex items-start justify-between gap-4 py-3">
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <KindChip kind={task.kind} />
                      <span className="text-muted-foreground/40">•</span>
                      <TaskTargetLink task={task} projectSlug={projectSlug} />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span>Начало: {formatTime(task.started_at)}</span>
                      {task.finished_at && <span>Конец: {formatTime(task.finished_at)}</span>}
                      <span>Длительность: {formatDuration(task.duration_ms)}</span>
                    </div>
                    {task.error_message && (
                      <p className="mt-1 rounded border border-destructive/30 bg-destructive/5 px-2 py-1 font-mono text-[0.7rem] text-destructive">
                        {task.error_message}
                      </p>
                    )}
                  </div>
                  <StatusBadge status={task.status} />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  tone = "default",
}: {
  label: string
  value: number
  tone?: "default" | "amber" | "emerald" | "red"
}) {
  const colorClass = {
    default: "text-foreground",
    amber: "text-amber-600 dark:text-amber-400",
    emerald: "text-emerald-600 dark:text-emerald-400",
    red: "text-destructive",
  }[tone]
  return (
    <Card className="border-border/70 shadow-none">
      <CardContent className="py-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-1 text-2xl font-semibold tabular-nums ${colorClass}`}>{value}</p>
      </CardContent>
    </Card>
  )
}

function FilterGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-muted-foreground">{label}:</span>
      <div className="flex gap-1">
        {options.map((opt) => (
          <button
            key={opt.value}
            className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
              value === opt.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent"
            }`}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

