"""Feature identity: what a feature extracted from a spec page is called.

The model reads the whole page — its title and place in the page tree included —
and states the parts of the identity (type, HTTP method, path / topic / operation,
human-readable title). Code only does what it can do reliably:

- checks that every stated part literally occurs on the page (nothing invented);
- assembles ``name`` from the parts, so its format never depends on the model;
- keeps the identity the page already has in the project (``prior``) for as long
  as it is still on the page, so a re-import cannot rename a feature just because
  the model picked another real token this time.

There is deliberately no rule about how a page title must look: titles in the
wild are "POST /v1/x", "[svc] POST/v1/x", "[svc] getWallet.do – Получение клиента",
a bare topic, "[svc] Обработчик топика a.b.c", "[svc] Отправка сообщений outbox".
The title is evidence (the strongest one), not a format to parse.
"""

from __future__ import annotations

import difflib
import json
import re

from app.schemas.extraction import DetectedFeature

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Dotted identifiers like Kafka topics: at least three dot-separated segments
_DOTTED_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}\b")
# URL-ish paths like /v1/credit-line or /api/orders/{id}
_PATH_TOKEN_RE = re.compile(r"(?<![\w.])/(?:[\w.-]+|\{[\w.-]+\})(?:/(?:[\w.-]+|\{[\w.-]+\}))+")
# "POST/v1/x": a method glued to its path is still a method and a path
_GLUED_METHOD_RE = re.compile(rf"\b({'|'.join(HTTP_METHODS)})/")
_METHOD_WORD_RE = re.compile(rf"\b({'|'.join(HTTP_METHODS)})\b")
_SERVICE_PREFIX_RE = re.compile(r"^\s*\[[^\]]+\]\s*")
_TOKEN_CHARS = r"\w./{}-"


def page_header(title: str | None, ancestors: list[dict] | None = None, service_name: str | None = None) -> str:
    """What the model is told about the page besides its body. The path, the
    method or the topic is often written only in the page title."""
    lines = [f"Заголовок страницы: {' '.join((title or '').split())}"]
    trail = [" ".join(str(a.get("title") or "").split()) for a in ancestors or []]
    trail = [t for t in trail if t]
    if trail:
        lines.append("Расположение: " + " / ".join(trail))
    if service_name:
        lines.append(f"Сервис: {service_name}")
    return "[СТРАНИЦА]\n" + "\n".join(lines) + "\n[/СТРАНИЦА]"


def strip_service_prefix(title: str | None) -> str:
    """"[flp-rbo-adapter] Автоматические задачи" → "Автоматические задачи"."""
    return _SERVICE_PREFIX_RE.sub("", " ".join((title or "").split())).strip()


def _unglue(text: str) -> str:
    return _GLUED_METHOD_RE.sub(r"\1 /", text or "")


def occurs(token: str | None, text: str | None) -> bool:
    """The token is on the page as a whole path/topic/operation — not as a piece
    of a longer one ("/v1/credit" inside "/v1/credit-line", "/v1/x" inside
    "/api/v1/x", "b.c.queue" inside "a.b.c.queue")."""
    token = (token or "").strip()
    if not token or not text:
        return False
    text = _unglue(text)
    start = 0
    while (pos := text.find(token, start)) != -1:
        start = pos + 1
        tail = re.match(rf"[{_TOKEN_CHARS}]*", text[pos + len(token):]).group(0).rstrip("./-")
        head = re.search(rf"[{_TOKEN_CHARS}]*$", text[:pos]).group(0)
        if tail:
            continue
        # a path may follow anything but a longer path; a bare token must stand alone
        if "/" in head if token.startswith("/") else head.lstrip("./-{}"):
            continue
        return True
    return False


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def _resolve_token(
    claimed: str, prior: str, *, title: str, corpus: str, token_re: re.Pattern, single_feature: bool,
) -> tuple[str | None, str | None]:
    """Pick the path/topic of a feature. Returns (token, why it is not the claimed one).

    Evidence, strongest first: stated in the page title → already the identity of
    this page and still on it → stated anywhere on the page → the closest real
    token (the model mistyped it). A token found nowhere is never accepted when
    the page offers a real one.
    """
    title_tokens = _unique(token_re.findall(_unglue(title)))
    if claimed and occurs(claimed, title):
        return claimed, None
    if prior and occurs(prior, title):
        return prior, "прежнее значение есть в заголовке страницы"
    if single_feature and len(title_tokens) == 1:
        return title_tokens[0], "страница названа по нему"
    if prior and occurs(prior, corpus):
        return prior, "прежнее значение по-прежнему есть на странице"
    if claimed and occurs(claimed, corpus):
        return claimed, None
    candidates = _unique(token_re.findall(_unglue(corpus)))
    if claimed and candidates:
        close = difflib.get_close_matches(claimed, candidates, n=1, cutoff=0.6)
        if close:
            return close[0], "заявленного значения на странице нет, взято ближайшее"
    if title_tokens:
        return title_tokens[0], "заявленного значения на странице нет, взято из заголовка"
    return (claimed or None), ("на странице не найдено (оставлено как есть)" if claimed else None)


