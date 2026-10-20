import { useState } from "react"
import { cn } from "@/lib/utils"
import { MethodBadge } from "./MethodBadge"
import { FeatureStatusDot, SidebarTrashButton, getFeatureSidebarMeta } from "./sidebar-helpers"
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog"
import type { FeatureResponse } from "@/types/api"

interface FeatureListItemProps {
  feature: FeatureResponse
  isActive: boolean
  onFeatureClick: (name: string) => void
  onDelete: (name: string) => void
  isDeletePending?: boolean
}

export function FeatureListItem({ feature, isActive, onFeatureClick, onDelete, isDeletePending }: FeatureListItemProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const hasDisplayName = !!feature.display_name
  const featureMeta = hasDisplayName
    ? { primary: feature.display_name as string, secondary: feature.schedule ?? null }
    : getFeatureSidebarMeta(feature.name)

  return (
    <div>
      <div className="group relative flex items-center">
        <button
          onClick={() => onFeatureClick(feature.name)}
          title={feature.display_name ?? feature.name}
          className={cn(
            "flex-1 rounded-xl border px-3 py-2.5 text-left transition-colors",
            isActive
              ? "border-primary/20 bg-background shadow-sm"
              : "border-transparent hover:border-border hover:bg-background/80"
          )}
        >
          <div className="flex items-start gap-2">
            <FeatureStatusDot status={feature.status} />
            <div className="min-w-0 flex-1">
              {featureMeta.secondary && (
                <p className="truncate text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground/80">
                  {featureMeta.secondary}
                </p>
              )}
              <div className="mt-1 flex items-center gap-2">
                <MethodBadge method={feature.method} featureType={feature.type} />
                <span className={cn("truncate text-sm font-medium", feature.orphaned && "text-muted-foreground line-through decoration-red-400/60")}>
                  {featureMeta.primary}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[0.6875rem] text-muted-foreground">
                <span>{feature.test_case_count ?? 0} тестов</span>
                <span>{feature.bug_count ?? 0} багов</span>
                {feature.orphaned && (
                  <span className="font-medium text-red-600 dark:text-red-400" title="Фичи больше нет в текущей версии спеки">
                    нет в спеке
                  </span>
                )}
                {!feature.orphaned && (feature.gaps_stale || feature.test_cases_stale) && (
                  <span
                    className="font-medium text-amber-600 dark:text-amber-400"
                    title={`Анализ посчитан до изменений в спеке или её источниках${feature.stale_spec_note ? ` (${feature.stale_spec_note})` : ""}`}
                  >
                    устарело
                  </span>
                )}
              </div>
            </div>
          </div>
        </button>

        <SidebarTrashButton onDelete={() => setConfirmOpen(true)} />
      </div>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Удалить фичу"
        description={`Удалить фичу "${feature.display_name ?? feature.name}" и все связанные test-cases/bugs?`}
        onConfirm={() => {
          onDelete(feature.name)
          setConfirmOpen(false)
        }}
        isPending={isDeletePending}
      />
    </div>
  )
}
