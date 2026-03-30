import { useMutation } from "@tanstack/react-query"
import { exportProjectZip } from "@/api/documents"

export function useExportProjectZip(projectSlug: string) {
  return useMutation({
    mutationFn: () => exportProjectZip(projectSlug),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${projectSlug}.zip`
      a.click()
      URL.revokeObjectURL(url)
    },
  })
}
