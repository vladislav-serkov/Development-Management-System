"""Source-grounded business gap analysis through the local Codex SDK."""
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.prompts.gap_agent import ANALYZE, SELECT, VERIFY
from app.schemas.gaps import GapReport, SourceSelection
from app.services import agent_runner
from app.services.gap_sources import SourceCorpus, digest, normalize


def now() -> str:
    return datetime.now(UTC).isoformat()


def with_ids(gaps: list[dict]) -> list[dict]:
    """Give legacy entries a deterministic ID without dropping review state."""
    result = []
    used = {g["id"] for g in gaps if g.get("id")}
    for gap in gaps:
        gid = gap.get("id")
        if not gid:
            base = "legacy-" + digest([gap.get("gap_type"), gap.get("question")])[:20]
            gid, duplicate = base, 0
            while gid in used:
                duplicate += 1
                gid = f"{base}-{duplicate}"
            used.add(gid)
        result.append({**gap, "id": gid})
    return result


def merge_findings(existing: list[dict], findings: list[dict], report: dict) -> list[dict]:
    previous = {g["id"]: g for g in with_ids(existing)}
    merged = []
    seen = set()
    for finding in findings:
        finding = dict(finding)
        requested_id = finding.pop("existing_gap_id", None)
        identity = digest([
            finding["gap_type"], finding["subject"].casefold().strip(), finding["location"].casefold().strip(),
            sorted({e["source_id"] for e in finding["evidence"]}),
        ])[:24]
        gid = requested_id if requested_id in previous else "gap-" + identity
        if gid not in previous:
            # A wording/location/source selection change must not bypass a decision.
            matches = [old for old in previous.values() if finding.get("subject") and
                       normalize(old.get("subject", "")).casefold() == normalize(finding["subject"]).casefold()
                       and old.get("gap_type") == finding["gap_type"]]
            if len(matches) == 1:
                gid = matches[0]["id"]
        if gid in seen:
            continue
        seen.add(gid)
        old = previous.get(gid, {})
        fingerprint = {e["source_id"]: next(s["content_hash"] for s in report["sources"] if s["id"] == e["source_id"])
                       for e in finding["evidence"]}
        changed = bool(old.get("source_hashes")) and old["source_hashes"] != fingerprint
        baseline = old.get("review_source_hashes", old.get("source_hashes", {}))
        old_quotes = {(e["source_id"], normalize(e["quote"])) for e in old.get("evidence", [])}
        new_evidence = any(
            baseline.get(e["source_id"]) != fingerprint[e["source_id"]]
            and (e["source_id"], normalize(e["quote"])) not in old_quotes for e in finding["evidence"]
        )
        reconsider = bool((finding.get("reconsideration_reason") or "").strip()) and new_evidence
        needs_review = old.get("needs_review", False) or (
            reconsider if old.get("status") == "rejected" else changed
        )
        if old.get("status") == "rejected" and not needs_review:
            # Retain the evidence underlying the dismissal until genuine new
            # grounds are found. Otherwise reruns would overwrite the baseline.
            merged.append({**old, "presence": "current", "last_seen_at": report["finished_at"]})
            continue
        history = list(old.get("history", []))
        if changed:
            history.append({"at": report["finished_at"], "action": "sources_changed", "text": "Изменились источники замечания"})
        merged.append({
            **old, **finding, "id": gid, "presence": "current", "source_hashes": fingerprint,
            "source_snapshots": [s for s in report["sources"] if s["id"] in fingerprint],
            "status": old.get("status", "pending"), "analyst_text": old.get("analyst_text"),
            "history": history, "needs_review": needs_review,
            "first_seen_at": old.get("first_seen_at", report["started_at"]), "last_seen_at": report["finished_at"],
            "actionable": False,
        })
    for gid, old in previous.items():
        if gid not in seen:
            checked = set(report["checked_source_ids"])
            evidence_ids = {e["source_id"] for e in old.get("evidence", [])}
            # Absence in partial coverage says nothing about resolution.
            absent = report["coverage"] == "complete" and bool(evidence_ids) and evidence_ids <= checked
            merged.append({**old, "presence": "not_detected" if absent else "unverified"})
    return merged


