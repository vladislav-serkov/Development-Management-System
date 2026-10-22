import { useState } from "react"
import { cn } from "@/lib/utils"
import { countLabel } from "@/lib/plural"
import { MethodBadge } from "./MethodBadge"
import { SidebarTrashButton } from "./sidebar-helpers"
import { stripMethodPrefix } from "@/lib/artifacts"
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
  const name = feature.display_name ?? stripMethodPrefix(feature.name, feature.method)
  const stale = !feature.orphaned && (feature.gaps_stale || feature.test_cases_stale)

  return (
    <div>
      <div className="group relative flex items-start">
        <button
          onClick={() => onFeatureClick(feature.name)}
          title={feature.display_name ?? feature.name}
          className={cn(
            "flex-1 rounded-lg px-2 py-1.5 text-left transition-colors",
            isActive ? "bg-background shadow-[0_0_0_1px_var(--color-border)]" : "hover:bg-background/70",
          )}
        >
          <div className="flex items-start gap-1.5">
            <MethodBadge method={feature.method} featureType={feature.type} />
            <span
              className={cn(
                "min-w-0 break-all font-mono text-[0.8125rem] leading-[1.1rem] font-medium",
                feature.orphaned && "text-muted-foreground line-through decoration-red-400/60",
              )}
            >
              {name}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[0.6875rem] text-muted-foreground">
            {feature.status === "extracting" ? (
              <span className="text-amber-600 dark:text-amber-400">извлечение…</span>
            ) : (
              <>
                <span>{countLabel(feature.test_case_count ?? 0, ["кейс", "кейса", "кейсов"])}</span>
                <span>{countLabel(feature.bug_count ?? 0, ["баг", "бага", "багов"])}</span>
              </>
            )}
            {feature.schedule && <span>{feature.schedule}</span>}
            {feature.orphaned && (
              <span className="font-medium text-red-600 dark:text-red-400" title="Фичи больше нет в текущей версии спеки">
                нет в спеке
              </span>
            )}
            {stale && (
              <span
                className="font-medium text-amber-600 dark:text-amber-400"
                title={`Анализ посчитан до изменений в спеке или её источниках${feature.stale_spec_note ? ` (${feature.stale_spec_note})` : ""}`}
              >
                спека обновилась
              </span>
            )}
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
