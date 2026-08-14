import { FileText, Table as TableIcon } from "lucide-react"
import { SpecTableGrid } from "@/components/feature/SpecTableView"
import type { GenericTable, LogicStep, ProjectDependency } from "@/types/api"

interface LogicTreeProps {
  steps: LogicStep[]
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
  onDocRefClick?: (name: string) => void
}

function ReferenceTableView({ table }: { table: GenericTable }) {
  const headers = table.headers ?? []
  const rows = table.rows ?? []
  return (
    <div className="mt-3 ml-14 overflow-hidden rounded-xl border border-border/70">
      {table.caption && (
        <div className="flex items-center gap-1.5 bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          <TableIcon className="h-3 w-3" />
          <span>{table.caption}</span>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-muted/50">
            <tr>
              {headers.map((h, i) => (
                <th key={i} className="text-left px-2 py-1 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="border-t border-muted">
                {headers.map((_, ci) => (
                  <td key={ci} className="px-2 py-1 text-muted-foreground align-top whitespace-pre-wrap">
                    {row[ci] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DocRefChips({ refs, onClick }: { refs: string[]; onClick?: (name: string) => void }) {
  if (refs.length === 0) return null
  return (
    <div className="mt-1 ml-14 flex flex-wrap gap-1.5">
      {refs.map((name) => (
        <button
          key={name}
          type="button"
          disabled={!onClick}
          onClick={() => onClick?.(name)}
          className={`inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs text-slate-800 ${
            onClick ? "cursor-pointer transition-colors hover:border-primary hover:bg-accent" : "cursor-default"
          }`}
          title={onClick ? "Открыть документ" : name}
        >
          <FileText className="h-3 w-3" />
          <span className="font-mono">{name}</span>
        </button>
      ))}
    </div>
  )
}

function LogicStepNode({
  step,
  level,
  projectDependencies,
  onDepClick,
  onDocRefClick,
}: {
  step: LogicStep
  level: number
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
  onDocRefClick?: (name: string) => void
}) {
  const mappingTables = step.mapping_tables ?? []
  return (
    <div className={level === 0 ? "rounded-xl border border-border/70 bg-background px-4 py-3" : ""}>
      <div className="flex items-start gap-3 py-1">
        <span className="min-w-[2.5rem] shrink-0 rounded-md bg-muted px-2 py-1 text-center font-mono text-sm text-muted-foreground">
          {step.number}
        </span>
        <span className="pt-1 text-sm leading-6">{step.text}</span>
      </div>
      <DocRefChips refs={step.external_doc_refs ?? []} onClick={onDocRefClick} />
      {mappingTables.map((table, i) => (
        <div key={i} className="mt-3 ml-14 overflow-hidden rounded-xl border border-border/70">
          {(step.message_type || table.caption) && (
            <div className="flex items-center gap-1.5 bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
              <TableIcon className="h-3 w-3" />
              {step.message_type && <span className="font-mono">{step.message_type}</span>}
              {table.caption && <span>{table.caption}</span>}
            </div>
          )}
          <SpecTableGrid table={table} projectDependencies={projectDependencies} onDepClick={onDepClick} />
        </div>
      ))}
      {(step.reference_tables ?? []).map((t, i) => (
        <ReferenceTableView key={`ref-${i}`} table={t} />
      ))}
      {step.children.length > 0 && (
        <div className="mt-3 ml-6 space-y-3 border-l-2 border-muted pl-4">
          {step.children.map((child, i) => (
            <LogicStepNode
              key={i}
              step={child}
              level={level + 1}
              projectDependencies={projectDependencies}
              onDepClick={onDepClick}
              onDocRefClick={onDocRefClick}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function LogicTree({ steps, projectDependencies, onDepClick, onDocRefClick }: LogicTreeProps) {
  if (steps.length === 0) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-10 text-center">
        <p className="text-sm font-medium">Шаги обработки не заполнены</p>
        <p className="mt-2 text-xs text-muted-foreground">После извлечения здесь появится последовательность бизнес-логики из ТЗ.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <LogicStepNode
          key={i}
          step={step}
          level={0}
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
          onDocRefClick={onDocRefClick}
        />
      ))}
    </div>
  )
}
