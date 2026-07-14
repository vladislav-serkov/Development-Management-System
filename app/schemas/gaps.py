from __future__ import annotations

from pydantic import BaseModel, Field


class SingleGapResult(BaseModel):
    """One gap found by Claude."""
    gap_type: str = Field(description="Gap category in snake_case describing the issue, e.g. missing_branch, field_not_in_schema, contradictory_logic, nullable_without_handling, ambiguous_condition")
    severity: str = Field(description="Impact level: critical (developer cannot implement correctly, data loss or wrong business result) or major (real bug in non-main scenario)")
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
    section: str = Field(description="Where in logic: 'logic_steps', 'business_rules', 'error_handling', 'input_parameters', 'success_response', 'error_responses', 'used_dependencies'")
    action: str = Field(description="What was done: 'added', 'modified', 'removed'")
    location: str = Field(description="Human-readable location, e.g. 'Шаг 4', 'Бизнес-правило #3', 'error_handling'")
    description: str = Field(description="What changed, in Russian. Readable for analyst.")
    detail: str = Field(description="The actual new/modified text content in Russian")
    gap_index: int = Field(description="Index of the gap that triggered this change")


class ApplyResult(BaseModel):
    """Tool output for apply-preview: updated logic + change descriptions."""
    structured_logic: "StructuredBusinessLogic" = Field(description="Complete updated structured_logic with all changes applied. MUST preserve all existing data — only add/modify what gaps require.")  # noqa: F821 — resolved at runtime by _rebuild_apply_result()
    changes: list[ApplyChange] = Field(description="Human-readable list of every change made")


class ApplyConfirmRequest(BaseModel):
    """Request body for apply-confirm endpoint."""
    proposed: dict


# Rebuild forward refs once StructuredBusinessLogic is importable
def _rebuild_apply_result() -> None:
    from app.schemas.extraction import StructuredBusinessLogic

    ApplyResult.model_rebuild(_types_namespace={"StructuredBusinessLogic": StructuredBusinessLogic})


_rebuild_apply_result()
