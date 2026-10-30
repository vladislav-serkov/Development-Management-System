import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useUIStore } from "@/stores/uiStore"
import { useProject, useImportConfluence, useProjectFeatures, useProjectDocuments, useSpecUpdates, useDeleteFeature, useImplementFeature } from "@/hooks/useDocuments"
import { useProjectDependencies } from "@/hooks/useDependencies"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { StatStrip } from "@/components/ui/stat-strip"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProjectSidebar, MethodBadge } from "@/components/sidebar"
import { Bot, Loader2, Trash2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { countLabel, plural } from "@/lib/plural"
import { stripMethodPrefix } from "@/lib/artifacts"
import { dependencyPath, featurePath, isFeatureTab, projectPath, type FeatureTab } from "@/lib/routes"
import { useConfirm } from "@/components/ConfirmDialog"
import type {
  DocumentResponse,
  FeatureResponse,
  ProjectDependency,
} from "@/types/api"

const StructuredLogicView = lazy(() =>
  import("@/components/feature/StructuredLogicView").then((module) => ({ default: module.StructuredLogicView }))
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
  const features = allFeatures?.filter(f => f.status === "done")
  const { data: documents } = useProjectDocuments(projectSlug, project?.status)
  const specUpdates = useSpecUpdates(projectSlug)
  const { data: dependencies } = useProjectDependencies(projectSlug)
  const confluenceMutation = useImportConfluence(projectSlug!)

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
        documents={documents}
        dependencies={dependencies}
        selectedFeatureName={selectedFeature?.name ?? null}
        selectedDep={selectedDep}
        onImportConfluence={(url) => confluenceMutation.mutate(url)}
        isImporting={confluenceMutation.isPending}
        importError={confluenceMutation.error?.message ?? null}
        isCheckingUpdates={specUpdates.isFetching}
        sidebarWidth={sidebarWidth}
        onStartDrag={() => { isDragging.current = true }}
      />

      <main className="flex-1 min-h-0 overflow-y-auto p-6">
        <ProjectContentArea
          key={contentKey}
          projectSlug={projectSlug!}
          projectName={project.name}
          documents={documents}
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
  documents,
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
  documents?: DocumentResponse[]
  selectedFeature: FeatureResponse | null
  selectedDep: ProjectDependency | null
  projectDependencies?: ProjectDependency[]
  features?: FeatureResponse[]
  onDepClick?: (dep: ProjectDependency) => void
  activeFeatureTab: FeatureTab
  onFeatureTabChange: (tab: FeatureTab) => void
}) {
  const navigate = useNavigate()
  const askConfirm = useConfirm()
  const deleteFeatureMutation = useDeleteFeature(projectSlug)
  const implementMutation = useImplementFeature(projectSlug)

  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false)
  const [showImplementForm, setShowImplementForm] = useState(false)
  const [implementJiraKey, setImplementJiraKey] = useState("")

  if (selectedDep) {
    return (
      <Suspense fallback={<ContentLoadingState label="Загрузка детали зависимости..." />}>
        <DependencyDetail dep={selectedDep} projectSlug={projectSlug} />
      </Suspense>
    )
  }

  if (selectedFeature) {
    const displayLogic = selectedFeature.structured_logic
    const integrationMeta = getFeatureIntegrationMeta(selectedFeature, selectedFeature.endpoint)
    const featureSummary = selectedFeature.summary ?? "Добавьте краткое описание, чтобы экран было проще сканировать и обсуждать с командой."
    const canCollapseSummary = featureSummary.length > 200
    const title = selectedFeature.display_name ?? stripMethodPrefix(selectedFeature.name, selectedFeature.method)
    const extraMeta = integrationMeta.value && integrationMeta.value !== title && integrationMeta.value !== selectedFeature.name ? integrationMeta : null
    const staleTargets = [
      selectedFeature.gaps_stale ? "Gaps-анализ" : null,
      selectedFeature.test_cases_stale ? "тест-кейсы" : null,
    ].filter(Boolean)

    return (
      <div className="space-y-4">
        <header className="space-y-3">
          <div className="flex flex-wrap items-start gap-4">
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <MethodBadge method={selectedFeature.method} featureType={selectedFeature.type} large />
                <h1 className="min-w-0 break-all font-mono text-[1.375rem] leading-8 font-semibold tracking-tight" title={selectedFeature.name}>
                  {title}
                </h1>
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  {Math.round(selectedFeature.confidence * 100)}% заполнено
                </Badge>
                {extraMeta && (
                  <Badge variant="outline" className="max-w-full text-xs text-muted-foreground" title={extraMeta.label}>
                    <span className="truncate">{extraMeta.value}</span>
                  </Badge>
                )}
                {selectedFeature.orphaned && (
                  <Badge variant="outline" className="border-red-300 text-xs text-red-700 dark:border-red-800 dark:text-red-400">
                    нет в текущей спеке
                  </Badge>
                )}
              </div>
              <p
                className="max-w-4xl text-sm leading-6 text-muted-foreground"
                style={canCollapseSummary && !isSummaryExpanded ? { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } : undefined}
              >
                {featureSummary}
              </p>
              <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                {canCollapseSummary && (
                  <button className="font-medium text-foreground/80 hover:text-foreground" onClick={() => setIsSummaryExpanded((value) => !value)}>
                    {isSummaryExpanded ? "Свернуть" : "Подробнее"}
                  </button>
                )}
                {selectedFeature.source_document && <span>Источник: {selectedFeature.source_document}</span>}
              </div>
            </div>

            <div className="flex items-center gap-2 self-start">
              {selectedFeature.impl_status !== "queued" && selectedFeature.impl_status !== "running" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-emerald-200 text-emerald-700 shadow-none hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-900/60 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
                  onClick={() => setShowImplementForm((v) => !v)}
                >
                  <Bot className="h-3.5 w-3.5" />
                  Реализовать по ТЗ
                </Button>
              )}
              <Button
                variant="destructive"
                size="sm"
                onClick={async () => {
                  const ok = await askConfirm({
                    title: `Удалить фичу "${selectedFeature.display_name ?? selectedFeature.name}"?`,
                    description: "Действие нельзя отменить.",
                    confirmText: "Удалить",
                    destructive: true,
                  })
                  if (ok) {
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

          {showImplementForm && selectedFeature.impl_status !== "queued" && selectedFeature.impl_status !== "running" && (
            <form
              className="flex flex-col gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/40 p-3 dark:border-emerald-900/40 dark:bg-emerald-950/10 sm:flex-row sm:items-center"
              onSubmit={(e) => {
                e.preventDefault()
                const key = implementJiraKey.trim()
                if (key.length < 3 || implementMutation.isPending) return
                implementMutation.mutate(
                  { featureName: selectedFeature.name, jiraKey: key },
                  { onSuccess: () => { setShowImplementForm(false); setImplementJiraKey("") } }
                )
              }}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground">Реализовать задачу по этой фиче</p>
                <p className="mt-0.5 text-[0.8125rem] text-muted-foreground">Агент возьмёт тикет в работу по стандартному флоу: ТЗ, реализация с тестами, MR, статусы Jira.</p>
                {implementMutation.error && (
                  <p className="mt-1 text-[0.75rem] text-destructive">{(implementMutation.error as Error).message}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Input
                  value={implementJiraKey}
                  onChange={(e) => setImplementJiraKey(e.target.value)}
                  placeholder="MTSPAY-12345"
                  className="w-40 font-mono text-sm"
                  disabled={implementMutation.isPending}
                />
                <Button size="sm" type="submit" disabled={implementMutation.isPending || implementJiraKey.trim().length < 3}>
                  {implementMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Запустить"}
                </Button>
                <Button size="icon-sm" type="button" variant="ghost" className="text-muted-foreground hover:text-foreground" onClick={() => setShowImplementForm(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </form>
          )}

          {selectedFeature.orphaned && (
            <Notice tone="danger">
              Этой фичи больше нет в текущей версии страницы Confluence. Она сохранена вместе со своими тест-кейсами и багами — удалите её вручную, когда артефакты больше не нужны.
            </Notice>
          )}

          {staleTargets.length > 0 && (
            <Notice tone="warning">
              Спека обновилась{selectedFeature.stale_spec_note ? ` (${selectedFeature.stale_spec_note})` : ""} после того, как посчитаны {staleTargets.join(" и ")}. Перегенерируйте их, чтобы учесть изменения.
            </Notice>
          )}

          {selectedFeature.impl_status && (
            <Notice tone="default">
              {selectedFeature.impl_status === "queued" && (
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Bot className="h-3.5 w-3.5" /> {selectedFeature.impl_jira_key}: в очереди на реализацию
                </span>
              )}
              {selectedFeature.impl_status === "running" && (
                <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Codex делает {selectedFeature.impl_jira_key}…
                </span>
              )}
              {selectedFeature.impl_status === "implemented" && (
                <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                  <Bot className="h-3.5 w-3.5" />
                  {selectedFeature.impl_jira_key}: реализовано
                  {selectedFeature.impl_mr_url && (
                    <a href={selectedFeature.impl_mr_url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-2 hover:text-emerald-700 dark:hover:text-emerald-300">MR</a>
                  )}
                  {selectedFeature.impl_summary && <span className="text-foreground/60">— {selectedFeature.impl_summary}</span>}
                </span>
              )}
              {selectedFeature.impl_status === "no_changes_needed" && (
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Bot className="h-3.5 w-3.5" />
                  {selectedFeature.impl_jira_key}: изменения не требуются{selectedFeature.impl_error ? ` — ${selectedFeature.impl_error}` : ""}
                </span>
              )}
              {selectedFeature.impl_status === "failed" && (
                <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                  <Bot className="h-3.5 w-3.5" />
                  {selectedFeature.impl_jira_key}: агент остановился{selectedFeature.impl_error ? `: ${selectedFeature.impl_error}` : ""}
                </span>
              )}
            </Notice>
          )}
        </header>

        <Tabs value={activeFeatureTab} onValueChange={(tab) => onFeatureTabChange(tab as FeatureTab)} className="gap-4">
          <TabsList className="flex-wrap">
            <TabsTrigger value="logic">Логика</TabsTrigger>
            <TabsTrigger value="tests">
              Тест-кейсы{selectedFeature.test_case_count ? <span className="text-xs tabular-nums opacity-60">{selectedFeature.test_case_count}</span> : null}
            </TabsTrigger>
            <TabsTrigger value="bugs">
              Баги{selectedFeature.bug_count ? <span className="text-xs tabular-nums opacity-60">{selectedFeature.bug_count}</span> : null}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="logic" className="rounded-xl border bg-card p-4">
            <Suspense fallback={<ContentLoadingState label="Загрузка логики..." />}>
              {displayLogic ? (
                <StructuredLogicView
                  logic={displayLogic}
                  featureType={selectedFeature.type}
                  projectDependencies={projectDependencies}
                  onDepClick={onDepClick}
                />
              ) : (
                <EmptyPanel
                  title="Структурированная логика пока не заполнена"
                  description="Импортируйте более полную страницу Confluence, чтобы заполнить этот блок."
                />
              )}
            </Suspense>
          </TabsContent>

          <TabsContent value="tests">
            <Suspense fallback={<ContentLoadingState label="Загрузка тест-кейсов..." />}>
              <TestCasesView projectSlug={projectSlug} featureName={selectedFeature.name} />
            </Suspense>
          </TabsContent>

          <TabsContent value="bugs">
            <Suspense fallback={<ContentLoadingState label="Загрузка багов..." />}>
              <BugsView projectSlug={projectSlug} featureName={selectedFeature.name} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  const featureList = features ?? []
  const totalTestCases = featureList.reduce((sum, f) => sum + (f.test_case_count ?? 0), 0)
  const totalBugs = featureList.reduce((sum, f) => sum + (f.bug_count ?? 0), 0)
  const deps = projectDependencies ?? []
  const depGroups: { label: string; type: ProjectDependency["dep_type"] }[] = [
    { label: "Таблицы БД", type: "db_table" },
    { label: "Внешние API", type: "external_api" },
    { label: "Кэш", type: "cache" },
    { label: "Топики Kafka", type: "kafka_topic" },
    { label: "Документы", type: "external_doc" },
  ]
  const confluenceDocs = documents?.filter((d) => d.confluence_url) ?? []

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Обзор проекта</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{projectName}</h1>
      </div>

      <StatStrip
        items={[
          { value: featureList.length, label: plural(featureList.length, ["фича", "фичи", "фич"]) },
          { value: totalTestCases, label: plural(totalTestCases, ["тест-кейс", "тест-кейса", "тест-кейсов"]) },
          { value: totalBugs, label: plural(totalBugs, ["баг", "бага", "багов"]), tone: totalBugs > 0 ? "danger" : "default" },
          { value: deps.length, label: plural(deps.length, ["зависимость", "зависимости", "зависимостей"]) },
        ]}
      />

      <section className="overflow-hidden rounded-xl border bg-card">
        <div className="border-b px-4 py-3">
          <h2 className="text-base font-semibold">Фичи</h2>
        </div>
        {featureList.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">Импортируйте страницу Confluence в сайдбаре — здесь появятся извлечённые фичи.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Фича</th>
                <th className="px-4 py-2 font-medium">Тест-кейсы</th>
                <th className="px-4 py-2 font-medium">Баги</th>
                <th className="px-4 py-2 font-medium">Спека</th>
              </tr>
            </thead>
            <tbody>
              {featureList.map((f) => {
                const stale = f.gaps_stale || f.test_cases_stale
                return (
                  <tr
                    key={f.name}
                    className="cursor-pointer border-b last:border-b-0 hover:bg-muted/40"
                    onClick={() => navigate(featurePath(projectSlug, f.name))}
                  >
                    <td className="px-4 py-2.5">
                      <div className="flex items-start gap-1.5">
                        <MethodBadge method={f.method} featureType={f.type} />
                        <span className="break-all font-mono text-[0.8125rem] font-medium">{f.display_name ?? stripMethodPrefix(f.name, f.method)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{f.test_case_count ?? 0}</td>
                    <td className="px-4 py-2.5">
                      {(f.bug_count ?? 0) > 0 ? (
                        <Badge variant="destructive">{countLabel(f.bug_count ?? 0, ["баг", "бага", "багов"])}</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {f.orphaned ? (
                        <Badge variant="destructive">нет в спеке</Badge>
                      ) : stale ? (
                        <Badge variant="outline" className="border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-300">обновилась{f.stale_spec_note ? ` ${f.stale_spec_note}` : ""}</Badge>
                      ) : (
                        <Badge variant="outline" className="border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-400">актуальна</Badge>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="overflow-hidden rounded-xl border bg-card">
          <div className="border-b px-4 py-3"><h2 className="text-base font-semibold">Источники</h2></div>
          {confluenceDocs.length === 0 ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Пока нет импортированных страниц.</p>
          ) : (
            confluenceDocs.map((doc) => (
              <div key={doc.slug} className="flex items-center gap-3 border-b px-4 py-2.5 last:border-b-0">
                <div className="min-w-0 flex-1">
                  <a href={doc.confluence_url ?? undefined} target="_blank" rel="noreferrer" className="block truncate font-mono text-[0.8125rem] hover:underline">{doc.filename}</a>
                  <p className="text-xs text-muted-foreground">Confluence · v{doc.confluence_version ?? "?"} · {countLabel(doc.feature_count, ["фича", "фичи", "фич"])}</p>
                </div>
                {doc.spec_outdated ? (
                  <Badge variant="outline" className="border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-300">v{doc.confluence_version} → v{doc.latest_confluence_version}</Badge>
                ) : (doc.deps_outdated?.length ?? 0) > 0 ? (
                  <Badge variant="outline" className="border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-300">обновились источники</Badge>
                ) : (
                  <Badge variant="outline" className="border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-400">актуальна</Badge>
                )}
              </div>
            ))
          )}
        </section>

        <section className="overflow-hidden rounded-xl border bg-card">
          <div className="border-b px-4 py-3"><h2 className="text-base font-semibold">Зависимости</h2></div>
          {depGroups.map((group) => {
            const items = deps.filter((d) => d.dep_type === group.type)
            if (items.length === 0) return null
            const stubs = items.filter((d) => d.enrichment_status !== "enriched").length
            return (
              <div key={group.type} className="flex items-center gap-3 border-b px-4 py-2.5 last:border-b-0">
                <span className="flex-1">{group.label}</span>
                <span className="text-sm tabular-nums text-muted-foreground">{items.length}</span>
                {stubs > 0 && (
                  <Badge variant="outline" className="border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-300">{stubs} не обогащено</Badge>
                )}
              </div>
            )
          })}
          {deps.length === 0 && <p className="px-4 py-6 text-sm text-muted-foreground">Зависимости появятся после импорта спеки.</p>}
        </section>
      </div>
    </div>
  )
}

function Notice({ tone, children }: { tone: "warning" | "danger" | "default"; children: ReactNode }) {
  const toneClasses = {
    warning: "border-amber-200/80 bg-amber-50/60 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/10 dark:text-amber-300",
    danger: "border-red-200/80 bg-red-50/50 text-red-800 dark:border-red-900/40 dark:bg-red-950/10 dark:text-red-300",
    default: "border-border bg-muted/20",
  }
  return <div className={cn("flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2 text-[0.8125rem]", toneClasses[tone])}>{children}</div>
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
  if (feature.type === "scheduled_task") {
    const schedule = feature.schedule?.trim()
    if (schedule) {
      return { label: "Расписание", value: schedule }
    }
    return { label: "Тип сценария", value: "Планировщик" }
  }

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
