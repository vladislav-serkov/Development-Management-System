import type { DocumentResponse, DocumentPatchRequest, FeatureResponse, FeaturePatchRequest, ExportRequest, ExportResponse, ProjectResponse, CreateProjectRequest, PatchProjectRequest, LinkProjectRequest, ImportContextResponse, ProjectDependency, CreateDependencyRequest, PatchDependencyRequest } from "@/types/api"
import { apiFetch } from "./client"

// Projects
export async function fetchProjects(): Promise<ProjectResponse[]> {
  const res = await apiFetch(`/projects/`)
  if (!res.ok) throw new Error(`Failed to fetch projects: ${res.status}`)
  return res.json()
}

export async function fetchProject(slug: string): Promise<ProjectResponse> {
  const res = await apiFetch(`/projects/${slug}`)
  if (!res.ok) throw new Error(`Failed to fetch project ${slug}: ${res.status}`)
  return res.json()
}

export async function createProject(req: CreateProjectRequest): Promise<ProjectResponse> {
  const res = await apiFetch(`/projects/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Failed to create project: ${res.status}`)
  return res.json()
}

export async function importContext(req: LinkProjectRequest): Promise<ImportContextResponse> {
  const res = await apiFetch(`/projects/import-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    let detail = `Failed to import .context: ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

export async function deleteProject(slug: string, removeFiles = false): Promise<void> {
  const url = `/projects/${slug}${removeFiles ? "?remove_files=true" : ""}`
  const res = await apiFetch(url, { method: "DELETE" })
  if (!res.ok) throw new Error(`Failed to delete project: ${res.status}`)
}

export async function patchProject(slug: string, patch: PatchProjectRequest): Promise<ProjectResponse> {
  const res = await apiFetch(`/projects/${slug}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to rename project: ${res.status}`)
  return res.json()
}

export async function fetchProjectFeatures(projectSlug: string): Promise<FeatureResponse[]> {
  const res = await apiFetch(`/projects/${projectSlug}/features`)
  if (!res.ok) throw new Error(`Failed to fetch features: ${res.status}`)
  return res.json()
}

// Documents
export async function fetchDocuments(): Promise<DocumentResponse[]> {
  const res = await apiFetch(`/documents/`)
  if (!res.ok) throw new Error(`Failed to fetch documents: ${res.status}`)
  return res.json()
}

export async function fetchDocument(slug: string, projectSlug: string): Promise<DocumentResponse> {
  const res = await apiFetch(`/documents/${slug}?project_slug=${projectSlug}`)
  if (!res.ok) throw new Error(`Failed to fetch document ${slug}: ${res.status}`)
  return res.json()
}

export async function uploadDocument(projectSlug: string, file: File): Promise<DocumentResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await apiFetch(`/documents/upload?project_slug=${projectSlug}`, { method: "POST", body: fd })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  return res.json()
}

export async function patchDocument(slug: string, projectSlug: string, patch: DocumentPatchRequest): Promise<DocumentResponse> {
  const res = await apiFetch(`/documents/${slug}?project_slug=${projectSlug}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Rename failed: ${res.status}`)
  return res.json()
}

export async function exportDocument(projectSlug: string, docSlug: string, request: ExportRequest): Promise<ExportResponse> {
  const res = await apiFetch(`/documents/${docSlug}/export?project_slug=${projectSlug}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  return res.json()
}

export async function patchFeature(
  projectSlug: string,
  featureName: string,
  patch: FeaturePatchRequest
): Promise<FeatureResponse> {
  const res = await apiFetch(`/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch feature: ${res.status}`)
  return res.json()
}

export async function deleteFeature(projectSlug: string, featureName: string): Promise<void> {
  const res = await apiFetch(`/projects/${projectSlug}/features/${encodeURIComponent(featureName.replaceAll("/", "__"))}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(`Failed to delete feature: ${res.status}`)
}

export async function createDependency(projectSlug: string, req: CreateDependencyRequest): Promise<ProjectDependency> {
  const res = await apiFetch(`/projects/${projectSlug}/dependencies/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Failed to create dependency: ${res.status}`)
  return res.json()
}

export async function patchDependency(
  projectSlug: string,
  depName: string,
  depType: string,
  patch: PatchDependencyRequest
): Promise<ProjectDependency> {
  const res = await apiFetch(`/projects/${projectSlug}/dependencies/${encodeURIComponent(depName)}?dep_type=${depType}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch dependency: ${res.status}`)
  return res.json()
}

export async function deleteDependency(projectSlug: string, depName: string, depType: string): Promise<void> {
  const res = await apiFetch(`/projects/${projectSlug}/dependencies/${encodeURIComponent(depName)}?dep_type=${depType}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(`Failed to delete dependency: ${res.status}`)
}

// Project zip export / import
export async function exportProjectZip(projectSlug: string): Promise<Blob> {
  const res = await apiFetch(`/projects/${projectSlug}/export/zip`)
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  return res.blob()
}

export async function importProjectZip(file: File): Promise<ProjectResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await apiFetch(`/projects/import`, { method: "POST", body: fd })
  if (!res.ok) throw new Error(`Import failed: ${res.status}`)
  return res.json()
}

// Dependencies
export async function fetchProjectDependencies(projectSlug: string): Promise<ProjectDependency[]> {
  const res = await apiFetch(`/projects/${projectSlug}/dependencies/`)
  if (!res.ok) throw new Error(`Failed to fetch dependencies: ${res.status}`)
  return res.json()
}

export async function enrichDependency(
  projectSlug: string,
  depType: string,
  file: File,
  depName?: string,
): Promise<{ status: string }> {
  const fd = new FormData()
  fd.append("file", file)
  let url = `/projects/${projectSlug}/dependencies/enrich?dep_type=${depType}`
  if (depName) {
    url += `&dep_name=${encodeURIComponent(depName)}`
  }
  const res = await apiFetch(url, { method: "POST", body: fd })
  if (!res.ok) throw new Error(`Enrichment failed: ${res.status}`)
  return res.json()
}
