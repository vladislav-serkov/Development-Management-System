import { useLocation, useNavigate } from "react-router-dom"
import { Activity, Database, Globe, HardDrive, MessageSquare } from "lucide-react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ExportDialog } from "@/components/project/ExportDialog"
import { SourcesPanel } from "@/components/project/SourcesPanel"
import { UploadZone } from "@/components/project/UploadZone"
import { useDeleteFeature } from "@/hooks/useDocuments"
import { useRenameProject } from "@/hooks/useDocuments"
import { useProjectTasks } from "@/hooks/useTasks"
import { featurePath, projectPath, tasksPath } from "@/lib/routes"
import { SidebarHeader } from "./SidebarHeader"
import { FeatureList } from "./FeatureList"
import { DependencySection } from "./DependencySection"
import type { DocumentResponse, FeatureResponse, ProjectDependency, ProjectResponse } from "@/types/api"

interface ProjectSidebarProps {
  project: ProjectResponse
  projectSlug: string
  features: FeatureResponse[] | undefined
  documents: DocumentResponse[] | undefined
  dependencies: ProjectDependency[] | undefined
  selectedFeatureName: string | null
  selectedDep: ProjectDependency | null
  onImportConfluence: (url: string) => void
  isImporting: boolean
  importError?: string | null
  isCheckingUpdates: boolean
  sidebarWidth: number
  onStartDrag: () => void
}

function SidebarLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 px-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{children}</p>
  )
}

export function ProjectSidebar({
  project,
  projectSlug,
  features,
  documents,
  dependencies,
  selectedFeatureName,
  selectedDep,
  onImportConfluence,
  isImporting,
  importError,
  isCheckingUpdates,
  sidebarWidth,
  onStartDrag,
}: ProjectSidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const renameMutation = useRenameProject(projectSlug)
  const deleteFeatureMutation = useDeleteFeature(projectSlug)
  const { data: runningTasks } = useProjectTasks(projectSlug, { status: "running" })
  const runningCount = runningTasks?.tasks.length ?? 0
  const isTasksActive = location.pathname === tasksPath(projectSlug)

  const depsByType = {
    db_table: dependencies?.filter((dep) => dep.dep_type === "db_table") ?? [],
    external_api: dependencies?.filter((dep) => dep.dep_type === "external_api") ?? [],
    cache: dependencies?.filter((dep) => dep.dep_type === "cache") ?? [],
    kafka_topic: dependencies?.filter((dep) => dep.dep_type === "kafka_topic") ?? [],
  }

  const handleFeatureClick = (name: string) => {
    navigate(featurePath(projectSlug, name))
  }

  const handleDeleteFeature = (name: string) => {
    deleteFeatureMutation.mutate(name, {
      onSuccess: () => {
        if (selectedFeatureName === name) {
          navigate(projectPath(projectSlug))
        }
      },
    })
  }

  const handleDepClick = (dep: ProjectDependency) => {
    navigate(`${projectPath(projectSlug)}/dependencies/${dep.dep_type}/${encodeURIComponent(dep.name)}`)
  }

  const isDepActive = (dep: ProjectDependency) => selectedDep?.name === dep.name && selectedDep?.dep_type === dep.dep_type

  return (
    <aside className="relative flex h-screen shrink-0 flex-col border-r bg-muted/30" style={{ width: sidebarWidth }}>
      <SidebarHeader
        project={project}
        featureCount={features?.length ?? 0}
        totalDependencies={dependencies?.length ?? 0}
        onRename={(name) => renameMutation.mutate(name)}
      />

      <ScrollArea className="flex-1 min-h-0 px-2 py-3">
        <div className="space-y-5">
          <FeatureList
            features={features}
            selectedFeatureName={selectedFeatureName}
            onFeatureClick={handleFeatureClick}
            onDeleteFeature={handleDeleteFeature}
            isDeletePending={deleteFeatureMutation.isPending}
          />

          <section>
            <SidebarLabel>Зависимости</SidebarLabel>
            <div className="space-y-0.5">
              <DependencySection
                label="Таблицы БД"
                icon={<Database className="h-3.5 w-3.5" />}
                deps={depsByType.db_table}
                depType="db_table"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
              <DependencySection
                label="Внешние API"
                icon={<Globe className="h-3.5 w-3.5" />}
                deps={depsByType.external_api}
                depType="external_api"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
              <DependencySection
                label="Кэш"
                icon={<HardDrive className="h-3.5 w-3.5" />}
                deps={depsByType.cache}
                depType="cache"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
              <DependencySection
                label="Топики Kafka"
                icon={<MessageSquare className="h-3.5 w-3.5" />}
                deps={depsByType.kafka_topic}
                depType="kafka_topic"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
            </div>
          </section>

          <section className="px-0.5">
            <SidebarLabel>Источники</SidebarLabel>
            <SourcesPanel
              documents={documents}
              onReimport={onImportConfluence}
              isImporting={isImporting}
              isCheckingUpdates={isCheckingUpdates}
            />
            <div className="mt-2 px-1">
              <UploadZone onImportConfluence={onImportConfluence} isImporting={isImporting} importError={importError} />
            </div>
          </section>
        </div>
      </ScrollArea>

      <div className="flex gap-1.5 border-t p-3">
        <button
          onClick={() => navigate(tasksPath(projectSlug))}
          className={cn(
            "flex h-8 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border bg-background px-2 text-xs font-medium transition-colors",
            isTasksActive ? "border-foreground/30" : "hover:bg-muted",
          )}
        >
          <Activity className={cn("h-3.5 w-3.5 shrink-0", runningCount > 0 ? "text-amber-500" : "text-muted-foreground")} />
          Фоновые задачи
          {runningCount > 0 && (
            <span className="rounded-full bg-amber-500/15 px-1.5 text-[0.6875rem] font-medium text-amber-600 tabular-nums dark:text-amber-400">
              {runningCount}
            </span>
          )}
        </button>
        <div className="shrink-0">
          <ExportDialog projectSlug={projectSlug} />
        </div>
      </div>

      <div
        className="absolute top-0 right-0 h-full w-1 cursor-col-resize transition-colors hover:bg-border"
        onMouseDown={onStartDrag}
      />
    </aside>
  )
}
