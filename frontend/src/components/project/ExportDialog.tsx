import { Button } from "@/components/ui/button"
import { useExportProjectZip } from "@/hooks/useExport"

interface ExportDialogProps {
  projectSlug: string
}

export function ExportDialog({ projectSlug }: ExportDialogProps) {
  const exportMutation = useExportProjectZip(projectSlug)

  return (
    <Button
      variant="outline"
      size="sm"
      className="h-8 w-full rounded-lg text-xs"
      onClick={() => exportMutation.mutate()}
      disabled={exportMutation.isPending}
    >
      {exportMutation.isPending ? "Скачивание..." : "Скачать .zip"}
    </Button>
  )
}
