import { useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { Plus } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { EnrichUploadZone } from "@/components/dependency/EnrichUploadZone"
import { useDeleteDependency, useCreateDependency } from "@/hooks/useDependencies"
import { projectPath } from "@/lib/routes"
import { DependencyListItem } from "./DependencyListItem"
import { CreateDependencyDialog } from "./CreateDependencyDialog"
import type { CreateDependencyRequest, DependencyType, ProjectDependency } from "@/types/api"

interface DependencySectionProps {
  label: string
  icon: ReactNode
  deps: ProjectDependency[]
  depType: DependencyType
  projectSlug: string
  isDepActive: (dep: ProjectDependency) => boolean
  onDepClick: (dep: ProjectDependency) => void
}

export function DependencySection({ label, icon, deps, depType, projectSlug, isDepActive, onDepClick }: DependencySectionProps) {
  const navigate = useNavigate()
  const hasRunning = deps.some(d => d.enrichment_status === "running")
  const deleteDep = useDeleteDependency(projectSlug)
  const createDep = useCreateDependency(projectSlug)
  const [createOpen, setCreateOpen] = useState(false)

  const handleCreate = (req: CreateDependencyRequest) => {
    createDep.mutate(req, {
      onSuccess: () => setCreateOpen(false),
    })
  }

  return (
    <>
      <Collapsible>
        <div className="mb-1 flex items-center justify-between px-1">
          <CollapsibleTrigger className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground">
            {icon}
            {label}
            {deps.length > 0 && <span className="text-[0.625rem] font-normal">({deps.length})</span>}
          </CollapsibleTrigger>

          <div className="flex items-center gap-1">
            {(depType === "db_table" || depType === "cache") && (
              <EnrichUploadZone projectSlug={projectSlug} depType={depType} isRunning={hasRunning} />
            )}
            <button
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              title={`Добавить ${label.toLowerCase()}`}
              onClick={() => setCreateOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <CollapsibleContent>
          <div className="space-y-1">
            {deps.map((dep) => (
              <DependencyListItem
                key={dep.name}
                dep={dep}
                isActive={isDepActive(dep)}
                onClick={() => onDepClick(dep)}
                onDelete={() => {
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
                }}
                isDeletePending={deleteDep.isPending}
              />
            ))}

            {deps.length === 0 && (
              <div className="rounded-xl border border-dashed px-3 py-3 text-xs text-muted-foreground">
                Пока нет зависимостей этого типа.
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      <CreateDependencyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        depType={depType}
        onSubmit={handleCreate}
        isPending={createDep.isPending}
      />
    </>
  )
}
