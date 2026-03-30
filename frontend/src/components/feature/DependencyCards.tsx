import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { X, Plus } from "lucide-react"
import type { UsedDependency, ProjectDependency } from "@/types/api"

interface DependencyCardsProps {
  dependencies: UsedDependency[]
  projectDependencies?: ProjectDependency[]
  onDepClick?: (depName: string) => void
  isEditing?: boolean
  onChange?: (deps: UsedDependency[]) => void
}

const SECTION_CONFIG = {
  db_table: { label: "DB Tables", prefix: "DB", badgeClass: "bg-blue-100 text-blue-800 border-blue-200" },
  external_api: { label: "External APIs", prefix: "API", badgeClass: "bg-purple-100 text-purple-800 border-purple-200" },
  cache: { label: "Cache", prefix: "Cache", badgeClass: "bg-orange-100 text-orange-800 border-orange-200" },
  kafka_topic: { label: "Kafka Topics", prefix: "Kafka", badgeClass: "bg-green-100 text-green-800 border-green-200" },
} as const

type DepType = keyof typeof SECTION_CONFIG

function normalizeName(name: string) {
  return name.toLowerCase().replace(/\s/g, "_")
}

function effectiveName(dep: UsedDependency): string {
  if (dep.type === "external_api" && dep.service_name && dep.path) {
    return `${dep.service_name}/${dep.path.replace(/^\//, "")}`
  }
  return dep.name
}

function DepMethodBadge({ method }: { method?: string }) {
  if (!method) return null
  const colorMap: Record<string, string> = {
    GET: "bg-green-100 text-green-700",
    POST: "bg-blue-100 text-blue-700",
    PUT: "bg-orange-100 text-orange-700",
    DELETE: "bg-red-100 text-red-700",
    PATCH: "bg-yellow-100 text-yellow-700",
  }
  const c = colorMap[method] ?? "bg-slate-100 text-slate-700"
  return <span className={`font-semibold font-mono text-[10px] px-1 py-0.5 rounded shrink-0 ${c}`}>{method}</span>
}

function emptyDep(type: DepType): UsedDependency {
  return { type, name: "", description: "" }
}

