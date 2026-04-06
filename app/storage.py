"""File-based storage layer. Replaces SQLAlchemy + SQLite with JSON files.

Directory structure:
    {DATA_DIR}/{project_slug}/
        project.json
        documents/
            {doc_slug}.json
        features/
            {feature_name}/
                feature.json      <- core feature data
                apply-preview.json <- temporary LLM diff preview
        gaps/
            {feature_name}.json   <- { gaps: [], gaps_status, gaps_run_at }
        test-cases/
            {feature_name}.json   <- { test_cases: [], test_cases_status, test_cases_run_at }
        bugs/
            {feature_name}.json   <- { bugs: [] }
        dependencies/
            db_tables.json
            external_apis.json
            cache.json
"""
import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiofiles.os

from app.config import settings

logger = logging.getLogger(__name__)

DEP_TYPE_FILE = {
    "db_table": "db_tables.json",
    "external_api": "external_apis.json",
    "cache": "cache.json",
    "kafka_topic": "kafka_topics.json",
}

AGENT_NAMES = ["extraction", "gaps", "test_cases", "bugs", "enrichment"]
EMPTY_RULES = {name: "" for name in AGENT_NAMES}


def slugify(name: str) -> str:
    """Convert name to URL-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "project"


class ProjectStore:
    """Async file-based storage for projects, documents, features, and dependencies."""

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = Path(data_dir or settings.data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _project_dir(self, project_slug: str) -> Path:
        return self._data_dir / project_slug

    def _project_json(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "project.json"

    def _documents_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "documents"

    def _features_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "features"

    @staticmethod
    def _sanitize_feature_name(feature_name: str) -> str:
        """Replace characters unsafe for filesystem paths (e.g. slashes)."""
        return feature_name.replace("/", "__")

    def _feature_dir(self, project_slug: str, feature_name: str) -> Path:
        """Return path to the feature folder: features/{safe_name}/."""
        return self._features_dir(project_slug) / self._sanitize_feature_name(feature_name)

    def _deps_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "dependencies"

    def _gaps_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "gaps"

    def _test_cases_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "test-cases"

    def _bugs_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "bugs"

    async def _read_json(self, path: Path) -> dict | list:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())

    async def _write_json(self, path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict]:
        """Scan DATA_DIR subdirectories, read each project.json."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        projects = []
        try:
            entries = list(self._data_dir.iterdir())
        except OSError:
            return []

        for entry in entries:
            if not entry.is_dir():
                continue
            pjson = entry / "project.json"
            if not pjson.exists():
                continue
            try:
                proj = await self._read_json(pjson)
                # Enrich with counts
                proj["document_count"] = await self._count_documents(proj["slug"])
                proj["feature_count"] = await self._count_features(proj["slug"])
                proj["status"] = await self._compute_project_status(proj["slug"])
                projects.append(proj)
            except Exception as exc:
                logger.warning("Could not read project at %s: %s", entry, exc)

        projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return projects

    async def get_project(self, slug: str) -> dict | None:
        pjson = self._project_json(slug)
        if not pjson.exists():
            return None
        proj = await self._read_json(pjson)
        proj["document_count"] = await self._count_documents(slug)
        proj["feature_count"] = await self._count_features(slug)
        proj["status"] = await self._compute_project_status(slug)
        return proj

    async def create_project(self, name: str) -> dict:
        """Create project directory and project.json. Handles slug collisions."""
        base_slug = slugify(name)
        slug = base_slug
        counter = 2
        while (self._project_dir(slug) / "project.json").exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        now = datetime.now(UTC).isoformat()
        proj = {
            "slug": slug,
            "name": name,
            "created_at": now,
            "status": "empty",
        }

        project_dir = self._project_dir(slug)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "documents").mkdir(exist_ok=True)
        (project_dir / "features").mkdir(exist_ok=True)
        (project_dir / "dependencies").mkdir(exist_ok=True)
        (project_dir / "gaps").mkdir(exist_ok=True)
        (project_dir / "test-cases").mkdir(exist_ok=True)
        (project_dir / "bugs").mkdir(exist_ok=True)

        await self._write_json(self._project_json(slug), proj)

        proj["document_count"] = 0
        proj["feature_count"] = 0
        return proj

    async def update_project(self, slug: str, name: str) -> dict | None:
        proj = await self.get_project(slug)
        if proj is None:
            return None
        proj["name"] = name
        # Remove computed fields before writing
        to_write = {k: v for k, v in proj.items() if k not in ("document_count", "feature_count", "status")}
        await self._write_json(self._project_json(slug), to_write)
        proj["document_count"] = await self._count_documents(slug)
        proj["feature_count"] = await self._count_features(slug)
        proj["status"] = await self._compute_project_status(slug)
        return proj

    async def delete_project(self, slug: str) -> None:
        project_dir = self._project_dir(slug)
        if project_dir.exists():
            shutil.rmtree(project_dir)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def list_documents(self, project_slug: str) -> list[dict]:
        docs_dir = self._documents_dir(project_slug)
        if not docs_dir.exists():
            return []
        docs = []
        for p in docs_dir.glob("*.json"):
            try:
                docs.append(await self._read_json(p))
            except Exception as exc:
                logger.warning("Could not read document %s: %s", p, exc)
        docs.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
        return docs

    async def get_document(self, project_slug: str, doc_slug: str) -> dict | None:
        path = self._documents_dir(project_slug) / f"{doc_slug}.json"
        if not path.exists():
            return None
        doc = await self._read_json(path)
        # Attach features
        doc["features"] = await self.list_features(project_slug)
        return doc

    async def save_document(self, project_slug: str, doc_data: dict) -> dict:
        slug = doc_data["slug"]
        path = self._documents_dir(project_slug) / f"{slug}.json"
        # Don't persist features inline — they're stored separately
        to_write = {k: v for k, v in doc_data.items() if k != "features"}
        await self._write_json(path, to_write)
        return doc_data

    async def update_document(self, project_slug: str, doc_slug: str, updates: dict) -> dict | None:
        path = self._documents_dir(project_slug) / f"{doc_slug}.json"
        if not path.exists():
            return None
        doc = await self._read_json(path)
        doc.update(updates)
        await self._write_json(path, doc)
        return doc

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    async def list_features(self, project_slug: str) -> list[dict]:
        """Scan features_dir for subdirectories containing feature.json.
        Falls back to scanning flat *.json files for backward compatibility.
        """
        features_dir = self._features_dir(project_slug)
        if not features_dir.exists():
            return []
        features = []

        # Primary: folder-based features
        seen_names = set()
        for entry in features_dir.iterdir():
            if not entry.is_dir():
                continue
            feature_json = entry / "feature.json"
            if not feature_json.exists():
                continue
            try:
                feat = await self._read_json(feature_json)
                features.append(feat)
                seen_names.add(entry.name)
            except Exception as exc:
                logger.warning("Could not read feature %s: %s", feature_json, exc)

        # Fallback: flat *.json files (old format, not yet migrated)
        for p in features_dir.glob("*.json"):
            stem = p.stem  # filename without .json extension
            if stem in seen_names:
                continue
            try:
                feat = await self._read_json(p)
                # Strip gaps/test_cases arrays from flat file reads
                feat.pop("gaps", None)
                feat.pop("test_cases", None)
                features.append(feat)
            except Exception as exc:
                logger.warning("Could not read feature %s: %s", p, exc)

        return features

    async def get_feature(self, project_slug: str, feature_name: str) -> dict | None:
        """Read feature data from folder structure. Falls back to flat file."""
        folder_path = self._feature_dir(project_slug, feature_name) / "feature.json"
        if folder_path.exists():
            feat = await self._read_json(folder_path)
            # Strip any residual gaps/test_cases if present
            feat.pop("gaps", None)
            feat.pop("test_cases", None)
            return feat

        # Fallback: old flat file format
        flat_path = self._features_dir(project_slug) / f"{feature_name}.json"
        if not flat_path.exists():
            return None
        feat = await self._read_json(flat_path)
        # Strip gaps/test_cases from old flat file
        feat.pop("gaps", None)
        feat.pop("test_cases", None)
        return feat

    async def save_feature(self, project_slug: str, feature_data: dict) -> dict:
        """Write feature to folder structure. Extracts gaps/test_cases to separate files."""
        name = feature_data["name"]
        feature_dir = self._feature_dir(project_slug, name)
        feature_dir.mkdir(parents=True, exist_ok=True)

        # Extract gaps/test_cases/bugs before writing feature.json
        feature_to_write = dict(feature_data)
        gaps = feature_to_write.pop("gaps", None)
        test_cases = feature_to_write.pop("test_cases", None)
        bugs = feature_to_write.pop("bugs", None)

        # Compute and store counts in feature.json
        sanitized = self._sanitize_feature_name(name)
        if gaps is not None:
            feature_to_write["gap_count"] = len(gaps)
            feature_to_write["pending_gap_count"] = sum(
                1 for g in gaps if g.get("status") == "pending"
            )
            # Write gaps to top-level gaps/ directory
            await self._write_json(
                self._gaps_dir(project_slug) / f"{sanitized}.json",
                {"gaps": gaps},
            )
        if test_cases is not None:
            feature_to_write["test_case_count"] = len(test_cases)
            feature_to_write["pending_test_case_count"] = sum(
                1 for t in test_cases if t.get("status") == "pending"
            )
            # Write test_cases to top-level test-cases/ directory
            await self._write_json(
                self._test_cases_dir(project_slug) / f"{sanitized}.json",
                {"test_cases": test_cases},
            )
        if bugs is not None:
            feature_to_write["bug_count"] = len(bugs)
            # Write bugs to top-level bugs/ directory
            await self._write_json(
                self._bugs_dir(project_slug) / f"{sanitized}.json",
                {"bugs": bugs},
            )

        await self._write_json(feature_dir / "feature.json", feature_to_write)
        return feature_data

    async def update_feature(self, project_slug: str, feature_name: str, updates: dict) -> dict | None:
        """Update feature data. Redirects gaps/test_cases updates to dedicated files."""
        # Resolve the feature.json path (folder-based primary, flat file fallback)
        folder_feature_json = self._feature_dir(project_slug, feature_name) / "feature.json"
        flat_feature_json = self._features_dir(project_slug) / f"{feature_name}.json"

        if folder_feature_json.exists():
            feature_json_path = folder_feature_json
            feature_dir = self._feature_dir(project_slug, feature_name)
        elif flat_feature_json.exists():
            # Migrate: read flat file, convert to folder structure
            feat = await self._read_json(flat_feature_json)
            feature_dir = self._feature_dir(project_slug, feature_name)
            feature_dir.mkdir(parents=True, exist_ok=True)
            # Write clean feature.json (without gaps/test_cases)
            feat_clean = dict(feat)
            feat_clean.pop("gaps", None)
            feat_clean.pop("test_cases", None)
            await self._write_json(feature_dir / "feature.json", feat_clean)
            flat_feature_json.unlink()
            feature_json_path = feature_dir / "feature.json"
        else:
            return None

        feature = await self._read_json(feature_json_path)

        updates_to_apply = dict(updates)

        # Handle gaps update: redirect to top-level gaps/ directory
        sanitized = self._sanitize_feature_name(feature_name)
        if "gaps" in updates_to_apply:
            gaps = updates_to_apply.pop("gaps")
            await self._write_json(
                self._gaps_dir(project_slug) / f"{sanitized}.json",
                {"gaps": gaps},
            )
            # Update counts in feature.json
            updates_to_apply["gap_count"] = len(gaps)
            updates_to_apply["pending_gap_count"] = sum(
                1 for g in gaps if g.get("status") == "pending"
            )

        # Handle test_cases update: redirect to top-level test-cases/ directory
        if "test_cases" in updates_to_apply:
            test_cases = updates_to_apply.pop("test_cases")
            await self._write_json(
                self._test_cases_dir(project_slug) / f"{sanitized}.json",
                {"test_cases": test_cases},
            )
            # Update counts in feature.json
            updates_to_apply["test_case_count"] = len(test_cases)
            updates_to_apply["pending_test_case_count"] = sum(
                1 for t in test_cases if t.get("status") == "pending"
            )

        # Handle bugs update: redirect to top-level bugs/ directory
        if "bugs" in updates_to_apply:
            bugs = updates_to_apply.pop("bugs")
            await self._write_json(
                self._bugs_dir(project_slug) / f"{sanitized}.json",
                {"bugs": bugs},
            )
            # Update count in feature.json
            updates_to_apply["bug_count"] = len(bugs)

        feature.update(updates_to_apply)
        await self._write_json(feature_json_path, feature)
        return feature

    # ------------------------------------------------------------------
    # Gaps (dedicated storage methods)
    # ------------------------------------------------------------------

    async def get_gaps(self, project_slug: str, feature_name: str) -> list[dict]:
        """Read gaps array from gaps/{name}.json (top-level).
        Falls back to old features/{name}/gaps.json with migration.
        Falls back to flat feature.json for oldest format.
        """
        sanitized = self._sanitize_feature_name(feature_name)

        # Primary: new top-level path
        new_path = self._gaps_dir(project_slug) / f"{sanitized}.json"
        if new_path.exists():
            try:
                data = await self._read_json(new_path)
                return data.get("gaps", [])
            except Exception as exc:
                logger.warning("Could not read gaps/%s.json: %s", sanitized, exc)
                return []

        # Fallback 1: old feature-nested gaps.json — migrate on read
        old_path = self._feature_dir(project_slug, feature_name) / "gaps.json"
        if old_path.exists():
            try:
                data = await self._read_json(old_path)
                gaps = data.get("gaps", [])
                # Migrate: copy to new location, delete old
                await self._write_json(new_path, data)
                old_path.unlink()
                logger.info("Migrated gaps for %s to top-level gaps/ dir", feature_name)
                return gaps
            except Exception as exc:
                logger.warning("Could not read/migrate old gaps.json for %s: %s", feature_name, exc)
                return []

        # Fallback 2: old flat feature.json
        flat_path = self._features_dir(project_slug) / f"{feature_name}.json"
        if flat_path.exists():
            try:
                feat = await self._read_json(flat_path)
                return feat.get("gaps", [])
            except Exception as exc:
                logger.warning("Could not read flat feature for gaps %s: %s", feature_name, exc)
        return []

    async def save_gaps(self, project_slug: str, feature_name: str, gaps: list[dict]) -> None:
        """Write gaps to gaps/{name}.json (top-level). Also update gap counts in feature.json."""
        sanitized = self._sanitize_feature_name(feature_name)

        await self._write_json(
            self._gaps_dir(project_slug) / f"{sanitized}.json",
            {"gaps": gaps},
        )

        # Update counts in feature.json
        gap_count = len(gaps)
        pending_gap_count = sum(1 for g in gaps if g.get("status") == "pending")

        feature_json_path = self._feature_dir(project_slug, feature_name) / "feature.json"
        if feature_json_path.exists():
            feature = await self._read_json(feature_json_path)
            feature["gap_count"] = gap_count
            feature["pending_gap_count"] = pending_gap_count
            await self._write_json(feature_json_path, feature)

    # ------------------------------------------------------------------
    # Apply Preview (temporary storage for LLM-generated diff)
    # ------------------------------------------------------------------

    async def get_apply_preview(self, project_slug: str, feature_name: str) -> dict | None:
        """Read apply-preview.json if it exists."""
        path = self._feature_dir(project_slug, feature_name) / "apply-preview.json"
        if not path.exists():
            return None
        return await self._read_json(path)

    async def save_apply_preview(self, project_slug: str, feature_name: str, data: dict) -> None:
        """Write apply-preview.json."""
        feature_dir = self._feature_dir(project_slug, feature_name)
        feature_dir.mkdir(parents=True, exist_ok=True)
        await self._write_json(feature_dir / "apply-preview.json", data)

    async def delete_apply_preview(self, project_slug: str, feature_name: str) -> None:
        """Delete apply-preview.json."""
        path = self._feature_dir(project_slug, feature_name) / "apply-preview.json"
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Test Cases (dedicated storage methods)
    # ------------------------------------------------------------------

    async def get_test_cases(self, project_slug: str, feature_name: str) -> list[dict]:
        """Read test_cases array from test-cases/{name}.json (top-level).
        Falls back to old features/{name}/test-cases.json with migration.
        Falls back to flat feature.json for oldest format.
        """
        sanitized = self._sanitize_feature_name(feature_name)

        # Primary: new top-level path
        new_path = self._test_cases_dir(project_slug) / f"{sanitized}.json"
        if new_path.exists():
            try:
                data = await self._read_json(new_path)
                return data.get("test_cases", [])
            except Exception as exc:
                logger.warning("Could not read test-cases/%s.json: %s", sanitized, exc)
                return []

        # Fallback 1: old feature-nested test-cases.json — migrate on read
        old_path = self._feature_dir(project_slug, feature_name) / "test-cases.json"
        if old_path.exists():
            try:
                data = await self._read_json(old_path)
                test_cases = data.get("test_cases", [])
                # Migrate: copy to new location, delete old
                await self._write_json(new_path, data)
                old_path.unlink()
                logger.info("Migrated test-cases for %s to top-level test-cases/ dir", feature_name)
                return test_cases
            except Exception as exc:
                logger.warning("Could not read/migrate old test-cases.json for %s: %s", feature_name, exc)
                return []

        # Fallback 2: old flat feature.json
        flat_path = self._features_dir(project_slug) / f"{feature_name}.json"
        if flat_path.exists():
            try:
                feat = await self._read_json(flat_path)
                return feat.get("test_cases", [])
            except Exception as exc:
                logger.warning("Could not read flat feature for test_cases %s: %s", feature_name, exc)
        return []

    async def save_test_cases(self, project_slug: str, feature_name: str, test_cases: list[dict]) -> None:
        """Write test_cases to test-cases/{name}.json (top-level). Also update counts in feature.json."""
        sanitized = self._sanitize_feature_name(feature_name)

        await self._write_json(
            self._test_cases_dir(project_slug) / f"{sanitized}.json",
            {"test_cases": test_cases},
        )

        # Update counts in feature.json
        test_case_count = len(test_cases)
        pending_test_case_count = sum(1 for t in test_cases if t.get("status") == "pending")

        feature_json_path = self._feature_dir(project_slug, feature_name) / "feature.json"
        if feature_json_path.exists():
            feature = await self._read_json(feature_json_path)
            feature["test_case_count"] = test_case_count
            feature["pending_test_case_count"] = pending_test_case_count
            await self._write_json(feature_json_path, feature)

    # ------------------------------------------------------------------
    # Bugs (dedicated storage methods)
    # ------------------------------------------------------------------

    async def get_bugs(self, project_slug: str, feature_name: str) -> list[dict]:
        """Read bugs array from bugs/{name}.json (top-level).
        Falls back to old features/{name}/bugs.json with migration.
        """
        sanitized = self._sanitize_feature_name(feature_name)

        # Primary: new top-level path
        new_path = self._bugs_dir(project_slug) / f"{sanitized}.json"
        if new_path.exists():
            try:
                data = await self._read_json(new_path)
                return data.get("bugs", [])
            except Exception as exc:
                logger.warning("Could not read bugs/%s.json: %s", sanitized, exc)
                return []

        # Fallback: old feature-nested bugs.json — migrate on read
        old_path = self._feature_dir(project_slug, feature_name) / "bugs.json"
        if old_path.exists():
            try:
                data = await self._read_json(old_path)
                bugs = data.get("bugs", [])
                # Migrate: copy to new location, delete old
                await self._write_json(new_path, data)
                old_path.unlink()
                logger.info("Migrated bugs for %s to top-level bugs/ dir", feature_name)
                return bugs
            except Exception as exc:
                logger.warning("Could not read/migrate old bugs.json for %s: %s", feature_name, exc)
                return []

        return []

    async def save_bugs(self, project_slug: str, feature_name: str, bugs: list[dict]) -> None:
        """Write bugs to bugs/{name}.json (top-level). Also update bug_count in feature.json."""
        sanitized = self._sanitize_feature_name(feature_name)

        await self._write_json(
            self._bugs_dir(project_slug) / f"{sanitized}.json",
            {"bugs": bugs},
        )

        # Update count in feature.json
        bug_count = len(bugs)

        feature_json_path = self._feature_dir(project_slug, feature_name) / "feature.json"
        if feature_json_path.exists():
            feature = await self._read_json(feature_json_path)
            feature["bug_count"] = bug_count
            await self._write_json(feature_json_path, feature)

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    async def list_dependencies(self, project_slug: str) -> dict[str, list]:
        """Return {dep_type: [dep_dict, ...]} for all 3 dep types."""
        result: dict[str, list] = {dep_type: [] for dep_type in DEP_TYPE_FILE}
        for dep_type, filename in DEP_TYPE_FILE.items():
            path = self._deps_dir(project_slug) / filename
            if path.exists():
                try:
                    data = await self._read_json(path)
                    # data is a dict {name: dep_dict}
                    result[dep_type] = list(data.values())
                except Exception as exc:
                    logger.warning("Could not read deps file %s: %s", path, exc)
        return result

    async def upsert_dependency(
        self,
        project_slug: str,
        dep_type: str,
        name: str,
        data: dict,
    ) -> dict:
        """Read dep file, update/insert entry by name, write back."""
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
        path.parent.mkdir(parents=True, exist_ok=True)

        existing: dict = {}
        if path.exists():
            try:
                existing = await self._read_json(path)
            except Exception:
                existing = {}

        # Merge: preserve existing keys, update with new data
        # Never downgrade enrichment: if already enriched, skip stub overwrites
        if name in existing:
            prev = existing[name]
            if (
                prev.get("enrichment_status") == "enriched"
                and data.get("enrichment_status") == "stub"
            ):
                data = {
                    k: v
                    for k, v in data.items()
                    if k not in ("enriched_data", "enrichment_status", "enriched_at")
                }
            prev.update(data)
        else:
            existing[name] = data

        await self._write_json(path, existing)
        return existing[name]

    async def get_dependency(self, project_slug: str, dep_type: str, name: str) -> dict | None:
        if dep_type not in DEP_TYPE_FILE:
            return None
        path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
        if not path.exists():
            return None
        data = await self._read_json(path)
        return data.get(name)

    async def delete_feature(self, project_slug: str, feature_name: str) -> bool:
        """Delete feature directory and associated gaps/test-cases/bugs files.
        Falls back to flat file removal for backward compatibility.
        Returns True if deleted, False if not found.
        """
        sanitized = self._sanitize_feature_name(feature_name)
        found = False

        feature_dir = self._feature_dir(project_slug, feature_name)
        if feature_dir.exists():
            shutil.rmtree(feature_dir)
            found = True
        else:
            # Fallback: flat file format
            flat_path = self._features_dir(project_slug) / f"{feature_name}.json"
            if flat_path.exists():
                flat_path.unlink()
                found = True

        # Clean up top-level analysis files
        for analysis_path in [
            self._gaps_dir(project_slug) / f"{sanitized}.json",
            self._test_cases_dir(project_slug) / f"{sanitized}.json",
            self._bugs_dir(project_slug) / f"{sanitized}.json",
        ]:
            if analysis_path.exists():
                analysis_path.unlink()

        return found

    async def rename_feature(self, project_slug: str, old_name: str, new_name: str) -> dict | None:
        """Rename feature directory and associated analysis files.
        Returns updated feature dict or None if old_name not found.
        Raises ValueError if new_name already exists.
        """
        old_dir = self._feature_dir(project_slug, old_name)
        if not old_dir.exists():
            return None

        new_dir = self._feature_dir(project_slug, new_name)
        if new_dir.exists():
            raise ValueError(f"Feature with name '{new_name}' already exists")

        old_dir.rename(new_dir)

        # Rename analysis files in top-level directories
        old_sanitized = self._sanitize_feature_name(old_name)
        new_sanitized = self._sanitize_feature_name(new_name)
        for analysis_dir in [
            self._gaps_dir(project_slug),
            self._test_cases_dir(project_slug),
            self._bugs_dir(project_slug),
        ]:
            old_file = analysis_dir / f"{old_sanitized}.json"
            if old_file.exists():
                old_file.rename(analysis_dir / f"{new_sanitized}.json")

        # Update name field in feature.json
        feature_json_path = new_dir / "feature.json"
        if feature_json_path.exists():
            feat = await self._read_json(feature_json_path)
            feat["name"] = new_name
            await self._write_json(feature_json_path, feat)
            return feat

        return {"name": new_name}

    async def delete_dependency(self, project_slug: str, dep_type: str, name: str) -> bool:
        """Remove dependency entry from the type's JSON file.
        Returns True if deleted, False if not found.
        """
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
        if not path.exists():
            return False

        data = await self._read_json(path)
        if name not in data:
            return False

        del data[name]
        await self._write_json(path, data)
        return True

    async def rename_dependency(
        self, project_slug: str, dep_type: str, old_name: str, new_name: str
    ) -> dict | None:
        """Rename dependency key in JSON file and update all features' used_dependencies.
        Returns renamed dep dict or None if old_name not found.
        Raises ValueError if new_name already exists.
        """
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
        if not path.exists():
            return None

        data = await self._read_json(path)
        if old_name not in data:
            return None
        if new_name in data:
            raise ValueError(f"Dependency with name '{new_name}' already exists")

        entry = data.pop(old_name)
        entry["name"] = new_name
        data[new_name] = entry
        await self._write_json(path, data)

        # Scan all features and update used_dependencies references
        features = await self.list_features(project_slug)
        for feat in features:
            feat_name = feat.get("name", "")
            sl = feat.get("structured_logic_json") or feat.get("structured_logic")
            if not isinstance(sl, dict):
                continue
            used_deps = sl.get("used_dependencies", [])
            if not isinstance(used_deps, list):
                continue

            modified = False
            for dep_ref in used_deps:
                if isinstance(dep_ref, dict) and dep_ref.get("type") == dep_type and dep_ref.get("name") == old_name:
                    dep_ref["name"] = new_name
                    modified = True

            if modified:
                # Persist the updated feature.json
                feature_json_path = self._feature_dir(project_slug, feat_name) / "feature.json"
                if feature_json_path.exists():
                    raw = await self._read_json(feature_json_path)
                    # Update structured_logic_json or structured_logic
                    if "structured_logic_json" in raw:
                        if isinstance(raw["structured_logic_json"], dict):
                            raw["structured_logic_json"]["used_dependencies"] = used_deps
                    elif "structured_logic" in raw:
                        if isinstance(raw["structured_logic"], dict):
                            raw["structured_logic"]["used_dependencies"] = used_deps
                    await self._write_json(feature_json_path, raw)

        return entry

    async def update_dependency(
        self,
        project_slug: str,
        dep_type: str,
        name: str,
        updates: dict,
    ) -> dict | None:
        if dep_type not in DEP_TYPE_FILE:
            return None
        path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
        if not path.exists():
            return None
        data = await self._read_json(path)
        if name not in data:
            return None
        data[name].update(updates)
        await self._write_json(path, data)
        return data[name]

    # ------------------------------------------------------------------
    # Rules (global + per-project)
    # ------------------------------------------------------------------

    def _global_rules_path(self) -> Path:
        return self._data_dir / "_global" / "rules.json"

    def _project_rules_path(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "rules.json"

    async def get_global_rules(self) -> dict:
        path = self._global_rules_path()
        if not path.exists():
            return dict(EMPTY_RULES)
        return await self._read_json(path)

    async def save_global_rules(self, rules: dict) -> dict:
        normalized = {k: rules.get(k, "") for k in AGENT_NAMES}
        await self._write_json(self._global_rules_path(), normalized)
        return normalized

    async def get_project_rules(self, project_slug: str) -> dict:
        path = self._project_rules_path(project_slug)
        if not path.exists():
            return dict(EMPTY_RULES)
        return await self._read_json(path)

    async def save_project_rules(self, project_slug: str, rules: dict) -> dict:
        normalized = {k: rules.get(k, "") for k in AGENT_NAMES}
        await self._write_json(self._project_rules_path(project_slug), normalized)
        return normalized

    def get_context_dir(self, project_slug: str) -> Path:
        return self._project_dir(project_slug)

    # ------------------------------------------------------------------
    # Internal helpers for counts/status
    # ------------------------------------------------------------------

    async def _count_documents(self, project_slug: str) -> int:
        docs_dir = self._documents_dir(project_slug)
        if not docs_dir.exists():
            return 0
        return len(list(docs_dir.glob("*.json")))

    async def _count_features(self, project_slug: str) -> int:
        features_dir = self._features_dir(project_slug)
        if not features_dir.exists():
            return 0
        count = 0
        # Count folder-based features (subdirectories with feature.json)
        seen = set()
        for entry in features_dir.iterdir():
            if entry.is_dir() and (entry / "feature.json").exists():
                count += 1
                seen.add(entry.name)
        # Count flat *.json files (backward compat for unmigrated features)
        for p in features_dir.glob("*.json"):
            if p.stem not in seen:
                count += 1
        return count

    async def _compute_project_status(self, project_slug: str) -> str:
        docs = await self.list_documents(project_slug)
        if not docs:
            return "empty"
        statuses = [d.get("status", "pending") for d in docs]
        if any(s in ("processing", "extracting") for s in statuses):
            return "processing"
        if all(s == "done" for s in statuses):
            return "done"
        if any(s == "error" for s in statuses):
            return "partial"
        return "pending"

    # ------------------------------------------------------------------
    # Document slug generation
    # ------------------------------------------------------------------

    def make_doc_slug(self, project_slug: str, filename: str) -> str:
        """Generate unique document slug from filename within a project."""
        base = slugify(filename.removesuffix(".pdf").removesuffix(".PDF"))
        if not base:
            base = "document"
        docs_dir = self._documents_dir(project_slug)
        slug = base
        counter = 2
        while (docs_dir / f"{slug}.json").exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug
