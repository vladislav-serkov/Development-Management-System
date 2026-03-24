"""Export service: write .context/ folder structure to disk."""
import json
import logging
from pathlib import Path

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, Feature
from app.models.registry import DependencyEntry, GapEntry
from app.schemas.export import ExportResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level file I/O helpers
# ---------------------------------------------------------------------------


async def _write_text(path: Path, content: str) -> None:
    """Write text content to path using async I/O."""
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)


async def _write_json(path: Path, data: dict) -> None:
    """Write JSON content to path using async I/O."""
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


def _merge_registry_data(existing: dict, new_data: dict, feature_name: str) -> dict:
    """Merge two registry dicts.

    - new non-empty values override existing empty/None values
    - used_by_features is always a union of both + feature_name
    """
    # Start with existing, then override with new non-empty values
    merged = {**existing}
    for key, value in new_data.items():
        if key == "used_by_features":
            continue  # handled separately below
        if value:  # new value is non-empty — overrides
            merged[key] = value
        elif key not in merged or not merged[key]:
            # existing is also empty — keep whatever new_data says (could be empty list etc.)
            merged[key] = value

    # Always union used_by_features
    existing_used_by = set(existing.get("used_by_features", []))
    new_used_by = set(new_data.get("used_by_features", []))
    merged["used_by_features"] = sorted(existing_used_by | new_used_by | {feature_name})

    return merged


async def _merge_registry_file(path: Path, new_data: dict, feature_name: str) -> None:
    """Merge feature's dependency data into existing registry file (additive, D-10)."""
    existing: dict = {}
    if path.exists():
        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()
        existing = json.loads(content)

    merged = _merge_registry_data(existing, new_data, feature_name)
    await _write_json(path, merged)


async def _write_gaps_md(path: Path, gaps: list[dict]) -> str:
    """Write gaps.md from all gap entries, grouped by category.

    Returns the markdown string written.
    """
    api_gaps = [g for g in gaps if g.get("category") == "API"]
    db_gaps = [g for g in gaps if g.get("category") == "DB"]
    cache_gaps = [g for g in gaps if g.get("category") == "Cache"]

    def _format_gap(gap: dict) -> str:
        lines = [f"### {gap.get('name', 'Unknown')}"]
        affected = gap.get("affected_features", [])
        if affected:
            lines.append(f"- **Affected features:** {', '.join(affected)}")
        lines.append(f"- **Priority:** {gap.get('priority', 'unknown')}")
        lines.append(f"- **What's missing:** {gap.get('what_missing', '')}")
        suggestion = gap.get("suggestion")
        if suggestion:
            lines.append("- **Suggested schema:**")
            lines.append("  ```json")
            lines.append(f"  {json.dumps(suggestion, ensure_ascii=False)}")
            lines.append("  ```")
        return "\n".join(lines)

    def _format_section(title: str, section_gaps: list[dict]) -> str:
        if not section_gaps:
            return f"## {title}\n\n*(none)*"
        parts = [f"## {title}", ""]
        for gap in section_gaps:
            parts.append(_format_gap(gap))
            parts.append("")
        return "\n".join(parts).rstrip()

    sections = [
        "# Gaps Analysis",
        "",
        _format_section("External API Gaps", api_gaps),
        "",
        _format_section("Database Gaps", db_gaps),
        "",
        _format_section("Cache Gaps", cache_gaps),
    ]

    content = "\n".join(sections) + "\n"
    await _write_text(path, content)
    return content


# ---------------------------------------------------------------------------
# Core export function
# ---------------------------------------------------------------------------


