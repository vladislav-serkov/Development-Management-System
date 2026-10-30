import { Check, Loader2, Upload } from "lucide-react"
import { useTestWireMockStatus, useUploadMock } from "@/hooks/useTestWireMock"
import { Button } from "@/components/ui/button"
import { ARTIFACT_BADGE, prettyJsonOrRaw } from "@/lib/artifacts"
import { ArtifactHead, CodeBlock, MetaChip, TypeBadge } from "./artifact-ui"

export function MockArtifact({ value }: { value: string }) {
  const { data: stand, error: statusError } = useTestWireMockStatus()
  const upload = useUploadMock()
  let method: string | null = null
  let path: string | null = null
  let status: number | null = null
  try {
    const parsed = JSON.parse(value)
    method = typeof parsed?.request?.method === "string" ? parsed.request.method : null
    const req = parsed?.request ?? {}
    const url = req.urlPath ?? req.url ?? req.urlPattern ?? req.urlPathPattern
    path = typeof url === "string" ? url : null
    status = typeof parsed?.response?.status === "number" ? parsed.response.status : null
  } catch {
    // Invalid mappings stay visible; the backend explains validation errors on upload.
  }

  return (
    <div className="space-y-2.5">
      <ArtifactHead
        badge={<TypeBadge label="MOCK" className={ARTIFACT_BADGE.MOCK} />}
        target={path ? `${method ? `${method} ` : ""}${path}` : "мок внешней системы"}
        chips={status !== null ? <MetaChip>ответ {status}</MetaChip> : undefined}
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={() => upload.mutate(value)}
            disabled={!stand?.configured || upload.isPending}
            title={stand?.target_url ?? "WireMock не настроен"}
          >
            {upload.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {upload.isPending ? "Загружается" : "Загрузить в WireMock"}
          </Button>
        }
      />
      {stand?.target_url && <p className="break-all text-[0.6875rem] text-muted-foreground">{stand.target_url}</p>}
      {stand && !stand.configured && <p className="text-[0.75rem] text-muted-foreground">Загрузка моков на стенд пока не настроена.</p>}
      <CodeBlock value={prettyJsonOrRaw(value)} copyValue={value} />
      {(upload.error || statusError) && (
        <p role="alert" className="whitespace-pre-wrap break-words text-[0.75rem] text-destructive">
          {(upload.error ?? statusError)?.message}
        </p>
      )}
      {upload.data && !upload.isPending && (
        <div role="status" className="space-y-1 rounded-lg border border-emerald-200 p-3 dark:border-emerald-900">
          <p className="flex items-center gap-1.5 text-[0.75rem] text-emerald-700 dark:text-emerald-400">
            <Check className="h-3.5 w-3.5" /> Мок загружен · HTTP {upload.data.status_code} · {upload.data.duration_ms} мс
          </p>
          <p className="break-all font-mono text-[0.6875rem] text-muted-foreground">ID: {upload.data.mapping_id}</p>
        </div>
      )}
    </div>
  )
}
