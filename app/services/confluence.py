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


_LINK_MARKER_RE = re.compile(r"\[LINK:(L\d+)\]")
# "credit_line [LINK:L2] .id" — the link names the dependency, the suffix names the field in it.
_LINK_WITH_FIELD_RE = re.compile(r"\[LINK:(L\d+)\]\s*(?:\.\s*([A-Za-z_]\w*))?")


def strip_link_markers(text: str) -> str:
    """Remove [LINK:Ln] markers from a cell, re-joining the field suffix: 'x [LINK:L2] .id' → 'x.id'.

    Markers exist for the LLM's benefit inside the markdown; they must never reach
    extracted data, where they would surface verbatim in the UI.
    """
    text = re.sub(r"\s*\[LINK:L\d+\]\s*(?=\.)", "", text)
    text = _LINK_MARKER_RE.sub("", text)
    return " ".join(text.split())


def _cell_links(text: str) -> list[dict]:
    """Dependency references carried by one cell: [{'link_id': 'L2', 'field': 'id'}]."""
    return [
        {"link_id": m.group(1), "field": m.group(2)}
        for m in _LINK_WITH_FIELD_RE.finditer(text)
    ]


def _is_struck(cell) -> bool:
    """True when the cell's whole text is struck through — a deprecated spec row."""
    text = " ".join(cell.get_text(" ", strip=True).split())
    if not text:
        return False
    struck = []
    for el in cell.find_all(["s", "del", "strike"]):
        struck.append(el.get_text(" ", strip=True))
    for el in cell.find_all(style=True):
        if "line-through" in (el.get("style") or ""):
            struck.append(el.get_text(" ", strip=True))
    struck_text = " ".join(" ".join(" ".join(struck).split()).split())
    return bool(struck_text) and struck_text == text


