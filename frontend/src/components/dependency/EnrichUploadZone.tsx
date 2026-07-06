import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useEnrichDependency } from "@/hooks/useDependencies"
import { AnimatedDots } from "./AnimatedDots"

interface EnrichUploadZoneProps {
  projectSlug: string
  depType: string
  depName?: string
  isRunning?: boolean
}

export function EnrichUploadZone({ projectSlug, depType, depName, isRunning }: EnrichUploadZoneProps) {
  const [editing, setEditing] = useState(false)
  const [url, setUrl] = useState("")
  const enrichMutation = useEnrichDependency(projectSlug)

  const submit = () => {
    const trimmed = url.trim()
    if (trimmed) {
      enrichMutation.mutate({ depType, url: trimmed, depName })
    }
    setUrl("")
    setEditing(false)
  }

  if (isRunning || enrichMutation.isPending) {
    return <AnimatedDots className="text-xs px-2" />
  }

  if (editing) {
    return (
      <input
        autoFocus
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit()
          if (e.key === "Escape") { setUrl(""); setEditing(false) }
        }}
        onBlur={submit}
        placeholder="Ссылка на Confluence"
        className="h-6 w-44 rounded border bg-background px-1.5 text-xs outline-none placeholder:text-muted-foreground/60 focus:border-primary"
        onClick={(e) => e.stopPropagation()}
      />
    )
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-6 px-2 text-xs"
      onClick={(e) => { e.stopPropagation(); setEditing(true) }}
    >
      + Confluence
    </Button>
  )
}
