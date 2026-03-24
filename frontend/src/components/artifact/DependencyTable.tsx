import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

interface DependencyTableProps {
  entries: Record<string, unknown>[]
  registryType: "db" | "external_api" | "cache"
}

function stringVal(v: unknown): string {
  if (v === null || v === undefined) return ""
  if (typeof v === "string") return v
  if (Array.isArray(v)) return v.join(", ")
  return String(v)
}

function countVal(v: unknown): string {
  if (Array.isArray(v)) return String(v.length)
  if (typeof v === "number") return String(v)
  return "-"
}

function featuresBadges(v: unknown) {
  const items = Array.isArray(v) ? v : typeof v === "string" ? [v] : []
  return items.map((item, i) => (
    <Badge key={i} variant="secondary" className="text-xs mr-1">
      {String(item)}
    </Badge>
  ))
}

export function DependencyTable({ entries, registryType }: DependencyTableProps) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4">
        No {registryType.replace("_", " ")} dependencies found.
      </p>
    )
  }

  if (registryType === "db") {
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Columns</TableHead>
            <TableHead>Used By</TableHead>
            <TableHead>Operations</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry, i) => (
            <TableRow key={i}>
              <TableCell className="font-medium font-mono">{stringVal(entry.name)}</TableCell>
              <TableCell>{stringVal(entry.type)}</TableCell>
              <TableCell>{countVal(entry.columns)}</TableCell>
              <TableCell>{featuresBadges(entry.used_by_features)}</TableCell>
              <TableCell>
                {Array.isArray(entry.known_operations)
                  ? entry.known_operations.map((op, j) => (
                      <Badge key={j} variant="outline" className="text-xs mr-1">
                        {String(op)}
                      </Badge>
                    ))
                  : stringVal(entry.known_operations)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }

  if (registryType === "external_api") {
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Base URL</TableHead>
            <TableHead>Endpoints</TableHead>
            <TableHead>Used By</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry, i) => (
            <TableRow key={i}>
              <TableCell className="font-medium">{stringVal(entry.name)}</TableCell>
              <TableCell className="font-mono text-xs">{stringVal(entry.base_url)}</TableCell>
              <TableCell>{countVal(entry.endpoints)}</TableCell>
              <TableCell>{featuresBadges(entry.used_by_features)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }

  // cache
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Structure</TableHead>
          <TableHead>Used By</TableHead>
          <TableHead>Operations</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry, i) => (
          <TableRow key={i}>
            <TableCell className="font-medium">{stringVal(entry.name)}</TableCell>
            <TableCell className="font-mono text-xs">{stringVal(entry.structure)}</TableCell>
            <TableCell>{featuresBadges(entry.used_by_features)}</TableCell>
            <TableCell>
              {Array.isArray(entry.known_operations)
                ? entry.known_operations.map((op, j) => (
                    <Badge key={j} variant="outline" className="text-xs mr-1">
                      {String(op)}
                    </Badge>
                  ))
                : stringVal(entry.known_operations)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
