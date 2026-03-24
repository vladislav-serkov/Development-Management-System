import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchDocuments, fetchDocument, uploadDocument, patchDocument, fetchDocumentRegistry, fetchDocumentGaps } from "@/api/documents"

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments,
  })
}

export function useDocument(id: number | null) {
  return useQuery({
    queryKey: ["documents", id],
    queryFn: () => fetchDocument(id!),
    enabled: id !== null,
  })
}

export function useDocumentRegistry(id: number | null) {
  return useQuery({
    queryKey: ["documents", id, "registry"],
    queryFn: () => fetchDocumentRegistry(id!),
    enabled: id !== null,
  })
}

export function useDocumentGaps(id: number | null) {
  return useQuery({
    queryKey: ["documents", id, "gaps"],
    queryFn: () => fetchDocumentGaps(id!),
    enabled: id !== null,
  })
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  })
}

export function useRenameDocument(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filename: string) => patchDocument(id, { filename }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", id] })
      qc.invalidateQueries({ queryKey: ["documents"] })
    },
  })
}
