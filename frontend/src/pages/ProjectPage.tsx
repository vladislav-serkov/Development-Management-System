import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useUIStore } from "@/stores/uiStore"
import { useProject, useUploadDocument, useProjectFeatures, useSaveFeature, useDeleteFeature } from "@/hooks/useDocuments"
import { useProjectDependencies } from "@/hooks/useDependencies"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProjectSidebar, MethodBadge } from "@/components/sidebar"
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Files,
  FolderKanban,
  Gauge,
  Inbox,
  Pencil,
  Sparkles,
  Trash2,
  Workflow,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { dependencyPath, featurePath, isFeatureTab, projectPath, type FeatureTab } from "@/lib/routes"
import type {
  FeatureResponse,
  ProjectDependency,
  StructuredBusinessLogic,
} from "@/types/api"

const StructuredLogicView = lazy(() =>
  import("@/components/feature/StructuredLogicView").then((module) => ({ default: module.StructuredLogicView }))
)
const GapsView = lazy(() =>
  import("@/components/feature/GapsView").then((module) => ({ default: module.GapsView }))
)
const TestCasesView = lazy(() =>
  import("@/components/feature/TestCasesView").then((module) => ({ default: module.TestCasesView }))
)
const BugsView = lazy(() =>
  import("@/components/feature/BugsView").then((module) => ({ default: module.BugsView }))
)
const DependencyDetail = lazy(() =>
  import("@/components/dependency/DependencyDetail").then((module) => ({ default: module.DependencyDetail }))
)

export default function ProjectPage() {
  const navigate = useNavigate()
  const {
    projectSlug: projectSlugParam,
    featureName: featureNameParam,
    tab: tabParam,
    depType: depTypeParam,
    depName: depNameParam,
  } = useParams()
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

  const { data: project, isLoading: projectLoading } = useProject(projectSlug)
  const { data: allFeatures } = useProjectFeatures(projectSlug, project?.status)
  const features = allFeatures?.filter(f => f.status === "done" || f.status === "error")
  const { data: dependencies } = useProjectDependencies(projectSlug)
  const uploadMutation = useUploadDocument(projectSlug!)

  const activeFeatureTab: FeatureTab = isFeatureTab(tabParam) ? tabParam : "logic"
  const selectedFeature = features?.find((feature) => feature.name === featureNameParam) ?? null
  const selectedDep = dependencies?.find((dep) => dep.dep_type === depTypeParam && dep.name === depNameParam) ?? null

  useEffect(() => {
    if (!projectSlug || !featureNameParam || !tabParam || isFeatureTab(tabParam)) return
    navigate(featurePath(projectSlug, featureNameParam, "logic"), { replace: true })
  }, [featureNameParam, navigate, projectSlug, tabParam])

  useEffect(() => {
    if (!projectSlug || !featureNameParam || !features || selectedFeature) return
    navigate(projectPath(projectSlug), { replace: true })
  }, [featureNameParam, features, navigate, projectSlug, selectedFeature])

  useEffect(() => {
    if (!projectSlug || !depTypeParam || !depNameParam || !dependencies || selectedDep) return
    navigate(projectPath(projectSlug), { replace: true })
  }, [dependencies, depNameParam, depTypeParam, navigate, projectSlug, selectedDep])

  if (projectLoading || !project) {
    return <div className="p-8 text-sm text-muted-foreground">Загрузка проекта...</div>
  }

  const contentKey = selectedDep
    ? `dep-${selectedDep.dep_type}-${selectedDep.name}`
    : selectedFeature
      ? `feature-${selectedFeature.name}-${activeFeatureTab}`
      : "none"

  return (
    <div className="flex h-screen bg-background">
      <ProjectSidebar
        project={project}
        projectSlug={projectSlug!}
        features={features}
        dependencies={dependencies}
        selectedFeatureName={selectedFeature?.name ?? null}
        selectedDep={selectedDep}
        onUpload={(file) => uploadMutation.mutate(file)}
        isUploading={uploadMutation.isPending}
        sidebarWidth={sidebarWidth}
        onStartDrag={() => { isDragging.current = true }}
      />

      <main className="flex-1 min-h-0 overflow-y-auto p-6">
        <ProjectContentArea
          key={contentKey}
          projectSlug={projectSlug!}
          projectName={project.name}
          projectDocumentCount={project.document_count}
          selectedFeature={selectedFeature}
          selectedDep={selectedDep}
          projectDependencies={dependencies}
          features={features}
          onDepClick={(dep) => navigate(dependencyPath(projectSlug!, dep.dep_type, dep.name))}
          activeFeatureTab={activeFeatureTab}
          onFeatureTabChange={(tab) => {
            if (selectedFeature) {
              navigate(featurePath(projectSlug!, selectedFeature.name, tab))
            }
          }}
        />
      </main>
    </div>
  )
}