def _resolve_method(claimed: str | None, prior: str | None, title: str) -> str | None:
    in_title = _unique(_METHOD_WORD_RE.findall(_unglue(title)))
    if len(in_title) == 1:
        return in_title[0]
    claimed = (claimed or "").strip().upper()
    if claimed in HTTP_METHODS:
        return claimed
    prior = (prior or "").strip().upper()
    return prior if prior in HTTP_METHODS else None


def _plain(text: str | None) -> str:
    """Text for a verbatim check: whitespace and markdown emphasis don't count."""
    return " ".join(re.sub(r"[*`_]", "", text or "").split())


def _resolve_display_name(claimed: str | None, prior: str | None, *, corpus_plain: str, taken: set[str]) -> str | None:
    """Human-readable title of a REST/Kafka feature: a verbatim line of the page.
    The one already stored wins while it is still there — a re-import must not
    report a "renamed" feature because the model quoted another line."""
    for value in (prior, claimed):
        value = " ".join((value or "").split())
        # the path/topic itself is the name, not the title
        if not value or any(token in value for token in taken):
            continue
        if _plain(value) in corpus_plain:
            return value
    return None


def resolve_identity(
    detected: DetectedFeature,
    *,
    title: str,
    text: str,
    tables: list[dict] | None = None,
    prior: dict | None = None,
    single_feature: bool = False,
) -> str | None:
    """Settle ``name`` / ``endpoint`` / ``method`` / ``display_name`` of a detected
    feature in place. ``prior`` — the feature this page already has in the project
    that ``detected`` continues (None on a first import). Returns a note when the
    result differs from what the model stated.
    """
    ftype = detected.type.value if hasattr(detected.type, "value") else str(detected.type)
    prior = prior or {}
    if prior.get("type") and prior.get("type") != ftype:
        prior = {}
    body = "\n".join([text or "", json.dumps(tables or [], ensure_ascii=False)])
    corpus = "\n".join([title or "", body])
    note = None

    if ftype == "kafka_consumer":
        claimed = (detected.endpoint or detected.name or "").strip()
        topic, why = _resolve_token(
            claimed, (prior.get("endpoint") or "").strip(),
            title=title, corpus=corpus, token_re=_DOTTED_TOKEN_RE, single_feature=single_feature,
        )
        if topic:
            detected.name = detected.endpoint = topic
        if why and topic != claimed:
            note = f"kafka topic '{claimed}' → '{topic}': {why}"
        elif why:
            note = f"kafka topic '{claimed}': {why}"

    elif ftype == "rest_endpoint":
        claimed = (detected.endpoint or "").strip()
        path, why = _resolve_token(
            claimed, (prior.get("endpoint") or "").strip(),
            title=title, corpus=corpus, token_re=_PATH_TOKEN_RE, single_feature=single_feature,
        )
        method = _resolve_method(detected.method, prior.get("method"), title)
        detected.method = method
        if path:
            detected.endpoint = path
            detected.name = f"{method} {path}" if method else path
            if why and path != claimed:
                note = f"REST endpoint '{claimed}' → '{path}': {why}"
            elif why:
                note = f"REST endpoint '{claimed}': {why}"
        else:
            # The page names no path or operation: the feature is called what the
            # page is called (or what it was called before), never what the model made up
            detected.endpoint = None
            fallback = prior.get("name") or (strip_service_prefix(title) if single_feature else "")
            if fallback:
                detected.name = fallback
            note = f"у REST-эндпоинта на странице не найден путь — имя '{detected.name}'"

    else:
        # scheduled_task / unknown: the name is a slug the model derives from a
        # heading; once the page has one it is kept (the verbatim identity of
        # such a feature is its display_name)
        if prior.get("name"):
            detected.name = prior["name"]
        return None

    detected.display_name = _resolve_display_name(
        detected.display_name, prior.get("display_name"),
        corpus_plain=_plain(corpus),
        taken={v for v in (detected.name, detected.endpoint) if v},
    )
    return note
