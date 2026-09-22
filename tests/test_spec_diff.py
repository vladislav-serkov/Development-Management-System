"""Unit tests for the deterministic spec diff (no DB, no LLM)."""

from app.services.spec_diff import (
    compute_spec_diff,
    diff_feature,
    merge_reextracted_feature,
)


def _feature(name="GET /v1/x", **overrides):
    base = {
        "name": name,
        "display_name": None,
        "type": "rest_endpoint",
        "method": "GET",
        "endpoint": "/v1/x",
        "schedule": None,
        "summary": "Возвращает X",
        "structured_logic_json": {
            "input_tables": [
                {
                    "caption": "Входные параметры",
                    "columns": [{"header": "Параметр"}, {"header": "Тип"}, {"header": "Обяз."}],
                    "fields": [
                        {"name": "clientId", "cells": ["clientId", "string", "да"], "children": []},
                        {
                            "name": "filter",
                            "cells": ["filter", "object", "нет"],
                            "children": [
                                {"name": "status", "cells": ["status", "string", "нет"], "children": []},
                            ],
                        },
                    ],
                }
            ],
            "response_tables": [],
            "logic_steps": [
                {"number": "1", "text": "Проверить клиента", "children": [], "mapping_tables": []},
                {"number": "2", "text": "Вернуть данные", "children": [], "mapping_tables": []},
            ],
            "used_dependencies": [
                {"type": "db_table", "name": "credit_line", "description": ""},
            ],
        },
    }
    base.update(overrides)
    return base


def _with_logic(feature, **logic_overrides):
    import copy

    feat = copy.deepcopy(feature)
    feat["structured_logic_json"].update(logic_overrides)
    return feat


class TestDiffFeature:
    def test_identical_features_diff_to_none(self):
        assert diff_feature(_feature(), _feature()) is None

    def test_whitespace_only_change_is_not_a_change(self):
        old = _feature()
        new = _feature(summary="Возвращает  X ")
        new["structured_logic_json"]["logic_steps"][0]["text"] = " Проверить\nклиента "
        assert diff_feature(old, new) is None

    def test_summary_only_change_is_not_material(self):
        detail = diff_feature(_feature(), _feature(summary="Отдаёт X"))
        assert detail is not None
        assert detail["summary_changed"] is True
        assert detail["material"] is False

    def test_identity_change_is_material(self):
        detail = diff_feature(_feature(), _feature(endpoint="/v2/x"))
        assert detail["material"] is True
        assert detail["identity"] == [{"field": "endpoint", "old": "/v1/x", "new": "/v2/x"}]

    def test_field_cell_change_reports_column(self):
        old = _feature()
        new = _feature()
        new["structured_logic_json"]["input_tables"][0]["fields"][0]["cells"] = ["clientId", "string", "нет"]
        detail = diff_feature(old, new)
        assert detail["material"] is True
        [table] = detail["tables"]
        assert table["section"] == "входные параметры"
        assert table["changed_fields"] == [
            {"name": "clientId", "changes": [{"column": "Обяз.", "old": "да", "new": "нет"}]}
        ]

    def test_nested_field_added_and_removed(self):
        old = _feature()
        new = _feature()
        fields = new["structured_logic_json"]["input_tables"][0]["fields"]
        fields[1]["children"] = [{"name": "dateFrom", "cells": ["dateFrom", "date", "нет"], "children": []}]
        detail = diff_feature(old, new)
        [table] = detail["tables"]
        assert table["added_fields"] == ["filter.dateFrom"]
        assert table["removed_fields"] == ["filter.status"]

    def test_table_added_in_new_version(self):
        old = _feature()
        new = _with_logic(
            _feature(),
            response_tables=[{"caption": "Ответ 200", "columns": [{"header": "Параметр"}], "fields": []}],
        )
        detail = diff_feature(old, new)
        assert {"section": "выходные параметры", "caption": "Ответ 200", "table": "added"} in detail["tables"]

    def test_steps_added_removed_changed(self):
        old = _feature()
        new = _feature()
        steps = new["structured_logic_json"]["logic_steps"]
        steps[1]["text"] = "Вернуть агрегированные данные"
        steps.append({"number": "3", "text": "Записать аудит", "children": [], "mapping_tables": []})
        detail = diff_feature(old, new)
        assert detail["steps"]["added"] == [{"number": "3", "text": "Записать аудит"}]
        assert detail["steps"]["removed"] == []
        assert detail["steps"]["changed"] == [
            {"number": "2", "old_text": "Вернуть данные", "new_text": "Вернуть агрегированные данные"}
        ]

    def test_dependency_change(self):
        old = _feature()
        new = _with_logic(
            _feature(),
            used_dependencies=[{"type": "external_api", "name": "/v1/wallet", "description": ""}],
        )
        detail = diff_feature(old, new)
        assert detail["dependencies"]["added"] == [{"type": "external_api", "name": "/v1/wallet"}]
        assert detail["dependencies"]["removed"] == [{"type": "db_table", "name": "credit_line"}]

    def test_step_mapping_table_change_names_the_step(self):
        table = {
            "caption": None,
            "columns": [{"header": "Поле"}, {"header": "Источник"}],
            "fields": [{"name": "amount", "cells": ["amount", "credit_line.limit"], "children": []}],
        }
        old = _feature()
        old["structured_logic_json"]["logic_steps"][1]["mapping_tables"] = [table]
        new = _feature()
        import copy

        changed_table = copy.deepcopy(table)
        changed_table["fields"][0]["cells"] = ["amount", "credit_line.available_limit"]
        new["structured_logic_json"]["logic_steps"][1]["mapping_tables"] = [changed_table]
        detail = diff_feature(old, new)
        [entry] = detail["tables"]
        assert entry["section"] == "шаг 2"
        assert entry["changed_fields"][0]["changes"] == [
            {"column": "Источник", "old": "credit_line.limit", "new": "credit_line.available_limit"}
        ]