def validate_report(report: dict, corpus: SourceCorpus, started: str) -> dict:
    limitations = [*corpus.limitations, *report["limitations"]]
    checked = set(report["checked_source_ids"])
    if not checked <= corpus.sources.keys():
        limitations.append("Отчёт ссылается на непрочитанные источники")
    checked &= corpus.sources.keys()
    if corpus.primary_id not in checked:
        limitations.append("Не подтверждено чтение основного ТЗ")
    valid_gaps = []
    for gap in report["gaps"]:
        valid = corpus.validate_evidence(gap["evidence"]) and all(
            (gap.get(field) or "").strip() for field in (
                "subject", "location", "question", "scenario", "business_impact", "suggestion",
            )
        )
        if gap["kind"] == "contradiction" and len({(e["source_id"], e["quote"]) for e in gap["evidence"]}) < 2:
            valid = False
        if not {e["source_id"] for e in gap["evidence"]} <= checked:
            valid = False
        if valid:
            valid_gaps.append(gap)
        else:
            limitations.append("Часть замечаний исключена: обоснование, цитаты или источники не подтверждены")
    picture = report["business_picture"]
    if (not corpus.validate_evidence(picture["purpose_evidence"])
            or not {e["source_id"] for e in picture["purpose_evidence"]} <= checked):
        picture["purpose"] = "Назначение операции не подтверждено источниками"
        picture["purpose_evidence"] = []
        limitations.append("Не подтверждено назначение бизнес-операции")
    for section in ("actors", "entities_and_states", "lifecycle", "business_rules"):
        facts = picture[section]
        picture[section] = [f for f in facts if corpus.validate_evidence(f["evidence"])
                            and {e["source_id"] for e in f["evidence"]} <= checked]
        if len(facts) != len(picture[section]):
            limitations.append("Часть бизнес-картины исключена: цитаты не подтверждены")
    if not report["checked_scenarios"]:
        limitations.append("Не перечислены проверенные сценарии")
    limitations = list(dict.fromkeys(limitations))
    return {
        **report, "gaps": valid_gaps, "business_picture": picture,
        "checked_source_ids": sorted(checked), "sources": corpus.source_metadata(),
        "limitations": limitations, "coverage": "partial" if limitations else "complete",
        "started_at": started, "finished_at": now(), "engine": "codex",
        "context_hash": digest(corpus.context),
    }


async def run_gaps_pipeline(project_slug: str, feature_name: str, store, *, task_id: str | None = None) -> list[dict]:
    started = now()
    run_id = uuid.uuid4().hex
    workspace = Path(settings.gaps_log_dir).resolve() / run_id

    async def stage(name: str, error: str | None = None):
        await store.update_feature(project_slug, feature_name, {
            "gaps_job": {"id": run_id, "stage": name, "error": error, "started_at": started},
        })

    try:
        workspace.mkdir(parents=True, mode=0o700)
        await stage("sources")
        feature = await store.get_feature(project_slug, feature_name)
        if feature is None:
            raise ValueError("Фича не найдена")
        context = await store.get_gap_context(project_slug) or {}
        corpus = SourceCorpus(store, project_slug, feature, workspace, context)
        await corpus.prepare()
        corpus.previous = with_ids(corpus.previous)
        corpus.write_manifest()
        await stage("queued")

        async def execute(ask):
            await stage("research")
            for _ in range(4):
                selection = await ask(SELECT, SourceSelection)
                ids = [sid for sid in selection["requested_source_ids"] if sid not in corpus.sources]
                if not ids:
                    break
                await corpus.load(ids)
            else:
                corpus.limitations.append("Достигнут лимит этапов поиска связанных источников")
                corpus.write_manifest()
            await stage("analysis")
            draft = await ask(ANALYZE, GapReport)
            # Preserve the draft for inspection; the verification turn has the
            # same conversation and reads the same immutable original sources.
            (workspace / "draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
            await stage("verification")
            final = await ask(VERIFY, GapReport)
            return validate_report(final, corpus, started)

        result = await agent_runner.analyze(workspace, workspace / "events.jsonl", execute, lambda: stage("research"))
        if digest(await store.get_gap_context(project_slug) or {}) != result["context_hash"]:
            result["limitations"].append("Исходные материалы изменились во время анализа; нужен повторный запуск")
            result["coverage"] = "partial"
        findings = result.pop("gaps")
        await stage("saving")
        merged = await store.mutate_gaps(
            project_slug, feature_name,
            lambda current: merge_findings(current, findings, result), analysis=result,
        )
        if result["coverage"] == "complete":
            await store.clear_stale(project_slug, feature_name, "gaps", started, "gaps_run_at")
        else:
            await store.update_feature(project_slug, feature_name, {"gaps_run_at": now()})
        await stage("done")
        if task_id:
            await store.finish_task(project_slug, task_id, status="done")
        return merged
    except asyncio.CancelledError:
        await stage("cancelled")
        if task_id:
            await store.finish_task(project_slug, task_id, status="error", error_message="Анализ остановлен пользователем")
        raise
    except Exception as exc:
        message = str(exc) if isinstance(exc, (ValueError, agent_runner.AgentError)) else "Не удалось завершить анализ"
        await stage("error", message)
        if task_id:
            await store.finish_task(project_slug, task_id, status="error", error_message=message)
        raise
