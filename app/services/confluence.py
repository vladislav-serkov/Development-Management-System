"""Confluence (Data Center/Server) integration: fetch a page by URL and convert
its storage-format XHTML to markdown for the extraction pipeline.

Auth: Personal Access Token (Bearer), configured via CONFLUENCE_BASE_URL / CONFLUENCE_PAT.
"""

import logging
import re
import ssl
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import truststore
from bs4 import BeautifulSoup
from markdownify import markdownify

from app.config import settings

logger = logging.getLogger(__name__)


class ConfluenceError(Exception):
    """User-facing Confluence integration error (bad URL, auth, page not found)."""


def _require_config() -> tuple[str, str]:
    base = settings.confluence_base_url.rstrip("/")
    pat = settings.confluence_pat
    if not base or not pat:
        raise ConfluenceError(
            "Confluence не настроен: задайте CONFLUENCE_BASE_URL и CONFLUENCE_PAT в .env"
        )
    return base, pat


def parse_page_ref(url: str) -> dict:
    """Parse a Confluence page URL into {'page_id': ...} or {'space': ..., 'title': ...}.

    Supported forms:
      - .../pages/viewpage.action?pageId=123456
      - .../spaces/KEY/pages/123456/Page+Title  (or any /pages/<digits> path)
      - .../display/KEY/Page+Title
      - a bare numeric page id
    """
    url = url.strip()
    if url.isdigit():
        return {"page_id": url}

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "pageId" in qs:
        return {"page_id": qs["pageId"][0]}

    m = re.search(r"/pages/(\d+)", parsed.path)
    if m:
        return {"page_id": m.group(1)}

    m = re.search(r"/display/([^/]+)/([^/?#]+)", parsed.path)
    if m:
        title = unquote(m.group(2)).replace("+", " ")
        return {"space": m.group(1), "title": title}

    raise ConfluenceError(f"Не удалось распознать ссылку на страницу Confluence: {url}")


