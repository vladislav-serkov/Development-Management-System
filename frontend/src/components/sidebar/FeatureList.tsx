import { useCallback, useMemo, useRef, useState } from "react"
import { Input } from "@/components/ui/input"
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
      <div className="mb-1.5 flex items-center gap-1.5 px-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Фичи
        {features && features.length > 0 && <span className="font-normal tabular-nums">{features.length}</span>}
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

      <div className="space-y-0.5" role="listbox" aria-label="Список фич" ref={listRef}>
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
            После импорта первой страницы Confluence здесь появятся извлеченные фичи.
          </div>
        )}
      </div>
    </section>
  )
}