class TestComputeSpecDiff:
    def test_added_removed_and_material_flag(self):
        prior = {"GET /v1/x": _feature()}
        current = {"GET /v1/y": _feature("GET /v1/y", endpoint="/v1/y")}
        diff = compute_spec_diff(prior, current, old_version=12, new_version=15)
        assert diff["added"] == ["GET /v1/y"]
        assert diff["removed"] == ["GET /v1/x"]
        assert diff["material"] is True
        assert diff["old_version"] == 12 and diff["new_version"] == 15

    def test_version_bump_without_material_change(self):
        prior = {"GET /v1/x": _feature()}
        current = {"GET /v1/x": _feature(summary="Слегка другая формулировка")}
        diff = compute_spec_diff(prior, current, old_version=12, new_version=13)
        assert diff["material"] is False
        assert [c["name"] for c in diff["changed"]] == ["GET /v1/x"]
        assert diff["unchanged"] == []

    def test_identical_versions(self):
        prior = {"GET /v1/x": _feature()}
        current = {"GET /v1/x": _feature()}
        diff = compute_spec_diff(prior, current)
        assert diff["material"] is False
        assert diff["changed"] == []
        assert diff["unchanged"] == ["GET /v1/x"]


class TestMergeReextractedFeature:
    def test_analysis_state_survives_reextraction(self):
        prior = _feature()
        prior.update({
            "gap_count": 3,
            "pending_gap_count": 1,
            "gaps_run_at": "2026-09-01T00:00:00+00:00",
            "test_case_count": 7,
            "bug_count": 2,
            "impl_status": "implemented",
            "impl_mr_url": "https://gitlab/mr/1",
        })
        extracted = _feature(summary="Новая версия")
        merged = merge_reextracted_feature(prior, extracted)
        assert merged["summary"] == "Новая версия"
        assert merged["gap_count"] == 3
        assert merged["test_case_count"] == 7
        assert merged["impl_mr_url"] == "https://gitlab/mr/1"

    def test_orphan_flag_cleared_on_redetection(self):
        prior = _feature()
        prior.update({"orphaned": True, "orphaned_at": "2026-09-01T00:00:00+00:00", "gap_count": 1})
        merged = merge_reextracted_feature(prior, _feature())
        assert "orphaned" not in merged
        assert "orphaned_at" not in merged
        assert merged["gap_count"] == 1

    def test_no_prior_returns_extracted(self):
        extracted = _feature()
        assert merge_reextracted_feature(None, extracted) is extracted
