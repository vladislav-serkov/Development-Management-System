import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  fetchProjects, fetchProject, createProject, patchProject,
  fetchProjectFeatures, fetchDocuments, checkSpecUpdates,
  importConfluencePage,
  patchFeature, deleteFeature, implementFeature, importProjectZip,
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
          || f.impl_status === "queued" || f.impl_status === "running"
      )
      const hasExtracting = features?.some(f => f.status === "extracting")
      const projectProcessing = projectStatus === "processing"
      return (hasRunning || hasExtracting || projectProcessing) ? 3000 : false
    },
  })
}

// Documents
export function useProjectDocuments(projectSlug: string | null, projectStatus?: ProjectResponse["status"]) {
  return useQuery({
    queryKey: ["documents", projectSlug],
    queryFn: () => fetchDocuments(projectSlug!),
    enabled: projectSlug !== null,
    refetchInterval: (query) => {
      const docs = query.state.data
      const extracting = docs?.some(d => d.status === "processing" || d.status === "extracting")
      return (extracting || projectStatus === "processing") ? 3000 : false
    },
  })
}

// Version probe against Confluence: cheap (numbers only), auto-runs on project
// open and re-runs at most every 5 minutes while the page stays open.
export function useSpecUpdates(projectSlug: string | null) {
  const qc = useQueryClient()
  return useQuery({
    queryKey: ["spec-updates", projectSlug],
    queryFn: async () => {
      const result = await checkSpecUpdates(projectSlug!)
      // The check persists latest versions on the documents — refresh them
      qc.invalidateQueries({ queryKey: ["documents", projectSlug] })
      return result
    },
    enabled: projectSlug !== null,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    retry: false,
  })
}

export function useImportConfluence(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (url: string) => importConfluencePage(projectSlug, url),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects", projectSlug] })
      qc.invalidateQueries({ queryKey: ["projects"] })
      qc.invalidateQueries({ queryKey: ["documents"] })
      qc.invalidateQueries({ queryKey: ["projects", projectSlug, "features"] })
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

export function useImplementFeature(projectSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ featureName, jiraKey }: { featureName: string; jiraKey: string }) =>
      implementFeature(projectSlug, featureName, jiraKey),
    onSuccess: () => {
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
