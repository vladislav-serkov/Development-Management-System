import { useState } from "react"

interface UploadZoneProps {
  onImportConfluence: (url: string) => void
  isImporting: boolean
  importError?: string | null
}

export function UploadZone({ onImportConfluence, isImporting, importError }: UploadZoneProps) {
  const [confluenceUrl, setConfluenceUrl] = useState("")

  const submitConfluence = () => {
    const url = confluenceUrl.trim()
    if (!url || isImporting) return
    onImportConfluence(url)
    setConfluenceUrl("")
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <input
          type="text"
          value={confluenceUrl}
          onChange={(e) => setConfluenceUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submitConfluence() }}
          placeholder="Ссылка на страницу Confluence"
          disabled={isImporting}
          className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-xs outline-none placeholder:text-muted-foreground/60 focus:border-primary disabled:opacity-50"
        />
        <button
          type="button"
          onClick={submitConfluence}
          disabled={isImporting || !confluenceUrl.trim()}
          className="h-8 shrink-0 rounded-md border px-2 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:pointer-events-none disabled:opacity-50"
        >
          {isImporting ? "Импорт..." : "Импорт"}
        </button>
      </div>
      {importError && (
        <p className="px-1 text-xs text-destructive">{importError}</p>
      )}
    </div>
  )
}
