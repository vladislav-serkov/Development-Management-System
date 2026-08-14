"""PostgreSQL-backed storage layer.

``ProjectStore`` keeps the same public async API the routers and services were
built against when storage was file-based; only the internals changed. Every
public method runs in its own transaction, so the old class-level asyncio locks
are gone — read-modify-write flows take a row-level ``SELECT ... FOR UPDATE``
instead, which also lifts the single-worker restriction.

Entity payloads live in JSONB ``data`` columns and round-trip verbatim, so the
dict shapes returned here are identical to the JSON files the store used to
serve.
"""

import copy
import logging
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from app.db import get_session_factory
from app.models import AnalysisItem, Dependency, Document, Feature, Project, Rules, Task

logger = logging.getLogger(__name__)

DEP_TYPE_FILE = {
    "db_table": "db_tables.json",
    "external_api": "external_apis.json",
    "cache": "cache.json",
    "kafka_topic": "kafka_topics.json",
    "external_doc": "external_docs.json",
}

AGENT_NAMES = ["extraction", "gaps", "test_cases", "bugs", "enrichment"]

# Keys that indicate the dep dict already contains enrichment data (Context Collector format)
_ENRICHMENT_MARKERS = {
    "db_table": "columns",
    "external_api": "endpoints",
    "cache": "key_patterns",
    "kafka_topic": "message_schema",
    "external_doc": "content_html",
}


class ActiveTaskExistsError(RuntimeError):
    """A running task of the same kind for the same target already exists."""


def _normalize_dep(dep_dict: dict, key: str, dep_type: str) -> dict:
    """Normalize a dependency dict: inject name/dep_type, wrap inline enrichment."""
    dep_dict.setdefault("name", key)
    dep_dict.setdefault("dep_type", dep_type)

    # If enrichment data is inline (Context Collector format), wrap it
    marker = _ENRICHMENT_MARKERS.get(dep_type)
    if marker and marker in dep_dict and "enriched_data" not in dep_dict:
        # Separate meta fields from enrichment payload
        meta_keys = {"name", "dep_type", "enrichment_status", "enriched_data",
                      "source_pdf_name", "enriched_at", "created_at", "updated_at",
                      "method", "service_name", "path"}
        enriched = {k: v for k, v in dep_dict.items() if k not in meta_keys}
        for k in list(dep_dict.keys()):
            if k not in meta_keys:
                del dep_dict[k]
        dep_dict["enriched_data"] = enriched
        dep_dict.setdefault("enrichment_status", "enriched")

    return dep_dict


EMPTY_RULES = {name: "" for name in AGENT_NAMES}


