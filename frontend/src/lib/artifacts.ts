/** Type badges of test-case artifacts — same shape as MethodBadge, own hue per kind. */
export const ARTIFACT_BADGE = {
  KAFKA: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  SQL: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",
  MOCK: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  DSL: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
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

type TitledFeature = { name: string; method?: string | null; type?: string | null; display_name?: string | null }

/** A REST endpoint or a Kafka consumer is called by its path / topic; everything
 *  else (scheduled tasks) by its human-readable title from the spec. */
function isNamedByEndpoint(feature: TitledFeature) {
  return feature.type === "rest_endpoint" || feature.type === "kafka_consumer"
}

/** What a feature is called on screen (the method is shown by MethodBadge). */
export function featureTitle(feature: TitledFeature) {
  const plain = stripMethodPrefix(feature.name, feature.method ?? null)
  return isNamedByEndpoint(feature) ? plain : feature.display_name ?? plain
}

/** The spec's own words for a feature that is called by its path / topic. */
export function featureSubtitle(feature: TitledFeature) {
  if (!isNamedByEndpoint(feature) || !feature.display_name) return null
  return feature.display_name === featureTitle(feature) ? null : feature.display_name
}
