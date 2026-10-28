from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.extraction import LogicStep, UsedDependency


class SingleGapResult(BaseModel):
    """One gap found by Claude."""
    gap_type: str = Field(description="Gap category in snake_case describing the issue, e.g. missing_branch, field_not_in_schema, contradictory_logic, nullable_without_handling, ambiguous_condition")
    severity: Literal["critical", "major"] = Field(description="Impact level: critical (developer cannot implement correctly, data loss or wrong business result) or major (real bug in non-main scenario)")
    question: str = Field(description="What is missing or inconsistent, in Russian")
    suggestion: str = Field(description="How to fix it, in Russian")
    actionable: bool = Field(description="true if suggestion is a concrete spec requirement ready to implement; false if it requires analyst clarification first")


class GapsAnalysisResult(BaseModel):
    """Tool output schema for single-call gaps analysis."""
    gaps: list[SingleGapResult]


class GapReviewRequest(BaseModel):
    """PATCH body for approving/clarifying/resetting a gap."""
    status: str = Field(pattern="^(pending|approved|clarified|applied)$")
    analyst_text: str | None = None


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
