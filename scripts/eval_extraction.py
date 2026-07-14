"""Extraction eval harness: run the pipeline against saved pages and score the gaps.

Works on fixtures — a fixture is the raw imported page (markdown + links + tables),
exactly what the pipeline sees — so prompt/parser changes can be compared without
re-fetching from Confluence.

    # save a page as a fixture (one Confluence round-trip)
    python scripts/eval_extraction.py fetch <confluence-url> penalty-tariff

    # run detection on it and score (one Claude call), then again after a change
    python scripts/eval_extraction.py run fixtures/penalty-tariff.json

The scores are gap detectors, not vanity metrics:
  - link coverage — links in the page that no dependency claims. Every such link is
    a dependency the extraction dropped, or one that will never auto-enrich.
  - unlinked deps  — dependencies with no link: they stay stubs and need manual URLs.
  - lost mappings  — steps flagged has_detailed_mapping with no message_mapping:
    the field mapping was seen and then lost.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services.extraction import (  # noqa: E402
    _apply_response_param_in,
    _apply_table_mappings,
    _build_link_resolver,
    _detect_features,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
LINK_MARKER = re.compile(r"\[LINK:(L\d+)\]")


async def cmd_fetch(url: str, name: str) -> None:
    from app.services.confluence import fetch_page

    page = await fetch_page(url)
    FIXTURES.mkdir(exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(
        json.dumps({"url": url, **page}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"saved {path}\n"
        f"  title:    {page['title']}\n"
        f"  markdown: {len(page['markdown']) / 1024:.1f}KB\n"
        f"  links:    {len(page['links'])}\n"
        f"  tables:   {len(page['tables'])}"
    )


def _walk(steps):
    for step in steps:
        yield step
        yield from _walk(step.children)


def _score(page: dict, features) -> dict:
    marker_ids = set(LINK_MARKER.findall(page["markdown"]))
    links_by_id = {link["id"]: link for link in page["links"] if link.get("id")}

    claimed: set[str] = set()
    deps: list[dict] = []
    lost_mappings: list[str] = []
    used_tables: set[str] = set()

    for feature in features:
        logic = feature.structured_logic
        for dep in logic.used_dependencies:
            claimed.update(dep.link_ids)
            deps.append(
                {
                    "feature": feature.name,
                    "type": dep.type,
                    "name": dep.name,
                    "link_ids": dep.link_ids,
                }
            )
        for step in _walk(logic.logic_steps):
            used_tables.update(t.strip().upper() for t in step.mapping_table_ids)
            if step.has_detailed_mapping and not step.message_mapping:
                lost_mappings.append(f"{feature.name}:{step.number}")

    all_tables = {t["id"].upper() for t in page["tables"]}
    return {
        "features": [(f.name, f.type.value) for f in features],
        "deps": deps,
        "uncovered_links": sorted(
            marker_ids - claimed, key=lambda i: int(i[1:])
        ),
        "links_by_id": links_by_id,
        "unlinked_deps": [d for d in deps if not d["link_ids"]],
        "lost_mappings": lost_mappings,
        "unused_tables": sorted(all_tables - used_tables),
        "link_total": len(marker_ids),
    }


def _report(score: dict) -> None:
    covered = score["link_total"] - len(score["uncovered_links"])
    linked_deps = len(score["deps"]) - len(score["unlinked_deps"])

    print("\n=== features ===")
    for name, ftype in score["features"]:
        print(f"  {ftype:15} {name}")

    print(f"\n=== dependencies ({len(score['deps'])}) ===")
    for dep in score["deps"]:
        mark = ",".join(dep["link_ids"]) if dep["link_ids"] else "— no link"
        print(f"  {dep['type']:13} {dep['name']:55} {mark}")

    print("\n=== scores ===")
    print(f"  link coverage:  {covered}/{score['link_total']} links claimed by a dependency")
    print(f"  linked deps:    {linked_deps}/{len(score['deps'])} can auto-enrich")
    print(f"  lost mappings:  {len(score['lost_mappings'])} steps flagged with mapping but empty")
    print(f"  unused tables:  {len(score['unused_tables'])}")

    if score["uncovered_links"]:
        print("\n  !! links no dependency claims (dropped dependencies):")
        for lid in score["uncovered_links"]:
            link = score["links_by_id"].get(lid, {})
            print(f"     {lid}: {link.get('text')!r} → {link.get('title') or link.get('page_id')}")
    if score["unlinked_deps"]:
        print("\n  !! dependencies with no link (will stay stubs):")
        for dep in score["unlinked_deps"]:
            print(f"     {dep['type']}/{dep['name']}")
    if score["lost_mappings"]:
        print(f"\n  !! steps with lost field mapping: {', '.join(score['lost_mappings'])}")


async def cmd_run(fixture: Path) -> None:
    page = json.loads(fixture.read_text(encoding="utf-8"))
    features = await _detect_features(page["markdown"], settings.claude_model)

    tables_by_id = {t["id"].upper(): t for t in page["tables"]}
    for feature in features:
        if tables_by_id:
            _apply_table_mappings(
                feature.structured_logic.logic_steps,
                tables_by_id,
                _build_link_resolver(feature.structured_logic.used_dependencies),
            )
        _apply_response_param_in(feature.structured_logic, tables_by_id)

    score = _score(page, features)
    _report(score)

    out = fixture.with_suffix(".result.json")
    out.write_text(
        json.dumps(
            {"features": [f.model_dump() for f in features]}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"\nresult → {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="save a Confluence page as a fixture")
    p_fetch.add_argument("url")
    p_fetch.add_argument("name")

    p_run = sub.add_parser("run", help="run detection on a fixture and score it")
    p_run.add_argument("fixture", type=Path)

    args = parser.parse_args()
    if args.cmd == "fetch":
        asyncio.run(cmd_fetch(args.url, args.name))
    else:
        asyncio.run(cmd_run(args.fixture))


if __name__ == "__main__":
    main()
