from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema

# ``SkipJsonSchema`` marks fields the LLM never fills: they stay in the stored
# shape but are left out of the structured-output schema. This is also what keeps
# the schema free of recursion (the API rejects self-referencing definitions):
# the LLM returns trees as flat lists, and ``nest_steps`` / ``nest_message_fields``
# rebuild ``children`` in code.


class FeatureType(str, Enum):
    kafka_consumer = "kafka_consumer"
    rest_endpoint = "rest_endpoint"
    scheduled_task = "scheduled_task"
    unknown = "unknown"


class SourceInfo(BaseModel):
    """Provenance of a feature: where it came from.

    PDF-sourced features fill ``document`` (PDF slug). Code-sourced features
    fill ``file`` and ``line`` (repo-relative path + 1-based annotation line).
    """

    kind: Literal["pdf", "code"]
    document: str | None = Field(default=None, description="PDF document slug, for pdf-sourced features")
    file: str | None = Field(default=None, description="Repo-relative path to the entry-point file, for code-sourced features")
    line: int | None = Field(default=None, description="1-based annotation line number, for code-sourced features")


class FieldSourceRef(BaseModel):
    """Machine-readable origin of a mapped field, parsed from a link in the spec's
    "Источник" cell: "credit_line[→DB page].id" → this table's ``id`` column.

    Unlike the free-text ``source``, this survives as a link: the UI can jump to the
    dependency, and a field pointing at a column the enriched dependency doesn't have
    is a spec/DB mismatch that needs no LLM to detect.
    """

    dep_type: str = Field(description="db_table, external_api, cache, kafka_topic, external_doc")
    dep_name: str = Field(description="Dependency name verbatim from used_dependencies")
    field: str | None = Field(default=None, description="Field/column inside the dependency, e.g. 'mrp_day'")


class SpecColumn(BaseModel):
    """One data column of a spec table, verbatim.

    ``role`` is a normalized annotation derived from header synonyms — it is what
    gives a column semantics (clickable source links, required highlighting)
    without constraining which columns a spec may have. ``None`` = unrecognized
    column, still stored and rendered verbatim.
    """

    header: str = Field(description="Column header verbatim from the spec table")
    role: str | None = Field(default=None, description="Normalized column role: type, required, constraint, source, description, example. Null for unrecognized columns.")


class SpecField(BaseModel):
    """One row of a spec table: a field with its cells verbatim.

    ``cells`` is positionally aligned with the owning table's ``columns``;
    empty cells are empty strings. Nesting mirrors the spec's colspan depth.
    """

    name: str = Field(description="Field name from the name column, verbatim")
    cells: list[str] = Field(default_factory=list, description="Cell values verbatim, aligned with the table's columns")
    source_refs: list[FieldSourceRef] = Field(
        default_factory=list,
        description="Dependencies the source cell links to, parsed deterministically from [LINK:Ln] markers",
    )
    children: list["SpecField"] = Field(default_factory=list)


class SpecTable(BaseModel):
    """A parameter/mapping table mirroring the spec's own structure.

    The LLM only references the table (``table_id`` from its [TABLE:Tn] marker,
    plus ``status_codes`` for response tables); the grid is parsed
    deterministically and ``caption``/``location``/``columns``/``fields`` are
    filled by code.
    """

    table_id: str | None = Field(default=None, description="Id from the [TABLE:Tn] marker above the table, e.g. 'T3'")
    caption: SkipJsonSchema[str | None] = Field(default=None, description="Text introducing the table, verbatim. Filled by code from the parsed document.")
    location: SkipJsonSchema[str | None] = Field(default=None, description="Where the fields live: body, header, query, path. Derived from the caption by code.")
    status_codes: str | None = Field(default=None, description="For response tables: HTTP status codes from the heading above, verbatim, e.g. '200' or '400, 404, 500'. Null for input tables.")
    columns: SkipJsonSchema[list[SpecColumn]] = Field(default_factory=list, description="Data columns verbatim. Filled by code.")
    fields: SkipJsonSchema[list[SpecField]] = Field(default_factory=list, description="Field rows. Filled by code.")


