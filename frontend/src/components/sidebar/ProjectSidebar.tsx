import { useNavigate } from "react-router-dom"
import { Database, Globe, HardDrive, MessageSquare } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ExportDialog } from "@/components/project/ExportDialog"
import { UploadZone } from "@/components/project/UploadZone"
import { useDeleteFeature } from "@/hooks/useDocuments"
import { useRenameProject } from "@/hooks/useDocuments"
import { featurePath, projectPath } from "@/lib/routes"
import { SidebarHeader } from "./SidebarHeader"
import { FeatureList } from "./FeatureList"
import { DependencySection } from "./DependencySection"
import type { FeatureResponse, ProjectDependency, ProjectResponse } from "@/types/api"

interface ProjectSidebarProps {
  project: ProjectResponse
  projectSlug: string
  features: FeatureResponse[] | undefined
  dependencies: ProjectDependency[] | undefined
  selectedFeatureName: string | null
  selectedDep: ProjectDependency | null
  onUpload: (file: File) => void
  isUploading: boolean
  sidebarWidth: number
  onStartDrag: () => void
}

export function ProjectSidebar({
  project,
  projectSlug,
  features,
  dependencies,
  selectedFeatureName,
  selectedDep,
  onUpload,
  isUploading,
  sidebarWidth,
  onStartDrag,
}: ProjectSidebarProps) {
  const navigate = useNavigate()
  const renameMutation = useRenameProject(projectSlug)
  const deleteFeatureMutation = useDeleteFeature(projectSlug)

  const readyFeatures = features?.filter((f) => f.status === "done").length ?? 0
  const errorFeatures = features?.filter((f) => f.status === "error").length ?? 0
  const totalDependencies = dependencies?.length ?? 0

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
        readyFeatures={readyFeatures}
        errorFeatures={errorFeatures}
        totalDependencies={totalDependencies}
        onRename={(name) => renameMutation.mutate(name)}
      />

      <div className="border-b p-4">
        <div className="mb-2 px-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Источники</p>
          <p className="mt-1 text-xs text-muted-foreground">Загрузите PDF, чтобы обновить фичи и зависимости проекта.</p>
        </div>
        <UploadZone onUpload={onUpload} isUploading={isUploading} />
      </div>

      <ScrollArea className="flex-1 min-h-0 p-4">
        <div className="space-y-5">
          <FeatureList
            features={features}
            selectedFeatureName={selectedFeatureName}
            onFeatureClick={handleFeatureClick}
            onDeleteFeature={handleDeleteFeature}
            isDeletePending={deleteFeatureMutation.isPending}
          />

          <section>
            <div className="space-y-4">
              <DependencySection
                label="DB"
                icon={<Database className="h-3.5 w-3.5" />}
                deps={depsByType.db_table}
                depType="db_table"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
              <DependencySection
                label="API"
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
                label="Топики"
                icon={<MessageSquare className="h-3.5 w-3.5" />}
                deps={depsByType.kafka_topic}
                depType="kafka_topic"
                projectSlug={projectSlug}
                isDepActive={isDepActive}
                onDepClick={handleDepClick}
              />
            </div>
          </section>
        </div>
      </ScrollArea>

      <div className="border-t p-4">
        <div className="mb-2 px-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Экспорт</p>
          <p className="mt-1 text-xs text-muted-foreground">Соберите текущее состояние проекта в архив.</p>
        </div>
        <ExportDialog projectSlug={projectSlug} />
      </div>

      <div
        className="absolute top-0 right-0 h-full w-1 cursor-col-resize transition-colors hover:bg-border"
        onMouseDown={onStartDrag}
      />
    </aside>
  )
}
