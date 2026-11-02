import type { DependencyType } from "@/types/api"

export type FeatureTab = "logic" | "gaps" | "tests" | "bugs"

const DEFAULT_FEATURE_TAB: FeatureTab = "logic"
const FEATURE_TABS: FeatureTab[] = ["logic", "gaps", "tests", "bugs"]

function encodeSegment(value: string) {
  return encodeURIComponent(value)
}

export function isFeatureTab(value: string | undefined): value is FeatureTab {
  return FEATURE_TABS.includes(value as FeatureTab)
}

export function homePath() {
  return "/"
}

export function rulesPath() {
  return "/rules"
}

export function projectPath(projectSlug: string) {
  return `/projects/${encodeSegment(projectSlug)}`
}

export function tasksPath(projectSlug: string) {
  return `${projectPath(projectSlug)}/tasks`
}

export function featurePath(projectSlug: string, featureName: string, tab: FeatureTab = DEFAULT_FEATURE_TAB) {
  const base = `${projectPath(projectSlug)}/features/${encodeSegment(featureName)}`
  return tab === DEFAULT_FEATURE_TAB ? base : `${base}/${tab}`
}

export function dependencyPath(projectSlug: string, depType: DependencyType, depName: string) {
  return `${projectPath(projectSlug)}/dependencies/${depType}/${encodeSegment(depName)}`
}
