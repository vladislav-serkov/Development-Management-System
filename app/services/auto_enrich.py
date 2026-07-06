"""Auto-enrichment after a Confluence import.

For every stub dependency whose ``source_doc_title`` matches a link collected
from the imported page, fetch the linked Confluence page and run the targeted
enrichment pipeline with its markdown. Depth is 1: pages linked from the spec
only, no transitive crawling.
"""

import asyncio
import logging

from app.services.confluence import fetch_page_by_ref
from app.services.enrichment import enrich_db_tables_from_page, run_enrichment_pipeline

logger = logging.getLogger(__name__)


def _norm(title: str) -> str:
    return " ".join(title.split()).lower()


def _link_ref(link: dict, page_space_key: str) -> dict:
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
    """Enrich stub deps of the project whose source_doc_title matches an imported-page link."""
    # First occurrence wins: the same link text can point to several pages
    # (e.g. a stale duplicate later in the spec) — the first mention is primary.
    by_title: dict[str, dict] = {}
    for link in links:
        for key in (link.get("text"), link.get("title")):
            if key:
                by_title.setdefault(_norm(key), link)

    if not by_title:
        return

    by_type = await store.list_dependencies(project_slug)
    jobs: list[tuple[str, str, dict]] = []
    for dep_type, deps in by_type.items():
        for dep in deps:
            if dep.get("enrichment_status") not in ("stub", "error"):
                continue
            title = dep.get("source_doc_title") or ""
            link = by_title.get(_norm(title)) if title else None
            if link is not None:
                jobs.append((dep_type, dep["name"], link))

    if not jobs:
        logger.info("Auto-enrich: no linked stub dependencies for project=%s", project_slug)
        return

    logger.info(
        "=== Auto-enrich started: project=%s, %d dependency(ies): %s ===",
        project_slug, len(jobs), [(t, n) for t, n, _ in jobs],
    )

    # db_table deps often all live on one page — group them by target page and
    # enrich each page with a single Claude call instead of one call per table.
    db_groups: dict[tuple, tuple[dict, list[str]]] = {}
    other_jobs: list[tuple[str, str, dict]] = []
    for dep_type, dep_name, link in jobs:
        if dep_type != "db_table":
            other_jobs.append((dep_type, dep_name, link))
            continue
        key = tuple(sorted(_link_ref(link, page_space_key).items()))
        db_groups.setdefault(key, (link, []))[1].append(dep_name)

    results = await asyncio.gather(
        *(
            _enrich_one(project_slug, dep_type, dep_name, link, page_space_key, store)
            for dep_type, dep_name, link in other_jobs
        ),
        *(
            _enrich_db_group(project_slug, dep_names, link, page_space_key, store)
            for link, dep_names in db_groups.values()
        ),
    )

    # Finalize db-group failures only now: a table missing from its own page may
    # have been enriched by another group's page (all tables are upserted), so a
    # fast-failing group must not clobber a slower successful one.
    db_failures = [f for r in results if r for f in r]
    for dep_name, task_id, error_msg in db_failures:
        dep = await store.get_dependency(project_slug, "db_table", dep_name)
        if dep is not None and dep.get("enrichment_status") == "enriched":
            logger.info(
                "Auto-enrich: db_table/%s rescued by another page's enrichment", dep_name
            )
            if dep.get("enriched_data"):
                from app.services.required_sync import sync_required_after_enrichment
                try:
                    await sync_required_after_enrichment(
                        project_slug=project_slug,
                        dep_type="db_table",
                        dep_name=dep_name,
                        enriched_data=dep["enriched_data"],
                        store=store,
                    )
                except Exception as sync_exc:
                    logger.warning(
                        "required_sync after rescue failed (non-fatal): db_table/%s: %s",
                        dep_name, sync_exc,
                    )
            await store.finish_task(project_slug, task_id, status="done")
            continue
        logger.error("Auto-enrich (db group): %s", error_msg)
        await store.update_dependency(
            project_slug, "db_table", dep_name, {"enrichment_status": "error"}
        )
        await store.finish_task(project_slug, task_id, status="error", error_message=error_msg)

    logger.info("=== Auto-enrich finished: project=%s ===", project_slug)


