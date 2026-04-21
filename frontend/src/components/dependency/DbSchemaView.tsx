import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import type { DbTableEnrichment } from "@/types/api"

export function DbSchemaView({ data }: { data: DbTableEnrichment }) {
  return (
    <div className="space-y-3">
      {data.description && <p className="text-sm text-muted-foreground">{data.description}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Колонка</TableHead>
            <TableHead>Тип</TableHead>
            <TableHead>NULL</TableHead>
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
