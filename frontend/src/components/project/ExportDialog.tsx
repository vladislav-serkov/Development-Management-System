import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog"
import { useExportDocument } from "@/hooks/useExport"

interface ExportDialogProps {
  documentId: number
}

export function ExportDialog({ documentId }: ExportDialogProps) {
  const [open, setOpen] = useState(false)
  const [targetPath, setTargetPath] = useState("")
  const exportMutation = useExportDocument(documentId)

  const handleExport = () => {
    if (!targetPath.trim()) return
    exportMutation.mutate(targetPath.trim())
  }

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next) {
      // reset on close
      setTargetPath("")
      exportMutation.reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button variant="outline" size="sm" className="w-full" />}>
        Export .context/
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Export .context/</DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">
              Absolute path to your microservice directory
            </label>
            <Input
              placeholder="/path/to/your-microservice"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleExport()
              }}
              disabled={exportMutation.isPending}
            />
          </div>

          {exportMutation.isSuccess && exportMutation.data && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Created files:</p>
              <ul className="space-y-0.5 text-xs">
                {exportMutation.data.files.map((file, i) => (
                  <li key={i} className="font-mono text-foreground/80">{file}</li>
                ))}
              </ul>
            </div>
          )}

          {exportMutation.isError && (
            <p className="text-xs text-destructive">
              Export failed. Please check the path and try again.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={handleExport}
            disabled={!targetPath.trim() || exportMutation.isPending}
          >
            {exportMutation.isPending ? "Exporting..." : "Export"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