class MessageField(BaseModel):
    """Hierarchical message field. Used by dependency enrichment only —
    feature structured logic stores tables as SpecTable."""

    element: str = Field(description="Field/element name")
    parent: str | None = Field(default=None, description="Element name of the enclosing (parent) field; null for top-level fields. Fields are listed in document order, each right after its parent subtree started")
    field_type: str | None = Field(default=None, description="Data type")
    required: bool | None = Field(default=None, description="Verbatim from spec table 'Обяз.' column: true/false. Null if no such column in spec.")
    cardinality: str | None = Field(default=None, description="Verbatim cardinality from spec table: '1', '0-1', '1-N', '0-N'. Null if not present in spec.")
    is_collection: bool = Field(default=False, description="True if this field is a list/array based on direct textual cues in the spec")
    description: str | None = Field(default=None, description="What this field is, in Russian from the spec")
    source: str | None = Field(default=None, description="Where the value comes from, in Russian from the spec")
    source_refs: list[FieldSourceRef] = Field(
        default_factory=list,
        description="Dependencies the source cell links to, parsed deterministically from the spec table. A field can draw on several (availableLimit = credit_line.limit - Debt.totalDebt).",
    )
    example: str | None = Field(default=None, description="Sample value for this field. Extract from spec if given, otherwise synthesise a realistic one based on type. Null for container fields whose value is represented by children.")
    children: SkipJsonSchema[list["MessageField"]] = Field(default_factory=list)


class GenericTable(BaseModel):
    """Reference / lookup table from the spec that is NOT a field mapping.

    Examples: enum value → action mapping, error code reference, status matrix.
    Stored verbatim as headers + rows so the original table structure is preserved
    without forcing it into the MessageField schema.
    """

    caption: str | None = Field(default=None, description="Optional table title/caption from the spec, in Russian")
    headers: list[str] = Field(description="Column headers verbatim from the spec, in order")
    rows: list[list[str]] = Field(description="Data rows; each row has len(headers) cells as strings")


class LogicStep(BaseModel):
    """One step of the feature logic. The LLM returns steps as a flat list in
    document order; nesting is rebuilt from ``number`` (see ``nest_steps``)."""

    number: str = Field(description="Hierarchical step number in document order: '1', '1.1', '1.1.2'. The number encodes nesting — a step numbered '2.3' is a sub-step of '2'")
    text: str = Field(description="Step text verbatim from the specification, in Russian")
    has_detailed_mapping: bool = Field(default=False, description="True if this step fills a message/record field by field (its mapping table ids go to mapping_table_ids)")
    mapping_table_ids: list[str] = Field(
        default_factory=list,
        description="IDs from [TABLE:Tn] markers of the tables holding this step's field mapping, e.g. ['T3']",
    )
    message_type: str | None = Field(default=None, description="Target table/message type name, e.g. 'outbox_payment'")
    mapping_tables: SkipJsonSchema[list[SpecTable]] = Field(default_factory=list, description="Mapping tables of this step. Filled by code from mapping_table_ids.")
    reference_tables: list[GenericTable] = Field(
        default_factory=list,
        description="Reference/lookup tables attached to this step (enum value mappings, code reference tables, etc.) — NOT field mappings.",
    )
    external_doc_refs: list[str] = Field(
        default_factory=list,
        description="Names of external documents referenced in this step. Must exactly match names in used_dependencies (type=external_doc).",
    )
    children: SkipJsonSchema[list["LogicStep"]] = Field(default_factory=list)


class UsedDependency(BaseModel):
    type: str = Field(description="db_table, external_api, cache, kafka_topic, or external_doc")
    name: str = Field(description="Name: table name, cache structure name, Kafka topic name, endpoint path for external_api, or document title for external_doc")
    description: str = Field(description="What it's used for, in Russian")
    method: str | None = Field(default=None, description="HTTP method for external_api: GET/POST/PUT/DELETE/PATCH")
    service_name: str | None = Field(default=None, description="Service name for external_api, e.g. flp-credit-line")
    path: str | None = Field(default=None, description="Endpoint path for external_api, e.g. /v1/credit-line")
    link_ids: list[str] = Field(
        default_factory=list,
        description="IDs from [LINK:Ln] markers in the document pointing at the page that documents this dependency, e.g. ['L5']. Fill for every dependency mentioned via a link. Empty if mentioned without a link.",
    )
    source_doc_title: SkipJsonSchema[str | None] = Field(default=None, description="Legacy fallback for link_ids: the link text of the page documenting this dependency. Filled by code.")


