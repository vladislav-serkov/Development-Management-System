import { X, Plus, FileText, Table as TableIcon } from "lucide-react"
import type { LogicStep, MessageField, GenericTable } from "@/types/api"

interface LogicTreeProps {
  steps: LogicStep[]
  isEditing?: boolean
  onChange?: (steps: LogicStep[]) => void
  onDocRefClick?: (name: string) => void
}

function hasAnyCardinality(fields: MessageField[]): boolean {
  return fields.some(f => f.cardinality != null || (f.children && hasAnyCardinality(f.children)))
}

function emptyStep(number: string): LogicStep {
  return { number, text: "", children: [], message_mapping: null, reference_tables: [], external_doc_refs: [] }
}

function emptyReferenceTable(): GenericTable {
  return { caption: null, headers: ["", ""], rows: [["", ""]] }
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
    example: null,
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
                placeholder="элемент"
                onChange={(e) => updateField(i, { ...field, element: e.target.value })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.field_type ?? ""}
                placeholder="тип"
                onChange={(e) => updateField(i, { ...field, field_type: e.target.value || null })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                type="checkbox"
                checked={field.required ?? false}
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
                placeholder="описание"
                onChange={(e) => updateField(i, { ...field, description: e.target.value || null })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs"
                value={field.source ?? ""}
                placeholder="источник"
                onChange={(e) => updateField(i, { ...field, source: e.target.value || null })}
              />
            </td>
            <td className="px-2 py-1">
              <input
                className="bg-transparent border-b border-border outline-none w-full text-xs font-mono"
                value={field.example ?? ""}
                placeholder="пример"
                onChange={(e) => updateField(i, { ...field, example: e.target.value || null })}
              />
            </td>
            <td className="px-1 py-1">
              <div className="flex items-center gap-0.5">
                <button
                  className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                  title="Добавить дочернее поле"
                  onClick={() => addChild(i)}
                >
                  <Plus className="h-3 w-3" />
                </button>
                <button
                  className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                  title="Удалить"
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
  )
}

function EditableReferenceTable({
  table,
  onChange,
  onDelete,
}: {
  table: GenericTable
  onChange: (updated: GenericTable) => void
  onDelete: () => void
}) {
  const headers = table.headers ?? []
  const rows = table.rows ?? []

  const updateCaption = (v: string) => onChange({ ...table, caption: v || null })

  const updateHeader = (i: number, v: string) => {
    onChange({ ...table, headers: headers.map((h, idx) => (idx === i ? v : h)) })
  }

  const updateCell = (ri: number, ci: number, v: string) => {
    const nextRows = rows.map((r, idx) => {
      if (idx !== ri) return r
      const nextRow = [...r]
      nextRow[ci] = v
      return nextRow
    })
    onChange({ ...table, rows: nextRows })
  }

  const addColumn = () => {
    onChange({
      ...table,
      headers: [...headers, ""],
      rows: rows.map((r) => [...r, ""]),
    })
  }

  const removeColumn = (i: number) => {
    if (headers.length <= 1) return
    onChange({
      ...table,
      headers: headers.filter((_, idx) => idx !== i),
      rows: rows.map((r) => r.filter((_, idx) => idx !== i)),
    })
  }

  const addRow = () => {
    onChange({ ...table, rows: [...rows, headers.map(() => "")] })
  }

  const removeRow = (i: number) => {
    onChange({ ...table, rows: rows.filter((_, idx) => idx !== i) })
  }

  return (
    <div className="mt-2 ml-8 border rounded-md overflow-hidden">
      <div className="flex items-center gap-2 bg-muted/30 px-2 py-1.5">
        <TableIcon className="h-3 w-3 text-muted-foreground shrink-0" />
        <input
          className="text-xs bg-transparent border-b border-border outline-none flex-1"
          value={table.caption ?? ""}
          placeholder="Заголовок таблицы (необязательно)"
          onChange={(e) => updateCaption(e.target.value)}
        />
        <button
          className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors shrink-0"
          title="Удалить таблицу"
          onClick={onDelete}
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      <table className="w-full text-xs">
        <thead className="bg-muted/50">
          <tr>
            {headers.map((h, i) => (
              <th key={i} className="text-left px-2 py-1 font-medium">
                <div className="flex items-center gap-1">
                  <input
                    className="bg-transparent border-b border-border outline-none w-full text-xs font-medium"
                    value={h}
                    placeholder="колонка"
                    onChange={(e) => updateHeader(i, e.target.value)}
                  />
                  {headers.length > 1 && (
                    <button
                      className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0"
                      title="Удалить колонку"
                      onClick={() => removeColumn(i)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </th>
            ))}
            <th className="w-8">
              <button
                className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                title="Добавить колонку"
                onClick={addColumn}
              >
                <Plus className="h-3 w-3" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-t border-muted">
              {headers.map((_, ci) => (
                <td key={ci} className="px-2 py-1 align-top">
                  <textarea
                    className="bg-transparent border-b border-border outline-none w-full text-xs resize-none"
                    rows={1}
                    value={row[ci] ?? ""}
                    placeholder="значение"
                    onChange={(e) => updateCell(ri, ci, e.target.value)}
                  />
                </td>
              ))}
              <td className="px-1 py-1 align-top">
                <button
                  className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                  title="Удалить строку"
                  onClick={() => removeRow(ri)}
                >
                  <X className="h-3 w-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="p-1.5 border-t">
        <button
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={addRow}
        >
          <Plus className="h-3 w-3" /> Добавить строку
        </button>
      </div>
    </div>
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
        <td className="px-2 py-1">{field.required === null || field.required === undefined ? "–" : field.required ? "Да" : "Нет"}</td>
        {showCardinality && <td className="px-2 py-1 text-muted-foreground font-mono">{field.cardinality ?? "–"}</td>}
        <td className="px-2 py-1 text-muted-foreground">{field.description ?? "-"}</td>
        <td className="px-2 py-1 text-muted-foreground">{field.source ?? "-"}</td>
        <td className="px-2 py-1 text-muted-foreground font-mono">{field.example ?? "-"}</td>
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

  const refTables = step.reference_tables ?? []
  const updateRefTable = (i: number, updated: GenericTable) => {
    onUpdate({ ...step, reference_tables: refTables.map((t, idx) => (idx === i ? updated : t)) })
  }
  const deleteRefTable = (i: number) => {
    onUpdate({ ...step, reference_tables: refTables.filter((_, idx) => idx !== i) })
  }
  const addRefTable = () => {
    onUpdate({ ...step, reference_tables: [...refTables, emptyReferenceTable()] })
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
          placeholder="Описание шага..."
        />
        <div className="flex items-center gap-1 shrink-0 pt-1">
          <button
            className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs"
            title="Добавить вложенный шаг"
            onClick={addSubStep}
          >
            <Plus className="h-3 w-3" />
          </button>
          <button
            className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title="Удалить шаг"
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
                <th className="text-left px-2 py-1 font-medium">Элемент</th>
                <th className="text-left px-2 py-1 font-medium">Тип</th>
                <th className="text-left px-2 py-1 font-medium">Обяз.</th>
                {showCardinality && <th className="text-left px-2 py-1 font-medium">Кардинальность</th>}
                <th className="text-left px-2 py-1 font-medium">Описание</th>
                <th className="text-left px-2 py-1 font-medium">Источник</th>
                <th className="text-left px-2 py-1 font-medium">Пример</th>
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

      {/* Reference tables (editable) */}
      {refTables.map((t, i) => (
        <EditableReferenceTable
          key={`ref-${i}`}
          table={t}
          onChange={(updated) => updateRefTable(i, updated)}
          onDelete={() => deleteRefTable(i)}
        />
      ))}
      <div className="ml-8 mt-1">
        <button
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={addRefTable}
        >
          <Plus className="h-3 w-3" /> Добавить справочную таблицу
        </button>
      </div>

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

function LogicStepNode({ step, level, onDocRefClick }: { step: LogicStep; level: number; onDocRefClick?: (name: string) => void }) {
  return (
    <div className={level === 0 ? "rounded-xl border border-border/70 bg-background px-4 py-3" : ""}>
      <div className="flex items-start gap-3 py-1">
        <span className="min-w-[2.5rem] shrink-0 rounded-md bg-muted px-2 py-1 text-center font-mono text-sm text-muted-foreground">
          {step.number}
        </span>
        <span className="pt-1 text-sm leading-6">{step.text}</span>
      </div>
      <DocRefChips refs={step.external_doc_refs ?? []} onClick={onDocRefClick} />
      {step.message_mapping && step.message_mapping.length > 0 && (() => {
        const showCardinality = hasAnyCardinality(step.message_mapping)
        return (
          <div className="mt-3 ml-14 overflow-hidden rounded-xl border border-border/70">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-2 py-1 font-medium">Элемент</th>
                  <th className="text-left px-2 py-1 font-medium">Тип</th>
                  <th className="text-left px-2 py-1 font-medium">Обяз.</th>
                  {showCardinality && <th className="text-left px-2 py-1 font-medium">Кардинальность</th>}
                  <th className="text-left px-2 py-1 font-medium">Описание</th>
                  <th className="text-left px-2 py-1 font-medium">Источник</th>
                  <th className="text-left px-2 py-1 font-medium">Пример</th>
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
      {(step.reference_tables ?? []).map((t, i) => (
        <ReferenceTableView key={`ref-${i}`} table={t} />
      ))}
      {step.children.length > 0 && (
        <div className="mt-3 ml-6 space-y-3 border-l-2 border-muted pl-4">
          {step.children.map((child, i) => (
            <LogicStepNode key={i} step={child} level={level + 1} onDocRefClick={onDocRefClick} />
          ))}
        </div>
      )}
    </div>
  )
}

export function LogicTree({ steps, isEditing = false, onChange, onDocRefClick }: LogicTreeProps) {
  if (!isEditing && steps.length === 0) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-10 text-center">
        <p className="text-sm font-medium">Шаги обработки не заполнены</p>
        <p className="mt-2 text-xs text-muted-foreground">После извлечения или ручного редактирования здесь появится последовательность бизнес-логики.</p>
      </div>
    )
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
      <div className="space-y-3">
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
    <div className="space-y-3">
      {steps.map((step, i) => (
        <LogicStepNode key={i} step={step} level={0} onDocRefClick={onDocRefClick} />
      ))}
    </div>
  )
}
