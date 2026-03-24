import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { JSONViewer } from "@/components/artifact/JSONViewer"
import type { StructuredBusinessLogic } from "@/types/api"

interface StructuredLogicViewProps {
  logic: StructuredBusinessLogic
}

export function StructuredLogicView({ logic }: StructuredLogicViewProps) {
  const hasProcessingSteps = logic.processing_steps && logic.processing_steps.length > 0
  const hasInputSchema = logic.input_schema && Object.keys(logic.input_schema).length > 0
  const hasOutputSchema = logic.output_schema && Object.keys(logic.output_schema).length > 0
  const hasErrorHandling = logic.error_handling && Object.keys(logic.error_handling).length > 0
  const hasExternalApiCalls = logic.external_api_calls && logic.external_api_calls.length > 0
  const hasDatabaseOperations = logic.database_operations && logic.database_operations.length > 0
  const hasCacheOperations = logic.cache_operations && logic.cache_operations.length > 0
  const hasBusinessRules = logic.business_rules && logic.business_rules.length > 0

  return (
    <div className="grid grid-cols-1 gap-4">
      {hasProcessingSteps && (
        <Card>
          <CardHeader>
            <CardTitle>Processing Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {logic.processing_steps!.map((step) => (
                <div key={step.step} className="flex items-start gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                    {step.step}
                  </span>
                  <div>
                    <p className="text-sm font-semibold">{step.action}</p>
                    {step.description && (
                      <p className="text-xs text-muted-foreground">{step.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {hasInputSchema && (
        <Card>
          <CardHeader>
            <CardTitle>Input Schema</CardTitle>
          </CardHeader>
          <CardContent>
            <JSONViewer value={logic.input_schema!} />
          </CardContent>
        </Card>
      )}

      {hasOutputSchema && (
        <Card>
          <CardHeader>
            <CardTitle>Output Schema</CardTitle>
          </CardHeader>
          <CardContent>
            <JSONViewer value={logic.output_schema!} />
          </CardContent>
        </Card>
      )}

      {hasErrorHandling && (
        <Card>
          <CardHeader>
            <CardTitle>Error Handling</CardTitle>
          </CardHeader>
          <CardContent>
            <JSONViewer value={logic.error_handling!} />
          </CardContent>
        </Card>
      )}

      {hasExternalApiCalls && (
        <Card>
          <CardHeader>
            <CardTitle>External API Calls</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {logic.external_api_calls!.map((call, i) => {
                const name = String(call.name ?? call.url ?? `Call ${i + 1}`)
                const method = call.method ? String(call.method) : null
                const url = call.url ? String(call.url) : null
                const description = call.description ? String(call.description) : null
                return (
                  <div key={i} className="rounded border p-2 text-sm space-y-1">
                    <p className="font-medium">{name}</p>
                    {method && url && (
                      <p className="text-xs text-muted-foreground font-mono">
                        {method} {url}
                      </p>
                    )}
                    {description && <p className="text-xs text-muted-foreground">{description}</p>}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {hasDatabaseOperations && (
        <Card>
          <CardHeader>
            <CardTitle>Database Operations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {logic.database_operations!.map((op, i) => {
                const table = op.table ? String(op.table) : null
                const operation = op.operation ? String(op.operation) : null
                const description = op.description ? String(op.description) : null
                return (
                  <div key={i} className="rounded border p-2 text-sm space-y-1">
                    {table && <p className="font-medium font-mono">{table}</p>}
                    {operation && <p className="text-xs text-muted-foreground">{operation}</p>}
                    {description && <p className="text-xs text-muted-foreground">{description}</p>}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {hasCacheOperations && (
        <Card>
          <CardHeader>
            <CardTitle>Cache Operations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {logic.cache_operations!.map((op, i) => {
                const name = op.name ? String(op.name) : `Operation ${i + 1}`
                const structure = op.structure ? String(op.structure) : null
                const description = op.description ? String(op.description) : null
                return (
                  <div key={i} className="rounded border p-2 text-sm space-y-1">
                    <p className="font-medium">{name}</p>
                    {structure && <p className="text-xs text-muted-foreground font-mono">{structure}</p>}
                    {description && <p className="text-xs text-muted-foreground">{description}</p>}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {hasBusinessRules && (
        <Card>
          <CardHeader>
            <CardTitle>Business Rules</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-4 space-y-1">
              {logic.business_rules!.map((rule, i) => (
                <li key={i} className="text-sm">{rule}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {!hasProcessingSteps && !hasInputSchema && !hasOutputSchema && !hasErrorHandling &&
       !hasExternalApiCalls && !hasDatabaseOperations && !hasCacheOperations && !hasBusinessRules && (
        <p className="text-sm text-muted-foreground">No structured logic available.</p>
      )}
    </div>
  )
}
