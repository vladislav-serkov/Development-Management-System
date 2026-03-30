import { X, Plus } from "lucide-react"
import type { LogicStep, MessageField } from "@/types/api"

interface LogicTreeProps {
  steps: LogicStep[]
  isEditing?: boolean
  onChange?: (steps: LogicStep[]) => void
}

function hasAnyCardinality(fields: MessageField[]): boolean {
  return fields.some(f => f.cardinality != null || (f.children && hasAnyCardinality(f.children)))
}

function emptyStep(number: string): LogicStep {
  return { number, text: "", children: [], message_mapping: null }
}

function emptyField(): MessageField {
  return {
    element: "",
    parent: null,
    field_type: null,
    required: false,
    cardinality: null,
    is_collection: false,
    description: null,
    source: null,
    children: [],
  }
}

// Editable mapping row (flat — not recursive for simplicity, children treated as nested rows)
function EditableMappingRows({
  fields,
  depth,
  showCardinality,
  onChange,
}: {
  fields: MessageField[]
  depth: number
  showCardinality: boolean
  onChange: (updated: MessageField[]) => void
}) {
  const updateField = (i: number, updated: MessageField) => {
    onChange(fields.map((f, idx) => (idx === i ? updated : f)))
  }
  const deleteField = (i: number) => {
    onChange(fields.filter((_, idx) => idx !== i))
  }
  const addChild = (i: number) => {
    onChange(
      fields.map((f, idx) =>
        idx === i ? { ...f, children: [...(f.children ?? []), emptyField()] } : f
      )
    )
  }

  return (
    <>
      {fields.map((field, i) => (
        <>
          <tr key={`emr-${depth}-${i}`} className="border-t border-muted">
            <td className="px-2 py-1 font-mono" style={{ paddingLeft: `${0.5 + depth * 1}rem` }}>
              <input
                className="font-mono bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.element}
                placeholder="element"
                onChange={(e) => updateField(i, { ...field, element: e.target.value })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.field_type ?? ""}
                placeholder="type"
                onChange={(e) => updateField(i, { ...field, field_type: e.target.value || null })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                type="checkbox"
                checked={field.required}
                onChange={(e) => updateField(i, { ...field, required: e.target.checked })}
              />
            </td>
            {showCardinality && (
              <td className="px-2 py-1">
                <input
                  className="bg-transparent border-b border-border outline-none w-full text-xs font-mono"
                  value={field.cardinality ?? ""}
                  placeholder="1..N"
                  onChange={(e) => updateField(i, { ...field, cardinality: e.target.value || null })}
                />
              </td>
            )}
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.description ?? ""}
                placeholder="description"
                onChange={(e) => updateField(i, { ...field, description: e.target.value || null })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.source ?? ""}
                placeholder="source"
                onChange={(e) => updateField(i, { ...field, source: e.target.value || null })}
              />
            </td>
            <td className="px-1 py-1">
              <div className="flex items-center gap-0.5">
                <button
                  className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                  title="Add child"
                  onClick={() => addChild(i)}
                >
                  <Plus className="h-3 w-3" />
                </button>
                <button
                  className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                  title="Delete"
                  onClick={() => deleteField(i)}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </td>
          </tr>
          {(field.children ?? []).length > 0 && (
            <EditableMappingRows
              fields={field.children}
              depth={depth + 1}
              showCardinality={showCardinality}
              onChange={(updatedChildren) =>
                updateField(i, { ...field, children: updatedChildren })
              }
            />
          )}
        </>
      ))}
    </>
  )
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

function EditableLogicStepNode({
  step,
  level,
  onUpdate,
  onDelete,
}: {
  step: LogicStep
  level: number
  onUpdate: (updated: LogicStep) => void
  onDelete: () => void
}) {
  const mappings = step.message_mapping ?? []
  const showCardinality = hasAnyCardinality(mappings)

  const addSubStep = () => {
    const nextNumber = `${step.number}.${step.children.length + 1}`
    onUpdate({ ...step, children: [...step.children, emptyStep(nextNumber)] })
  }

  const updateChild = (i: number, updated: LogicStep) => {
    onUpdate({ ...step, children: step.children.map((c, idx) => (idx === i ? updated : c)) })
  }

  const deleteChild = (i: number) => {
    onUpdate({ ...step, children: step.children.filter((_, idx) => idx !== i) })
  }

  const addMappingRow = () => {
    onUpdate({ ...step, message_mapping: [...mappings, emptyField()] })
  }

  const updateMappings = (updated: MessageField[]) => {
    onUpdate({ ...step, message_mapping: updated })
  }

  return (
    <div className="group">
      <div className="flex items-start gap-2 py-1">
        <input
          className="font-mono text-muted-foreground shrink-0 text-sm bg-transparent border-b border-border outline-none w-16"
          value={step.number}
          onChange={(e) => onUpdate({ ...step, number: e.target.value })}
        />
        <textarea
          className="text-sm bg-transparent border border-border rounded px-2 py-1 outline-none flex-1 resize-none min-h-[2rem]"
          value={step.text}
          rows={2}
          onChange={(e) => onUpdate({ ...step, text: e.target.value })}
          placeholder="Step description..."
        />
        <div className="flex items-center gap-1 shrink-0 pt-1">
          <button
            className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs"
            title="Add sub-step"
            onClick={addSubStep}
          >
            <Plus className="h-3 w-3" />
          </button>
          <button
            className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title="Delete step"
            onClick={onDelete}
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Message mapping table (editable) */}
      {(mappings.length > 0 || step.has_detailed_mapping) && (
        <div className="mt-2 ml-8 border rounded-md overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-2 py-1 font-medium">Element</th>
                <th className="text-left px-2 py-1 font-medium">Type</th>
                <th className="text-left px-2 py-1 font-medium">Req</th>
                {showCardinality && <th className="text-left px-2 py-1 font-medium">Cardinality</th>}
                <th className="text-left px-2 py-1 font-medium">Description</th>
                <th className="text-left px-2 py-1 font-medium">Source</th>
                <th className="w-12"></th>
              </tr>
            </thead>
            <tbody>
              <EditableMappingRows
                fields={mappings}
                depth={0}
                showCardinality={showCardinality}
                onChange={updateMappings}
              />
            </tbody>
          </table>
          <div className="p-1.5 border-t">
            <button
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              onClick={addMappingRow}
            >
              <Plus className="h-3 w-3" /> Добавить поле
            </button>
          </div>
        </div>
      )}

      {/* Add mapping table button if none exists */}
      {mappings.length === 0 && !step.has_detailed_mapping && (
        <div className="ml-8 mt-1">
          <button
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            onClick={addMappingRow}
          >
            <Plus className="h-3 w-3" /> Добавить маппинг
          </button>
        </div>
      )}

      {/* Children steps */}
      {step.children.length > 0 && (
        <div className="ml-6 border-l-2 border-muted pl-4 mt-1 space-y-1">
          {step.children.map((child, i) => (
            <EditableLogicStepNode
              key={i}
              step={child}
              level={level + 1}
              onUpdate={(updated) => updateChild(i, updated)}
              onDelete={() => deleteChild(i)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function LogicStepNode({ step, level }: { step: LogicStep; level: number }) {
  return (
    <div>
      <div className="flex items-start gap-2 py-1">
        <span className="font-mono text-muted-foreground shrink-0 text-sm min-w-[2.5rem]">
          {step.number}
        </span>
        <span className="text-sm">{step.text}</span>
      </div>
      {step.message_mapping && step.message_mapping.length > 0 && (() => {
        const showCardinality = hasAnyCardinality(step.message_mapping)
        return (
          <div className="mt-2 ml-8 border rounded-md overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-2 py-1 font-medium">Element</th>
                  <th className="text-left px-2 py-1 font-medium">Type</th>
                  <th className="text-left px-2 py-1 font-medium">Req</th>
                  {showCardinality && <th className="text-left px-2 py-1 font-medium">Cardinality</th>}
                  <th className="text-left px-2 py-1 font-medium">Description</th>
                  <th className="text-left px-2 py-1 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {step.message_mapping.map((field, idx) => (
                  <MappingRow key={idx} field={field} depth={0} showCardinality={showCardinality} />
                ))}
              </tbody>
            </table>
          </div>
        )
      })()}
      {step.children.length > 0 && (
        <div className="ml-6 border-l-2 border-muted pl-4 mt-1 space-y-1">
          {step.children.map((child, i) => (
            <LogicStepNode key={i} step={child} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export function LogicTree({ steps, isEditing = false, onChange }: LogicTreeProps) {
  if (!isEditing && steps.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет шагов обработки</p>
  }

  if (isEditing) {
    const updateStep = (i: number, updated: LogicStep) => {
      onChange?.(steps.map((s, idx) => (idx === i ? updated : s)))
    }
    const deleteStep = (i: number) => {
      onChange?.(steps.filter((_, idx) => idx !== i))
    }
    const addStep = () => {
      onChange?.([...steps, emptyStep(String(steps.length + 1))])
    }

    return (
      <div className="space-y-2">
        {steps.map((step, i) => (
          <EditableLogicStepNode
            key={i}
            step={step}
            level={0}
            onUpdate={(updated) => updateStep(i, updated)}
            onDelete={() => deleteStep(i)}
          />
        ))}
        <button
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-2"
          onClick={addStep}
        >
          <Plus className="h-3 w-3" /> Добавить шаг
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {steps.map((step, i) => (
        <LogicStepNode key={i} step={step} level={0} />
      ))}
    </div>
  )
}
