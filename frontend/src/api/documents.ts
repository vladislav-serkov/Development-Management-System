import type { DocumentResponse, DocumentPatchRequest, FeatureResponse, FeaturePatchRequest, GapPatchRequest, RegistryResponse, GapResponse, ExportRequest, ExportResponse, ProjectResponse, CreateProjectRequest, PatchProjectRequest } from "@/types/api"

const API_BASE = "/api"

// Projects
export async function fetchProjects(): Promise<ProjectResponse[]> {
  const res = await fetch(`${API_BASE}/projects/`)
  if (!res.ok) throw new Error(`Failed to fetch projects: ${res.status}`)
  return res.json()
}

export async function fetchProject(id: number): Promise<ProjectResponse> {
  const res = await fetch(`${API_BASE}/projects/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch project ${id}: ${res.status}`)
  return res.json()
}

export async function createProject(req: CreateProjectRequest): Promise<ProjectResponse> {
  const res = await fetch(`${API_BASE}/projects/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Failed to create project: ${res.status}`)
  return res.json()
}

export async function patchProject(id: number, patch: PatchProjectRequest): Promise<ProjectResponse> {
  const res = await fetch(`${API_BASE}/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to rename project: ${res.status}`)
  return res.json()
}

export async function fetchProjectFeatures(projectId: number): Promise<FeatureResponse[]> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/features`)
  if (!res.ok) throw new Error(`Failed to fetch features: ${res.status}`)
  return res.json()
}

export async function fetchProjectRegistry(projectId: number): Promise<RegistryResponse> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/registry`)
  if (!res.ok) throw new Error(`Failed to fetch registry: ${res.status}`)
  return res.json()
}

export async function fetchProjectGaps(projectId: number): Promise<GapResponse[]> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/gaps`)
  if (!res.ok) throw new Error(`Failed to fetch gaps: ${res.status}`)
  return res.json()
}

// Documents
export async function fetchDocuments(): Promise<DocumentResponse[]> {
  const res = await fetch(`${API_BASE}/documents/`)
  if (!res.ok) throw new Error(`Failed to fetch documents: ${res.status}`)
  return res.json()
}

export async function fetchDocument(id: number): Promise<DocumentResponse> {
  const res = await fetch(`${API_BASE}/documents/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch document ${id}: ${res.status}`)
  return res.json()
}

export async function uploadDocument(projectId: number, file: File): Promise<DocumentResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await fetch(`${API_BASE}/documents/upload?project_id=${projectId}`, { method: "POST", body: fd })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  return res.json()
}

export async function patchDocument(id: number, patch: DocumentPatchRequest): Promise<DocumentResponse> {
  const res = await fetch(`${API_BASE}/documents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Rename failed: ${res.status}`)
  return res.json()
}

export async function fetchDocumentRegistry(id: number): Promise<RegistryResponse> {
  const res = await fetch(`${API_BASE}/documents/${id}/registry`)
  if (!res.ok) throw new Error(`Failed to fetch registry: ${res.status}`)
  return res.json()
}

export async function fetchDocumentGaps(id: number): Promise<GapResponse[]> {
  const res = await fetch(`${API_BASE}/documents/${id}/gaps`)
  if (!res.ok) throw new Error(`Failed to fetch gaps: ${res.status}`)
  return res.json()
}

export async function exportDocument(id: number, request: ExportRequest): Promise<ExportResponse> {
  const res = await fetch(`${API_BASE}/documents/${id}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  return res.json()
}

export async function patchFeature(
  documentId: number,
  featureId: number,
  patch: FeaturePatchRequest
): Promise<FeatureResponse> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/features/${featureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch feature: ${res.status}`)
  return res.json()
}

export async function patchDependencyEntry(
  documentId: number,
  entryId: number,
  data: Record<string, unknown>
): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/registry/entries/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data }),
  })
  if (!res.ok) throw new Error(`Failed to patch dependency entry: ${res.status}`)
}

export async function patchGapEntry(
  documentId: number,
  entryId: number,
  patch: GapPatchRequest
): Promise<GapResponse> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/gaps/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch gap entry: ${res.status}`)
  return res.json()
}