async def _enrich_db_group(
    project_slug: str,
    dep_names: list[str],
    link: dict,
    page_space_key: str,
    store,
) -> list[tuple[str, str, str]]:
    """Fetch one page and enrich all db_table stubs pointing at it with a single Claude call.

    Returns failures as (dep_name, task_id, error_message) — the caller finalizes them
    after ALL groups finish, so another page's enrichment can still rescue a dep.
    """
    tasks: dict[str, dict] = {}
    for dep_name in dep_names:
        tasks[dep_name] = await store.create_task(
            project_slug, kind="enrichment", target_type="dependency", target_id=dep_name,
        )
        await store.update_dependency(
            project_slug, "db_table", dep_name, {"enrichment_status": "running"}
        )

    try:
        page = await fetch_page_by_ref(_link_ref(link, page_space_key))
        outcomes, extracted_names = await enrich_db_tables_from_page(
            project_slug=project_slug,
            dep_names=dep_names,
            text_content=page["markdown"],
            source_name=page["title"],
            store=store,
        )
    except Exception as exc:
        logger.error("Auto-enrich (db group) failed: %s: %s", dep_names, exc)
        return [(dep_name, tasks[dep_name]["id"], str(exc)) for dep_name in dep_names]

    failures: list[tuple[str, str, str]] = []
    from app.services.required_sync import sync_required_after_enrichment
    for dep_name in dep_names:
        dep_resp = outcomes.get(dep_name)
        if dep_resp is None:
            msg = (
                f"Таблица '{dep_name}' не найдена на странице '{page['title']}'; "
                f"извлечены: {extracted_names}"
            )
            failures.append((dep_name, tasks[dep_name]["id"], msg))
            continue

        if dep_resp.enriched_data:
            try:
                await sync_required_after_enrichment(
                    project_slug=project_slug,
                    dep_type="db_table",
                    dep_name=dep_name,
                    enriched_data=dep_resp.enriched_data,
                    store=store,
                )
            except Exception as sync_exc:
                logger.warning(
                    "required_sync after auto-enrich failed (non-fatal): db_table/%s: %s",
                    dep_name, sync_exc,
                )
        await store.finish_task(project_slug, tasks[dep_name]["id"], status="done")
        logger.info("Auto-enrich done: db_table/%s ← '%s'", dep_name, page["title"])

    return failures


async def _enrich_one(
    project_slug: str,
    dep_type: str,
    dep_name: str,
    link: dict,
    page_space_key: str,
    store,
) -> None:
    """Fetch one linked page and run targeted enrichment. Failures are non-fatal: dep → error."""
    task = await store.create_task(
        project_slug, kind="enrichment", target_type="dependency", target_id=dep_name,
    )
    await store.update_dependency(project_slug, dep_type, dep_name, {"enrichment_status": "running"})
    try:
        if link.get("page_id"):
            ref = {"page_id": link["page_id"]}
        else:
            ref = {
                "space": link.get("space_key") or page_space_key,
                "title": link.get("title") or link.get("text"),
            }
        page = await fetch_page_by_ref(ref)

        enriched_deps = await run_enrichment_pipeline(
            project_slug=project_slug,
            dep_type=dep_type,
            text_content=page["markdown"],
            source_name=page["title"],
            store=store,
            target_dep_name=dep_name,
        )

        from app.services.required_sync import sync_required_after_enrichment
        for dep_resp in enriched_deps:
            if dep_resp.enriched_data:
                try:
                    await sync_required_after_enrichment(
                        project_slug=project_slug,
                        dep_type=dep_resp.dep_type,
                        dep_name=dep_resp.name,
                        enriched_data=dep_resp.enriched_data,
                        store=store,
                    )
                except Exception as sync_exc:
                    logger.warning(
                        "required_sync after auto-enrich failed (non-fatal): %s/%s: %s",
                        dep_resp.dep_type, dep_resp.name, sync_exc,
                    )

        await store.finish_task(project_slug, task["id"], status="done")
        logger.info("Auto-enrich done: %s/%s ← '%s'", dep_type, dep_name, page["title"])
    except Exception as exc:
        logger.error("Auto-enrich failed: %s/%s: %s", dep_type, dep_name, exc)
        await store.update_dependency(project_slug, dep_type, dep_name, {"enrichment_status": "error"})
        await store.finish_task(project_slug, task["id"], status="error", error_message=str(exc))
