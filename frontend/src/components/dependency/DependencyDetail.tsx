import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DbSchemaView } from "./DbSchemaView"
import { ApiEndpointsView } from "./ApiEndpointsView"
import { CacheStructureView } from "./CacheStructureView"
import { KafkaTopicView } from "./KafkaTopicView"
import { ExternalDocView } from "./ExternalDocView"
import { EnrichUploadZone } from "./EnrichUploadZone"
import { AnimatedDots } from "./AnimatedDots"
import { usePatchDependency, useDeleteDependency, useProjectDependencies, useEnrichDependency } from "@/hooks/useDependencies"
import { Loader2, Pencil, RefreshCw, Trash2 } from "lucide-react"
import { dependencyPath, projectPath } from "@/lib/routes"
import { useConfirm } from "@/components/ConfirmDialog"
import type { ProjectDependency, DbTableEnrichment, ExternalApiEnrichment, CacheEnrichment, KafkaTopicEnrichment, ExternalDocEnrichment, DepItemsDiff, DepSourceDiff } from "@/types/api"

const diffSectionLabels: Record<string, string> = {
  columns: "Колонки",
  endpoints: "Эндпоинты",
  message_fields: "Поля сообщения",
  key_patterns: "Ключи",
}

/** "Что изменилось в источнике" — deterministic diff of the last re-enrichment. */
function SourceDiffBlock({ diff }: { diff: DepSourceDiff }) {
  const sections = (Object.keys(diffSectionLabels) as (keyof typeof diffSectionLabels)[])
    .map((key) => ({ key, items: diff[key as keyof DepSourceDiff] as DepItemsDiff | undefined }))
    .filter((s) => s.items)
  if (sections.length === 0 && !diff.content_changed) return null

  return (
    <div className="space-y-2 rounded-2xl border border-border/70 bg-muted/[0.15] px-4 py-3 text-[0.8125rem]">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Что изменилось в источнике
        {diff.old_version && diff.new_version ? ` (v${diff.old_version} → v${diff.new_version})` : ""}
      </p>
      {diff.content_changed && <p>Содержимое документа изменилось — просмотрите его заново.</p>}
      {sections.map(({ key, items }) => (
        <div key={key} className="space-y-0.5">
          <p className="text-xs font-medium text-muted-foreground">{diffSectionLabels[key]}</p>
          {items!.added.map((n) => (
            <p key={`a${n}`} className="font-mono text-emerald-700 dark:text-emerald-400">+ {n}</p>
          ))}
          {items!.removed.map((n) => (
            <p key={`r${n}`} className="font-mono text-red-700 line-through dark:text-red-400">{n}</p>
          ))}
          {items!.changed.map((c) => (
            <p key={`c${c.name}`} className="font-mono">
              ~ {c.name}{" "}
              <span className="font-sans text-muted-foreground">
                ({c.changes.map((ch) => `${ch.field}: ${ch.old || "∅"} → ${ch.new || "∅"}`).join(", ")})
              </span>
            </p>
          ))}
        </div>
      ))}
    </div>
  )
}

const typeLabels: Record<string, string> = {
  db_table: "Таблица БД",
  external_api: "Внешний API",
  cache: "Кэш",
  kafka_topic: "Kafka-топик",
  external_doc: "Документ",
}

export function DependencyDetail({ dep, projectSlug }: { dep: ProjectDependency; projectSlug: string }) {
  const navigate = useNavigate()
  const askConfirm = useConfirm()
  const isEnriched = dep.enrichment_status === "enriched" && dep.enriched_data
  const isEnriching = dep.enrichment_status === "running"

  const patchDep = usePatchDependency(projectSlug)
  const deleteDep = useDeleteDependency(projectSlug)
  const enrichDep = useEnrichDependency(projectSlug)

  // An FK names its target table ("product_schedule.id"); a table the project actually
  // has becomes a link. Case-insensitive: the FK text and the dependency name are both
  // written by hand and need not agree on case.
  const { data: allDeps } = useProjectDependencies(projectSlug)
  const tableNames = useMemo(() => {
    const map = new Map<string, string>()
    for (const d of allDeps ?? []) {
      if (d.dep_type === "db_table") map.set(d.name.toLowerCase(), d.name)
    }
    return map
  }, [allDeps])
  const knownTables = useMemo(() => new Set(tableNames.keys()), [tableNames])

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

  const handleDelete = async () => {
    const ok = await askConfirm({
      title: `Удалить зависимость "${dep.name}"?`,
      description: "Действие нельзя отменить.",
      confirmText: "Удалить",
      destructive: true,
    })
    if (ok) {
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
          <Badge variant={isEnriched ? "default" : isEnriching ? "secondary" : "outline"} className="text-xs">
            {isEnriched ? "Обогащена" : isEnriching ? "Обогащение..." : "Черновик"}
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
          <p className="text-xs text-muted-foreground">
            Источник:{" "}
            {dep.source_page_url ? (
              <a href={dep.source_page_url} target="_blank" rel="noreferrer" className="hover:underline">
                {dep.source_pdf_name}
              </a>
            ) : (
              dep.source_pdf_name
            )}
            {dep.source_page_version ? ` · v${dep.source_page_version}` : ""}
          </p>
        )}
      </div>

      {dep.source_outdated && dep.source_page_url && !isEnriching && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-amber-200/70 bg-amber-50/40 px-4 py-2.5 text-[0.8125rem] text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/10 dark:text-amber-300">
          <span className="min-w-0 flex-1">
            Страница-источник обновилась: v{dep.source_page_version} → v{dep.latest_source_version}.
            Данные зависимости могли устареть.
          </span>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0 border-amber-300 text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-900/30"
            disabled={enrichDep.isPending}
            onClick={() =>
              enrichDep.mutate({ depType: dep.dep_type, url: dep.source_page_url!, depName: dep.name })
            }
          >
            {enrichDep.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Переобогатить
          </Button>
        </div>
      )}

      {dep.last_source_diff && !isEnriching && <SourceDiffBlock diff={dep.last_source_diff} />}

      {isEnriched ? (
        <div>
          {dep.dep_type === "db_table" && (
            <DbSchemaView
              data={dep.enriched_data as DbTableEnrichment}
              knownTables={knownTables}
              onNavigateToTable={(table) =>
                navigate(dependencyPath(projectSlug, "db_table", tableNames.get(table.toLowerCase()) ?? table))
              }
            />
          )}
          {dep.dep_type === "external_api" && <ApiEndpointsView data={dep.enriched_data as ExternalApiEnrichment} />}
          {dep.dep_type === "cache" && <CacheStructureView data={dep.enriched_data as CacheEnrichment} />}
          {dep.dep_type === "kafka_topic" && <KafkaTopicView data={dep.enriched_data as KafkaTopicEnrichment} />}
          {dep.dep_type === "external_doc" && <ExternalDocView data={dep.enriched_data as ExternalDocEnrichment} />}
        </div>
      ) : isEnriching ? (
        <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
          <p className="text-sm text-muted-foreground">Обогащаем из Confluence...</p>
          <AnimatedDots className="text-lg" />
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
          <p className="text-sm text-muted-foreground">
            Зависимость ещё не обогащена. Укажите ссылку на страницу Confluence со спецификацией.
          </p>
          <EnrichUploadZone projectSlug={dep.project_slug} depType={dep.dep_type} depName={dep.name} />
        </div>
      )}
    </div>
  )
}
