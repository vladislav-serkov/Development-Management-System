import { useState } from "react"
import { useUIStore } from "@/stores/uiStore"
import { useDocument, useRenameDocument } from "@/hooks/useDocuments"
import { useExtractionSSE } from "@/hooks/useExtraction"
import { Sidebar } from "@/components/layout/Sidebar"
import { ContentArea } from "@/components/layout/ContentArea"

export default function ProjectPage() {
  const documentId = useUIStore((s) => s.selectedDocumentId)
  const { data: document, isLoading } = useDocument(documentId)

  const isExtracting = document?.status === "processing" || document?.status === "extracting"
  useExtractionSSE(documentId, isExtracting ?? false)

  const [isEditingName, setIsEditingName] = useState(false)
  const [editedName, setEditedName] = useState("")
  const renameMutation = useRenameDocument(documentId!)

  const handleStartEdit = () => {
    setEditedName(document?.filename.replace(/\.pdf$/i, "") ?? "")
    setIsEditingName(true)
  }

  const handleSaveName = () => {
    if (editedName.trim()) {
      renameMutation.mutate(editedName.trim(), {
        onSuccess: () => setIsEditingName(false),
      })
    }
  }

  const handleCancelEdit = () => setIsEditingName(false)

  if (isLoading || !document) {
    return <div className="p-8 text-sm text-muted-foreground">Loading...</div>
  }

  return (
    <div className="flex h-screen">
      <Sidebar document={document} />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Editable project name header */}
        <header className="px-6 py-4 border-b flex items-center gap-2 shrink-0">
          {isEditingName ? (
            <>
              <input
                className="text-xl font-semibold bg-transparent border-b border-primary outline-none min-w-0 flex-1"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName()
                  if (e.key === "Escape") handleCancelEdit()
                }}
                autoFocus
              />
              <button
                onClick={handleSaveName}
                className="text-sm text-primary hover:underline shrink-0"
                disabled={renameMutation.isPending}
              >
                {renameMutation.isPending ? "Saving..." : "Save"}
              </button>
              <button
                onClick={handleCancelEdit}
                className="text-sm text-muted-foreground hover:underline shrink-0"
              >
                Cancel
              </button>
            </>
          ) : (
            <h1
              className="text-xl font-semibold cursor-pointer hover:text-primary transition-colors"
              onClick={handleStartEdit}
              title="Click to edit project name"
            >
              {document.filename.replace(/\.pdf$/i, "")}
            </h1>
          )}
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <ContentArea document={document} />
        </main>
      </div>
    </div>
  )
}
