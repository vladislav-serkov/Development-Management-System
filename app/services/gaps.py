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
from app.services.gap_results import REVIEW_FIELDS, gap_text
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
            base = "legacy-" + digest([gap.get("gap_type"), gap_text(gap)])[:20]
            gid, duplicate = base, 0
            while gid in used:
                duplicate += 1
                gid = f"{base}-{duplicate}"
            used.add(gid)
        result.append({**gap, "id": gid})
    return result


def _quotes(item: dict) -> set[tuple[str, str]]:
    return {(e["source_id"], normalize(e["quote"])) for e in item.get("evidence", [])}


def merge_findings(existing: list[dict], findings: list[dict], report: dict) -> list[dict]:
    previous = {g["id"]: g for g in with_ids(existing)}
    merged, seen = [], set()
    for finding in findings:
        finding = dict(finding)
        requested_id = finding.pop("existing_gap_id", None)
        quotes = _quotes(finding)
        gid = requested_id if requested_id in previous else "gap-" + digest([sorted(quotes), normalize(finding["text"])])[:24]
        if gid not in previous:
            # Citation overlap keeps decisions stable even if wording changes or
            # a model forgets the prior ID. Ambiguous matches are never guessed.
            matches = [old for old in previous.values() if old["id"] not in seen and
                       (quotes & _quotes(old) or normalize(gap_text(old)) == normalize(finding["text"]))]
            if len(matches) == 1:
                gid = matches[0]["id"]
        if gid in seen:
            continue
        seen.add(gid)
        old = previous.get(gid, {})
        state = {k: v for k, v in old.items() if k in REVIEW_FIELDS}
        fingerprint = {e["source_id"]: next(s["content_hash"] for s in report["sources"] if s["id"] == e["source_id"])
                       for e in finding["evidence"]}
        changed = bool(old.get("source_hashes")) and old["source_hashes"] != fingerprint
        baseline = old.get("review_source_hashes", old.get("source_hashes", {}))
        old_quotes = _quotes(old)
        new_evidence = bool(baseline) and any(
            baseline.get(sid) != fingerprint[sid]
            and not any(old_sid == sid and quote in old_quote for old_sid, old_quote in old_quotes)
            for sid, quote in quotes
        )
        needs_review = old.get("needs_review", False) or (
            new_evidence if old.get("status") == "rejected" else changed
        )
        if old.get("status") == "rejected" and not needs_review:
            merged.append({**state, "text": gap_text(old), "evidence": old.get("evidence", []),
                           "source_snapshots": old.get("source_snapshots", []),
                           "presence": "current", "last_seen_at": report["finished_at"]})
            continue
        history = list(old.get("history", []))
        if changed:
            history.append({"at": report["finished_at"], "action": "sources_changed", "text": "Изменились источники замечания"})
        merged.append({
            **state, **finding, "id": gid, "presence": "current", "source_hashes": fingerprint,
            "source_snapshots": [s for s in report["sources"] if s["id"] in fingerprint],
            "status": old.get("status", "pending"), "analyst_text": old.get("analyst_text"),
            "history": history, "needs_review": needs_review,
            "first_seen_at": old.get("first_seen_at", report["started_at"]), "last_seen_at": report["finished_at"],
        })
    for gid, old in previous.items():
        if gid not in seen:
            # Only source availability is tracked by the backend. An absent
            # remark never claims that the source TЗ has been fixed.
            checked = set(report["checked_source_ids"])
            evidence_ids = {e["source_id"] for e in old.get("evidence", [])}
            absent = report["coverage"] == "complete" and bool(evidence_ids) and evidence_ids <= checked
            merged.append({**{k: v for k, v in old.items() if k in REVIEW_FIELDS},
                           "text": gap_text(old), "evidence": old.get("evidence", []),
                           "source_snapshots": old.get("source_snapshots", []),
                           "presence": "not_detected" if absent else "unverified"})
    return merged


def validate_report(report: dict, corpus: SourceCorpus, started: str) -> dict:
    # The model returns only remarks. Runtime diagnostics and source inventory
    # are application metadata, never another report the model must produce.
    limitations = list(corpus.limitations)
    valid_gaps = []
    for gap in report["gaps"]:
        if gap["text"].strip() and corpus.validate_evidence(gap["evidence"]):
            valid_gaps.append({**gap, "text": normalize(gap["text"])})
        else:
            limitations.append("Часть замечаний исключена: текст или цитаты не подтверждены")
    return {
        "gaps": valid_gaps, "checked_source_ids": sorted(corpus.sources),
        "sources": corpus.source_metadata(), "limitations": list(dict.fromkeys(limitations)),
        "coverage": "partial" if limitations else "complete",
        "started_at": started, "finished_at": now(), "context_hash": digest(corpus.context),
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
        (workspace / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
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
