import { useState, useEffect, useRef } from "react"
import { useUIStore } from "@/stores/uiStore"
import { useProject, useRenameProject, useUploadDocument, useProjectFeatures, useSaveFeature, useDeleteFeature } from "@/hooks/useDocuments"
import { useProjectDependencies, useCreateDependency, useDeleteDependency } from "@/hooks/useDependencies"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { UploadZone } from "@/components/project/UploadZone"
import { ExportDialog } from "@/components/project/ExportDialog"
import { StructuredLogicView } from "@/components/feature/StructuredLogicView"
import { GapsView } from "@/components/feature/GapsView"
import { TestCasesView } from "@/components/feature/TestCasesView"
import { BugsView } from "@/components/feature/BugsView"
import { DependencyDetail } from "@/components/dependency/DependencyDetail"
import { EnrichUploadZone } from "@/components/dependency/EnrichUploadZone"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { Database, Globe, HardDrive, MessageSquare, ChevronRight, Layers, Trash2, Plus, Pencil, Check, X, FileJson2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FeatureResponse, FeatureStatus, ProjectDependency, DependencyStatus, DependencyType, CreateDependencyRequest, StructuredBusinessLogic } from "@/types/api"

export default function ProjectPage() {
  const projectSlug = useUIStore((s) => s.selectedProjectSlug)
  const goHome = useUIStore((s) => s.goHome)
  const goToRules = useUIStore((s) => s.goToRules)
  const { selectedFeatureName, selectedDependencyName, activeSidebarItem, setSelectedFeature, setSelectedDependency, setActiveSidebarItem, sidebarWidth, setSidebarWidth } = useUIStore()

  const isDragging = useRef(false)

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isDragging.current) return
      setSidebarWidth(e.clientX)
    }
    function onMouseUp() {
      isDragging.current = false
    }
    document.addEventListener("mousemove", onMouseMove)
    document.addEventListener("mouseup", onMouseUp)
    return () => {
      document.removeEventListener("mousemove", onMouseMove)
      document.removeEventListener("mouseup", onMouseUp)
    }
  }, [setSidebarWidth])

  const { data: project, isLoading: projectLoading } = useProject(projectSlug)
  const { data: features } = useProjectFeatures(projectSlug)
  const { data: dependencies } = useProjectDependencies(projectSlug)
  const uploadMutation = useUploadDocument(projectSlug!)

  // Active feature tab (logic | gaps | tests)
  const [activeFeatureTab, setActiveFeatureTab] = useState<string>("logic")

  // Reset to logic tab when selected feature changes
  useEffect(() => {
    setActiveFeatureTab("logic")
  }, [selectedFeatureName])

  // Editable project name
  const [isEditingName, setIsEditingName] = useState(false)
  const [editedName, setEditedName] = useState("")
  const renameMutation = useRenameProject(projectSlug!)

  const deleteFeatureMutation = useDeleteFeature(projectSlug ?? "")

  const handleStartEdit = () => {
    setEditedName(project?.name ?? "")
    setIsEditingName(true)
  }

  const handleSaveName = () => {
    if (editedName.trim()) {
      renameMutation.mutate(editedName.trim(), {
        onSuccess: () => setIsEditingName(false),
      })
    }
  }

  if (projectLoading || !project) {
    return <div className="p-8 text-sm text-muted-foreground">Loading...</div>
  }

  function handleFeatureClick(featureName: string) {
    setSelectedFeature(featureName)
    setActiveSidebarItem(`feature-${featureName}`)
  }

  function handleDepClick(depName: string) {
    setSelectedDependency(depName)
    setActiveSidebarItem(`dep-${depName}`)
  }

  const isFeatureActive = (featureName: string) => selectedFeatureName === featureName
  const isDepActive = (depName: string) => selectedDependencyName === depName

  // Find the selected feature object
  const selectedFeature = features?.find((f) => f.name === selectedFeatureName) ?? null

  // Group dependencies by type
  const depsByType = {
    db_table: dependencies?.filter(d => d.dep_type === "db_table") ?? [],
    external_api: dependencies?.filter(d => d.dep_type === "external_api") ?? [],
    cache: dependencies?.filter(d => d.dep_type === "cache") ?? [],
    kafka_topic: dependencies?.filter(d => d.dep_type === "kafka_topic") ?? [],
  }

  // Find the selected dependency
  const selectedDep = dependencies?.find(d => d.name === selectedDependencyName) ?? null

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="relative border-r bg-muted/30 h-screen flex flex-col shrink-0" style={{ width: sidebarWidth }}>
        <div className="p-3 border-b">
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" className="justify-start text-xs" onClick={goHome}>
              &larr; Все проекты
            </Button>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground" onClick={goToRules}>
              Rules
            </Button>
          </div>
          <div className="mt-2 px-1">
            {isEditingName ? (
              <div className="flex items-center gap-1">
                <input
                  className="text-sm font-medium bg-transparent border-b border-primary outline-none min-w-0 flex-1"
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName()
                    if (e.key === "Escape") setIsEditingName(false)
                  }}
                  autoFocus
                />
              </div>
            ) : (
              <p
                className="text-sm font-medium truncate cursor-pointer hover:text-primary transition-colors"
                onClick={handleStartEdit}
                title="Click to edit"
              >
                {project.name}
              </p>
            )}
          </div>
        </div>

        {/* Upload zone (compact) */}
        <div className="p-3 border-b">
          <UploadZone onUpload={(file) => uploadMutation.mutate(file)} isUploading={uploadMutation.isPending} />
        </div>

        {/* features/ tree */}
        <ScrollArea className="flex-1 min-h-0 p-3">
          <div className="space-y-4">
            {/* Features */}
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1 px-1">
                <Layers className="h-3.5 w-3.5" />
                Features {features && features.length > 0 && <span className="text-[10px] font-normal">({features.length})</span>}
              </div>
              <div className="space-y-0.5">
                {features?.map((feature) => (
                  <div key={feature.name}>
                    <div className="group relative flex items-center">
                      <button
                        onClick={() => handleFeatureClick(feature.name)}
                        title={feature.name}
                        className={cn(
                          "flex-1 text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors",
                          isFeatureActive(feature.name) ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                        )}
                      >
                        <FeatureStatusDot status={feature.status} />
                        <MethodBadge method={feature.method} featureType={feature.type} />
                        <span className="truncate flex-1">{feature.name}</span>
                        <ChevronRight className={cn("h-3 w-3 shrink-0 text-muted-foreground transition-transform", isFeatureActive(feature.name) && "rotate-90")} />
                      </button>
                      <SidebarTrashButton
                        onDelete={() => {
                          if (window.confirm(`Удалить фичу "${feature.name}" и все связанные gaps/test-cases/bugs?`)) {
                            deleteFeatureMutation.mutate(feature.name)
                          }
                        }}
                      />
                    </div>
                    {isFeatureActive(feature.name) && (
                      <div>
                        <button
                          onClick={() => { handleFeatureClick(feature.name); setActiveFeatureTab("logic") }}
                          className={cn(
                            "w-full text-left flex items-center gap-2 px-2 py-1 rounded-md text-xs transition-colors ml-4",
                            isFeatureActive(feature.name) && activeFeatureTab === "logic" ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                          )}
                        >
                          <span>Логика</span>
                        </button>
                        <button
                          onClick={() => { handleFeatureClick(feature.name); setActiveFeatureTab("gaps") }}
                          className={cn(
                            "w-full text-left flex items-center gap-2 px-2 py-1 rounded-md text-xs transition-colors ml-4",
                            isFeatureActive(feature.name) && activeFeatureTab === "gaps" ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                          )}
                        >
                          <span className="flex-1">Пробелы</span>
                          {feature.gaps_status === "running" && <AnimatedDots className="text-xs shrink-0" />}
                        </button>
                        <button
                          onClick={() => { handleFeatureClick(feature.name); setActiveFeatureTab("tests") }}
                          className={cn(
                            "w-full text-left flex items-center gap-2 px-2 py-1 rounded-md text-xs transition-colors ml-4",
                            isFeatureActive(feature.name) && activeFeatureTab === "tests" ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                          )}
                        >
                          <span className="flex-1">Тест-кейсы</span>
                          {feature.test_cases_status === "running" && <AnimatedDots className="text-xs shrink-0" />}
                        </button>
                        <button
                          onClick={() => { handleFeatureClick(feature.name); setActiveFeatureTab("bugs") }}
                          className={cn(
                            "w-full text-left flex items-center gap-2 px-2 py-1 rounded-md text-xs transition-colors ml-4",
                            isFeatureActive(feature.name) && activeFeatureTab === "bugs" ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                          )}
                        >
                          <span className="flex-1">Баги</span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {(!features || features.length === 0) && (
                  <p className="text-xs text-muted-foreground px-2">Загрузите PDF для извлечения фич</p>
                )}
              </div>
            </div>

            {/* Dependency sections */}
            <DepSection
              label="DB"
              icon={<Database className="h-3.5 w-3.5" />}
              deps={depsByType.db_table}
              depType="db_table"
              projectSlug={projectSlug!}
              isDepActive={isDepActive}
              onDepClick={handleDepClick}
            />
            <DepSection
              label="API"
              icon={<Globe className="h-3.5 w-3.5" />}
              deps={depsByType.external_api}
              depType="external_api"
              projectSlug={projectSlug!}
              isDepActive={isDepActive}
              onDepClick={handleDepClick}
            />
            <DepSection
              label="Cache"
              icon={<HardDrive className="h-3.5 w-3.5" />}
              deps={depsByType.cache}
              depType="cache"
              projectSlug={projectSlug!}
              isDepActive={isDepActive}
              onDepClick={handleDepClick}
            />
            <DepSection
              label="Topics"
              icon={<MessageSquare className="h-3.5 w-3.5" />}
              deps={depsByType.kafka_topic}
              depType="kafka_topic"
              projectSlug={projectSlug!}
              isDepActive={isDepActive}
              onDepClick={handleDepClick}
            />

            {/* Swagger — coming soon */}
            <div className="flex items-center gap-2 px-1">
              <FileJson2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Swagger
              </span>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 leading-4 text-muted-foreground">
                coming soon
              </Badge>
            </div>

          </div>
        </ScrollArea>

        {/* Export */}
        <div className="p-3 border-t">
          <ExportDialog projectSlug={projectSlug!} />
        </div>

        {/* Drag handle */}
        <div
          className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-border transition-colors"
          onMouseDown={() => { isDragging.current = true }}
        />
      </aside>

      {/* Content */}
      <main className="flex-1 min-h-0 overflow-y-auto p-6">
        <ProjectContentArea
          key={activeSidebarItem ?? "none"}
          projectSlug={projectSlug!}
          selectedFeature={selectedFeature}
          selectedDep={selectedDep}
          activeSidebarItem={activeSidebarItem}
          projectDependencies={dependencies}
          onDepClick={handleDepClick}
          activeFeatureTab={activeFeatureTab}
          onFeatureTabChange={setActiveFeatureTab}
        />
      </main>
    </div>
  )
}

function MethodBadge({ method, featureType, large }: { method: string | null; featureType: string; large?: boolean }) {
  const resolved = method ?? (featureType === "kafka_consumer" ? "CONSUMER" : featureType === "rest_endpoint" ? "API" : null)
  if (!resolved) return null

  const colorMap: Record<string, string> = {
    GET: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    POST: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    PUT: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    DELETE: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    PATCH: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    CONSUMER: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    API: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400",
  }
  const colorClass = colorMap[resolved] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400"
  const sizeClass = large ? "text-xs" : "text-[10px]"
  return (
    <span className={cn(`font-semibold font-mono px-1.5 py-0.5 rounded shrink-0 ${sizeClass}`, colorClass)}>
      {resolved}
    </span>
  )
}

function FeatureStatusDot({ status }: { status: FeatureStatus }) {
  const colors: Record<FeatureStatus, string> = {
    done: "bg-green-500",
    extracting: "bg-amber-400",
    error: "bg-destructive",
    detected: "bg-muted-foreground/40",
  }
  return <span className={cn("inline-block h-2 w-2 rounded-full shrink-0", colors[status] ?? "bg-muted-foreground/40")} />
}


// Inline content area that works with project-level data
function ProjectContentArea({
  projectSlug,
  selectedFeature,
  selectedDep,
  activeSidebarItem,
  projectDependencies,
  onDepClick,
  activeFeatureTab,
  onFeatureTabChange,
}: {
  projectSlug: string
  selectedFeature: FeatureResponse | null
  selectedDep: ProjectDependency | null
  activeSidebarItem: string | null
  projectDependencies?: ProjectDependency[]
  onDepClick?: (depName: string) => void
  activeFeatureTab: string
  onFeatureTabChange: (tab: string) => void
}) {
  const { setSelectedFeature, setActiveSidebarItem } = useUIStore()
  const saveFeatureMutation = useSaveFeature(projectSlug)
  const deleteFeatureMutation = useDeleteFeature(projectSlug)

  // === Global edit mode state ===
  const [isEditing, setIsEditing] = useState(false)
  const [editedLogic, setEditedLogic] = useState<StructuredBusinessLogic | null>(null)
  // Header fields in edit mode
  const [editName, setEditName] = useState("")
  const [editMethod, setEditMethod] = useState("")
  const [editEndpoint, setEditEndpoint] = useState("")
  const [editSummary, setEditSummary] = useState("")

  // Reset edit state when selected feature changes
  useEffect(() => {
    setIsEditing(false)
    setEditedLogic(null)
  }, [selectedFeature?.name])

  const startEdit = () => {
    if (!selectedFeature) return
    setEditName(selectedFeature.name)
    setEditMethod(selectedFeature.method ?? "")
    setEditEndpoint(selectedFeature.endpoint ?? "")
    setEditSummary(selectedFeature.summary ?? "")
    setEditedLogic(structuredClone(selectedFeature.structured_logic ?? {}))
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setIsEditing(false)
    setEditedLogic(null)
  }

  const handleSave = () => {
    if (!selectedFeature) { console.error("handleSave: selectedFeature is null"); return }
    const patch: Record<string, unknown> = {}
    if (editName.trim() && editName.trim() !== selectedFeature.name) patch.name = editName.trim()
    if (editMethod && editMethod !== selectedFeature.method) patch.method = editMethod
    if (editEndpoint !== (selectedFeature.endpoint ?? "")) patch.endpoint = editEndpoint
    if (editSummary !== (selectedFeature.summary ?? "")) patch.summary = editSummary
    if (editedLogic) patch.structured_logic_json = editedLogic as Record<string, unknown>

    const newName = (patch.name as string | undefined) ?? selectedFeature.name

    console.log("handleSave: featureName=", selectedFeature.name, "patch keys=", Object.keys(patch), "patch=", patch)

    saveFeatureMutation.mutate(
      { featureName: selectedFeature.name, patch },
      {
        onSuccess: () => {
          console.log("handleSave: success!")
          setIsEditing(false)
          setEditedLogic(null)
          if (patch.name) {
            setSelectedFeature(newName)
            setActiveSidebarItem(`feature-${newName}`)
          }
        },
        onError: (err) => {
          console.error("handleSave: error!", err)
        },
      }
    )
  }

  // Dependency view branch
  if (activeSidebarItem?.startsWith("dep-") && selectedDep) {
    return <DependencyDetail dep={selectedDep} projectSlug={projectSlug} />
  }

  if (selectedFeature) {
    // Logic source: when editing use editedLogic, otherwise use original
    const displayLogic = isEditing ? (editedLogic ?? selectedFeature.structured_logic) : selectedFeature.structured_logic

    return (
      <div className="space-y-4">
        {/* Sticky save/cancel bar when editing */}
        {isEditing && (
          <div className="sticky top-0 z-10 bg-background border-b p-2 flex items-center gap-2 -mx-6 px-6 shadow-sm">
            <span className="text-sm font-medium text-muted-foreground">Режим редактирования</span>
            <div className="flex items-center gap-2 ml-auto">
              <Button
                size="sm"
                variant="outline"
                onClick={cancelEdit}
                className="flex items-center gap-1"
              >
                <X className="h-3.5 w-3.5" />
                Отмена
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saveFeatureMutation.isPending}
                className="flex items-center gap-1"
              >
                <Check className="h-3.5 w-3.5" />
                {saveFeatureMutation.isPending ? "Сохранение..." : "Сохранить"}
              </Button>
            </div>
          </div>
        )}

        {/* Feature header — persists across all tabs */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Feature name */}
            {isEditing ? (
              <input
                className="text-xl font-semibold bg-transparent border-b border-primary outline-none min-w-0 flex-1"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            ) : (
              <h2 className="text-xl font-semibold">
                {selectedFeature.name}
              </h2>
            )}

            {/* Method badge */}
            {isEditing ? (
              <select
                value={editMethod}
                onChange={(e) => setEditMethod(e.target.value)}
                className="text-xs font-semibold font-mono px-1.5 py-0.5 rounded bg-transparent border border-border cursor-pointer"
              >
                {["GET", "POST", "PUT", "DELETE", "PATCH", "CONSUMER"].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            ) : (
              <select
                value={selectedFeature.method ?? ""}
                onChange={(e) => saveFeatureMutation.mutate({ featureName: selectedFeature.name, patch: { method: e.target.value } })}
                className="text-xs font-semibold font-mono px-1.5 py-0.5 rounded bg-transparent border border-transparent hover:border-border cursor-pointer"
                title="Click to change method"
              >
                {["GET", "POST", "PUT", "DELETE", "PATCH", "CONSUMER"].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}

            <Badge variant="outline" className="text-xs">
              {Math.round(selectedFeature.confidence * 100)}%
            </Badge>

            <div className="ml-auto flex items-center gap-1">
              {!isEditing && (
                <button
                  className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  title="Edit feature"
                  onClick={startEdit}
                >
                  <Pencil className="h-4 w-4" />
                </button>
              )}
              <button
                className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="Delete feature"
                onClick={() => {
                  if (window.confirm(`Удалить фичу "${selectedFeature.name}"?`)) {
                    deleteFeatureMutation.mutate(selectedFeature.name)
                  }
                }}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Endpoint */}
          {isEditing ? (
            <input
              className="text-sm text-muted-foreground font-mono bg-transparent border-b border-border outline-none w-full"
              value={editEndpoint}
              placeholder="endpoint (e.g. /api/resource)"
              onChange={(e) => setEditEndpoint(e.target.value)}
            />
          ) : (
            <span className="text-sm text-muted-foreground font-mono block">
              {selectedFeature.endpoint ?? <span className="italic text-muted-foreground/50">Нет endpoint</span>}
            </span>
          )}

          {/* Summary */}
          {isEditing ? (
            <input
              className="text-sm text-muted-foreground bg-transparent border-b border-border outline-none w-full"
              value={editSummary}
              placeholder="summary"
              onChange={(e) => setEditSummary(e.target.value)}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {selectedFeature.summary ?? <span className="italic text-muted-foreground/50">Нет summary</span>}
            </p>
          )}
        </div>

        {/* Tabbed content */}
        <Tabs value={activeFeatureTab} onValueChange={onFeatureTabChange}>
          <TabsList>
            <TabsTrigger value="logic">Логика</TabsTrigger>
            <TabsTrigger value="gaps">
              Пробелы{selectedFeature.gap_count ? ` (${selectedFeature.gap_count})` : ""}
            </TabsTrigger>
            <TabsTrigger value="tests">
              Тест-кейсы{selectedFeature.test_case_count ? ` (${selectedFeature.test_case_count})` : ""}
            </TabsTrigger>
            <TabsTrigger value="bugs">
              Баги{selectedFeature.bug_count ? ` (${selectedFeature.bug_count})` : ""}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="logic">
            {displayLogic
              ? (
                <StructuredLogicView
                  logic={displayLogic}
                  featureType={selectedFeature.type}
                  projectDependencies={projectDependencies}
                  onDepClick={onDepClick}
                  isEditing={isEditing}
                  onChange={isEditing ? setEditedLogic : undefined}
                />
              )
              : <p className="text-sm text-muted-foreground">Нет structured logic.</p>
            }
          </TabsContent>
          <TabsContent value="gaps">
            <GapsView
              projectSlug={projectSlug}
              featureName={selectedFeature.name}
              usedDependencies={selectedFeature.structured_logic?.used_dependencies}
              projectDependencies={projectDependencies}
            />
          </TabsContent>
          <TabsContent value="tests">
            <TestCasesView
              projectSlug={projectSlug}
              featureName={selectedFeature.name}
              onBugCreated={() => onFeatureTabChange("bugs")}
            />
          </TabsContent>
          <TabsContent value="bugs">
            <BugsView projectSlug={projectSlug} featureName={selectedFeature.name} />
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-muted-foreground">Выберите фичу или зависимость в боковом меню.</p>
    </div>
  )
}

// Dependency section in sidebar
function DepSection({
  label,
  icon,
  deps,
  depType,
  projectSlug,
  isDepActive,
  onDepClick,
}: {
  label: string
  icon: React.ReactNode
  deps: ProjectDependency[]
  depType: string
  projectSlug: string
  isDepActive: (name: string) => boolean
  onDepClick: (name: string) => void
}) {
  const enrichingDepTypes = useUIStore((s) => s.enrichingDepTypes)
  const isEnriching = enrichingDepTypes.includes(depType)
  const deleteDep = useDeleteDependency(projectSlug)
  const createDep = useCreateDependency(projectSlug)

  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newDepName, setNewDepName] = useState("")
  const [newDepDesc, setNewDepDesc] = useState("")
  const [newDepMethod, setNewDepMethod] = useState("GET")
  const [newDepService, setNewDepService] = useState("")

  const handleCreate = () => {
    if (!newDepName.trim()) return
    const req: CreateDependencyRequest = {
      dep_type: depType as DependencyType,
      name: newDepName.trim(),
      description: newDepDesc.trim(),
      ...(depType === "external_api" && { method: newDepMethod, service_name: newDepService.trim() }),
    }
    createDep.mutate(req, {
      onSuccess: () => {
        setShowCreateForm(false)
        setNewDepName("")
        setNewDepDesc("")
        setNewDepMethod("GET")
        setNewDepService("")
      },
    })
  }

  return (
    <Collapsible>
      <div className="flex items-center justify-between mb-1 px-1">
        <CollapsibleTrigger className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors">
          {icon}
          {label} {deps.length > 0 && <span className="text-[10px] font-normal">({deps.length})</span>}
        </CollapsibleTrigger>
        <div className="flex items-center gap-1">
          {(depType === "db_table" || depType === "cache") && (
            <EnrichUploadZone projectSlug={projectSlug} depType={depType} />
          )}
          <button
            className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            title={`Добавить ${label}`}
            onClick={() => setShowCreateForm((v) => !v)}
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <CollapsibleContent>
        {showCreateForm && (
          <div className="mb-1 p-2 rounded-md border bg-background space-y-1.5 text-xs">
            <input
              className="w-full border-b bg-transparent outline-none pb-0.5 placeholder:text-muted-foreground/60"
              placeholder="Название *"
              value={newDepName}
              onChange={(e) => setNewDepName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); if (e.key === "Escape") setShowCreateForm(false) }}
              autoFocus
            />
            <input
              className="w-full border-b bg-transparent outline-none pb-0.5 placeholder:text-muted-foreground/60"
              placeholder="Описание"
              value={newDepDesc}
              onChange={(e) => setNewDepDesc(e.target.value)}
            />
            {depType === "external_api" && (
              <>
                <select
                  className="w-full border-b bg-transparent outline-none pb-0.5"
                  value={newDepMethod}
                  onChange={(e) => setNewDepMethod(e.target.value)}
                >
                  {["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <input
                  className="w-full border-b bg-transparent outline-none pb-0.5 placeholder:text-muted-foreground/60"
                  placeholder="Service name"
                  value={newDepService}
                  onChange={(e) => setNewDepService(e.target.value)}
                />
              </>
            )}
            <div className="flex gap-1 pt-0.5">
              <button
                className="flex-1 rounded bg-primary text-primary-foreground py-0.5 hover:opacity-90 transition-opacity"
                onClick={handleCreate}
                disabled={createDep.isPending}
              >
                Сохранить
              </button>
              <button
                className="flex-1 rounded border py-0.5 hover:bg-accent transition-colors"
                onClick={() => { setShowCreateForm(false); setNewDepName(""); setNewDepDesc("") }}
              >
                Отмена
              </button>
            </div>
          </div>
        )}
        <div className="space-y-0.5">
          {deps.map((dep) => (
            <div key={dep.name} className="group relative flex items-center">
              <button
                onClick={() => onDepClick(dep.name)}
                title={dep.name}
                className={cn(
                  "flex-1 text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors",
                  isDepActive(dep.name) ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                )}
              >
                <DepStatusDot status={dep.enrichment_status} />
                {dep.dep_type === "external_api" && dep.method && (
                  <MethodBadge method={dep.method} featureType="rest_endpoint" />
                )}
                <span className="truncate">{dep.name}</span>
                {isEnriching && dep.enrichment_status === "stub" && (
                  <AnimatedDots className="text-xs shrink-0" />
                )}
              </button>
              <SidebarTrashButton
                onDelete={() => {
                  if (window.confirm(`Удалить зависимость "${dep.name}"?`)) {
                    deleteDep.mutate({ depName: dep.name, depType: dep.dep_type })
                  }
                }}
              />
            </div>
          ))}
          {deps.length === 0 && !showCreateForm && (
            <p className="text-xs text-muted-foreground px-2">Нет зависимостей</p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// Reusable hover trash icon for sidebar items
function SidebarTrashButton({ onDelete }: { onDelete: () => void }) {
  return (
    <button
      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all shrink-0"
      title="Удалить"
      onClick={(e) => { e.stopPropagation(); onDelete() }}
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  )
}

function DepStatusDot({ status }: { status: DependencyStatus }) {
  const colors: Record<DependencyStatus, string> = {
    enriched: "bg-green-500",
    stub: "bg-muted-foreground/40",
    error: "bg-destructive",
  }
  return <span className={cn("inline-block h-2 w-2 rounded-full shrink-0", colors[status] ?? "bg-muted-foreground/40")} />
}
