import { useProjects } from "@/hooks/useDocuments"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useNavigate } from "react-router-dom"
import { projectPath } from "@/lib/routes"

export function ProjectGrid() {
  const { data: projects, isLoading, error } = useProjects()
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-32 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">
          Не удалось загрузить проекты. Обновите страницу и попробуйте снова.
        </p>
      )}

      {!isLoading && !error && projects && projects.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-8">
          Проектов пока нет. Создайте первый, чтобы начать работу.
        </p>
      )}

      {!isLoading && projects && projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <Card
              key={project.slug}
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => navigate(projectPath(project.slug))}
            >
              <CardHeader>
                <CardTitle className="truncate text-base">{project.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-xs">
                    {project.feature_count} фич
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {project.document_count} документов
                  </Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
