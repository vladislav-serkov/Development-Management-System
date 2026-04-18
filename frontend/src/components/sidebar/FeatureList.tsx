import { useCallback, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Layers } from "lucide-react"
import { FeatureListItem } from "./FeatureListItem"
import type { FeatureResponse } from "@/types/api"

interface FeatureListProps {
  features: FeatureResponse[] | undefined
  selectedFeatureName: string | null
  onFeatureClick: (name: string) => void
  onDeleteFeature: (name: string) => void
  isDeletePending?: boolean
}

export function FeatureList({
  features,
  selectedFeatureName,
  onFeatureClick,
  onDeleteFeature,
  isDeletePending,
}: FeatureListProps) {
  const [search, setSearch] = useState("")
  const [focusIndex, setFocusIndex] = useState(-1)
  const listRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    if (!features) return []
    if (!search.trim()) return features
    const q = search.toLowerCase()
    return features.filter((f) => f.name.toLowerCase().includes(q))
  }, [features, search])

  const showSearch = (features?.length ?? 0) >= 5

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setFocusIndex((i) => Math.min(i + 1, filtered.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setFocusIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === "Enter" && focusIndex >= 0 && focusIndex < filtered.length) {
        e.preventDefault()
        onFeatureClick(filtered[focusIndex].name)
      }
    },
    [filtered, focusIndex, onFeatureClick]
  )

  return (
    <section>
      <div className="mb-2 flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Layers className="h-3.5 w-3.5" />
          Навигация по фичам
        </div>
        {features && features.length > 0 && (
          <Badge variant="outline" className="h-5 px-1.5 py-0 text-[0.625rem]">
            {features.length}
          </Badge>
        )}
      </div>

      {showSearch && (
        <div className="mb-2">
          <Input
            placeholder="Поиск фич..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setFocusIndex(-1)
            }}
            onKeyDown={handleKeyDown}
            className="h-7 text-xs"
          />
        </div>
      )}

      <div className="space-y-1" role="listbox" aria-label="Список фич" ref={listRef}>
        {filtered.map((feature, index) => (
          <div key={feature.name} aria-selected={selectedFeatureName === feature.name} data-focused={focusIndex === index || undefined}>
            <FeatureListItem
              feature={feature}
              isActive={selectedFeatureName === feature.name}
              onFeatureClick={onFeatureClick}
              onDelete={onDeleteFeature}
              isDeletePending={isDeletePending}
            />
          </div>
        ))}

        {filtered.length === 0 && search && (
          <div className="rounded-xl border border-dashed px-3 py-4 text-xs text-muted-foreground">
            Ничего не найдено по запросу "{search}"
          </div>
        )}

        {(!features || features.length === 0) && !search && (
          <div className="rounded-xl border border-dashed px-3 py-4 text-xs text-muted-foreground">
            После загрузки первого PDF здесь появятся извлеченные фичи.
          </div>
        )}
      </div>
    </section>
  )
}
