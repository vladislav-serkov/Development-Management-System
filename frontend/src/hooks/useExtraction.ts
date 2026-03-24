import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { ProgressEvent } from "@/types/api"

export function useExtractionSSE(documentId: number | null, enabled: boolean) {
  const qc = useQueryClient()

  useEffect(() => {
    if (!enabled || documentId === null) return

    const es = new EventSource(`/api/documents/${documentId}/progress`)

    es.onmessage = (e) => {
      const event: ProgressEvent = JSON.parse(e.data)
      qc.invalidateQueries({ queryKey: ["documents", documentId] })
      qc.invalidateQueries({ queryKey: ["documents"] })
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
  }, [documentId, enabled, qc])
}
