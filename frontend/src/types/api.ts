// Document statuses
export type DocumentStatus = "pending" | "processing" | "extracting" | "done" | "error" | "partial"
export type FeatureStatus = "detected" | "extracting" | "done" | "error"
export type FeatureType = "kafka_consumer" | "rest_endpoint" | "scheduled_task" | "unknown"

// Structured business logic from 1st Claude call (D-06, D-09)
export interface ProcessingStep {
  step: number
  action: string
  description: string
}

export interface StructuredBusinessLogic {
  processing_steps?: ProcessingStep[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  error_handling?: Record<string, unknown>
  external_api_calls?: Record<string, unknown>[]
  database_operations?: Record<string, unknown>[]
  cache_operations?: Record<string, unknown>[]
  business_rules?: string[]
}

// Feature response
export interface FeatureResponse {
  id: number
  name: string
  type: FeatureType
  confidence: number
  summary: string | null
  status: FeatureStatus
  business_logic: Record<string, unknown> | null   // free JSON from 2nd call (CodeMirror viewer)
  structured_logic: StructuredBusinessLogic | null  // structured from 1st call (cards/tables)
  overview_md: string | null
}

// Document response
export interface DocumentResponse {
  id: number
  filename: string
  status: DocumentStatus
  pdf_size_bytes: number
  feature_count: number
  features: FeatureResponse[]
  uploaded_at: string
  error_message: string | null
}

// Document patch (D-03/D-15 — editable project name)
export interface DocumentPatchRequest {
  filename: string
}

// Registry (dependencies)
export interface RegistryResponse {
  db: Record<string, unknown>[]
  external_api: Record<string, unknown>[]
  cache: Record<string, unknown>[]
}

// Gap
export interface GapResponse {
  id: number
  category: string
  name: string
  affected_features: string[]
  what_missing: string
  priority: "critical" | "medium" | "low"
  suggestion: Record<string, unknown> | null
}

// Export
export interface ExportRequest {
  target_path: string
  feature_name?: string
}

export interface ExportResponse {
  files: string[]
  target_path: string
}

// SSE progress event
export interface ProgressEvent {
  type: "progress" | "done" | "error"
  status?: DocumentStatus
  feature_count?: number
  features?: { id: number; name: string; type: string; status: FeatureStatus }[]
  message?: string
}
