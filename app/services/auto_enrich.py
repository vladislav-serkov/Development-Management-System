"""Auto-enrichment after a Confluence import.

For every stub dependency that points at a link collected from the imported page,
fetch the linked Confluence page and run the targeted enrichment pipeline with its
markdown. Depth is 1: pages linked from the spec only, no transitive crawling.

Work is batched per (page, dep_type): one spec routinely links many dependencies to
the same page — eight tables on one "[flp-order] DB" page, four config parameters
anchored on one service-configuration page — and each such page is fetched once and
sent to Claude once, no matter how many dependencies it feeds.
"""

import asyncio
import logging

from app.services.confluence import fetch_page_by_ref
from app.services.enrichment import enrich_group_from_page
from app.services.required_sync import sync_required_after_enrichment

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
    links: list[dict],
    page_space_key: str,
    store,
) -> None:
    """Enrich stub deps of the project that point at a link of the imported page.

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

    by_type = await store.list_dependencies(project_slug)
    jobs: list[tuple[str, str, dict]] = []
    for dep_type, deps in by_type.items():
        for dep in deps:
            if dep.get("enrichment_status") not in ("stub", "error"):
                continue
            # Several link_ids mean the dependency is documented on several pages
            # (e.g. a table of the same name in two service DBs); the first mention
            # in the spec is the primary one.
            link = next((by_id[lid] for lid in dep.get("link_ids") or [] if lid in by_id), None)
            if link is None:
                title = dep.get("source_doc_title") or ""
                link = by_title.get(_norm(title)) if title else None
            if link is not None:
                jobs.append((dep_type, dep["name"], link))

    if not jobs:
        logger.info("Auto-enrich: no linked stub dependencies for project=%s", project_slug)
        return

    # (page, dep_type) → the dependencies to enrich from that page with one Claude call.
    groups: dict[tuple, tuple[dict, str, list[str]]] = {}
    for dep_type, dep_name, link in jobs:
        ref = _link_ref(link, page_space_key)
        ref_key = tuple(sorted(ref.items()))
        groups.setdefault((ref_key, dep_type), (ref, dep_type, []))[2].append(dep_name)

    logger.info(
        "=== Auto-enrich started: project=%s, %d dependency(ies) → %d page-group(s) ===",
        project_slug, len(jobs), len(groups),
    )

    # One fetch per distinct page, shared across the dep_type groups reading it.
    refs = {ref_key: ref for (ref_key, _), (ref, _, _) in groups.items()}
    fetched = await asyncio.gather(
        *(fetch_page_by_ref(ref) for ref in refs.values()), return_exceptions=True
    )
    pages: dict[tuple, dict | BaseException] = dict(zip(refs, fetched))

    results = await asyncio.gather(
        *(
            _enrich_group(project_slug, dep_type, dep_names, pages[ref_key], store)
            for (ref_key, dep_type), (_, _, dep_names) in groups.items()
        )
    )

    # Finalize failures only now: a table missing from its own page may have been
    # enriched by another page's extraction (db pages adopt every table they describe),
    # so a fast-failing group must not clobber a slower successful one.
    for dep_type, dep_name, task_id, error_msg in [f for group in results for f in group]:
        dep = await store.get_dependency(project_slug, dep_type, dep_name)
        if dep is not None and dep.get("enrichment_status") == "enriched":
            logger.info(
                "Auto-enrich: %s/%s rescued by another page's enrichment", dep_type, dep_name
            )
            if dep.get("enriched_data"):
                await _sync_required(project_slug, dep_type, dep_name, dep["enriched_data"], store)
            await store.finish_task(project_slug, task_id, status="done")
            continue
        logger.error("Auto-enrich failed: %s", error_msg)
        await store.update_dependency(
            project_slug, dep_type, dep_name, {"enrichment_status": "error"}
        )
        await store.finish_task(project_slug, task_id, status="error", error_message=error_msg)

    logger.info("=== Auto-enrich finished: project=%s ===", project_slug)


async def _sync_required(project_slug, dep_type, dep_name, enriched_data, store) -> None:
    """Propagate enriched field metadata into features (non-fatal)."""
    try:
        await sync_required_after_enrichment(
            project_slug=project_slug,
            dep_type=dep_type,
            dep_name=dep_name,
            enriched_data=enriched_data,
            store=store,
        )
    except Exception as exc:
        logger.warning(
            "required_sync after auto-enrich failed (non-fatal): %s/%s: %s",
            dep_type, dep_name, exc,
        )


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
    for dep_name in dep_names:
        tasks[dep_name] = await store.create_task(
            project_slug, kind="enrichment", target_type="dependency", target_id=dep_name,
        )
        await store.update_dependency(
            project_slug, dep_type, dep_name, {"enrichment_status": "running"}
        )

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

        if dep_resp.enriched_data:
            await _sync_required(project_slug, dep_type, dep_name, dep_resp.enriched_data, store)
        await store.finish_task(project_slug, tasks[dep_name]["id"], status="done")
        logger.info("Auto-enrich done: %s/%s ← '%s'", dep_type, dep_name, page["title"])

    return failures
