import pytest

from app.config import settings
from app.services import sql_runner
from app.services.sql_runner import _returns_rows, destructive_statement, split_sql_statements

# How a generated sql_setup may start: on the shared stand this empties the table for everyone
WIPE = "DELETE FROM shop.orders;"


# --- statements the shared stand must never run -----------------------------


@pytest.mark.parametrize("sql,said", [
    (WIPE, "DELETE без WHERE"),
    ("delete from shop.orders", "DELETE без WHERE"),
    ("UPDATE shop.orders SET status = 'X'", "UPDATE без WHERE"),
    ("TRUNCATE shop.orders", "TRUNCATE отклонён"),
    ("truncate table shop.orders, shop.items cascade", "TRUNCATE отклонён"),
    ("DROP TABLE shop.orders", "DROP отклонён"),
    ("ALTER TABLE shop.orders ADD COLUMN x int", "ALTER отклонён"),
    ("DELETE FROM shop.orders WHERE true", "WHERE не зависит от данных строки"),
    ("DELETE FROM shop.orders WHERE 1=1", "WHERE не зависит от данных строки"),
    ("UPDATE shop.orders SET status = 'X' WHERE 1 = 1 RETURNING id", "WHERE не зависит от данных строки"),
])
def test_destructive_statement_is_refused(sql, said):
    idx, reason = destructive_statement(sql)
    assert idx == 0
    assert said in reason and "стенд общий" in reason


@pytest.mark.parametrize("sql", [
    # a WHERE that only looks like one
    "-- cleanup\nDELETE FROM shop.orders",
    "DELETE /* where id = 1 */ FROM shop.orders -- where id = 1",
    'DELETE FROM shop.orders "where"',
    "UPDATE shop.orders SET note = 'where id = 1'",
    "UPDATE shop.orders SET total = (SELECT sum(x) FROM shop.items WHERE order_id = 1)",
    "DELETE FROM shop.orders USING (SELECT id FROM shop.items WHERE id = 1) i",
    # a condition that holds for every row
    "DELETE FROM shop.orders WHERE (1 = 1)",
    "DELETE FROM shop.orders WHERE 'a' = 'a'",
    "DELETE FROM shop.orders WHERE NOT false",
    "DELETE FROM shop.orders WHERE 1=1 AND 2=2",
    "DELETE FROM shop.orders WHERE id = 5 OR 1=1",
    "DELETE FROM shop.orders WHERE id = id",
    "DELETE FROM shop.orders WHERE 1=1 -- AND id = 5",
    # wrapped in something else
    "WITH gone AS (DELETE FROM shop.orders RETURNING id) SELECT * FROM gone WHERE id = 1",
    "EXPLAIN ANALYZE DELETE FROM shop.orders",
    "DO $$ BEGIN DELETE FROM shop.orders; END $$",
    "DO $body$ BEGIN IF true THEN TRUNCATE shop.orders; END IF; END $body$ LANGUAGE plpgsql",
])
def test_destructive_statement_is_refused_however_it_is_written(sql):
    assert destructive_statement(sql) is not None


@pytest.mark.parametrize("sql", [
    "DELETE FROM shop.orders WHERE id = 'a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0'",
    'DELETE FROM flp_order."order" WHERE id = 1 RETURNING id',
    "DELETE FROM shop.orders WHERE external_id LIKE 'qa-st-%'",
    "DELETE FROM shop.orders WHERE id IN (1, 2) AND created_at < now() - interval '1 day'",
    "DELETE FROM shop.orders WHERE 1=1 AND id = 5",
    "DELETE FROM shop.orders o USING shop.items i WHERE o.id = i.order_id AND i.sku = 'X'",
    "UPDATE shop.orders SET status = 'X', deleted = true WHERE id = 5",
    'UPDATE "shop"."orders" SET updated_at = now() WHERE "id" = 1',
    "INSERT INTO shop.orders (id) VALUES (1)",
    "INSERT INTO shop.orders (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = 1",
    "SELECT * FROM shop.orders",
    "SELECT * FROM shop.orders WHERE id = 1 FOR UPDATE",
    "WITH gone AS (DELETE FROM shop.orders WHERE id = 1 RETURNING id) SELECT * FROM gone",
    "DO $$ BEGIN DELETE FROM shop.orders WHERE id = 1; END $$",
])
def test_ordinary_statement_passes(sql):
    assert destructive_statement(sql) is None


