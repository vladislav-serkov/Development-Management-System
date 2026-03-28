import { useState, useEffect, useRef } from "react"
import { Database, Globe, HardDrive, AlertTriangle, type LucideIcon } from "lucide-react"
import { useUIStore } from "@/stores/uiStore"
import { useProject, useRenameProject, useUploadDocument, useProjectFeatures, useProjectRegistry, useProjectGaps, useSaveFeature, useSaveDependencyEntry, useSaveGapEntry } from "@/hooks/useDocuments"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { UploadZone } from "@/components/project/UploadZone"
import { ExportDialog } from "@/components/project/ExportDialog"
import { MarkdownViewer } from "@/components/artifact/MarkdownViewer"
import { JSONViewer } from "@/components/artifact/JSONViewer"
import { JSONEditor } from "@/components/artifact/JSONEditor"
import { MarkdownEditor } from "@/components/artifact/MarkdownEditor"
import { DependencyTable } from "@/components/artifact/DependencyTable"
import { GapCard } from "@/components/artifact/GapCard"
import { StructuredLogicView } from "@/components/feature/StructuredLogicView"
import { cn } from "@/lib/utils"
import type { FeatureResponse, FeatureStatus, RegistryResponse, GapResponse } from "@/types/api"

export default function ProjectPage() {
  const projectId = useUIStore((s) => s.selectedProjectId)
  const goHome = useUIStore((s) => s.goHome)
  const { selectedFeatureId, activeSidebarItem, setSelectedFeature, setActiveSidebarItem, sidebarWidth, setSidebarWidth } = useUIStore()

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

  const { data: project, isLoading: projectLoading } = useProject(projectId)
  const { data: features } = useProjectFeatures(projectId)
  const { data: registry } = useProjectRegistry(projectId)
  const { data: gaps } = useProjectGaps(projectId)
  const uploadMutation = useUploadDocument(projectId!)

  // Editable project name
  const [isEditingName, setIsEditingName] = useState(false)
  const [editedName, setEditedName] = useState("")
  const renameMutation = useRenameProject(projectId!)

  // Compute documentId from first feature's document_id
  const documentId = features?.[0]?.document_id ?? null

  // Save mutations
  const saveFeatureMutation = useSaveFeature(documentId ?? 0)
  const saveDependencyMutation = useSaveDependencyEntry(documentId ?? 0)
  const saveGapMutation = useSaveGapEntry(documentId ?? 0)

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

  const dbCount = registry?.db.length ?? 0
  const apiCount = registry?.external_api.length ?? 0
  const cacheCount = registry?.cache.length ?? 0
  const gapsCount = gaps?.length ?? 0

  function handleFeatureClick(featureId: number) {
    setSelectedFeature(featureId)
    setActiveSidebarItem(`feature-${featureId}`)
  }

  function handleCategoryClick(category: string) {
    setSelectedFeature(null)
    setActiveSidebarItem(category)
  }

  const isCategoryActive = (cat: string) => activeSidebarItem === cat && selectedFeatureId === null
  const isFeatureActive = (featureId: number) => selectedFeatureId === featureId

  // Find the selected feature object
  const selectedFeature = features?.find((f) => f.id === selectedFeatureId) ?? null

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="relative border-r bg-muted/30 h-screen flex flex-col shrink-0" style={{ width: sidebarWidth }}>
        <div className="p-3 border-b">
          <Button variant="ghost" size="sm" className="w-full justify-start text-xs" onClick={goHome}>
            &larr; Все проекты
          </Button>
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

        {/* .context/ tree */}
        <ScrollArea className="flex-1 p-3">
          <div className="space-y-4">
            {/* Features */}
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1 px-1">
                features/
              </p>
              <div className="space-y-0.5">
                {features?.map((feature) => (
                  <button
                    key={feature.id}
                    onClick={() => handleFeatureClick(feature.id)}
                    title={feature.name}
                    className={cn(
                      "w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors",
                      isFeatureActive(feature.id) ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                    )}
                  >
                    <FeatureStatusDot status={feature.status} />
                    <span className="truncate">{feature.name}</span>
                  </button>
                ))}
                {(!features || features.length === 0) && (
                  <p className="text-xs text-muted-foreground px-2">Загрузите PDF для извлечения фич</p>
                )}
              </div>
            </div>

            {/* db */}
            <SidebarCategory name="db" icon={Database} count={dbCount} active={isCategoryActive("db")} onClick={() => handleCategoryClick("db")} />
            {/* external_api */}
            <SidebarCategory name="external_api" icon={Globe} count={apiCount} active={isCategoryActive("external_api")} onClick={() => handleCategoryClick("external_api")} />
            {/* cache */}
            <SidebarCategory name="cache" icon={HardDrive} count={cacheCount} active={isCategoryActive("cache")} onClick={() => handleCategoryClick("cache")} />
            {/* gaps */}
            <SidebarCategory name="gaps" icon={AlertTriangle} count={gapsCount} active={isCategoryActive("gaps")} onClick={() => handleCategoryClick("gaps")} />
          </div>
        </ScrollArea>

        {/* Export */}
        <div className="p-3 border-t">
          <ExportDialog documentId={projectId!} />
        </div>

        {/* Drag handle */}
        <div
          className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-border transition-colors"
          onMouseDown={() => { isDragging.current = true }}
        />
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6">
        <ProjectContentArea
          key={selectedFeatureId ?? "none"}
          selectedFeature={selectedFeature}
          activeSidebarItem={activeSidebarItem}
          registry={registry ?? null}
          gaps={gaps ?? null}
          documentId={documentId}
          saveFeatureMutation={saveFeatureMutation}
          saveDependencyMutation={saveDependencyMutation}
          saveGapMutation={saveGapMutation}
        />
      </main>
    </div>
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

function SidebarCategory({ name, icon: Icon, count, active, onClick }: { name: string; icon?: LucideIcon; count: number; active: boolean; onClick: () => void }) {
  return (
    <div>
      <button
        onClick={onClick}
        className={cn(
          "w-full text-left flex items-center justify-between px-2 py-1.5 rounded-md text-sm transition-colors",
          active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
        )}
      >
        <span className="flex items-center gap-1.5 font-medium">
          {Icon && <Icon size={14} className="shrink-0" />}
          {name}
        </span>
        {count > 0 && <Badge variant="secondary" className="text-xs h-4 px-1">{count}</Badge>}
      </button>
    </div>
  )
}

// Inline content area that works with project-level data
function ProjectContentArea({
  selectedFeature,
  activeSidebarItem,
  registry,
  gaps,
  documentId,
  saveFeatureMutation,
  saveDependencyMutation,
  saveGapMutation,
}: {
  selectedFeature: FeatureResponse | null
  activeSidebarItem: string | null
  registry: RegistryResponse | null
  gaps: GapResponse[] | null
  documentId: number | null
  saveFeatureMutation: ReturnType<typeof useSaveFeature>
  saveDependencyMutation: ReturnType<typeof useSaveDependencyEntry>
  saveGapMutation: ReturnType<typeof useSaveGapEntry>
}) {
  const [editingTab, setEditingTab] = useState<"overview" | "json" | null>(null)

  if (selectedFeature) {
    return (
      <div className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-semibold">{selectedFeature.name}</h2>
            <Badge variant="secondary" className="text-xs capitalize">
              {selectedFeature.type === "kafka_consumer" ? "Kafka" : selectedFeature.type === "rest_endpoint" ? "REST" : selectedFeature.type === "scheduled_task" ? "Scheduled" : selectedFeature.type}
            </Badge>
            <Badge variant="outline" className="text-xs">
              {Math.round(selectedFeature.confidence * 100)}%
            </Badge>
          </div>
          {selectedFeature.summary && <p className="text-sm text-muted-foreground">{selectedFeature.summary}</p>}
        </div>

        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="structured">Structured Logic</TabsTrigger>
            <TabsTrigger value="json">Business Logic JSON</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="mt-4">
            {documentId !== null && (
              <div className="flex justify-end mb-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditingTab(editingTab === "overview" ? null : "overview")}
                >
                  {editingTab === "overview" ? "Cancel" : "Edit"}
                </Button>
              </div>
            )}
            {editingTab === "overview" ? (
              <MarkdownEditor
                value={selectedFeature.overview_md ?? ""}
                onSave={(md) => {
                  saveFeatureMutation.mutate(
                    { featureId: selectedFeature.id, patch: { overview_md: md } },
                    { onSuccess: () => setEditingTab(null) }
                  )
                }}
                onCancel={() => setEditingTab(null)}
                isSaving={saveFeatureMutation.isPending}
              />
            ) : (
              selectedFeature.overview_md
                ? <MarkdownViewer content={selectedFeature.overview_md} />
                : <p className="text-sm text-muted-foreground">Нет overview.</p>
            )}
          </TabsContent>
          <TabsContent value="structured" className="mt-4">
            {selectedFeature.structured_logic ? <StructuredLogicView logic={selectedFeature.structured_logic} /> : <p className="text-sm text-muted-foreground">Нет structured logic.</p>}
          </TabsContent>
          <TabsContent value="json" className="mt-4">
            {documentId !== null && (
              <div className="flex justify-end mb-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditingTab(editingTab === "json" ? null : "json")}
                >
                  {editingTab === "json" ? "Cancel" : "Edit"}
                </Button>
              </div>
            )}
            {editingTab === "json" ? (
              <JSONEditor
                value={selectedFeature.business_logic ?? {}}
                onSave={(updated) => {
                  saveFeatureMutation.mutate(
                    { featureId: selectedFeature.id, patch: { business_logic: updated } },
                    { onSuccess: () => setEditingTab(null) }
                  )
                }}
                onCancel={() => setEditingTab(null)}
                isSaving={saveFeatureMutation.isPending}
              />
            ) : (
              selectedFeature.business_logic
                ? <JSONViewer value={selectedFeature.business_logic} />
                : <p className="text-sm text-muted-foreground">Нет business logic JSON.</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  if (activeSidebarItem === "db") return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Database Dependencies</h2>
      <DependencyTable
        entries={registry?.db ?? []}
        registryType="db"
        onSaveEntry={documentId !== null ? (entryId, data) => saveDependencyMutation.mutate({ entryId, data }) : undefined}
        isSaving={saveDependencyMutation.isPending}
      />
    </div>
  )
  if (activeSidebarItem === "external_api") return (
    <div>
      <h2 className="text-xl font-semibold mb-4">External API Dependencies</h2>
      <DependencyTable
        entries={registry?.external_api ?? []}
        registryType="external_api"
        onSaveEntry={documentId !== null ? (entryId, data) => saveDependencyMutation.mutate({ entryId, data }) : undefined}
        isSaving={saveDependencyMutation.isPending}
      />
    </div>
  )
  if (activeSidebarItem === "cache") return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Cache Dependencies</h2>
      <DependencyTable
        entries={registry?.cache ?? []}
        registryType="cache"
        onSaveEntry={documentId !== null ? (entryId, data) => saveDependencyMutation.mutate({ entryId, data }) : undefined}
        isSaving={saveDependencyMutation.isPending}
      />
    </div>
  )
  if (activeSidebarItem === "gaps") return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Gaps</h2>
      {gaps && gaps.length > 0 ? (
        <div className="space-y-3">
          {gaps.map((gap) => (
            <GapCard
              key={gap.id}
              gap={gap}
              onSave={documentId !== null ? (patch) => saveGapMutation.mutate({ entryId: gap.id, patch }) : undefined}
              isSaving={saveGapMutation.isPending}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Нет выявленных gaps.</p>
      )}
    </div>
  )

  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-muted-foreground">Выберите фичу или категорию в боковом меню.</p>
    </div>
  )
}
