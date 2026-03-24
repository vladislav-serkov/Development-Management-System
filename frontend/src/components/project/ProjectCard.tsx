import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ExtractionProgress } from "@/components/progress/ExtractionProgress"
import { useExtractionSSE } from "@/hooks/useExtraction"
import { useUIStore } from "@/stores/uiStore"
import type { DocumentResponse } from "@/types/api"

interface ProjectCardProps {
  document: DocumentResponse
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

export function ProjectCard({ document }: ProjectCardProps) {
  const setSelectedDocument = useUIStore((s) => s.setSelectedDocument)
  const isActive = document.status === "processing" || document.status === "extracting"

  useExtractionSSE(document.id, isActive)

  const displayName = document.filename.replace(/\.pdf$/i, "")
  const uploadedDate = new Date(document.uploaded_at).toLocaleDateString()

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => setSelectedDocument(document.id)}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="truncate">{displayName}</CardTitle>
          <Badge variant={statusVariant(document.status)} className="shrink-0 text-xs capitalize">
            {document.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{document.feature_count} feature{document.feature_count !== 1 ? "s" : ""}</span>
            <span>·</span>
            <span>{uploadedDate}</span>
          </div>
          {isActive && (
            <ExtractionProgress
              status={document.status}
              features={document.features.map((f) => ({ name: f.name, status: f.status }))}
            />
          )}
          {(document.status === "done" || document.status === "partial" || document.status === "error") && (
            <ExtractionProgress
              status={document.status}
              features={document.features.map((f) => ({ name: f.name, status: f.status }))}
            />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