@pytest.mark.parametrize("sql", [
    "INSERT INTO shop.log (note) VALUES ('очистка; DELETE FROM shop.orders; DROP TABLE shop.orders')",
    "INSERT INTO shop.log (note) VALUES ('it''s; TRUNCATE shop.orders')",
    "INSERT INTO shop.log (note) VALUES ($$ {\"sql\": \"DELETE FROM shop.orders;\"} $$)",
    "SELECT 'TRUNCATE', \"drop\" FROM shop.log WHERE action = 'ALTER'",
    "INSERT INTO shop.orders (id) VALUES (1); -- потом: DELETE FROM shop.orders; DROP TABLE shop.orders",
    "/* DELETE FROM shop.orders; */ SELECT 1",
])
def test_keywords_inside_literals_and_comments_are_not_statements(sql):
    assert destructive_statement(sql) is None


def test_refusal_points_at_the_statement_and_says_why():
    idx, reason = destructive_statement(f"INSERT INTO shop.orders (id) VALUES (1);\n-- чистим\n{WIPE}")
    assert idx == 1
    assert reason == (
        "DELETE без WHERE отклонён: он удалит все строки таблицы, а тестовый стенд общий. "
        "Ограничьте оператор условием по идентификаторам своих записей. "
        "Оператор: DELETE FROM shop.orders"
    )


# --- the executor refuses before it connects --------------------------------


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self):
        self.executed: list[str] = []

    def transaction(self, **kwargs):
        return _FakeTransaction()

    async def execute(self, stmt):
        self.executed.append(stmt)
        return "OK"

    async def fetch(self, stmt):
        self.executed.append(stmt)
        return []

    async def close(self):
        pass


@pytest.fixture
def stand(monkeypatch):
    """A configured test DB that is never really contacted: connections are counted and faked."""
    connections: list[_FakeConnection] = []

    async def connect(*args, **kwargs):
        connections.append(_FakeConnection())
        return connections[-1]

    monkeypatch.setattr(settings, "test_db_url", "postgresql://u:p@stand.invalid/db")
    monkeypatch.setattr(sql_runner.asyncpg, "connect", connect)
    return connections


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("sql", [
    WIPE,
    "UPDATE shop.orders SET status = 'X'",
    "TRUNCATE shop.orders",
    "DROP TABLE shop.orders",
    "ALTER TABLE shop.orders ADD COLUMN x int",
    "DELETE FROM shop.orders WHERE true",
    "DELETE FROM shop.orders WHERE 1=1",
])
async def test_execute_refuses_without_connecting(stand, sql, readonly):
    result = await sql_runner.execute_sql(sql, readonly=readonly)

    assert stand == []
    assert result["results"] == [] and result["failed_statement"] == 0
    assert "отклонён" in result["error"]


async def test_execute_refuses_the_whole_script_not_only_the_bad_statement(stand):
    result = await sql_runner.execute_sql(f"INSERT INTO shop.orders (id) VALUES (1);\n{WIPE}\nSELECT 1;")

    # nothing ran, not even the harmless INSERT before the DELETE
    assert stand == []
    assert result == {
        "results": [],
        "error": destructive_statement(WIPE)[1],
        "failed_statement": 1,
        "duration_ms": 0,
    }


async def test_execute_runs_an_ordinary_script(stand):
    script = (
        "DELETE FROM shop.orders WHERE id = 1;\n"
        "INSERT INTO shop.orders (id, note) VALUES (1, 'DELETE FROM shop.orders; TRUNCATE');\n"
        "SELECT * FROM shop.orders WHERE id = 1;"
    )

    result = await sql_runner.execute_sql(script)

    assert result["error"] is None and result["failed_statement"] is None
    assert len(stand) == 1 and stand[0].executed == split_sql_statements(script)


async def test_dry_run_never_sends_a_destructive_script_even_to_roll_it_back(stand):
    safe = "DELETE FROM shop.orders WHERE id = 1; INSERT INTO shop.orders (id) VALUES (1)"

    errors = await sql_runner.dry_run_scripts([WIPE, safe, "TRUNCATE shop.orders"])

    assert errors[0].startswith("DELETE без WHERE отклонён") and errors[1] is None
    assert errors[2].startswith("TRUNCATE отклонён")
    assert len(stand) == 1 and stand[0].executed == split_sql_statements(safe)


async def test_dry_run_of_destructive_scripts_alone_does_not_connect(stand):
    errors = await sql_runner.dry_run_scripts([WIPE, "UPDATE shop.orders SET status = 'X'"])

    assert stand == []
    assert all(error and "без WHERE отклонён" in error for error in errors)


# --- splitting and row detection --------------------------------------------


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
