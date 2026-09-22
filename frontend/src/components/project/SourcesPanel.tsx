import { useState } from "react"
import { FileText, GitCompareArrows, Loader2, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import { SpecDiffDialog } from "./SpecDiffDialog"
import type { DocumentResponse } from "@/types/api"

interface SourcesPanelProps {
  documents: DocumentResponse[] | undefined
  onReimport: (confluenceUrl: string) => void
  isImporting: boolean
  isCheckingUpdates: boolean
}

/** Imported Confluence pages with their spec-version state:
 * current version, "v12 → v15" badge when the page moved ahead,
 * one-click re-import and the diff of the last re-extraction. */
export function SourcesPanel({ documents, onReimport, isImporting, isCheckingUpdates }: SourcesPanelProps) {
  const [diffDoc, setDiffDoc] = useState<DocumentResponse | null>(null)

  const confluenceDocs = documents?.filter((d) => d.confluence_url) ?? []
  if (confluenceDocs.length === 0) return null

  return (
    <div className="space-y-1.5">
      {confluenceDocs.map((doc) => {
        const extracting = doc.status === "processing" || doc.status === "extracting"
        const outdated = !!doc.spec_outdated
        return (
          <div
            key={doc.slug}
            className={cn(
              "group flex items-center gap-2 rounded-lg border px-2 py-1.5 text-xs",
              outdated ? "border-amber-300/70 bg-amber-50/50 dark:border-amber-700/50 dark:bg-amber-950/20" : "border-transparent bg-background/60",
            )}
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <a
                href={doc.confluence_url ?? undefined}
                target="_blank"
                rel="noreferrer"
                title={doc.filename}
                className="block truncate font-medium hover:underline"
              >
                {doc.filename}
              </a>
              <p className="mt-0.5 flex items-center gap-1.5 text-[0.6875rem] text-muted-foreground">
                {extracting ? (
                  <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                    <Loader2 className="h-3 w-3 animate-spin" /> извлечение…
                  </span>
                ) : outdated ? (
                  <span className="font-medium text-amber-700 dark:text-amber-400">
                    спека обновилась: v{doc.confluence_version} → v{doc.latest_confluence_version}
                  </span>
                ) : (
                  <span>
                    v{doc.confluence_version ?? "?"}
                    {isCheckingUpdates ? " · проверка…" : " · актуальна"}
                  </span>
                )}
              </p>
            </div>

            {doc.last_diff && !extracting && (
              <button
                type="button"
                title={doc.last_diff.material ? "Что изменилось при последнем обновлении" : "Последнее обновление: содержательных изменений нет"}
                onClick={() => setDiffDoc(doc)}
                className={cn(
                  "shrink-0 rounded-md p-1 transition-colors hover:bg-accent",
                  doc.last_diff.material ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground/70",
                )}
              >
                <GitCompareArrows className="h-3.5 w-3.5" />
              </button>
            )}

            {doc.confluence_url && !extracting && (
              <button
                type="button"
                title={outdated ? "Переизвлечь по новой версии спеки" : "Переизвлечь страницу"}
                disabled={isImporting}
                onClick={() => onReimport(doc.confluence_url!)}
                className={cn(
                  "shrink-0 rounded-md p-1 transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-50",
                  outdated ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground/70 opacity-0 group-hover:opacity-100",
                )}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", isImporting && "animate-spin")} />
              </button>
            )}
          </div>
        )
      })}

      <SpecDiffDialog doc={diffDoc} onClose={() => setDiffDoc(null)} />
    </div>
  )
}