SpecField.model_rebuild()
MessageField.model_rebuild()
LogicStep.model_rebuild()


def _parent_number(number: str) -> str | None:
    head, sep, _ = number.strip().rstrip(".").rpartition(".")
    return head if sep else None


def nest_steps(flat: list[LogicStep]) -> list[LogicStep]:
    """Rebuild the step tree from a flat, document-ordered list.

    A step whose number has a dotted prefix ('2.3' → '2') becomes a child of the
    nearest preceding step with that number; a step whose prefix is unknown is
    attached to the step one level up in the current path, or to the root. Steps
    that already carry children are returned as they are.
    """
    if any(step.children for step in flat):
        return flat
    roots: list[LogicStep] = []
    path: list[LogicStep] = []  # current ancestor chain
    for step in flat:
        step.children = []
        parent_num = _parent_number(step.number)
        while path and path[-1].number != parent_num:
            path.pop()
        if parent_num is not None and not path:
            # Prefix never seen (numbering gap in the spec): nest under the last
            # step shallower than this one, so the document order is kept.
            depth = step.number.count(".")
            path = [s for s in _last_chain(roots) if s.number.count(".") < depth]
        (path[-1].children if path else roots).append(step)
        path.append(step)
    return roots


def _last_chain(roots: list[LogicStep]) -> list[LogicStep]:
    chain: list[LogicStep] = []
    nodes = roots
    while nodes:
        chain.append(nodes[-1])
        nodes = nodes[-1].children
    return chain


def nest_message_fields(flat: list[MessageField]) -> list[MessageField]:
    """Rebuild the message field tree from a flat, document-ordered list using
    ``parent``: each field attaches to the nearest open ancestor with that
    element name, so repeated element names in different branches stay apart."""
    if any(field.children for field in flat):
        return flat
    roots: list[MessageField] = []
    path: list[MessageField] = []
    for field in flat:
        field.children = []
        if field.parent:
            while path and path[-1].element != field.parent:
                path.pop()
        else:
            path = []
        (path[-1].children if path else roots).append(field)
        path.append(field)
    return roots


class StructuredBusinessLogic(BaseModel):
    """Feature logic mirroring the Confluence spec structure: parameter tables
    verbatim (grouped the way the spec groups them), logic steps, dependencies."""

    input_tables: list[SpecTable] = Field(
        default_factory=list,
        description="Tables of the 'Входные параметры' section, one entry per table (a spec may split input by Header/query/body). For Kafka: the incoming message structure tables.",
    )
    response_tables: list[SpecTable] = Field(
        default_factory=list,
        description="Tables of the 'Выходные параметры' section, one entry per table, each tagged with its HTTP status_codes ('200', '400, 404, 500'). Empty for Kafka/scheduled tasks.",
    )
    logic_steps: list[LogicStep] = Field(default_factory=list)
    used_dependencies: list[UsedDependency] = Field(default_factory=list)


class ConfluenceImportRequest(BaseModel):
    url: str = Field(min_length=1, description="Confluence page URL (or bare pageId)")


class DetectedFeature(BaseModel):
    """Feature detected from a spec page by the extraction call (structured output schema)."""

    name: str = Field(description="Identifier: the Kafka topic name, 'METHOD /path' for REST, or a latin snake_case slug derived from the scheduled-task heading (unique within the document)")
    display_name: str | None = Field(default=None, description="Human-readable name verbatim from the spec (Russian). Required for scheduled_task (heading of the task section). Null for kafka_consumer/rest_endpoint — UI falls back to name.")
    type: FeatureType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(description="One-paragraph summary of what the feature does, in Russian")
    method: str | None = Field(default=None, description="HTTP method for REST (GET/POST/PUT/DELETE), CONSUMER for Kafka, SCHEDULED for scheduled_task")
    endpoint: str | None = Field(default=None, description="REST path like /v1/credit-line or Kafka topic like pay-later.flp.rbo-adapter.product.return.queue. Null for scheduled_task — use `schedule` instead.")
    schedule: str | None = Field(default=None, description="Trigger schedule verbatim from the spec (Russian). Examples: 'Ежедневно в 19:00 МСК', 'Каждый час'. Required for scheduled_task, null otherwise.")
    dependencies: SkipJsonSchema[list[str]] = Field(default_factory=list, description="Names of used_dependencies. Derived by code.")
    source: SkipJsonSchema[SourceInfo | None] = Field(default=None, description="Provenance: pdf or code. Null for legacy records where kind is inferred from source_document presence.")
    structured_logic: StructuredBusinessLogic

    def nest(self) -> "DetectedFeature":
        """Turn the flat LLM output into the stored shape: step tree, dependency names."""
        self.structured_logic.logic_steps = nest_steps(self.structured_logic.logic_steps)
        self.dependencies = [d.name for d in self.structured_logic.used_dependencies]
        return self


