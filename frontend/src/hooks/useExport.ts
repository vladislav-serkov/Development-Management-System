import { useMutation } from "@tanstack/react-query"
import { exportDocument } from "@/api/documents"

export function useExportDocument(documentId: number) {
  return useMutation({
    mutationFn: (targetPath: string) => exportDocument(documentId, { target_path: targetPath }),
  })
}
