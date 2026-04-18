import { useState } from "react"
import { cn } from "@/lib/utils"
import { AnimatedDots } from "@/components/dependency/AnimatedDots"
import { MethodBadge } from "./MethodBadge"
import { DepStatusDot, SidebarTrashButton } from "./sidebar-helpers"
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog"
import type { ProjectDependency } from "@/types/api"

interface DependencyListItemProps {
  dep: ProjectDependency
  isActive: boolean
  onClick: () => void
  onDelete: () => void
  isDeletePending?: boolean
}

export function DependencyListItem({ dep, isActive, onClick, onDelete, isDeletePending }: DependencyListItemProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <>
      <div className="group relative flex items-center">
        <button
          onClick={onClick}
          title={dep.name}
          className={cn(
            "flex-1 rounded-xl border px-3 py-2 text-left text-sm transition-colors",
            isActive
              ? "border-primary/20 bg-background shadow-sm"
              : "border-transparent hover:border-border hover:bg-background/80"
          )}
        >
          <div className="flex items-center gap-2">
            <DepStatusDot status={dep.enrichment_status} />
            {dep.dep_type === "external_api" && dep.method && (
              <MethodBadge method={dep.method} featureType="rest_endpoint" />
            )}
            <span className="truncate">{dep.name}</span>
            {dep.enrichment_status === "running" && (
              <AnimatedDots className="ml-auto shrink-0 text-xs" />
            )}
          </div>
        </button>

        <SidebarTrashButton onDelete={() => setConfirmOpen(true)} />
      </div>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Удалить зависимость"
        description={`Удалить зависимость "${dep.name}"?`}
        onConfirm={() => {
          onDelete()
          setConfirmOpen(false)
        }}
        isPending={isDeletePending}
      />
    </>
  )
}
