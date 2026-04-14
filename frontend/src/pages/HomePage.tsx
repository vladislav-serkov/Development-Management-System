import { useRef, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowUpRight, FileText, FolderKanban, Sparkles, Workflow } from "lucide-react"
import { useProjects, useCreateProject, useImportProject } from "@/hooks/useDocuments"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { projectPath, rulesPath } from "@/lib/routes"

export default function HomePage() {
  const { data: projects, isLoading, error } = useProjects()
  const createMutation = useCreateProject()
  const importMutation = useImportProject()
  const navigate = useNavigate()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [importError, setImportError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCreate = () => {
    if (!newName.trim()) return
    createMutation.mutate(newName.trim(), {
      onSuccess: (project) => {
        setDialogOpen(false)
        setNewName("")
        navigate(projectPath(project.slug))
      },
    })
  }

  const handleImportClick = () => {
    setImportError(null)
    fileInputRef.current?.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ""
    importMutation.mutate(file, {
      onSuccess: (project) => {
        setDialogOpen(false)
        navigate(projectPath(project.slug))
      },
      onError: (err) => {
        setImportError(err instanceof Error ? err.message : "Ошибка импорта")
      },
    })
  }

  const totalProjects = projects?.length ?? 0
  const totalDocuments = projects?.reduce((sum, project) => sum + project.document_count, 0) ?? 0
  const totalFeatures = projects?.reduce((sum, project) => sum + project.feature_count, 0) ?? 0
  const readyProjects = projects?.filter((project) => project.status === "done").length ?? 0

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8 flex items-center justify-between gap-6">
        <div>
          <h1 className="text-3xl font-bold">Development Management System</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            Рабочее пространство для извлечения спецификаций, управления фичами и сборки проектных артефактов.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate(rulesPath())}>Правила</Button>
          <Dialog
            open={dialogOpen}
            onOpenChange={(open) => {
              setDialogOpen(open)
              if (!open) setImportError(null)
            }}
          >
            <DialogTrigger render={<Button />}>+ Новый проект</DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Создать проект</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <Input
                  placeholder="Название проекта, например pay-later-adapter"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  autoFocus
                />
                <Button onClick={handleCreate} disabled={!newName.trim() || createMutation.isPending} className="w-full">
                  {createMutation.isPending ? "Создание..." : "Создать"}
                </Button>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-background px-2 text-muted-foreground">или</span>
                  </div>
                </div>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={handleImportClick}
                  disabled={importMutation.isPending}
                >
                  {importMutation.isPending ? "Импорт..." : "Импортировать из .zip"}
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

      <div className="mb-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={<FolderKanban className="h-4 w-4" />} label="Проекты" value={totalProjects} helper="Всего рабочих пространств" />
        <SummaryCard icon={<FileText className="h-4 w-4" />} label="PDF" value={totalDocuments} helper="Загруженные документы" />
        <SummaryCard icon={<Workflow className="h-4 w-4" />} label="Фичи" value={totalFeatures} helper="Извлеченные сущности" />
        <SummaryCard icon={<Sparkles className="h-4 w-4" />} label="Готово" value={readyProjects} helper="Проекты со статусом done" />
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-40 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">Не удалось загрузить проекты.</p>
      )}

      {!isLoading && !error && projects && projects.length === 0 && (
        <div className="rounded-2xl border border-dashed px-6 py-16 text-center">
          <p className="text-sm text-muted-foreground">
            Пока нет проектов. Создайте новый проект или импортируйте существующий архив.
          </p>
        </div>
      )}

      {!isLoading && projects && projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card
              key={project.slug}
              className="cursor-pointer border border-border/70 transition-all hover:-translate-y-0.5 hover:shadow-md"
              onClick={() => navigate(projectPath(project.slug))}
            >
              <CardHeader className="gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">{project.name}</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Создан {new Date(project.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge variant={project.status === "done" ? "secondary" : "outline"} className="capitalize">
                    {project.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-xs">
                    {project.feature_count} фич
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {project.document_count} PDF
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Открыть рабочее пространство</span>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  icon,
  label,
  value,
  helper,
}: {
  icon: ReactNode
  label: string
  value: number
  helper: string
}) {
  return (
    <Card className="border border-border/70">
      <CardContent className="flex items-start justify-between gap-4 py-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold">{value}</p>
          <p className="mt-1 text-sm text-muted-foreground">{helper}</p>
        </div>
        <div className="rounded-lg bg-muted p-2 text-muted-foreground">
          {icon}
        </div>
      </CardContent>
    </Card>
  )
}
