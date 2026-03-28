import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Pencil } from "lucide-react"
import { JSONEditor } from "@/components/artifact/JSONEditor"
import type { RegistryEntry } from "@/types/api"

interface DependencyTableProps {
  entries: RegistryEntry[]
  registryType: "db" | "external_api" | "cache"
  onSaveEntry?: (entryId: number, data: Record<string, unknown>) => void
  isSaving?: boolean
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

function EditCell({ entry, onSaveEntry, isSaving }: { entry: RegistryEntry; onSaveEntry?: (entryId: number, data: Record<string, unknown>) => void; isSaving?: boolean }) {
  if (!onSaveEntry) return <TableCell />
  return (
    <TableCell>
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit {entry.name}</DialogTitle>
          </DialogHeader>
          <JSONEditor
            value={entry.data}
            onSave={(updated) => onSaveEntry(entry.id, updated)}
            onCancel={() => {/* Dialog closes via shadcn internal state */}}
            isSaving={isSaving}
          />
        </DialogContent>
      </Dialog>
    </TableCell>
  )
}

export function DependencyTable({ entries, registryType, onSaveEntry, isSaving }: DependencyTableProps) {
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
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="font-medium font-mono">{stringVal(entry.name)}</TableCell>
              <TableCell>{stringVal(entry.data.type)}</TableCell>
              <TableCell>{countVal(entry.data.columns)}</TableCell>
              <TableCell>{featuresBadges(entry.data.used_by_features)}</TableCell>
              <TableCell>
                {Array.isArray(entry.data.known_operations)
                  ? entry.data.known_operations.map((op, j) => (
                      <Badge key={j} variant="outline" className="text-xs mr-1">
                        {String(op)}
                      </Badge>
                    ))
                  : stringVal(entry.data.known_operations)}
              </TableCell>
              <EditCell entry={entry} onSaveEntry={onSaveEntry} isSaving={isSaving} />
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
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="font-medium">{stringVal(entry.name)}</TableCell>
              <TableCell className="font-mono text-xs">{stringVal(entry.data.base_url)}</TableCell>
              <TableCell>{countVal(entry.data.endpoints)}</TableCell>
              <TableCell>{featuresBadges(entry.data.used_by_features)}</TableCell>
              <EditCell entry={entry} onSaveEntry={onSaveEntry} isSaving={isSaving} />
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
          <TableHead></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => (
          <TableRow key={entry.id}>
            <TableCell className="font-medium">{stringVal(entry.name)}</TableCell>
            <TableCell className="font-mono text-xs">{stringVal(entry.data.structure)}</TableCell>
            <TableCell>{featuresBadges(entry.data.used_by_features)}</TableCell>
            <TableCell>
              {Array.isArray(entry.data.known_operations)
                ? entry.data.known_operations.map((op, j) => (
                    <Badge key={j} variant="outline" className="text-xs mr-1">
                      {String(op)}
                    </Badge>
                  ))
                : stringVal(entry.data.known_operations)}
            </TableCell>
            <EditCell entry={entry} onSaveEntry={onSaveEntry} isSaving={isSaving} />
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
