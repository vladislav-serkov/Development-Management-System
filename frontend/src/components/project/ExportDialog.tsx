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
      className="w-full"
      onClick={() => exportMutation.mutate()}
      disabled={exportMutation.isPending}
    >
      {exportMutation.isPending ? "Downloading..." : "Download .zip"}
    </Button>
  )
}
