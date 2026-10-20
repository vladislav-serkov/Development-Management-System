"""Auto-enrichment after a Confluence (re-)import.

For every dependency that points at a link collected from the imported page,
fetch the linked Confluence page and run the targeted enrichment pipeline with its
markdown. Depth is 1: pages linked from the spec only, no transitive crawling.

Stub/errored dependencies are enriched; already enriched ones are *refreshed* —
re-imported together with the spec — but only when their source page moved to a
new version (one cheap fetch, no LLM call otherwise). Dependencies enriched before
provenance existed are refreshed once, which backfills their provenance.

Candidates are the dependencies used by the imported document's features, matched
through those features' own [LINK:Ln] ids: link ids are local to a page, so a
dependency row's ids (written by whichever document created it) cannot be trusted
against another page's links.
"""

import asyncio
import logging

from app.services.confluence import fetch_page_by_ref, page_provenance
from app.services.dep_impact import dep_key
from app.services.enrichment import enrich_group_from_page
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)


def _norm(title: str) -> str:
    return " ".join(title.split()).lower()


def _link_ref(link: dict, page_space_key: str) -> dict:
    """Page reference for re-fetching. The link's anchor is deliberately dropped:
    four parameters anchored on one configuration page are one page, one fetch."""
    if link.get("page_id"):
        return {"page_id": link["page_id"]}
    return {
        "space": link.get("space_key") or page_space_key,
        "title": link.get("title") or link.get("text"),
    }


async def auto_enrich_from_links(
    project_slug: str,
    doc_slug: str,
    links: list[dict],
    page_space_key: str,
    store,
) -> None:
    """Enrich stub deps / refresh enriched deps used by the document's features
    that point at a link of the imported page.

    A dependency points at a link either by id (``link_ids``, from the [LINK:Ln]
    markers — the reliable path) or, for documents extracted before markers existed,
    by link text (``source_doc_title``).
    """
    by_id: dict[str, dict] = {link["id"]: link for link in links if link.get("id")}

    # Legacy fallback only. First occurrence wins: the same link text can point to
    # several pages, and without an id there is no way to tell which one was meant.
    by_title: dict[str, dict] = {}
    for link in links:
        for key in (link.get("text"), link.get("title")):
            if key:
                by_title.setdefault(_norm(key), link)

    if not by_id and not by_title:
        return

    # dep_key → the link this document uses for it
    wanted: dict[tuple[str, str], dict] = {}
    for feature in await store.list_features(project_slug):
        if feature.get("source_document") != doc_slug or feature.get("orphaned"):
            continue
        for used in (feature.get("structured_logic_json") or {}).get("used_dependencies") or []:
            # Several link_ids mean the dependency is documented on several pages
            # (e.g. a table of the same name in two service DBs); the first mention
            # in the spec is the primary one.
            link = next((by_id[lid] for lid in used.get("link_ids") or [] if lid in by_id), None)
            if link is None and used.get("source_doc_title"):
                link = by_title.get(_norm(used["source_doc_title"]))
            if link is not None:
                wanted.setdefault(dep_key(used.get("type") or "", used.get("name") or ""), link)

    by_type = await store.list_dependencies(project_slug)
    # (dep_type, dep, ref_key, ref)
    candidates: list[tuple[str, dict, tuple, dict]] = []
    for dep_type, deps in by_type.items():
        for dep in deps:
            if dep.get("enrichment_status") not in ("stub", "error", "enriched"):
                continue
            link = wanted.get(dep_key(dep_type, dep["name"]))
            if link is not None:
                ref = _link_ref(link, page_space_key)
                candidates.append((dep_type, dep, tuple(sorted(ref.items())), ref))

    if not candidates:
        logger.info("Auto-enrich: no linked dependencies for %s/%s", project_slug, doc_slug)
        return

    # One fetch per distinct page — also how a refresh learns the page's version.
    refs = {ref_key: ref for _, _, ref_key, ref in candidates}
    fetched = await asyncio.gather(
        *(fetch_page_by_ref(ref) for ref in refs.values()), return_exceptions=True
    )
    pages: dict[tuple, dict | BaseException] = dict(zip(refs, fetched))

    # (page, dep_type) → the dependencies to enrich from that page with one Claude call.
    groups: dict[tuple, list[str]] = {}
    refreshing: set[tuple[str, str]] = set()
    for dep_type, dep, ref_key, _ in candidates:
        if dep.get("enrichment_status") == "enriched":
            if not _needs_refresh(dep, pages[ref_key]):
                continue
            refreshing.add((dep_type, dep["name"]))
        groups.setdefault((ref_key, dep_type), []).append(dep["name"])

    if not groups:
        logger.info("Auto-enrich: linked dependencies are up to date for project=%s", project_slug)
        return

    logger.info(
        "=== Auto-enrich started: project=%s, %d dependency(ies) (%d refresh) → %d page-group(s) ===",
        project_slug, sum(len(v) for v in groups.values()), len(refreshing), len(groups),
    )

    results = await asyncio.gather(
        *(
            _enrich_group(project_slug, dep_type, dep_names, pages[ref_key], store)
            for (ref_key, dep_type), dep_names in groups.items()
        ),
        return_exceptions=True,
    )
    for group, outcome in zip(groups, results):
        if isinstance(outcome, BaseException):
            logger.error("Auto-enrich group %s crashed: %s", group, outcome)
    results = [r for r in results if not isinstance(r, BaseException)]

    # Finalize failures only now: a table missing from its own page may have been
    # enriched by another page's extraction (db pages adopt every table they describe),
    # so a fast-failing group must not clobber a slower successful one.
    for dep_type, dep_name, task_id, error_msg in [f for group in results for f in group]:
        dep = await store.get_dependency(project_slug, dep_type, dep_name)
        if dep is not None and dep.get("enrichment_status") == "enriched":
            logger.info(
                "Auto-enrich: %s/%s rescued by another page's enrichment", dep_type, dep_name
            )
            await store.finish_task(project_slug, task_id, status="done")
            continue
        logger.error("Auto-enrich failed: %s", error_msg)
        # A failed refresh keeps the previous enrichment: stale data beats no data,
        # and the source_outdated badge still says it needs another try.
        status = "enriched" if (dep_type, dep_name) in refreshing else "error"
        await store.update_dependency(
            project_slug, dep_type, dep_name, {"enrichment_status": status}
        )
        await store.finish_task(project_slug, task_id, status="error", error_message=error_msg)

    logger.info("=== Auto-enrich finished: project=%s ===", project_slug)


