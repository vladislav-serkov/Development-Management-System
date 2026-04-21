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
import asyncio
import json
import logging
import os
import re
import shutil
import uuid
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


class ProjectStore:
    """Async file-based storage for projects, documents, features, and dependencies."""

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = Path(data_dir or settings.data_dir)
        self._dep_locks: dict[str, asyncio.Lock] = {}
        self._registry_cache: dict | None = None

    def _get_dep_lock(self, project_slug: str, dep_type: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for a specific project+dep_type combination."""
        key = f"{project_slug}:{dep_type}"
        if key not in self._dep_locks:
            self._dep_locks[key] = asyncio.Lock()
        return self._dep_locks[key]

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _project_dir(self, project_slug: str) -> Path:
        entry = self._get_linked_entry(project_slug)
        if entry is not None:
            return Path(entry["external_path"]) / ".context"
        return self._data_dir / project_slug

    # ------------------------------------------------------------------
    # Linked project registry
    # ------------------------------------------------------------------

    def _registry_path(self) -> Path:
        return self._data_dir / "registry.json"

    def _load_registry(self) -> dict:
        if self._registry_cache is None:
            path = self._registry_path()
            if path.exists():
                try:
                    self._registry_cache = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.warning("Could not read registry: %s", exc)
                    self._registry_cache = {"linked": []}
            else:
                self._registry_cache = {"linked": []}
            self._registry_cache.setdefault("linked", [])
        return self._registry_cache

    def _persist_registry(self, registry: dict) -> None:
        path = self._registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
        self._registry_cache = registry

    def _get_linked_entry(self, slug: str) -> dict | None:
        for entry in self._load_registry().get("linked", []):
            if entry.get("slug") == slug:
                return entry
        return None

    def _find_linked_by_path(self, external_path: str) -> dict | None:
        target = str(Path(external_path).resolve())
        for entry in self._load_registry().get("linked", []):
            try:
                if str(Path(entry["external_path"]).resolve()) == target:
                    return entry
            except Exception:
                continue
        return None

    def _register_link(self, slug: str, name: str, external_path: str) -> dict:
        registry = self._load_registry()
        entry = {
            "slug": slug,
            "name": name,
            "external_path": str(Path(external_path).resolve()),
            "linked_at": datetime.now(UTC).isoformat(),
        }
        registry["linked"].append(entry)
        self._persist_registry(registry)
        return entry

    def _unregister_link(self, slug: str) -> dict | None:
        registry = self._load_registry()
        before = registry.get("linked", [])
        after = [e for e in before if e.get("slug") != slug]
        if len(after) == len(before):
            return None
        removed = next(e for e in before if e.get("slug") == slug)
        registry["linked"] = after
        self._persist_registry(registry)
        return removed

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

    # Per-path asyncio locks to prevent concurrent read-modify-write races
    _locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, path: Path) -> asyncio.Lock:
        key = str(path)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _read_json(self, path: Path) -> dict | list:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())

    async def _write_json(self, path: Path, data: dict | list) -> None:
        """Atomic write: write to .tmp file, then os.rename (atomic on POSIX)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        os.replace(str(tmp_path), str(path))

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        """Delete file if it exists, ignore if already gone."""
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict]:
        """Scan DATA_DIR subdirectories + linked registry, read each project.json."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        projects = []
        linked_slugs = {e.get("slug") for e in self._load_registry().get("linked", [])}

        try:
            entries = list(self._data_dir.iterdir())
        except OSError:
            entries = []

        for entry in entries:
            if not entry.is_dir():
                continue
            pjson = entry / "project.json"
            if not pjson.exists():
                continue
            if entry.name in linked_slugs:
                # A linked slug lives in registry, not in data_dir
                continue
            try:
                proj = await self._read_json(pjson)
                proj["document_count"] = await self._count_documents(proj["slug"])
                proj["feature_count"] = await self._count_features(proj["slug"])
                proj["status"] = await self._compute_project_status(proj["slug"])
                proj["is_linked"] = False
                proj["external_path"] = None
                proj["available"] = True
                projects.append(proj)
            except Exception as exc:
                logger.warning("Could not read project at %s: %s", entry, exc)

        for link in self._load_registry().get("linked", []):
            slug = link.get("slug")
            external = link.get("external_path")
            if not slug or not external:
                continue
            pjson = Path(external) / ".context" / "project.json"
            if pjson.exists():
                try:
                    proj = await self._read_json(pjson)
                    proj["slug"] = slug  # registry slug wins
                    proj["document_count"] = await self._count_documents(slug)
                    proj["feature_count"] = await self._count_features(slug)
                    proj["status"] = await self._compute_project_status(slug)
                    proj["is_linked"] = True
                    proj["external_path"] = external
                    proj["available"] = True
                    projects.append(proj)
                except Exception as exc:
                    logger.warning("Could not read linked project %s: %s", slug, exc)
            else:
                projects.append({
                    "slug": slug,
                    "name": link.get("name", slug),
                    "created_at": link.get("linked_at", ""),
                    "document_count": 0,
                    "feature_count": 0,
                    "status": "empty",
                    "is_linked": True,
                    "external_path": external,
                    "available": False,
                })

        projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return projects

    async def get_project(self, slug: str) -> dict | None:
        entry = self._get_linked_entry(slug)
        pjson = self._project_json(slug)
        if not pjson.exists():
            if entry is None:
                return None
            return {
                "slug": slug,
                "name": entry.get("name", slug),
                "created_at": entry.get("linked_at", ""),
                "document_count": 0,
                "feature_count": 0,
                "status": "empty",
                "is_linked": True,
                "external_path": entry.get("external_path"),
                "available": False,
            }
        proj = await self._read_json(pjson)
        proj["slug"] = slug
        proj["document_count"] = await self._count_documents(slug)
        proj["feature_count"] = await self._count_features(slug)
        proj["status"] = await self._compute_project_status(slug)
        proj["is_linked"] = entry is not None
        proj["external_path"] = entry.get("external_path") if entry else None
        proj["available"] = True
        return proj

    async def create_project(self, name: str) -> dict:
        """Create project directory and project.json. Handles slug collisions."""
        base_slug = slugify(name)
        slug = base_slug
        counter = 2
        while self._slug_taken(slug):
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
        proj["is_linked"] = False
        proj["external_path"] = None
        proj["available"] = True
        return proj

    def _slug_taken(self, slug: str) -> bool:
        """True if slug is registered as a link or has a local project dir."""
        if self._get_linked_entry(slug) is not None:
            return True
        return (self._data_dir / slug / "project.json").exists()

    async def link_project(self, external_path: str) -> dict:
        """Attach an existing `.context/` inside `external_path` (create if missing).

        Raises ValueError with a user-facing message on conflicts.
        """
        base = Path(external_path).expanduser()
        if not base.exists() or not base.is_dir():
            raise ValueError(f"Directory does not exist: {external_path}")
        resolved = base.resolve()

        existing_by_path = self._find_linked_by_path(str(resolved))
        if existing_by_path is not None:
            # Same directory already attached — return the existing project.
            result = await self.get_project(existing_by_path["slug"])
            if result is not None:
                return result

        context_dir = resolved / ".context"
        project_json_path = context_dir / "project.json"

        if project_json_path.exists():
            try:
                existing_proj = json.loads(project_json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError(f"Could not parse existing .context/project.json: {exc}") from exc
            name = existing_proj.get("name") or resolved.name
            slug = existing_proj.get("slug") or slugify(name)
            if self._slug_taken(slug):
                raise ValueError(
                    f"Project with slug '{slug}' is already linked or exists locally. "
                    "Rename the project in its .context/project.json or remove the existing entry."
                )
            # Ensure project.json has up-to-date slug
            existing_proj["slug"] = slug
            existing_proj.setdefault("name", name)
            existing_proj.setdefault("created_at", datetime.now(UTC).isoformat())
            existing_proj.setdefault("status", "empty")
            self._register_link(slug, name, str(resolved))
            await self._write_json(project_json_path, existing_proj)
            for sub in ("documents", "features", "dependencies", "gaps", "test-cases", "bugs"):
                (context_dir / sub).mkdir(parents=True, exist_ok=True)
        else:
            name = resolved.name or "project"
            base_slug = slugify(name)
            slug = base_slug
            counter = 2
            while self._slug_taken(slug):
                slug = f"{base_slug}-{counter}"
                counter += 1
            now = datetime.now(UTC).isoformat()
            proj = {
                "slug": slug,
                "name": name,
                "created_at": now,
                "status": "empty",
            }
            self._register_link(slug, name, str(resolved))
            context_dir.mkdir(parents=True, exist_ok=True)
            for sub in ("documents", "features", "dependencies", "gaps", "test-cases", "bugs"):
                (context_dir / sub).mkdir(parents=True, exist_ok=True)
            await self._write_json(project_json_path, proj)

        return await self.get_project(slug)

    async def update_project(self, slug: str, name: str) -> dict | None:
        proj = await self.get_project(slug)
        if proj is None:
            return None
        proj["name"] = name
        # Remove computed fields before writing
        to_write = {
            k: v for k, v in proj.items()
            if k not in ("document_count", "feature_count", "status", "is_linked", "external_path", "available")
        }
        await self._write_json(self._project_json(slug), to_write)
        # Update cached registry name if linked
        entry = self._get_linked_entry(slug)
        if entry is not None:
            registry = self._load_registry()
            for e in registry["linked"]:
                if e.get("slug") == slug:
                    e["name"] = name
            self._persist_registry(registry)
        return await self.get_project(slug)

    async def delete_project(self, slug: str, *, remove_files: bool = False) -> None:
        """Delete project. For linked projects, by default only removes from registry.
        With remove_files=True, also removes .context/ on disk (linked) or rmtree (local).
        """
        entry = self._get_linked_entry(slug)
        if entry is not None:
            if remove_files:
                ctx_dir = Path(entry["external_path"]) / ".context"
                if ctx_dir.exists():
                    shutil.rmtree(ctx_dir)
            self._unregister_link(slug)
            return

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
        async with self._get_lock(path):
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
        folder_feature_json = self._feature_dir(project_slug, feature_name) / "feature.json"
        async with self._get_lock(folder_feature_json):
            return await self._update_feature_locked(project_slug, feature_name, updates)

    async def _update_feature_locked(self, project_slug: str, feature_name: str, updates: dict) -> dict | None:
        """Update feature data (called under lock). Redirects gaps/test_cases updates to dedicated files."""
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
            self._safe_unlink(flat_feature_json)
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

    async def get_gaps(self, project_slug: str, feature_name: str, *, include_archived: bool = False) -> list[dict]:
        """Read gaps array from gaps/{name}.json (top-level).
        Falls back to old features/{name}/gaps.json with migration.
        Falls back to flat feature.json for oldest format.
        By default filters out archived gaps.
        """
        sanitized = self._sanitize_feature_name(feature_name)

        # Primary: new top-level path
        new_path = self._gaps_dir(project_slug) / f"{sanitized}.json"
        if new_path.exists():
            try:
                data = await self._read_json(new_path)
                all_gaps = data.get("gaps", [])
                if include_archived:
                    return all_gaps
                return [g for g in all_gaps if not g.get("archived")]
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
                self._safe_unlink(old_path)
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

        # Update counts in feature.json (exclude archived)
        active_gaps = [g for g in gaps if not g.get("archived")]
        gap_count = len(active_gaps)
        pending_gap_count = sum(1 for g in active_gaps if g.get("status") == "pending")

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
        self._safe_unlink(path)

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
                self._safe_unlink(old_path)
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
                self._safe_unlink(old_path)
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

    @staticmethod
    def _find_key_ci(data: dict, name: str) -> str | None:
        """Find dict key by case-insensitive match. Returns actual key or None."""
        if name in data:
            return name
        lower = name.lower()
        for key in data:
            if key.lower() == lower:
                return key
        return None

    async def list_dependencies(self, project_slug: str) -> dict[str, list]:
        """Return {dep_type: [dep_dict, ...]} for all 3 dep types."""
        result: dict[str, list] = {dep_type: [] for dep_type in DEP_TYPE_FILE}
        for dep_type, filename in DEP_TYPE_FILE.items():
            path = self._deps_dir(project_slug) / filename
            if path.exists():
                try:
                    data = await self._read_json(path)
                    # data is a dict {name: dep_dict}; normalize for app format
                    result[dep_type] = [
                        _normalize_dep(dep_dict, key, dep_type)
                        for key, dep_dict in data.items()
                    ]
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
        """Read dep file, update/insert entry by name, write back. Thread-safe per project+dep_type."""
        if dep_type not in DEP_TYPE_FILE:
            raise ValueError(f"Unknown dep_type: {dep_type}")

        async with self._get_dep_lock(project_slug, dep_type):
            path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
            path.parent.mkdir(parents=True, exist_ok=True)

            existing: dict = {}
            if path.exists():
                try:
                    existing = await self._read_json(path)
                except Exception:
                    existing = {}

            # Case-insensitive lookup: find existing key regardless of case
            actual_key = self._find_key_ci(existing, name)

            # Merge: preserve existing keys, update with new data
            # Never downgrade enrichment: if already enriched, skip stub overwrites
            if actual_key is not None:
                prev = existing[actual_key]
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
                # If incoming name has different case, re-key to preserve original case
                if actual_key != name:
                    existing[name] = existing.pop(actual_key)
                    existing[name]["name"] = name
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
        actual_key = self._find_key_ci(data, name)
        if actual_key is None:
            return None
        dep = _normalize_dep(data[actual_key], actual_key, dep_type)
        return dep

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
                self._safe_unlink(flat_path)
                found = True

        # Clean up top-level analysis files
        for analysis_path in [
            self._gaps_dir(project_slug) / f"{sanitized}.json",
            self._test_cases_dir(project_slug) / f"{sanitized}.json",
            self._bugs_dir(project_slug) / f"{sanitized}.json",
        ]:
            self._safe_unlink(analysis_path)

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

        async with self._get_dep_lock(project_slug, dep_type):
            path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
            if not path.exists():
                return False

            data = await self._read_json(path)
            actual_key = self._find_key_ci(data, name)
            if actual_key is None:
                return False

            del data[actual_key]
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

        async with self._get_dep_lock(project_slug, dep_type):
            path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
            if not path.exists():
                return None

            data = await self._read_json(path)
            actual_old = self._find_key_ci(data, old_name)
            if actual_old is None:
                return None
            actual_new = self._find_key_ci(data, new_name)
            if actual_new is not None and actual_new != actual_old:
                raise ValueError(f"Dependency with name '{new_name}' already exists")

            entry = data.pop(actual_old)
            entry["name"] = new_name
            data[new_name] = entry
            await self._write_json(path, data)

        # Scan all features and update used_dependencies references (outside lock)
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
        async with self._get_dep_lock(project_slug, dep_type):
            path = self._deps_dir(project_slug) / DEP_TYPE_FILE[dep_type]
            if not path.exists():
                return None
            data = await self._read_json(path)
            actual_key = self._find_key_ci(data, name)
            if actual_key is None:
                return None
            data[actual_key].update(updates)
            data[actual_key] = _normalize_dep(data[actual_key], actual_key, dep_type)
            await self._write_json(path, data)
            return data[actual_key]

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
    # Tasks (background-task log, per-project)
    # ------------------------------------------------------------------

    def _tasks_path(self, project_slug: str) -> Path:
        return self._project_dir(project_slug) / "tasks.json"

    async def _read_tasks(self, project_slug: str) -> list[dict]:
        path = self._tasks_path(project_slug)
        if not path.exists():
            return []
        data = await self._read_json(path)
        return data.get("tasks", []) if isinstance(data, dict) else []

    async def _write_tasks(self, project_slug: str, tasks: list[dict]) -> None:
        await self._write_json(self._tasks_path(project_slug), {"tasks": tasks})

    async def create_task(
        self,
        project_slug: str,
        *,
        kind: str,
        target_type: str,
        target_id: str,
    ) -> dict:
        """Append a new running task to tasks.json and return it."""
        lock = self._get_lock(self._tasks_path(project_slug))
        async with lock:
            tasks = await self._read_tasks(project_slug)
            task = {
                "id": str(uuid.uuid4()),
                "kind": kind,
                "target_type": target_type,
                "target_id": target_id,
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "finished_at": None,
                "error_message": None,
                "duration_ms": None,
            }
            tasks.append(task)
            await self._write_tasks(project_slug, tasks)
            return task

    async def update_task(
        self,
        project_slug: str,
        task_id: str,
        updates: dict,
    ) -> dict | None:
        """Merge updates into a task by id. Returns the updated task or None."""
        lock = self._get_lock(self._tasks_path(project_slug))
        async with lock:
            tasks = await self._read_tasks(project_slug)
            for i, t in enumerate(tasks):
                if t.get("id") == task_id:
                    tasks[i] = {**t, **updates}
                    await self._write_tasks(project_slug, tasks)
                    return tasks[i]
            return None

    async def finish_task(
        self,
        project_slug: str,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> dict | None:
        """Close a running task with done/error, set finished_at + duration_ms."""
        lock = self._get_lock(self._tasks_path(project_slug))
        async with lock:
            tasks = await self._read_tasks(project_slug)
            now = datetime.now(UTC)
            for i, t in enumerate(tasks):
                if t.get("id") != task_id:
                    continue
                started = t.get("started_at")
                duration_ms: int | None = None
                if started:
                    try:
                        started_dt = datetime.fromisoformat(started)
                        duration_ms = int((now - started_dt).total_seconds() * 1000)
                    except (ValueError, TypeError):
                        duration_ms = None
                tasks[i] = {
                    **t,
                    "status": status,
                    "finished_at": now.isoformat(),
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                }
                await self._write_tasks(project_slug, tasks)
                return tasks[i]
            return None

    async def list_tasks(
        self,
        project_slug: str,
        *,
        status: str | None = None,
        kind: str | None = None,
        target_id: str | None = None,
    ) -> list[dict]:
        tasks = await self._read_tasks(project_slug)
        if status is not None:
            tasks = [t for t in tasks if t.get("status") == status]
        if kind is not None:
            tasks = [t for t in tasks if t.get("kind") == kind]
        if target_id is not None:
            tasks = [t for t in tasks if t.get("target_id") == target_id]
        tasks.sort(key=lambda t: t.get("started_at", ""), reverse=True)
        return tasks

    async def get_active_task(
        self,
        project_slug: str,
        *,
        kind: str,
        target_id: str,
    ) -> dict | None:
        """Return the running task for (kind, target_id) if any, else None.

        Used by routers to enforce «no concurrent task of the same kind for
        the same target» (returns 409 to the client).
        """
        tasks = await self._read_tasks(project_slug)
        for t in tasks:
            if (
                t.get("status") == "running"
                and t.get("kind") == kind
                and t.get("target_id") == target_id
            ):
                return t
        return None

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
