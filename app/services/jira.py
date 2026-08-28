"""Jira (Data Center) integration: create bug issues from stored bug reports
and read back their live status.

Auth: Personal Access Token (Bearer), configured via JIRA_BASE_URL / JIRA_PAT.
The target project and issue type are fixed by config (JIRA_PROJECT_KEY /
JIRA_ISSUE_TYPE) — one Jira project receives every exported bug.
"""

import asyncio
import logging
import ssl

import httpx
import truststore

from app.config import settings

logger = logging.getLogger(__name__)


class JiraError(Exception):
    """User-facing Jira integration error (config, auth, request rejected)."""


# Jira DC priority names as used in the MTSPAY workflow (Blocker/High for incidents).
SEVERITY_TO_PRIORITY = {
    "critical": "Blocker",
    "major": "High",
    "minor": "Medium",
    "trivial": "Low",
}


def is_configured() -> bool:
    return bool(settings.jira_base_url and settings.jira_pat)


def _require_config() -> tuple[str, str]:
    base = settings.jira_base_url.rstrip("/")
    pat = settings.jira_pat
    if not base or not pat:
        raise JiraError("Jira не настроена: задайте JIRA_BASE_URL и JIRA_PAT в .env")
    return base, pat


def _client(base: str, pat: str) -> httpx.AsyncClient:
    # Same transport quirks as Confluence: internal host reachable directly (no proxy),
    # corporate CA lives in the system keychain rather than certifi.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.AsyncClient(
        base_url=base,
        headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
        timeout=60.0,
        follow_redirects=True,
        trust_env=False,
        verify=ssl_context,
    )


def _code_block(value: str, lang: str | None = None) -> list[str]:
    opener = f"{{code:{lang}}}" if lang else "{code}"
    return [opener, value.rstrip("\n"), "{code}"]


def format_bug_description(bug: dict, feature: dict, spec_url: str | None) -> str:
    """Render a stored bug dict as Jira wiki markup for the issue description."""
    lines: list[str] = []

    f_name = feature.get("name", "")
    f_method = feature.get("method") or ""
    f_endpoint = feature.get("endpoint") or ""
    feature_line = f_name
    if f_method and f_endpoint:
        feature_line += f" ({f_method} {f_endpoint})"
    elif f_endpoint:
        feature_line += f" ({f_endpoint})"

    lines.append(f"*Фича:* {feature_line}")
    if bug.get("test_case_name"):
        lines.append(f"*Тест-кейс:* {bug['test_case_name']}")
    if spec_url:
        lines.append(f"*ТЗ:* [{spec_url}]")
    lines.append("")

    if bug.get("analyst_text"):
        lines += ["*Наблюдение тестировщика:*", bug["analyst_text"], ""]

    steps = bug.get("steps") or []
    if steps:
        lines.append("h3. Сценарий")
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step.get('action', '')}")
            if step.get("result"):
                lines.append(f"Результат: {step['result']}")
            if step.get("curl_command"):
                lines += _code_block(step["curl_command"], "bash")
            if step.get("sql_query"):
                lines += _code_block(step["sql_query"], "sql")
            if step.get("kafka_message"):
                lines += _code_block(step["kafka_message"])
        lines.append("")

    lines += [
        "h3. ОР — ожидаемый результат",
        bug.get("expected_result", ""),
        "",
        "h3. ФР — фактический результат",
        bug.get("actual_result", ""),
        "",
        "----",
        "_Создано автоматически из Extract Agent_",
    ]
    return "\n".join(lines)


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    if resp.status_code == 401:
        raise JiraError("Jira отклонила токен (401): проверьте JIRA_PAT (нужен именно Jira-токен, не Confluence)")
    if resp.status_code == 403:
        raise JiraError(f"Нет прав в Jira (403): {context}")
    raise JiraError(f"Jira вернула {resp.status_code} ({context}): {resp.text[:300]}")


