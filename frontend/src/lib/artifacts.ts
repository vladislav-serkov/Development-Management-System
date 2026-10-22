/** Type badges of test-case artifacts — same shape as MethodBadge, own hue per kind. */
export const ARTIFACT_BADGE = {
  KAFKA: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  SQL: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",
  MOCK: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
} as const

export function prettyJsonOrRaw(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

/** Feature name without the leading HTTP method — MethodBadge already shows it. */
export function stripMethodPrefix(name: string, method: string | null) {
  if (method && name.toUpperCase().startsWith(`${method.toUpperCase()} `)) return name.slice(method.length + 1)
  return name
}
