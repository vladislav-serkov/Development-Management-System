import { useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { ParametersTable } from "@/components/feature/ParametersTable"
import { LogicTree } from "@/components/feature/LogicTree"
import { DependencyCards } from "@/components/feature/DependencyCards"
import { AlertTriangle, GitBranch, ListTree, Network, X, Plus } from "lucide-react"
import type { StructuredBusinessLogic, ProjectDependency, ErrorResponseSchema, ParameterField } from "@/types/api"

interface StructuredLogicViewProps {
  logic: StructuredBusinessLogic
  featureType?: string
  projectDependencies?: ProjectDependency[]
  onDepClick?: (dep: ProjectDependency) => void
  isEditing?: boolean
  onChange?: (logic: StructuredBusinessLogic) => void
}

function emptyErrorResponse(): ErrorResponseSchema {
  return { status_codes: "", description: "", parameters: [] }
}

export function StructuredLogicView({
  logic,
  featureType,
  projectDependencies,
  onDepClick,
  isEditing = false,
  onChange,
}: StructuredLogicViewProps) {
  const isRest = featureType === "rest_endpoint"

  const hasErrorHandling = logic.error_handling && Object.keys(logic.error_handling).length > 0
  const hasBusinessRules = logic.business_rules && logic.business_rules.length > 0
  const inputCount = logic.input_parameters?.length ?? 0
  const responseCount = (logic.success_response ?? logic.output_parameters ?? []).length
  const logicCount = logic.logic_steps?.length ?? 0
  const dependencyCount = logic.used_dependencies?.length ?? 0
  const rulesCount = logic.business_rules?.length ?? 0
  const errorCount = logic.error_responses?.length ?? 0

  // Local state for error_handling JSON edit (only used when isEditing=true)
  const [errorHandlingJson, setErrorHandlingJson] = useState(
    () => JSON.stringify(logic.error_handling ?? {}, null, 2)
  )
  const [errorHandlingJsonError, setErrorHandlingJsonError] = useState(false)

  const handleErrorHandlingChange = (text: string) => {
    setErrorHandlingJson(text)
    try {
      const parsed = JSON.parse(text)
      setErrorHandlingJsonError(false)
      onChange?.({ ...logic, error_handling: parsed })
    } catch {
      setErrorHandlingJsonError(true)
    }
  }

  const updateErrorResponse = (i: number, updated: ErrorResponseSchema) => {
    const next = (logic.error_responses ?? []).map((e, idx) => (idx === i ? updated : e))
    onChange?.({ ...logic, error_responses: next })
  }

  const deleteErrorResponse = (i: number) => {
    onChange?.({ ...logic, error_responses: (logic.error_responses ?? []).filter((_, idx) => idx !== i) })
  }

  const addErrorResponse = () => {
    onChange?.({ ...logic, error_responses: [...(logic.error_responses ?? []), emptyErrorResponse()] })
  }

  const updateBusinessRule = (i: number, text: string) => {
    const next = (logic.business_rules ?? []).map((r, idx) => (idx === i ? text : r))
    onChange?.({ ...logic, business_rules: next })
  }

  const deleteBusinessRule = (i: number) => {
    onChange?.({ ...logic, business_rules: (logic.business_rules ?? []).filter((_, idx) => idx !== i) })
  }

  const addBusinessRule = () => {
    onChange?.({ ...logic, business_rules: [...(logic.business_rules ?? []), ""] })
  }

  return (
    <Tabs defaultValue="input_params" className="gap-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <LogicSummaryCard icon={<ListTree className="h-4 w-4" />} label="Входные параметры" value={String(inputCount)} helper={isRest ? "С учетом param_in" : "Структура входа"} />
        <LogicSummaryCard icon={<GitBranch className="h-4 w-4" />} label="Шаги логики" value={String(logicCount)} helper="Основная последовательность" />
        <LogicSummaryCard icon={<Network className="h-4 w-4" />} label="Зависимости" value={String(dependencyCount)} helper="Связанные сущности" />
        <LogicSummaryCard icon={<AlertTriangle className="h-4 w-4" />} label="Ошибки и правила" value={String(errorCount + rulesCount)} helper={`${errorCount} ошибок, ${rulesCount} правил`} />
      </div>

      <TabsList className="h-auto flex-wrap gap-1">
        <TabsTrigger value="input_params">Параметры (вход)</TabsTrigger>
        {isRest && (
          <TabsTrigger value="response">Ответ{responseCount ? ` (${responseCount})` : ""}</TabsTrigger>
        )}
        <TabsTrigger value="logic">Логика{logicCount ? ` (${logicCount})` : ""}</TabsTrigger>
        <TabsTrigger value="dependencies">Зависимости{dependencyCount ? ` (${dependencyCount})` : ""}</TabsTrigger>
        <TabsTrigger value="errors_rules">Ошибки и правила</TabsTrigger>
      </TabsList>

      <TabsContent value="input_params" className="space-y-3">
        <SectionLead
          title="Параметры входа"
          description={isRest ? "Собранные поля запроса, path/query/header и тело входного сообщения." : "Структура входного сообщения или payload, с которым работает фича."}
        />
        <ParametersTable
          parameters={logic.input_parameters ?? []}
          showParamIn={isRest}
          isEditing={isEditing}
          onChange={isEditing ? (params) => onChange?.({ ...logic, input_parameters: params }) : undefined}
        />
      </TabsContent>

      {isRest && (
        <TabsContent value="response" className="space-y-6">
          <SectionLead
            title="Ответы"
            description="Успешный ответ и отдельные схемы ошибок. Здесь важно быстро сравнивать happy path и error path."
          />
          <div className="space-y-6">
            <div>
              <h3 className="mb-2 text-sm font-medium">Успешный ответ (2xx)</h3>
              <ParametersTable
                parameters={logic.success_response ?? logic.output_parameters ?? []}
                showParamIn={false}
                isEditing={isEditing}
                onChange={isEditing ? (params) => onChange?.({ ...logic, success_response: params }) : undefined}
              />
            </div>

            {/* Error responses section */}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <h3 className="text-sm font-medium">Ответы при ошибках</h3>
                {isEditing && (
                  <button
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    onClick={addErrorResponse}
                  >
                    <Plus className="h-3 w-3" /> Добавить
                  </button>
                )}
              </div>
              {(logic.error_responses ?? []).length > 0 ? (
                <div className="space-y-4">
                  {(logic.error_responses ?? []).map((err: ErrorResponseSchema, i: number) => (
                    <div key={i} className="relative rounded-xl border border-border/70 p-4">
                      {isEditing ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <input
                              className="text-xs font-mono bg-transparent border-b border-border outline-none w-24"
                              value={err.status_codes}
                              placeholder="4xx / 5xx"
                              onChange={(e) => updateErrorResponse(i, { ...err, status_codes: e.target.value })}
                            />
                            <input
                              className="text-sm text-muted-foreground bg-transparent border-b border-border outline-none flex-1"
                              value={err.description}
                              placeholder="description"
                              onChange={(e) => updateErrorResponse(i, { ...err, description: e.target.value })}
                            />
                            <button
                              className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors shrink-0"
                              title="Delete error response"
                              onClick={() => deleteErrorResponse(i)}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                          <ParametersTable
                            parameters={err.parameters ?? []}
                            showParamIn={false}
                            isEditing={isEditing}
                            onChange={(params) => updateErrorResponse(i, { ...err, parameters: params as ParameterField[] })}
                          />
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs font-mono bg-red-100 text-red-800 px-2 py-0.5 rounded">{err.status_codes}</span>
                            <span className="text-sm text-muted-foreground">{err.description}</span>
                          </div>
                          <ParametersTable parameters={err.parameters ?? []} showParamIn={false} />
                        </>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                !isEditing && !(logic.success_response ?? logic.output_parameters ?? []).length && (
                  <p className="text-sm text-muted-foreground">Отдельные схемы ошибок не заполнены.</p>
                )
              )}
            </div>
          </div>
        </TabsContent>
      )}

      <TabsContent value="logic" className="space-y-3">
        <SectionLead
          title="Шаги логики"
          description="Основная последовательность обработки, включая вложенные шаги и mapping входных или выходных сообщений."
        />
        <LogicTree
          steps={logic.logic_steps ?? []}
          isEditing={isEditing}
          onChange={isEditing ? (steps) => onChange?.({ ...logic, logic_steps: steps }) : undefined}
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
          isEditing={isEditing}
          onChange={isEditing ? (deps) => onChange?.({ ...logic, used_dependencies: deps }) : undefined}
        />
      </TabsContent>

      <TabsContent value="errors_rules" className="space-y-4">
        <SectionLead
          title="Ошибки и правила"
          description="Операционные сценарии отказа и бизнес-ограничения, которые должны быть видны отдельно от основной логики."
        />
        <div className="space-y-4">
          {isEditing ? (
            <>
              <div>
                <h3 className="text-sm font-medium mb-2">Обработка ошибок (JSON)</h3>
                <textarea
                  className={`w-full text-xs font-mono bg-muted/30 border rounded px-3 py-2 outline-none resize-none min-h-[7.5rem] ${
                    errorHandlingJsonError ? "border-destructive" : "border-border"
                  }`}
                  value={errorHandlingJson}
                  onChange={(e) => handleErrorHandlingChange(e.target.value)}
                  rows={8}
                />
                {errorHandlingJsonError && (
                  <p className="text-xs text-destructive mt-1">Некорректный JSON</p>
                )}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-medium">Бизнес-правила</h3>
                  <button
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    onClick={addBusinessRule}
                  >
                    <Plus className="h-3 w-3" /> Добавить
                  </button>
                </div>
                <div className="space-y-1">
                  {(logic.business_rules ?? []).map((rule, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        className="text-sm bg-transparent border-b border-border outline-none flex-1"
                        value={rule}
                        placeholder="Бизнес-правило..."
                        onChange={(e) => updateBusinessRule(i, e.target.value)}
                      />
                      <button
                        className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors shrink-0"
                        title="Delete rule"
                        onClick={() => deleteBusinessRule(i)}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                  {(logic.business_rules ?? []).length === 0 && (
                    <p className="text-xs text-muted-foreground">Нет правил. Нажмите + для добавления.</p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              {hasErrorHandling ? (
                <div>
                  <h3 className="text-sm font-medium mb-2">Обработка ошибок</h3>
                  <ul className="list-disc pl-4 space-y-1">
                    {Object.entries(logic.error_handling!).map(([key, value]) => (
                      <li key={key} className="text-sm">
                        <span className="font-mono text-xs text-muted-foreground">{key}</span>
                        {" — "}
                        {String(value)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Нет данных об обработке ошибок</p>
              )}
              {hasBusinessRules && (
                <div>
                  <h3 className="text-sm font-medium mb-2">Бизнес-правила</h3>
                  <ul className="list-disc pl-4 space-y-1">
                    {logic.business_rules!.map((rule, i) => (
                      <li key={i} className="text-sm">{rule}</li>
                    ))}
                  </ul>
                </div>
              )}
              {!hasErrorHandling && !hasBusinessRules && (
                <p className="text-sm text-muted-foreground">Нет бизнес-правил</p>
              )}
            </>
          )}
        </div>
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
