import { useRef, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowUpRight, DownloadCloud, FileText, FolderKanban, FolderOpen, MoreVertical, Sparkles, Workflow } from "lucide-react"
import {
  useProjects,
  useCreateProject,
  useImportProject,
  useLinkProject,
  useImportContext,
  useDeleteProject,
} from "@/hooks/useDocuments"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { projectPath, rulesPath } from "@/lib/routes"
import { isDesktop } from "@/lib/platform"
import type { ProjectResponse } from "@/types/api"

export default function HomePage() {
  const { data: projects, isLoading, error } = useProjects()
  const createMutation = useCreateProject()
  const importMutation = useImportProject()
  const linkMutation = useLinkProject()
  const importContextMutation = useImportContext()
  const deleteMutation = useDeleteProject()
  const navigate = useNavigate()
  const desktop = isDesktop()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [importError, setImportError] = useState<string | null>(null)
  const [linkError, setLinkError] = useState<string | null>(null)
  const [importContextError, setImportContextError] = useState<string | null>(null)
  const [importSummary, setImportSummary] = useState<{ slug: string; adapted: number; warnings: string[] } | null>(null)
  const [projectToRemove, setProjectToRemove] = useState<ProjectResponse | null>(null)
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

  const handleLinkDirectory = async () => {
    setLinkError(null)
    try {
      const { open } = await import("@tauri-apps/plugin-dialog")
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Выберите директорию проекта",
      })
      if (!selected || typeof selected !== "string") return
      linkMutation.mutate(selected, {
        onSuccess: (project) => {
          setDialogOpen(false)
          navigate(projectPath(project.slug))
        },
        onError: (err) => {
          setLinkError(err instanceof Error ? err.message : "Не удалось подключить директорию")
        },
      })
    } catch (err) {
      setLinkError(err instanceof Error ? err.message : "Не удалось открыть диалог выбора папки")
    }
  }

  const handleImportContextDirectory = async () => {
    setImportContextError(null)
    try {
      const { open } = await import("@tauri-apps/plugin-dialog")
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Выберите директорию с .context (сгенерирован DMS)",
      })
      if (!selected || typeof selected !== "string") return
      importContextMutation.mutate(selected, {
        onSuccess: (result) => {
          setDialogOpen(false)
          if (result.warnings.length > 0) {
            setImportSummary({
              slug: result.project.slug,
              adapted: result.adapted_features,
              warnings: result.warnings,
            })
          } else {
            navigate(projectPath(result.project.slug))
          }
        },
        onError: (err) => {
          setImportContextError(err instanceof Error ? err.message : "Не удалось импортировать .context")
        },
      })
    } catch (err) {
      setImportContextError(err instanceof Error ? err.message : "Не удалось открыть диалог выбора папки")
    }
  }

  const handleRemoveProject = (removeFiles: boolean) => {
    if (!projectToRemove) return
    deleteMutation.mutate(
      { slug: projectToRemove.slug, removeFiles },
      {
        onSuccess: () => setProjectToRemove(null),
      },
    )
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
              if (!open) {
                setImportError(null)
                setLinkError(null)
                setImportContextError(null)
              }
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

                {desktop ? (
                  <>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={handleLinkDirectory}
                      disabled={linkMutation.isPending}
                    >
                      <FolderOpen className="mr-2 h-4 w-4" />
                      {linkMutation.isPending ? "Подключение..." : "Подключить директорию"}
                    </Button>
                    <p className="text-xs text-muted-foreground">
                      Папка <code>.context</code> будет создана внутри выбранной директории.
                      Добавьте её в git, чтобы делиться контекстом с командой.
                    </p>
                    {linkError && (
                      <p className="text-xs text-destructive">{linkError}</p>
                    )}
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={handleImportContextDirectory}
                      disabled={importContextMutation.isPending}
                    >
                      <DownloadCloud className="mr-2 h-4 w-4" />
                      {importContextMutation.isPending ? "Импорт..." : "Импортировать .context (от DMS)"}
                    </Button>
                    <p className="text-xs text-muted-foreground">
                      Подключит существующую <code>.context</code>, собранную плагином DMS,
                      и мигрирует feature.json в канонический формат.
                    </p>
                    {importContextError && (
                      <p className="text-xs text-destructive">{importContextError}</p>
                    )}
                  </>
                ) : (
                  <>
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
                  </>
                )}
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
          {projects.map((project) => {
            const unavailable = project.available === false
            return (
              <Card
                key={project.slug}
                className={`relative border border-border/70 transition-all ${
                  unavailable
                    ? "opacity-70"
                    : "cursor-pointer hover:-translate-y-0.5 hover:shadow-md"
                }`}
                onClick={() => {
                  if (!unavailable) navigate(projectPath(project.slug))
                }}
              >
                <button
                  type="button"
                  aria-label="Действия с проектом"
                  className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground hover:bg-muted"
                  onClick={(e) => {
                    e.stopPropagation()
                    setProjectToRemove(project)
                  }}
                >
                  <MoreVertical className="h-4 w-4" />
                </button>
                <CardHeader className="gap-3">
                  <div className="flex items-start justify-between gap-3 pr-6">
                    <div className="min-w-0">
                      <CardTitle className="truncate">{project.name}</CardTitle>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Создан {project.created_at ? new Date(project.created_at).toLocaleDateString() : "—"}
                      </p>
                      {project.is_linked && project.external_path && (
                        <p className="mt-1 truncate text-xs text-muted-foreground" title={project.external_path}>
                          <FolderOpen className="mr-1 inline h-3 w-3" />
                          {project.external_path}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {unavailable ? (
                        <Badge variant="destructive" className="capitalize">недоступен</Badge>
                      ) : (
                        <Badge variant={project.status === "done" ? "secondary" : "outline"} className="capitalize">
                          {project.status}
                        </Badge>
                      )}
                      {project.is_linked && <Badge variant="outline" className="text-[10px]">linked</Badge>}
                    </div>
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
                    <span className="text-muted-foreground">
                      {unavailable ? "Папка .context недоступна" : "Открыть рабочее пространство"}
                    </span>
                    {!unavailable && <ArrowUpRight className="h-4 w-4 text-muted-foreground" />}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <Dialog
        open={importSummary !== null}
        onOpenChange={(open) => {
          if (!open) setImportSummary(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Импорт .context завершён</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2 text-sm">
            <p>
              Мигрировано фич: <span className="font-medium">{importSummary?.adapted ?? 0}</span>.
              Получено <span className="font-medium">{importSummary?.warnings.length ?? 0}</span> предупреждений от адаптера.
            </p>
            {importSummary && importSummary.warnings.length > 0 && (
              <div className="max-h-72 overflow-auto rounded-md border bg-muted/30 p-3">
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {importSummary.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <Button
              className="w-full"
              onClick={() => {
                const slug = importSummary?.slug
                setImportSummary(null)
                if (slug) navigate(projectPath(slug))
              }}
            >
              Открыть проект
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={projectToRemove !== null}
        onOpenChange={(open) => {
          if (!open) setProjectToRemove(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {projectToRemove?.is_linked ? "Отвязать или удалить проект" : "Удалить проект"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-sm text-muted-foreground">
              Проект <span className="font-medium text-foreground">{projectToRemove?.name}</span>
              {projectToRemove?.is_linked && projectToRemove?.external_path && (
                <>
                  {" "}привязан к <code className="text-xs">{projectToRemove.external_path}</code>.
                </>
              )}
            </p>
            {projectToRemove?.is_linked ? (
              <>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => handleRemoveProject(false)}
                  disabled={deleteMutation.isPending}
                >
                  Отвязать (папка <code className="mx-1">.context</code> останется на диске)
                </Button>
                <Button
                  variant="destructive"
                  className="w-full"
                  onClick={() => handleRemoveProject(true)}
                  disabled={deleteMutation.isPending}
                >
                  Удалить навсегда (вместе с папкой <code className="mx-1">.context</code>)
                </Button>
              </>
            ) : (
              <Button
                variant="destructive"
                className="w-full"
                onClick={() => handleRemoveProject(true)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? "Удаление..." : "Удалить проект"}
              </Button>
            )}
            <Button
              variant="ghost"
              className="w-full"
              onClick={() => setProjectToRemove(null)}
              disabled={deleteMutation.isPending}
            >
              Отмена
            </Button>
          </div>
        </DialogContent>
      </Dialog>
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
