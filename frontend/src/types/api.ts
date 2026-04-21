// Document statuses
export type DocumentStatus = "pending" | "processing" | "extracting" | "done" | "error" | "partial"
export type FeatureStatus = "extracting" | "done"
export type FeatureType = "kafka_consumer" | "rest_endpoint" | "scheduled_task" | "unknown"

// Structured business logic from 1st Claude call
export interface ParameterField {
  name: string
  field_type: string
  description: string
  required: boolean
  validation_rules: string[]
  param_in: string | null
  example?: string | null
  children: ParameterField[]
}

export interface MessageField {
  element: string
  parent: string | null
  field_type: string | null
  required: boolean
  cardinality?: string | null
  is_collection?: boolean
  description?: string | null
  source?: string | null
  example?: string | null
  children: MessageField[]
}

export interface GenericTable {
  caption?: string | null
  headers: string[]
  rows: string[][]
}

export interface LogicStep {
  number: string
  text: string
  has_detailed_mapping?: boolean
  message_mapping?: MessageField[] | null
  reference_tables?: GenericTable[]
  external_doc_refs?: string[]
  children: LogicStep[]
}

export interface UsedDependency {
  type: "db_table" | "external_api" | "cache" | "kafka_topic" | "external_doc"
  name: string
  description: string
  method?: string
  service_name?: string
  path?: string
}

export interface ErrorResponseSchema {
  status_codes: string
  description: string
  parameters: ParameterField[]
}

export interface StructuredBusinessLogic {
  input_parameters?: ParameterField[]
  output_parameters?: ParameterField[]  // kept for backward compat with old data
  success_response?: ParameterField[]
  error_responses?: ErrorResponseSchema[]
  logic_steps?: LogicStep[]
  used_dependencies?: UsedDependency[]
  error_handling?: Record<string, unknown>
  business_rules?: string[]
}

// Source provenance for a feature
export interface SourceInfo {
  kind: "pdf" | "code"
  document: string | null
  file: string | null
  line: number | null
}

// Feature response — keyed by name (no numeric id)
export interface FeatureResponse {
  name: string
  display_name: string | null
  source_document: string | null  // doc slug for pdf features; null for code
  source: SourceInfo | null
  type: FeatureType
  confidence: number
  summary: string | null
  status: FeatureStatus
  method: string | null
  endpoint: string | null
  schedule: string | null
  structured_logic: StructuredBusinessLogic | null
  gap_count?: number
  pending_gap_count?: number
  gaps_running?: boolean
  apply_running?: boolean
  test_case_count?: number
  pending_test_case_count?: number
  test_cases_running?: boolean
  bug_count?: number
}

// Background tasks (per-project log)
export type TaskKind = "extraction" | "gaps" | "apply_gaps" | "test_cases" | "enrichment"
export type TaskStatus = "running" | "done" | "error"
export type TaskTargetType = "document" | "feature" | "dependency"

export interface TaskRecord {
  id: string
  kind: TaskKind
  target_type: TaskTargetType
  target_id: string
  status: TaskStatus
  started_at: string
  finished_at: string | null
  error_message: string | null
  duration_ms: number | null
}

export interface TaskListResponse {
  tasks: TaskRecord[]
}

export interface FeaturePatchRequest {
  name?: string
  type?: string
  method?: string
  endpoint?: string
  summary?: string
  structured_logic_json?: Record<string, unknown>
}

export interface CreateDependencyRequest {
  dep_type: DependencyType
  name: string
  description: string
  method?: string
  service_name?: string
  path?: string
}

export interface PatchDependencyRequest {
  name?: string
  description?: string
  method?: string
  service_name?: string
  path?: string
}

// Document response — keyed by slug
export interface DocumentResponse {
  slug: string
  project_slug: string
  filename: string
  status: DocumentStatus
  pdf_size_bytes: number
  feature_count: number
  features: FeatureResponse[]
  uploaded_at: string
  error_message: string | null
}

// Document patch
export interface DocumentPatchRequest {
  filename: string
}

// Project — keyed by slug
export interface ProjectResponse {
  slug: string
  name: string
  created_at: string
  document_count: number
  feature_count: number
  status: "empty" | "pending" | "processing" | "done" | "partial"
  is_linked: boolean
  external_path: string | null
  available: boolean
}

export interface LinkProjectRequest {
  path: string
}

export interface ImportContextResponse {
  project: ProjectResponse
  adapted_features: number
  warnings: string[]
}

export interface CreateProjectRequest {
  name: string
}

export interface PatchProjectRequest {
  name: string
}

// Export
export interface ExportRequest {
  target_path?: string
  feature_name?: string
}

