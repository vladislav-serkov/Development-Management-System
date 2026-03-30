import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { X, Plus } from "lucide-react"
import type { ParameterField } from "@/types/api"

interface ParametersTableProps {
  parameters: ParameterField[]
  showParamIn?: boolean
  isEditing?: boolean
  onChange?: (params: ParameterField[]) => void
}

function emptyParam(): ParameterField {
  return {
    name: "",
    field_type: "string",
    description: "",
    required: false,
    validation_rules: [],
    param_in: null,
    children: [],
  }
}

function EditableParameterRows({
  parameters,
  depth,
  showParamIn,
  onChange,
}: {
  parameters: ParameterField[]
  depth: number
  showParamIn: boolean
  onChange: (params: ParameterField[]) => void
}) {
  const updateParam = (i: number, updated: ParameterField) => {
    const next = parameters.map((p, idx) => (idx === i ? updated : p))
    onChange(next)
  }

  const deleteParam = (i: number) => {
    onChange(parameters.filter((_, idx) => idx !== i))
  }

  const addChild = (i: number) => {
    const next = parameters.map((p, idx) =>
      idx === i ? { ...p, children: [...p.children, emptyParam()] } : p
    )
    onChange(next)
  }

  return (
    <>
      {parameters.map((param, i) => (
        <>
          <TableRow key={`edit-${depth}-${i}`}>
            <TableCell style={{ paddingLeft: `${depth * 24 + 12}px` }}>
              <input
                className="font-mono text-sm bg-transparent border-b border-border outline-none w-full"
                value={param.name}
                placeholder="name"
                onChange={(e) => updateParam(i, { ...param, name: e.target.value })}
              />
            </TableCell>
            <TableCell>
              <input
                className="text-xs font-mono bg-transparent border-b border-border outline-none w-full"
                value={param.field_type}
                placeholder="type"
                onChange={(e) => updateParam(i, { ...param, field_type: e.target.value })}
              />
            </TableCell>
            {showParamIn && (
              <TableCell>
                <select
                  className="text-xs bg-transparent border-b border-border outline-none"
                  value={param.param_in ?? ""}
                  onChange={(e) =>
                    updateParam(i, { ...param, param_in: e.target.value || null })
                  }
                >
                  <option value="">—</option>
                  <option value="body">body</option>
                  <option value="query">query</option>
                  <option value="path">path</option>
                  <option value="header">header</option>
                </select>
              </TableCell>
            )}
            <TableCell>
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={param.required}
                  onChange={(e) => updateParam(i, { ...param, required: e.target.checked })}
                />
                <span className="text-xs">{param.required ? "required" : "optional"}</span>
              </label>
            </TableCell>
            <TableCell>
              <input
                className="text-sm bg-transparent border-b border-border outline-none w-full"
                value={param.description}
                placeholder="description"
                onChange={(e) => updateParam(i, { ...param, description: e.target.value })}
              />
            </TableCell>
            <TableCell>
              <input
                className="text-xs text-muted-foreground bg-transparent border-b border-border outline-none w-full"
                value={param.validation_rules.join(", ")}
                placeholder="rule1, rule2"
                onChange={(e) =>
                  updateParam(i, {
                    ...param,
                    validation_rules: e.target.value
                      ? e.target.value.split(",").map((r) => r.trim())
                      : [],
                  })
                }
              />
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-1">
                <button
                  className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  title="Add child"
                  onClick={() => addChild(i)}
                >
                  <Plus className="h-3 w-3" />
                </button>
                <button
                  className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  title="Delete row"
                  onClick={() => deleteParam(i)}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </TableCell>
          </TableRow>
          {param.children.length > 0 && (
            <EditableParameterRows
              parameters={param.children}
              depth={depth + 1}
              showParamIn={showParamIn}
              onChange={(updatedChildren) =>
                updateParam(i, { ...param, children: updatedChildren })
              }
            />
          )}
        </>
      ))}
    </>
  )
}

function ParameterRows({
  parameters,
  depth,
  showParamIn,
}: {
  parameters: ParameterField[]
  depth: number
  showParamIn: boolean
}) {
  return (
    <>
      {parameters.map((param, i) => (
        <>
          <TableRow key={`${depth}-${i}`}>
            <TableCell style={{ paddingLeft: `${depth * 24 + 12}px` }}>
              <span className="font-mono text-sm">{param.name}</span>
            </TableCell>
            <TableCell>
              <Badge variant="secondary" className="text-xs font-mono">
                {param.field_type}
              </Badge>
            </TableCell>
            {showParamIn && (
              <TableCell>
                {param.param_in ? (
                  <Badge variant="outline" className="text-xs">
                    {param.param_in}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground text-xs">—</span>
                )}
              </TableCell>
            )}
            <TableCell>
              {param.required ? (
                <Badge className="text-xs bg-green-100 text-green-800 hover:bg-green-100 border-green-200">
                  required
                </Badge>
              ) : (
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  optional
                </Badge>
              )}
            </TableCell>
            <TableCell className="text-sm">{param.description}</TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {param.validation_rules.length > 0
                ? param.validation_rules.join(", ")
                : "—"}
            </TableCell>
          </TableRow>
          {param.children.length > 0 && (
            <ParameterRows
              parameters={param.children}
              depth={depth + 1}
              showParamIn={showParamIn}
            />
          )}
        </>
      ))}
    </>
  )
}

export function ParametersTable({
  parameters,
  showParamIn = false,
  isEditing = false,
  onChange,
}: ParametersTableProps) {
  if (!isEditing && parameters.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет параметров</p>
  }

  return (
    <div className="rounded-md border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Имя</TableHead>
            <TableHead>Тип</TableHead>
            {showParamIn && <TableHead>In</TableHead>}
            <TableHead>Обязательность</TableHead>
            <TableHead>Описание</TableHead>
            <TableHead>Валидация</TableHead>
            {isEditing && <TableHead className="w-16"></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {isEditing ? (
            <EditableParameterRows
              parameters={parameters}
              depth={0}
              showParamIn={showParamIn}
              onChange={onChange ?? (() => {})}
            />
          ) : (
            <ParameterRows
              parameters={parameters}
              depth={0}
              showParamIn={showParamIn}
            />
          )}
        </TableBody>
      </Table>
      {isEditing && (
        <div className="p-2 border-t">
          <button
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => onChange?.([...parameters, emptyParam()])}
          >
            <Plus className="h-3 w-3" /> Добавить строку
          </button>
        </div>
      )}
    </div>
  )
}
