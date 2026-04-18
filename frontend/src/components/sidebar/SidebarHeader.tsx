import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { homePath, rulesPath } from "@/lib/routes"
import { SidebarMetric } from "./sidebar-helpers"
import type { ProjectResponse } from "@/types/api"

interface SidebarHeaderProps {
  project: ProjectResponse
  featureCount: number
  readyFeatures: number
  errorFeatures: number
  totalDependencies: number
  onRename: (newName: string) => void
}

export function SidebarHeader({ project, featureCount, readyFeatures, errorFeatures, totalDependencies, onRename }: SidebarHeaderProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editedName, setEditedName] = useState("")

  const handleStartEdit = () => {
    setEditedName(project.name)
    setIsEditing(true)
  }

  const handleSave = () => {
    if (!editedName.trim()) return
    onRename(editedName.trim())
    setIsEditing(false)
  }

  return (
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
        {isEditing ? (
          <div className="flex items-center gap-1">
            <input
              className="min-w-0 flex-1 border-b border-primary bg-transparent text-base font-semibold outline-none"
              value={editedName}
              onChange={(e) => setEditedName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave()
                if (e.key === "Escape") setIsEditing(false)
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
          <SidebarMetric label="Фичи" value={featureCount} helper={`${readyFeatures} готовы${errorFeatures > 0 ? `, ${errorFeatures} ошибок` : ""}`} />
          <SidebarMetric label="Источники" value={project.document_count} helper={`${totalDependencies} зависимостей`} />
        </div>
      </div>
    </div>
  )
}