def build_issue_fields(
    bug: dict,
    feature: dict,
    spec_url: str | None,
    service_name: str | None,
    sprint_id: int | None = None,
    feature_ticket: str | None = None,
) -> dict:
    """Issue fields payload for POST /rest/api/2/issue."""
    summary = bug.get("title", "")[:250] or "Баг-репорт из Extract Agent"
    # Team convention: bug summaries carry the service in brackets ("[flp-order] ...")
    if service_name and not summary.startswith("["):
        summary = f"[{service_name}] {summary}"

    fields = {
        "project": {"key": settings.jira_project_key},
        "issuetype": {"name": settings.jira_issue_type},
        "summary": summary,
        "description": format_bug_description(bug, feature, spec_url),
        "priority": {"name": SEVERITY_TO_PRIORITY.get(bug.get("severity", ""), "Medium")},
    }
    if settings.jira_bug_type:
        fields["customfield_10519"] = {"value": settings.jira_bug_type}
    if settings.jira_system:
        fields["customfield_10523"] = [{"value": settings.jira_system}]
    if settings.jira_team:
        fields["customfield_20600"] = [{"value": settings.jira_team}]
    if settings.jira_developer:
        fields["customfield_10402"] = [{"name": settings.jira_developer}]  # ОР
    if settings.jira_fix_version:
        fields["fixVersions"] = [{"name": settings.jira_fix_version}]
    if sprint_id is not None:
        fields["customfield_10108"] = sprint_id  # Спринт
    if feature_ticket:
        fields["customfield_10107"] = feature_ticket.strip().upper()  # Feature Link (epic key)
    return fields


async def _active_sprint_id(client: httpx.AsyncClient) -> int | None:
    """Id of the configured board's own active sprint (shared boards expose foreign ones too)."""
    if not settings.jira_board_id:
        return None
    try:
        resp = await client.get(
            f"/rest/agile/1.0/board/{settings.jira_board_id}/sprint", params={"state": "active"}
        )
    except httpx.HTTPError as exc:
        logger.warning("[jira] Active sprint lookup failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning("[jira] Active sprint lookup returned %s: %s", resp.status_code, resp.text[:200])
        return None
    sprints = resp.json().get("values") or []
    own = [s for s in sprints if s.get("originBoardId") == settings.jira_board_id]
    chosen = (own or sprints)[-1] if sprints else None
    return chosen.get("id") if chosen else None


# Nice-to-have fields: a bad value must not block bug creation — dropped on a 400 that names them.
_OPTIONAL_FIELDS = ("priority", "fixVersions", "customfield_10402", "customfield_10108", "customfield_10107")


async def create_bug_issue(
    bug: dict,
    feature: dict,
    spec_url: str | None,
    service_name: str | None = None,
    feature_ticket: str | None = None,
) -> dict:
    """Create a Bug issue in the configured Jira project.

    Returns {"key": "MTSPAY-123", "url": "https://jira.../browse/MTSPAY-123"}.
    """
    base, pat = _require_config()

    async with _client(base, pat) as client:
        sprint_id = await _active_sprint_id(client)
        fields = build_issue_fields(bug, feature, spec_url, service_name, sprint_id, feature_ticket)
        try:
            resp = await client.post("/rest/api/2/issue", json={"fields": fields})
            if resp.status_code == 400:
                rejected = [f for f in _OPTIONAL_FIELDS if f in fields and f in resp.text]
                if rejected:
                    logger.warning("[jira] Retrying issue creation without rejected fields %s: %s",
                                   rejected, resp.text[:300])
                    for f in rejected:
                        del fields[f]
                    resp = await client.post("/rest/api/2/issue", json={"fields": fields})
        except httpx.HTTPError as exc:
            detail = str(exc) or type(exc).__name__
            raise JiraError(f"Ошибка соединения с Jira: {detail}") from exc

    if resp.status_code not in (200, 201):
        _raise_for_status(resp, f"создание задачи в проекте {settings.jira_project_key}")

    key = resp.json().get("key")
    if not key:
        raise JiraError(f"Jira не вернула ключ созданной задачи: {resp.text[:300]}")
    url = f"{base}/browse/{key}"
    logger.info("[jira] Created issue %s for bug '%s'", key, bug.get("title", ""))
    return {"key": key, "url": url}


async def fetch_issue_statuses(keys: list[str]) -> dict[str, str | None]:
    """Current status name per issue key; None for issues Jira no longer knows."""
    base, pat = _require_config()

    async with _client(base, pat) as client:
        async def fetch_one(key: str) -> tuple[str, str | None]:
            try:
                resp = await client.get(f"/rest/api/2/issue/{key}", params={"fields": "status"})
            except httpx.HTTPError as exc:
                detail = str(exc) or type(exc).__name__
                raise JiraError(f"Ошибка соединения с Jira: {detail}") from exc
            if resp.status_code == 404:
                return key, None
            if resp.status_code != 200:
                _raise_for_status(resp, f"чтение статуса {key}")
            status = (((resp.json().get("fields") or {}).get("status")) or {}).get("name")
            return key, status

        results = await asyncio.gather(*(fetch_one(k) for k in keys))
    return dict(results)
