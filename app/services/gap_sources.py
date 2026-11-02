"""Bounded, versioned source corpus for the specification-only Codex analyst.

Only this backend code fetches pages. The agent requests catalog IDs, never
arbitrary URLs or credentials. Imported originals remain reproducible snapshots.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.services import confluence
from app.services.gap_results import PRIVATE_SOURCE_IDS


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_source_url(url: str) -> dict:
    parsed = urlparse(url)
    base = urlparse(settings.confluence_base_url)
    if not base.hostname:
        raise ValueError("Сначала настройте Confluence для дополнительных источников")
    if parsed.scheme not in ("http", "https") or parsed.netloc != base.netloc or parsed.username:
        raise ValueError("Источники должны ссылаться на настроенный сервер Confluence")
    try:
        return confluence.parse_page_ref(url)
    except confluence.ConfluenceError as exc:
        raise ValueError("Ссылка должна указывать на страницу Confluence") from exc


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class SourceCorpus:
    def __init__(self, store, project: str, feature: dict, workspace: Path, context: dict):
        self.store, self.project, self.feature = store, project, feature
        self.workspace, self.context = workspace, context
        self.catalog: dict[str, dict] = {}
        self.sources: dict[str, dict] = {}
        self.limitations: list[str] = []
        self.primary_id: str | None = None
        self.previous: list[dict] = []
        self.dependencies: list[dict] = []

    def add_ref(self, ref: dict, title: str = "", *, doc_slug: str | None = None) -> str:
        key = {k: str(v) for k, v in ref.items() if k in ("page_id", "space", "title") and v}
        sid = "source-" + digest(key)[:16]
        previous = self.catalog.get(sid, {})
        self.catalog[sid] = {**previous, "id": sid, "title": title or previous.get("title", ""), "ref": key}
        if doc_slug:
            self.catalog[sid]["doc_slug"] = doc_slug
        return sid

    def add_links(self, links: list[dict], default_space: str | None = None) -> None:
        for link in links:
            if link.get("page_id"):
                ref = {"page_id": link["page_id"]}
            elif (link.get("space_key") or default_space) and link.get("title"):
                ref = {"space": link.get("space_key") or default_space, "title": link["title"]}
            elif link.get("title"):
                self.limitations.append(f"Не определено пространство Confluence для ссылки: {link['title']}")
                continue
            else:
                continue
            self.add_ref(ref, link.get("title") or link.get("text") or "")

    def put(self, sid: str, source: dict) -> None:
        markdown = source.get("markdown", "")
        if not markdown.strip():
            raise ValueError("В источнике нет исходного текста")
        if len(markdown.encode()) > 1_000_000:
            raise ValueError("Источник больше 1 МБ; проверка требует отдельного разбора")
        page_id = source.get("confluence_page_id") or source.get("id")
        for existing in self.sources.values():
            if (page_id and str(page_id) == existing.get("page_id") and sid != existing["id"]
                    and digest(markdown) != existing["content_hash"]):
                raise ValueError("Получены разные версии одной страницы; обновите импорт перед анализом")
        url = source.get("confluence_url")
        if not url and page_id:
            url = f"{settings.confluence_base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"
        item = {
            "id": sid, "title": source.get("title") or self.catalog[sid]["title"],
            "url": url or None,
            "page_id": str(page_id) if page_id else None,
            "space_key": source.get("space_key"),
            "service_name": source.get("service_name") or self.catalog[sid].get("service_name"),
            "version": source.get("confluence_version") or source.get("version"),
            "markdown": markdown, "content_hash": digest(markdown),
            "links": source.get("links", []), "tables": source.get("tables", []),
        }
        self.sources[sid] = item
        self.catalog[sid].update(title=item["title"], loaded=True)
        (self.workspace / "sources").mkdir(exist_ok=True)
        (self.workspace / "sources" / f"{sid}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        self.add_links(item["links"], source.get("space_key"))
        self.add_links(source.get("ancestors", []))

    async def prepare(self) -> None:
        documents = await self.store.list_documents(self.project)
        for doc in documents:
            ref = {"page_id": doc["confluence_page_id"]} if doc.get("confluence_page_id") else {
                "title": doc["slug"], "space": "imported",
            }
            sid = self.add_ref(ref, doc.get("filename") or doc.get("title") or doc["slug"], doc_slug=doc["slug"])
            self.catalog[sid]["outdated"] = bool(doc.get("spec_outdated"))
            self.catalog[sid]["service_name"] = doc.get("service_name")
            if doc["slug"] == self.feature.get("source_document"):
                self.primary_id = sid
                if doc.get("spec_outdated"):
                    self.limitations.append("Основное ТЗ обновилось в Confluence; анализируется импортированная версия")
        if not self.primary_id:
            raise ValueError("Не найден оригинал ТЗ фичи. Повторно импортируйте исходную страницу")
        await self.load([self.primary_id])
        if self.primary_id not in self.sources:
            raise ValueError("Оригинал ТЗ недоступен. Повторно импортируйте исходную страницу")
        context_ids = [self.add_ref(validate_source_url(url), url) for url in self.context.get("source_urls", [])]
        await self.load(context_ids)
        deps_by_type = await self.store.list_dependencies(self.project)
        for deps in deps_by_type.values():
            for dep in deps:
                # An index for discovery, not evidence of a schema or business rule.
                self.dependencies.append({k: dep.get(k) for k in (
                    "name", "dep_type", "description", "service_name", "path", "source_page_id", "source_page_version",
                )})
                if dep.get("source_page_id"):
                    self.add_ref({"page_id": dep["source_page_id"]}, dep["name"])
        global_rules = await self.store.get_global_rules()
        project_rules = await self.store.get_project_rules(self.project)
        rules = "\n\n".join(x for x in (global_rules.get("gaps", ""), project_rules.get("gaps", "")) if x)
        if rules:
            sid = "analysis-rules"
            self.catalog[sid] = {"id": sid, "title": "Правила анализа проекта"}
            self.put(sid, {"markdown": rules})
        self.previous = await self.store.get_gaps(self.project, self.feature["name"], include_archived=True)
        self.write_manifest()

    async def load(self, ids: list[str]) -> None:
        for sid in dict.fromkeys(ids):
            entry = self.catalog.get(sid)
            if entry is None:
                self.limitations.append(f"Запрошен неизвестный источник: {sid}")
                continue
            if sid in self.sources or entry.get("error"):
                continue
            if len(self.sources) >= settings.gaps_max_sources:
                self.limitations.append("Достигнут лимит источников; часть связанных спецификаций не проверена")
                break
            try:
                if entry.get("doc_slug"):
                    source = await self.store.get_document_source(self.project, entry["doc_slug"])
                    if not source:
                        raise ValueError("Импорт не содержит оригинала страницы; нужен повторный импорт")
                else:
                    source = await confluence.fetch_page_by_ref(entry["ref"])
                self.put(sid, source)
                if entry.get("outdated"):
                    self.limitations.append(f"{entry['title']}: импортированная версия источника устарела")
            except confluence.ConfluenceError:
                # Do not expose HTTP bodies, PATs or internal filesystem paths.
                entry["error"] = "Источник недоступен; проверьте доступ, VPN и импорт страницы"
                self.limitations.append(f"{entry['title']}: {entry['error']}")
            except ValueError as exc:
                entry["error"] = str(exc)
                self.limitations.append(f"{entry['title']}: {entry['error']}")
        self.write_manifest()

    def write_manifest(self) -> None:
        data = {
            "feature": {key: self.feature.get(key) for key in (
                "name", "type", "method", "endpoint", "summary", "source_document", "structured_logic_json",
            )},
            "primary_source_id": self.primary_id,
            "catalog": list(self.catalog.values()),
            "dependency_index": self.dependencies,
            "business_context": self.context.get("notes", ""),
            "previous_decisions": self.previous,
            "limitations": self.limitations,
        }
        (self.workspace / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def validate_evidence(self, evidence: list[dict]) -> bool:
        return bool(evidence) and all(
            e["source_id"] not in PRIVATE_SOURCE_IDS and e["source_id"] in self.sources
            and bool(normalize(e["quote"]))
            and normalize(e["quote"]) in normalize(self.sources[e["source_id"]]["markdown"])
            for e in evidence
        )

    def source_metadata(self) -> list[dict]:
        return [{k: v for k, v in source.items() if k not in ("markdown", "tables", "links")} for source in self.sources.values()]