async def _fetch_page_data(ref: dict) -> dict:
    """Fetch raw page JSON by ref ({'page_id': ...} or {'space': ..., 'title': ...})."""
    base, pat = _require_config()
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    expand = "body.storage,version,space"

    # trust_env=False: внутренний Confluence доступен напрямую, системный HTTP(S)_PROXY его не резолвит.
    # truststore: корпоративный CA лежит в системном хранилище (Keychain), а не в certifi.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with httpx.AsyncClient(
        headers=headers, timeout=60.0, follow_redirects=True, trust_env=False, verify=ssl_context
    ) as client:
        try:
            if "page_id" in ref:
                resp = await client.get(f"{base}/rest/api/content/{ref['page_id']}", params={"expand": expand})
            else:
                resp = await client.get(
                    f"{base}/rest/api/content",
                    params={"spaceKey": ref["space"], "title": ref["title"], "expand": expand},
                )
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Ошибка соединения с Confluence: {exc}") from exc

    if resp.status_code == 401:
        raise ConfluenceError("Confluence отклонил токен (401): проверьте CONFLUENCE_PAT")
    if resp.status_code == 403:
        raise ConfluenceError("Нет доступа к странице (403): у токена не хватает прав")
    if resp.status_code == 404:
        raise ConfluenceError("Страница не найдена в Confluence (404)")
    if resp.status_code != 200:
        raise ConfluenceError(f"Confluence вернул {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    if "page_id" not in ref:
        results = data.get("results") or []
        if not results:
            raise ConfluenceError(
                f"Страница '{ref['title']}' не найдена в пространстве {ref['space']}"
            )
        data = results[0]
    return data


def _page_result(data: dict) -> dict:
    storage_html = ((data.get("body") or {}).get("storage") or {}).get("value", "")
    if not storage_html.strip():
        raise ConfluenceError("Страница пуста — Confluence вернул пустой body.storage")

    markdown, links, tables = storage_to_markdown(storage_html)
    title = data.get("title", "untitled")
    version = ((data.get("version") or {}).get("number")) or 0
    space_key = ((data.get("space") or {}).get("key")) or ""
    logger.info(
        "Confluence page fetched: id=%s, title='%s', version=%s, markdown=%.1fKB, links=%d, tables=%d",
        data.get("id"), title, version, len(markdown) / 1024, len(links), len(tables),
    )
    return {
        "id": str(data.get("id", "")),
        "title": title,
        "version": version,
        "space_key": space_key,
        "markdown": markdown,
        "links": links,
        "tables": tables,
    }


async def fetch_page(url: str) -> dict:
    """Fetch a Confluence page by URL: {'id', 'title', 'version', 'space_key', 'markdown', 'links'}."""
    return _page_result(await _fetch_page_data(parse_page_ref(url)))


async def fetch_page_by_ref(ref: dict) -> dict:
    """Fetch a Confluence page by parsed ref: {'page_id': ...} or {'space': ..., 'title': ...}."""
    return _page_result(await _fetch_page_data(ref))


def _table_grid(table) -> tuple[list[str], list[list[str]]]:
    """Extract a table as (headers, rows) expanding colspans with trailing empty cells.

    The colspan expansion preserves the nesting convention of spec tables:
    a nested field's name sits in a deeper column, so 'index of first non-empty
    name cell' equals the nesting depth.
    """
    grid: list[list[str]] = []
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells: list[str] = []
        for cell in tr.find_all(["th", "td"], recursive=False):
            text = " ".join(cell.get_text(" ", strip=True).split())
            cells.append(text)
            try:
                span = int(cell.get("colspan") or 1)
            except (TypeError, ValueError):
                span = 1
            cells.extend([""] * (span - 1))
        if cells:
            grid.append(cells)
    if not grid:
        return [], []
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    return grid[0], grid[1:]


def storage_to_markdown(storage_html: str) -> tuple[str, list[dict], list[dict]]:
    """Convert Confluence storage-format XHTML to markdown + collected links + table IR.

    Handles the common ac:/ri: macros: code blocks become fenced code, panel-like
    macros are unwrapped to their rich-text body, links become their text, images
    are dropped, everything else ac:/ri: is unwrapped so tables/headings survive.

    Returns (markdown, links, tables):
    - links: {'text', 'title', 'space_key', 'page_id'?} — enough to re-fetch the
      linked page later (auto-enrichment);
    - tables: {'id': 'T1', 'headers': [...], 'rows': [[...]]} — verbatim table grids;
      a [TABLE:T1] marker is inserted into the markdown right before each table so
      the LLM can reference tables by id instead of re-copying them.
    """
    soup = BeautifulSoup(storage_html, "html.parser")
    links: list[dict] = []

    for macro in soup.find_all("ac:structured-macro"):
        name = macro.get("ac:name", "")
        if name in ("code", "codeblock", "noformat"):
            body = macro.find("ac:plain-text-body")
            pre = soup.new_tag("pre")
            pre.string = body.get_text() if body else ""
            macro.replace_with(pre)
        else:
            body = macro.find("ac:rich-text-body") or macro.find("ac:plain-text-body")
            if body is not None:
                body.name = "div"
                macro.replace_with(body)
            else:
                macro.decompose()

    for link in soup.find_all("ac:link"):
        page_ref = link.find("ri:page")
        text_el = link.find("ac:plain-text-link-body") or link.find("ac:link-body")
        text = text_el.get_text() if text_el else ""
        if not text and page_ref is not None:
            text = page_ref.get("ri:content-title", "")
        if page_ref is not None and page_ref.get("ri:content-title"):
            links.append({
                "text": text or page_ref["ri:content-title"],
                "title": page_ref["ri:content-title"],
                "space_key": page_ref.get("ri:space-key") or None,
            })
        link.replace_with(text or "")

    # Plain <a href> links to Confluence pages (pasted URLs, not ac:link)
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        if not text or not href.startswith(("http://", "https://")):
            continue
        try:
            ref = parse_page_ref(href)
        except ConfluenceError:
            continue
        links.append({
            "text": text,
            "title": ref.get("title"),
            "space_key": ref.get("space"),
            "page_id": ref.get("page_id"),
        })

    for img in soup.find_all("ac:image"):
        img.decompose()

    for tag in soup.find_all(True):
        if tag.name and (tag.name.startswith("ac:") or tag.name.startswith("ri:")):
            tag.unwrap()

    tables: list[dict] = []
    for table in soup.find_all("table"):
        if table.find_parent("table") is not None:
            continue
        headers, rows = _table_grid(table)
        if not headers or not rows:
            continue
        table_id = f"T{len(tables) + 1}"
        tables.append({"id": table_id, "headers": headers, "rows": rows})
        marker = soup.new_tag("p")
        marker.string = f"[TABLE:{table_id}]"
        table.insert_before(marker)

    md = markdownify(str(soup), heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md, links, tables
