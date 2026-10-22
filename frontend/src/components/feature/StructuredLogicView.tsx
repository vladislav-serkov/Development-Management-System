import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LogicTree } from "@/components/feature/LogicTree"
import { DependencyCards } from "@/components/feature/DependencyCards"
import { SpecTablesSection } from "@/components/feature/SpecTableView"
import { countSpecFields } from "@/lib/specTables"
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
      <TabsList variant="line" className="h-auto w-full flex-wrap justify-start gap-4 border-b pb-px">
        <TabsTrigger value="input" className="flex-none px-0.5">Входные параметры<Count n={inputCount} /></TabsTrigger>
        {showResponses && (
          <TabsTrigger value="responses" className="flex-none px-0.5">Ответы<Count n={responseTableCount} /></TabsTrigger>
        )}
        <TabsTrigger value="logic" className="flex-none px-0.5">Шаги логики<Count n={logicCount} /></TabsTrigger>
        <TabsTrigger value="dependencies" className="flex-none px-0.5">Зависимости<Count n={dependencyCount} /></TabsTrigger>
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

function SectionLead({ description }: { title: string; description: string }) {
  return <p className="text-xs text-muted-foreground">{description}</p>
}

function Count({ n }: { n: number }) {
  if (!n) return null
  return <span className="text-xs tabular-nums opacity-60">{n}</span>
}
