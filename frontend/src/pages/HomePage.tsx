import { useRef, useState } from "react"
import { useProjects, useCreateProject, useImportProject } from "@/hooks/useDocuments"
import { useUIStore } from "@/stores/uiStore"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"

export default function HomePage() {
  const { data: projects, isLoading, error } = useProjects()
  const createMutation = useCreateProject()
  const importMutation = useImportProject()
  const goToProject = useUIStore((s) => s.goToProject)
  const goToRules = useUIStore((s) => s.goToRules)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [importError, setImportError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCreate = () => {
    if (newName.trim()) {
      createMutation.mutate(newName.trim(), {
        onSuccess: (project) => {
          setDialogOpen(false)
          setNewName("")
          goToProject(project.slug)
        },
      })
    }
  }

  const handleImportClick = () => {
    setImportError(null)
    fileInputRef.current?.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    // Reset so selecting the same file again triggers onChange
    e.target.value = ""
    importMutation.mutate(file, {
      onSuccess: (project) => {
        setDialogOpen(false)
        goToProject(project.slug)
      },
      onError: (err) => {
        setImportError(err instanceof Error ? err.message : "Import failed")
      },
    })
  }

  return (
    <div className="container mx-auto py-8 px-4">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Extract Agent</h1>
          <p className="text-muted-foreground mt-1">
            Extract structured context from PDF specs for coding agents
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={goToRules}>Rules</Button>
        <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setImportError(null) }}>
          <DialogTrigger asChild>
            <Button>+ New Project</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Project</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <Input
                placeholder="Project name (e.g. pay-later-adapter)"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                autoFocus
              />
              <Button onClick={handleCreate} disabled={!newName.trim() || createMutation.isPending} className="w-full">
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">or</span>
                </div>
              </div>

              <Button
                variant="outline"
                className="w-full"
                onClick={handleImportClick}
                disabled={importMutation.isPending}
              >
                {importMutation.isPending ? "Importing..." : "Import from .zip"}
              </Button>

              {importError && (
                <p className="text-xs text-destructive">{importError}</p>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
          </DialogContent>
        </Dialog>
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-32 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">Failed to load projects.</p>
      )}

      {!isLoading && !error && projects && projects.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-16">
          No projects yet. Create one to get started.
        </p>
      )}

      {!isLoading && projects && projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <Card
              key={project.slug}
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => goToProject(project.slug)}
            >
              <CardHeader>
                <CardTitle className="truncate">{project.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-xs">
                    {project.feature_count} фич
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {project.document_count} PDF
                  </Badge>
                  <span>{new Date(project.created_at).toLocaleDateString()}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