def _table_context(table, max_len: int = 200) -> str:
    """Text introducing the table — the spec says what it is right above it.

    "**query**", "**HTTP 200** Тело ответа в формате JSON", "**HTTP 400, 404, 500**":
    this is what tells body from header from query, so it must survive alongside the grid.
    """
    parts: list[str] = []
    # Block-level only: a <strong> inside a <p> would otherwise be picked up twice.
    for prev in table.find_all_previous(["p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        text = " ".join(prev.get_text(" ", strip=True).split())
        if not text or text.startswith("[TABLE:"):
            continue
        parts.append(text)
        # Two blocks back is enough to catch a heading plus its caption line.
        if len(parts) == 2 or sum(len(p) for p in parts) >= max_len:
            break
    return " | ".join(reversed(parts))[:max_len]


def _table_grid(table) -> tuple[list[str], list[list[str]], list[list[list[dict]]], list[int]]:
    """Extract a table as (headers, rows, row_links, deprecated_rows), expanding colspans.

    The colspan expansion preserves the nesting convention of spec tables:
    a nested field's name sits in a deeper column, so 'index of first non-empty
    name cell' equals the nesting depth.

    Cell text is cleaned of [LINK:Ln] markers; the references they carried are kept
    separately in ``row_links`` (parallel to ``rows``), so a "Источник" cell like
    "credit_line [LINK:L2].id" yields the clean text "credit_line.id" *and* a
    machine-readable pointer at the credit_line dependency's ``id`` field.

    ``deprecated_rows`` holds indices of rows struck through in the spec — a field
    the spec has retired (rendered ~~like this~~) must not land in the mapping as
    if it were live.
    """
    grid: list[list[str]] = []
    links_grid: list[list[list[dict]]] = []
    deprecated: list[int] = []

    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells: list[str] = []
        cell_links: list[list[dict]] = []
        struck_flags: list[bool] = []
        for cell in tr.find_all(["th", "td"], recursive=False):
            raw = " ".join(cell.get_text(" ", strip=True).split())
            try:
                span = int(cell.get("colspan") or 1)
            except (TypeError, ValueError):
                span = 1
            cells.append(strip_link_markers(raw))
            cell_links.append(_cell_links(raw))
            struck_flags.append(_is_struck(cell))
            cells.extend([""] * (span - 1))
            cell_links.extend([[] for _ in range(span - 1)])
            struck_flags.extend([False] * (span - 1))
        if not cells:
            continue
        # A row counts as retired only when every cell carrying text is struck through —
        # a single struck word inside one cell is an edit, not a deprecation.
        filled = [i for i, c in enumerate(cells) if c]
        if filled and all(struck_flags[i] for i in filled):
            deprecated.append(len(grid))
        grid.append(cells)
        links_grid.append(cell_links)

    if not grid:
        return [], [], [], []

    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    links_grid = [r + [[] for _ in range(width - len(r))] for r in links_grid]

    # deprecated indices were counted over the full grid (header included) — rebase to rows
    row_deprecated = [i - 1 for i in deprecated if i >= 1]
    return grid[0], grid[1:], links_grid[1:], row_deprecated


def storage_to_markdown(storage_html: str) -> tuple[str, list[dict], list[dict]]:
    """Convert Confluence storage-format XHTML to markdown + collected links + table IR.

    Handles the common ac:/ri: macros: code blocks become fenced code, panel-like
    macros are unwrapped to their rich-text body, images are dropped, everything
    else ac:/ri: is unwrapped so tables/headings survive.

    Returns (markdown, links, tables):
    - links: {'id': 'L1', 'text', 'title', 'space_key', 'page_id', 'anchor'} — enough
      to re-fetch the linked page later (auto-enrichment). Both native ``ac:link``
      and plain ``<a href>`` page links are collected uniformly, and each occurrence
      in the markdown is annotated with a ``[LINK:L1]`` marker right after the link
      text, so the LLM can attach a dependency to a link by id instead of retyping
      the link text character-for-character.
    - tables: {'id': 'T1', 'headers': [...], 'rows': [[...]]} — verbatim table grids;
      a [TABLE:T1] marker is inserted into the markdown right before each table so
      the LLM can reference tables by id instead of re-copying them.
    """
    soup = BeautifulSoup(storage_html, "html.parser")

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

    links: list[dict] = []
    links_by_key: dict[tuple, dict] = {}

    def _register(text: str, target: dict) -> str:
        """Assign (or reuse) an id for one link target and return its [LINK:Ln] marker.

        The same link text can point at different pages (``product_date`` → both
        ``[flp-schedule] DB`` and ``[flp-order] DB``), so the target — not the text —
        is what identifies a link.
        """
        key = (
            target.get("page_id") or "",
            (target.get("space_key") or "").upper(),
            " ".join((target.get("title") or "").split()).lower(),
            target.get("anchor") or "",
        )
        link = links_by_key.get(key)
        if link is None:
            link = {"id": f"L{len(links) + 1}", "text": text, **target}
            links_by_key[key] = link
            links.append(link)
        return f"[LINK:{link['id']}]"

    for link_el in soup.find_all("ac:link"):
        page_ref = link_el.find("ri:page")
        text_el = link_el.find("ac:plain-text-link-body") or link_el.find("ac:link-body")
        text = " ".join((text_el.get_text() if text_el else "").split())
        title = page_ref.get("ri:content-title") if page_ref is not None else None
        if not text:
            text = title or ""
        if not title:
            # Anchor-only link or a link to something other than a page — no target to fetch.
            link_el.replace_with(text)
            continue
        marker = _register(text or title, {
            "title": title,
            "space_key": page_ref.get("ri:space-key") or None,
            "page_id": None,
            "anchor": link_el.get("ac:anchor") or None,
        })
        link_el.replace_with(f"{text or title} {marker}")

    # Plain <a href> links to Confluence pages (pasted URLs, not ac:link)
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = " ".join(a.get_text(strip=True).split())
        if not text or not href.startswith(("http://", "https://")):
            continue
        try:
            ref = parse_page_ref(href)
        except ConfluenceError:
            continue
        marker = _register(text, {
            "title": ref.get("title"),
            "space_key": ref.get("space"),
            "page_id": ref.get("page_id"),
            "anchor": urlparse(href).fragment or None,
        })
        # Replace the whole <a> (URL included) with "text [LINK:Ln]": the raw URL is
        # noise for the LLM, and the marker carries the reference.
        a.replace_with(f"{text} {marker}")

    for img in soup.find_all("ac:image"):
        img.decompose()

    for tag in soup.find_all(True):
        if tag.name and (tag.name.startswith("ac:") or tag.name.startswith("ri:")):
            tag.unwrap()

    tables: list[dict] = []
    for table in soup.find_all("table"):
        if table.find_parent("table") is not None:
            continue
        headers, rows, row_links, deprecated_rows = _table_grid(table)
        if not headers or not rows:
            continue
        table_id = f"T{len(tables) + 1}"
        tables.append({
            "id": table_id,
            "context": _table_context(table),
            "headers": headers,
            "rows": rows,
            "row_links": row_links,
            "deprecated_rows": deprecated_rows,
        })
        marker = soup.new_tag("p")
        marker.string = f"[TABLE:{table_id}]"
        table.insert_before(marker)

    md = markdownify(str(soup), heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md, links, tables
