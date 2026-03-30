import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { KafkaTopicEnrichment, MessageField } from "@/types/api"

function hasAnyCardinality(fields: MessageField[]): boolean {
  return fields.some(f => f.cardinality != null || (f.children && hasAnyCardinality(f.children)))
}

function formatRetention(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds}s`
  const minutes = seconds / 60
  if (minutes < 60) return `${minutes}m`
  const hours = minutes / 60
  if (hours < 24) return `${hours}h`
  const days = hours / 24
  return `${days}d`
}

function MappingRow({ field, depth, showCardinality }: { field: MessageField; depth: number; showCardinality: boolean }) {
  return (
    <>
      <tr className="border-t border-muted">
        <td className="px-2 py-1 font-mono" style={{ paddingLeft: `${0.5 + depth * 1}rem` }}>
          {field.element}{field.is_collection && <span className="text-muted-foreground">[]</span>}
        </td>
        <td className="px-2 py-1 text-muted-foreground">{field.field_type ?? "-"}</td>
        <td className="px-2 py-1">{field.required ? "Yes" : "No"}</td>
        {showCardinality && <td className="px-2 py-1 text-muted-foreground font-mono">{field.cardinality ?? "–"}</td>}
        <td className="px-2 py-1 text-muted-foreground">{field.description ?? "-"}</td>
        <td className="px-2 py-1 text-muted-foreground">{field.source ?? "-"}</td>
      </tr>
      {field.children?.map((child, i) => (
        <MappingRow key={i} field={child} depth={depth + 1} showCardinality={showCardinality} />
      ))}
    </>
  )
}

function FieldsTable({ fields, title }: { fields: MessageField[]; title: string }) {
  if (fields.length === 0) return null
  const showCardinality = hasAnyCardinality(fields)
  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3">
        <div className="border rounded-md overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-2 py-1 text-left font-medium">Element</th>
                <th className="px-2 py-1 text-left font-medium">Type</th>
                <th className="px-2 py-1 text-left font-medium">Req</th>
                {showCardinality && <th className="px-2 py-1 text-left font-medium">Cardinality</th>}
                <th className="px-2 py-1 text-left font-medium">Description</th>
                <th className="px-2 py-1 text-left font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field, idx) => (
                <MappingRow key={idx} field={field} depth={0} showCardinality={showCardinality} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

export function KafkaTopicView({ data }: { data: KafkaTopicEnrichment }) {
  return (
    <div className="space-y-3">
      {data.description && <p className="text-sm text-muted-foreground">{data.description}</p>}
      <div className="flex gap-4 text-xs text-muted-foreground">
        {data.partitions != null && <span>Partitions: {data.partitions}</span>}
        {data.retention_ms != null && <span>Retention: {formatRetention(data.retention_ms)}</span>}
      </div>
      <FieldsTable fields={data.message_fields} title="Message fields (value)" />
      <FieldsTable fields={data.key_fields} title="Key fields" />
      {data.notes.length > 0 && (
        <ul className="text-sm space-y-0.5 list-disc list-inside text-muted-foreground">
          {data.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
