import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { homePath, rulesPath } from "@/lib/routes"
import { countLabel } from "@/lib/plural"
import type { ProjectResponse } from "@/types/api"

interface SidebarHeaderProps {
  project: ProjectResponse
  featureCount: number
  totalDependencies: number
  onRename: (newName: string) => void
}

export function SidebarHeader({ project, featureCount, totalDependencies, onRename }: SidebarHeaderProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editedName, setEditedName] = useState("")

  const handleSave = () => {
    if (!editedName.trim()) return
    onRename(editedName.trim())
    setIsEditing(false)
  }

  return (
    <div className="border-b px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" className="-ml-2 text-xs" onClick={() => navigate(homePath())}>
          &larr; Все проекты
        </Button>
        <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" onClick={() => navigate(rulesPath())}>
          Правила
        </Button>
      </div>

      <div className="mt-2">
        {isEditing ? (
          <input
            className="w-full border-b border-primary bg-transparent text-base font-semibold outline-none"
            value={editedName}
            onChange={(e) => setEditedName(e.target.value)}
            onBlur={() => setIsEditing(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave()
              if (e.key === "Escape") setIsEditing(false)
            }}
            autoFocus
          />
        ) : (
          <button
            type="button"
            className="block w-full truncate text-left text-base font-semibold transition-colors hover:text-primary/80"
            onClick={() => {
              setEditedName(project.name)
              setIsEditing(true)
            }}
            title="Нажмите, чтобы переименовать проект"
          >
            {project.name}
          </button>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground">
          {countLabel(featureCount, ["фича", "фичи", "фич"])} · {countLabel(project.document_count, ["источник", "источника", "источников"])} ·{" "}
          {countLabel(totalDependencies, ["зависимость", "зависимости", "зависимостей"])}
        </p>
      </div>
    </div>
  )
}
