import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { MarkdownViewer } from "@/components/artifact/MarkdownViewer"
import { JSONViewer } from "@/components/artifact/JSONViewer"
import { DependencyTable } from "@/components/artifact/DependencyTable"
import { GapCard } from "@/components/artifact/GapCard"
import { StructuredLogicView } from "@/components/feature/StructuredLogicView"
import { useUIStore } from "@/stores/uiStore"
import { useDocumentRegistry, useDocumentGaps } from "@/hooks/useDocuments"
import type { DocumentResponse } from "@/types/api"

interface ContentAreaProps {
  document: DocumentResponse
}

function featureTypeBadge(type: string) {
  const labels: Record<string, string> = {
    rest_endpoint: "REST",
    kafka_consumer: "Kafka",
    scheduled_task: "Scheduled",
    unknown: "Unknown",
  }
  return (
    <Badge variant="secondary" className="text-xs capitalize">
      {labels[type] ?? type}
    </Badge>
  )
}

export function ContentArea({ document }: ContentAreaProps) {
  const { selectedFeatureId, activeSidebarItem } = useUIStore()
  const { data: registry } = useDocumentRegistry(document.id)
  const { data: gaps } = useDocumentGaps(document.id)

  // Feature view
  if (selectedFeatureId !== null) {
    const feature = document.features.find((f) => f.id === selectedFeatureId)

    if (!feature) {
      return <p className="text-sm text-muted-foreground">Feature not found.</p>
    }

    return (
      <div className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-semibold">{feature.name}</h2>
            {featureTypeBadge(feature.type)}
            <Badge variant="outline" className="text-xs">
              {Math.round(feature.confidence * 100)}% confidence
            </Badge>
          </div>
          {feature.summary && (
            <p className="text-sm text-muted-foreground">{feature.summary}</p>
          )}
        </div>

        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="structured">Structured Logic</TabsTrigger>
            <TabsTrigger value="json">Business Logic JSON</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-4">
            {feature.overview_md ? (
              <MarkdownViewer content={feature.overview_md} />
            ) : (
              <p className="text-sm text-muted-foreground">No overview available.</p>
            )}
          </TabsContent>

          <TabsContent value="structured" className="mt-4">
            {feature.structured_logic ? (
              <StructuredLogicView logic={feature.structured_logic} />
            ) : (
              <p className="text-sm text-muted-foreground">No structured logic available.</p>
            )}
          </TabsContent>

          <TabsContent value="json" className="mt-4">
            {feature.business_logic ? (
              <JSONViewer value={feature.business_logic} />
            ) : (
              <p className="text-sm text-muted-foreground">No business logic JSON available.</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    )
  }

  // Category views
  if (activeSidebarItem === "db") {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">Database Dependencies</h2>
        <DependencyTable entries={registry?.db ?? []} registryType="db" />
      </div>
    )
  }

  if (activeSidebarItem === "external_api") {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">External API Dependencies</h2>
        <DependencyTable entries={registry?.external_api ?? []} registryType="external_api" />
      </div>
    )
  }

  if (activeSidebarItem === "cache") {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">Cache Dependencies</h2>
        <DependencyTable entries={registry?.cache ?? []} registryType="cache" />
      </div>
    )
  }

  if (activeSidebarItem === "gaps") {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">Gaps</h2>
        {gaps && gaps.length > 0 ? (
          <div className="space-y-3">
            {gaps.map((gap) => (
              <GapCard key={gap.id} gap={gap} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No gaps identified.</p>
        )}
      </div>
    )
  }

  // Default: nothing selected
  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-muted-foreground">
        Select a feature or category from the sidebar.
      </p>
    </div>
  )
}