def slugify(name: str) -> str:
    """Convert name to URL-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "project"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


class ProjectStore:
    """Async PostgreSQL storage for projects, documents, features, and dependencies."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    def _sf(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_feature_name(feature_name: str) -> str:
        """Map a feature name to a single safe path segment (used by the
        .context file layout on import/export). Slashes become ``__``;
        traversal/empty names are rejected."""
        safe = feature_name.replace("/", "__")
        if not safe or safe in (".", "..") or "/" in safe or "\\" in safe:
            raise ValueError(f"Invalid feature name: {feature_name!r}")
        return safe

    @staticmethod
    async def _project_row(session: AsyncSession, slug: str, *, for_update: bool = False) -> Project | None:
        stmt = select(Project).where(Project.slug == slug)
        if for_update:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _feature_row(
        session: AsyncSession, project_id: int, name: str, *, for_update: bool = False
    ) -> Feature | None:
        stmt = select(Feature).where(Feature.project_id == project_id, Feature.name == name)
        if for_update:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _project_and_feature(
        self, session: AsyncSession, project_slug: str, feature_name: str, *, for_update: bool = False
    ) -> Feature | None:
        project = await self._project_row(session, project_slug)
        if project is None:
            return None
        return await self._feature_row(session, project.id, feature_name, for_update=for_update)

    async def _project_dict(self, session: AsyncSession, project: Project) -> dict:
        doc_count = await session.scalar(
            select(func.count()).select_from(Document).where(Document.project_id == project.id)
        )
        feature_count = await session.scalar(
            select(func.count()).select_from(Feature).where(Feature.project_id == project.id)
        )
        doc_statuses = (
            await session.execute(select(Document.data["status"].astext).where(Document.project_id == project.id))
        ).scalars().all()
        return {
            "slug": project.slug,
            "name": project.name,
            "created_at": _iso(project.created_at),
            "document_count": doc_count or 0,
            "feature_count": feature_count or 0,
            "status": self._status_from_docs(doc_statuses),
            "is_linked": False,
            "external_path": project.context_dir,
            "available": True,
        }

    @staticmethod
    def _status_from_docs(statuses: list[str | None]) -> str:
        if not statuses:
            return "empty"
        statuses = [s or "pending" for s in statuses]
        if any(s in ("processing", "extracting") for s in statuses):
            return "processing"
        if all(s == "done" for s in statuses):
            return "done"
        if any(s == "error" for s in statuses):
            return "partial"
        return "pending"

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict]:
        async with self._sf()() as session:
            rows = (await session.execute(select(Project))).scalars().all()
            projects = [await self._project_dict(session, p) for p in rows]
        projects.sort(key=lambda p: p.get("created_at") or "", reverse=True)
        return projects

    async def get_project(self, slug: str) -> dict | None:
        async with self._sf()() as session:
            project = await self._project_row(session, slug)
            if project is None:
                return None
            return await self._project_dict(session, project)

    async def create_project(self, name: str) -> dict:
        """Create a project row. Handles slug collisions by suffixing a counter."""
        base_slug = slugify(name)
        async with self._sf().begin() as session:
            taken = set(
                (await session.execute(select(Project.slug).where(Project.slug.startswith(base_slug)))).scalars()
            )
            slug = base_slug
            counter = 2
            while slug in taken:
                slug = f"{base_slug}-{counter}"
                counter += 1
            project = Project(slug=slug, name=name, created_at=datetime.now(UTC))
            session.add(project)
            await session.flush()
            return await self._project_dict(session, project)

    async def update_project(self, slug: str, name: str) -> dict | None:
        async with self._sf().begin() as session:
            project = await self._project_row(session, slug, for_update=True)
            if project is None:
                return None
            project.name = name
            return await self._project_dict(session, project)

    async def set_project_context_dir(self, slug: str, context_dir: str | None) -> None:
        """Remember the external .context/ directory a project was imported from."""
        async with self._sf().begin() as session:
            project = await self._project_row(session, slug, for_update=True)
            if project is not None:
                project.context_dir = context_dir

    async def get_project_context_dir(self, slug: str) -> str | None:
        async with self._sf()() as session:
            project = await self._project_row(session, slug)
            return project.context_dir if project else None

    async def delete_project(self, slug: str, *, remove_files: bool = False) -> None:
        """Delete a project row; FK cascade removes everything else.

        ``remove_files`` is accepted for API compatibility and ignored.
        """
        async with self._sf().begin() as session:
            await session.execute(delete(Project).where(Project.slug == slug))

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def list_documents(self, project_slug: str) -> list[dict]:
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return []
            rows = (
                await session.execute(select(Document).where(Document.project_id == project.id))
            ).scalars().all()
        docs = [dict(r.data) for r in rows]
        docs.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
        return docs

    async def get_document(self, project_slug: str, doc_slug: str) -> dict | None:
        async with self._sf()() as session:
            row = await self._document_row(session, project_slug, doc_slug)
            if row is None:
                return None
            doc = dict(row.data)
        doc["features"] = await self.list_features(project_slug)
        return doc

    @staticmethod
    async def _document_row(
        session: AsyncSession, project_slug: str, doc_slug: str, *, for_update: bool = False
    ) -> Document | None:
        stmt = (
            select(Document)
            .join(Project, Document.project_id == Project.id)
            .where(Project.slug == project_slug, Document.slug == doc_slug)
        )
        if for_update:
            stmt = stmt.with_for_update(of=Document)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def save_document(self, project_slug: str, doc_data: dict) -> dict:
        slug = doc_data["slug"]
        # Don't persist features inline — they're stored separately
        to_write = {k: v for k, v in doc_data.items() if k != "features"}
        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                raise ValueError(f"Project '{project_slug}' not found")
            row = await self._document_row(session, project_slug, slug, for_update=True)
            if row is None:
                session.add(Document(project_id=project.id, slug=slug, data=to_write))
            else:
                row.data = to_write
        return doc_data

    async def save_document_source(self, project_slug: str, doc_slug: str, source: dict) -> None:
        """Persist the raw imported page (markdown + links + tables).

        This is the input the extraction pipeline actually saw. Keeping it makes an
        import reproducible: re-running extraction, diffing prompt changes and building
        eval fixtures all work off this data instead of re-fetching from Confluence.
        """
        async with self._sf().begin() as session:
            row = await self._document_row(session, project_slug, doc_slug, for_update=True)
            if row is None:
                raise ValueError(f"Document '{doc_slug}' not found in project '{project_slug}'")
            row.source = source

    async def get_document_source(self, project_slug: str, doc_slug: str) -> dict | None:
        async with self._sf()() as session:
            row = await self._document_row(session, project_slug, doc_slug)
            if row is None or row.source is None:
                return None
            return dict(row.source)

    async def update_document(self, project_slug: str, doc_slug: str, updates: dict) -> dict | None:
        async with self._sf().begin() as session:
            row = await self._document_row(session, project_slug, doc_slug, for_update=True)
            if row is None:
                return None
            doc = dict(row.data)
            doc.update(updates)
            row.data = doc
            return doc

    async def make_doc_slug(self, project_slug: str, filename: str) -> str:
        """Generate unique document slug from filename within a project."""
        base = slugify(filename.removesuffix(".pdf").removesuffix(".PDF"))
        if not base:
            base = "document"
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            existing: set[str] = set()
            if project is not None:
                existing = set(
                    (
                        await session.execute(select(Document.slug).where(Document.project_id == project.id))
                    ).scalars()
                )
        slug = base
        counter = 2
        while slug in existing:
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    async def list_features(self, project_slug: str) -> list[dict]:
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return []
            rows = (
                await session.execute(
                    select(Feature).where(Feature.project_id == project.id).order_by(Feature.id)
                )
            ).scalars().all()
        features = []
        for row in rows:
            feat = dict(row.data)
            feat.pop("gaps", None)
            feat.pop("test_cases", None)
            features.append(feat)
        return features

    async def get_feature(self, project_slug: str, feature_name: str) -> dict | None:
        async with self._sf()() as session:
            row = await self._project_and_feature(session, project_slug, feature_name)
            if row is None:
                return None
            feat = dict(row.data)
        feat.pop("gaps", None)
        feat.pop("test_cases", None)
        return feat

    async def save_feature(self, project_slug: str, feature_data: dict) -> dict:
        """Upsert a feature. Extracts gaps/test_cases/bugs into analysis rows."""
        name = feature_data["name"]
        self._sanitize_feature_name(name)  # reject path-hostile names, as before

        feature_to_write = dict(feature_data)
        gaps = feature_to_write.pop("gaps", None)
        test_cases = feature_to_write.pop("test_cases", None)
        bugs = feature_to_write.pop("bugs", None)

        if gaps is not None:
            feature_to_write["gap_count"] = len(gaps)
            feature_to_write["pending_gap_count"] = sum(1 for g in gaps if g.get("status") == "pending")
        if test_cases is not None:
            feature_to_write["test_case_count"] = len(test_cases)
            feature_to_write["pending_test_case_count"] = sum(1 for t in test_cases if t.get("status") == "pending")
        if bugs is not None:
            feature_to_write["bug_count"] = len(bugs)

        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                raise ValueError(f"Project '{project_slug}' not found")
            row = await self._feature_row(session, project.id, name, for_update=True)
            if row is None:
                row = Feature(project_id=project.id, name=name, data=feature_to_write)
                session.add(row)
                await session.flush()
            else:
                row.data = feature_to_write
            if gaps is not None:
                await self._replace_items(session, row.id, "gap", gaps)
            if test_cases is not None:
                await self._replace_items(session, row.id, "test_case", test_cases)
            if bugs is not None:
                await self._replace_items(session, row.id, "bug", bugs)
        return feature_data

    async def update_feature(self, project_slug: str, feature_name: str, updates: dict) -> dict | None:
        """Update feature data. Redirects gaps/test_cases/bugs updates to analysis rows."""
        async with self._sf().begin() as session:
            row = await self._project_and_feature(session, project_slug, feature_name, for_update=True)
            if row is None:
                return None

            updates_to_apply = dict(updates)

            if "gaps" in updates_to_apply:
                gaps = updates_to_apply.pop("gaps")
                await self._replace_items(session, row.id, "gap", gaps)
                updates_to_apply["gap_count"] = len(gaps)
                updates_to_apply["pending_gap_count"] = sum(1 for g in gaps if g.get("status") == "pending")

            if "test_cases" in updates_to_apply:
                test_cases = updates_to_apply.pop("test_cases")
                await self._replace_items(session, row.id, "test_case", test_cases)
                updates_to_apply["test_case_count"] = len(test_cases)
                updates_to_apply["pending_test_case_count"] = sum(
                    1 for t in test_cases if t.get("status") == "pending"
                )

            if "bugs" in updates_to_apply:
                bugs = updates_to_apply.pop("bugs")
                await self._replace_items(session, row.id, "bug", bugs)
                updates_to_apply["bug_count"] = len(bugs)

            feature = dict(row.data)
            feature.update(updates_to_apply)
            row.data = feature
            return feature

    async def delete_feature(self, project_slug: str, feature_name: str) -> bool:
        """Delete feature row; analysis items follow via FK cascade."""
        async with self._sf().begin() as session:
            row = await self._project_and_feature(session, project_slug, feature_name)
            if row is None:
                return False
            await session.delete(row)
            return True

    async def rename_feature(self, project_slug: str, old_name: str, new_name: str) -> dict | None:
        """Rename a feature. Returns updated feature dict or None if old_name not found.
        Raises ValueError if new_name already exists."""
        self._sanitize_feature_name(new_name)
        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return None
            row = await self._feature_row(session, project.id, old_name, for_update=True)
            if row is None:
                return None
            existing = await self._feature_row(session, project.id, new_name)
            if existing is not None:
                raise ValueError(f"Feature with name '{new_name}' already exists")
            feat = dict(row.data)
            feat["name"] = new_name
            row.name = new_name
            row.data = feat
            return feat

    # ------------------------------------------------------------------
    # Apply Preview (temporary storage for LLM-generated diff)
    # ------------------------------------------------------------------

    async def get_apply_preview(self, project_slug: str, feature_name: str) -> dict | None:
        async with self._sf()() as session:
            row = await self._project_and_feature(session, project_slug, feature_name)
            if row is None or row.apply_preview is None:
                return None
            return dict(row.apply_preview)

    async def save_apply_preview(self, project_slug: str, feature_name: str, data: dict) -> None:
        async with self._sf().begin() as session:
            row = await self._project_and_feature(session, project_slug, feature_name, for_update=True)
            if row is None:
                raise ValueError(f"Feature '{feature_name}' not found in project '{project_slug}'")
            row.apply_preview = data

    async def delete_apply_preview(self, project_slug: str, feature_name: str) -> None:
        async with self._sf().begin() as session:
            row = await self._project_and_feature(session, project_slug, feature_name, for_update=True)
            if row is not None:
                row.apply_preview = None

    # ------------------------------------------------------------------
    # Gaps / Test Cases / Bugs (analysis items)
    # ------------------------------------------------------------------

    @staticmethod
    async def _replace_items(session: AsyncSession, feature_id: int, kind: str, items: list[dict]) -> None:
        await session.execute(
            delete(AnalysisItem).where(AnalysisItem.feature_id == feature_id, AnalysisItem.kind == kind)
        )
        session.add_all(
            AnalysisItem(
                feature_id=feature_id,
                kind=kind,
                position=i,
                status=item.get("status"),
                archived=bool(item.get("archived")),
                data=item,
            )
            for i, item in enumerate(items)
        )

    async def _get_items(self, project_slug: str, feature_name: str, kind: str) -> list[dict]:
        async with self._sf()() as session:
            row = await self._project_and_feature(session, project_slug, feature_name)
            if row is None:
                return []
            items = (
                await session.execute(
                    select(AnalysisItem.data)
                    .where(AnalysisItem.feature_id == row.id, AnalysisItem.kind == kind)
                    .order_by(AnalysisItem.position)
                )
            ).scalars().all()
            return [dict(i) for i in items]

    async def get_gaps(self, project_slug: str, feature_name: str, *, include_archived: bool = False) -> list[dict]:
        gaps = await self._get_items(project_slug, feature_name, "gap")
        if include_archived:
            return gaps
        return [g for g in gaps if not g.get("archived")]

    async def save_gaps(self, project_slug: str, feature_name: str, gaps: list[dict]) -> None:
        """Replace the feature's gaps and update gap counts in the feature dict."""
        active_gaps = [g for g in gaps if not g.get("archived")]
        counts = {
            "gap_count": len(active_gaps),
            "pending_gap_count": sum(1 for g in active_gaps if g.get("status") == "pending"),
        }
        await self._save_items(project_slug, feature_name, "gap", gaps, counts)

    async def get_test_cases(self, project_slug: str, feature_name: str) -> list[dict]:
        return await self._get_items(project_slug, feature_name, "test_case")

    async def save_test_cases(self, project_slug: str, feature_name: str, test_cases: list[dict]) -> None:
        counts = {
            "test_case_count": len(test_cases),
            "pending_test_case_count": sum(1 for t in test_cases if t.get("status") == "pending"),
        }
        await self._save_items(project_slug, feature_name, "test_case", test_cases, counts)

    async def get_bugs(self, project_slug: str, feature_name: str) -> list[dict]:
        return await self._get_items(project_slug, feature_name, "bug")

    async def save_bugs(self, project_slug: str, feature_name: str, bugs: list[dict]) -> None:
        await self._save_items(project_slug, feature_name, "bug", bugs, {"bug_count": len(bugs)})

    async def _save_items(
        self, project_slug: str, feature_name: str, kind: str, items: list[dict], counts: dict
    ) -> None:
        async with self._sf().begin() as session:
            row = await self._project_and_feature(session, project_slug, feature_name, for_update=True)
            if row is None:
                return
            await self._replace_items(session, row.id, kind, items)
            row.data = {**row.data, **counts}

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    @staticmethod
    async def _dep_row(
        session: AsyncSession, project_id: int, dep_type: str, name: str, *, for_update: bool = False
    ) -> Dependency | None:
        """Case-insensitive dependency lookup."""
        stmt = select(Dependency).where(
            Dependency.project_id == project_id,
            Dependency.dep_type == dep_type,
            func.lower(Dependency.name) == name.lower(),
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_dependencies(self, project_slug: str) -> dict[str, list]:
        """Return {dep_type: [dep_dict, ...]} for all dep types."""
        result: dict[str, list] = {dep_type: [] for dep_type in DEP_TYPE_FILE}
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return result
            rows = (
                await session.execute(
                    select(Dependency).where(Dependency.project_id == project.id).order_by(Dependency.id)
                )
            ).scalars().all()
        for row in rows:
            if row.dep_type in result:
                result[row.dep_type].append(_normalize_dep(dict(row.data), row.name, row.dep_type))
        return result

    async def upsert_dependency(self, project_slug: str, dep_type: str, name: str, data: dict) -> dict:
        """Insert or merge a dependency entry (case-insensitive by name).

        Never downgrades enrichment: if already enriched, stub overwrites are filtered.
        """
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                raise ValueError(f"Project '{project_slug}' not found")
            row = await self._dep_row(session, project.id, dep_type, name, for_update=True)
            if row is None:
                session.add(Dependency(project_id=project.id, dep_type=dep_type, name=name, data=data))
                return data
            prev = dict(row.data)
            if prev.get("enrichment_status") == "enriched" and data.get("enrichment_status") == "stub":
                data = {
                    k: v for k, v in data.items() if k not in ("enriched_data", "enrichment_status", "enriched_at")
                }
            prev.update(data)
            # If incoming name has different case, re-key to preserve original case
            if row.name != name:
                row.name = name
                prev["name"] = name
            row.data = prev
            return prev

    async def get_dependency(self, project_slug: str, dep_type: str, name: str) -> dict | None:
        if dep_type not in DEP_TYPE_FILE:
            return None
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return None
            row = await self._dep_row(session, project.id, dep_type, name)
            if row is None:
                return None
            return _normalize_dep(dict(row.data), row.name, dep_type)

    async def update_dependency(self, project_slug: str, dep_type: str, name: str, updates: dict) -> dict | None:
        if dep_type not in DEP_TYPE_FILE:
            return None
        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return None
            row = await self._dep_row(session, project.id, dep_type, name, for_update=True)
            if row is None:
                return None
            merged = dict(row.data)
            merged.update(updates)
            merged = _normalize_dep(merged, row.name, dep_type)
            row.data = merged
            return merged

    async def delete_dependency(self, project_slug: str, dep_type: str, name: str) -> bool:
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")
        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return False
            row = await self._dep_row(session, project.id, dep_type, name)
            if row is None:
                return False
            await session.delete(row)
            return True

    async def rename_dependency(self, project_slug: str, dep_type: str, old_name: str, new_name: str) -> dict | None:
        """Rename a dependency and update all features' used_dependencies references,
        all in one transaction. Returns renamed dep dict or None if old_name not found.
        Raises ValueError if new_name already exists."""
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return None
            row = await self._dep_row(session, project.id, dep_type, old_name, for_update=True)
            if row is None:
                return None
            conflict = await self._dep_row(session, project.id, dep_type, new_name)
            if conflict is not None and conflict.id != row.id:
                raise ValueError(f"Dependency with name '{new_name}' already exists")

            entry = dict(row.data)
            entry["name"] = new_name
            row.name = new_name
            row.data = entry

            # Cascade: rewrite used_dependencies refs inside every feature's structured logic
            features = (
                await session.execute(
                    select(Feature).where(Feature.project_id == project.id).with_for_update()
                )
            ).scalars().all()
            for feat_row in features:
                # Deep copy: mutating nested dicts shared with the old value would
                # make old == new and SQLAlchemy would skip the UPDATE.
                feat = copy.deepcopy(feat_row.data)
                sl = feat.get("structured_logic_json") or feat.get("structured_logic")
                if not isinstance(sl, dict):
                    continue
                used_deps = sl.get("used_dependencies", [])
                if not isinstance(used_deps, list):
                    continue
                modified = False
                for dep_ref in used_deps:
                    if (
                        isinstance(dep_ref, dict)
                        and dep_ref.get("type") == dep_type
                        and dep_ref.get("name") == old_name
                    ):
                        dep_ref["name"] = new_name
                        modified = True
                if modified:
                    feat_row.data = feat

            return entry

    # ------------------------------------------------------------------
    # Rules (global + per-project)
    # ------------------------------------------------------------------

    async def get_global_rules(self) -> dict:
        async with self._sf()() as session:
            row = (
                await session.execute(select(Rules).where(Rules.project_id.is_(None)))
            ).scalar_one_or_none()
            if row is None:
                return dict(EMPTY_RULES)
            return dict(row.data)

    async def save_global_rules(self, rules: dict) -> dict:
        normalized = {k: rules.get(k, "") for k in AGENT_NAMES}
        async with self._sf().begin() as session:
            row = (
                await session.execute(select(Rules).where(Rules.project_id.is_(None)).with_for_update())
            ).scalar_one_or_none()
            if row is None:
                session.add(Rules(project_id=None, data=normalized))
            else:
                row.data = normalized
        return normalized

    async def get_project_rules(self, project_slug: str) -> dict:
        async with self._sf()() as session:
            row = (
                await session.execute(
                    select(Rules)
                    .join(Project, Rules.project_id == Project.id)
                    .where(Project.slug == project_slug)
                )
            ).scalar_one_or_none()
            if row is None:
                return dict(EMPTY_RULES)
            return dict(row.data)

    async def save_project_rules(self, project_slug: str, rules: dict) -> dict:
        normalized = {k: rules.get(k, "") for k in AGENT_NAMES}
        async with self._sf().begin() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                raise ValueError(f"Project '{project_slug}' not found")
            row = (
                await session.execute(
                    select(Rules).where(Rules.project_id == project.id).with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                session.add(Rules(project_id=project.id, data=normalized))
            else:
                row.data = normalized
        return normalized

    # ------------------------------------------------------------------
    # Tasks (background-task log, per-project)
    # ------------------------------------------------------------------

    @staticmethod
    def _task_dict(row: Task) -> dict:
        return {
            "id": row.task_id,
            "kind": row.kind,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "status": row.status,
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
            "error_message": row.error_message,
            "duration_ms": row.duration_ms,
        }

    async def create_task(self, project_slug: str, *, kind: str, target_type: str, target_id: str) -> dict:
        """Insert a new running task. Raises ActiveTaskExistsError if a running
        task of the same kind for the same target already exists (enforced by a
        partial unique index, so this is race-free across workers)."""
        try:
            async with self._sf().begin() as session:
                project = await self._project_row(session, project_slug)
                if project is None:
                    raise ValueError(f"Project '{project_slug}' not found")
                row = Task(
                    project_id=project.id,
                    task_id=str(uuid.uuid4()),
                    kind=kind,
                    target_type=target_type,
                    target_id=target_id,
                    status="running",
                    started_at=datetime.now(UTC),
                )
                session.add(row)
                await session.flush()
                return self._task_dict(row)
        except IntegrityError as exc:
            raise ActiveTaskExistsError(
                f"A '{kind}' task is already running for '{target_id}'"
            ) from exc

    async def finish_task(
        self, project_slug: str, task_id: str, *, status: str, error_message: str | None = None
    ) -> dict | None:
        """Close a running task with done/error, set finished_at + duration_ms."""
        async with self._sf().begin() as session:
            row = (
                await session.execute(select(Task).where(Task.task_id == task_id).with_for_update())
            ).scalar_one_or_none()
            if row is None:
                return None
            now = datetime.now(UTC)
            row.status = status
            row.finished_at = now
            row.error_message = error_message
            if row.started_at is not None:
                row.duration_ms = int((now - row.started_at).total_seconds() * 1000)
            return self._task_dict(row)

    async def list_tasks(
        self,
        project_slug: str,
        *,
        status: str | None = None,
        kind: str | None = None,
        target_id: str | None = None,
    ) -> list[dict]:
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return []
            stmt = select(Task).where(Task.project_id == project.id)
            if status is not None:
                stmt = stmt.where(Task.status == status)
            if kind is not None:
                stmt = stmt.where(Task.kind == kind)
            if target_id is not None:
                stmt = stmt.where(Task.target_id == target_id)
            stmt = stmt.order_by(Task.started_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._task_dict(r) for r in rows]

    async def get_active_task(self, project_slug: str, *, kind: str, target_id: str) -> dict | None:
        """Return the running task for (kind, target_id) if any, else None."""
        async with self._sf()() as session:
            project = await self._project_row(session, project_slug)
            if project is None:
                return None
            row = (
                await session.execute(
                    select(Task).where(
                        Task.project_id == project.id,
                        Task.status == "running",
                        Task.kind == kind,
                        Task.target_id == target_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._task_dict(row)
