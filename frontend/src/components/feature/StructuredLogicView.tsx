import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { LogicTree } from "@/components/feature/LogicTree"
import { DependencyCards } from "@/components/feature/DependencyCards"
import { SpecTablesSection } from "@/components/feature/SpecTableView"
import { countSpecFields } from "@/lib/specTables"
import { AlertTriangle, GitBranch, ListTree, Network } from "lucide-react"
import type { StructuredBusinessLogic, ProjectDependency } from "@/types/api"

interface StructuredLogicViewProps {
  logic: StructuredBusinessLogic
  featureType?: string
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
}

export function StructuredLogicView({
  logic,
  featureType,
  projectDependencies,
  onDepClick,
}: StructuredLogicViewProps) {
  const isRest = featureType === "rest_endpoint"

  const inputTables = logic.input_tables ?? []
  const responseTables = logic.response_tables ?? []
  const inputCount = countSpecFields(inputTables)
  const responseTableCount = responseTables.length
  const logicCount = logic.logic_steps?.length ?? 0
  const dependencyCount = logic.used_dependencies?.length ?? 0
  const showResponses = isRest || responseTableCount > 0

  return (
    <Tabs defaultValue="input" className="gap-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <LogicSummaryCard icon={<ListTree className="h-4 w-4" />} label="Входные параметры" value={String(inputCount)} helper={`${inputTables.length} табл. из ТЗ`} />
        <LogicSummaryCard icon={<GitBranch className="h-4 w-4" />} label="Шаги логики" value={String(logicCount)} helper="Основная последовательность" />
        <LogicSummaryCard icon={<Network className="h-4 w-4" />} label="Зависимости" value={String(dependencyCount)} helper="Связанные сущности" />
        <LogicSummaryCard icon={<AlertTriangle className="h-4 w-4" />} label="Ответы" value={String(responseTableCount)} helper="Таблицы по HTTP-статусам" />
      </div>

      <TabsList className="h-auto flex-wrap gap-1">
        <TabsTrigger value="input">Входные параметры{inputTables.length ? ` (${inputTables.length})` : ""}</TabsTrigger>
        {showResponses && (
          <TabsTrigger value="responses">Выходные параметры{responseTableCount ? ` (${responseTableCount})` : ""}</TabsTrigger>
        )}
        <TabsTrigger value="logic">Логика{logicCount ? ` (${logicCount})` : ""}</TabsTrigger>
        <TabsTrigger value="dependencies">Зависимости{dependencyCount ? ` (${dependencyCount})` : ""}</TabsTrigger>
      </TabsList>

      <TabsContent value="input" className="space-y-3">
        <SectionLead
          title="Входные параметры"
          description="Таблицы раздела «Входные параметры» ТЗ — дословно, с теми же колонками, что в Confluence."
        />
        <SpecTablesSection
          tables={inputTables}
          emptyText="В ТЗ нет таблиц входных параметров."
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
        />
      </TabsContent>

      {showResponses && (
        <TabsContent value="responses" className="space-y-3">
          <SectionLead
            title="Выходные параметры"
            description="Таблицы раздела «Выходные параметры» ТЗ, сгруппированные по HTTP-статусам — как в Confluence."
          />
          <SpecTablesSection
            tables={responseTables}
            emptyText="В ТЗ нет таблиц выходных параметров."
            projectDependencies={projectDependencies}
            onDepClick={onDepClick}
          />
        </TabsContent>
      )}

      <TabsContent value="logic" className="space-y-3">
        <SectionLead
          title="Шаги логики"
          description="Основная последовательность обработки, включая вложенные шаги и mapping входных или выходных сообщений."
        />
        <LogicTree
          steps={logic.logic_steps ?? []}
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
          onDocRefClick={(name) => {
            const dep = projectDependencies?.find(
              (pd) => pd.dep_type === "external_doc" && pd.name === name
            )
            if (dep && onDepClick) onDepClick(dep)
          }}
        />
      </TabsContent>

      <TabsContent value="dependencies" className="space-y-3">
        <SectionLead
          title="Связанные зависимости"
          description="Системы, таблицы и топики, которые реально участвуют в сценарии. Этот блок должен помогать быстро проверить полноту модели."
        />
        <DependencyCards
          dependencies={logic.used_dependencies ?? []}
          projectDependencies={projectDependencies}
          onDepClick={onDepClick}
        />
      </TabsContent>
    </Tabs>
  )
}

function LogicSummaryCard({
  icon,
  label,
  value,
  helper,
}: {
  icon: React.ReactNode
  label: string
  value: string
  helper: string
}) {
  return (
    <Card className="border border-border/70 shadow-none">
      <CardContent className="flex items-start justify-between gap-3 py-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold">{value}</p>
          <p className="mt-1 text-sm text-muted-foreground">{helper}</p>
        </div>
        <div className="rounded-lg bg-muted p-2 text-muted-foreground">
          {icon}
        </div>
      </CardContent>
    </Card>
  )
}

function SectionLead({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-1">
      <h3 className="text-base font-medium">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