function ProjectContentArea({
  projectSlug,
  projectName,
  projectDocumentCount,
  selectedFeature,
  selectedDep,
  projectDependencies,
  features,
  onDepClick,
  activeFeatureTab,
  onFeatureTabChange,
}: {
  projectSlug: string
  projectName: string
  projectDocumentCount: number
  selectedFeature: FeatureResponse | null
  selectedDep: ProjectDependency | null
  projectDependencies?: ProjectDependency[]
  features?: FeatureResponse[]
  onDepClick?: (dep: ProjectDependency) => void
  activeFeatureTab: FeatureTab
  onFeatureTabChange: (tab: FeatureTab) => void
}) {
  const navigate = useNavigate()
  const saveFeatureMutation = useSaveFeature(projectSlug)
  const deleteFeatureMutation = useDeleteFeature(projectSlug)

  const [isEditing, setIsEditing] = useState(false)
  const [editedLogic, setEditedLogic] = useState<StructuredBusinessLogic | null>(null)
  const [editName, setEditName] = useState("")
  const [editMethod, setEditMethod] = useState("")
  const [editEndpoint, setEditEndpoint] = useState("")
  const [editSummary, setEditSummary] = useState("")
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false)

  const startEdit = () => {
    if (!selectedFeature) return
    setEditName(selectedFeature.name)
    setEditMethod(selectedFeature.method ?? "")
    setEditEndpoint(selectedFeature.endpoint ?? "")
    setEditSummary(selectedFeature.summary ?? "")
    setEditedLogic(structuredClone(selectedFeature.structured_logic ?? {}))
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setIsEditing(false)
    setEditedLogic(null)
  }

  const handleSave = () => {
    if (!selectedFeature) return

    const patch: Record<string, unknown> = {}
    if (editName.trim() && editName.trim() !== selectedFeature.name) patch.name = editName.trim()
    if (editMethod && editMethod !== selectedFeature.method) patch.method = editMethod
    if (editEndpoint !== (selectedFeature.endpoint ?? "")) patch.endpoint = editEndpoint
    if (editSummary !== (selectedFeature.summary ?? "")) patch.summary = editSummary
    if (editedLogic) patch.structured_logic_json = editedLogic as Record<string, unknown>

    const newName = (patch.name as string | undefined) ?? selectedFeature.name

    saveFeatureMutation.mutate(
      { featureName: selectedFeature.name, patch },
      {
        onSuccess: () => {
          setIsEditing(false)
          setEditedLogic(null)
          if (patch.name) {
            navigate(featurePath(projectSlug, newName, activeFeatureTab), { replace: true })
          }
        },
      }
    )
  }

  if (selectedDep) {
    return (
      <Suspense fallback={<ContentLoadingState label="Загрузка детали зависимости..." />}>
        <DependencyDetail dep={selectedDep} projectSlug={projectSlug} />
      </Suspense>
    )
  }

  if (selectedFeature && selectedFeature.status === "error") {
    return (
      <div className="space-y-6">
        <Card className="border border-destructive/30 bg-destructive/5">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-destructive/10 p-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
              </div>
              <div>
                <CardTitle className="text-lg">Ошибка извлечения</CardTitle>
                <CardDescription>Не удалось извлечь фичу «{selectedFeature.name}» из PDF</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedFeature.error_message && (
              <div className="rounded-lg border border-destructive/20 bg-background p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Подробности</p>
                <p className="mt-1 text-sm">{selectedFeature.error_message}</p>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              Попробуйте загрузить PDF повторно или убедитесь, что документ содержит читаемое техническое задание.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (selectedFeature) {
    const displayLogic = isEditing ? (editedLogic ?? selectedFeature.structured_logic) : selectedFeature.structured_logic
    const resolvedMethod = editMethod || selectedFeature.method || (selectedFeature.type === "kafka_consumer" ? "CONSUMER" : "GET")
    const integrationMeta = getFeatureIntegrationMeta(selectedFeature, isEditing ? editEndpoint : selectedFeature.endpoint)
    const integrationFieldLabel = selectedFeature.type === "rest_endpoint" ? "Маршрут" : "Точка интеграции"
    const integrationFieldPlaceholder =
      selectedFeature.type === "rest_endpoint"
        ? "/api/resource"
        : selectedFeature.type === "kafka_consumer"
          ? "pay-later.adapter.topic"
          : "Опишите точку интеграции"
    const featureSummary = selectedFeature.summary ?? "Добавьте краткое описание, чтобы экран было проще сканировать и обсуждать с командой."
    const canCollapseSummary = !isEditing && featureSummary.length > 240

    return (
      <div className="space-y-6">
        {isEditing && (
          <div className="-mx-6 sticky top-0 z-10 flex items-center gap-2 border-b bg-background px-6 py-2 shadow-sm">
            <span className="text-sm font-medium text-muted-foreground">Режим редактирования</span>
            <div className="ml-auto flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={cancelEdit}>
                <X className="h-3.5 w-3.5" />
                Отмена
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saveFeatureMutation.isPending}>
                <Check className="h-3.5 w-3.5" />
                {saveFeatureMutation.isPending ? "Сохранение..." : "Сохранить"}
              </Button>
            </div>
          </div>
        )}

        <Card className="border border-border/70">
          <CardHeader className="gap-4">
            <div className="flex flex-wrap items-start gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  {isEditing ? (
                    <input
                      className="min-w-0 flex-1 border-b border-primary bg-transparent text-2xl font-semibold outline-none"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                    />
                  ) : (
                    <h2 className="min-w-0 text-2xl font-semibold tracking-tight">{selectedFeature.name}</h2>
                  )}

                  {isEditing ? (
                    <select
                      value={resolvedMethod}
                      onChange={(e) => setEditMethod(e.target.value)}
                      className="rounded-md border border-border bg-transparent px-2 py-1 text-xs font-semibold font-mono"
                    >
                      {["GET", "POST", "PUT", "DELETE", "PATCH", "CONSUMER"].map((method) => (
                        <option key={method} value={method}>{method}</option>
                      ))}
                    </select>
                  ) : (
                    <MethodBadge method={selectedFeature.method} featureType={selectedFeature.type} large />
                  )}

                  <Badge variant="outline" className="text-xs">
                    {Math.round(selectedFeature.confidence * 100)}% заполнено
                  </Badge>
                  {selectedFeature.source_document && (
                    <Badge variant="secondary" className="max-w-full text-xs text-muted-foreground">
                      <span className="truncate">Источник: {selectedFeature.source_document}</span>
                    </Badge>
                  )}
                </div>

                <div className="mt-3 max-w-5xl">
                  <CardDescription
                    className="text-sm leading-6"
                    style={
                      canCollapseSummary && !isSummaryExpanded
                        ? {
                            display: "-webkit-box",
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }
                        : undefined
                    }
                  >
                    {featureSummary}
                  </CardDescription>
                  {canCollapseSummary && (
                    <button
                      className="mt-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                      onClick={() => setIsSummaryExpanded((value) => !value)}
                    >
                      {isSummaryExpanded ? "Свернуть описание" : "Показать описание полностью"}
                    </button>
                  )}
                </div>
              </div>

              <div className="ml-auto flex items-center gap-2 self-start">
                {!isEditing && (
                  <Button variant="outline" size="sm" className="shadow-none" onClick={startEdit}>
                    <Pencil className="h-3.5 w-3.5" />
                    Редактировать
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="border-destructive/20 text-destructive shadow-none hover:border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => {
                    if (window.confirm(`Удалить фичу "${selectedFeature.name}"?`)) {
                      deleteFeatureMutation.mutate(selectedFeature.name, {
                        onSuccess: () => navigate(projectPath(projectSlug)),
                      })
                    }
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Удалить
                </Button>
              </div>
            </div>

        <div className="grid overflow-hidden rounded-2xl border border-border/70 bg-muted/10 md:grid-cols-4 md:divide-x md:divide-border/70">
          <FeatureOverviewCard
            icon={<Workflow className="h-4 w-4" />}
            label={integrationMeta.label}
            value={integrationMeta.value}
            tone="muted"
              />
              <FeatureOverviewCard
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Пробелы"
                value={String(selectedFeature.gap_count ?? 0)}
                tone={(selectedFeature.gap_count ?? 0) > 0 ? "warning" : "default"}
              />
              <FeatureOverviewCard
                icon={<Gauge className="h-4 w-4" />}
                label="Тест-кейсы"
                value={String(selectedFeature.test_case_count ?? 0)}
                tone={(selectedFeature.test_case_count ?? 0) > 0 ? "default" : "muted"}
              />
              <FeatureOverviewCard
                icon={<Inbox className="h-4 w-4" />}
                label="Баги"
                value={String(selectedFeature.bug_count ?? 0)}
                tone={(selectedFeature.bug_count ?? 0) > 0 ? "danger" : "muted"}
              />
            </div>
          </CardHeader>
        </Card>

        {isEditing && (
          <Card className="border border-border/70">
            <CardHeader className="gap-1">
              <CardTitle>Редактирование метаданных</CardTitle>
              <CardDescription>Приведите в порядок маршрут или точку интеграции и краткое описание, чтобы фича читалась быстрее.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{integrationFieldLabel}</p>
                <input
                  className="w-full border-b border-border bg-transparent pb-1 text-sm font-mono outline-none"
                  value={editEndpoint}
                  placeholder={integrationFieldPlaceholder}
                  onChange={(e) => setEditEndpoint(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Краткое описание</p>
                <input
                  className="w-full border-b border-border bg-transparent pb-1 text-sm outline-none"
                  value={editSummary}
                  placeholder="Что делает эта фича"
                  onChange={(e) => setEditSummary(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        )}

        <Tabs value={activeFeatureTab} onValueChange={(tab) => onFeatureTabChange(tab as FeatureTab)} className="gap-4">
          <TabsList className="flex-wrap">
            <TabsTrigger value="logic">Логика</TabsTrigger>
            <TabsTrigger value="gaps">Пробелы{selectedFeature.gap_count ? ` (${selectedFeature.gap_count})` : ""}</TabsTrigger>
            <TabsTrigger value="tests">Тест-кейсы{selectedFeature.test_case_count ? ` (${selectedFeature.test_case_count})` : ""}</TabsTrigger>
            <TabsTrigger value="bugs">Баги{selectedFeature.bug_count ? ` (${selectedFeature.bug_count})` : ""}</TabsTrigger>
          </TabsList>

          <TabsContent value="logic" className="rounded-xl border border-border/70 bg-card p-4">
            <Suspense fallback={<ContentLoadingState label="Загрузка логики..." />}>
              {displayLogic ? (
                <StructuredLogicView
                  logic={displayLogic}
                  featureType={selectedFeature.type}
                  projectDependencies={projectDependencies}
                  onDepClick={onDepClick}
                  isEditing={isEditing}
                  onChange={isEditing ? setEditedLogic : undefined}
                />
              ) : (
                <EmptyPanel
                  title="Структурированная логика пока не заполнена"
                  description="Загрузите более полный PDF или отредактируйте фичу вручную, чтобы заполнить этот блок."
                />
              )}
            </Suspense>
          </TabsContent>

          <TabsContent value="gaps" className="rounded-xl border border-border/70 bg-card p-4">
            <Suspense fallback={<ContentLoadingState label="Загрузка пробелов..." />}>
              <GapsView
                projectSlug={projectSlug}
                featureName={selectedFeature.name}
                usedDependencies={selectedFeature.structured_logic?.used_dependencies}
                projectDependencies={projectDependencies}
              />
            </Suspense>
          </TabsContent>

          <TabsContent value="tests" className="rounded-xl border border-border/70 bg-card p-4">
            <Suspense fallback={<ContentLoadingState label="Загрузка тест-кейсов..." />}>
              <TestCasesView projectSlug={projectSlug} featureName={selectedFeature.name} />
            </Suspense>
          </TabsContent>

          <TabsContent value="bugs" className="rounded-xl border border-border/70 bg-card p-4">
            <Suspense fallback={<ContentLoadingState label="Загрузка багов..." />}>
              <BugsView projectSlug={projectSlug} featureName={selectedFeature.name} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  const totalFeatures = features?.length ?? 0
  const totalDependencies = projectDependencies?.length ?? 0
  const completedFeatures = features?.filter((feature) => feature.status === "done").length ?? 0
  const pendingFeatures = Math.max(totalFeatures - completedFeatures, 0)

  return (
    <div className="space-y-6">
      <div className="max-w-4xl space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Обзор проекта</p>
        <h2 className="text-3xl font-semibold tracking-tight">{projectName}</h2>
        <p className="text-base text-muted-foreground">
          Выберите фичу или зависимость слева. Пока ничего не выбрано, здесь отображается текущее состояние проекта и следующий полезный шаг.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ProjectOverviewCard icon={<FolderKanban className="h-4 w-4" />} label="Фичи" value={String(totalFeatures)} helper={`${completedFeatures} готовы, ${pendingFeatures} в работе`} />
        <ProjectOverviewCard icon={<Files className="h-4 w-4" />} label="Источники" value={String(projectDocumentCount)} helper="Загруженные PDF" />
        <ProjectOverviewCard icon={<Workflow className="h-4 w-4" />} label="Зависимости" value={String(totalDependencies)} helper="DB, API, кэш, топики" />
        <ProjectOverviewCard icon={<Sparkles className="h-4 w-4" />} label="Следующий шаг" value={totalFeatures > 0 ? "Выбрать фичу" : "Загрузить PDF"} helper={totalFeatures > 0 ? "Перейдите к логике, пробелам и тест-кейсам" : "После загрузки появятся фичи и зависимости"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <Card className="border border-border/70">
          <CardHeader>
            <CardTitle>С чего начать</CardTitle>
            <CardDescription>Основные сценарии, которые должны быть видны до выбора конкретной сущности.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <NextStepCard
              title="1. Обновить исходники проекта"
              description="Загрузите новый PDF, если нужно переизвлечь фичи или пополнить модель зависимостей."
              icon={<Files className="h-4 w-4" />}
            />
            <NextStepCard
              title="2. Открыть конкретную фичу"
              description="Проверьте summary, параметры и артефакты. Это основной рабочий сценарий продукта."
              icon={<ArrowRight className="h-4 w-4" />}
            />
            <NextStepCard
              title="3. Дойти до пробелов и тест-кейсов"
              description="После проверки логики можно быстро перейти к gaps, test-cases и баг-репортам."
              icon={<Sparkles className="h-4 w-4" />}
            />
          </CardContent>
        </Card>

        <Card className="border border-border/70">
          <CardHeader>
            <CardTitle>Что доступно сейчас</CardTitle>
            <CardDescription>Подсказка по рабочему сценарию без лишней пустоты на экране.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>В левой колонке собраны фичи, зависимости и загрузка исходников. Правая часть предназначена для детальной работы с выбранной сущностью.</p>
            <p>Если вы видите этот экран, проект уже готов к навигации, но ни одна фича еще не выбрана.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function ProjectOverviewCard({
  icon,
  label,
  value,
  helper,
}: {
  icon: ReactNode
  label: string
  value: string
  helper: string
}) {
  return (
    <Card className="border border-border/70">
      <CardContent className="flex items-start justify-between gap-4 py-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold">{value}</p>
          <p className="mt-1 text-sm text-muted-foreground">{helper}</p>
        </div>
        <div className="rounded-lg bg-muted p-2 text-muted-foreground">{icon}</div>
      </CardContent>
    </Card>
  )
}

function FeatureOverviewCard({
  icon,
  label,
  value,
  tone = "default",
}: {
  icon: ReactNode
  label: string
  value: string
  tone?: "default" | "warning" | "danger" | "muted"
}) {
  const toneClasses = {
    default: "bg-transparent",
    warning: "bg-amber-50/60",
    danger: "bg-red-50/60",
    muted: "bg-muted/30",
  }

  return (
    <div className={cn("min-w-0 min-h-20 px-4 py-3.5", toneClasses[tone])}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className="rounded-md bg-background/80 p-1.5 text-muted-foreground shadow-sm">{icon}</span>
        <span className="text-[0.625rem] font-semibold uppercase tracking-[0.14em]">{label}</span>
      </div>
      <p className="mt-3 truncate text-lg font-semibold leading-tight" title={value}>{value}</p>
    </div>
  )
}

function NextStepCard({
  title,
  description,
  icon,
}: {
  title: string
  description: string
  icon: ReactNode
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/70 px-4 py-3">
      <div className="rounded-lg bg-muted p-2 text-muted-foreground">{icon}</div>
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

function EmptyPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-dashed px-4 py-10 text-center">
      <p className="text-base font-medium">{title}</p>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

function ContentLoadingState({ label }: { label: string }) {
  return <div className="rounded-xl border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">{label}</div>
}

function getFeatureIntegrationMeta(feature: FeatureResponse, endpointValue: string | null | undefined) {
  const normalizedEndpoint = endpointValue?.trim()
  if (normalizedEndpoint) {
    return {
      label: feature.type === "rest_endpoint" ? "Маршрут" : "Точка интеграции",
      value: normalizedEndpoint,
    }
  }

  const fallbackByType: Record<FeatureResponse["type"], { label: string; value: string }> = {
    kafka_consumer: { label: "Тип сценария", value: "Kafka-консьюмер" },
    rest_endpoint: { label: "Тип сценария", value: "REST API" },
    scheduled_task: { label: "Тип сценария", value: "Планировщик" },
    unknown: { label: "Тип сценария", value: inferFeatureTypeLabel(feature) },
  }

  return fallbackByType[feature.type] ?? fallbackByType.unknown
}

function inferFeatureTypeLabel(feature: FeatureResponse) {
  const haystack = `${feature.name} ${feature.summary ?? ""}`.toLowerCase()

  if (/(kafka|консьюмер|топик|queue)/.test(haystack)) {
    return "Kafka-консьюмер"
  }

  if (/(get|post|put|patch|delete|api|endpoint|route|маршрут)/.test(haystack)) {
    return "REST API"
  }

  if (/(cron|scheduler|scheduled|job|расписан)/.test(haystack)) {
    return "Планировщик"
  }

  return "Не определен"
}
