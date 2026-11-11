// Document statuses
export type DocumentStatus = "pending" | "processing" | "extracting" | "done" | "error" | "partial"
export type FeatureStatus = "extracting" | "done"
export type FeatureType = "kafka_consumer" | "rest_endpoint" | "scheduled_task" | "unknown"

export interface FieldSourceRef {
  dep_type: string
  dep_name: string
  field: string | null
}

// A spec table mirrored verbatim: columns as the spec has them, rows as a field tree
export interface SpecColumn {
  header: string
  role?: string | null // type | required | constraint | source | description | example
}

export interface SpecField {
  name: string
  cells: string[] // aligned with the owning table's columns
  source_refs?: FieldSourceRef[]
  children?: SpecField[]
}

export interface SpecTable {
  table_id?: string | null
  caption?: string | null
  location?: string | null // body | header | query | path
  status_codes?: string | null // for response tables
  columns: SpecColumn[]
  fields: SpecField[]
}

// Hierarchical message field — used by dependency enrichment payloads
export interface MessageField {
  element: string
  parent: string | null
  field_type: string | null
  required: boolean
  cardinality?: string | null
  is_collection?: boolean
  description?: string | null
  source?: string | null
  /** Dependencies the source cell linked to, parsed from the spec table. */
  source_refs?: FieldSourceRef[]
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
  message_type?: string | null
  mapping_tables?: SpecTable[]
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

export interface StructuredBusinessLogic {
  input_tables?: SpecTable[]
  response_tables?: SpecTable[]
  logic_steps?: LogicStep[]
  used_dependencies?: UsedDependency[]
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
  impl_status?: "queued" | "running" | "implemented" | "no_changes_needed" | "failed" | null
  impl_jira_key?: string | null
  impl_mr_url?: string | null
  impl_summary?: string | null
  impl_error?: string | null
  /** No longer present in the latest version of the source spec page */
  orphaned?: boolean
  /** Gaps were computed against an older spec version */
  gaps_stale?: boolean
  /** Test cases were computed against an older spec version */
  test_cases_stale?: boolean
  /** e.g. "v12 → v15" — which spec versions the stale flags refer to */
  stale_spec_note?: string | null
}

// Background tasks (per-project log)
export type TaskKind =
  | "extraction"
  | "gaps"
  | "apply_gaps"
  | "test_cases"
  | "tc_assistant"
  | "enrichment"
  | "implement"
  | "bugs"
  | "bug_fix"
  | "dsl_script"
  /** legacy rows: Java autotests, replaced by dsl_script */
  | "autotest_gen"
export type TaskStatus = "running" | "done" | "error"
export type TaskTargetType = "document" | "feature" | "dependency" | "service" | "repo"

export interface TaskRecord {
  id: string
  kind: TaskKind
  target_type: TaskTargetType
  target_id: string
  status: TaskStatus
  started_at: string
  finished_at: string | null
  error_message: string | null
  result_message: string | null
  result_data: Record<string, unknown> | null
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

// Spec diff (deterministic; computed by the backend on re-extraction)
export interface SpecCellChange {
  column: string
  old: string
  new: string
}

export interface SpecFieldChange {
  name: string
  changes: SpecCellChange[]
}

export interface SpecTableDiff {
  section: string
  caption: string | null
  /** Present when a whole table appeared/disappeared */
  table?: "added" | "removed"
  added_fields?: string[]
  removed_fields?: string[]
  changed_fields?: SpecFieldChange[]
}

export interface SpecStepChange {
  number: string
  old_text: string
  new_text: string
}

export interface SpecStepsDiff {
  added: { number: string; text: string }[]
  removed: { number: string; text: string }[]
  changed: SpecStepChange[]
  /** Same verbatim text under a new number (e.g. after an inserted step) — non-material */
  renumbered?: { old_number: string; new_number: string; text: string }[]
  /** Step split into sub-steps (or merged back) with identical verbatim text — non-material */
  resliced?: { number: string }[]
}

export interface SpecDepsDiff {
  added: { type: string; name: string }[]
  removed: { type: string; name: string }[]
  /** Same link target / containing name — a rename, non-material */
  renamed?: { type: string; old_name: string; new_name: string }[]
}

export interface FeatureDiff {
  name: string
  display_name: string | null
  material: boolean
  identity: { field: string; old: string; new: string }[]
  summary_changed: boolean
  tables: SpecTableDiff[]
  steps: SpecStepsDiff | null
  dependencies: SpecDepsDiff | null
}

export interface SpecDiff {
  computed_at: string
  old_version: number | null
  new_version: number | null
  material: boolean
  /** Page text identical to the previous import — every difference is LLM noise */
  source_unchanged?: boolean
  added: string[]
  removed: string[]
  changed: FeatureDiff[]
  unchanged: string[]
}

// Document response — keyed by slug
export interface DocumentResponse {
  slug: string
  project_slug: string
  filename: string
  status: DocumentStatus
  source_type?: "pdf" | "confluence"
  pdf_size_bytes: number
  feature_count: number
  features: FeatureResponse[]
  uploaded_at: string
  error_message: string | null
  confluence_url?: string | null
  confluence_version?: number | null
  latest_confluence_version?: number | null
  spec_checked_at?: string | null
  spec_outdated?: boolean
  last_diff?: SpecDiff | null
  /** Dependencies of this doc's features whose source page moved ahead */
  deps_outdated?: string[]
}

export interface SpecUpdateCheck {
  slug: string
  filename: string
  confluence_url: string | null
  current_version: number | null
  latest_version: number | null
  outdated: boolean
  error: string | null
}

export interface DepSourceCheck {
  dep_type: string
  name: string
  source_page_url: string | null
  current_version: number | null
  latest_version: number | null
  outdated: boolean
  error: string | null
}

export interface SpecUpdatesResponse {
  checked: number
  outdated: number
  documents: SpecUpdateCheck[]
  dependencies_checked?: number
  dependencies_outdated?: number
  dependencies?: DepSourceCheck[]
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

// Dependency types (v1.1)
export type DependencyType = "db_table" | "external_api" | "cache" | "kafka_topic" | "external_doc"
export type DependencyStatus = "stub" | "enriched" | "error" | "running"

// Deterministic diff of a dependency's enrichment vs the previous one
export interface DepItemsDiff {
  added: string[]
  removed: string[]
  changed: { name: string; changes: { field: string; old: string; new: string }[] }[]
}

export interface DepSourceDiff {
  computed_at: string
  old_version: number | null
  new_version: number | null
  columns?: DepItemsDiff
  endpoints?: DepItemsDiff
  message_fields?: DepItemsDiff
  key_patterns?: DepItemsDiff
  content_changed?: boolean
}

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
  /** Source-page provenance + version tracking (Confluence-enriched deps) */
  source_page_id?: string | null
  source_page_version?: number | null
  source_page_url?: string | null
  latest_source_version?: number | null
  source_checked_at?: string | null
  source_outdated?: boolean
  last_source_diff?: DepSourceDiff | null
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
interface ApiParamInfo {
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
export type GapStatus = "pending" | "approved" | "clarified" | "rejected" | "applied"
export interface GapEvidence {
  source_id: string
  location: string
  quote: string
}

export interface GapSource {
  id: string
  title: string
  url: string | null
  version: number | null
  content_hash: string
}

export interface GapItem {
  id: string
  text: string
  status: GapStatus
  analyst_text: string | null
  evidence: GapEvidence[]
  source_snapshots: GapSource[]
  presence?: "current" | "not_detected" | "unverified"
  needs_review?: boolean
}

export interface GapAnalysis {
  coverage: "complete" | "partial"
  finished_at: string
}

export interface GapsResponse {
  gaps: GapItem[]
  gaps_running: boolean
  gaps_run_at: string | null
  analysis: GapAnalysis | null
  job: { stage: string; error: string | null } | null
  stale: boolean
  configured: boolean
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

/** One step of a ru-dsl scenario run on the test stand */
export interface ScriptRunStep {
  keyword: string
  text: string
  status: "passed" | "failed" | "skipped" | "undefined" | "pending" | "ambiguous"
  error?: string | null
  /** set when the tag matched several scenarios (a scenario outline) */
  scenario?: string
}

export interface TestStep {
  action: string
  expected: string
}

export interface TestCaseItem {
  /** Stable id: list positions shift when a case is deleted */
  id: string
  category: TestCaseCategory
  name: string
  preconditions: string
  steps: TestStep[]
  expected_result: string
  priority: "high" | "medium" | "low"
  status: TestCaseStatus
  analyst_text: string | null
  origin?: "ask" | null
  covers?: string | null
  curl_command: string | null
  kafka_message: { key: string; value: string } | null
  sql_setup: string | null
  mock_config: string | null
  /** ru-dsl-v2 scenario written for the accepted case */
  script_status?: "queued" | "running" | "generated" | "failed" | null
  script_mr_url?: string | null
  script_summary?: string | null
  script_error?: string | null
  /** .feature file in the ru-dsl-v2 repo */
  script_path?: string | null
  /** the scenario as committed; null if it could not be read back */
  script_text?: string | null
  /** run of the scenario on the test stand; `error` = could not be run at all */
  script_run_status?: "queued" | "running" | "passed" | "failed" | "error" | null
  script_run_error?: string | null
  script_run_steps?: ScriptRunStep[] | null
  script_run_finished_at?: string | null
}

export interface TestCasesResponse {
  test_cases: TestCaseItem[]
  test_cases_running: boolean
  test_cases_run_at: string | null
  last_ask_message: string | null
  last_ask_at: string | null
  last_ask_covered_by: string[]
}

// Test-case assistant (chat about one feature's cases)
export type AssistantTurnStatus = "queued" | "running" | "done" | "error" | "cancelled"

/** Context pinned to a message: a case, or a failed run of one of its artifacts. */
export interface AssistantAttachment {
  kind: "case" | "sql_error" | "http_result" | "mock_error"
  case_id: string
  error?: string | null
  failed_statement?: number | null
  status_code?: number | null
  reason?: string | null
  url?: string | null
  body?: string | null
}

/** One thing the assistant did on the stand. */
export interface AssistantAction {
  id: string
  kind: "sql" | "http" | "wiremock_upload" | "wiremock_mappings" | "wiremock_requests"
  title: string
  case_id: string | null
  /** true = the action changed the stand */
  write: boolean
  status: "ok" | "error" | "blocked"
  summary: string
  detail: string
  duration_ms: number | null
  at: string
}

export interface AssistantChange {
  id: string
  kind: "edit" | "add"
  case_id: string
  case_name: string
  summary: string
  fields?: string[]
  before?: Record<string, unknown>
  after?: Record<string, unknown>
  state: "applied" | "reverted"
  /** How an edited SQL was checked on the stand before saving */
  stand_check?: { status: "ok" | "skipped"; summary?: string; duration_ms?: number | null }
}

export interface AssistantFailure {
  case_id: string
  case_name: string
  field: string
  attempts: number
  error: string
}

export interface AssistantSuggestion {
  id: string
  kind: "delete" | "bug"
  case_id: string
  case_name: string
  text: string
  state: "open" | "accepted" | "dismissed"
}

export interface AssistantTurn {
  id: string
  session_id: string
  status: AssistantTurnStatus
  created_at: string
  text: string
  attachments: AssistantAttachment[]
  author: string | null
  stage: "waiting" | "thinking" | "acting" | "verifying" | "saving" | null
  current: string | null
  started_at?: string
  finished_at?: string
  actions: AssistantAction[]
  reply?: string
  cause?: string | null
  changes?: AssistantChange[]
  failures?: AssistantFailure[]
  suggestions?: AssistantSuggestion[]
  case_refs?: { case_id: string; case_name: string }[]
  /** #N in the reply → case id, as numbered when the message was answered */
  numbering?: Record<string, string>
  error?: string
}

export interface AssistantSessionSummary {
  id: string
  title: string
  author: string | null
  created_at: string
  updated_at: string
  turn_count: number
  state: "running" | "queued" | "idle"
}

export interface AssistantSession extends Omit<AssistantSessionSummary, "turn_count" | "state"> {
  turns: AssistantTurn[]
}

export interface AssistantOverview {
  sessions: AssistantSessionSummary[]
  stand: {
    sql: boolean
    database: string | null
    write_schemas: string[]
    http: boolean
    service: string | null
    wiremock: boolean
  }
  /** false = Codex is switched off on the server */
  enabled: boolean
}

// Test DB (SQL artifact execution) types
export interface TestDbStatus {
  configured: boolean
  host: string | null
  database: string | null
}

export interface SqlStatementResult {
  statement: string
  status: string
  columns: string[] | null
  rows: (string | number | boolean | null)[][] | null
  truncated: boolean
}

export interface SqlExecuteResponse {
  results: SqlStatementResult[]
  error: string | null
  failed_statement: number | null
  duration_ms: number
}

// Test stand (curl artifact execution) types
export interface TestStandStatus {
  configured: boolean
  base_url: string | null
  service: string | null
  target_base: string | null
}

export interface HttpExecuteRequest {
  method: string
  path: string
  headers: Record<string, string>
  body: string | null
}

export interface HttpExecuteResponse {
  url: string
  method: string
  status_code: number | null
  reason: string | null
  headers: { name: string; value: string }[]
  body: string | null
  body_truncated: boolean
  duration_ms: number
  error: string | null
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
  jira_key?: string | null
  jira_url?: string | null
  jira_status?: string | null
  fix_status?: "queued" | "running" | "fix_proposed" | "failed" | null
  fix_service?: string | null
  fix_branch?: string | null
  fix_mr_url?: string | null
  fix_summary?: string | null
  fix_error?: string | null
}

export interface BugsResponse {
  bugs_running?: boolean
  generation_error?: string | null
  bugs: BugItem[]
  bug_count: number
  jira_configured?: boolean
}
