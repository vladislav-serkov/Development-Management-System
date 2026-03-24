import { useDocuments, useUploadDocument } from "@/hooks/useDocuments"
import { ProjectCard } from "@/components/project/ProjectCard"
import { UploadZone } from "@/components/project/UploadZone"

export function ProjectGrid() {
  const { data: documents, isLoading, error } = useDocuments()
  const uploadMutation = useUploadDocument()

  return (
    <div className="space-y-6">
      <UploadZone
        onUpload={(file) => uploadMutation.mutate(file)}
        isUploading={uploadMutation.isPending}
      />

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-32 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">
          Failed to load projects. Please try refreshing.
        </p>
      )}

      {!isLoading && !error && documents && documents.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-8">
          No projects yet. Upload a PDF to get started.
        </p>
      )}

      {!isLoading && documents && documents.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {documents.map((doc) => (
            <ProjectCard key={doc.id} document={doc} />
          ))}
        </div>
      )}
    </div>
  )
}
