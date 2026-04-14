import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DbSchemaView } from "./DbSchemaView"
import { ApiEndpointsView } from "./ApiEndpointsView"
import { CacheStructureView } from "./CacheStructureView"
import { KafkaTopicView } from "./KafkaTopicView"
import { EnrichUploadZone } from "./EnrichUploadZone"
import { AnimatedDots } from "./AnimatedDots"
import { useUIStore } from "@/stores/uiStore"
import { usePatchDependency, useDeleteDependency } from "@/hooks/useDependencies"
import { Pencil, Trash2 } from "lucide-react"
import { dependencyPath, projectPath } from "@/lib/routes"
import type { ProjectDependency, DbTableEnrichment, ExternalApiEnrichment, CacheEnrichment, KafkaTopicEnrichment } from "@/types/api"

const typeLabels: Record<string, string> = {
  db_table: "Таблица БД",
  external_api: "Внешний API",
  cache: "Кэш",
  kafka_topic: "Kafka-топик",
}

export function DependencyDetail({ dep, projectSlug }: { dep: ProjectDependency; projectSlug: string }) {
  const navigate = useNavigate()
  const isEnriched = dep.enrichment_status === "enriched" && dep.enriched_data
  const enrichingDepTypes = useUIStore((s) => s.enrichingDepTypes)
  const isEnriching = enrichingDepTypes.includes(dep.dep_type)

  const patchDep = usePatchDependency(projectSlug)
  const deleteDep = useDeleteDependency(projectSlug)

  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState(dep.name)
  const [editDesc, setEditDesc] = useState(dep.description ?? "")

  const startEdit = () => {
    setEditName(dep.name)
    setEditDesc(dep.description ?? "")
    setIsEditing(true)
  }

  const cancelEdit = () => setIsEditing(false)

  const saveEdit = () => {
    const patch: Record<string, string> = {}
    if (editName.trim() && editName.trim() !== dep.name) patch.name = editName.trim()
    if (editDesc.trim() !== (dep.description ?? "")) patch.description = editDesc.trim()

    if (Object.keys(patch).length === 0) {
      setIsEditing(false)
      return
    }

    patchDep.mutate(
      { depName: dep.name, depType: dep.dep_type, patch },
      {
        onSuccess: () => {
          setIsEditing(false)
          if (patch.name) {
            navigate(dependencyPath(projectSlug, dep.dep_type, patch.name), { replace: true })
          }
        },
      }
    )
  }

  const handleDelete = () => {
    if (window.confirm(`Удалить зависимость "${dep.name}"?`)) {
      deleteDep.mutate(
        { depName: dep.name, depType: dep.dep_type },
        { onSuccess: () => navigate(projectPath(projectSlug)) }
      )
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        {/* Save/Cancel bar when editing */}
        {isEditing && (
          <div className="flex items-center gap-2 mb-2 pb-2 border-b">
            <Button size="sm" onClick={saveEdit} disabled={patchDep.isPending}>
              {patchDep.isPending ? "Сохраняем..." : "Сохранить"}
            </Button>
            <Button size="sm" variant="ghost" onClick={cancelEdit}>Отмена</Button>
          </div>
        )}

        <div className="flex items-center gap-2 flex-wrap">
          {isEditing ? (
            <input
              className="text-xl font-semibold bg-transparent border-b-2 border-primary outline-none min-w-0 flex-1"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              autoFocus
            />
          ) : (
            <h2 className="text-xl font-semibold">{dep.name}</h2>
          )}
          <Badge variant="secondary" className="text-xs">{typeLabels[dep.dep_type] ?? dep.dep_type}</Badge>
          <Badge variant={isEnriched ? "default" : "outline"} className="text-xs">
            {isEnriched ? "Обогащена" : "Черновик"}
          </Badge>

          {!isEditing && (
            <div className="ml-auto flex items-center gap-1">
              <button onClick={startEdit} className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title="Редактировать">
                <Pencil className="h-4 w-4" />
              </button>
              <button onClick={handleDelete} className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors" title="Удалить">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {isEditing ? (
          <input
            className="text-sm bg-transparent border-b border-muted-foreground/30 outline-none w-full focus:border-primary transition-colors"
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            placeholder="Описание"
          />
        ) : (
          dep.description && <p className="text-sm text-muted-foreground">{dep.description}</p>
        )}

        {dep.source_pdf_name && (
          <p className="text-xs text-muted-foreground">Источник: {dep.source_pdf_name}</p>
        )}
      </div>

      {isEnriched ? (
        <div>
          {dep.dep_type === "db_table" && <DbSchemaView data={dep.enriched_data as DbTableEnrichment} />}
          {dep.dep_type === "external_api" && <ApiEndpointsView data={dep.enriched_data as ExternalApiEnrichment} />}
          {dep.dep_type === "cache" && <CacheStructureView data={dep.enriched_data as CacheEnrichment} />}
          {dep.dep_type === "kafka_topic" && <KafkaTopicView data={dep.enriched_data as KafkaTopicEnrichment} />}
        </div>
      ) : isEnriching ? (
        <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
          <p className="text-sm text-muted-foreground">Загружаем PDF...</p>
          <AnimatedDots className="text-lg" />
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
          <p className="text-sm text-muted-foreground">
            Зависимость ещё не обогащена. Загрузите PDF со спецификацией.
          </p>
          <EnrichUploadZone projectSlug={dep.project_slug} depType={dep.dep_type} depName={dep.name} />
        </div>
      )}
    </div>
  )
}
