from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import LogicStep, UsedDependency


class SingleGapResult(BaseModel):
    """Legacy schema for structured-output regression tests, not the Codex pipeline."""
    gap_type: str = Field(description="Gap category in snake_case describing the issue, e.g. missing_branch, field_not_in_schema, contradictory_logic, nullable_without_handling, ambiguous_condition")
    severity: Literal["critical", "major"] = Field(description="Impact level: critical (developer cannot implement correctly, data loss or wrong business result) or major (real bug in non-main scenario)")
    question: str = Field(description="What is missing or inconsistent, in Russian")
    suggestion: str = Field(description="How to fix it, in Russian")
    actionable: bool = Field(description="true if suggestion is a concrete spec requirement ready to implement; false if it requires analyst clarification first")


class GapsAnalysisResult(BaseModel):
    """Tool output schema for single-call gaps analysis."""
    gaps: list[SingleGapResult]


class GapReviewRequest(BaseModel):
    """A decision about a finding; never a change to the source specification."""
    status: Literal["approved", "rejected"]
    analyst_text: str | None = Field(default=None, max_length=20000)


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(AnalysisModel):
    source_id: str
    location: str = Field(description="Раздел, таблица или шаг первоисточника")
    quote: str = Field(min_length=12, description="Дословная непрерывная цитата из markdown источника")


class BusinessFact(AnalysisModel):
    text: str
    evidence: list[Evidence] = Field(min_length=1)


class BusinessPicture(AnalysisModel):
    purpose: str
    purpose_evidence: list[Evidence] = Field(min_length=1)
    actors: list[BusinessFact]
    entities_and_states: list[BusinessFact]
    lifecycle: list[BusinessFact]
    business_rules: list[BusinessFact]
    unknowns: list[str]


class SourceSelection(AnalysisModel):
    requested_source_ids: list[str]
    rationale: str


class Finding(AnalysisModel):
    existing_gap_id: str | None = Field(description="ID того же замечания из предыдущего анализа, иначе null")
    kind: Literal["contradiction", "missing_logic", "business_question"]
    gap_type: str
    severity: Literal["critical", "major"]
    subject: str = Field(description="Стабильный предмет: payment.external_id или переход RESERVED→CANCELLED")
    location: str
    question: str
    scenario: str = Field(description="Конкретные входные условия и ход проблемного сценария")
    business_impact: str
    suggestion: str = Field(description="Обоснованное уточнение ТЗ или вопрос; не выдумывай бизнес-решение")
    evidence: list[Evidence] = Field(min_length=1)
    reconsideration_reason: str | None = Field(
        description="Только для отклонённого замечания: какие новые требования ТЗ дают основание вернуть его; иначе null",
    )


class GapReport(AnalysisModel):
    business_picture: BusinessPicture
    checked_source_ids: list[str]
    checked_scenarios: list[str]
    limitations: list[str]
    gaps: list[Finding]


class ApplyChange(BaseModel):
    """One change to be applied to structured logic."""
    section: str = Field(description="Where in logic: 'logic_steps', 'input_tables', 'response_tables', 'used_dependencies'")
    action: str = Field(description="What was done: 'added', 'modified', 'removed'")
    location: str = Field(description="Human-readable location, e.g. 'Шаг 4', 'Параметр limitAmount'")
    description: str = Field(description="What changed, in Russian. Readable for analyst.")
    detail: str = Field(description="The actual new/modified text content in Russian")
    gap_index: int = Field(description="Index of the gap that triggered this change")


class ApplyResult(BaseModel):
    """Structured output of apply-preview: the updated logic steps and
    dependencies plus change descriptions. Parameter tables mirror the spec
    verbatim and are not edited here — the service carries them over."""
    logic_steps: list[LogicStep] = Field(description="All logic steps after the changes, flat, in document order, existing numbers kept")
    used_dependencies: list[UsedDependency] = Field(description="All dependencies after the changes")
    changes: list[ApplyChange] = Field(description="Human-readable list of every change made")


class ApplyConfirmRequest(BaseModel):
    """Request body for apply-confirm endpoint."""
    proposed: dict
