import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { JSONViewer } from "@/components/artifact/JSONViewer"
import type { GapResponse } from "@/types/api"

interface GapCardProps {
  gap: GapResponse
  onSave?: (patch: { what_missing?: string; priority?: string; affected_features?: string[] }) => void
  isSaving?: boolean
}

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  switch (priority) {
    case "critical": return "destructive"
    case "medium": return "secondary"
    case "low": return "outline"
    default: return "secondary"
  }
}

export function GapCard({ gap, onSave, isSaving }: GapCardProps) {
  const [showSuggestion, setShowSuggestion] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editedWhatMissing, setEditedWhatMissing] = useState(gap.what_missing)
  const [editedPriority, setEditedPriority] = useState(gap.priority)

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
            {onSave && !isEditing && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  setEditedWhatMissing(gap.what_missing)
                  setEditedPriority(gap.priority)
                  setIsEditing(true)
                }}
              >
                Edit
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isEditing ? (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">What's missing</label>
              <textarea
                className="w-full text-sm border rounded p-2 min-h-24 resize-y mt-1"
                value={editedWhatMissing}
                onChange={(e) => setEditedWhatMissing(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Priority</label>
              <select
                value={editedPriority}
                onChange={(e) => setEditedPriority(e.target.value)}
                className="block text-sm border rounded p-1.5 mt-1"
              >
                <option value="critical">Critical</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => {
                  onSave?.({ what_missing: editedWhatMissing, priority: editedPriority })
                  setIsEditing(false)
                }}
                disabled={isSaving}
              >
                {isSaving ? "Saving..." : "Save"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <>
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
          </>
        )}
      </CardContent>
    </Card>
  )
}
