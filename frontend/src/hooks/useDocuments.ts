import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  fetchProjects, fetchProject, createProject, patchProject,
  fetchProjectFeatures,
  fetchDocuments, fetchDocument, uploadDocument, patchDocument,
  patchFeature, deleteFeature, importProjectZip,
  importContext, deleteProject,
} from "@/api/documents"
import type { ProjectResponse } from "@/types/api"
import type { FeaturePatchRequest } from "@/types/api"

// Projects
export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
  })
}

export function useProject(slug: string | null) {
  return useQuery({
    queryKey: ["projects", slug],
    queryFn: () => fetchProject(slug!),
    enabled: slug !== null,
    refetchInterval: (query) => {
      const project = query.state.data
      return project?.status === "processing" ? 3000 : false
    },
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => createProject({ name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useRenameProject(slug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => patchProject(slug, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", slug] })
      qc.invalidateQueries({ queryKey: ["projects"] })
    },
  })
}

export function useProjectFeatures(projectSlug: string | null, projectStatus?: ProjectResponse["status"]) {
  return useQuery({
    queryKey: ["projects", projectSlug, "features"],
    queryFn: () => fetchProjectFeatures(projectSlug!),
    enabled: projectSlug !== null,
    refetchInterval: (query) => {
      const features = query.state.data
      const hasRunning = features?.some(
        f => f.gaps_running || f.test_cases_running || f.apply_running
      )
      const hasExtracting = features?.some(f => f.status === "extracting")
      const projectProcessing = projectStatus === "processing"
      return (hasRunning || hasExtracting || projectProcessing) ? 3000 : false
    },
  })
}

// Documents
export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: fetchDocuments,
  })
}

export function useDocument(slug: string | null, projectSlug: string | null) {
  return useQuery({
    queryKey: ["documents", slug],
    queryFn: () => fetchDocument(slug!, projectSlug!),
    enabled: slug !== null && projectSlug !== null,
  })
}

export function useUploadDocument(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadDocument(projectSlug, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug] })
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useRenameDocument(slug: string, projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filename: string) => patchDocument(slug, projectSlug, { filename }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", slug] })
      qc.invalidateQueries({ queryKey: ["documents"] })
    },
  })
}

export function useImportProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => importProjectZip(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useImportContext() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => importContext({ path }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ slug, removeFiles }: { slug: string; removeFiles?: boolean }) =>
      deleteProject(slug, removeFiles),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useSaveFeature(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ featureName, patch }: { featureName: string; patch: FeaturePatchRequest }) =>
      patchFeature(projectSlug, featureName, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
    },
  })
}

export function useDeleteFeature(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (featureName: string) => deleteFeature(projectSlug, featureName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
      qc.invalidateQueries({ queryKey: ["projects"] })
    },
  })
}
