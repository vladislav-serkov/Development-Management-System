import { Badge } from "@/components/ui/badge"
import type { DocumentStatus, FeatureStatus } from "@/types/api"

interface ExtractionProgressProps {
  status: DocumentStatus
  features: { name: string; status: FeatureStatus }[]
}

function featureStatusVariant(status: FeatureStatus): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "done":
      return "default"
    case "extracting":
      return "outline"
  }
}

function featureStatusLabel(status: FeatureStatus): string {
  switch (status) {
    case "done": return "done"
    case "extracting": return "extracting"
  }
}

export function ExtractionProgress({ status, features }: ExtractionProgressProps) {
  if (status === "pending") {
    return <p className="text-xs text-muted-foreground">Waiting...</p>
  }

  if (status === "processing" || status === "extracting") {
    const doneCount = features.filter((f) => f.status === "done").length
    const totalCount = features.length

    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">
          {doneCount}/{totalCount} features extracted
        </p>
        <div className="space-y-1">
          {features.map((feature, i) => (
            <div key={i} className="flex items-center gap-2">
              <Badge variant={featureStatusVariant(feature.status)} className="text-xs">
                {featureStatusLabel(feature.status)}
              </Badge>
              <span className="text-xs truncate max-w-[10rem]">{feature.name}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (status === "done") {
    return (
      <div className="flex items-center gap-1">
        <span className="text-green-600 text-xs">✓</span>
        <span className="text-xs text-green-600">Complete</span>
      </div>
    )
  }

  if (status === "error") {
    return (
      <div className="flex items-center gap-1">
        <span className="text-destructive text-xs">✗</span>
        <span className="text-xs text-destructive">Error</span>
      </div>
    )
  }

  if (status === "partial") {
    return (
      <div className="flex items-center gap-1">
        <span className="text-amber-500 text-xs">⚠</span>
        <span className="text-xs text-amber-600">Partial</span>
      </div>
    )
  }

  return null
}
