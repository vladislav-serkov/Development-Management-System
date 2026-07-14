import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { ArrowUpRight } from "lucide-react"
import type { DbTableEnrichment } from "@/types/api"

/** "product_schedule.id" → table "product_schedule", column "id". */
function parseReference(ref: string): { table: string; column: string | null } {
  const dot = ref.indexOf(".")
  if (dot === -1) return { table: ref.trim(), column: null }
  return { table: ref.slice(0, dot).trim(), column: ref.slice(dot + 1).trim() || null }
}

function ReferenceCell({
  reference,
  knownTables,
  onNavigate,
}: {
  reference: string | null
  knownTables: Set<string>
  onNavigate?: (table: string) => void
}) {
  if (!reference) return <span className="text-muted-foreground text-sm">—</span>

  const { table, column } = parseReference(reference)
  const label = column ? `${table}.${column}` : table
  // Only a table the project actually has enriched can be navigated to.
  const canNavigate = onNavigate && knownTables.has(table.toLowerCase())

  if (!canNavigate) {
    return <span className="font-mono text-sm text-muted-foreground">{label}</span>
  }

  return (
    <button
      className="group inline-flex items-center gap-1 font-mono text-sm text-foreground hover:text-primary transition-colors"
      onClick={() => onNavigate(table)}
      title={`Перейти к таблице ${table}`}
    >
      {label}
      <ArrowUpRight className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  )
}

export function DbSchemaView({
  data,
  knownTables = new Set(),
  onNavigateToTable,
}: {
  data: DbTableEnrichment
  /** Lower-cased names of db_table dependencies in this project — used to make an FK clickable. */
  knownTables?: Set<string>
  onNavigateToTable?: (table: string) => void
}) {
  const hasReferences = data.columns.some((col) => col.fk_references)

  return (
    <div className="space-y-3">
      {data.description && <p className="text-sm text-muted-foreground">{data.description}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Колонка</TableHead>
            <TableHead>Тип</TableHead>
            <TableHead>NULL</TableHead>
            {hasReferences && <TableHead>Ссылается на</TableHead>}
            <TableHead>Описание</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.columns.map((col) => (
            <TableRow key={col.name}>
              <TableCell className="font-mono text-sm">
                {col.name}
                {col.is_pk && <Badge variant="outline" className="ml-1 text-[0.625rem]">PK</Badge>}
                {col.is_fk && <Badge variant="outline" className="ml-1 text-[0.625rem]">FK</Badge>}
              </TableCell>
              <TableCell className="font-mono text-sm">{col.col_type}</TableCell>
              <TableCell>{col.nullable ? "Да" : "Нет"}</TableCell>
              {hasReferences && (
                <TableCell>
                  <ReferenceCell
                    reference={col.fk_references}
                    knownTables={knownTables}
                    onNavigate={onNavigateToTable}
                  />
                </TableCell>
              )}
              <TableCell className="text-sm text-muted-foreground">{col.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {data.indexes.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase mb-1">Индексы</p>
          <ul className="text-sm list-disc list-inside">
            {data.indexes.map((idx, i) => <li key={i}>{idx}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
