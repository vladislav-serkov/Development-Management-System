from app.services.sql_runner import _returns_rows, split_sql_statements


def test_split_simple_statements():
    sql = "DELETE FROM flp_order.payment WHERE id = 1;\nINSERT INTO flp_order.payment (id) VALUES (1);"
    assert split_sql_statements(sql) == [
        "DELETE FROM flp_order.payment WHERE id = 1",
        "INSERT INTO flp_order.payment (id) VALUES (1)",
    ]


def test_split_ignores_semicolon_in_string_literal():
    sql = "INSERT INTO t (comment) VALUES ('a; b');SELECT 1"
    assert split_sql_statements(sql) == [
        "INSERT INTO t (comment) VALUES ('a; b')",
        "SELECT 1",
    ]


def test_split_handles_escaped_quotes():
    sql = "INSERT INTO t (name) VALUES ('it''s; fine'); SELECT 2"
    assert split_sql_statements(sql) == [
        "INSERT INTO t (name) VALUES ('it''s; fine')",
        "SELECT 2",
    ]


def test_split_ignores_semicolon_in_comments():
    sql = "-- cleanup; important\nDELETE FROM t; /* multi;\nline */ SELECT 1"
    assert split_sql_statements(sql) == [
        "-- cleanup; important\nDELETE FROM t",
        "/* multi;\nline */ SELECT 1",
    ]


def test_split_dollar_quoted_body():
    sql = "DO $$ BEGIN PERFORM 1; END $$; SELECT 3"
    assert split_sql_statements(sql) == [
        "DO $$ BEGIN PERFORM 1; END $$",
        "SELECT 3",
    ]


def test_split_drops_empty_trailing():
    assert split_sql_statements("SELECT 1;;\n;  ") == ["SELECT 1"]


def test_returns_rows_detection():
    assert _returns_rows("SELECT * FROM t")
    assert _returns_rows("  with x as (select 1) select * from x")
    assert _returns_rows("-- note\nSELECT 1")
    assert _returns_rows("DELETE FROM t WHERE id = 1 RETURNING id")
    assert not _returns_rows("DELETE FROM t WHERE id = 1")
    assert not _returns_rows("INSERT INTO t (id) VALUES (1)")
    assert not _returns_rows("UPDATE t SET x = 1")


def test_render_live_ddl_block():
    from app.services.test_cases import _render_live_ddl

    block = _render_live_ddl("bnpl_payment", {
        "purchase": [
            {"name": "id", "type": "uuid", "required": True},
            {"name": "has_initial_payment", "type": "boolean", "required": True},
            {"name": "rbo_id", "type": "bigint", "required": False},
        ],
    })
    assert "bnpl_payment.purchase" in block
    assert "has_initial_payment (boolean)" in block
    assert "rbo_id" in block
    # optional column must not land in the required list line
    required_line = next(l for l in block.splitlines() if "Обязательные колонки" in l)
    assert "rbo_id" not in required_line
