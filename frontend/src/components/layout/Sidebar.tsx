import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ExportDialog } from "@/components/project/ExportDialog"
import { useUIStore } from "@/stores/uiStore"
import { cn } from "@/lib/utils"
import type { DocumentResponse, FeatureStatus } from "@/types/api"

interface SidebarProps {
  document: DocumentResponse
}

function featureStatusDot(status: FeatureStatus) {
  const colors: Record<FeatureStatus, string> = {
    done: "bg-green-500",
    extracting: "bg-amber-400",
    error: "bg-destructive",
    detected: "bg-muted-foreground/40",
  }
  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full shrink-0", colors[status] ?? "bg-muted-foreground/40")}
    />
  )
}

export function Sidebar({ document }: SidebarProps) {
  const { selectedFeatureName, activeSidebarItem, setSelectedFeature, setActiveSidebarItem, goHome } = useUIStore()

  function handleFeatureClick(featureName: string) {
    setSelectedFeature(featureName)
    setActiveSidebarItem(`feature-${featureName}`)
  }

  const isFeatureActive = (featureName: string) =>
    selectedFeatureName === featureName

  return (
    <aside className="w-64 border-r bg-muted/30 h-screen flex flex-col shrink-0">
      {/* Top navigation */}
      <div className="p-3 border-b">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-xs"
          onClick={goHome}
        >
          ← Back to projects
        </Button>
        <p className="mt-2 px-1 text-sm font-medium truncate" title={document.filename.replace(/\.pdf$/i, "")}>
          {document.filename.replace(/\.pdf$/i, "")}
        </p>
      </div>

      {/* Tree navigation */}
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-4">
          {/* Features */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1 px-1">
              features/
            </p>
            <div className="space-y-0.5">
              {document.features.map((feature) => (
                <button
                  key={feature.name}
                  onClick={() => handleFeatureClick(feature.name)}
                  className={cn(
                    "w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors",
                    isFeatureActive(feature.name)
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent/50"
                  )}
                >
                  {featureStatusDot(feature.status)}
                  <span className="truncate">{feature.name}</span>
                </button>
              ))}
              {document.features.length === 0 && (
                <p className="text-xs text-muted-foreground px-2">No features detected</p>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>

      {/* Export button at bottom */}
      <div className="p-3 border-t">
        <ExportDialog projectSlug={document.project_slug} docSlug={document.slug} />
      </div>
    </aside>
  )
}