async def export_feature_to_context(
    target_root: Path,
    feature_name: str,
    overview_md: str,
    business_logic: dict,
    dependencies: list[dict],
    gaps: list[dict],
) -> list[str]:
    """Export one feature to .context/ folder structure.

    Args:
        target_root: filesystem path to the microservice root (e.g., /projects/my-service)
        feature_name: name of the feature being exported
        overview_md: markdown overview text for the feature
        business_logic: dict with feature business logic (will be written as JSON)
        dependencies: list of dicts with keys: registry_type, name, data (dict)
        gaps: list of ALL document gaps (not just this feature's) — regenerates gaps.md

    Returns:
        list of file paths written (relative to target_root)
    """
    context_root = target_root / ".context"
    feature_dir = context_root / "features" / feature_name
    feature_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    # Write feature-specific files (overwrite per D-09)
    overview_path = feature_dir / "overview.md"
    await _write_text(overview_path, overview_md)
    files_written.append(str(overview_path.relative_to(target_root)))

    bl_path = feature_dir / "business-logic.json"
    await _write_json(bl_path, business_logic)
    files_written.append(str(bl_path.relative_to(target_root)))

    # Write/merge shared registries (augment per D-10)
    for dep in dependencies:
        registry_type = dep["registry_type"]
        dep_name = dep["name"]
        dep_data = dep["data"]

        registry_dir = context_root / registry_type
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_file = registry_dir / f"{dep_name}.json"

        await _merge_registry_file(registry_file, dep_data, feature_name)
        files_written.append(str(registry_file.relative_to(target_root)))

    # Regenerate gaps.md from ALL document gaps (D-08, Pitfall 3)
    gaps_path = context_root / "gaps.md"
    await _write_gaps_md(gaps_path, gaps)
    files_written.append(str(gaps_path.relative_to(target_root)))

    return files_written


# ---------------------------------------------------------------------------
# Document-level export (reads from SQLite)
# ---------------------------------------------------------------------------


async def export_document_context(
    document_id: int,
    target_path: str,
    feature_name: str | None,
    session: AsyncSession,
) -> ExportResponse:
    """Export all (or one) feature's .context/ from SQLite to the filesystem.

    Args:
        document_id: ID of the document to export
        target_path: absolute path to the target microservice root
        feature_name: if specified, only export this feature; else export all done features
        session: async DB session

    Returns:
        ExportResponse with list of exported features and files written
    """
    target_root = Path(target_path)

    # Load features for this document
    stmt = select(Feature).where(Feature.document_id == document_id)
    result = await session.execute(stmt)
    features = result.scalars().all()

    # Filter to desired feature(s)
    if feature_name is not None:
        features = [f for f in features if f.name == feature_name]
    else:
        features = [f for f in features if f.status == "done"]

    # Load ALL dependency entries for this document
    dep_stmt = select(DependencyEntry).where(DependencyEntry.document_id == document_id)
    dep_result = await session.execute(dep_stmt)
    all_deps = dep_result.scalars().all()

    # Load ALL gap entries for this document
    gap_stmt = select(GapEntry).where(GapEntry.document_id == document_id)
    gap_result = await session.execute(gap_stmt)
    all_gaps = gap_result.scalars().all()

    # Convert gap ORM rows to export dicts
    gap_dicts = [
        {
            "category": g.category,
            "name": g.name,
            "affected_features": json.loads(g.affected_features),
            "what_missing": g.what_missing,
            "priority": g.priority,
            "suggestion": json.loads(g.suggestion_json) if g.suggestion_json else None,
        }
        for g in all_gaps
    ]

    exported_features: list[str] = []
    all_files_written: list[str] = []

    for feature in features:
        # Convert dependency ORM rows to export dicts for this feature
        # Use all_deps for this document — cross-document dedup happens at file merge time
        dep_dicts = [
            {
                "registry_type": d.registry_type,
                "name": d.name,
                "data": json.loads(d.data_json),
            }
            for d in all_deps
        ]

        bl_dict: dict = {}
        if feature.business_logic:
            try:
                bl_dict = json.loads(feature.business_logic)
            except json.JSONDecodeError:
                bl_dict = {"_raw": feature.business_logic}

        overview = feature.overview_md or f"## {feature.name}\n\n{feature.summary or 'No overview available.'}"

        files = await export_feature_to_context(
            target_root=target_root,
            feature_name=feature.name,
            overview_md=overview,
            business_logic=bl_dict,
            dependencies=dep_dicts,
            gaps=gap_dicts,
        )

        exported_features.append(feature.name)
        all_files_written.extend(files)

    # Deduplicate files_written (gaps.md is written once per feature export)
    seen: set[str] = set()
    deduped_files: list[str] = []
    for f in all_files_written:
        if f not in seen:
            seen.add(f)
            deduped_files.append(f)

    return ExportResponse(
        exported_features=exported_features,
        target_path=target_path,
        files_written=deduped_files,
    )
