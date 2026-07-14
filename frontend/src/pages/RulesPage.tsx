import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useGlobalRules, useProjectRules, useSaveGlobalRules, useSaveProjectRules } from "@/hooks/useRules"
import { useProjects } from "@/hooks/useDocuments"
import { homePath } from "@/lib/routes"
import { EMPTY_RULES, type AgentName, type RulesData } from "@/api/rules"

const AGENT_TABS: { id: AgentName; label: string }[] = [
  { id: "extraction", label: "Извлечение" },
  { id: "gaps", label: "Пробелы" },
  { id: "test_cases", label: "Тест-кейсы" },
  { id: "bugs", label: "Баги" },
  { id: "enrichment", label: "Обогащение" },
]

export default function RulesPage() {
  const navigate = useNavigate()
  const { data: globalRules } = useGlobalRules()
  const saveGlobal = useSaveGlobalRules()
  const [globalDraft, setGlobalDraft] = useState<RulesData | null>(null)

  const { data: projects } = useProjects()
  const [selectedProjectSlug, setSelectedProjectSlug] = useState<string | null>(null)
  const { data: projectRules } = useProjectRules(selectedProjectSlug)
  const saveProject = useSaveProjectRules(selectedProjectSlug ?? "")
  const [projectDraft, setProjectDraft] = useState<RulesData | null>(null)

  const effectiveGlobal = globalDraft ?? globalRules ?? EMPTY_RULES
  const effectiveProject = projectDraft ?? projectRules ?? EMPTY_RULES

  const handleGlobalChange = (agent: AgentName, value: string) => {
    setGlobalDraft((prev) => ({ ...(prev ?? globalRules ?? EMPTY_RULES), [agent]: value }))
  }

  const handleProjectChange = (agent: AgentName, value: string) => {
    setProjectDraft((prev) => ({ ...(prev ?? projectRules ?? EMPTY_RULES), [agent]: value }))
  }

  const handleSaveGlobal = () => {
    if (!globalDraft) return
    saveGlobal.mutate(globalDraft, { onSuccess: () => setGlobalDraft(null) })
  }

  const handleSaveProject = () => {
    if (!projectDraft || !selectedProjectSlug) return
    saveProject.mutate(projectDraft, { onSuccess: () => setProjectDraft(null) })
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate(homePath())}>← Назад</Button>
          <div>
            <h1 className="text-xl font-semibold">Правила агентов</h1>
            <p className="text-sm text-muted-foreground">Глобальные и проектные инструкции для генерации артефактов.</p>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-5xl p-6">
        <Tabs defaultValue="extraction" className="gap-6">
          <TabsList className="flex-wrap">
            {AGENT_TABS.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id}>{tab.label}</TabsTrigger>
            ))}
          </TabsList>

          {AGENT_TABS.map((tab) => (
            <TabsContent key={tab.id} value={tab.id} className="space-y-6">
              <Card className="border border-border/70">
                <CardHeader>
                  <CardTitle>Глобальные правила</CardTitle>
                  <CardDescription>Применяются ко всем проектам для агента «{tab.label}».</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Textarea
                    value={effectiveGlobal[tab.id]}
                    onChange={(e) => handleGlobalChange(tab.id, e.target.value)}
                    placeholder={`Введите глобальные правила для агента «${tab.label}»...`}
                    rows={10}
                    className="font-mono text-sm"
                  />
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-muted-foreground">
                      {globalDraft ? "Есть несохраненные изменения" : "Изменений нет"}
                    </p>
                    <Button size="sm" onClick={handleSaveGlobal} disabled={!globalDraft || saveGlobal.isPending}>
                      {saveGlobal.isPending ? "Сохранение..." : "Сохранить глобальные правила"}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Card className="border border-border/70">
                <CardHeader>
                  <CardTitle>Правила проекта</CardTitle>
                  <CardDescription>Используйте project-scoped правила, когда поведение агента должно отличаться для одного проекта.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <select
                    className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
                    value={selectedProjectSlug ?? ""}
                    onChange={(e) => {
                      setSelectedProjectSlug(e.target.value || null)
                      setProjectDraft(null)
                    }}
                  >
                    <option value="">Выберите проект...</option>
                    {(projects ?? []).map((project) => (
                      <option key={project.slug} value={project.slug}>{project.name}</option>
                    ))}
                  </select>

                  {selectedProjectSlug ? (
                    <>
                      <Textarea
                        value={effectiveProject[tab.id]}
                        onChange={(e) => handleProjectChange(tab.id, e.target.value)}
                        placeholder={`Введите правила для проекта и агента «${tab.label}»...`}
                        rows={10}
                        className="font-mono text-sm"
                      />
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs text-muted-foreground">
                          {projectDraft ? "Есть несохраненные изменения" : "Изменений нет"}
                        </p>
                        <Button size="sm" onClick={handleSaveProject} disabled={!projectDraft || saveProject.isPending}>
                          {saveProject.isPending ? "Сохранение..." : "Сохранить правила проекта"}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                      Выберите проект, чтобы редактировать project-scoped правила.
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  )
}
