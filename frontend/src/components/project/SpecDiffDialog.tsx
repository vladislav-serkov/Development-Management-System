import { Minus, Plus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { DocumentResponse, FeatureDiff, SpecTableDiff } from "@/types/api"

interface SpecDiffDialogProps {
  doc: DocumentResponse | null
  onClose: () => void
}

/** "Что изменилось" — renders the deterministic diff of the last re-extraction. */
export function SpecDiffDialog({ doc, onClose }: SpecDiffDialogProps) {
  const diff = doc?.last_diff
  return (
    <Dialog open={!!doc} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Что изменилось в спеке</DialogTitle>
          <DialogDescription>
            {doc?.filename}
            {diff?.old_version && diff?.new_version
              ? ` — версия ${diff.old_version} → ${diff.new_version}`
              : ""}
          </DialogDescription>
        </DialogHeader>

        {diff && !diff.material && (
          <p className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
            {diff.source_unchanged
              ? "Текст страницы не изменился — изменений в спеке нет. Отличия ниже — разночтения повторного извлечения, на анализ они не влияют."
              : <>Содержательных изменений нет: структуры фич идентичны
                {diff.changed.some((c) => c.summary_changed) ? " (изменились только формулировки описаний)" : ""}.</>}
          </p>
        )}

        {diff && (
          <div className="space-y-4 text-sm">
            {diff.added.length > 0 && (
              <DiffSection title="Новые фичи">
                {diff.added.map((name) => (
                  <li key={name} className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
                    <Plus className="h-3.5 w-3.5 shrink-0" /> <span className="font-mono text-[0.8125rem]">{name}</span>
                  </li>
                ))}
              </DiffSection>
            )}

            {diff.removed.length > 0 && (
              <DiffSection title="Пропали из спеки (помечены как orphaned)">
                {diff.removed.map((name) => (
                  <li key={name} className="flex items-center gap-1.5 text-red-700 dark:text-red-400">
                    <Minus className="h-3.5 w-3.5 shrink-0" /> <span className="font-mono text-[0.8125rem]">{name}</span>
                  </li>
                ))}
              </DiffSection>
            )}

            {diff.changed.filter((c) => c.material).map((change) => (
              <FeatureDiffBlock key={change.name} change={change} />
            ))}

            {diff.changed.some((c) => !c.material) && (
              <p className="text-xs text-muted-foreground">
                Непринципиальные отличия (формулировки, нумерация, имена): {diff.changed.filter((c) => !c.material).map((c) => c.display_name ?? c.name).join(", ")}
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function DiffSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <ul className="space-y-1">{children}</ul>
    </section>
  )
}

function FeatureDiffBlock({ change }: { change: FeatureDiff }) {
  return (
    <section className="rounded-xl border border-border/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium">{change.display_name ?? change.name}</p>
        <Badge variant="outline" className="text-[0.6875rem] text-amber-700 dark:text-amber-400">изменена</Badge>
      </div>

      <div className="mt-2 space-y-3">
        {change.identity.length > 0 && (
          <ul className="space-y-1">
            {change.identity.map((id) => (
              <li key={id.field} className="text-[0.8125rem]">
                <span className="text-muted-foreground">{id.field}:</span>{" "}
                <OldNew old={id.old} new_={id.new} />
              </li>
            ))}
          </ul>
        )}

        {change.tables.map((table, i) => (
          <TableDiffBlock key={i} table={table} />
        ))}

        {change.steps && (change.steps.added.length > 0 || change.steps.removed.length > 0 || change.steps.changed.length > 0 || (change.steps.renumbered?.length ?? 0) > 0 || (change.steps.resliced?.length ?? 0) > 0) && (
          <div className="space-y-1 text-[0.8125rem]">
            <p className="text-xs font-semibold text-muted-foreground">Шаги логики</p>
            {change.steps.added.map((s) => (
              <p key={`a${s.number}`} className="text-emerald-700 dark:text-emerald-400">+ шаг {s.number}: {s.text}</p>
            ))}
            {change.steps.removed.map((s) => (
              <p key={`r${s.number}`} className="text-red-700 line-through dark:text-red-400">шаг {s.number}: {s.text}</p>
            ))}
            {change.steps.changed.map((s) => (
              <div key={`c${s.number}`}>
                <p className="text-muted-foreground">~ шаг {s.number}:</p>
                <p className="pl-4 text-red-700/80 line-through dark:text-red-400/80">{s.old_text}</p>
                <p className="pl-4 text-emerald-700 dark:text-emerald-400">{s.new_text}</p>
              </div>
            ))}
            {(change.steps.renumbered ?? []).map((s) => (
              <p key={`n${s.old_number}`} className="text-muted-foreground">
                шаг {s.old_number} → {s.new_number} (текст не менялся)
              </p>
            ))}
            {(change.steps.resliced ?? []).map((s) => (
              <p key={`s${s.number}`} className="text-muted-foreground">
                шаг {s.number} разбит на подшаги иначе (текст не менялся)
              </p>
            ))}
          </div>
        )}

        {change.dependencies && (change.dependencies.added.length > 0 || change.dependencies.removed.length > 0 || (change.dependencies.renamed?.length ?? 0) > 0) && (
          <div className="space-y-1 text-[0.8125rem]">
            <p className="text-xs font-semibold text-muted-foreground">Зависимости</p>
            {change.dependencies.added.map((d) => (
              <p key={`a${d.type}${d.name}`} className="text-emerald-700 dark:text-emerald-400">+ {d.type}: {d.name}</p>
            ))}
            {change.dependencies.removed.map((d) => (
              <p key={`r${d.type}${d.name}`} className="text-red-700 dark:text-red-400">− {d.type}: {d.name}</p>
            ))}
            {(change.dependencies.renamed ?? []).map((d) => (
              <p key={`n${d.type}${d.old_name}`} className="text-muted-foreground">
                {d.type}: {d.old_name} → {d.new_name} (та же сущность)
              </p>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function TableDiffBlock({ table }: { table: SpecTableDiff }) {
  const label = table.caption ? `${table.section} · ${table.caption}` : table.section
  if (table.table) {
    return (
      <p className={table.table === "added" ? "text-[0.8125rem] text-emerald-700 dark:text-emerald-400" : "text-[0.8125rem] text-red-700 dark:text-red-400"}>
        {table.table === "added" ? "+ добавлена таблица" : "− удалена таблица"}: {label}
      </p>
    )
  }
  return (
    <div className="space-y-1 text-[0.8125rem]">
      <p className="text-xs font-semibold text-muted-foreground">{label}</p>
      {(table.added_fields ?? []).map((f) => (
        <p key={`a${f}`} className="font-mono text-emerald-700 dark:text-emerald-400">+ {f}</p>
      ))}
      {(table.removed_fields ?? []).map((f) => (
        <p key={`r${f}`} className="font-mono text-red-700 line-through dark:text-red-400">{f}</p>
      ))}
      {(table.changed_fields ?? []).map((f) => (
        <div key={`c${f.name}`}>
          <p className="font-mono">~ {f.name}</p>
          <ul className="pl-4">
            {f.changes.map((c) => (
              <li key={c.column}>
                <span className="text-muted-foreground">{c.column}:</span> <OldNew old={c.old} new_={c.new} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function OldNew({ old, new_ }: { old: string; new_: string }) {
  return (
    <>
      <span className="text-red-700/80 line-through dark:text-red-400/80">{old || "∅"}</span>
      {" → "}
      <span className="text-emerald-700 dark:text-emerald-400">{new_ || "∅"}</span>
    </>
  )
}
