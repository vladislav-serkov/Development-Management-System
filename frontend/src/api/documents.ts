import type { DocumentResponse, DocumentPatchRequest, RegistryResponse, GapResponse, ExportRequest, ExportResponse } from "@/types/api"

const API_BASE = "/api"

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

export async function uploadDocument(file: File): Promise<DocumentResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const res = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: fd })
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
