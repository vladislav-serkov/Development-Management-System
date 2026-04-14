import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ExternalApiEnrichment } from "@/types/api"

function generateExampleValue(schema: Record<string, unknown>): unknown {
  const type = schema.type as string | undefined
  const format = schema.format as string | undefined
  const enumValues = schema.enum as unknown[] | undefined
  const properties = schema.properties as Record<string, Record<string, unknown>> | undefined
  const items = schema.items as Record<string, unknown> | undefined

  if (type === "string") {
    if (format === "uuid") return "550e8400-e29b-41d4-a716-446655440000"
    if (format === "date-time") return "2024-01-01T00:00:00Z"
    if (format === "date") return "2024-01-01"
    if (format === "email") return "user@example.com"
    if (enumValues && enumValues.length > 0) return enumValues[0]
    return "string"
  }
  if (type === "number" || type === "integer") return 0
  if (type === "boolean") return false
  if (type === "array") {
    if (items) return [generateExampleValue(items)]
    return []
  }
  if (type === "object" && properties) {
    const result: Record<string, unknown> = {}
    for (const [key, fieldSchema] of Object.entries(properties)) {
      result[key] = generateExampleValue(fieldSchema)
    }
    return result
  }
  return null
}

interface SchemaTableProps {
  schema: Record<string, unknown>
}

function SchemaTable({ schema }: SchemaTableProps) {
  if (!schema || typeof schema !== "object") return null
  const properties = schema.properties as Record<string, Record<string, unknown>> | undefined
  const required = (schema.required as string[] | undefined) ?? []

  if (!properties) return null

  function renderRows(
    props: Record<string, Record<string, unknown>>,
    req: string[],
    depth: number
  ): React.ReactNode[] {
    if (depth > 4) return []
    return Object.entries(props).flatMap(([fieldName, fieldSchema]) => {
      if (!fieldSchema || typeof fieldSchema !== "object") return []
      const fieldType = fieldSchema.type as string | undefined
      const fieldDesc = fieldSchema.description as string | undefined
      const fieldProps = fieldSchema.properties as Record<string, Record<string, unknown>> | undefined
      const fieldItems = fieldSchema.items as Record<string, unknown> | undefined

      let displayType = fieldType ?? "unknown"
      if (fieldType === "array" && fieldItems) {
        const itemType = (fieldItems.type as string | undefined) ?? "unknown"
        displayType = `array<${itemType}>`
      }

      const rows: React.ReactNode[] = [
        <TableRow key={`${depth}-${fieldName}`}>
          <TableCell className={`font-mono text-sm pl-${depth * 4 + 2}`} style={{ paddingLeft: `${depth * 16 + 8}px` }}>
            {fieldName}
          </TableCell>
          <TableCell className="font-mono text-xs text-muted-foreground">{displayType}</TableCell>
          <TableCell className="text-xs">{req.includes(fieldName) ? "Да" : "Нет"}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{fieldDesc ?? ""}</TableCell>
        </TableRow>,
      ]

      if (fieldType === "object" && fieldProps) {
        const nestedRequired = (fieldSchema.required as string[] | undefined) ?? []
        rows.push(...renderRows(fieldProps, nestedRequired, depth + 1))
      } else if (fieldType === "array" && fieldItems) {
        const itemsType = (fieldItems.type as string | undefined)
        const itemsProps = fieldItems.properties as Record<string, Record<string, unknown>> | undefined
        if (itemsType === "object" && itemsProps) {
          const itemsRequired = (fieldItems.required as string[] | undefined) ?? []
          rows.push(...renderRows(itemsProps, itemsRequired, depth + 1))
        }
      }

      return rows
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Поле</TableHead>
          <TableHead>Тип</TableHead>
          <TableHead>Обяз.</TableHead>
          <TableHead>Описание</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {renderRows(properties, required, 0)}
      </TableBody>
    </Table>
  )
}

function errorBadgeClass(code: string): string {
  if (code.startsWith("4")) return "border-amber-300 text-amber-700"
  if (code.startsWith("5")) return "border-red-300 text-red-700"
  return ""
}

export function ApiEndpointsView({ data }: { data: ExternalApiEnrichment }) {
  return (
    <div className="space-y-3">
      {data.description && <p className="text-sm text-muted-foreground">{data.description}</p>}
      {data.base_url && <p className="text-xs font-mono text-muted-foreground">Базовый URL: {data.base_url}</p>}
      {data.endpoints.map((ep, i) => (
        <div key={i} className="space-y-3">
          {ep.description && <p className="text-sm mb-2">{ep.description}</p>}
          {ep.params.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Параметр</TableHead>
                  <TableHead>Где</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Обяз.</TableHead>
                  <TableHead>Описание</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ep.params.map((p) => (
                  <TableRow key={p.name}>
                    <TableCell className="font-mono text-sm">{p.name}</TableCell>
                    <TableCell className="text-sm">{p.param_in}</TableCell>
                    <TableCell className="font-mono text-sm">{p.param_type}</TableCell>
                    <TableCell>{p.required ? "Да" : "Нет"}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{p.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {ep.request_body_schema && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1">Тело запроса</h4>
              <SchemaTable schema={ep.request_body_schema} />
            </>
          )}

          {ep.response_schema && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1">Ответ</h4>
              <SchemaTable schema={ep.response_schema} />
            </>
          )}

          {(ep.response_schema || ep.error_codes.length > 0) && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1">Примеры</h4>
              {ep.response_schema && (
                <div className="mb-2">
                  <p className="text-xs text-muted-foreground mb-1">Успешный ответ</p>
                  <pre className="bg-muted rounded p-2 text-xs font-mono overflow-x-auto mt-1">
                    <code>{JSON.stringify(generateExampleValue(ep.response_schema), null, 2)}</code>
                  </pre>
                </div>
              )}
              {ep.error_codes.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Ответ с ошибкой</p>
                  <pre className="bg-muted rounded p-2 text-xs font-mono overflow-x-auto mt-1">
                    <code>{JSON.stringify({ error: { code: ep.error_codes[0], title: "Описание ошибки", uuid: "550e8400-e29b-41d4-a716-446655440000" } }, null, 2)}</code>
                  </pre>
                </div>
              )}
            </>
          )}

          {ep.error_codes.length > 0 && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1">Коды ошибок</h4>
              <div className="flex flex-wrap gap-1.5">
                {ep.error_codes.map((code) => (
                  <Badge key={code} variant="outline" className={`font-mono text-xs ${errorBadgeClass(code)}`}>
                    {code}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  )
}
