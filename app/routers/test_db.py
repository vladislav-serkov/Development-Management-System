from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import sql_runner

router = APIRouter(prefix="/test-db", tags=["test-db"])


class ExecuteSqlRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=100_000)


@router.get("/status")
async def test_db_status():
    """Whether a test DB is configured, and where it points (no credentials)."""
    return sql_runner.test_db_info()


@router.post("/execute")
async def execute_sql(body: ExecuteSqlRequest):
    """Run a SQL script on the test stand DB in a single transaction."""
    if not sql_runner.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Тестовая БД не настроена — задайте TEST_DB_URL в .env",
        )
    return await sql_runner.execute_sql(body.sql)
