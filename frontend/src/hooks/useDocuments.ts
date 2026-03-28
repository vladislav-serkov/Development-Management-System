import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  fetchProjects, fetchProject, createProject, patchProject,
  fetchProjectFeatures, fetchProjectRegistry, fetchProjectGaps,
  fetchDocuments, fetchDocument, uploadDocument, patchDocument,
  fetchDocumentRegistry, fetchDocumentGaps,
  patchFeature, patchDependencyEntry, patchGapEntry,
} from "@/api/documents"
import type { FeaturePatchRequest, GapPatchRequest } from "@/types/api"

// Projects
export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
  })
}

export function useProject(id: number | null) {
  return useQuery({
    queryKey: ["projects", id],
    queryFn: () => fetchProject(id!),
    enabled: id !== null,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => createProject({ name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useRenameProject(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => patchProject(id, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", id] })
      qc.invalidateQueries({ queryKey: ["projects"] })
    },
  })
}

export function useProjectFeatures(projectId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "features"],
    queryFn: () => fetchProjectFeatures(projectId!),
    enabled: projectId !== null,
  })
}

export function useProjectRegistry(projectId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "registry"],
    queryFn: () => fetchProjectRegistry(projectId!),
    enabled: projectId !== null,
  })
}

export function useProjectGaps(projectId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "gaps"],
    queryFn: () => fetchProjectGaps(projectId!),
    enabled: projectId !== null,
  })
}

// Documents
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

export function useUploadDocument(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadDocument(projectId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectId] })
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents"] })
    },
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

export function useSaveFeature(documentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ featureId, patch }: { featureId: number; patch: FeaturePatchRequest }) =>
      patchFeature(documentId, featureId, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents", documentId] })
    },
  })
}

export function useSaveDependencyEntry(documentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, data }: { entryId: number; data: Record<string, unknown> }) =>
      patchDependencyEntry(documentId, entryId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents", documentId, "registry"] })
    },
  })
}

export function useSaveGapEntry(documentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, patch }: { entryId: number; patch: GapPatchRequest }) =>
      patchGapEntry(documentId, entryId, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents", documentId, "gaps"] })
    },
  })
}
