import { useMutation } from "@tanstack/react-query"
import { exportProjectZip } from "@/api/documents"

function saveBlobWeb(blob: Blob, defaultName: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = defaultName
  a.click()
  URL.revokeObjectURL(url)
}

export function useExportProjectZip(projectSlug: string) {
  return useMutation({
    mutationFn: () => exportProjectZip(projectSlug),
    onSuccess: (blob) => {
      saveBlobWeb(blob, `${projectSlug}.zip`)
    },
  })
}
