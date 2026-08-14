import type { SpecField, SpecTable } from "@/types/api"

export function countSpecFields(tables: SpecTable[] | undefined): number {
  const walk = (fields: SpecField[]): number =>
    fields.reduce((acc, f) => acc + 1 + walk(f.children ?? []), 0)
  return (tables ?? []).reduce((acc, t) => acc + walk(t.fields), 0)
}
