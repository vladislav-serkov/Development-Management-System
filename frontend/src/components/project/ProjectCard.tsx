import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useUIStore } from "@/stores/uiStore"

interface ProjectCardProject {
  slug: string
  name: string
  status: string
  feature_count: number
  document_count: number
}

interface ProjectCardProps {
  project: ProjectCardProject
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "done": return "default"
    case "processing":
    case "extracting": return "outline"
    case "error": return "destructive"
    case "partial": return "secondary"
    default: return "secondary"
  }
}

export function ProjectCard({ project }: ProjectCardProps) {
  const goToProject = useUIStore((s) => s.goToProject)

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => goToProject(project.slug)}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="truncate text-base">{project.name}</CardTitle>
          <Badge variant={statusVariant(project.status)} className="shrink-0 text-xs capitalize">
            {project.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-xs text-muted-foreground">
          {project.feature_count} feature{project.feature_count !== 1 ? "s" : ""} · {project.document_count} PDF
        </div>
      </CardContent>
    </Card>
  )
}