def _needs_refresh(dep: dict, page: dict | BaseException) -> bool:
    """Should an already enriched dependency be re-enriched from this page?"""
    if isinstance(page, BaseException):
        return False  # keep what we have; the version check will flag it later
    page_id = str(page.get("id") or "")
    if dep.get("source_page_id"):
        # Enriched from another page on purpose (targeted enrichment) — not ours to touch
        if str(dep["source_page_id"]) != page_id:
            return False
        return page.get("version") != dep.get("source_page_version")
    # Enriched before provenance existed: refresh once to start tracking it
    return True


async def _enrich_group(
    project_slug: str,
    dep_type: str,
    dep_names: list[str],
    page: dict | BaseException,
    store,
) -> list[tuple[str, str, str, str]]:
    """Enrich every dependency of one (page, dep_type) group with a single Claude call.

    Returns failures as (dep_type, dep_name, task_id, error_message) — the caller
    finalizes them after ALL groups finish, so another page can still rescue a dep.
    """
    tasks: dict[str, dict] = {}
    for dep_name in list(dep_names):
        try:
            tasks[dep_name] = await store.create_task(
                project_slug, kind="enrichment", target_type="dependency", target_id=dep_name,
            )
        except ActiveTaskExistsError:
            # Another import/enrichment is on it right now — leave it to that one
            logger.info("Auto-enrich: %s/%s is already being enriched — skipped", dep_type, dep_name)
            dep_names = [n for n in dep_names if n != dep_name]
            continue
        await store.update_dependency(
            project_slug, dep_type, dep_name, {"enrichment_status": "running"}
        )
    if not dep_names:
        return []

    if isinstance(page, BaseException):
        logger.error("Auto-enrich: page fetch failed for %s/%s: %s", dep_type, dep_names, page)
        return [(dep_type, n, tasks[n]["id"], str(page)) for n in dep_names]

    try:
        outcomes, extracted_names = await enrich_group_from_page(
            project_slug=project_slug,
            dep_type=dep_type,
            dep_names=dep_names,
            text_content=page["markdown"],
            source_name=page["title"],
            store=store,
            source_page=page_provenance(page),
        )
    except Exception as exc:
        logger.error("Auto-enrich failed: %s/%s: %s", dep_type, dep_names, exc)
        return [(dep_type, n, tasks[n]["id"], str(exc)) for n in dep_names]

    failures: list[tuple[str, str, str, str]] = []
    for dep_name in dep_names:
        dep_resp = outcomes.get(dep_name)
        if dep_resp is None:
            msg = (
                f"'{dep_name}' ({dep_type}) не найдена на странице '{page['title']}'; "
                f"извлечены: {extracted_names}"
            )
            failures.append((dep_type, dep_name, tasks[dep_name]["id"], msg))
            continue

        await store.finish_task(project_slug, tasks[dep_name]["id"], status="done")
        logger.info("Auto-enrich done: %s/%s ← '%s'", dep_type, dep_name, page["title"])

    return failures
