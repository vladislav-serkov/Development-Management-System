import { Link2, Table as TableIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FieldSourceRef, ProjectDependency, SpecField, SpecTable } from "@/types/api"

const LOCATION_LABELS: Record<string, string> = {
  body: "Body",
  header: "Header",
  query: "Query",
  path: "Path",
}

function statusTone(statusCodes: string): string {
  if (/^\s*2/.test(statusCodes)) {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
  }
  if (/[45]\d\d|[45]xx/i.test(statusCodes)) {
    return "bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300"
  }
  return "bg-muted text-muted-foreground"
}

function SourceRefChips({
  refs,
  projectDependencies,
  onDepClick,
}: {
  refs: FieldSourceRef[]
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}) {
  if (!refs.length) return null
  return (
    <span className="mt-0.5 flex flex-wrap gap-1">
      {refs.map((ref, i) => {
        const dep = projectDependencies?.find(
          (pd) => pd.dep_type === ref.dep_type && pd.name === ref.dep_name
        )
        const clickable = dep && onDepClick
        const label = ref.field ? `${ref.dep_name}.${ref.field}` : ref.dep_name
        return (
          <button
            key={i}
            type="button"
            disabled={!clickable}
            onClick={() => clickable && onDepClick(dep)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-1.5 py-0.5 text-[0.6875rem] font-mono",
              clickable ? "cursor-pointer transition-colors hover:border-primary hover:bg-accent" : "cursor-default"
            )}
            title={clickable ? "Открыть зависимость" : label}
          >
            <Link2 className="h-2.5 w-2.5" />
            {label}
          </button>
        )
      })}
    </span>
  )
}

function SpecFieldRow({
  field,
  table,
  depth,
  projectDependencies,
  onDepClick,
}: {
  field: SpecField
  table: SpecTable
  depth: number
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}) {
  return (
    <>
      <tr className="border-t border-muted">
        <td className="px-2 py-1 font-mono" style={{ paddingLeft: `${0.5 + depth}rem` }}>
          {field.name}
        </td>
        {table.columns.map((col, ci) => (
          <td key={ci} className="px-2 py-1 align-top text-muted-foreground whitespace-pre-wrap">
            {field.cells[ci] || (col.role === "source" && field.source_refs?.length ? "" : "—")}
            {col.role === "source" && (
              <SourceRefChips
                refs={field.source_refs ?? []}
                projectDependencies={projectDependencies}
                onDepClick={onDepClick}
              />
            )}
          </td>
        ))}
      </tr>
      {(field.children ?? []).map((child, i) => (
        <SpecFieldRow
          key={i}
          field={child}
          table={table}
          depth={depth + 1}
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
        />
      ))}
    </>
  )
}

/** Bare table grid (no card chrome) — reused by logic-step mappings and diffs. */
export function SpecTableGrid({
  table,
  projectDependencies,
  onDepClick,
}: {
  table: SpecTable
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="bg-muted/50">
          <tr>
            <th className="text-left px-2 py-1 font-medium">Параметр</th>
            {table.columns.map((col, i) => (
              <th key={i} className="text-left px-2 py-1 font-medium">{col.header || "—"}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.fields.map((field, i) => (
            <SpecFieldRow
              key={i}
              field={field}
              table={table}
              depth={0}
              projectDependencies={projectDependencies}
              onDepClick={onDepClick}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One spec table with its caption/location/status header, as the spec wrote it. */
export function SpecTableCard({
  table,
  projectDependencies,
  onDepClick,
}: {
  table: SpecTable
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}) {
  const locationLabel = table.location ? LOCATION_LABELS[table.location] ?? table.location : null
  return (
    <div className="overflow-hidden rounded-xl border border-border/70">
      {(table.caption || locationLabel || table.status_codes) && (
        <div className="flex flex-wrap items-center gap-2 bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          <TableIcon className="h-3 w-3 shrink-0" />
          {table.status_codes && (
            <span className={cn("rounded px-1.5 py-0.5 font-mono font-medium", statusTone(table.status_codes))}>
              HTTP {table.status_codes}
            </span>
          )}
          {locationLabel && (
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono">{locationLabel}</span>
          )}
          {table.caption && <span className="min-w-0">{table.caption}</span>}
        </div>
      )}
      <SpecTableGrid table={table} projectDependencies={projectDependencies} onDepClick={onDepClick} />
    </div>
  )
}

/** A list of spec tables with a shared empty state. */
export function SpecTablesSection({
  tables,
  emptyText,
  projectDependencies,
  onDepClick,
}: {
  tables: SpecTable[]
  emptyText: string
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}) {
  if (!tables.length) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-10 text-center">
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      {tables.map((table, i) => (
        <SpecTableCard
          key={table.table_id ?? i}
          table={table}
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
        />
      ))}
    </div>
  )
}
