import { useState, useEffect } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { useUIStore } from "@/stores/uiStore"
import { useGlobalRules, useSaveGlobalRules, useProjectRules, useSaveProjectRules } from "@/hooks/useRules"
import { useProjects } from "@/hooks/useDocuments"
import type { AgentName, RulesData } from "@/api/rules"

const AGENT_TABS: { id: AgentName; label: string }[] = [
  { id: "extraction", label: "Extraction" },
  { id: "gaps", label: "Gaps" },
  { id: "test_cases", label: "Test Cases" },
  { id: "bugs", label: "Bugs" },
  { id: "enrichment", label: "Enrichment" },
]

const EMPTY_RULES: RulesData = { extraction: "", gaps: "", test_cases: "", bugs: "", enrichment: "" }

export default function RulesPage() {
  const goHome = useUIStore((s) => s.goHome)

  // Global rules
  const { data: globalRules } = useGlobalRules()
  const saveGlobal = useSaveGlobalRules()
  const [globalDraft, setGlobalDraft] = useState<RulesData | null>(null)

  // Project selection — dropdown of all projects
  const { data: projects } = useProjects()
  const [selectedProjectSlug, setSelectedProjectSlug] = useState<string | null>(null)

  // Project rules (loaded when project selected)
  const { data: projectRules } = useProjectRules(selectedProjectSlug)
  const saveProject = useSaveProjectRules(selectedProjectSlug ?? "")
  const [projectDraft, setProjectDraft] = useState<RulesData | null>(null)

  // Reset project draft when project changes
  useEffect(() => { setProjectDraft(null) }, [selectedProjectSlug])

  // Effective values: draft if editing, otherwise server data
  const effectiveGlobal = globalDraft ?? globalRules ?? EMPTY_RULES
  const effectiveProject = projectDraft ?? projectRules ?? EMPTY_RULES

  const handleGlobalChange = (agent: AgentName, value: string) => {
    setGlobalDraft(prev => ({ ...(prev ?? globalRules ?? EMPTY_RULES), [agent]: value }))
  }

  const handleProjectChange = (agent: AgentName, value: string) => {
    setProjectDraft(prev => ({ ...(prev ?? projectRules ?? EMPTY_RULES), [agent]: value }))
  }

  const handleSaveGlobal = () => {
    if (globalDraft) {
      saveGlobal.mutate(globalDraft, { onSuccess: () => setGlobalDraft(null) })
    }
  }

  const handleSaveProject = () => {
    if (projectDraft && selectedProjectSlug) {
      saveProject.mutate(projectDraft, { onSuccess: () => setProjectDraft(null) })
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b px-6 py-4 flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={goHome}>← Back</Button>
        <h1 className="text-xl font-semibold">Prompt Rules</h1>
      </div>

      <div className="max-w-4xl mx-auto p-6">
        <Tabs defaultValue="extraction">
          <TabsList>
            {AGENT_TABS.map(tab => (
              <TabsTrigger key={tab.id} value={tab.id}>{tab.label}</TabsTrigger>
            ))}
          </TabsList>

          {AGENT_TABS.map(tab => (
            <TabsContent key={tab.id} value={tab.id} className="space-y-6 mt-4">
              {/* Global Rules Section */}
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Global Rules</h3>
                <p className="text-xs text-muted-foreground">Applied to all projects for the {tab.label} agent</p>
                <Textarea
                  value={effectiveGlobal[tab.id]}
                  onChange={(e) => handleGlobalChange(tab.id, e.target.value)}
                  placeholder={`Enter global rules for ${tab.label} agent...`}
                  rows={6}
                />
                <Button
                  size="sm"
                  onClick={handleSaveGlobal}
                  disabled={!globalDraft || saveGlobal.isPending}
                >
                  {saveGlobal.isPending ? "Saving..." : "Save Global Rules"}
                </Button>
              </div>

              {/* Project Rules Section */}
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Project Rules</h3>
                <select
                  className="border rounded px-3 py-1.5 text-sm bg-background"
                  value={selectedProjectSlug ?? ""}
                  onChange={(e) => {
                    setSelectedProjectSlug(e.target.value || null)
                    setProjectDraft(null)
                  }}
                >
                  <option value="">Select a project...</option>
                  {(projects ?? []).map((p) => (
                    <option key={p.slug} value={p.slug}>{p.name}</option>
                  ))}
                </select>

                {selectedProjectSlug ? (
                  <>
                    <Textarea
                      value={effectiveProject[tab.id]}
                      onChange={(e) => handleProjectChange(tab.id, e.target.value)}
                      placeholder={`Enter project-specific rules for ${tab.label} agent...`}
                      rows={6}
                    />
                    <Button
                      size="sm"
                      onClick={handleSaveProject}
                      disabled={!projectDraft || saveProject.isPending}
                    >
                      {saveProject.isPending ? "Saving..." : "Save Project Rules"}
                    </Button>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground italic">Select a project to edit project-scoped rules</p>
                )}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  )
}
