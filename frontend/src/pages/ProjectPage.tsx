import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useUIStore } from "@/stores/uiStore"
import { useProject, useRenameProject, useUploadDocument, useProjectFeatures, useSaveFeature, useDeleteFeature } from "@/hooks/useDocuments"
import { useProjectDependencies, useCreateDependency, useDeleteDependency } from "@/hooks/useDependencies"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { UploadZone } from "@/components/project/UploadZone"
import { ExportDialog } from "@/components/project/ExportDialog"
import { EnrichUploadZone } from "@/components/dependency/EnrichUploadZone"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronRight,
  Database,
  FileJson2,
  Files,
  FolderKanban,
  Gauge,
  Globe,
  HardDrive,
  Inbox,
  Layers,
  MessageSquare,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Workflow,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { dependencyPath, featurePath, homePath, isFeatureTab, projectPath, rulesPath, type FeatureTab } from "@/lib/routes"
import type {
  CreateDependencyRequest,
  DependencyStatus,
  DependencyType,
  FeatureResponse,
  FeatureStatus,
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
  const { data: features } = useProjectFeatures(projectSlug)
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

  const renameMutation = useRenameProject(projectSlug!)
  const deleteFeatureMutation = useDeleteFeature(projectSlug ?? "")

  const [isEditingName, setIsEditingName] = useState(false)
  const [editedName, setEditedName] = useState("")

  const handleStartEdit = () => {
    setEditedName(project?.name ?? "")
    setIsEditingName(true)
  }

  const handleSaveName = () => {
    if (!editedName.trim()) return
    renameMutation.mutate(editedName.trim(), {
      onSuccess: () => setIsEditingName(false),
    })
  }

  if (projectLoading || !project) {
    return <div className="p-8 text-sm text-muted-foreground">Загрузка проекта...</div>
  }

  function handleFeatureClick(featureName: string, tab: FeatureTab = "logic") {
    navigate(featurePath(projectSlug!, featureName, tab))
  }

  function handleDepClick(dep: ProjectDependency) {
    navigate(dependencyPath(projectSlug!, dep.dep_type, dep.name))
  }

  const isFeatureActive = (featureName: string) => selectedFeature?.name === featureName
  const isDepActive = (dep: ProjectDependency) => selectedDep?.name === dep.name && selectedDep?.dep_type === dep.dep_type

  const depsByType = {
    db_table: dependencies?.filter((dep) => dep.dep_type === "db_table") ?? [],
    external_api: dependencies?.filter((dep) => dep.dep_type === "external_api") ?? [],
    cache: dependencies?.filter((dep) => dep.dep_type === "cache") ?? [],
    kafka_topic: dependencies?.filter((dep) => dep.dep_type === "kafka_topic") ?? [],
  }

  const contentKey = selectedDep
    ? `dep-${selectedDep.dep_type}-${selectedDep.name}`
    : selectedFeature
      ? `feature-${selectedFeature.name}-${activeFeatureTab}`
      : "none"

  const totalDependencies = dependencies?.length ?? 0
  const readyFeatures = features?.filter((feature) => feature.status === "done").length ?? 0

  return (
    <div className="flex h-screen bg-background">
      <aside className="relative flex h-screen shrink-0 flex-col border-r bg-muted/30" style={{ width: sidebarWidth }}>
        <div className="border-b p-4">
          <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" size="sm" className="justify-start text-xs" onClick={() => navigate(homePath())}>
              &larr; Все проекты
            </Button>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" onClick={() => navigate(rulesPath())}>
              Правила
            </Button>
          </div>

          <div className="mt-4 space-y-3 px-1">
            {isEditingName ? (
              <div className="flex items-center gap-1">
                <input
                  className="min-w-0 flex-1 border-b border-primary bg-transparent text-base font-semibold outline-none"
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName()
                    if (e.key === "Escape") setIsEditingName(false)
                  }}
                  autoFocus
                />
              </div>
            ) : (
              <div>
                <p
                  className="cursor-pointer truncate text-base font-semibold transition-colors hover:text-primary"
                  onClick={handleStartEdit}
                  title="Нажмите, чтобы переименовать проект"
                >
                  {project.name}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Создан {new Date(project.created_at).toLocaleDateString()}
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <SidebarMetric label="Фичи" value={features?.length ?? 0} helper={`${readyFeatures} готовы`} />
              <SidebarMetric label="Источники" value={project.document_count} helper={`${totalDependencies} зависимостей`} />
            </div>
          </div>
        </div>

        <div className="border-b p-4">
          <div className="mb-2 px-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Источники</p>
            <p className="mt-1 text-xs text-muted-foreground">Загрузите PDF, чтобы обновить фичи и зависимости проекта.</p>
          </div>
          <UploadZone onUpload={(file) => uploadMutation.mutate(file)} isUploading={uploadMutation.isPending} />
        </div>

        <ScrollArea className="flex-1 min-h-0 p-4">
          <div className="space-y-5">
            <section>
              <div className="mb-2 flex items-center justify-between px-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Layers className="h-3.5 w-3.5" />
                  Навигация по фичам
                </div>
                {features && features.length > 0 && (
                  <Badge variant="outline" className="h-5 px-1.5 py-0 text-[10px]">
                    {features.length}
                  </Badge>
                )}
              </div>

              <div className="space-y-1">
                {features?.map((feature) => (
                  <div key={feature.name}>
                    <div className="group relative flex items-center">
                      {(() => {
                        const featureMeta = getFeatureSidebarMeta(feature.name)

                        return (
                      <button
                        onClick={() => handleFeatureClick(feature.name)}
                        title={feature.name}
                        className={cn(
                          "flex-1 rounded-xl border px-3 py-2.5 text-left transition-colors",
                          isFeatureActive(feature.name)
                            ? "border-primary/20 bg-background shadow-sm"
                            : "border-transparent hover:border-border hover:bg-background/80"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <FeatureStatusDot status={feature.status} />
                          <div className="min-w-0 flex-1">
                            {featureMeta.secondary && (
                              <p className="truncate text-[10px] uppercase tracking-[0.12em] text-muted-foreground/80">
                                {featureMeta.secondary}
                              </p>
                            )}
                            <div className="mt-1 flex items-center gap-2">
                              <MethodBadge method={feature.method} featureType={feature.type} />
                              <span className="truncate text-sm font-medium">{featureMeta.primary}</span>
                            </div>
                            <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                              <span>{feature.gap_count ?? 0} пробелов</span>
                              <span>{feature.test_case_count ?? 0} тестов</span>
                              <span>{feature.bug_count ?? 0} багов</span>
                            </div>
                          </div>
                          <ChevronRight className={cn("mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", isFeatureActive(feature.name) && "rotate-90")} />
                        </div>
                      </button>
                        )
                      })()}
                      <SidebarTrashButton
                        onDelete={() => {
                          if (window.confirm(`Удалить фичу "${feature.name}" и все связанные gaps/test-cases/bugs?`)) {
                            deleteFeatureMutation.mutate(feature.name, {
                              onSuccess: () => {
                                if (isFeatureActive(feature.name)) {
                                  navigate(projectPath(projectSlug!))
                                }
                              },
                            })
                          }
                        }}
                      />
                    </div>

                    {isFeatureActive(feature.name) && (
                      <div className="mt-1 space-y-1 pl-5">
                        <FeatureTabButton active={activeFeatureTab === "logic"} onClick={() => handleFeatureClick(feature.name, "logic")}>
                          Логика
                        </FeatureTabButton>
                        <FeatureTabButton active={activeFeatureTab === "gaps"} onClick={() => handleFeatureClick(feature.name, "gaps")}>
                          <span className="flex-1">Пробелы</span>
                          {feature.gaps_status === "running" && <AnimatedDots className="shrink-0 text-xs" />}
                        </FeatureTabButton>
                        <FeatureTabButton active={activeFeatureTab === "tests"} onClick={() => handleFeatureClick(feature.name, "tests")}>
                          <span className="flex-1">Тест-кейсы</span>
                          {feature.test_cases_status === "running" && <AnimatedDots className="shrink-0 text-xs" />}
                        </FeatureTabButton>
                        <FeatureTabButton active={activeFeatureTab === "bugs"} onClick={() => handleFeatureClick(feature.name, "bugs")}>
                          Баги
                        </FeatureTabButton>
                      </div>
                    )}
                  </div>
                ))}

                {(!features || features.length === 0) && (
                  <div className="rounded-xl border border-dashed px-3 py-4 text-xs text-muted-foreground">
                    После загрузки первого PDF здесь появятся извлеченные фичи.
                  </div>
                )}
              </div>
            </section>

            <section>
              <div className="mb-2 px-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Зависимости и интеграции</p>
                <p className="mt-1 text-xs text-muted-foreground">Инфраструктурные сущности проекта, сгруппированные по типам.</p>
              </div>

              <div className="space-y-4">
                <DepSection
                  label="DB"
                  icon={<Database className="h-3.5 w-3.5" />}
                  deps={depsByType.db_table}
                  depType="db_table"
                  projectSlug={projectSlug!}
                  isDepActive={isDepActive}
                  onDepClick={handleDepClick}
                />
                <DepSection
                  label="API"
                  icon={<Globe className="h-3.5 w-3.5" />}
                  deps={depsByType.external_api}
                  depType="external_api"
                  projectSlug={projectSlug!}
                  isDepActive={isDepActive}
                  onDepClick={handleDepClick}
                />
                <DepSection
                  label="Кэш"
                  icon={<HardDrive className="h-3.5 w-3.5" />}
                  deps={depsByType.cache}
                  depType="cache"
                  projectSlug={projectSlug!}
                  isDepActive={isDepActive}
                  onDepClick={handleDepClick}
                />
                <DepSection
                  label="Топики"
                  icon={<MessageSquare className="h-3.5 w-3.5" />}
                  deps={depsByType.kafka_topic}
                  depType="kafka_topic"
                  projectSlug={projectSlug!}
                  isDepActive={isDepActive}
                  onDepClick={handleDepClick}
                />

                <div className="rounded-xl border border-dashed px-3 py-3">
                  <div className="flex items-center gap-2">
                    <FileJson2 className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Swagger</span>
                    <Badge variant="outline" className="h-5 px-1.5 py-0 text-[10px] text-muted-foreground">
                      скоро
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Этот блок не должен конкурировать с основной навигацией, пока он не реализован.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </ScrollArea>

        <div className="border-t p-4">
          <div className="mb-2 px-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Экспорт</p>
            <p className="mt-1 text-xs text-muted-foreground">Соберите текущее состояние проекта в архив.</p>
          </div>
          <ExportDialog projectSlug={projectSlug!} />
        </div>

        <div
          className="absolute top-0 right-0 h-full w-1 cursor-col-resize transition-colors hover:bg-border"
          onMouseDown={() => {
            isDragging.current = true
          }}
        />
      </aside>

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
          onDepClick={handleDepClick}
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

function MethodBadge({ method, featureType, large }: { method: string | null; featureType: string; large?: boolean }) {
  const resolved = method ?? (featureType === "kafka_consumer" ? "CONSUMER" : featureType === "rest_endpoint" ? "API" : null)
  if (!resolved) return null

  const colorMap: Record<string, string> = {
    GET: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    POST: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    PUT: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    DELETE: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    PATCH: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    CONSUMER: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    API: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400",
  }

  return (
    <span className={cn("shrink-0 rounded px-1.5 py-0.5 font-mono font-semibold", large ? "text-xs" : "text-[10px]", colorMap[resolved] ?? colorMap.API)}>
      {resolved}
    </span>
  )
}

function FeatureStatusDot({ status }: { status: FeatureStatus }) {
  const colors: Record<FeatureStatus, string> = {
    done: "bg-green-500",
    extracting: "bg-amber-400",
    error: "bg-destructive",
    detected: "bg-muted-foreground/40",
  }

  return <span className={cn("mt-1 inline-block h-2 w-2 shrink-0 rounded-full", colors[status] ?? "bg-muted-foreground/40")} />
}

function SidebarMetric({ label, value, helper }: { label: string; value: number; helper: string }) {
  return (
    <div className="rounded-xl border bg-background px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      <p className="text-[11px] text-muted-foreground">{helper}</p>
    </div>
  )
}

function getFeatureSidebarMeta(featureName: string) {
  const [context, ...rest] = featureName.split(".")

  if (rest.length === 0) {
    return { primary: featureName, secondary: null as string | null }
  }

  return {
    primary: rest.join("."),
    secondary: context,
  }
}

function FeatureTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors",
        active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
      )}
    >
      {children}
    </button>
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
    <div className={cn("min-h-20 px-4 py-3.5", toneClasses[tone])}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className="rounded-md bg-background/80 p-1.5 text-muted-foreground shadow-sm">{icon}</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em]">{label}</span>
      </div>
      <p className="mt-3 text-lg font-semibold leading-tight">{value}</p>
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

function DepSection({
  label,
  icon,
  deps,
  depType,
  projectSlug,
  isDepActive,
  onDepClick,
}: {
  label: string
  icon: ReactNode
  deps: ProjectDependency[]
  depType: string
  projectSlug: string
  isDepActive: (dep: ProjectDependency) => boolean
  onDepClick: (dep: ProjectDependency) => void
}) {
  const navigate = useNavigate()
  const enrichingDepTypes = useUIStore((s) => s.enrichingDepTypes)
  const isEnriching = enrichingDepTypes.includes(depType)
  const deleteDep = useDeleteDependency(projectSlug)
  const createDep = useCreateDependency(projectSlug)

  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newDepName, setNewDepName] = useState("")
  const [newDepDesc, setNewDepDesc] = useState("")
  const [newDepMethod, setNewDepMethod] = useState("GET")
  const [newDepService, setNewDepService] = useState("")
  const createActionLabel =
    depType === "db_table"
      ? "таблицу"
      : depType === "external_api"
        ? "API"
        : depType === "cache"
          ? "кэш"
          : depType === "kafka_topic"
            ? "топик"
            : label.toLowerCase()

  const handleCreate = () => {
    if (!newDepName.trim()) return

    const req: CreateDependencyRequest = {
      dep_type: depType as DependencyType,
      name: newDepName.trim(),
      description: newDepDesc.trim(),
      ...(depType === "external_api" && { method: newDepMethod, service_name: newDepService.trim() }),
    }

    createDep.mutate(req, {
      onSuccess: () => {
        setShowCreateForm(false)
        setNewDepName("")
        setNewDepDesc("")
        setNewDepMethod("GET")
        setNewDepService("")
      },
    })
  }

  return (
    <Collapsible defaultOpen>
      <div className="mb-1 flex items-center justify-between px-1">
        <CollapsibleTrigger className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground">
          {icon}
          {label}
          {deps.length > 0 && <span className="text-[10px] font-normal">({deps.length})</span>}
        </CollapsibleTrigger>

        <div className="flex items-center gap-1">
          {(depType === "db_table" || depType === "cache") && (
            <EnrichUploadZone projectSlug={projectSlug} depType={depType} />
          )}
          <button
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title={`Добавить ${createActionLabel}`}
            onClick={() => setShowCreateForm((value) => !value)}
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <CollapsibleContent>
        {showCreateForm && (
          <div className="mb-2 space-y-1.5 rounded-xl border bg-background p-3 text-xs">
            <input
              className="w-full border-b bg-transparent pb-0.5 outline-none placeholder:text-muted-foreground/60"
              placeholder="Название *"
              value={newDepName}
              onChange={(e) => setNewDepName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate()
                if (e.key === "Escape") setShowCreateForm(false)
              }}
              autoFocus
            />
            <input
              className="w-full border-b bg-transparent pb-0.5 outline-none placeholder:text-muted-foreground/60"
              placeholder="Описание"
              value={newDepDesc}
              onChange={(e) => setNewDepDesc(e.target.value)}
            />

            {depType === "external_api" && (
              <>
                <select
                  className="w-full border-b bg-transparent pb-0.5 outline-none"
                  value={newDepMethod}
                  onChange={(e) => setNewDepMethod(e.target.value)}
                >
                  {["GET", "POST", "PUT", "DELETE", "PATCH"].map((method) => (
                    <option key={method} value={method}>{method}</option>
                  ))}
                </select>
                <input
                  className="w-full border-b bg-transparent pb-0.5 outline-none placeholder:text-muted-foreground/60"
                  placeholder="Имя сервиса"
                  value={newDepService}
                  onChange={(e) => setNewDepService(e.target.value)}
                />
              </>
            )}

            <div className="flex gap-1 pt-1">
              <button
                className="flex-1 rounded bg-primary py-1 text-primary-foreground transition-opacity hover:opacity-90"
                onClick={handleCreate}
                disabled={createDep.isPending}
              >
                Сохранить
              </button>
              <button
                className="flex-1 rounded border py-1 transition-colors hover:bg-accent"
                onClick={() => {
                  setShowCreateForm(false)
                  setNewDepName("")
                  setNewDepDesc("")
                  setNewDepMethod("GET")
                  setNewDepService("")
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        )}

        <div className="space-y-1">
          {deps.map((dep) => (
            <div key={dep.name} className="group relative flex items-center">
              <button
                onClick={() => onDepClick(dep)}
                title={dep.name}
                className={cn(
                  "flex-1 rounded-xl border px-3 py-2 text-left text-sm transition-colors",
                  isDepActive(dep)
                    ? "border-primary/20 bg-background shadow-sm"
                    : "border-transparent hover:border-border hover:bg-background/80"
                )}
              >
                <div className="flex items-center gap-2">
                  <DepStatusDot status={dep.enrichment_status} />
                  {dep.dep_type === "external_api" && dep.method && (
                    <MethodBadge method={dep.method} featureType="rest_endpoint" />
                  )}
                  <span className="truncate">{dep.name}</span>
                  {isEnriching && dep.enrichment_status === "stub" && (
                    <AnimatedDots className="ml-auto shrink-0 text-xs" />
                  )}
                </div>
              </button>

              <SidebarTrashButton
                onDelete={() => {
                  if (window.confirm(`Удалить зависимость "${dep.name}"?`)) {
                    deleteDep.mutate(
                      { depName: dep.name, depType: dep.dep_type },
                      {
                        onSuccess: () => {
                          if (isDepActive(dep)) {
                            navigate(projectPath(projectSlug))
                          }
                        },
                      }
                    )
                  }
                }}
              />
            </div>
          ))}

          {deps.length === 0 && !showCreateForm && (
            <div className="rounded-xl border border-dashed px-3 py-3 text-xs text-muted-foreground">
              Пока нет зависимостей этого типа.
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function SidebarTrashButton({ onDelete }: { onDelete: () => void }) {
  return (
    <button
      className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
      title="Удалить"
      onClick={(e) => {
        e.stopPropagation()
        onDelete()
      }}
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  )
}

function DepStatusDot({ status }: { status: DependencyStatus }) {
  const colors: Record<DependencyStatus, string> = {
    enriched: "bg-green-500",
    stub: "bg-muted-foreground/40",
    error: "bg-destructive",
  }

  return <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full", colors[status] ?? "bg-muted-foreground/40")} />
}
