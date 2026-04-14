import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { CacheEnrichment } from "@/types/api"

export function CacheStructureView({ data }: { data: CacheEnrichment }) {
  return (
    <div className="space-y-3">
      {data.description && <p className="text-sm text-muted-foreground">{data.description}</p>}
      {data.eviction_policy && <p className="text-xs text-muted-foreground">Политика вытеснения: {data.eviction_policy}</p>}
      <div className="grid gap-3">
        {data.key_patterns.map((kp, i) => (
          <Card key={i}>
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-sm font-mono">{kp.pattern}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-1">
              {kp.description && <p className="text-sm">{kp.description}</p>}
              {kp.ttl_seconds != null && <p className="text-xs text-muted-foreground">TTL: {kp.ttl_seconds}s</p>}
              {kp.value_structure && (
                <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                  {JSON.stringify(kp.value_structure, null, 2)}
                </pre>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
