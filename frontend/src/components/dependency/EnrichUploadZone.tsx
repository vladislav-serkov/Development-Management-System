import { useRef } from "react"
import { Button } from "@/components/ui/button"
import { useEnrichDependency } from "@/hooks/useDependencies"
import { useUIStore } from "@/stores/uiStore"
import { AnimatedDots } from "./AnimatedDots"

interface EnrichUploadZoneProps {
  projectSlug: string
  depType: string
  depName?: string
}

export function EnrichUploadZone({ projectSlug, depType, depName }: EnrichUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const enrichMutation = useEnrichDependency(projectSlug)
  const enrichingDepTypes = useUIStore((s) => s.enrichingDepTypes)
  const isEnriching = enrichingDepTypes.includes(depType)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      enrichMutation.mutate({ depType, file, depName })
      e.target.value = ""  // reset for re-upload
    }
  }

  return (
    <>
      <input ref={inputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
      {isEnriching ? (
        <AnimatedDots className="text-xs px-2" />
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={() => inputRef.current?.click()}
          disabled={enrichMutation.isPending}
        >
          + PDF
        </Button>
      )}
    </>
  )
}
