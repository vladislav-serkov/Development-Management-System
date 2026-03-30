export type AgentName = "extraction" | "gaps" | "test_cases" | "bugs" | "enrichment"
export type RulesData = Record<AgentName, string>

export const EMPTY_RULES: RulesData = { extraction: "", gaps: "", test_cases: "", bugs: "", enrichment: "" }

export async function fetchGlobalRules(): Promise<RulesData> {
  const res = await fetch("/api/rules/global")
  if (!res.ok) throw new Error(`Failed to fetch global rules: ${res.status}`)
  return res.json()
}

export async function saveGlobalRules(rules: RulesData): Promise<RulesData> {
  const res = await fetch("/api/rules/global", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  })
  if (!res.ok) throw new Error(`Failed to save global rules: ${res.status}`)
  return res.json()
}

export async function fetchProjectRules(projectSlug: string): Promise<RulesData> {
  const res = await fetch(`/api/rules/projects/${projectSlug}`)
  if (!res.ok) throw new Error(`Failed to fetch project rules: ${res.status}`)
  return res.json()
}

export async function saveProjectRules(projectSlug: string, rules: RulesData): Promise<RulesData> {
  const res = await fetch(`/api/rules/projects/${projectSlug}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  })
  if (!res.ok) throw new Error(`Failed to save project rules: ${res.status}`)
  return res.json()
}