class FeatureDetectionResult(BaseModel):
    """Root model of the extraction call's structured output."""

    features: list[DetectedFeature]


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    extracting = "extracting"
    done = "done"
    error = "error"
    partial = "partial"


class FeatureStatus(str, Enum):
    extracting = "extracting"
    done = "done"


class FeaturePatchRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    method: str | None = None
    endpoint: str | None = None
    summary: str | None = None
    structured_logic_json: dict | None = None


class FeatureResponse(BaseModel):
    """HTTP response model for a single feature."""

    name: str
    display_name: str | None = None
    source_document: str | None = None  # doc slug for pdf features; null for code features
    source: SourceInfo | None = None
    type: str
    confidence: float
    summary: str | None = None
    status: str
    method: str | None = None
    endpoint: str | None = None
    schedule: str | None = None
    structured_logic: dict | None = None  # from structured_logic_json field
    gap_count: int = 0
    pending_gap_count: int = 0
    gaps_running: bool = False
    apply_running: bool = False
    test_case_count: int = 0
    pending_test_case_count: int = 0
    test_cases_running: bool = False
    bug_count: int = 0
    impl_status: str | None = None
    impl_jira_key: str | None = None
    impl_mr_url: str | None = None
    impl_summary: str | None = None
    impl_error: str | None = None
    orphaned: bool = False
    gaps_stale: bool = False
    test_cases_stale: bool = False
    stale_spec_note: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    """HTTP response model for a document with its features."""

    slug: str
    project_slug: str
    filename: str
    status: str
    source_type: str = "pdf"  # "pdf" | "confluence"
    pdf_size_bytes: int
    feature_count: int
    features: list[FeatureResponse]
    uploaded_at: datetime
    error_message: str | None = None
    confluence_url: str | None = None
    confluence_version: int | None = None
    latest_confluence_version: int | None = None
    spec_checked_at: str | None = None
    spec_outdated: bool = False
    # Deterministic diff of the last re-extraction (see app/services/spec_diff.py)
    last_diff: dict | None = None
    # Dependencies used by this document's features whose source page moved
    # ahead — re-importing the document refreshes them (see dep_impact)
    deps_outdated: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SpecUpdateCheck(BaseModel):
    """Version probe result for one imported Confluence page."""

    slug: str
    filename: str
    confluence_url: str | None = None
    current_version: int | None = None
    latest_version: int | None = None
    outdated: bool = False
    deps_outdated: list[str] = Field(default_factory=list)
    error: str | None = None


class DepSourceCheck(BaseModel):
    """Version probe result for one enriched dependency's source page."""

    dep_type: str
    name: str
    source_page_url: str | None = None
    current_version: int | None = None
    latest_version: int | None = None
    outdated: bool = False
    error: str | None = None


class SpecUpdatesResponse(BaseModel):
    checked: int
    outdated: int
    documents: list[SpecUpdateCheck]
    dependencies_checked: int = 0
    dependencies_outdated: int = 0
    dependencies: list[DepSourceCheck] = []


class ProjectResponse(BaseModel):
    """HTTP response model for a project."""

    slug: str
    name: str
    created_at: datetime
    document_count: int
    feature_count: int = 0
    status: str = "empty"
    is_linked: bool = False
    external_path: str | None = None
    available: bool = True

    model_config = ConfigDict(from_attributes=True)