function EditableDependencyCard({
  dep,
  onUpdate,
  onDelete,
}: {
  dep: UsedDependency
  onUpdate: (updated: UsedDependency) => void
  onDelete: () => void
}) {
  return (
    <div className="rounded border p-2 space-y-1.5 bg-background">
      <div className="flex items-start gap-1">
        <div className="flex-1 space-y-1">
          {dep.type === "external_api" && (
            <div className="flex items-center gap-1">
              <select
                className="text-xs font-mono bg-transparent border-b border-border outline-none"
                value={dep.method ?? ""}
                onChange={(e) => onUpdate({ ...dep, method: e.target.value || undefined })}
              >
                <option value="">—</option>
                {["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <input
                className="text-xs bg-transparent border-b border-border outline-none flex-1"
                value={dep.service_name ?? ""}
                placeholder="service_name"
                onChange={(e) => onUpdate({ ...dep, service_name: e.target.value || undefined })}
              />
            </div>
          )}
          <input
            className="font-mono font-medium text-sm bg-transparent border-b border-border outline-none w-full"
            value={dep.name}
            placeholder="name"
            onChange={(e) => onUpdate({ ...dep, name: e.target.value })}
          />
          {dep.type === "external_api" && (
            <input
              className="text-xs bg-transparent border-b border-border outline-none w-full text-muted-foreground"
              value={dep.path ?? ""}
              placeholder="path (e.g. /api/resource)"
              onChange={(e) => onUpdate({ ...dep, path: e.target.value || undefined })}
            />
          )}
          <textarea
            className="text-xs text-muted-foreground bg-transparent border border-border rounded px-1.5 py-1 outline-none w-full resize-none"
            value={dep.description}
            placeholder="description"
            rows={2}
            onChange={(e) => onUpdate({ ...dep, description: e.target.value })}
          />
        </div>
        <button
          className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors shrink-0"
          title="Delete"
          onClick={onDelete}
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

export function DependencyCards({ dependencies, projectDependencies, onDepClick, isEditing = false, onChange }: DependencyCardsProps) {

  if (!isEditing && dependencies.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет зависимостей</p>
  }

  const grouped = dependencies.reduce<Record<DepType, UsedDependency[]>>(
    (acc, dep) => {
      const key = dep.type as DepType
      if (key in acc) {
        acc[key].push(dep)
      }
      return acc
    },
    { db_table: [], external_api: [], cache: [], kafka_topic: [] }
  )

  const sections = isEditing
    ? (Object.keys(SECTION_CONFIG) as DepType[])
    : (Object.keys(SECTION_CONFIG) as DepType[]).filter((key) => grouped[key].length > 0)

  const updateDep = (depIdx: number, updated: UsedDependency) => {
    onChange?.(dependencies.map((d, i) => (i === depIdx ? updated : d)))
  }

  const deleteDep = (depIdx: number) => {
    onChange?.(dependencies.filter((_, i) => i !== depIdx))
  }

  const addDep = (type: DepType) => {
    onChange?.([...dependencies, emptyDep(type)])
  }

  return (
    <div className="space-y-4">
      {sections.map((type) => {
        const config = SECTION_CONFIG[type]
        const items = grouped[type]

        // Build per-section indices into full dependencies array
        const sectionIndices = dependencies
          .map((d, i) => ({ d, i }))
          .filter(({ d }) => d.type === type)

        return (
          <Card key={type}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <span className="font-mono text-xs px-1.5 py-0.5 rounded border">
                  {config.prefix}
                </span>
                {config.label}
                {!isEditing && (() => {
                  const unenrichedCount = items.filter(dep => {
                    const pd = projectDependencies?.find(
                      p => p.dep_type === dep.type && normalizeName(p.name) === normalizeName(effectiveName(dep))
                    )
                    return !pd || pd.enrichment_status !== "enriched"
                  }).length
                  return unenrichedCount > 0 ? (
                    <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">
                      {unenrichedCount} unenriched
                    </Badge>
                  ) : null
                })()}
                <Badge variant="secondary" className="text-xs ml-auto">
                  {items.length}
                </Badge>
                {isEditing && (
                  <button
                    className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                    title={`Add ${config.label}`}
                    onClick={() => addDep(type)}
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isEditing ? (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {sectionIndices.map(({ d: dep, i: depIdx }) => (
                    <EditableDependencyCard
                      key={depIdx}
                      dep={dep}
                      onUpdate={(updated) => updateDep(depIdx, updated)}
                      onDelete={() => deleteDep(depIdx)}
                    />
                  ))}
                  {items.length === 0 && (
                    <p className="text-xs text-muted-foreground col-span-full">Нет зависимостей. Нажмите + для добавления.</p>
                  )}
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {items.map((dep, i) => {
                    const depName = effectiveName(dep)
                    const registryDep = projectDependencies?.find(
                      pd => pd.dep_type === dep.type && normalizeName(pd.name) === normalizeName(depName)
                    )
                    const clickable = registryDep && onDepClick
                    const isUnenriched = !registryDep || registryDep.enrichment_status !== "enriched"
                    return (
                      <div
                        key={i}
                        className={`rounded border p-2 space-y-1 ${clickable ? "cursor-pointer hover:border-primary hover:bg-accent/50 transition-colors" : ""}`}
                        onClick={clickable ? () => onDepClick(registryDep.name) : undefined}
                      >
                        <div className="flex items-center gap-1">
                          {dep.type === "external_api" && <DepMethodBadge method={dep.method} />}
                          <p className="font-mono font-medium text-sm truncate">{depName}</p>
                          {isUnenriched && (
                            <span
                              className="ml-auto shrink-0 text-amber-500 text-sm leading-none"
                              title="Не обогащена"
                            >
                              &#x26A0;
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{dep.description}</p>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
