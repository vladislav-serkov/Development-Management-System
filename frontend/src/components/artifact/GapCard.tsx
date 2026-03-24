import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { JSONViewer } from "@/components/artifact/JSONViewer"
import type { GapResponse } from "@/types/api"

interface GapCardProps {
  gap: GapResponse
}

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  switch (priority) {
    case "critical": return "destructive"
    case "medium": return "secondary"
    case "low": return "outline"
    default: return "secondary"
  }
}

export function GapCard({ gap }: GapCardProps) {
  const [showSuggestion, setShowSuggestion] = useState(false)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{gap.name}</CardTitle>
          <div className="flex items-center gap-1 shrink-0">
            <Badge variant={priorityVariant(gap.priority)} className="text-xs capitalize">
              {gap.priority}
            </Badge>
            <Badge variant="outline" className="text-xs capitalize">
              {gap.category}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">{gap.what_missing}</p>

        {gap.affected_features.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {gap.affected_features.map((feature, i) => (
              <Badge key={i} variant="secondary" className="text-xs">
                {feature}
              </Badge>
            ))}
          </div>
        )}

        {gap.suggestion && (
          <div>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 px-2"
              onClick={() => setShowSuggestion((v) => !v)}
            >
              {showSuggestion ? "Hide suggestion" : "Show suggestion"}
            </Button>
            {showSuggestion && (
              <div className="mt-2">
                <JSONViewer value={gap.suggestion} />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
