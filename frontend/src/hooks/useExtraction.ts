import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { ProgressEvent } from "@/types/api"

export function useExtractionSSE(
  docSlug: string | null,
  projectSlug: string | null,
  enabled: boolean
) {
  const qc = useQueryClient()

  useEffect(() => {
    if (!enabled || docSlug === null || projectSlug === null) return

    const es = new EventSource(`/api/documents/${docSlug}/progress?project_slug=${projectSlug}`)

    es.onmessage = (e) => {
      const event: ProgressEvent = JSON.parse(e.data)
      qc.invalidateQueries({ queryKey: ["documents", docSlug] })
      qc.invalidateQueries({ queryKey: ["documents"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
      if (event.type === "done" || event.type === "error") {
        es.close()
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [docSlug, projectSlug, enabled, qc])
}
