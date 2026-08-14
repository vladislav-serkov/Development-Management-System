import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.bugs import router as bugs_router
from app.routers.dependencies import router as dependencies_router
from app.routers.documents import router as documents_router
from app.routers.gaps import router as gaps_router
from app.routers.projects import router as projects_router
from app.routers.rules import router as rules_router
from app.routers.tasks import router as tasks_router
from app.routers.test_cases import router as test_cases_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Alembic's env.py opens its own (sync-wrapped async) connection; run it
    # in a thread so it doesn't collide with the running event loop.
    await asyncio.to_thread(_run_migrations)
    if settings.anthropic_api_key in ("", "sk-ant-xxx"):
        logger.warning(
            "ANTHROPIC_API_KEY is not configured — Claude-backed features will fail. "
            "Set it in .env before serving traffic."
        )
    yield
    from app.db import dispose_engine

    await dispose_engine()


app = FastAPI(title="Extract Agent", lifespan=lifespan)

cors_origins = settings.parsed_cors_origins()
allow_all_origins = not cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(dependencies_router)
app.include_router(gaps_router)
app.include_router(test_cases_router)
app.include_router(bugs_router)
app.include_router(rules_router)
app.include_router(tasks_router)


@app.get("/")
async def health():
    return {"status": "ok", "service": "extract-agent"}
