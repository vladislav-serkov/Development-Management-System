from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect as sa_inspect, text

from app.database import Base, engine
from app.routers.documents import router as documents_router

# Import models to register them with Base.metadata before create_all
import app.models.document  # noqa: F401
import app.models.registry  # noqa: F401


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with engine.begin() as conn:
        # Migrate: add structured_logic_json column if missing
        def _migrate(sync_conn):
            inspector = sa_inspect(sync_conn)
            try:
                columns = [c["name"] for c in inspector.get_columns("features")]
                if "structured_logic_json" not in columns:
                    sync_conn.execute(text("ALTER TABLE features ADD COLUMN structured_logic_json TEXT"))
            except Exception:
                pass  # Table doesn't exist yet, create_all will handle it

        try:
            await conn.run_sync(_migrate)
        except Exception:
            pass  # Table doesn't exist yet, create_all will handle it

        # Create all tables on startup
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Extract Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(documents_router)


@app.get("/")
async def health():
    return {"status": "ok", "service": "extract-agent"}