export interface ExportResponse {
  exported_features: string[]
  target_path: string
  files_written: string[]
}

// Dependency types (v1.1)
export type DependencyType = "db_table" | "external_api" | "cache" | "kafka_topic" | "external_doc"
export type DependencyStatus = "stub" | "enriched" | "error" | "running"

export interface ProjectDependency {
  project_slug: string
  dep_type: DependencyType
  name: string
  description: string | null
  enrichment_status: DependencyStatus
  enriched_data: DbTableEnrichment | ExternalApiEnrichment | CacheEnrichment | KafkaTopicEnrichment | ExternalDocEnrichment | null
  source_pdf_name: string | null
  enriched_at: string | null
  created_at: string
  method: string | null
  service_name: string | null
  path: string | null
}

// DB enrichment types
export interface DbColumnInfo {
  name: string
  col_type: string
  nullable: boolean
  description: string
  is_pk: boolean
  is_fk: boolean
  fk_references: string | null
}

export interface DbTableEnrichment {
  table_name: string
  description: string
  columns: DbColumnInfo[]
  indexes: string[]
  business_notes: string[]
}

// API enrichment types
export interface ApiParamInfo {
  name: string
  param_in: string
  param_type: string
  required: boolean
  description: string
}

export interface ApiEndpointInfo {
  method: string
  path: string
  description: string
  params: ApiParamInfo[]
  request_body_schema: Record<string, unknown> | null
  response_schema: Record<string, unknown> | null
  error_codes: string[]
}

export interface ExternalApiEnrichment {
  api_name: string
  base_url: string | null
  description: string
  endpoints: ApiEndpointInfo[]
}

// Cache enrichment types
export interface CacheKeyPattern {
  pattern: string
  description: string
  ttl_seconds: number | null
  value_structure: Record<string, unknown> | null
}

export interface CacheEnrichment {
  cache_name: string
  description: string
  key_patterns: CacheKeyPattern[]
  eviction_policy: string | null
  notes: string[]
}

// Kafka topic enrichment types
export interface KafkaTopicEnrichment {
  topic_name: string
  description: string
  message_fields: MessageField[]
  key_fields: MessageField[]
  partitions: number | null
  retention_ms: number | null
  notes: string[]
}

// External document enrichment (verbatim sanitized HTML of a reference doc)
export interface ExternalDocEnrichment {
  doc_name: string
  description: string
  content_html: string
}

// Gaps types (v1.1 Phase 6)
export type GapStatus = "pending" | "approved" | "clarified" | "applied"
export type GapType = string

export type GapSeverity = "critical" | "major"

export interface GapItem {
  gap_type: GapType
  severity: GapSeverity
  actionable: boolean
  question: string
  suggestion: string
  status: GapStatus
  analyst_text: string | null
}

export interface GapsResponse {
  gaps: GapItem[]
  gaps_running: boolean
  gaps_run_at: string | null
}

export interface ApplyChange {
  section: string
  action: "added" | "modified" | "removed"
  location: string
  description: string
  detail: string
  gap_index: number
}

export interface ApplyPreviewData {
  status: "running" | "done" | "error" | null
  original: StructuredBusinessLogic
  proposed: StructuredBusinessLogic
  changes: ApplyChange[]
  error?: string
}

// Test Cases types (v1.1 Phase 6 / quick-260329-ski)
export type TestCaseStatus = "pending" | "approved" | "edited"
export type TestCaseCategory = "validation" | "positive" | "negative" | "edge_case"

export interface TestStep {
  action: string
  expected: string
}

export interface TestCaseItem {
  category: TestCaseCategory
  name: string
  preconditions: string
  steps: TestStep[]
  expected_result: string
  priority: "high" | "medium" | "low"
  status: TestCaseStatus
  analyst_text: string | null
  curl_command: string | null
  kafka_message: { key: string; value: string } | null
  sql_setup: string | null
  mock_config: string | null
}

export interface TestCasesResponse {
  test_cases: TestCaseItem[]
  test_cases_running: boolean
  test_cases_run_at: string | null
}

// Bug Report types
export type BugStatus = "open" | "fixed" | "verified"
export type BugSeverity = "critical" | "major" | "minor" | "trivial"

export interface BugStep {
  action: string
  result: string
  curl_command: string | null
  sql_query: string | null
  kafka_message: string | null
}

export interface BugItem {
  title: string
  test_case_name: string
  severity: BugSeverity
  steps: BugStep[]
  expected_result: string
  actual_result: string
  status: BugStatus
  analyst_text: string | null
  created_at: string
}

export interface BugsResponse {
  bugs: BugItem[]
  bug_count: number
}
